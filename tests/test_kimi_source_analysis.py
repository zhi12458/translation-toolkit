import hashlib
import importlib.util
import json
import subprocess
import sys
import urllib.error
from pathlib import Path
from unittest import mock

import pytest


ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "scripts" / "kimi-source-analysis.py"
SPEC = importlib.util.spec_from_file_location("mpi_kimi_source_analysis", MODULE_PATH)
kimi = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = kimi
SPEC.loader.exec_module(kimi)


def make_project(tmp_path, *, policy="allow", release_level="draft"):
    project = tmp_path / "article"
    project.mkdir()
    (project / "source.dj").write_text(
        "空性不是虚无。\n\n慈悲需要智慧。\n", encoding="utf-8"
    )
    # A target exists to prove that the blind loader and requests ignore it.
    (project / "target.dj").write_text(
        "NEVER-SEND-THIS-TARGET\n\nNOR-THIS-TRANSLATION\n", encoding="utf-8"
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
                "project_id": "blind-source-analysis",
                "title": "盲态源义分析",
                "author": "MPI",
                "translator": "Test Translator",
                "source_origin": "written_text",
                "delivery_format": "publication_article",
                "external_semantic_review": policy,
                "genre": "written_article",
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
                    "level": release_level,
                    "independent_review_required": False,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return project


def valid_paragraph(paragraph_id, source_text):
    evidence = source_text.rstrip("。")
    return {
        "paragraph_id": paragraph_id,
        "predicates": [
            {
                "predicate": evidence,
                "canonical_meaning": "保持原句命题",
                "evidence": evidence,
                "participants": [],
            }
        ],
        "relations": [],
        "temporal_relations": [],
        "operators": [],
        "references_and_ellipsis": [],
        "elliptical_subject": [],
        "cultural_allusions": [],
        "competing_interpretations": [],
        "must_preserve": ["保留原句的判断关系"],
        "must_not_invent": ["不得擅增时态或情态"],
        "status": "clear",
    }


def api_envelope(paragraphs, *, content_override=None):
    content = (
        content_override
        if content_override is not None
        else json.dumps({"paragraphs": paragraphs}, ensure_ascii=False)
    )
    return json.dumps(
        {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "reasoning_content": "private model reasoning",
                        "content": content,
                    },
                }
            ]
        },
        ensure_ascii=False,
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


def test_blind_loader_never_opens_or_requires_target(monkeypatch, tmp_path):
    project = make_project(tmp_path)
    (project / "target.dj").unlink()
    original_read_text = Path.read_text

    def guarded_read_text(path, *args, **kwargs):
        if path.name == "target.dj":
            raise AssertionError("blind Kimi stage attempted to read target.dj")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    inputs = kimi.load_project(project)

    assert [paragraph.paragraph_id for paragraph in inputs.paragraphs] == ["L1", "L3"]
    assert not hasattr(inputs, "target")


def test_request_is_strict_high_and_contains_full_source_but_not_target(tmp_path):
    project = make_project(tmp_path)
    inputs = kimi.load_project(project)
    schema = kimi.load_analysis_schema()

    payload = kimi.build_request_payload(inputs, inputs.paragraphs[:1], schema)
    prompt = "\n".join(message["content"] for message in payload["messages"])

    assert payload["model"] == "kimi-k3"
    assert payload["reasoning_effort"] == "high"
    assert "thinking" not in payload
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["strict"] is True
    assert payload["max_completion_tokens"] == 32_768
    assert "max_tokens" not in payload
    assert "空性不是虚无。" in prompt
    assert "慈悲需要智慧。" in prompt  # complete context, even outside the batch
    assert "NEVER-SEND-THIS-TARGET" not in prompt
    assert "NOR-THIS-TRANSLATION" not in prompt
    assert "主标题、目录项和章节标题必须识别中心词" in prompt
    assert payload["messages"][-1]["content"].strip().endswith(
        "</requested-paragraph-ids>"
    )
    assert "complete-indexed-chinese-source" in payload["messages"][-2]["content"]
    paragraph_id_schema = payload["response_format"]["json_schema"]["schema"]
    assert paragraph_id_schema["properties"]["paragraphs"]["items"]["properties"][
        "paragraph_id"
    ]["enum"] == ["L1"]


