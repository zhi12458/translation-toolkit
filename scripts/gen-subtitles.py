#!/usr/bin/env python3
"""Generate Chinese, English, and bilingual SRT/VTT from toolkit line mappings."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Sequence

from _toolkit_io import ToolkitError, atomic_write_text, resolve_input, sha256_file


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_directory")
    parser.add_argument("--source-map", default="source-map.json")
    parser.add_argument("--output-dir")
    return parser.parse_args(argv)


def timestamp(seconds: float, *, vtt: bool) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    separator = "." if vtt else ","
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"


def load_map(path: Path, source_lines: list[str]) -> list[dict]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ToolkitError("source-map.json is missing or invalid") from exc
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ToolkitError("source-map.json has an unsupported schema")
    segments = document.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ToolkitError("source-map.json must contain segments")
    previous_end = 0.0
    seen_ids: set[str] = set()
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            raise ToolkitError(f"source-map segment {index} is invalid")
        identifier = str(segment.get("id", "")).strip()
        start, end, line = segment.get("start"), segment.get("end"), segment.get("source_line")
        if not identifier or identifier in seen_ids:
            raise ToolkitError(f"source-map segment {index} has an invalid id")
        if not isinstance(start, (int, float)) or not math.isfinite(start) or start < 0:
            raise ToolkitError(f"source-map segment {identifier} has an invalid start")
        if not isinstance(end, (int, float)) or not math.isfinite(end) or end <= start:
            raise ToolkitError(f"source-map segment {identifier} has an invalid end")
        if start < previous_end:
            raise ToolkitError(f"source-map segment {identifier} overlaps the previous segment")
        if not isinstance(line, int) or isinstance(line, bool) or line < 1 or line > len(source_lines):
            raise ToolkitError(f"source-map segment {identifier} has an invalid source_line")
        if not source_lines[line - 1].strip():
            raise ToolkitError(f"source-map segment {identifier} points to a blank source line")
        previous_end = float(end)
        seen_ids.add(identifier)
    return segments


def render(cues: list[tuple[float, float, str]], *, vtt: bool) -> str:
    parts = ["WEBVTT\n"] if vtt else []
    for index, (start, end, text) in enumerate(cues, 1):
        if not vtt:
            parts.append(str(index))
        parts.append(f"{timestamp(start, vtt=vtt)} --> {timestamp(end, vtt=vtt)}")
        parts.append(text)
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        project = Path(args.project_directory).expanduser().resolve()
        if not project.is_dir():
            raise ToolkitError(f"project directory does not exist: {project}")
        source = resolve_input(project / "source.dj", "source.dj")
        target = resolve_input(project / "target.dj", "target.dj")
        map_path = resolve_input(project / args.source_map, "source-map.json")
        output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else project
        if not output_dir.is_dir():
            raise ToolkitError(f"output directory does not exist: {output_dir}")
        source_lines = source.read_text(encoding="utf-8").splitlines()
        target_lines = target.read_text(encoding="utf-8").splitlines()
        if len(source_lines) != len(target_lines):
            raise ToolkitError("source.dj and target.dj line counts differ")
        segments = load_map(map_path, source_lines)
        source_cues: list[tuple[float, float, str]] = []
        target_cues: list[tuple[float, float, str]] = []
        bilingual_cues: list[tuple[float, float, str]] = []
        for segment in segments:
            line = segment["source_line"] - 1
            start, end = float(segment["start"]), float(segment["end"])
            zh, en = source_lines[line].strip(), target_lines[line].strip()
            if not en:
                raise ToolkitError(f"target line {line + 1} is empty for subtitle segment {segment['id']}")
            source_cues.append((start, end, zh))
            target_cues.append((start, end, en))
            bilingual_cues.append((start, end, f"{zh}\n{en}"))
        outputs = {
            "source.srt": render(source_cues, vtt=False),
            "target.srt": render(target_cues, vtt=False),
            "bilingual.srt": render(bilingual_cues, vtt=False),
            "source.vtt": render(source_cues, vtt=True),
            "target.vtt": render(target_cues, vtt=True),
            "bilingual.vtt": render(bilingual_cues, vtt=True),
        }
        for name, body in outputs.items():
            atomic_write_text(output_dir / name, body)
    except (ToolkitError, UnicodeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for name in sorted(outputs):
        path = output_dir / name
        print(f"{path}\tsha256={sha256_file(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
