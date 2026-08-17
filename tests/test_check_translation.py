import importlib.util
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check-translation.py"


def load_script():
    spec = importlib.util.spec_from_file_location("check_translation", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = load_script()


class InputAndStructureTests(unittest.TestCase):
    def test_empty_translation_fails(self):
        checks = gate.run_checks([], [])
        statuses = {name: status for name, status, *_ in checks}

        self.assertEqual(statuses["non-empty inputs"], gate.FAIL)

    def test_blank_mask_shift_fails(self):
        result = gate.check_blank_alignment(
            ["甲", "", "乙", "丙"],
            ["A", "B", "", "C"],
        )

        self.assertEqual(result[0], gate.FAIL)
        self.assertEqual(result[2], [2, 3])

    def test_heading_signature_is_line_aligned(self):
        result = gate.check_headings(
            ["# 标题", "", "正文", "## 小节"],
            ["# Title", "", "## Section", "Body"],
        )

        self.assertEqual(result[0], gate.FAIL)

    def test_repeated_toc_and_body_title_must_use_same_translation(self):
        result = gate.check_repeated_title_consistency(
            ["- 一、出家的内涵", "", "## 一、出家的内涵"],
            ["- I. The Meaning of Going Forth", "", "## I. The Meaning of Monasticism"],
        )

        self.assertEqual(result[0], gate.FAIL)
        self.assertEqual([line for line, _title in result[2][0]], [1, 3])

    def test_repeated_title_ignores_djot_markers_and_numbering(self):
        result = gate.check_repeated_title_consistency(
            ["- 三、正确的发心", "", "#### 3．正确的发心"],
            ["- III. Right Aspiration", "", "#### 3. Right Aspiration"],
        )

        self.assertEqual(result[0], gate.PASS)

    def test_comment_markers_are_line_aligned(self):
        result = gate.check_comments(
            ["甲 {% keep %}", "", "乙"],
            ["A", "", "B {% keep %}"],
        )

        self.assertEqual(result[0], gate.FAIL)

    def test_malformed_comment_delimiters_fail_even_when_counts_match(self):
        result = gate.check_comments(
            ["甲 {% keep %}"],
            ["A %} keep {%"],
        )

        self.assertEqual(result[0], gate.FAIL)

    def test_source_emphasis_multiplicity_is_preserved(self):
        result = gate.check_emphasis(["*甲*与*乙*"], ["*one* and two"])

        self.assertEqual(result[0], gate.FAIL)

    def test_target_may_add_emphasis(self):
        result = gate.check_emphasis(["甲"], ["*one*"])

        self.assertEqual(result[0], gate.PASS)

    def test_cjk_in_plain_parentheses_fails(self):
        result = gate.check_cjk(["English prose (中文残留)"])

        self.assertEqual(result[0], gate.FAIL)

    def test_supplementary_cjk_ideograph_fails(self):
        result = gate.check_cjk(["English prose with 𠀀 left behind"])

        self.assertEqual(result[0], gate.FAIL)

    def test_cjk_in_link_destination_is_structural(self):
        result = gate.check_cjk(["See [source](#中文锚点)"])

        self.assertEqual(result[0], gate.PASS)

    def test_late_first_blocking_cycle_is_valid_even_after_clear_rounds(self):
        document = {
            "schema_version": 1,
            "stage": "semantic_review",
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "source_sha256": "1" * 64,
            "target_sha256": "2" * 64,
            "review_round": 3,
            "blocking_findings": 1,
            "blocking_finding_ids": ["finding-1"],
            "status": "blocking",
            "finding_ids": ["finding-1"],
            "findings_sha256": "3" * 64,
            "generated_at": "2026-08-13T00:00:00Z",
            "summary": "The first two rounds were clear; this is the first blocking cycle.",
        }

        certificate = gate.semantic_review_from_json(json.dumps(document))
        self.assertEqual(certificate.status, "blocking")

    def test_clear_status_is_rejected_when_blockers_remain(self):
        document = {
            "schema_version": 1,
            "stage": "semantic_review",
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "source_sha256": "1" * 64,
            "target_sha256": "2" * 64,
            "review_round": 3,
            "blocking_findings": 1,
            "blocking_finding_ids": ["finding-1"],
            "status": "clear",
            "finding_ids": ["finding-1"],
            "findings_sha256": "3" * 64,
            "generated_at": "2026-08-13T00:00:00Z",
            "summary": "Invalid clear certificate.",
        }

        with self.assertRaisesRegex(ValueError, "inconsistent"):
            gate.semantic_review_from_json(json.dumps(document))


class CliStrictModeTests(unittest.TestCase):
    def make_project(self, temp, with_optional_files=False, release_ready=True):
        source = temp / "source.dj"
        target = temp / "target.dj"
        source.write_text("空性\n", encoding="utf-8")
        target.write_text("emptiness\n", encoding="utf-8")
        if with_optional_files:
            (temp / "term-map.md").write_text(
                "空性|emptiness\n", encoding="utf-8"
            )
            (temp / "bilingual.dj").write_text(
                "空性\nemptiness\n\n", encoding="utf-8"
            )
            release = {
                "level": "public" if release_ready else "draft",
                "independent_review_required": release_ready,
                "named_approver_required": release_ready,
                "independent_review": {
                    "completed": release_ready,
                    "reviewer": "Reviewer" if release_ready else "",
                },
                "approval": {
                    "approved": release_ready,
                    "approver": "Approver" if release_ready else "",
                    "note": "Approved for release." if release_ready else "Draft only.",
                },
            }
            (temp / "translation-project.yaml").write_text(
                json.dumps({
                    "project_id": "test-project",
                    "title": "Test project",
                    "author": "Author",
                    "translator": "Translator",
                    "source_origin": "written_text",
                    "delivery_format": "publication_article",
                    "external_semantic_review": "allow",
                    "genre": "written_article",
                    "audience": "General readers",
                    "register": {"voice": "clear", "formality": "neutral"},
                    "cultural_bridge": {"policy": "none"},
                    "sanskrit": {
                        "diacritics": True,
                        "first_mention": "english_and_sanskrit",
                    },
                    "versions": {
                        "toolkit_commit": "test-commit",
                        "termbase": "test-termbase",
                    },
                    "release": release,
                }),
                encoding="utf-8",
            )
            (temp / "review-findings.jsonl").write_text(
                json.dumps({
                    "finding_id": "test-001",
                    "paragraph_id": "L1",
                    "severity": "minor",
                    "category": "fluency",
                    "message": "Reviewed.",
                    "suggestion": "No change required.",
                    "status": "resolved",
                    "reviewer": "Reviewer",
                }) + "\n",
                encoding="utf-8",
            )
            if release_ready:
                source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
                target_sha256 = hashlib.sha256(target.read_bytes()).hexdigest()
                project_sha256 = hashlib.sha256(
                    (temp / "translation-project.yaml").read_bytes()
                ).hexdigest()
                term_map_sha256 = hashlib.sha256(
                    (temp / "term-map.md").read_bytes()
                ).hexdigest()
                findings_path = temp / "review-findings.jsonl"
                findings_sha256 = hashlib.sha256(findings_path.read_bytes()).hexdigest()
                (temp / "source-analysis.json").write_text(
                    json.dumps({
                        "schema_version": 1,
                        "project": {
                            "project_id": "test-project",
                            "title": "Test project",
                            "source_origin": "written_text",
                            "delivery_format": "publication_article",
                            "external_semantic_review": "allow",
                        },
                        "provider": "internal",
                        "model": "test-internal-analysis",
                        "source_sha256": source_sha256,
                        "project_sha256": project_sha256,
                        "term_map_sha256": term_map_sha256,
                        "configuration": {
                            "base_url": "internal",
                            "reasoning_effort": "high",
                            "response_format": "json_schema",
                            "strict": True,
                            "serial": True,
                            "batch_size": 1,
                            "request_count": 1,
                            "timeout_seconds": 1,
                            "max_completion_tokens": 1,
                            "rate_limit_tier": "Tier1",
                            "rate_limit_concurrency": 1,
                            "rate_limit_rpm": 200,
                            "rate_limit_tpm": 2000000,
                        },
                        "generated_at": "2026-08-12T00:00:00Z",
                        "paragraphs": [{
                            "paragraph_id": "L1",
                            "predicates": [],
                            "relations": [],
                            "operators": [],
                            "references_and_ellipsis": [],
                            "competing_interpretations": [],
                            "must_preserve": ["保留空性的意义"],
                            "must_not_invent": ["不得擅增情态"],
                            "status": "clear",
                        }],
                    }) + "\n",
                    encoding="utf-8",
                )
                (temp / "semantic-review.json").write_text(
                    json.dumps({
                        "schema_version": 1,
                        "stage": "semantic_review",
                        "provider": "internal",
                        "model": "test-internal-reviewer",
                        "source_sha256": source_sha256,
                        "target_sha256": target_sha256,
                        "review_round": 2,
                        "blocking_findings": 0,
                        "blocking_finding_ids": [],
                        "status": "clear",
                        "finding_ids": ["test-001"],
                        "findings_sha256": findings_sha256,
                        "generated_at": "2026-08-12T00:00:00Z",
                        "summary": "Test-only internal semantic review certificate.",
                    }) + "\n",
                    encoding="utf-8",
                )
        return source, target

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, args)],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_non_strict_mode_reports_skips_but_succeeds(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            self.make_project(temp)
            result = self.run_cli(temp)

        self.assertEqual(result.returncode, 0)
        self.assertIn("[SKIP] terminology", result.stdout)
        self.assertIn("[SKIP] bilingual freshness", result.stdout)

    def test_strict_mode_rejects_any_skip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            self.make_project(temp)
            result = self.run_cli(temp, "--strict")

        self.assertEqual(result.returncode, 1)
        self.assertIn("STRICT FAILED", result.stdout)

    def test_strict_mode_passes_with_term_map_and_fresh_bilingual(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            self.make_project(temp, with_optional_files=True)
            result = self.run_cli(temp, "--strict")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ALL CHECKS PASSED", result.stdout)

    def test_strict_mode_rejects_draft_governance_even_when_mechanics_pass(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            self.make_project(temp, with_optional_files=True, release_ready=False)
            result = self.run_cli(temp, "--strict", "--json")

        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            payload["details"]["release governance"]["status"], gate.FAIL
        )
        self.assertIn("release.level public or sensitive", payload["details"]["release governance"]["detail"])

    def test_strict_public_release_requires_fresh_post_polish_semantic_review(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            self.make_project(temp, with_optional_files=True)
            certificate = temp / "semantic-review.json"
            document = json.loads(certificate.read_text(encoding="utf-8"))
            document["target_sha256"] = "0" * 64
            certificate.write_text(json.dumps(document), encoding="utf-8")

            stale = self.run_cli(temp, "--strict", "--json")
            certificate.unlink()
            missing = self.run_cli(temp, "--strict", "--json")

        stale_payload = json.loads(stale.stdout)
        missing_payload = json.loads(missing.stdout)
        self.assertEqual(stale.returncode, 1)
        self.assertEqual(
            stale_payload["details"]["semantic review freshness"]["status"],
            gate.FAIL,
        )
        self.assertIn(
            "target hash is stale",
            stale_payload["details"]["semantic review freshness"]["detail"],
        )
        self.assertEqual(missing.returncode, 1)
        self.assertEqual(
            missing_payload["details"]["semantic review freshness"]["status"],
            gate.SKIP,
        )

    def test_strict_public_release_requires_fresh_source_analysis(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            self.make_project(temp, with_optional_files=True)
            analysis = temp / "source-analysis.json"
            analysis_document = json.loads(analysis.read_text(encoding="utf-8"))
            analysis.unlink()
            missing = self.run_cli(temp, "--strict", "--json")
            analysis_document["source_sha256"] = "0" * 64
            analysis.write_text(
                json.dumps(analysis_document),
                encoding="utf-8",
            )
            stale = self.run_cli(temp, "--strict", "--json")

        missing_payload = json.loads(missing.stdout)
        stale_payload = json.loads(stale.stdout)
        self.assertEqual(missing.returncode, 1)
        self.assertEqual(
            missing_payload["details"]["external semantic review policy"]["status"],
            gate.SKIP,
        )
        self.assertEqual(stale.returncode, 1)
        self.assertIn(
            "source-analysis.json source hash is stale",
            stale_payload["details"]["external semantic review policy"]["detail"],
        )

    def test_source_analysis_binds_project_term_map_and_paragraph_coverage(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            self.make_project(temp, with_optional_files=True)
            path = temp / "source-analysis.json"
            baseline = json.loads(path.read_text(encoding="utf-8"))
            mutations = (
                ("project_sha256", "0" * 64, "project hash is stale"),
                ("term_map_sha256", "0" * 64, "term-map hash is stale"),
                (
                    "paragraphs",
                    [{**baseline["paragraphs"][0], "paragraph_id": "L2"}],
                    "paragraph coverage/order",
                ),
            )
            for field, value, expected in mutations:
                with self.subTest(field=field):
                    path.write_text(
                        json.dumps({**baseline, field: value}), encoding="utf-8"
                    )
                    result = self.run_cli(temp, "--strict", "--json")
                    payload = json.loads(result.stdout)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn(
                        expected,
                        payload["details"]["external semantic review policy"]["detail"],
                    )

    def test_explicit_missing_term_map_is_usage_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source, target = self.make_project(temp)
            result = self.run_cli(
                source, target, "--term-map", temp / "missing-terms.md"
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("explicit term map does not exist", result.stderr)

    def test_explicit_missing_bilingual_is_usage_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source, target = self.make_project(temp)
            result = self.run_cli(
                source, target, "--bilingual", temp / "missing-bilingual.dj"
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("explicit bilingual file does not exist", result.stderr)

    def test_json_distinguishes_skipped_checks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            self.make_project(temp)
            result = self.run_cli(temp, "--json")

        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            payload["skipped"],
            ["terminology", "bilingual freshness", "release governance"],
        )
        self.assertEqual(payload["mode"], "draft")
        self.assertEqual(payload["overall"], "WARN")
        self.assertTrue(payload["ok"])

    def test_json_output_file_is_atomic_and_cannot_alias_input(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source, _ = self.make_project(temp, with_optional_files=True)
            report = temp / "qa-report.json"
            report.write_text("old report\n", encoding="utf-8")

            written = self.run_cli(temp, "--strict", "--json", "--output", report)
            alias = self.run_cli(
                temp, "--strict", "--json", "--output", source
            )

            payload = json.loads(report.read_text(encoding="utf-8"))
            source_text = source.read_text(encoding="utf-8")

        self.assertEqual(written.returncode, 0, written.stderr)
        self.assertEqual(written.stdout, "")
        self.assertTrue(payload["ok"])
        self.assertEqual(alias.returncode, 2)
        self.assertEqual(source_text, "空性\n")


if __name__ == "__main__":
    unittest.main()