def test_du_shan_qi_shen_requires_cultural_allusion_and_must_preserve(tmp_path):
    project = make_project(tmp_path)
    (project / "source.dj").write_text(
        "倘生不逢时，才会退隐江湖、独善其身。\n", encoding="utf-8"
    )
    inputs = kimi.load_project(project)
    schema = kimi.load_analysis_schema()
    analysis = valid_paragraph("L1", inputs.paragraphs[0].text)
    analysis["temporal_relations"] = [
        {
            "marker": "时",
            "relation": "when",
            "event_or_scope": "生不逢时",
            "linked_event": "退隐江湖",
            "evidence_status": "explicit",
            "notes": "时限定所生处境。",
        },
        {
            "marker": "才",
            "relation": "only_then",
            "event_or_scope": "退隐江湖、独善其身",
            "linked_event": "生不逢时",
            "evidence_status": "explicit",
            "notes": "才表示条件满足后方发生。",
        },
    ]
    analysis["must_preserve"] = ["必须保留时与才的约束"]
    content = json.dumps({"paragraphs": [analysis]}, ensure_ascii=False)
    with pytest.raises(kimi.AnalysisError, match="cultural_allusions omits known allusion"):
        kimi.validate_batch_content(content, inputs.paragraphs, schema, inputs.source)

    analysis["cultural_allusions"] = [{
        "expression": "独善其身",
        "kind": "canonical_allusion",
        "source_or_origin": "《孟子·尽心上》",
        "contextual_meaning": "退隐后修养自身德行并保持节操。",
        "competing_senses": ["后起义可指只顾自己。"],
        "translation_constraint": "采用古义，不得误作自私自利。",
        "research_trigger": "mpi_missing",
        "external_research_required": True,
        "evidence_status": "explicit",
        "notes": "本段与生不逢时和退隐并列，采用古义。",
    }]
    analysis["must_preserve"].append("独善其身采用古义")
    validated = kimi.validate_batch_content(
        json.dumps({"paragraphs": [analysis]}, ensure_ascii=False),
        inputs.paragraphs,
        schema,
        inputs.source,
    )
    assert validated[0]["cultural_allusions"][0]["research_trigger"] == "mpi_missing"


def test_provider_schema_gives_every_enum_and_const_an_explicit_type(tmp_path):
    """Kimi MFJS rejects otherwise valid JSON Schema enum/const shorthands."""
    inputs = kimi.load_project(make_project(tmp_path))
    schema = kimi.build_provider_schema(
        kimi.load_analysis_schema(), [item.paragraph_id for item in inputs.paragraphs]
    )

    def walk(node):
        if isinstance(node, dict):
            if "enum" in node or "const" in node:
                assert "type" in node
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)


def test_provider_schema_is_documented_mfjs_projection(tmp_path):
    inputs = kimi.load_project(make_project(tmp_path))
    schema = kimi.build_provider_schema(
        kimi.load_analysis_schema(), [item.paragraph_id for item in inputs.paragraphs]
    )

    def walk(node):
        if not isinstance(node, dict):
            return
        assert set(node) <= kimi.MFJS_WIRE_KEYWORDS
        for key, value in node.items():
            if key == "properties":
                for subschema in value.values():
                    walk(subschema)
            elif key == "items":
                walk(value)
            elif key == "anyOf":
                for option in value:
                    walk(option)

    walk(schema)
    rendered = json.dumps(schema, ensure_ascii=False)
    assert "maxLength" not in rendered
    assert "maxItems" not in rendered
    assert "minLength" not in rendered
    assert "explicit 时必须是当前段落" in rendered


@pytest.mark.parametrize("filename", ["translation-project.yaml", "term-map.yaml"])
def test_blind_inputs_reject_unknown_fields_before_prompt_build(tmp_path, filename):
    project = make_project(tmp_path)
    path = project / filename
    document = json.loads(path.read_text(encoding="utf-8"))
    document["hidden_target"] = "SMUGGLED-ENGLISH-DRAFT"
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(kimi.AnalysisError, match="unknown fields"):
        kimi.load_project(project)


def test_prompt_uses_metadata_and_term_projections_not_raw_files(tmp_path):
    project = make_project(tmp_path)
    project_path = project / "translation-project.yaml"
    metadata = json.loads(project_path.read_text(encoding="utf-8"))
    metadata["translator"] = "TARGET-CANARY-IN-TRANSLATOR"
    metadata["versions"]["model"] = "TARGET-CANARY-IN-MODEL"
    project_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    term_path = project / "term-map.yaml"
    terms = json.loads(term_path.read_text(encoding="utf-8"))
    terms["terms"][0]["reviewer"] = "TARGET-CANARY-IN-REVIEWER"
    term_path.write_text(json.dumps(terms, ensure_ascii=False), encoding="utf-8")

    inputs = kimi.load_project(project)
    payload = kimi.build_request_payload(inputs, inputs.paragraphs[:1], kimi.load_analysis_schema())
    prompt = json.dumps(payload["messages"], ensure_ascii=False)

    assert "TARGET-CANARY" not in prompt
    assert "blind-source-analysis" in prompt
    assert "缘起性空" in prompt


def test_hashes_bind_exact_raw_bytes_and_inflight_check_detects_byte_change(tmp_path):
    project = make_project(tmp_path)
    source_path = project / "source.dj"
    raw_source = "空性不是虚无。\r\n\r\n慈悲需要智慧。\r\n".encode("utf-8")
    source_path.write_bytes(raw_source)
    inputs = kimi.load_project(project)

    assert inputs.source_sha256 == hashlib.sha256(raw_source).hexdigest()

    project_path = project / "translation-project.yaml"
    project_path.write_bytes(project_path.read_bytes() + b"\n")
    with pytest.raises(kimi.AnalysisError, match="changed during analysis"):
        kimi.assert_inputs_unchanged(inputs)


