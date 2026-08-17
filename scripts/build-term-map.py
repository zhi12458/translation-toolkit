#!/usr/bin/env python3
"""Search the MPI term database and atomically build a project term-map.yaml."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from _toolkit_io import ToolkitError, atomic_write_text, resolve_input, resolve_output, sha256_file


REPOSITORY = Path(__file__).resolve().parents[1]
SEARCH_SCRIPT = REPOSITORY / "terms-database" / "search.py"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("candidates")
    parser.add_argument("--output", required=True)
    parser.add_argument("--receipts", required=True)
    parser.add_argument("--limit", type=int, default=20)
    return parser.parse_args(argv)


def load_candidates(path: Path) -> list[dict[str, str]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ToolkitError("term candidates must be valid UTF-8 JSON") from exc
    values = document.get("terms") if isinstance(document, dict) else document
    if not isinstance(values, list):
        raise ToolkitError("term candidates must contain a terms array")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(values):
        if isinstance(item, str):
            source, sense = item.strip(), ""
        elif isinstance(item, dict):
            source = str(item.get("source", "")).strip()
            sense = str(item.get("sense", "")).strip()
        else:
            raise ToolkitError(f"term candidates item {index} is invalid")
        if not source:
            raise ToolkitError(f"term candidates item {index} has no source term")
        if source not in seen:
            seen.add(source)
            result.append({"source": source, "sense": sense})
    return result


def search_term(term: str, limit: int) -> tuple[list[dict], dict]:
    command = [sys.executable, str(SEARCH_SCRIPT), term, str(limit), "--json"]
    started = datetime.now(timezone.utc)
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    finished = datetime.now(timezone.utc)
    if completed.returncode != 0:
        raise ToolkitError(f"MPI term search failed for candidate {term!r}")
    try:
        results = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ToolkitError("MPI term search returned invalid JSON") from exc
    if not isinstance(results, list):
        raise ToolkitError("MPI term search returned an invalid result list")
    receipt = {
        "source": term,
        "search_script": str(SEARCH_SCRIPT.resolve()),
        "search_script_sha256": sha256_file(SEARCH_SCRIPT),
        "started_at": started.isoformat().replace("+00:00", "Z"),
        "finished_at": finished.isoformat().replace("+00:00", "Z"),
        "exit_code": completed.returncode,
        "result_count": len(results),
        "stdout_sha256": hashlib.sha256(completed.stdout.encode("utf-8")).hexdigest(),
    }
    return results, receipt


def build_entry(candidate: dict[str, str], results: list[dict]) -> dict:
    source = candidate["source"]
    exact = [row for row in results if str(row.get("zh", "")).strip() == source]
    if not exact:
        return {
            "source": source,
            "sense": candidate["sense"] or "待人工确认",
            "preferred": "__UNRESOLVED__",
            "allowed": [],
            "forbidden": [],
            "sources": ["MPI术语库：无精确匹配"],
            "rationale": "MPI术语库没有精确匹配；翻译前必须人工确认。",
            "status": "needs_human",
            "reviewer": "translation-toolkit/build-term-map.py",
        }
    preferred = str(exact[0].get("en", "")).strip()
    if not preferred:
        raise ToolkitError(f"MPI term search returned an empty English term for {source!r}")
    allowed: list[str] = []
    for row in exact[1:]:
        value = str(row.get("en", "")).strip()
        if value and value.casefold() != preferred.casefold() and value not in allowed:
            allowed.append(value)
    sources = []
    for row in exact:
        label = str(row.get("source", "")).strip()
        if label and label not in sources:
            sources.append(label)
    return {
        "source": source,
        "sense": candidate["sense"] or source,
        "preferred": preferred,
        "allowed": allowed,
        "forbidden": [],
        "sources": sources or ["MPI术语库"],
        "rationale": "由锁定版 MPI术语库按权威顺序选择；译者仍须结合上下文核实词义。",
        "status": "selected",
        "reviewer": "translation-toolkit/build-term-map.py",
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.limit <= 0:
        print("error: --limit must be greater than zero", file=sys.stderr)
        return 1
    try:
        source_path = resolve_input(args.source, "source.dj")
        candidates_path = resolve_input(args.candidates, "term candidates")
        output = resolve_output(args.output, [source_path, candidates_path])
        receipts = resolve_output(args.receipts, [source_path, candidates_path, output])
        source_text = source_path.read_text(encoding="utf-8")
        candidates = load_candidates(candidates_path)
        entries: list[dict] = []
        receipt_rows: list[dict] = []
        for candidate in candidates:
            if candidate["source"] not in source_text:
                raise ToolkitError(f"term candidate is absent from source.dj: {candidate['source']!r}")
            results, receipt = search_term(candidate["source"], args.limit)
            entries.append(build_entry(candidate, results))
            receipt_rows.append(receipt)
        atomic_write_text(output, json.dumps({"version": 1, "terms": entries}, ensure_ascii=False, indent=2) + "\n")
        atomic_write_text(receipts, "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in receipt_rows))
    except (ToolkitError, UnicodeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    unresolved = sum(entry["status"] == "needs_human" for entry in entries)
    print(f"{output}\tterms={len(entries)}\tunresolved={unresolved}\tsha256={sha256_file(output)}")
    return 2 if unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main())
