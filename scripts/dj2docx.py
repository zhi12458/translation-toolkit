#!/usr/bin/env python3
"""Render target or bilingual Djot to DOCX atomically through Pandoc."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from _toolkit_io import (
    ToolkitError,
    ensure_docx_cjk_fonts,
    resolve_input,
    resolve_output,
    run_pandoc,
    sha256_file,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--kind", choices=("target", "bilingual"), required=True)
    parser.add_argument("--reference-doc")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        source = resolve_input(args.input, f"{args.kind} Djot")
        inputs = [source]
        pandoc_args = ["-f", "djot", "-t", "docx"]
        if args.reference_doc:
            reference = resolve_input(args.reference_doc, "reference DOCX")
            inputs.append(reference)
            pandoc_args.extend(["--reference-doc", str(reference)])
        output = resolve_output(args.output, inputs)
        if output.suffix.casefold() != ".docx":
            raise ToolkitError("output must have a .docx extension")
        run_pandoc(source, output, *pandoc_args)
        ensure_docx_cjk_fonts(output)
    except ToolkitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"{output}\tsha256={sha256_file(output)}\tkind={args.kind}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
