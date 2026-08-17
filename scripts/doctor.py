#!/usr/bin/env python3
"""Read-only dependency checks for the MPI translation toolkit."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


@dataclass(frozen=True)
class ToolSpec:
    name: str
    command: str
    required: bool
    version_args: tuple[str, ...] = ("--version",)
    minimum_version: tuple[int, int] | None = None


REQUIRED_TOOLS = (
    ToolSpec("python", "python3", True, minimum_version=(3, 11)),
    ToolSpec("git", "git", True),
    ToolSpec("sqlite3", "sqlite3", True),
)

OPTIONAL_TOOLS = (
    ToolSpec("uv", "uv", False),
    ToolSpec("fish", "fish", False),
    ToolSpec("pandoc", "pandoc", False),
    ToolSpec("typst", "typst", False),
    ToolSpec("pdftotext", "pdftotext", False, ("-v",)),
    ToolSpec("jq", "jq", False),
    ToolSpec("omp", "omp", False),
    ToolSpec("herdr", "herdr", False),
)

STRATEGY_C_TOOLS = (
    ToolSpec("python", "python3", True, minimum_version=(3, 11)),
    ToolSpec("git", "git", True),
    ToolSpec("pandoc", "pandoc", True),
)

REPOSITORY = Path(__file__).resolve().parents[1]
STRATEGY_C_FILES = (
    "AGENTS.md",
    "terms-database/search.py",
    "terms-database/termlib.sqlite",
    "scripts/source2dj.py",
    "scripts/docx2dj.py",
    "scripts/build-term-map.py",
    "scripts/deepseek-source-analysis.py",
    "scripts/gen-bilingual.py",
    "scripts/check-translation.py",
    "scripts/dj2docx.py",
    "scripts/gen-subtitles.py",
    "scripts/check-subtitles.py",
    "schemas/term-map.schema.json",
    "schemas/source-map.schema.json",
)


def _read_version(path: str, args: Sequence[str]) -> tuple[str | None, str | None]:
    """Return the first version line without changing system state."""
    try:
        completed = subprocess.run(
            [path, *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, str(exc)

    combined = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    first_line = next((line.strip() for line in combined.splitlines() if line.strip()), None)
    if completed.returncode != 0:
        detail = f"version command exited {completed.returncode}"
        if first_line:
            detail = f"{detail}: {first_line}"
        return None, detail
    return first_line, None


def inspect_tool(spec: ToolSpec) -> dict[str, Any]:
    path = shutil.which(spec.command)
    version: str | None = None
    error: str | None = None
    if path is not None:
        version, error = _read_version(path, spec.version_args)
        if error is None and spec.minimum_version is not None:
            match = re.search(r"\bPython\s+(\d+)\.(\d+)(?:\.\d+)?\b", version or "")
            if match is None:
                error = f"could not parse required version from: {version or 'no output'}"
            else:
                actual = (int(match.group(1)), int(match.group(2)))
                if actual < spec.minimum_version:
                    required = ".".join(str(part) for part in spec.minimum_version)
                    error = f"requires Python >= {required}; found {version}"

    return {
        "name": spec.name,
        "command": spec.command,
        "required": spec.required,
        "ok": path is not None and error is None,
        "path": path,
        "version": version,
        "minimum_version": (
            ".".join(str(part) for part in spec.minimum_version)
            if spec.minimum_version is not None
            else None
        ),
        "error": error,
    }


def collect_checks(
    *, minimal: bool = False, strategy_c: bool = False
) -> list[dict[str, Any]]:
    specs = STRATEGY_C_TOOLS if strategy_c else REQUIRED_TOOLS if minimal else REQUIRED_TOOLS + OPTIONAL_TOOLS
    checks = [inspect_tool(spec) for spec in specs]
    if strategy_c:
        for relative in STRATEGY_C_FILES:
            path = REPOSITORY / relative
            checks.append(
                {
                    "name": f"file:{relative}",
                    "command": None,
                    "required": True,
                    "ok": path.is_file() and path.stat().st_size > 0,
                    "path": str(path.resolve()),
                    "version": None,
                    "minimum_version": None,
                    "error": None if path.is_file() and path.stat().st_size > 0 else "required strategy-C file is missing or empty",
                }
            )
    return checks


def build_report(
    *, strict: bool = False, minimal: bool = False, strategy_c: bool = False
) -> dict[str, Any]:
    checks = collect_checks(minimal=minimal, strategy_c=strategy_c)
    required_ok = all(check["ok"] for check in checks if check["required"])
    optional_ok = all(check["ok"] for check in checks if not check["required"])
    ok = required_ok and (optional_ok if strict else True)
    mode = "strategy-c" if strategy_c else "minimal" if minimal else "strict" if strict else "default"
    return {
        "mode": mode,
        "ok": ok,
        "required_ok": required_ok,
        "optional_ok": optional_ok,
        "checks": checks,
    }


def render_human(report: dict[str, Any]) -> str:
    lines = [f"MPI translation toolkit doctor ({report['mode']})"]
    for check in report["checks"]:
        role = "required" if check["required"] else "optional"
        if check["ok"]:
            detail = check["version"] or check["path"]
            lines.append(f"[OK]      {check['name']:<10} ({role}) {detail}")
        elif check["path"] is None:
            lines.append(f"[MISSING] {check['name']:<10} ({role}) command: {check['command']}")
        else:
            lines.append(f"[ERROR]   {check['name']:<10} ({role}) {check['error']}")

    if report["ok"]:
        if report["optional_ok"]:
            lines.append("Result: ready")
        else:
            lines.append("Result: minimum requirements satisfied; optional tools are missing")
    else:
        lines.append("Result: not ready")
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only dependency checks for the MPI translation toolkit."
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--strict",
        action="store_true",
        help="treat missing optional tools as failures",
    )
    mode.add_argument(
        "--strategy-c",
        action="store_true",
        help="check the cross-platform tools and repository files required by strategy C",
    )
    mode.add_argument(
        "--minimal",
        action="store_true",
        help="check only required tools (python, git, sqlite3)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(
        strict=args.strict, minimal=args.minimal, strategy_c=args.strategy_c
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_human(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
