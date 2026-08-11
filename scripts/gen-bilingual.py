#!/usr/bin/env python3
"""Generate a bilingual .dj file from source (Chinese) and target (English) .dj files.

Usage:
    gen-bilingual.py source.dj target.dj --output bilingual.dj
    gen-bilingual.py source.dj target.dj  # stdout for pipelines only

Prefer --output when replacing a file: shell redirection truncates its target
before this program can validate source/target alignment.

Output format: source line, target line, blank line, repeated. Paragraph breaks
are preserved: blank lines in the input produce blank lines in the output.
"""

import argparse
import os
import stat
import sys
import tempfile
from pathlib import Path


def is_blank(line):
    """Return True for structural blank lines, including whitespace-only lines."""
    return not line.strip()


def validate_alignment(src_lines, tgt_lines):
    """Validate the invariants required before any bilingual output is emitted."""
    if not any(not is_blank(line) for line in src_lines):
        raise ValueError("Source is empty or contains only blank lines")
    if not any(not is_blank(line) for line in tgt_lines):
        raise ValueError("Target is empty or contains only blank lines")
    if len(src_lines) != len(tgt_lines):
        raise ValueError(
            f"Line count mismatch: source={len(src_lines)} target={len(tgt_lines)}"
        )

    mismatches = [
        i
        for i, (source_line, target_line) in enumerate(
            zip(src_lines, tgt_lines), start=1
        )
        if is_blank(source_line) != is_blank(target_line)
    ]
    if mismatches:
        shown = ", ".join(str(i) for i in mismatches[:10])
        suffix = "" if len(mismatches) <= 10 else f" (+{len(mismatches) - 10} more)"
        raise ValueError(
            f"Blank-line alignment mismatch at line(s): {shown}{suffix}"
        )


def generate_bilingual_lines(src_lines, tgt_lines):
    """Return canonical bilingual lines after validating source/target alignment."""
    validate_alignment(src_lines, tgt_lines)

    out = []
    for source_line, target_line in zip(src_lines, tgt_lines):
        if is_blank(source_line):
            out.append("")
        else:
            out.extend([source_line, target_line, ""])
    return out


def render_bilingual_text(src_lines, tgt_lines):
    """Render a complete bilingual document in memory before any output."""
    lines = generate_bilingual_lines(src_lines, tgt_lines)
    return "\n".join(lines) + "\n"


def paths_refer_to_same_file(first, second):
    """Compare existing files by identity and new paths by resolved location."""
    try:
        return os.path.samefile(first, second)
    except OSError:
        return Path(first).resolve() == Path(second).resolve()


def atomic_write_text(output_path, text):
    """Atomically replace output_path after a durable same-directory write."""
    output_path = Path(output_path)
    parent = output_path.parent
    if not parent.is_dir():
        raise OSError(f"Output directory does not exist: {parent}")
    if output_path.exists() and not output_path.is_file():
        raise OSError(f"Output path is not a regular file: {output_path}")

    existing_mode = (
        stat.S_IMODE(output_path.stat().st_mode)
        if output_path.exists()
        else None
    )
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            dir=parent,
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(text)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        # NamedTemporaryFile creates a private 0600 file. Keep that safe
        # default for a new manuscript; preserve explicit permissions only
        # when replacing an existing output.
        if existing_mode is not None:
            os.chmod(temp_path, existing_mode)
        os.replace(temp_path, output_path)
        temp_path = None

        # The file data is already fsynced. Persist the directory entry where
        # the platform supports directory descriptors; failure here is best
        # effort because the atomic replacement has already succeeded.
        if hasattr(os, "O_DIRECTORY"):
            try:
                directory_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError:
                pass
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        help="atomically write FILE instead of emitting bilingual text to stdout",
    )
    args = parser.parse_args()

    src_path = args.source
    tgt_path = args.target

    if not src_path.is_file():
        print(f"Source file not found: {src_path}", file=sys.stderr)
        return 1
    if not tgt_path.is_file():
        print(f"Target file not found: {tgt_path}", file=sys.stderr)
        return 1
    if args.output is not None and (
        paths_refer_to_same_file(args.output, src_path)
        or paths_refer_to_same_file(args.output, tgt_path)
    ):
        print("Output path must differ from source and target", file=sys.stderr)
        return 1

    src_lines = src_path.read_text(encoding="utf-8").splitlines()
    tgt_lines = tgt_path.read_text(encoding="utf-8").splitlines()

    try:
        rendered = render_bilingual_text(src_lines, tgt_lines)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.output is None:
        sys.stdout.write(rendered)
        return 0

    try:
        atomic_write_text(args.output, rendered)
    except OSError as exc:
        print(f"Failed to write output atomically: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
