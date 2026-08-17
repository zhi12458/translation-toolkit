#!/usr/bin/env python3
"""Convert DOCX to Djot atomically through Pandoc on macOS or Windows."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from _toolkit_io import ToolkitError, resolve_input, resolve_output, run_pandoc, sha256_file


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("output")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        source = resolve_input(args.input, "DOCX source")
        if source.suffix.casefold() != ".docx":
            raise ToolkitError("DOCX source must have a .docx extension")
        output = resolve_output(args.output, [source])
        run_pandoc(source, output, "-f", "docx", "-t", "djot", "--wrap=none")
    except ToolkitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"{output}\tsha256={sha256_file(output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