def test_schema_uses_closed_required_objects_and_nullable_unknowns():
    schema = kimi.load_analysis_schema()

    def inspect(node):
        if not isinstance(node, dict):
            return
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False
            assert set(node.get("required", [])) == set(node.get("properties", {}))
        for value in node.values():
            if isinstance(value, dict):
                inspect(value)
            elif isinstance(value, list):
                for item in value:
                    inspect(item)

    provider = kimi.build_provider_schema(schema, ["L1"])
    inspect(provider)
    participant = provider["properties"]["paragraphs"]["items"]["properties"][
        "predicates"
    ]["items"]["properties"]["participants"]["items"]["properties"]
    assert {option.get("type") for option in participant["participant"]["anyOf"]} == {
        "string",
        "null",
    }
    assert participant["evidence_status"]["enum"] == [
        "explicit",
        "contextual_inference",
        "ambiguous",
    ]


def test_temporal_markers_require_dedicated_relations_and_must_preserve():
    source = "我想，多数人出家时，也是为了解脱；出家后，仍要修行。"
    paragraph = kimi.SourceParagraph("L1", source)
    schema = kimi.load_analysis_schema()
    analysis = valid_paragraph("L1", source)

    with pytest.raises(kimi.AnalysisError, match="temporal_relations omits source marker 时"):
        kimi.validate_batch_content(
            json.dumps({"paragraphs": [analysis]}, ensure_ascii=False),
            [paragraph], schema, source,
        )

    analysis["temporal_relations"] = [
        {
            "marker": "出家时",
            "relation": "when",
            "event_or_scope": "多数人最初出家的时点",
            "linked_event": "为了解脱",
            "evidence_status": "explicit",
            "notes": "保留出家当时的初衷。",
        },
        {
            "marker": "出家后",
            "relation": "after",
            "event_or_scope": "出家后的修行",
            "linked_event": "多数人最初出家",
            "evidence_status": "explicit",
            "notes": "保留出家前后对照。",
        },
        {
            "marker": "仍",
            "relation": "continuation",
            "event_or_scope": "修行持续不变",
            "linked_event": None,
            "evidence_status": "explicit",
            "notes": "仍表示持续。",
        },
    ]
    analysis["must_preserve"] = [
        "“时”限定最初出家的时点",
        "“后”建立出家前后关系",
        "“仍”表示修行持续",
    ]
    validated = kimi.validate_batch_content(
        json.dumps({"paragraphs": [analysis]}, ensure_ascii=False),
        [paragraph], schema, source,
    )
    assert validated[0]["temporal_relations"][0]["relation"] == "when"


def test_compressed_buddhist_parallel_requires_subject_and_separate_causes():
    source = (
        "像佛陀那样，智不住三有，悲不住涅槃。"
        "因为智慧，所以超越轮回；因为慈悲，所以积极入世。"
    )
    paragraph = kimi.SourceParagraph("L1", source)
    schema = kimi.load_analysis_schema()
    analysis = valid_paragraph("L1", source)

    with pytest.raises(kimi.AnalysisError, match="elliptical_subject omits"):
        kimi.validate_batch_content(
            json.dumps({"paragraphs": [analysis]}, ensure_ascii=False),
            [paragraph], schema, source,
        )

    analysis["elliptical_subject"] = [
        {
            "clause": "智不住三有，悲不住涅槃",
            "predicate": "不住",
            "subject_resolution": "佛陀所示范的修行者",
            "subject_evidence": "像佛陀那样",
            "role_bindings": [
                {
                    "role": "state_holder",
                    "participant": "佛陀所示范的修行者",
                    "evidence": "像佛陀那样",
                    "evidence_status": "contextual_inference",
                    "notes": "修行者是不住两边的状态承担者。",
                },
                {
                    "role": "cause",
                    "participant": "智慧",
                    "evidence": "因为智慧",
                    "evidence_status": "explicit",
                    "notes": "智慧说明不住三有的原因。",
                },
                {
                    "role": "cause",
                    "participant": "慈悲",
                    "evidence": "因为慈悲",
                    "evidence_status": "explicit",
                    "notes": "慈悲说明不住涅槃的原因。",
                },
            ],
            "evidence_status": "contextual_inference",
            "notes": "不得把智慧或慈悲提升为不住的英文主语。",
        }
    ]
    validated = kimi.validate_batch_content(
        json.dumps({"paragraphs": [analysis]}, ensure_ascii=False),
        [paragraph], schema, source,
    )
    assert validated[0]["elliptical_subject"][0]["subject_resolution"] == "佛陀所示范的修行者"

    analysis["elliptical_subject"][0]["role_bindings"][0].update(
        participant="智慧", evidence="智慧", evidence_status="explicit"
    )
    with pytest.raises(kimi.AnalysisError, match="promotes an explicit cause"):
        kimi.validate_batch_content(
            json.dumps({"paragraphs": [analysis]}, ensure_ascii=False),
            [paragraph], schema, source,
        )


