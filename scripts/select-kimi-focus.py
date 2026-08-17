#!/usr/bin/env python3
"""Select source-only semantic-risk paragraphs for focused Kimi analysis.

This routing step reads the canonical full ``source-analysis.json`` and the
same three Chinese-side inputs used by the blind analyzer.  It never reads an
English target or review output.  Kimi itself receives only paragraph IDs as
control data and still opens only source.dj, translation-project.yaml, and
term-map.yaml.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ANALYSIS_NAME = "source-analysis.json"


class SelectionError(Exception):
    """Safe selection failure that does not echo manuscript text."""


def _load_validator():
    path = ROOT / "scripts" / "kimi-source-analysis.py"
    spec = importlib.util.spec_from_file_location("mpi_kimi_focus_validator", path)
    if spec is None or spec.loader is None:
        raise SelectionError("source-analysis validator is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _read_json_snapshot(path: Path, label: str) -> tuple[dict, str]:
    try:
        raw = path.read_bytes()
        document = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SelectionError(f"{label} is missing or invalid") from exc
    if not isinstance(document, dict):
        raise SelectionError(f"{label} must contain an object")
    return document, hashlib.sha256(raw).hexdigest()


def load_validated_analysis(project_directory: Path, analysis_path: Path):
    validator = _load_validator()
    inputs = validator.load_project(project_directory)
    schema = validator.load_analysis_schema()
    document, artifact_sha256 = _read_json_snapshot(
        analysis_path, "canonical source analysis"
    )
    try:
        validator._validate_instance(document, schema)
        for field in ("source_sha256", "project_sha256", "term_map_sha256"):
            if document[field] != getattr(inputs, field):
                raise SelectionError("canonical source analysis is stale")
        validated = validator.validate_batch_content(
            json.dumps({"paragraphs": document["paragraphs"]}, ensure_ascii=False),
            inputs.paragraphs,
            schema,
            inputs.source,
        )
    except SelectionError:
        raise
    except Exception as exc:
        raise SelectionError("canonical source analysis failed local validation") from exc
    return inputs, document, validated, artifact_sha256


def risk_reasons(paragraph: dict) -> list[str]:
    """Return evidence-based escalation reasons, without guessing from prose."""
    reasons: list[str] = []
    if paragraph["status"] == "needs_human":
        reasons.append("needs_human")
    if paragraph["competing_interpretations"]:
        reasons.append("competing_interpretations")
    if any(
        participant["evidence_status"] == "ambiguous"
        for predicate in paragraph["predicates"]
        for participant in predicate["participants"]
    ):
        reasons.append("ambiguous_semantic_role")
    if any(
        relation["evidence_status"] == "ambiguous"
        for relation in paragraph["relations"]
    ):
        reasons.append("ambiguous_relation")
    if any(
        operator["evidence_status"] == "ambiguous"
        for operator in paragraph["operators"]
    ):
        reasons.append("ambiguous_scope")
    if any(
        reference["evidence_status"] == "ambiguous"
        for reference in paragraph["references_and_ellipsis"]
    ):
        reasons.append("ambiguous_reference_or_ellipsis")
    return reasons


def build_selection(
    inputs, document: dict, paragraphs: list[dict], artifact_sha256: str,
    manual_ids: list[str],
) -> dict:
    if len(manual_ids) != len(set(manual_ids)):
        raise SelectionError("manual paragraph IDs must be unique")
    available = {paragraph.paragraph_id for paragraph in inputs.paragraphs}
    if set(manual_ids) - available:
        raise SelectionError("manual paragraph ID is not a nonempty source line")
    manual = set(manual_ids)
    selected = []
    for paragraph in paragraphs:
        reasons = risk_reasons(paragraph)
        if paragraph["paragraph_id"] in manual:
            reasons.append("manual_escalation")
        if reasons:
            selected.append(
                {"paragraph_id": paragraph["paragraph_id"], "reasons": reasons}
            )
    return {
        "schema_version": 1,
        "project_id": document["project"]["project_id"],
        "source_sha256": inputs.source_sha256,
        "source_analysis_sha256": artifact_sha256,
        "selection_policy": "ambiguity_or_manual_escalation",
        "total_source_paragraphs": len(inputs.paragraphs),
        "selected_count": len(selected),
        "selected": selected,
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Select ambiguous or manually escalated source paragraphs for focused "
            "Kimi K3 analysis."
        )
    )
    parser.add_argument("project_directory", type=Path)
    parser.add_argument(
        "--analysis",
        type=Path,
        help="canonical full analysis (default: PROJECT/source-analysis.json)",
    )
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        help="manually escalate an additional nonempty source line ID (repeatable)",
    )
    parser.add_argument(
        "--format",
        choices=("json", "args", "ids"),
        default="json",
        help="output JSON evidence, repeatable Kimi CLI arguments, or IDs only",
    )
    args = parser.parse_args(argv)
    if any(re.fullmatch(r"L[1-9][0-9]*", value) is None for value in args.include):
        parser.error("--include must use a source line ID such as L57")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    project = args.project_directory.expanduser().resolve()
    analysis_path = (
        args.analysis.expanduser().resolve()
        if args.analysis
        else project / DEFAULT_ANALYSIS_NAME
    )
    try:
        inputs, document, paragraphs, artifact_sha256 = load_validated_analysis(
            project, analysis_path
        )
        selection = build_selection(
            inputs, document, paragraphs, artifact_sha256, args.include
        )
    except SelectionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    ids = [entry["paragraph_id"] for entry in selection["selected"]]
    if args.format == "args":
        print(" ".join(f"--paragraph-id {paragraph_id}" for paragraph_id in ids))
    elif args.format == "ids":
        print("\n".join(ids))
    else:
        print(json.dumps(selection, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
