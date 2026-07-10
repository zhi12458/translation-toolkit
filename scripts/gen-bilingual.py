#!/usr/bin/env python3
"""Generate a bilingual .dj file from source (Chinese) and target (English) .dj files.

Usage:
    gen-bilingual.py source.dj target.dj > bilingual.dj

Output format: source line, target line, blank line, repeated. Paragraph breaks
are preserved: blank lines in the input produce blank lines in the output.
"""

import sys
from pathlib import Path


def main():
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        sys.exit(1)

    src_path = Path(sys.argv[1])
    tgt_path = Path(sys.argv[2])

    if not src_path.exists():
        print(f"Source file not found: {src_path}", file=sys.stderr)
        sys.exit(1)
    if not tgt_path.exists():
        print(f"Target file not found: {tgt_path}", file=sys.stderr)
        sys.exit(1)

    src_lines = src_path.read_text(encoding="utf-8").splitlines()
    tgt_lines = tgt_path.read_text(encoding="utf-8").splitlines()

    if len(src_lines) != len(tgt_lines):
        print(
            f"Line count mismatch: source={len(src_lines)} target={len(tgt_lines)}",
            file=sys.stderr,
        )
        sys.exit(1)

    out = []
    for s, t in zip(src_lines, tgt_lines):
        if s == "":
            out.append("")
        else:
            out.append(s)
            out.append(t)
            out.append("")

    # Ensure the output always ends with a single trailing blank line to match
    # the project convention: source, target, blank, source, target, blank...
    if out and out[-1] != "":
        out.append("")

    sys.stdout.write("\n".join(out))
    if out:
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
