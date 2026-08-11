import importlib.util
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
