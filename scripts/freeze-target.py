#!/usr/bin/env python3
"""Validate and atomically freeze a Sol-authored Djot draft as target.dj."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _toolkit_io import ToolkitError, atomic_write_text, resolve_input, resolve_output


def read_lines(path: Path, label: str) -> tuple[str, list[str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ToolkitError(f"{label} must be UTF-8") from exc
    if "\x00" in text:
        raise ToolkitError(f"{label} contains a NUL byte")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.endswith("\n"):
        normalized += "\n"
    return normalized, normalized.splitlines()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="toolkit-frozen source.dj")
    parser.add_argument("draft", help="Sol-authored UTF-8 Djot draft")
    parser.add_argument("--output", required=True, help="canonical target.dj")
    args = parser.parse_args()
    try:
        source = resolve_input(args.source, "source")
        draft = resolve_input(args.draft, "draft")
        output = resolve_output(args.output, [source, draft])
        target_text, target_lines = read_lines(draft, "draft")
        _, source_lines = read_lines(source, "source")
        if not any(line.strip() for line in target_lines):
            raise ToolkitError("draft is empty")
        if len(source_lines) != len(target_lines):
            raise ToolkitError(
                f"line count mismatch: source={len(source_lines)} target={len(target_lines)}"
            )
        mismatches = [
            number
            for number, (source_line, target_line) in enumerate(
                zip(source_lines, target_lines), start=1
            )
            if bool(source_line.strip()) != bool(target_line.strip())
        ]
        if mismatches:
            shown = ", ".join(str(number) for number in mismatches[:10])
            raise ToolkitError(f"blank-line alignment mismatch at line(s): {shown}")
        atomic_write_text(output, target_text)
        print(f"Frozen target: {output}")
        return 0
    except (OSError, ToolkitError) as exc:
        print(f"freeze-target: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
