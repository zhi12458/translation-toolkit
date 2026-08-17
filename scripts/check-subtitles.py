#!/usr/bin/env python3
"""Run deterministic timing, coverage, line-length, and reading-speed subtitle QA."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from _toolkit_io import ToolkitError, atomic_write_text, resolve_input, sha256_file


TIMING = re.compile(r"^(\d{2}):(\d{2}):(\d{2})[,.](\d{3}) --> (\d{2}):(\d{2}):(\d{2})[,.](\d{3})$")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_directory")
    parser.add_argument("--output", required=True)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--not-applicable", action="store_true")
    parser.add_argument("--max-english-line", type=int, default=42)
    parser.add_argument("--max-chinese-line", type=int, default=22)
    parser.add_argument("--max-english-cps", type=float, default=20.0)
    return parser.parse_args(argv)


def seconds(parts: tuple[str, ...]) -> float:
    h, m, s, ms = (int(value) for value in parts)
    return h * 3600 + m * 60 + s + ms / 1000


def parse_srt(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    blocks = [block for block in text.strip().split("\n\n") if block.strip()]
    cues: list[dict] = []
    for expected, block in enumerate(blocks, 1):
        lines = block.splitlines()
        if len(lines) < 3 or lines[0].strip() != str(expected):
            raise ToolkitError(f"invalid SRT cue structure in {path.name} at cue {expected}")
        match = TIMING.fullmatch(lines[1].strip())
        if match is None:
            raise ToolkitError(f"invalid SRT timing in {path.name} at cue {expected}")
        start, end = seconds(match.groups()[:4]), seconds(match.groups()[4:])
        cues.append({"start": start, "end": end, "lines": lines[2:]})
    return cues


def parse_vtt(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not text.startswith("WEBVTT\n"):
        raise ToolkitError(f"invalid VTT header in {path.name}")
    blocks = [block for block in text[len("WEBVTT\n") :].strip().split("\n\n") if block.strip()]
    cues: list[dict] = []
    for expected, block in enumerate(blocks, 1):
        lines = block.splitlines()
        if len(lines) < 2:
            raise ToolkitError(f"invalid VTT cue structure in {path.name} at cue {expected}")
        match = TIMING.fullmatch(lines[0].strip())
        if match is None:
            raise ToolkitError(f"invalid VTT timing in {path.name} at cue {expected}")
        cues.append(
            {
                "start": seconds(match.groups()[:4]),
                "end": seconds(match.groups()[4:]),
                "lines": lines[1:],
            }
        )
    return cues


def check(name: str, ok: bool, detail: str) -> dict:
    return {"name": name, "status": "PASS" if ok else "FAIL", "detail": detail}


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    output = Path(args.output).expanduser().resolve()
    if args.not_applicable:
        report = {
            "schema_version": 1,
            "status": "not_applicable",
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "checks": [{"name": "subtitle_input", "status": "N/A", "detail": "project input is not timed media"}],
        }
        try:
            atomic_write_text(output, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        except OSError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(output)
        return 0
    try:
        project = Path(args.project_directory).expanduser().resolve()
        map_path = resolve_input(project / "source-map.json", "source-map.json")
        map_document = json.loads(map_path.read_text(encoding="utf-8"))
        expected = len(map_document.get("segments", []))
        names = (
            "source.srt",
            "target.srt",
            "bilingual.srt",
            "source.vtt",
            "target.vtt",
            "bilingual.vtt",
        )
        files = {name: resolve_input(project / name, name) for name in names}
        parsed = {
            name: parse_srt(path) if path.suffix == ".srt" else parse_vtt(path)
            for name, path in files.items()
        }
        checks: list[dict] = []
        for name, cues in parsed.items():
            checks.append(check(f"{name}:coverage", len(cues) == expected, f"cues={len(cues)} expected={expected}"))
            ordered = all(cue["end"] > cue["start"] and (i == 0 or cue["start"] >= cues[i - 1]["end"]) for i, cue in enumerate(cues))
            checks.append(check(f"{name}:timing", ordered, "timestamps are ordered and non-overlapping" if ordered else "timestamps overlap or have non-positive duration"))
        aligned = all(
            len(parsed[name]) == len(parsed["source.srt"])
            and all(
                left["start"] == right["start"] and left["end"] == right["end"]
                for left, right in zip(parsed["source.srt"], parsed[name])
            )
            for name in names[1:]
        )
        checks.append(check("bilingual_timing_alignment", aligned, "all subtitle variants share identical timings" if aligned else "subtitle variant timings differ"))
        mirror_ok = all(
            parsed[f"{stem}.srt"] == parsed[f"{stem}.vtt"]
            for stem in ("source", "target", "bilingual")
        )
        checks.append(
            check(
                "srt_vtt_content_alignment",
                mirror_ok,
                "SRT and VTT variants have identical cues" if mirror_ok else "SRT and VTT variants differ",
            )
        )
        zh_ok = all(len(line) <= args.max_chinese_line for cue in parsed["source.srt"] for line in cue["lines"])
        en_ok = all(len(line) <= args.max_english_line for cue in parsed["target.srt"] for line in cue["lines"])
        cps_ok = all(
            sum(len(line) for line in cue["lines"]) / (cue["end"] - cue["start"]) <= args.max_english_cps
            for cue in parsed["target.srt"]
        )
        checks.extend([
            check("chinese_line_length", zh_ok, f"maximum={args.max_chinese_line}"),
            check("english_line_length", en_ok, f"maximum={args.max_english_line}"),
            check("english_reading_speed", cps_ok, f"maximum={args.max_english_cps:g} characters/second"),
        ])
        status = "pass" if all(item["status"] == "PASS" for item in checks) else "fail"
        report = {
            "schema_version": 1,
            "status": status,
            "strict": args.strict,
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "source_map_sha256": sha256_file(map_path),
            "subtitle_sha256": {name: sha256_file(path) for name, path in files.items()},
            "checks": checks,
        }
        atomic_write_text(output, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    except (ToolkitError, OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"{output}\tstatus={status}\tsha256={sha256_file(output)}")
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
