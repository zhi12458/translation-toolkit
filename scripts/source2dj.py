#!/usr/bin/env python3
"""Normalize TXT, Markdown, or Djot source into an atomic UTF-8 source.dj."""

from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path
from typing import Sequence

from _toolkit_io import (
    ToolkitError,
    atomic_write_text,
    resolve_input,
    resolve_output,
    run_pandoc,
    sha256_file,
)


def normalize_plain_text(text: str) -> str:
    if "\x00" in text:
        raise ToolkitError("source contains a NUL byte")
    normalized = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    return normalized.rstrip("\n") + "\n"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument(
        "--format",
        choices=("auto", "txt", "markdown", "djot"),
        default="auto",
    )
    return parser.parse_args(argv)


def detected_format(path: Path, requested: str) -> str:
    if requested != "auto":
        return requested
    suffix = path.suffix.casefold()
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix in {".dj", ".djot"}:
        return "djot"
    if suffix == ".txt":
        return "txt"
    raise ToolkitError(f"cannot infer source format from extension: {path.suffix or '(none)'}")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        source = resolve_input(args.input, "source")
        output = resolve_output(args.output, [source])
        source_format = detected_format(source, args.format)
        if source_format == "markdown":
            run_pandoc(source, output, "-f", "commonmark_x", "-t", "djot", "--wrap=none")
        else:
            try:
                text = source.read_text(encoding="utf-8")
            except UnicodeError as exc:
                raise ToolkitError("source is not valid UTF-8") from exc
            atomic_write_text(output, normalize_plain_text(text))
        if output.stat().st_size == 0:
            raise ToolkitError("normalized source is empty")
    except ToolkitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"{output}\tsha256={sha256_file(output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
