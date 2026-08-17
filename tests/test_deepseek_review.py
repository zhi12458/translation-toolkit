import hashlib
import importlib.util
import json
import subprocess
import sys
import urllib.error
from pathlib import Path
from unittest import mock

import pytest


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "deepseek-review.py"
SPEC = importlib.util.spec_from_file_location("mpi_deepseek_review", MODULE_PATH)
deepseek = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = deepseek
SPEC.loader.exec_module(deepseek)


def make_project(tmp_path):
    project = tmp_path / "article"
    project.mkdir()
    (project / "source.dj").write_text(
        "# 人工智能时代\n\n空性不是虚无。\n", encoding="utf-8"
    )
    (project / "target.dj").write_text(
        "# The Age of Artificial Intelligence\n\nEmptiness is not nothingness.\n",
        encoding="utf-8",
    )
    (project / "term-map.yaml").write_text(
        json.dumps(
            {
                "version": 1,
                "terms": [
                    {
                        "source": "空性",
                        "sense": "缘起性空",
                        "preferred": "emptiness",
                        "allowed": ["emptiness"],
                        "forbidden": [],
                        "sources": ["DoT定稿"],
                        "rationale": "采用项目术语库定稿。",
                        "status": "selected",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (project / "translation-project.yaml").write_text(
        json.dumps(
            {
                "project_id": "ai-age",
                "title": "人工智能时代",
                "author": "MPI",
                "translator": "Test Translator",
                "genre": "written_article",
                "source_origin": "written_text",
                "delivery_format": "publication_article",
                "external_semantic_review": "allow",
                "audience": "general readers",
                "register": {"voice": "gentle", "formality": "neutral"},
                "cultural_bridge": {"policy": "none"},
                "scriptures": [],
                "sanskrit": {
                    "diacritics": True,
                    "first_mention": "english_and_sanskrit",
                },
                "versions": {
                    "toolkit_commit": "1234567",
                    "termbase": "test-fixture",
                },
                "release": {
                    "level": "draft",
                    "independent_review_required": True,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return project


def valid_review_content(inputs, *, severity="major", finding_id=None):
    finding_id = finding_id or f"deepseek-{inputs.target_sha256[:12]}-L3-1"
    return json.dumps(
        {
            "findings": [
                {
                    "finding_id": finding_id,
                    "paragraph_id": "L3",
                    "severity": severity,
                    "category": "meaning",
                    "message": "译文把原文的动作类型改变了。",
                    "suggestion": "须保留原文的取得含义，不得增补生产这一动作。",
                    "status": "open",
                    "reviewer": "DeepSeek V4 Pro",
                }
            ],
            "summary": "准确性复核完成，发现一项需要修正的问题。",
        },
        ensure_ascii=False,
    )


_DEFAULT_CONTENT = object()


def api_envelope(inputs, content=_DEFAULT_CONTENT, *, finish_reason="stop"):
    if content is _DEFAULT_CONTENT:
        content = valid_review_content(inputs)
    return json.dumps(
        {"choices": [{"finish_reason": finish_reason, "message": {"content": content}}]}
    ).encode("utf-8")


class FakeHTTPResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self, size=-1):
        if size is None or size < 0:
            return self.body
        return self.body[:size]


@pytest.mark.parametrize("filename", ["translation-project.yaml", "term-map.yaml"])
def test_review_inputs_reject_unknown_fields_before_prompt_build(tmp_path, filename):
    project = make_project(tmp_path)
    path = project / filename
    document = json.loads(path.read_text(encoding="utf-8"))
    document["source_analysis"] = "SMUGGLED-K3-CONCLUSION"
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(deepseek.ReviewError, match="unknown fields"):
        deepseek.load_project(project)


def test_review_prompt_uses_metadata_and_term_projections_not_raw_files(tmp_path):
    project = make_project(tmp_path)
    project_path = project / "translation-project.yaml"
    metadata = json.loads(project_path.read_text(encoding="utf-8"))
    metadata["translator"] = "K3-CANARY-IN-TRANSLATOR"
    metadata["versions"]["model"] = "K3-CANARY-IN-MODEL"
    project_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    term_path = project / "term-map.yaml"
    terms = json.loads(term_path.read_text(encoding="utf-8"))
    terms["terms"][0]["reviewer"] = "K3-CANARY-IN-REVIEWER"
    term_path.write_text(json.dumps(terms, ensure_ascii=False), encoding="utf-8")

    inputs = deepseek.load_project(project)
    prompt = json.dumps(deepseek.build_request_payload(inputs, deepseek.DEFAULT_MODEL), ensure_ascii=False)

    assert "K3-CANARY" not in prompt
    assert "ai-age" in prompt
    assert "缘起性空" in prompt


def test_review_hashes_bind_raw_bytes_and_inflight_check_detects_byte_change(tmp_path):
    project = make_project(tmp_path)
    source_path = project / "source.dj"
    target_path = project / "target.dj"
    raw_source = "# 人工智能时代\r\n\r\n空性不是虚无。\r\n".encode("utf-8")
    raw_target = (
        "# The Age of Artificial Intelligence\r\n\r\n"
        "Emptiness is not nothingness.\r\n"
    ).encode("utf-8")
    source_path.write_bytes(raw_source)
    target_path.write_bytes(raw_target)
    inputs = deepseek.load_project(project)

    assert inputs.source_sha256 == hashlib.sha256(raw_source).hexdigest()
    assert inputs.target_sha256 == hashlib.sha256(raw_target).hexdigest()

    project_path = project / "translation-project.yaml"
    project_path.write_bytes(project_path.read_bytes() + b"\n")
    with pytest.raises(deepseek.ReviewError, match="changed during review"):
        deepseek.assert_inputs_unchanged(inputs)


def test_http_request_merges_provenance_and_writes_fresh_certificate(
    monkeypatch, tmp_path, capsys
):
    project = make_project(tmp_path)
    (project / "source-analysis.json").write_text(
        '{"blind-canary":"K3-ANALYSIS-MUST-NOT-LEAK"}', encoding="utf-8"
    )
    inputs = deepseek.load_project(project)
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        return FakeHTTPResponse(api_envelope(inputs))

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-secret")
    monkeypatch.setattr(deepseek.urllib.request, "urlopen", fake_urlopen)

    assert deepseek.main([str(project)]) == 0

    output = project / "review-findings.jsonl"
    finding = json.loads(output.read_text(encoding="utf-8"))
    assert finding["reviewer"] == "DeepSeek V4 Pro"
    assert finding["paragraph_id"] == "L3"
    assert finding["stage"] == "semantic_review"
    assert finding["provider"] == "deepseek"
    assert finding["model"] == "deepseek-v4-pro"
    assert finding["source_sha256"] == inputs.source_sha256
    assert finding["target_sha256"] == inputs.target_sha256

    certificate = json.loads((project / "semantic-review.json").read_text("utf-8"))
    assert certificate["review_round"] == 1
    assert certificate["blocking_findings"] == 1
    assert certificate["blocking_finding_ids"] == [finding["finding_id"]]
    assert certificate["status"] == "blocking"
    assert certificate["source_sha256"] == inputs.source_sha256
    assert certificate["target_sha256"] == inputs.target_sha256
    assert certificate["findings_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert certificate["finding_ids"] == [finding["finding_id"]]

    assert len(calls) == 1
    request, timeout = calls[0]
    assert request.full_url == "https://api.deepseek.com/chat/completions"
    assert timeout == 300.0
    assert request.get_header("Authorization") == "Bearer test-only-secret"
    payload = json.loads(request.data.decode("utf-8"))
    assert payload["model"] == "deepseek-v4-pro"
    assert payload["thinking"] == {"type": "enabled"}
    assert payload["reasoning_effort"] == "high"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["max_tokens"] == 32_768
    serialized_payload = json.dumps(payload, ensure_ascii=False)
    assert "K3-ANALYSIS-MUST-NOT-LEAK" not in serialized_payload
    assert "source-analysis.json" not in serialized_payload
    assert "不做通用英文润色" in serialized_payload
    assert "意义修正约束" in serialized_payload
    assert "test-only-secret" not in capsys.readouterr().out


def test_environment_key_takes_priority_over_keychain(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "environment-secret")
    keychain = mock.Mock()
    monkeypatch.setattr(deepseek.subprocess, "run", keychain)

    credential = deepseek.load_credential()

    assert credential.value == "environment-secret"
    assert "environment" in credential.source
    keychain.assert_not_called()


def test_keychain_lookup_uses_current_user(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(deepseek.sys, "platform", "darwin")
    monkeypatch.setattr(deepseek.shutil, "which", lambda command: "/usr/bin/security")
    monkeypatch.setattr(deepseek.getpass, "getuser", lambda: "current-reviewer")
    completed = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="keychain-test-secret\n", stderr=""
    )
    keychain = mock.Mock(return_value=completed)
    monkeypatch.setattr(deepseek.subprocess, "run", keychain)

    credential = deepseek.load_credential()

    assert credential.value == "keychain-test-secret"
    assert credential.source == "macOS Keychain (mpi-deepseek-review/current-reviewer)"
    keychain.assert_called_once_with(
        [
            "security",
            "find-generic-password",
            "-a",
            "current-reviewer",
            "-s",
            "mpi-deepseek-review",
            "-w",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_dry_run_builds_isolated_request_without_network_or_secret_output(
    monkeypatch, tmp_path, capsys
):
    project = make_project(tmp_path)
    (project / "source-analysis.json").write_text(
        '{"canary":"NEVER-SEND-THIS"}', encoding="utf-8"
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dry-run-secret")
    urlopen = mock.Mock()
    monkeypatch.setattr(deepseek.urllib.request, "urlopen", urlopen)

    assert deepseek.main([str(project), "--dry-run"]) == 0

    captured = capsys.readouterr()
    assert "credential source: environment variable DEEPSEEK_API_KEY" in captured.out
    assert "source, target, term map, and project metadata only" in captured.out
    assert "dry-run-secret" not in captured.out + captured.err
    assert not (project / "review-findings.jsonl").exists()
    assert not (project / "semantic-review.json").exists()
    urlopen.assert_not_called()


@pytest.mark.parametrize(
    "exception, expected",
    [
        (urllib.error.URLError("offline and echoed manuscript"), "failed before a response"),
        (
            urllib.error.HTTPError(
                "https://api.deepseek.com", 400, "secret response body", {}, None
            ),
            "HTTP 400",
        ),
    ],
)
def test_api_failure_preserves_history_and_never_echoes_details(
    monkeypatch, tmp_path, capsys, exception, expected
):
    project = make_project(tmp_path)
    output = project / "review-findings.jsonl"
    output.write_text('{"finding_id":"old-1","status":"resolved"}\n', encoding="utf-8")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "api-failure-secret")
    monkeypatch.setattr(
        deepseek.urllib.request, "urlopen", mock.Mock(side_effect=exception)
    )

    assert deepseek.main([str(project)]) == 1

    captured = capsys.readouterr()
    assert output.read_text(encoding="utf-8") == '{"finding_id":"old-1","status":"resolved"}\n'
    assert not (project / "semantic-review.json").exists()
    assert expected in captured.err
    assert "api-failure-secret" not in captured.out + captured.err
    assert "echoed manuscript" not in captured.err
    assert "secret response body" not in captured.err


@pytest.mark.parametrize("content", ["not json", "", "   "])
def test_invalid_or_empty_model_content_preserves_history(
    monkeypatch, tmp_path, capsys, content
):
    project = make_project(tmp_path)
    inputs = deepseek.load_project(project)
    output = project / "review-findings.jsonl"
    output.write_text('{"finding_id":"old-1"}\n', encoding="utf-8")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "invalid-json-secret")
    monkeypatch.setattr(
        deepseek.urllib.request,
        "urlopen",
        lambda request, timeout: FakeHTTPResponse(api_envelope(inputs, content)),
    )

    assert deepseek.main([str(project)]) == 1

    captured = capsys.readouterr()
    assert output.read_text(encoding="utf-8") == '{"finding_id":"old-1"}\n'
    assert not (project / "semantic-review.json").exists()
    assert "invalid-json-secret" not in captured.out + captured.err


def test_local_validation_rejects_schema_enum_paragraph_language_and_prefix(tmp_path):
    project = make_project(tmp_path)
    inputs = deepseek.load_project(project)
    prefix = f"deepseek-{inputs.target_sha256[:12]}-"
    base = json.loads(valid_review_content(inputs))

    mutations = [
        (lambda document: document["findings"][0].update(extra="no"), "unknown fields"),
        (lambda document: document["findings"][0].update(severity="important"), "severity"),
        (lambda document: document["findings"][0].update(paragraph_id="L999"), "paragraph_id"),
        (lambda document: document["findings"][0].update(message="English only"), "Chinese"),
        (lambda document: document["findings"][0].update(finding_id="deepseek-old-L3-1"), "begin"),
    ]
    for mutate, expected in mutations:
        document = json.loads(json.dumps(base))
        mutate(document)
        with pytest.raises(deepseek.ReviewError, match=expected):
            deepseek.validate_review_content(
                json.dumps(document), inputs.paragraph_ids, finding_id_prefix=prefix
            )


def test_safe_merge_preserves_history_and_is_idempotent(tmp_path):
    project = make_project(tmp_path)
    output = project / "review-findings.jsonl"
    original = '{"finding_id":"human-1","status":"resolved","message":"历史"}\n'
    output.write_text(original, encoding="utf-8")
    inputs = deepseek.load_project(project)
    base, _ = deepseek.validate_review_content(
        valid_review_content(inputs),
        inputs.paragraph_ids,
        finding_id_prefix=f"deepseek-{inputs.target_sha256[:12]}-",
    )
    findings = deepseek.add_provenance(base, inputs, deepseek.DEFAULT_MODEL)

    merged, added, skipped = deepseek.prepare_merged_jsonl(output, findings)
    assert merged.startswith(original)
    assert added == 1 and skipped == 0
    deepseek.atomic_write_text(output, merged, "review findings")

    same, added, skipped = deepseek.prepare_merged_jsonl(output, findings)
    assert same == merged
    assert added == 0 and skipped == 1


def test_conflicting_finding_id_fails_before_write(tmp_path):
    project = make_project(tmp_path)
    inputs = deepseek.load_project(project)
    finding_id = f"deepseek-{inputs.target_sha256[:12]}-L3-1"
    original = json.dumps({"finding_id": finding_id, "message": "旧内容"}) + "\n"
    output = project / "review-findings.jsonl"
    output.write_text(original, encoding="utf-8")
    base, _ = deepseek.validate_review_content(
        valid_review_content(inputs),
        inputs.paragraph_ids,
        finding_id_prefix=f"deepseek-{inputs.target_sha256[:12]}-",
    )
    findings = deepseek.add_provenance(base, inputs, deepseek.DEFAULT_MODEL)

    with pytest.raises(deepseek.ReviewError, match="finding_id conflict"):
        deepseek.prepare_merged_jsonl(output, findings)
    assert output.read_text(encoding="utf-8") == original


def test_atomic_write_failure_preserves_old_output(monkeypatch, tmp_path, capsys):
    project = make_project(tmp_path)
    inputs = deepseek.load_project(project)
    output = project / "review-findings.jsonl"
    original = '{"finding_id":"old-1","status":"resolved"}\n'
    output.write_text(original, encoding="utf-8")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "atomic-test-secret")
    monkeypatch.setattr(
        deepseek.urllib.request,
        "urlopen",
        lambda request, timeout: FakeHTTPResponse(api_envelope(inputs)),
    )
    monkeypatch.setattr(
        deepseek.os, "replace", mock.Mock(side_effect=OSError("simulated failure"))
    )

    assert deepseek.main([str(project)]) == 1

    captured = capsys.readouterr()
    assert output.read_text(encoding="utf-8") == original
    assert "atomic-test-secret" not in captured.out + captured.err
    assert not list(project.glob(".review-findings.jsonl.*.tmp"))
    assert not (project / "semantic-review.json").exists()


def test_certificate_write_failure_rolls_back_findings(monkeypatch, tmp_path):
    project = make_project(tmp_path)
    output = project / "review-findings.jsonl"
    output.write_text("", encoding="utf-8")
    inputs = deepseek.load_project(project)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "rollback-test-secret")
    monkeypatch.setattr(
        deepseek.urllib.request,
        "urlopen",
        lambda request, timeout: FakeHTTPResponse(api_envelope(inputs)),
    )
    real_replace = deepseek.os.replace
    replace_calls = 0

    def fail_second_replace(source, destination):
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 2:
            raise OSError("simulated certificate rename failure")
        return real_replace(source, destination)

    monkeypatch.setattr(deepseek.os, "replace", fail_second_replace)
    assert deepseek.main([str(project)]) == 1
    assert output.read_bytes() == b""
    assert not (project / "semantic-review.json").exists()


def test_input_change_during_review_prevents_findings_and_certificate_write(
    monkeypatch, tmp_path
):
    project = make_project(tmp_path)
    inputs = deepseek.load_project(project)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "change-secret")

    def fake_urlopen(request, timeout):
        (project / "target.dj").write_text(
            "# Changed while reviewing\n\nChanged target.\n", encoding="utf-8"
        )
        return FakeHTTPResponse(api_envelope(inputs))

    monkeypatch.setattr(deepseek.urllib.request, "urlopen", fake_urlopen)
    assert deepseek.main([str(project)]) == 1
    assert not (project / "review-findings.jsonl").exists()
    assert not (project / "semantic-review.json").exists()


@pytest.mark.parametrize(
    "name",
    [
        "source.dj", "target.dj", "term-map.yaml", "translation-project.yaml",
        "bilingual.dj", "source-analysis.json", "semantic-review.json",
    ],
)
def test_output_cannot_overwrite_protected_project_files(
    monkeypatch, tmp_path, name
):
    project = make_project(tmp_path)
    protected = project / name
    before = protected.read_bytes() if protected.exists() else None
    monkeypatch.setenv("DEEPSEEK_API_KEY", "output-secret")

    assert deepseek.main([str(project), "--output", str(protected), "--dry-run"]) == 1
    assert protected.read_bytes() == before if before is not None else not protected.exists()


def test_two_blocking_rounds_mark_certificate_as_needing_human(monkeypatch, tmp_path):
    project = make_project(tmp_path)
    inputs = deepseek.load_project(project)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "round-secret")
    urlopen = mock.Mock(
        side_effect=lambda request, timeout: FakeHTTPResponse(api_envelope(inputs))
    )
    monkeypatch.setattr(deepseek.urllib.request, "urlopen", urlopen)

    assert deepseek.main([str(project)]) == 0
    assert deepseek.main([str(project)]) == 0
    certificate = json.loads((project / "semantic-review.json").read_text("utf-8"))
    assert certificate["review_round"] == 2
    assert certificate["status"] == "needs_human"
    assert len(certificate["blocking_finding_ids"]) == 1
    assert certificate["blocking_findings"] == len(
        certificate["blocking_finding_ids"]
    )
    assert len((project / "review-findings.jsonl").read_text("utf-8").splitlines()) == 1
    assert urlopen.call_count == 2

    # The third automated loop is stopped before credentials or network.  A
    # human must first resolve/reject/defer-and-adjudicate the blocker.
    assert deepseek.main([str(project)]) == 1
    assert urlopen.call_count == 2


def test_human_resolution_after_two_rounds_allows_final_recheck(
    monkeypatch, tmp_path
):
    project = make_project(tmp_path)
    inputs = deepseek.load_project(project)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "round-secret")
    urlopen = mock.Mock(
        side_effect=lambda request, timeout: FakeHTTPResponse(api_envelope(inputs))
    )
    monkeypatch.setattr(deepseek.urllib.request, "urlopen", urlopen)

    assert deepseek.main([str(project)]) == 0
    assert deepseek.main([str(project)]) == 0
    path = project / "review-findings.jsonl"
    finding = json.loads(path.read_text("utf-8"))
    finding["status"] = "resolved"
    finding["resolution_note"] = "人工依据上下文裁决并完成意义修正。"
    path.write_text(json.dumps(finding, ensure_ascii=False) + "\n", "utf-8")

    clear_content = json.dumps(
        {"findings": [], "summary": "人工裁决后的最终复核未发现阻断问题。"},
        ensure_ascii=False,
    )
    urlopen.side_effect = lambda request, timeout: FakeHTTPResponse(
        api_envelope(inputs, clear_content)
    )
    assert deepseek.main([str(project)]) == 0
    certificate = json.loads((project / "semantic-review.json").read_text("utf-8"))
    assert certificate["review_round"] == 3
    assert certificate["status"] == "clear"


def test_needs_human_cannot_be_bypassed_with_alternate_output(
    monkeypatch, tmp_path
):
    project = make_project(tmp_path)
    inputs = deepseek.load_project(project)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "round-secret")
    urlopen = mock.Mock(
        side_effect=lambda request, timeout: FakeHTTPResponse(api_envelope(inputs))
    )
    monkeypatch.setattr(deepseek.urllib.request, "urlopen", urlopen)
    assert deepseek.main([str(project)]) == 0
    assert deepseek.main([str(project)]) == 0
    alternate = project / "alternate-findings.jsonl"
    alternate.write_text("", encoding="utf-8")

    assert deepseek.main([str(project), "--output", str(alternate)]) == 1
    assert urlopen.call_count == 2


def test_first_round_custom_output_is_rejected_before_credential_or_network(
    monkeypatch, tmp_path
):
    project = make_project(tmp_path)
    alternate = project / "alternate-findings.jsonl"
    alternate.write_text("existing alternate history\n", encoding="utf-8")
    credential = mock.Mock()
    urlopen = mock.Mock()
    monkeypatch.setattr(deepseek, "load_credential", credential)
    monkeypatch.setattr(deepseek.urllib.request, "urlopen", urlopen)

    assert deepseek.main([str(project), "--output", str(alternate)]) == 1
    credential.assert_not_called()
    urlopen.assert_not_called()
    assert alternate.read_text(encoding="utf-8") == "existing alternate history\n"
    assert not (project / "review-findings.jsonl").exists()
    assert not (project / "semantic-review.json").exists()


def test_deleting_certified_blocker_cannot_be_hidden_by_another_resolution(
    monkeypatch, tmp_path
):
    project = make_project(tmp_path)
    inputs = deepseek.load_project(project)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "round-secret")
    urlopen = mock.Mock(
        side_effect=lambda request, timeout: FakeHTTPResponse(api_envelope(inputs))
    )
    monkeypatch.setattr(deepseek.urllib.request, "urlopen", urlopen)

    assert deepseek.main([str(project)]) == 0
    assert deepseek.main([str(project)]) == 0
    certificate = json.loads((project / "semantic-review.json").read_text("utf-8"))
    certified_id = certificate["blocking_finding_ids"][0]

    # This changed history would satisfy the former global "some blocker was
    # resolved" check while deleting the exact finding that required a human.
    substitute = {
        "finding_id": "unrelated-resolved-major",
        "paragraph_id": "L3",
        "severity": "major",
        "category": "meaning",
        "message": "另一项已经处理的问题。",
        "suggestion": "保留历史。",
        "status": "resolved",
        "reviewer": "Human",
        "resolution_note": "人工处理了另一项问题。",
    }
    (project / "review-findings.jsonl").write_text(
        json.dumps(substitute, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    assert deepseek.main([str(project)]) == 1
    assert urlopen.call_count == 2
    assert certified_id not in (project / "review-findings.jsonl").read_text("utf-8")


def test_first_blocking_round_history_cannot_be_deleted_before_second_review(
    monkeypatch, tmp_path
):
    project = make_project(tmp_path)
    inputs = deepseek.load_project(project)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "round-secret")
    urlopen = mock.Mock(
        side_effect=lambda request, timeout: FakeHTTPResponse(api_envelope(inputs))
    )
    monkeypatch.setattr(deepseek.urllib.request, "urlopen", urlopen)

    assert deepseek.main([str(project)]) == 0
    certificate = json.loads((project / "semantic-review.json").read_text("utf-8"))
    assert certificate["status"] == "blocking"
    assert certificate["finding_ids"]

    (project / "review-findings.jsonl").write_text("", encoding="utf-8")
    assert deepseek.main([str(project)]) == 1
    assert urlopen.call_count == 1


def test_certificate_finding_ids_cover_complete_merged_history(tmp_path):
    project = make_project(tmp_path)
    inputs = deepseek.load_project(project)
    historical = {
        "finding_id": "historical-minor",
        "paragraph_id": "L1",
        "severity": "minor",
        "category": "meaning",
        "message": "历史记录。",
        "suggestion": "保留历史。",
        "status": "resolved",
        "reviewer": "Human",
        "resolution_note": "已经处理。",
    }
    current = json.loads(valid_review_content(inputs))["findings"][0]
    merged = (
        json.dumps(historical, ensure_ascii=False) + "\n"
        + json.dumps(current, ensure_ascii=False) + "\n"
    )
    certificate = deepseek.build_semantic_certificate(
        inputs=inputs,
        model=deepseek.DEFAULT_MODEL,
        review_round=1,
        findings=[current],
        merged_jsonl=merged,
        summary="完整历史测试。",
    )
    assert certificate["finding_ids"] == ["historical-minor", current["finding_id"]]


def test_clear_round_does_not_count_as_a_failed_blocking_revision_cycle(tmp_path):
    project = make_project(tmp_path)
    inputs = deepseek.load_project(project)
    current = json.loads(valid_review_content(inputs))["findings"][0]
    merged = json.dumps(current, ensure_ascii=False) + "\n"

    first_blocker = deepseek.build_semantic_certificate(
        inputs=inputs,
        model=deepseek.DEFAULT_MODEL,
        review_round=3,
        findings=[current],
        merged_jsonl=merged,
        summary="Earlier rounds were clear.",
        previous_status="clear",
    )
    second_blocker = deepseek.build_semantic_certificate(
        inputs=inputs,
        model=deepseek.DEFAULT_MODEL,
        review_round=4,
        findings=[current],
        merged_jsonl=merged,
        summary="A consecutive blocking cycle remains.",
        previous_status="blocking",
    )

    assert first_blocker["status"] == "blocking"
    assert second_blocker["status"] == "needs_human"


@pytest.mark.parametrize(
    "updates",
    [
        {"status": "resolved"},
        {"status": "deferred", "resolution_note": "尚未裁决。"},
        {
            "status": "resolved",
            "severity": "minor",
            "resolution_note": "仅降低严重度。",
        },
    ],
)
def test_each_certified_blocker_requires_final_status_note_and_severity(
    monkeypatch, tmp_path, updates
):
    project = make_project(tmp_path)
    inputs = deepseek.load_project(project)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "round-secret")
    urlopen = mock.Mock(
        side_effect=lambda request, timeout: FakeHTTPResponse(api_envelope(inputs))
    )
    monkeypatch.setattr(deepseek.urllib.request, "urlopen", urlopen)
    assert deepseek.main([str(project)]) == 0
    assert deepseek.main([str(project)]) == 0

    path = project / "review-findings.jsonl"
    finding = json.loads(path.read_text("utf-8"))
    finding.update(updates)
    path.write_text(json.dumps(finding, ensure_ascii=False) + "\n", "utf-8")

    assert deepseek.main([str(project)]) == 1
    assert urlopen.call_count == 2


def test_truncated_model_response_preserves_history(monkeypatch, tmp_path):
    project = make_project(tmp_path)
    inputs = deepseek.load_project(project)
    history = project / "review-findings.jsonl"
    history.write_text('{"finding_id":"old-1"}\n', encoding="utf-8")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "length-secret")
    monkeypatch.setattr(
        deepseek.urllib.request,
        "urlopen",
        lambda request, timeout: FakeHTTPResponse(
            api_envelope(inputs, valid_review_content(inputs), finish_reason="length")
        ),
    )

    assert deepseek.main([str(project)]) == 1
    assert history.read_text("utf-8") == '{"finding_id":"old-1"}\n'
    assert not (project / "semantic-review.json").exists()


def test_nonblocking_review_is_clear(monkeypatch, tmp_path):
    project = make_project(tmp_path)
    inputs = deepseek.load_project(project)
    clear_content = json.dumps(
        {"findings": [], "summary": "准确性复核完成，未发现问题。"},
        ensure_ascii=False,
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "clear-secret")
    monkeypatch.setattr(
        deepseek.urllib.request,
        "urlopen",
        lambda request, timeout: FakeHTTPResponse(api_envelope(inputs, clear_content)),
    )

    assert deepseek.main([str(project)]) == 0
    certificate = json.loads((project / "semantic-review.json").read_text("utf-8"))
    assert certificate["blocking_findings"] == 0
    assert certificate["blocking_finding_ids"] == []
    assert certificate["status"] == "clear"
    assert (project / "review-findings.jsonl").read_text("utf-8") == ""


def test_empty_current_response_cannot_hide_unresolved_historical_blocker(
    monkeypatch, tmp_path
):
    project = make_project(tmp_path)
    inputs = deepseek.load_project(project)
    historical = {
        "finding_id": "human-major-1",
        "paragraph_id": "L3",
        "severity": "major",
        "category": "meaning",
        "message": "历史问题",
        "suggestion": "仍须处理",
        "status": "deferred",
        "reviewer": "Human",
    }
    (project / "review-findings.jsonl").write_text(
        json.dumps(historical, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    clear_content = json.dumps(
        {"findings": [], "summary": "本轮复核未发现新的问题。"},
        ensure_ascii=False,
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "clear-secret")
    monkeypatch.setattr(
        deepseek.urllib.request,
        "urlopen",
        lambda request, timeout: FakeHTTPResponse(api_envelope(inputs, clear_content)),
    )

    assert deepseek.main([str(project)]) == 0
    certificate = json.loads((project / "semantic-review.json").read_text("utf-8"))
    assert certificate["blocking_findings"] == 1
    assert certificate["blocking_finding_ids"] == [historical["finding_id"]]
    assert certificate["status"] == "blocking"


def test_external_review_policy_stops_before_credential(monkeypatch, tmp_path):
    project = make_project(tmp_path)
    metadata = json.loads((project / "translation-project.yaml").read_text("utf-8"))
    metadata["external_semantic_review"] = "deny"
    (project / "translation-project.yaml").write_text(json.dumps(metadata), "utf-8")
    credential = mock.Mock()
    monkeypatch.setattr(deepseek, "load_credential", credential)

    assert deepseek.main([str(project)]) == 1
    credential.assert_not_called()


def test_invalid_external_review_policy_fails_closed_before_credential(
    monkeypatch, tmp_path
):
    project = make_project(tmp_path)
    metadata = json.loads((project / "translation-project.yaml").read_text("utf-8"))
    metadata["external_semantic_review"] = "sometimes"
    (project / "translation-project.yaml").write_text(json.dumps(metadata), "utf-8")
    credential = mock.Mock()
    monkeypatch.setattr(deepseek, "load_credential", credential)

    assert deepseek.main([str(project)]) == 1
    credential.assert_not_called()


@pytest.mark.parametrize("release", [None, "sensitive", {"level": "senstive"}])
def test_invalid_release_policy_fails_closed_before_credential(
    monkeypatch, tmp_path, release
):
    project = make_project(tmp_path)
    metadata = json.loads((project / "translation-project.yaml").read_text("utf-8"))
    metadata["release"] = release
    (project / "translation-project.yaml").write_text(json.dumps(metadata), "utf-8")
    credential = mock.Mock()
    monkeypatch.setattr(deepseek, "load_credential", credential)

    assert deepseek.main([str(project)]) == 1
    credential.assert_not_called()


def test_missing_or_misaligned_input_stops_before_credential_lookup(
    monkeypatch, tmp_path
):
    project = make_project(tmp_path)
    (project / "target.dj").write_text("one line only\n", encoding="utf-8")
    credential = mock.Mock()
    monkeypatch.setattr(deepseek, "load_credential", credential)

    assert deepseek.main([str(project), "--dry-run"]) == 1
    credential.assert_not_called()


def test_cli_does_not_accept_or_echo_api_key(tmp_path, capsys):
    project = make_project(tmp_path)
    with pytest.raises(SystemExit):
        deepseek.parse_args([str(project), "--api-key", "must-never-be-accepted"])
    captured = capsys.readouterr()
    assert "must-never-be-accepted" not in captured.out + captured.err
    assert "not accepted on the command line" in captured.err

    with pytest.raises(SystemExit):
        deepseek.parse_args([str(project), "--api_key", "underscore-secret-canary"])
    captured = capsys.readouterr()
    assert "underscore-secret-canary" not in captured.out + captured.err

    with pytest.raises(SystemExit):
        deepseek.parse_args(
            [str(project), "--deepseek-api-key", "provider-secret-canary"]
        )
    captured = capsys.readouterr()
    assert "provider-secret-canary" not in captured.out + captured.err


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "0", "-1"])
def test_timeout_must_be_positive_and_finite(value):
    with pytest.raises(SystemExit):
        deepseek.parse_args(["project", "--timeout", value])


def test_project_lock_stops_parallel_review_before_credential(monkeypatch, tmp_path):
    project = make_project(tmp_path)
    descriptor = deepseek.acquire_project_review_lock(
        project / "translation-project.yaml"
    )
    credential = mock.Mock()
    monkeypatch.setattr(deepseek, "load_credential", credential)
    try:
        assert deepseek.main([str(project), "--dry-run"]) == 1
    finally:
        deepseek.release_project_review_lock(descriptor)
    credential.assert_not_called()


def test_focused_batches_cover_each_paragraph_once_with_adjacent_context(tmp_path):
    project = make_project(tmp_path)
    inputs = deepseek.load_project(project)

    batches = deepseek.build_review_batches(inputs, 1)

    assert [batch.ordered_paragraph_ids for batch in batches] == [("L1",), ("L3",)]
    assert "<review-focus>\n[L1]" in batches[0].aligned_text
    assert "<adjacent-context>\n[L3]" in batches[0].aligned_text
    assert "<adjacent-context>\n[L1]" in batches[1].aligned_text
    assert "<review-focus>\n[L3]" in batches[1].aligned_text
    assert set().union(*(batch.paragraph_ids for batch in batches)) == inputs.paragraph_ids


@pytest.mark.parametrize("batch_size", [1, 2, 4, 9])
def test_focused_batches_report_each_of_six_paragraphs_exactly_once(
    tmp_path, batch_size
):
    project = make_project(tmp_path)
    source_lines = [f"段落{i}" for i in range(1, 7)]
    target_lines = [f"Paragraph {i}" for i in range(1, 7)]
    (project / "source.dj").write_text(
        "\n\n".join(source_lines) + "\n", encoding="utf-8"
    )
    (project / "target.dj").write_text(
        "\n\n".join(target_lines) + "\n", encoding="utf-8"
    )
    inputs = deepseek.load_project(project)
    batches = deepseek.build_review_batches(inputs, batch_size)
    reported = [
        paragraph_id
        for batch in batches
        for paragraph_id in batch.ordered_paragraph_ids
    ]
    assert reported == ["L1", "L3", "L5", "L7", "L9", "L11"]
    assert len(reported) == len(set(reported)) == 6


def test_main_runs_all_focused_batches_before_one_atomic_clear_write(
    monkeypatch, tmp_path
):
    project = make_project(tmp_path)
    inputs = deepseek.load_project(project)
    calls = []
    empty = json.dumps(
        {"findings": [], "summary": "本批逐段复核完成，未发现问题。"},
        ensure_ascii=False,
    )

    def fake_urlopen(request, timeout):
        calls.append(json.loads(request.data.decode("utf-8")))
        return FakeHTTPResponse(api_envelope(inputs, empty))

    monkeypatch.setenv("DEEPSEEK_API_KEY", "batch-secret")
    monkeypatch.setattr(deepseek.urllib.request, "urlopen", fake_urlopen)

    assert deepseek.main([str(project), "--batch-size", "1"]) == 0
    assert len(calls) == 2
    prompts = [call["messages"][1]["content"] for call in calls]
    assert "<review-focus-ids>L1</review-focus-ids>" in prompts[0]
    assert "<review-focus-ids>L3</review-focus-ids>" in prompts[1]
    assert all("source-analysis.json" not in json.dumps(call) for call in calls)
    certificate = json.loads((project / "semantic-review.json").read_text("utf-8"))
    assert certificate["status"] == "clear"
    assert certificate["summary"].startswith("分段聚焦复核共2批。")
    assert (project / "review-findings.jsonl").read_text("utf-8") == ""


def test_context_only_finding_rejects_entire_batch_run_without_writes(
    monkeypatch, tmp_path
):
    project = make_project(tmp_path)
    inputs = deepseek.load_project(project)
    empty = json.dumps(
        {"findings": [], "summary": "第一批复核完成，未发现问题。"},
        ensure_ascii=False,
    )
    invalid_context_finding = json.dumps(
        {
            "findings": [
                {
                    "finding_id": f"deepseek-{inputs.target_sha256[:12]}-L1-1",
                    "paragraph_id": "L1",
                    "severity": "major",
                    "category": "meaning",
                    "message": "上下文段落不应在本批报告。",
                    "suggestion": "只允许报告本批焦点段落。",
                    "status": "open",
                    "reviewer": "DeepSeek V4 Pro",
                }
            ],
            "summary": "第二批错误地报告了相邻上下文。",
        },
        ensure_ascii=False,
    )
    responses = iter((empty, invalid_context_finding))

    def fake_urlopen(request, timeout):
        return FakeHTTPResponse(api_envelope(inputs, next(responses)))

    monkeypatch.setenv("DEEPSEEK_API_KEY", "batch-secret")
    monkeypatch.setattr(deepseek.urllib.request, "urlopen", fake_urlopen)

    assert deepseek.main([str(project), "--batch-size", "1"]) == 1
    assert not (project / "review-findings.jsonl").exists()
    assert not (project / "semantic-review.json").exists()


@pytest.mark.parametrize("value", ["0", "51"])
def test_batch_size_is_bounded(value):
    with pytest.raises(SystemExit):
        deepseek.parse_args(["project", "--batch-size", value])
