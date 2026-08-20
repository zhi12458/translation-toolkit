import importlib.util
import json
import copy
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECK_SCRIPT = ROOT / "scripts" / "check-translation.py"
GEN_SCRIPT = ROOT / "scripts" / "gen-bilingual.py"
EXAMPLE = ROOT / "examples" / "minimal-article"


def load_gate():
    spec = importlib.util.spec_from_file_location("check_translation_interfaces", CHECK_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = load_gate()


class ProjectInterfaceTests(unittest.TestCase):
    def test_json_schemas_are_valid_json_documents(self):
        for path in sorted((ROOT / "schemas").glob("*.schema.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                document["$schema"],
                "https://json-schema.org/draft/2020-12/schema",
                path,
            )

    def test_example_review_findings_are_one_object_per_line(self):
        lines = (EXAMPLE / "review-findings.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        self.assertTrue(lines)
        required = {
            "finding_id", "paragraph_id", "severity", "category", "message",
            "suggestion", "status", "reviewer",
        }
        for line in lines:
            self.assertTrue(required <= json.loads(line).keys())

    def test_machine_term_map_enforces_forbidden_and_unresolved_states(self):
        selected = gate.term_policy_from_yaml_json(json.dumps({
            "version": 1,
            "terms": [{
                "source": "空性",
                "sense": "doctrinal emptiness",
                "preferred": "emptiness",
                "allowed": ["emptiness"],
                "forbidden": ["nothingness"],
                "sources": ["DoT定稿"],
                "rationale": "Selected for this sense.",
                "status": "selected",
            }],
        }))
        unresolved = gate.term_policy_from_yaml_json(json.dumps({
            "version": 1,
            "terms": [{
                "source": "空性",
                "sense": "requires context",
                "preferred": "emptiness",
                "allowed": [],
                "forbidden": [],
                "sources": ["DoT定稿"],
                "rationale": "Awaiting reviewer decision.",
                "status": "needs_human",
            }],
        }))

        self.assertEqual(
            gate.check_terminology(["空性"], ["nothingness"], selected)[0],
            gate.FAIL,
        )
        self.assertEqual(
            gate.check_terminology(["空性"], ["emptiness"], unresolved)[0],
            gate.SKIP,
        )

    def test_term_map_rejects_unknown_fields_and_duplicate_project_senses(self):
        entry = {
            "source": "空性",
            "sense": "doctrinal emptiness",
            "preferred": "emptiness",
            "allowed": [],
            "forbidden": [],
            "sources": ["DoT定稿"],
            "rationale": "Frozen for this project.",
            "status": "selected",
        }
        unknown = {"version": 1, "terms": [{**entry, "unexpected": True}]}
        duplicate = {"version": 1, "terms": [entry, {**entry, "sense": "other"}]}

        for document in (unknown, duplicate):
            with self.subTest(document=document):
                with self.assertRaises(ValueError):
                    gate.term_policy_from_yaml_json(json.dumps(document))

    def test_term_renderings_use_boundaries_and_do_not_double_count(self):
        policy = gate.TermPolicy(
            allowed={"止": ["calm", "calm abiding"]},
            forbidden={"止": ["void"]},
            needs_human=(),
        )

        boundary = gate.check_terminology(["止"], ["avoid calmness"], policy)
        overlap = gate.check_terminology(["止止"], ["calm abiding"], policy)

        self.assertEqual(boundary[0], gate.FAIL)
        self.assertEqual(overlap[0], gate.WARN)

    def test_strict_terminology_requires_at_least_99_percent_coverage(self):
        policy = gate.TermPolicy(
            allowed={"空性": ["emptiness"]},
            forbidden={"空性": []},
            needs_human=(),
        )

        result = gate.check_terminology(
            ["空性"] * 100,
            ["emptiness"] * 98 + ["omitted"] * 2,
            policy,
            strict=True,
        )

        self.assertEqual(result[0], gate.FAIL)

    def test_irrelevant_term_map_is_not_treated_as_coverage(self):
        result = gate.check_terminology(["正文"], ["Body"], {"空性": ["emptiness"]})

        self.assertEqual(result[0], gate.SKIP)
        self.assertIn("no terms present", result[1])

    def test_public_release_requires_independent_review_and_named_approval(self):
        incomplete = gate.ProjectPolicy(
            author="Author",
            translator="Translator",
            genre="scripture",
            level="public",
            independent_review_required=False,
            review_completed=False,
            reviewer="",
            named_approver_required=False,
            approved=False,
            approver="",
            approval_note="",
        )
        ready = gate.ProjectPolicy(
            author="Author",
            translator="Translator",
            genre="scripture",
            level="public",
            independent_review_required=True,
            review_completed=True,
            reviewer="Independent reviewer",
            named_approver_required=True,
            approved=True,
            approver="Human approver",
            approval_note="Approved after review.",
        )
        open_major = [{
            "finding_id": "f-1",
            "severity": "major",
            "status": "open",
        }]

        self.assertEqual(
            gate.check_release_governance(incomplete, None)[0], gate.FAIL
        )
        self.assertEqual(
            gate.check_release_governance(ready, open_major)[0], gate.FAIL
        )
        self.assertEqual(gate.check_release_governance(ready, [])[0], gate.PASS)
        self.assertEqual(
            gate.check_release_governance(ready, [], strict=True)[0], gate.PASS
        )
        self.assertEqual(
            gate.check_release_governance(incomplete, [], strict=True)[0], gate.FAIL
        )

    def test_project_parser_rejects_schema_level_invalid_values(self):
        base = json.loads(
            (EXAMPLE / "translation-project.yaml").read_text(encoding="utf-8")
        )
        invalid_documents = []
        for path, value in (
            (("project_id",), ""),
            (("genre",), "invalid"),
            (("source_origin",), "podcast-ish"),
            (("delivery_format",), "website-ish"),
            (("external_semantic_review",), "sometimes"),
            (("versions", "toolkit_commit"), "x"),
            (("register", "formality"), "casual-ish"),
        ):
            document = copy.deepcopy(base)
            cursor = document
            for key in path[:-1]:
                cursor = cursor[key]
            cursor[path[-1]] = value
            invalid_documents.append(document)
        with_extra = copy.deepcopy(base)
        with_extra["unexpected"] = True
        invalid_documents.append(with_extra)

        for document in invalid_documents:
            with self.subTest(document=document):
                with self.assertRaises(ValueError):
                    gate.project_policy_from_yaml_json(json.dumps(document))

    def test_project_parser_defaults_new_metadata_for_legacy_drafts(self):
        document = json.loads(
            (EXAMPLE / "translation-project.yaml").read_text(encoding="utf-8")
        )
        for field in (
            "source_origin", "delivery_format", "external_semantic_review"
        ):
            document.pop(field)

        policy = gate.project_policy_from_yaml_json(json.dumps(document))

        self.assertEqual(policy.source_origin, "unknown")
        self.assertEqual(policy.delivery_format, "other")
        self.assertEqual(policy.external_semantic_review, "allow")
        self.assertFalse(policy.source_origin_declared)
        self.assertFalse(policy.delivery_format_declared)
        policy = gate.ProjectPolicy(
            **{
                **policy.__dict__,
                "level": "public",
            }
        )
        self.assertEqual(
            gate.check_release_governance(policy, [], strict=True)[0], gate.FAIL
        )

    def test_publication_delivery_rejects_conversational_register(self):
        document = json.loads(
            (EXAMPLE / "translation-project.yaml").read_text(encoding="utf-8")
        )
        document["source_origin"] = "oral_talk"
        document["delivery_format"] = "publication_book"
        document["register"]["formality"] = "conversational"

        with self.assertRaisesRegex(ValueError, "conversational"):
            gate.project_policy_from_yaml_json(json.dumps(document))

    def test_review_findings_parser_rejects_invalid_or_empty_schema_fields(self):
        valid = {
            "finding_id": "f-1",
            "paragraph_id": "L1",
            "severity": "minor",
            "category": "fluency",
            "message": "Review message.",
            "suggestion": "Suggested edit.",
            "status": "open",
            "reviewer": "Reviewer",
        }
        invalid_records = [
            {**valid, "finding_id": ""},
            {**valid, "category": "doctrine-ish"},
            {**valid, "suggestion": 123},
            {**valid, "unexpected": True},
        ]

        for record in invalid_records:
            with self.subTest(record=record):
                with self.assertRaises(ValueError):
                    gate.review_findings_from_jsonl(json.dumps(record))

    def test_review_findings_parser_accepts_valid_provenance_and_rejects_bad_hashes(self):
        valid = {
            "finding_id": "f-1",
            "paragraph_id": "L1",
            "severity": "major",
            "category": "meaning",
            "message": "The predicate changed.",
            "suggestion": "Preserve the source predicate.",
            "status": "open",
            "reviewer": "Reviewer",
            "stage": "semantic_review",
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "source_sha256": "a" * 64,
            "target_sha256": "b" * 64,
        }

        parsed = gate.review_findings_from_jsonl(json.dumps(valid))

        self.assertEqual(parsed[0]["stage"], "semantic_review")
        with self.assertRaisesRegex(ValueError, "target_sha256"):
            gate.review_findings_from_jsonl(
                json.dumps({**valid, "target_sha256": "not-a-digest"})
            )

    def test_sensitive_and_deny_projects_reject_external_semantic_artifacts(self):
        project = gate.ProjectPolicy(
            author="Author",
            translator="Translator",
            genre="other",
            level="sensitive",
            independent_review_required=True,
            review_completed=True,
            reviewer="Reviewer",
            named_approver_required=True,
            approved=True,
            approver="Approver",
            approval_note="Approved.",
            external_semantic_review="allow",
        )
        external_certificate = gate.SemanticReviewCertificate(
            provider="deepseek",
            model="deepseek-v4-pro",
            source_sha256="a" * 64,
            target_sha256="b" * 64,
            review_round=2,
            blocking_findings=0,
            blocking_finding_ids=(),
            status="clear",
            finding_ids=(),
            findings_sha256="c" * 64,
            paragraph_audits=({
                "paragraph_id": "L1",
                "temporal_relations": "not_present",
                "conditions": "not_present",
                "negation": "not_present",
                "degree": "not_present",
                "elliptical_subject": "not_present",
                "semantic_roles": "preserved",
                "actor_or_state_holder": "无相关省略主语。",
                "cause_or_instrument": "无相关原因或工具。",
                "finding_ids": [],
            },),
            generated_at="2026-08-12T00:00:00Z",
            summary="Review complete.",
        )
        internal_certificate = gate.SemanticReviewCertificate(
            **{
                **external_certificate.__dict__,
                "provider": "internal",
                "model": "independent-internal-role",
            }
        )

        self.assertEqual(
            gate.check_external_semantic_policy(
                project, certificate=external_certificate
            )[0],
            gate.FAIL,
        )
        self.assertEqual(
            gate.check_external_semantic_policy(
                project, certificate=internal_certificate
            )[0],
            gate.PASS,
        )
        self.assertEqual(
            gate.check_external_semantic_policy(
                project,
                certificate=internal_certificate,
                review_findings=[{"provider": "deepseek"}],
            )[0],
            gate.FAIL,
        )

    def test_semantic_certificate_binds_exact_blocking_finding_ids(self):
        document = json.loads(
            (EXAMPLE / "semantic-review.json").read_text(encoding="utf-8")
        )
        parsed = gate.semantic_review_from_json(json.dumps(document))
        self.assertEqual(parsed.blocking_finding_ids, ())

        invalid = copy.deepcopy(document)
        invalid["blocking_findings"] = 1
        with self.assertRaisesRegex(ValueError, "length must equal"):
            gate.semantic_review_from_json(json.dumps(invalid))

        certificate = gate.SemanticReviewCertificate(
            provider="internal",
            model="independent-internal-role",
            source_sha256="a" * 64,
            target_sha256="b" * 64,
            review_round=1,
            blocking_findings=1,
            blocking_finding_ids=("certified-major",),
            status="blocking",
            finding_ids=(),
            findings_sha256="c" * 64,
            paragraph_audits=({
                "paragraph_id": "L1",
                "temporal_relations": "not_present",
                "conditions": "not_present",
                "negation": "not_present",
                "degree": "not_present",
                "elliptical_subject": "not_present",
                "semantic_roles": "preserved",
                "actor_or_state_holder": "无相关省略主语。",
                "cause_or_instrument": "无相关原因或工具。",
                "finding_ids": [],
            },),
            generated_at="2026-08-12T00:00:00Z",
            summary="One blocker remains.",
        )
        different_history = [{
            "finding_id": "different-major",
            "severity": "major",
            "status": "open",
        }]
        result = gate.check_semantic_review(
            None,
            certificate,
            source_sha256="a" * 64,
            target_sha256="b" * 64,
            findings_sha256="c" * 64,
            findings=different_history,
        )
        self.assertEqual(result[0], gate.FAIL)
        self.assertIn("blocking_finding_ids", result[1])

    def test_public_example_passes_atomic_generation_and_strict_gate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "minimal-article"
            project.mkdir()
            for name in (
                "source.dj",
                "target.dj",
                "term-map.yaml",
                "translation-project.yaml",
                "source-analysis.json",
                "review-findings.jsonl",
                "semantic-review.json",
            ):
                shutil.copy2(EXAMPLE / name, project / name)

            generated = subprocess.run(
                [
                    sys.executable,
                    str(GEN_SCRIPT),
                    str(project / "source.dj"),
                    str(project / "target.dj"),
                    "--output",
                    str(project / "bilingual.dj"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            checked = subprocess.run(
                [sys.executable, str(CHECK_SCRIPT), str(project), "--strict", "--json"],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(generated.returncode, 0, generated.stderr)
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        report = json.loads(checked.stdout)
        qa_schema = json.loads(
            (ROOT / "schemas" / "qa-report.schema.json").read_text(encoding="utf-8")
        )
        self.assertTrue(set(qa_schema["required"]) <= report.keys())
        self.assertEqual(report["mode"], "strict")
        self.assertEqual(report["overall"], "PASS")
        self.assertEqual(report["skipped"], [])
        self.assertTrue(report["ok"])


if __name__ == "__main__":
    unittest.main()
