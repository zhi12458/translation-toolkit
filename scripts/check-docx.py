#!/usr/bin/env python3
"""Verify a generated DOCX is readable and text-faithful to its Djot input."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

from _toolkit_io import ToolkitError, atomic_write_text, resolve_input, resolve_output, sha256_file


def pandoc_plain(path: Path) -> bytes:
    try:
        completed = subprocess.run(
            ["pandoc", str(path), "-t", "plain"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ToolkitError("pandoc is required but was not found on PATH") from exc
    if completed.returncode:
        raise ToolkitError(f"pandoc could not read {path.name}")
    return completed.stdout.replace(b"\r\n", b"\n").rstrip() + b"\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("djot")
    parser.add_argument("docx")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        djot = resolve_input(args.djot, "Djot input")
        docx = resolve_input(args.docx, "DOCX output")
        output = resolve_output(args.output, [djot, docx])
        try:
            with zipfile.ZipFile(docx) as archive:
                names = set(archive.namelist())
                if "word/document.xml" not in names or not archive.read("word/document.xml").strip():
                    raise ToolkitError("DOCX has no nonempty word/document.xml")
                bad_member = archive.testzip()
                if bad_member:
                    raise ToolkitError("DOCX ZIP integrity check failed")
        except zipfile.BadZipFile as exc:
            raise ToolkitError("DOCX is not a valid ZIP package") from exc
        expected = pandoc_plain(djot)
        actual = pandoc_plain(docx)
        match = expected == actual
        report = {
            "schema_version": 1,
            "status": "PASS" if match else "FAIL",
            "djot_absolute_path": str(djot),
            "docx_absolute_path": str(docx),
            "djot_sha256": sha256_file(djot),
            "docx_sha256": sha256_file(docx),
            "expected_plain_sha256": hashlib.sha256(expected).hexdigest(),
            "actual_plain_sha256": hashlib.sha256(actual).hexdigest(),
            "zip_integrity": "PASS",
            "text_fidelity": "PASS" if match else "FAIL",
        }
        atomic_write_text(output, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"status": report["status"], "output": str(output)}))
        return 0 if match else 1
    except (OSError, ToolkitError) as exc:
        print(f"check-docx: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
