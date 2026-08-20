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
    assert config["analysis_components"] == list(MODULE.COMPONENT_FIELDS)
    assert config["component_context_windows"] == MODULE.COMPONENT_CONTEXT_WINDOWS


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
        json.dumps(document, ensure_ascii=False), batch, schema, "temporal"
    )

    assert [item["paragraph_id"] for item in validated] == [
        paragraph.paragraph_id for paragraph in batch
    ]
    document["paragraphs"][0]["unexpected"] = True
    try:
        MODULE.validate_component_content(
            json.dumps(document, ensure_ascii=False), batch, schema, "temporal"
        )
    except MODULE.AnalysisError:
        pass
    else:
        raise AssertionError("unknown component fields must be rejected")


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

    def fake_request(_inputs, _batch, _schema, component, _credential, _timeout):
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

    def fake_request(_inputs, batch, _schema, component, _credential, _timeout):
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