def test_environment_key_takes_priority_over_keychain(monkeypatch):
    monkeypatch.setenv("KIMI_API_KEY", "environment-secret")
    keychain = mock.Mock()
    monkeypatch.setattr(kimi.subprocess, "run", keychain)

    credential = kimi.load_credential()

    assert credential.value == "environment-secret"
    assert "environment" in credential.source
    keychain.assert_not_called()


def test_keychain_uses_service_and_current_account(monkeypatch):
    monkeypatch.delenv("KIMI_API_KEY", raising=False)
    monkeypatch.setattr(kimi.sys, "platform", "darwin")
    monkeypatch.setattr(kimi.shutil, "which", lambda command: "/usr/bin/security")
    monkeypatch.setattr(kimi.getpass, "getuser", lambda: "current-reviewer")
    completed = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="keychain-test-secret\n", stderr=""
    )
    keychain = mock.Mock(return_value=completed)
    monkeypatch.setattr(kimi.subprocess, "run", keychain)

    credential = kimi.load_credential()

    assert credential.value == "keychain-test-secret"
    assert credential.source == "macOS Keychain (mpi-kimi-review/current-reviewer)"
    keychain.assert_called_once_with(
        [
            "security",
            "find-generic-password",
            "-a",
            "current-reviewer",
            "-s",
            "mpi-kimi-review",
            "-w",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_cli_does_not_accept_or_echo_api_key(tmp_path, capsys):
    project = make_project(tmp_path)
    with pytest.raises(SystemExit):
        kimi.parse_args([str(project), "--api-key", "must-never-be-accepted"])
    captured = capsys.readouterr()
    assert "must-never-be-accepted" not in captured.out + captured.err
    assert "not accepted on the command line" in captured.err

    with pytest.raises(SystemExit):
        kimi.parse_args([str(project), "--api_key", "underscore-secret-canary"])
    captured = capsys.readouterr()
    assert "underscore-secret-canary" not in captured.out + captured.err

    args = kimi.parse_args([str(project), "--max-tokens", "4096"])
    assert args.max_tokens == 4096


def test_serial_batches_validate_cover_hash_and_atomically_write(
    monkeypatch, tmp_path, capsys
):
    project = make_project(tmp_path)
    calls = []
    analyses = {
        "L1": valid_paragraph("L1", "空性不是虚无。"),
        "L3": valid_paragraph("L3", "慈悲需要智慧。"),
    }

    def fake_urlopen(request, timeout):
        payload = json.loads(request.data.decode("utf-8"))
        ids = payload["response_format"]["json_schema"]["schema"]["properties"][
            "paragraphs"
        ]["items"]["properties"]["paragraph_id"]["enum"]
        calls.append((request, timeout, ids))
        return FakeHTTPResponse(api_envelope([analyses[paragraph_id] for paragraph_id in ids]))

    monkeypatch.setenv("KIMI_API_KEY", "test-only-secret")
    monkeypatch.setattr(kimi.urllib.request, "urlopen", fake_urlopen)

    assert kimi.main([str(project), "--batch-size", "1"]) == 0

    artifact = json.loads((project / "source-analysis.json").read_text(encoding="utf-8"))
    assert [item["paragraph_id"] for item in artifact["paragraphs"]] == ["L1", "L3"]
    assert artifact["source_sha256"] == kimi._sha256(
        (project / "source.dj").read_text(encoding="utf-8")
    )
    assert artifact["provider"] == "moonshot"
    assert artifact["model"] == "kimi-k3"
    assert artifact["configuration"]["reasoning_effort"] == "high"
    assert artifact["configuration"]["serial"] is True
    assert artifact["configuration"]["request_count"] == 2
    assert len(calls) == 2
    assert [call[2] for call in calls] == [["L1"], ["L3"]]
    for request, timeout, _ids in calls:
        assert request.full_url == "https://api.moonshot.cn/v1/chat/completions"
        assert request.get_header("Authorization") == "Bearer test-only-secret"
        assert timeout == 300.0
    captured = capsys.readouterr()
    assert "test-only-secret" not in captured.out + captured.err


def test_focused_mode_analyzes_only_requested_ids_with_full_blind_context(
    monkeypatch, tmp_path
):
    project = make_project(tmp_path)
    calls = []

    def fake_urlopen(request, timeout):
        payload = json.loads(request.data.decode("utf-8"))
        prompt = json.dumps(payload["messages"], ensure_ascii=False)
        ids = payload["response_format"]["json_schema"]["schema"]["properties"][
            "paragraphs"
        ]["items"]["properties"]["paragraph_id"]["enum"]
        calls.append((ids, prompt))
        return FakeHTTPResponse(
            api_envelope([valid_paragraph("L3", "慈悲需要智慧。")])
        )

    monkeypatch.setenv("KIMI_API_KEY", "focused-secret")
    monkeypatch.setattr(kimi.urllib.request, "urlopen", fake_urlopen)

    assert kimi.main([str(project), "--paragraph-id", "L3"]) == 0

    output = project / "source-analysis-kimi-focused.json"
    artifact = json.loads(output.read_text(encoding="utf-8"))
    assert [item["paragraph_id"] for item in artifact["paragraphs"]] == ["L3"]
    assert calls[0][0] == ["L3"]
    assert "空性不是虚无。" in calls[0][1]
    assert "慈悲需要智慧。" in calls[0][1]
    assert "NEVER-SEND-THIS-TARGET" not in calls[0][1]
    assert not (project / "source-analysis.json").exists()


def test_focused_mode_preserves_source_order_and_rejects_invalid_selection(tmp_path):
    inputs = kimi.load_project(make_project(tmp_path))
    selected = kimi.select_paragraphs(inputs.paragraphs, ["L3", "L1"])
    assert [paragraph.paragraph_id for paragraph in selected] == ["L1", "L3"]

    with pytest.raises(kimi.AnalysisError, match="unique"):
        kimi.select_paragraphs(inputs.paragraphs, ["L1", "L1"])
    with pytest.raises(kimi.AnalysisError, match="not a nonempty source line"):
        kimi.select_paragraphs(inputs.paragraphs, ["L2"])


def test_focused_mode_cannot_replace_canonical_full_analysis(
    monkeypatch, tmp_path, capsys
):
    project = make_project(tmp_path)
    monkeypatch.setenv("KIMI_API_KEY", "focused-secret")
    urlopen = mock.Mock()
    monkeypatch.setattr(kimi.urllib.request, "urlopen", urlopen)

    assert kimi.main(
        [
            str(project),
            "--paragraph-id",
            "L1",
            "--output",
            str(project / "source-analysis.json"),
        ]
    ) == 1
    assert "must not replace canonical" in capsys.readouterr().err
    urlopen.assert_not_called()


def test_failed_batch_is_retried_without_repairing_invalid_output(
    monkeypatch, tmp_path
):
    project = make_project(tmp_path)
    paragraphs = [
        valid_paragraph("L1", "空性不是虚无。"),
        valid_paragraph("L3", "慈悲需要智慧。"),
    ]
    responses = iter(
        [
            FakeHTTPResponse(api_envelope([], content_override="not json")),
            FakeHTTPResponse(api_envelope(paragraphs)),
        ]
    )
    urlopen = mock.Mock(side_effect=lambda request, timeout: next(responses))
    monkeypatch.setenv("KIMI_API_KEY", "retry-secret")
    monkeypatch.setattr(kimi.urllib.request, "urlopen", urlopen)

    assert kimi.main([str(project), "--batch-size", "2", "--retries", "1"]) == 0
    assert urlopen.call_count == 2
    assert (project / "source-analysis.json").is_file()
    assert not (project / ".source-analysis.json.partial").exists()


def test_validated_checkpoint_resumes_without_repeating_completed_batch(
    monkeypatch, tmp_path
):
    project = make_project(tmp_path)
    analyses = {
        "L1": valid_paragraph("L1", "空性不是虚无。"),
        "L3": valid_paragraph("L3", "慈悲需要智慧。"),
    }
    first_calls = []

    def first_urlopen(request, timeout):
        payload = json.loads(request.data.decode("utf-8"))
        paragraph_id = payload["response_format"]["json_schema"]["schema"][
            "properties"
        ]["paragraphs"]["items"]["properties"]["paragraph_id"]["enum"][0]
        first_calls.append(paragraph_id)
        if paragraph_id == "L3":
            raise TimeoutError("simulated interruption")
        return FakeHTTPResponse(api_envelope([analyses[paragraph_id]]))

    monkeypatch.setenv("KIMI_API_KEY", "resume-secret")
    monkeypatch.setattr(kimi.urllib.request, "urlopen", first_urlopen)
    arguments = [str(project), "--batch-size", "1", "--retries", "0"]
    assert kimi.main(arguments) == 1
    assert first_calls == ["L1", "L3"]
    assert (project / ".source-analysis.json.partial").is_file()

    resumed_calls = []

    def resumed_urlopen(request, timeout):
        payload = json.loads(request.data.decode("utf-8"))
        paragraph_id = payload["response_format"]["json_schema"]["schema"][
            "properties"
        ]["paragraphs"]["items"]["properties"]["paragraph_id"]["enum"][0]
        resumed_calls.append(paragraph_id)
        return FakeHTTPResponse(api_envelope([analyses[paragraph_id]]))

    monkeypatch.setattr(kimi.urllib.request, "urlopen", resumed_urlopen)
    assert kimi.main(arguments) == 0
    assert resumed_calls == ["L3"]
    artifact = json.loads((project / "source-analysis.json").read_text("utf-8"))
    assert [item["paragraph_id"] for item in artifact["paragraphs"]] == ["L1", "L3"]
    assert not (project / ".source-analysis.json.partial").exists()


def test_dry_run_builds_blind_requests_without_network_or_output(
    monkeypatch, tmp_path, capsys
):
    project = make_project(tmp_path)
    monkeypatch.setenv("KIMI_API_KEY", "dry-run-secret")
    urlopen = mock.Mock()
    monkeypatch.setattr(kimi.urllib.request, "urlopen", urlopen)

    assert kimi.main([str(project), "--batch-size", "1", "--dry-run"]) == 0

    captured = capsys.readouterr()
    assert "2 serial batches" in captured.out
    assert "credential source: environment variable KIMI_API_KEY" in captured.out
    assert "dry-run-secret" not in captured.out + captured.err
    assert not (project / "source-analysis.json").exists()
    urlopen.assert_not_called()


def test_timeout_or_empty_content_preserves_existing_output(
    monkeypatch, tmp_path, capsys
):
    project = make_project(tmp_path)
    output = project / "source-analysis.json"
    output.write_text('{"old":true}\n', encoding="utf-8")
    monkeypatch.setenv("KIMI_API_KEY", "failure-secret")
    monkeypatch.setattr(
        kimi.urllib.request, "urlopen", mock.Mock(side_effect=TimeoutError("late"))
    )

    assert kimi.main([str(project)]) == 1
    assert output.read_text(encoding="utf-8") == '{"old":true}\n'
    captured = capsys.readouterr()
    assert "failure-secret" not in captured.out + captured.err
    assert "timed out" in captured.err

    monkeypatch.setattr(
        kimi.urllib.request,
        "urlopen",
        lambda request, timeout: FakeHTTPResponse(api_envelope([], content_override="")),
    )
    assert kimi.main([str(project)]) == 1
    assert output.read_text(encoding="utf-8") == '{"old":true}\n'
    captured = capsys.readouterr()
    assert "failure-secret" not in captured.out + captured.err
    assert "no content" in captured.err


def test_schema_or_coverage_failure_preserves_existing_output(
    monkeypatch, tmp_path, capsys
):
    project = make_project(tmp_path)
    output = project / "source-analysis.json"
    output.write_text("old analysis\n", encoding="utf-8")
    monkeypatch.setenv("KIMI_API_KEY", "schema-secret")
    invalid = valid_paragraph("L1", "空性不是虚无。")
    invalid.pop("must_not_invent")
    monkeypatch.setattr(
        kimi.urllib.request,
        "urlopen",
        lambda request, timeout: FakeHTTPResponse(api_envelope([invalid])),
    )

    assert kimi.main([str(project)]) == 1

    assert output.read_text(encoding="utf-8") == "old analysis\n"
    captured = capsys.readouterr()
    assert "schema-secret" not in captured.out + captured.err
    assert "missing" in captured.err


def test_explicit_participant_must_be_verbatim_source_evidence(tmp_path):
    project = make_project(tmp_path)
    inputs = kimi.load_project(project)
    schema = kimi.load_analysis_schema()
    analysis = valid_paragraph("L1", "空性不是虚无。")
    analysis["predicates"][0]["participants"] = [
        {
            "role": "agent",
            "participant": "人们",
            "evidence": "空性",
            "evidence_status": "explicit",
            "notes": "错误地虚构了原文没有的人们。",
        }
    ]

    with pytest.raises(kimi.AnalysisError, match="participant"):
        kimi.validate_batch_content(
            json.dumps({"paragraphs": [analysis]}, ensure_ascii=False),
            [inputs.paragraphs[0]],
            schema,
            inputs.source,
        )


def test_null_participant_may_be_contextual_inference_but_never_explicit(tmp_path):
    inputs = kimi.load_project(make_project(tmp_path))
    schema = kimi.load_analysis_schema()
    analysis = valid_paragraph("L1", "空性不是虚无。")
    role = {
        "role": "agent",
        "participant": None,
        "evidence": "空性",
        "evidence_status": "contextual_inference",
        "notes": "上下文只能支持存在该角色，不能定名。",
    }
    analysis["predicates"][0]["participants"] = [role]
    assert kimi.validate_batch_content(
        json.dumps({"paragraphs": [analysis]}, ensure_ascii=False),
        [inputs.paragraphs[0]],
        schema,
        inputs.source,
    ) == [analysis]

    role["evidence_status"] = "explicit"
    with pytest.raises(kimi.AnalysisError, match="null participant explicit"):
        kimi.validate_batch_content(
            json.dumps({"paragraphs": [analysis]}, ensure_ascii=False),
            [inputs.paragraphs[0]],
            schema,
            inputs.source,
        )


def test_explicit_participant_must_appear_in_current_paragraph_and_own_evidence(
    tmp_path
):
    inputs = kimi.load_project(make_project(tmp_path))
    schema = kimi.load_analysis_schema()
    analysis = valid_paragraph("L1", "空性不是虚无。")
    analysis["predicates"][0]["participants"] = [
        {
            "role": "agent",
            "participant": "我们",  # occurs elsewhere in the complete source only
            "evidence": "空性",
            "evidence_status": "explicit",
            "notes": "错把其他段落的词当成当前段落证据。",
        }
    ]
    # Add the canary only to the complete source, not the current paragraph.
    with pytest.raises(kimi.AnalysisError, match="participant"):
        kimi.validate_batch_content(
            json.dumps({"paragraphs": [analysis]}, ensure_ascii=False),
            [inputs.paragraphs[0]],
            schema,
            inputs.source + "\n我们",
        )


def test_tier1_rate_limiter_waits_for_tpm_window():
    now = [0.0]
    sleeps = []

    def sleeper(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    limiter = kimi.Tier1RateLimiter(clock=lambda: now[0], sleeper=sleeper)
    limiter.acquire(1_500_000)
    limiter.acquire(600_000)

    assert sum(sleeps) >= 60.0


def test_tier1_rate_limiter_rejects_single_oversized_request():
    limiter = kimi.Tier1RateLimiter(clock=lambda: 0.0, sleeper=lambda _seconds: None)
    with pytest.raises(kimi.AnalysisError, match="Tier 1 TPM"):
        limiter.acquire(kimi.TIER1_TPM + 1)


def test_http_429_uses_bounded_retry_after_without_echoing_body(
    monkeypatch, tmp_path
):
    inputs = kimi.load_project(make_project(tmp_path))
    error = urllib.error.HTTPError(
        kimi.API_URL,
        429,
        "secret response body",
        {"Retry-After": "7"},
        mock.Mock(read=lambda: b"must-not-read"),
    )
    monkeypatch.setattr(kimi.urllib.request, "urlopen", mock.Mock(side_effect=error))
    with pytest.raises(kimi.RateLimitError) as caught:
        kimi.request_batch(
            inputs=inputs,
            batch=inputs.paragraphs[:1],
            schema_document=kimi.load_analysis_schema(),
            credential=kimi.Credential("secret", "test"),
            model="kimi-k3",
            reasoning_effort="high",
            timeout=1,
            max_tokens=100,
        )
    assert caught.value.retry_after == 7


@pytest.mark.parametrize("section", ["relation", "operator", "reference"])
def test_explicit_semantic_items_require_source_evidence(tmp_path, section):
    inputs = kimi.load_project(make_project(tmp_path))
    schema = kimi.load_analysis_schema()
    analysis = valid_paragraph("L1", "空性不是虚无。")
    if section == "relation":
        analysis["relations"] = [{
            "type": "contrast",
            "source_clause": "空性",
            "target_clause": "虚无",
            "evidence": None,
            "evidence_status": "explicit",
            "notes": "错误地缺少明示关系证据。",
        }]
    elif section == "operator":
        analysis["operators"] = [{
            "kind": "negation",
            "marker": None,
            "scope": "虚无",
            "interpretation": "否定空性等同于虚无",
            "evidence_status": "explicit",
            "notes": "错误地缺少明示算子标记。",
        }]
    else:
        analysis["references_and_ellipsis"] = [{
            "kind": "coreference",
            "expression": "空性",
            "predicate": "空性不是虚无",
            "role": "theme",
            "referent": "空性",
            "candidate_referents": ["空性"],
            "evidence": None,
            "evidence_status": "explicit",
            "notes": "错误地缺少明示指代证据。",
        }]
    with pytest.raises(kimi.AnalysisError, match="explicit"):
        kimi.validate_batch_content(
            json.dumps({"paragraphs": [analysis]}, ensure_ascii=False),
            [inputs.paragraphs[0]],
            schema,
            inputs.source,
        )


def test_analytical_fields_cannot_contain_an_english_draft(tmp_path):
    inputs = kimi.load_project(make_project(tmp_path))
    schema = kimi.load_analysis_schema()
    analysis = valid_paragraph("L1", "空性不是虚无。")
    analysis["predicates"][0]["canonical_meaning"] = (
        "Emptiness is not nothingness and should never be understood as nihilism."
    )

    with pytest.raises(kimi.AnalysisError, match="English draft"):
        kimi.validate_batch_content(
            json.dumps({"paragraphs": [analysis]}, ensure_ascii=False),
            [inputs.paragraphs[0]],
            schema,
            inputs.source,
        )


def test_atomic_replace_failure_preserves_old_output(monkeypatch, tmp_path, capsys):
    project = make_project(tmp_path)
    output = project / "source-analysis.json"
    output.write_text("old analysis\n", encoding="utf-8")
    analyses = [
        valid_paragraph("L1", "空性不是虚无。"),
        valid_paragraph("L3", "慈悲需要智慧。"),
    ]
    monkeypatch.setenv("KIMI_API_KEY", "atomic-secret")
    monkeypatch.setattr(
        kimi.urllib.request,
        "urlopen",
        lambda request, timeout: FakeHTTPResponse(api_envelope(analyses)),
    )
    monkeypatch.setattr(
        kimi.os, "replace", mock.Mock(side_effect=OSError("simulated failure"))
    )

    assert kimi.main([str(project)]) == 1

    assert output.read_text(encoding="utf-8") == "old analysis\n"
    captured = capsys.readouterr()
    assert "atomic-secret" not in captured.out + captured.err
    assert not list(project.glob(".source-analysis.json.*.tmp"))


def test_input_change_during_analysis_prevents_certificate_write(
    monkeypatch, tmp_path
):
    project = make_project(tmp_path)
    analyses = [
        valid_paragraph("L1", "空性不是虚无。"),
        valid_paragraph("L3", "慈悲需要智慧。"),
    ]
    monkeypatch.setenv("KIMI_API_KEY", "change-secret")

    def fake_urlopen(request, timeout):
        (project / "term-map.yaml").write_text('{"version":1,"terms":[]}\n', "utf-8")
        return FakeHTTPResponse(api_envelope(analyses))

    monkeypatch.setattr(kimi.urllib.request, "urlopen", fake_urlopen)
    assert kimi.main([str(project)]) == 1
    assert not (project / "source-analysis.json").exists()


@pytest.mark.parametrize(
    "name",
    [
        "source.dj", "target.dj", "term-map.yaml", "translation-project.yaml",
        "bilingual.dj", "review-findings.jsonl", "semantic-review.json",
    ],
)
def test_output_cannot_overwrite_protected_project_files(
    monkeypatch, tmp_path, name
):
    project = make_project(tmp_path)
    protected = project / name
    before = protected.read_bytes() if protected.exists() else None
    monkeypatch.setenv("KIMI_API_KEY", "output-secret")

    assert kimi.main([str(project), "--output", str(protected), "--dry-run"]) == 1
    assert protected.read_bytes() == before if before is not None else not protected.exists()


def test_external_review_policy_blocks_before_credential(monkeypatch, tmp_path):
    denied = make_project(tmp_path, policy="deny")
    credential = mock.Mock()
    monkeypatch.setattr(kimi, "load_credential", credential)

    assert kimi.main([str(denied), "--dry-run"]) == 1
    credential.assert_not_called()


def test_sensitive_release_blocks_before_credential(monkeypatch, tmp_path):
    sensitive = make_project(tmp_path, release_level="sensitive")
    credential = mock.Mock()
    monkeypatch.setattr(kimi, "load_credential", credential)

    assert kimi.main([str(sensitive), "--dry-run"]) == 1
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
    monkeypatch.setattr(kimi, "load_credential", credential)

    assert kimi.main([str(project), "--dry-run"]) == 1
    credential.assert_not_called()


def test_http_error_body_and_request_content_are_not_echoed(
    monkeypatch, tmp_path, capsys
):
    project = make_project(tmp_path)
    monkeypatch.setenv("KIMI_API_KEY", "http-secret")
    body = b"http-secret NEVER-SEND-THIS-TARGET private source echo"
    error = urllib.error.HTTPError(
        kimi.API_URL, 429, "provider echoed private data", {}, mock.Mock(read=lambda: body)
    )
    monkeypatch.setattr(kimi.urllib.request, "urlopen", mock.Mock(side_effect=error))

    assert kimi.main([str(project)]) == 1

    captured = capsys.readouterr()
    assert "rate limit reached" in captured.err
    assert "http-secret" not in captured.out + captured.err
    assert "NEVER-SEND-THIS-TARGET" not in captured.out + captured.err
    assert "private source echo" not in captured.out + captured.err


def test_livelihood_food_gold_preserves_ambiguity_and_roles():
    fixture_path = (
        ROOT
        / "tests"
        / "fixtures"
        / "kimi-source-analysis"
        / "food-for-livelihood.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    source = fixture["source"]
    analysis = fixture["analysis"]
    schema = kimi.load_analysis_schema()
    batch = [kimi.SourceParagraph("L1", source)]

    validated = kimi.validate_batch_content(
        json.dumps({"paragraphs": [analysis]}, ensure_ascii=False),
        batch,
        schema,
        source,
    )

    assert validated == [analysis]
    get_predicate = next(item for item in analysis["predicates"] if item["predicate"] == "得到")
    agent = next(item for item in get_predicate["participants"] if item["role"] == "agent")
    theme = next(item for item in get_predicate["participants"] if item["role"] == "theme")
    assert agent["participant"] is None
    assert agent["evidence_status"] == "ambiguous"
    assert theme["participant"] == "谋生的食粮"
    suffering = next(item for item in analysis["predicates"] if item["predicate"] == "忍受")
    assert any(
        role["participant"] == "多少生命" and role["role"] == "experiencer"
        for role in suffering["participants"]
    )
    inherited = next(
        item
        for item in analysis["references_and_ellipsis"]
        if item["kind"] == "inherited_subject" and item["predicate"] == "丧生"
    )
    assert inherited["referent"] == "多少生命"
    assert {relation["type"] for relation in analysis["relations"]} >= {
        "purpose",
        "cost",
        "progression",
    }
    assert analysis["status"] == "needs_human"
    assert "不得把得到改成生产" in analysis["must_not_invent"]
    assert "不得擅增义务情态" in analysis["must_not_invent"]
    assert "不得擅增可能情态" in analysis["must_not_invent"]
    assert "不得擅自限定为过去时" in analysis["must_not_invent"]


def test_public_internal_source_analysis_fixture_matches_full_schema():
    artifact = json.loads(
        (ROOT / "examples" / "minimal-article" / "source-analysis.json").read_text(
            encoding="utf-8"
        )
    )
    schema = kimi.load_analysis_schema()

    kimi._validate_instance(artifact, schema)
    assert artifact["provider"] == "internal"
