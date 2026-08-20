import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "deepseek-source-analysis.py"
SPEC = importlib.util.spec_from_file_location("deepseek_source_analysis", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_json_mode_prompt_contains_exact_batch_schema_and_remains_blind(tmp_path):
    project = tmp_path / "deepseek-blind-test"
    project.mkdir()
    example = ROOT / "examples" / "minimal-article"
    for name in ("source.dj", "translation-project.yaml", "term-map.yaml"):
        (project / name).write_bytes((example / name).read_bytes())
    (project / "target.dj").write_text("LEAKED_ENGLISH_CANARY\n", encoding="utf-8")

    inputs = MODULE.shared.load_project(project)
    schema = MODULE.shared.load_analysis_schema()
    batch = inputs.paragraphs[:1]
    payload = MODULE.build_request_payload(inputs, batch, schema, "temporal")
    serialized = json.dumps(payload, ensure_ascii=False)
    schema_message = payload["messages"][2]["content"]

    assert payload["response_format"] == {"type": "json_object"}
    assert payload["max_tokens"] == MODULE.MAX_COMPLETION_TOKENS == 8192
    assert "<required-json-schema>" in schema_message
    assert '"additionalProperties":false' in schema_message
    assert '"paragraphs"' in schema_message
    assert batch[0].paragraph_id in schema_message
    assert "顶层只能有 paragraphs" in schema_message
    assert '"temporal_relations"' in schema_message
    assert '"predicates"' not in schema_message
    assert "LEAKED_ENGLISH_CANARY" not in serialized


def test_long_document_prompt_uses_local_window_and_relevant_terms(tmp_path):
    project = tmp_path / "deepseek-window-test"
    project.mkdir()
    example = ROOT / "examples" / "minimal-article"
    (project / "translation-project.yaml").write_bytes(
        (example / "translation-project.yaml").read_bytes()
    )
    distant_tail = "DISTANT_FULL_TEXT_MUST_NOT_REPEAT"
    lines = [
        "# 标题",
        "第一段包含正念并说明背景。",
        "第二段承接前文。",
        "第三段是当前请求。",
        "第四段提供后文。",
        "第五段仍在邻近窗口。",
        "第六段也在邻近窗口。",
        "遥远段落的开头用于索引，但其很长的后半部分" + distant_tail,
    ]
    (project / "source.dj").write_text("\n".join(lines) + "\n", encoding="utf-8")
    term_map = {
        "version": 1,
        "terms": [
            {
                "source": "正念",
                "sense": "当下觉知",
                "preferred": "mindfulness",
                "allowed": ["mindfulness"],
                "forbidden": [],
                "sources": ["test"],
                "rationale": "test",
                "status": "selected",
            },
            {
                "source": "遥远术语",
                "sense": "不相关",
                "preferred": "distant term",
                "allowed": ["distant term"],
                "forbidden": [],
                "sources": ["test"],
                "rationale": "SHOULD_NOT_APPEAR",
                "status": "selected",
            },
        ],
    }
    (project / "term-map.yaml").write_text(
        json.dumps(term_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    inputs = MODULE.shared.load_project(project)
    schema = MODULE.shared.load_analysis_schema()
    batch = (inputs.paragraphs[2],)
    payload = MODULE.build_request_payload(inputs, batch, schema, "core")
    serialized = json.dumps(payload, ensure_ascii=False)
    context = payload["messages"][1]["content"]
    schema_message = payload["messages"][2]["content"]

    assert "<complete-indexed-chinese-source>" in context
    assert "[L3] 第二段承接前文。" in context
    assert "遥远段落的开头" not in context
    assert distant_tail not in serialized
    assert '"source": "正念"' in context
    assert "SHOULD_NOT_APPEAR" not in serialized
    assert '"description"' in schema_message
    assert payload["messages"][3]["content"].count("L3") == 1


def test_deepseek_checkpoint_configuration_binds_window_strategy():
    config = MODULE.configuration(2, 120.0, 5)

    assert config["context_mode"] == MODULE.CONTEXT_MODE
    assert config["context_window_paragraphs"] == MODULE.CONTEXT_WINDOW_PARAGRAPHS
    assert config["max_completion_tokens"] == MODULE.MAX_COMPLETION_TOKENS
    assert config["retry_limit"] == 5
    assert config["component_mode"] == MODULE.COMPONENT_MODE
    assert config["component_fallback_mode"] == MODULE.COMPONENT_FALLBACK_MODE
    assert config["completion_recovery_mode"] == MODULE.COMPLETION_RECOVERY_MODE
    assert "transient_batch_recovery_mode" not in config
    assert "transient_batch_retry_limit" not in config
    assert "cross_component_reconciliation_mode" not in config
    assert "component_evidence_prevalidation_mode" not in config
    assert config["analysis_components"] == list(MODULE.COMPONENT_FIELDS)
    assert config["component_context_windows"] == MODULE.COMPONENT_CONTEXT_WINDOWS


def test_final_artifact_records_transient_batch_recovery(tmp_path):
    project = tmp_path / "deepseek-artifact-recovery"
    project.mkdir()
    example = ROOT / "examples" / "minimal-article"
    for name in ("source.dj", "translation-project.yaml", "term-map.yaml"):
        (project / name).write_bytes((example / name).read_bytes())
    inputs = MODULE.shared.load_project(project)
    analyses = json.loads(
        (example / "source-analysis.json").read_text(encoding="utf-8")
    )["paragraphs"]

    artifact = MODULE.build_artifact(inputs, analyses, 2, 300.0, 5)
    config = artifact["configuration"]

    assert config["transient_batch_recovery_mode"] == (
        MODULE.TRANSIENT_BATCH_RECOVERY_MODE
    )
    assert config["transient_batch_retry_limit"] == (
        MODULE.TRANSIENT_BATCH_RETRY_LIMIT
    )
    assert config["cross_component_reconciliation_mode"] == (
        MODULE.CROSS_COMPONENT_RECONCILIATION_MODE
    )
    assert config["component_evidence_prevalidation_mode"] == (
        MODULE.COMPONENT_EVIDENCE_PREVALIDATION_MODE
    )
    MODULE.shared._validate_instance(
        artifact, MODULE.shared.load_analysis_schema()
    )


def test_reconcile_temporal_markers_is_deterministic_and_idempotent():
    analyses = [
        {
            "paragraph_id": "L1",
            "temporal_relations": [
                {"marker": "先"},
                {"marker": "才"},
                {"marker": "后"},
            ],
            "must_preserve": ["先说明条件", "保留原有约束"],
        }
    ]

    assert MODULE.reconcile_temporal_markers(analyses) == 2
    assert analyses[0]["must_preserve"] == [
        "先说明条件",
        "保留原有约束",
        "才",
        "后",
    ]
    assert MODULE.reconcile_temporal_markers(analyses) == 0


def test_reconciled_temporal_marker_passes_strong_batch_validation():
    source = "条件具足，才会结果。"
    paragraph = MODULE.shared.SourceParagraph("L1", source)
    analysis = {
        "paragraph_id": "L1",
        "predicates": [
            {
                "predicate": "结果",
                "canonical_meaning": "条件具足后出现结果",
                "evidence": "结果",
                "participants": [],
            }
        ],
        "relations": [],
        "temporal_relations": [
            {
                "marker": "才",
                "relation": "after",
                "event_or_scope": "条件具足之后出现结果",
                "linked_event": "条件具足",
                "evidence_status": "explicit",
                "notes": "才表示结果以条件具足为前提。",
            }
        ],
        "operators": [],
        "references_and_ellipsis": [],
        "elliptical_subject": [],
        "cultural_allusions": [],
        "competing_interpretations": [],
        "must_preserve": ["保留条件与结果的关系"],
        "must_not_invent": ["不得增加原文没有的条件"],
        "status": "clear",
    }

    assert MODULE.reconcile_temporal_markers([analysis]) == 1
    validated = MODULE.shared.validate_batch_content(
        json.dumps({"paragraphs": [analysis]}, ensure_ascii=False),
        [paragraph],
        MODULE.shared.load_analysis_schema(),
        source,
    )

    assert validated[0]["must_preserve"][-1] == "才"


def test_deterministic_validation_diagnostic_exposes_only_structure():
    original = MODULE.AnalysisError(
        "source analysis field $.paragraphs[L45].predicates[2].participants[0].participant "
        "is not supported by its own evidence"
    )
    metadata = MODULE.deterministic_validation_metadata(original)
    wrapped = MODULE.DeepSeekDeterministicValidationError(**metadata)
    wrapped.__cause__ = original

    assert MODULE.safe_diagnostic(wrapped) == {
        "schema_version": 1,
        "code": "deepseek_source_analysis_validation",
        "retryable": False,
        "paragraph_id": "L45",
        "field": "predicates[2].participants[0].participant",
        "category": "participant_evidence_support",
    }
    assert "evidence" not in str(wrapped)
    assert "participant" not in str(wrapped)


def test_deterministic_validation_is_never_retried(tmp_path, monkeypatch):
    project = tmp_path / "deepseek-deterministic-validation"
    project.mkdir()
    example = ROOT / "examples" / "minimal-article"
    for name in ("source.dj", "translation-project.yaml", "term-map.yaml"):
        (project / name).write_bytes((example / name).read_bytes())
    inputs = MODULE.shared.load_project(project)
    schema = MODULE.shared.load_analysis_schema()
    batch = inputs.paragraphs[:1]
    calls = []

    def fake_analyze(*args):
        calls.append(args[1])
        raise MODULE.DeepSeekDeterministicValidationError(
            paragraph_id=batch[0].paragraph_id,
            field="must_preserve",
            category="temporal_preservation_coverage",
        )

    monkeypatch.setattr(MODULE, "analyze_batch", fake_analyze)
    monkeypatch.setattr(
        MODULE.time,
        "sleep",
        lambda _seconds: (_ for _ in ()).throw(AssertionError("must not retry")),
    )

    try:
        MODULE.analyze_batch_with_transient_recovery(
            inputs,
            batch,
            schema,
            MODULE.Credential("not-used", "test"),
            30.0,
            1,
        )
    except MODULE.DeepSeekDeterministicValidationError:
        pass
    else:
        raise AssertionError("deterministic validation error must propagate")

    assert calls == [batch]


def test_component_validator_orders_coverage_and_rejects_unknown_fields(tmp_path):
    project = tmp_path / "deepseek-component-test"
    project.mkdir()
    example = ROOT / "examples" / "minimal-article"
    for name in ("source.dj", "translation-project.yaml", "term-map.yaml"):
        (project / name).write_bytes((example / name).read_bytes())
    inputs = MODULE.shared.load_project(project)
    schema = MODULE.shared.load_analysis_schema()
    batch = inputs.paragraphs
    document = {
        "paragraphs": [
            {"paragraph_id": paragraph.paragraph_id, "temporal_relations": []}
            for paragraph in reversed(batch)
        ]
    }

    validated = MODULE.validate_component_content(
        json.dumps(document, ensure_ascii=False),
        batch,
        schema,
        "temporal",
        inputs.source,
    )

    assert [item["paragraph_id"] for item in validated] == [
        paragraph.paragraph_id for paragraph in batch
    ]
    document["paragraphs"][0]["unexpected"] = True
    try:
        MODULE.validate_component_content(
            json.dumps(document, ensure_ascii=False),
            batch,
            schema,
            "temporal",
            inputs.source,
        )
    except MODULE.AnalysisError:
        pass
    else:
        raise AssertionError("unknown component fields must be rejected")


def test_nonverbatim_constraints_evidence_retries_same_component(
    tmp_path, monkeypatch
):
    project = tmp_path / "deepseek-constraints-evidence-retry"
    project.mkdir()
    example = ROOT / "examples" / "minimal-article"
    for name in ("translation-project.yaml", "term-map.yaml"):
        (project / name).write_bytes((example / name).read_bytes())
    (project / "source.dj").write_text(
        "条件具足，才会结果。\n", encoding="utf-8"
    )
    inputs = MODULE.shared.load_project(project)
    schema = MODULE.shared.load_analysis_schema()
    batch = inputs.paragraphs
    attempts = []

    def fake_request(*args):
        attempts.append(args[-1])
        evidence = "概括条件" if len(attempts) == 1 else "条件具足"
        return json.dumps(
            {
                "paragraphs": [
                    {
                        "paragraph_id": batch[0].paragraph_id,
                        "cultural_allusions": [],
                        "competing_interpretations": [
                            {
                                "interpretation": "条件是结果出现的前提",
                                "supporting_evidence": [evidence],
                                "counterevidence": [],
                                "evidence_status": "explicit",
                            }
                        ],
                        "must_preserve": ["保留条件关系"],
                        "must_not_invent": ["不得增加新条件"],
                        "status": "clear",
                    }
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(MODULE, "request_component", fake_request)
    monkeypatch.setattr(MODULE.time, "sleep", lambda _seconds: None)
    partials = MODULE.request_validated_component(
        inputs,
        batch,
        schema,
        "constraints",
        MODULE.Credential("not-used", "test"),
        30.0,
        1,
    )

    assert len(attempts) == 2
    assert partials[0]["competing_interpretations"][0]["supporting_evidence"] == [
        "条件具足"
    ]


def test_component_retry_keeps_successful_components(monkeypatch, tmp_path):
    project = tmp_path / "deepseek-component-retry"
    project.mkdir()
    example = ROOT / "examples" / "minimal-article"
    for name in ("source.dj", "translation-project.yaml", "term-map.yaml"):
        (project / name).write_bytes((example / name).read_bytes())
    inputs = MODULE.shared.load_project(project)
    schema = MODULE.shared.load_analysis_schema()
    canonical = json.loads((example / "source-analysis.json").read_text(encoding="utf-8"))[
        "paragraphs"
    ]
    calls = {component: 0 for component in MODULE.COMPONENT_FIELDS}

    def fake_request(
        _inputs,
        _batch,
        _schema,
        component,
        _credential,
        _timeout,
        _max_completion_tokens,
    ):
        calls[component] += 1
        if component == "temporal" and calls[component] == 1:
            raise MODULE.AnalysisError("synthetic empty response")
        fields = MODULE.COMPONENT_FIELDS[component]
        paragraphs = []
        allowed = MODULE.OPERATOR_COMPONENT_RULES.get(component, ((), 0))[0]
        for source in canonical:
            item = {"paragraph_id": source["paragraph_id"]}
            for field in fields:
                value = source[field]
                if field == "operators":
                    value = [entry for entry in value if entry["kind"] in allowed]
                item[field] = value
            paragraphs.append(item)
        return json.dumps({"paragraphs": paragraphs}, ensure_ascii=False)

    monkeypatch.setattr(MODULE, "request_component", fake_request)
    monkeypatch.setattr(MODULE.time, "sleep", lambda _seconds: None)
    analyses = MODULE.analyze_batch(
        inputs,
        inputs.paragraphs,
        schema,
        MODULE.Credential("not-used", "test"),
        30.0,
        1,
    )

    assert len(analyses) == len(inputs.paragraphs)
    assert calls["temporal"] == 2
    assert all(
        count == 1 for component, count in calls.items() if component != "temporal"
    )


def test_component_exhaustion_falls_back_to_single_paragraph_requests(
    monkeypatch, tmp_path
):
    project = tmp_path / "deepseek-component-single-fallback"
    project.mkdir()
    example = ROOT / "examples" / "minimal-article"
    for name in ("source.dj", "translation-project.yaml", "term-map.yaml"):
        (project / name).write_bytes((example / name).read_bytes())
    inputs = MODULE.shared.load_project(project)
    schema = MODULE.shared.load_analysis_schema()
    canonical = json.loads((example / "source-analysis.json").read_text(encoding="utf-8"))[
        "paragraphs"
    ]
    calls = []

    def fake_request(
        _inputs,
        batch,
        _schema,
        component,
        _credential,
        _timeout,
        _max_completion_tokens,
    ):
        calls.append((component, tuple(item.paragraph_id for item in batch)))
        if component == "core" and len(batch) > 1:
            raise MODULE.AnalysisError("synthetic batch-only empty response")
        fields = MODULE.COMPONENT_FIELDS[component]
        allowed = MODULE.OPERATOR_COMPONENT_RULES.get(component, ((), 0))[0]
        paragraphs = []
        canonical_by_id = {item["paragraph_id"]: item for item in canonical}
        for paragraph in batch:
            source = canonical_by_id[paragraph.paragraph_id]
            item = {"paragraph_id": source["paragraph_id"]}
            for field in fields:
                value = source[field]
                if field == "operators":
                    value = [entry for entry in value if entry["kind"] in allowed]
                item[field] = value
            paragraphs.append(item)
        return json.dumps({"paragraphs": paragraphs}, ensure_ascii=False)

    monkeypatch.setattr(MODULE, "request_component", fake_request)
    monkeypatch.setattr(MODULE.time, "sleep", lambda _seconds: None)
    analyses = MODULE.analyze_batch(
        inputs,
        inputs.paragraphs,
        schema,
        MODULE.Credential("not-used", "test"),
        30.0,
        1,
    )

    full_ids = tuple(item.paragraph_id for item in inputs.paragraphs)
    assert len(analyses) == len(inputs.paragraphs)
    assert calls.count(("core", full_ids)) == 2
    assert [(component, ids) for component, ids in calls if component == "core"][2:] == [
        ("core", (paragraph.paragraph_id,)) for paragraph in inputs.paragraphs
    ]
    assert all(
        calls.count((component, full_ids)) == 1
        for component in MODULE.COMPONENT_FIELDS
        if component != "core"
    )


def test_empty_completion_retries_without_explicit_completion_cap(
    monkeypatch, tmp_path
):
    project = tmp_path / "deepseek-completion-recovery"
    project.mkdir()
    example = ROOT / "examples" / "minimal-article"
    for name in ("source.dj", "translation-project.yaml", "term-map.yaml"):
        (project / name).write_bytes((example / name).read_bytes())
    inputs = MODULE.shared.load_project(project)
    schema = MODULE.shared.load_analysis_schema()
    batch = inputs.paragraphs[:1]
    canonical = json.loads((example / "source-analysis.json").read_text(encoding="utf-8"))[
        "paragraphs"
    ][0]
    completion_caps = []

    def fake_request(
        _inputs,
        _batch,
        _schema,
        component,
        _credential,
        _timeout,
        max_completion_tokens,
    ):
        completion_caps.append(max_completion_tokens)
        if len(completion_caps) == 1:
            raise MODULE.DeepSeekCompletionRecoveryError(
                "synthetic empty structured content"
            )
        item = {"paragraph_id": canonical["paragraph_id"]}
        for field in MODULE.COMPONENT_FIELDS[component]:
            item[field] = canonical[field]
        return json.dumps({"paragraphs": [item]}, ensure_ascii=False)

    monkeypatch.setattr(MODULE, "request_component", fake_request)
    monkeypatch.setattr(MODULE.time, "sleep", lambda _seconds: None)
    partials = MODULE.request_validated_component(
        inputs,
        batch,
        schema,
        "core",
        MODULE.Credential("not-used", "test"),
        30.0,
        1,
    )

    assert partials[0]["paragraph_id"] == canonical["paragraph_id"]
    assert completion_caps == [MODULE.MAX_COMPLETION_TOKENS, None]


def test_payload_omits_max_tokens_only_for_completion_recovery(tmp_path):
    project = tmp_path / "deepseek-recovery-payload"
    project.mkdir()
    example = ROOT / "examples" / "minimal-article"
    for name in ("source.dj", "translation-project.yaml", "term-map.yaml"):
        (project / name).write_bytes((example / name).read_bytes())
    inputs = MODULE.shared.load_project(project)
    schema = MODULE.shared.load_analysis_schema()
    batch = inputs.paragraphs[:1]

    primary = MODULE.build_request_payload(inputs, batch, schema, "core")
    recovery = MODULE.build_request_payload(
        inputs, batch, schema, "core", max_completion_tokens=None
    )

    assert primary["max_tokens"] == MODULE.MAX_COMPLETION_TOKENS
    assert "max_tokens" not in recovery


def test_transient_batch_recovery_retries_unchanged_batch(tmp_path, monkeypatch):
    project = tmp_path / "deepseek-transient-batch-recovery"
    project.mkdir()
    example = ROOT / "examples" / "minimal-article"
    for name in ("source.dj", "translation-project.yaml", "term-map.yaml"):
        (project / name).write_bytes((example / name).read_bytes())
    inputs = MODULE.shared.load_project(project)
    schema = MODULE.shared.load_analysis_schema()
    batch = inputs.paragraphs[:1]
    calls = []
    sleeps = []
    errors = []

    def fake_analyze(*args):
        calls.append(args[1])
        if len(calls) == 1:
            transport = MODULE.DeepSeekTransportError(
                "DeepSeek API request failed", transport_kind="timeout"
            )
            wrapped = MODULE.ComponentAnalysisError(
                "safe wrapper",
                component="reference",
                paragraph_id=batch[0].paragraph_id,
                fallback="single-paragraph",
            )
            wrapped.__cause__ = transport
            errors.append(wrapped)
            raise wrapped
        return [{"paragraph_id": batch[0].paragraph_id}]

    monkeypatch.setattr(MODULE, "analyze_batch", fake_analyze)
    monkeypatch.setattr(MODULE.time, "sleep", sleeps.append)
    result = MODULE.analyze_batch_with_transient_recovery(
        inputs,
        batch,
        schema,
        MODULE.Credential("not-used", "test"),
        30.0,
        1,
        transient_batch_retry_limit=2,
    )

    assert result == [{"paragraph_id": batch[0].paragraph_id}]
    assert calls == [batch, batch]
    assert sleeps == [10.0]
    diagnostic = MODULE.safe_diagnostic(errors[0])
    assert diagnostic == {
        "schema_version": 1,
        "code": "deepseek_transport_failure",
        "retryable": True,
        "component": "reference",
        "paragraph_id": batch[0].paragraph_id,
        "fallback": "single-paragraph",
        "transport_kind": "timeout",
    }
