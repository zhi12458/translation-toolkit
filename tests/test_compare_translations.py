from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "translate-files"
    / "出家与解脱-语义流程重译"
    / "compare-translations.py"
)
FOCUS = "仅仅为了得到谋生的食粮，就有多少生命在忍受痛苦，甚至丧生。"


def write_project(project: Path) -> dict[str, Path]:
    project.mkdir()
    paths = {
        "source": project / "source.dj",
        "baseline": project / "baseline-target.dj",
        "candidate": project / "target.dj",
        "term_map": project / "term-map.yaml",
        "metrics": project / "comparison-metrics.json",
        "report": project / "comparison-report.md",
    }
    paths["source"].write_text(
        "# 标题\n\n这是一个问题？\n"
        + FOCUS
        + "\n空性不是虚无。\n他说：“这不是虚无。”\n",
        encoding="utf-8",
    )
    paths["baseline"].write_text(
        "# Title\n\nThis is a question?\n"
        "How many lives had to suffer or perish merely so that food could be produced?\n"
        "Emptiness is not nothingness.\n"
        'He said, "It isn\'t nothingness." It isn\'t.\n',
        encoding="utf-8",
    )
    paths["candidate"].write_text(
        "# Title\n\nThis is a statement.\n"
        "How many lives suffer and even perish merely to obtain food for sustenance?\n"
        "Emptiness is not nihilism.\n"
        'He wrote, "It isn\'t nihilism." It isn\'t.\n',
        encoding="utf-8",
    )
    paths["term_map"].write_text(
        json.dumps(
            {
                "version": 1,
                "terms": [
                    {
                        "source": "空性",
                        "preferred": "emptiness",
                        "allowed": [],
                        "forbidden": [],
                        "status": "selected",
                    },
                    {
                        "source": "虚无",
                        "preferred": "nihilism",
                        "allowed": [],
                        "forbidden": ["nothingness"],
                        "status": "selected",
                    },
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return paths


def run_comparison(paths: dict[str, Path], *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source",
            str(paths["source"]),
            "--baseline",
            str(paths["baseline"]),
            "--candidate",
            str(paths["candidate"]),
            "--term-map",
            str(paths["term_map"]),
            "--metrics",
            str(paths["metrics"]),
            "--report",
            str(paths["report"]),
            *extra,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_deterministic_comparison_metrics_and_report(tmp_path: Path) -> None:
    paths = write_project(tmp_path / "article")
    # A canary analysis artifact must neither be read nor copied to output.
    canary = "BLIND_ANALYSIS_CANARY_9e08ad"
    (paths["source"].parent / "source-analysis.json").write_bytes(
        b"\xff" + canary.encode("ascii")
    )

    first = run_comparison(paths)
    assert first.returncode == 0, first.stderr
    first_metrics = paths["metrics"].read_bytes()
    first_report = paths["report"].read_bytes()

    second = run_comparison(paths)
    assert second.returncode == 0, second.stderr
    assert paths["metrics"].read_bytes() == first_metrics
    assert paths["report"].read_bytes() == first_report
    assert canary.encode("ascii") not in first_metrics
    assert canary.encode("ascii") not in first_report

    metrics = json.loads(first_metrics)
    assert metrics["subjective_quality_verdict"] is None
    assert metrics["report_scope"] == "deterministic_mechanical_comparison_only"
    assert metrics["declared_inputs_read"] == [
        "source.dj",
        "baseline-target.dj",
        "target.dj",
        "term-map.yaml",
    ]
    assert metrics["inputs"]["source"]["sha256"] == hashlib.sha256(
        paths["source"].read_bytes()
    ).hexdigest()

    assert metrics["alignment"]["baseline"]["fully_aligned"] is True
    assert metrics["alignment"]["candidate"]["fully_aligned"] is True
    assert metrics["statistics"]["source"]["cjk_character_count"] > 0
    assert metrics["statistics"]["candidate"]["english_word_count"] > 0

    baseline_contractions = metrics["non_quotation_contractions"]["baseline"]
    candidate_contractions = metrics["non_quotation_contractions"]["candidate"]
    assert baseline_contractions["count"] == 1
    assert candidate_contractions["count"] == 1
    assert baseline_contractions["occurrences"][0] == {
        "form": "isn't",
        "line_number": 6,
        "normalized": "isn't",
    }

    baseline_questions = metrics["source_question_mark_retention"]["baseline"]
    candidate_questions = metrics["source_question_mark_retention"]["candidate"]
    assert baseline_questions["line_retention_rate"] == 1.0
    assert candidate_questions["line_retention_rate"] == 0.0
    assert candidate_questions["missing_question_line_numbers"] == [3]

    baseline_terms = metrics["terminology"]["baseline"]
    candidate_terms = metrics["terminology"]["candidate"]
    assert baseline_terms["status"] == "FAIL"
    assert baseline_terms["presence_gate_status"] == "FAIL"
    assert baseline_terms["source_occurrences"] == 3
    assert baseline_terms["matched_occurrences"] == 1
    assert baseline_terms["forbidden_hit_count"] == 2
    assert candidate_terms["status"] == "PASS"
    assert candidate_terms["presence_gate_status"] == "PASS"
    assert candidate_terms["matched_occurrences"] == 3
    assert candidate_terms["coverage_rate"] == 1.0

    slot = metrics["l57_comparison_slot"]
    assert slot["found"] is True
    assert slot["line_number"] == 4
    assert "food could be produced" in slot["baseline_target_line"]
    assert "obtain food for sustenance" in slot["candidate_target_line"]

    report = first_report.decode("utf-8")
    assert "不判断任何一版译文更好" in report
    assert "L57" in report


def test_misalignment_is_reported_and_dependent_metrics_are_skipped(
    tmp_path: Path,
) -> None:
    paths = write_project(tmp_path / "article")
    paths["candidate"].write_text("# Title\nThis is shifted.\n", encoding="utf-8")

    completed = run_comparison(paths)
    assert completed.returncode == 0, completed.stderr
    metrics = json.loads(paths["metrics"].read_text(encoding="utf-8"))
    assert metrics["alignment"]["candidate"]["fully_aligned"] is False
    assert metrics["source_question_mark_retention"]["candidate"]["available"] is False
    assert metrics["terminology"]["candidate"]["status"] == "SKIP"
    assert metrics["terminology"]["candidate"]["presence_gate_status"] == "SKIP"
    assert metrics["terminology"]["candidate"]["available"] is False
    assert metrics["l57_comparison_slot"]["candidate_target_line"] is None


def test_missing_candidate_leaves_outputs_absent(tmp_path: Path) -> None:
    paths = write_project(tmp_path / "article")
    paths["candidate"].unlink()

    completed = run_comparison(paths)
    assert completed.returncode == 1
    assert "candidate target is not a regular file" in completed.stderr
    assert not paths["metrics"].exists()
    assert not paths["report"].exists()


def test_output_cannot_overwrite_an_input(tmp_path: Path) -> None:
    paths = write_project(tmp_path / "article")
    original_source = paths["source"].read_bytes()
    paths["metrics"] = paths["source"]

    completed = run_comparison(paths)
    assert completed.returncode == 1
    assert "must not overwrite an input" in completed.stderr
    assert paths["source"].read_bytes() == original_source
    assert not paths["report"].exists()


def test_invalid_term_map_leaves_outputs_absent(tmp_path: Path) -> None:
    paths = write_project(tmp_path / "article")
    paths["term_map"].write_text("not-json\n", encoding="utf-8")

    completed = run_comparison(paths)
    assert completed.returncode == 1
    assert "JSON-compatible YAML" in completed.stderr
    assert not paths["metrics"].exists()
    assert not paths["report"].exists()


def test_one_shared_rendering_cannot_cover_two_source_terms(tmp_path: Path) -> None:
    paths = write_project(tmp_path / "article")
    paths["source"].write_text("贪著和执著。\n", encoding="utf-8")
    paths["baseline"].write_text("Attachment.\n", encoding="utf-8")
    paths["candidate"].write_text("Attachment.\n", encoding="utf-8")
    paths["term_map"].write_text(
        json.dumps(
            {
                "version": 1,
                "terms": [
                    {
                        "source": "贪著",
                        "preferred": "attachment",
                        "allowed": [],
                        "forbidden": [],
                        "status": "selected",
                    },
                    {
                        "source": "执著",
                        "preferred": "attachment",
                        "allowed": [],
                        "forbidden": [],
                        "status": "selected",
                    },
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    completed = run_comparison(paths)
    assert completed.returncode == 0, completed.stderr
    metrics = json.loads(paths["metrics"].read_text(encoding="utf-8"))
    for version in ("baseline", "candidate"):
        terms = metrics["terminology"][version]
        assert terms["source_occurrences"] == 2
        assert terms["matched_occurrences"] == 1
        assert terms["coverage_rate"] == 0.5
        assert terms["presence_gate_status"] == "PASS"
        assert terms["status"] == "WARN"
