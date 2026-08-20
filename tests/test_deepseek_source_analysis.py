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
    payload = MODULE.build_request_payload(inputs, batch, schema)
    serialized = json.dumps(payload, ensure_ascii=False)
    schema_message = payload["messages"][2]["content"]

    assert payload["response_format"] == {"type": "json_object"}
    assert "<required-json-schema>" in schema_message
    assert '"additionalProperties":false' in schema_message
    assert '"paragraphs"' in schema_message
    assert batch[0].paragraph_id in schema_message
    assert "顶层只能有 paragraphs" in schema_message
    assert "LEAKED_ENGLISH_CANARY" not in serialized


def test_long_document_prompt_uses_complete_outline_local_window_and_relevant_terms(tmp_path):
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
    batch = (inputs.paragraphs[3],)
    payload = MODULE.build_request_payload(inputs, batch, schema)
    serialized = json.dumps(payload, ensure_ascii=False)
    context = payload["messages"][1]["content"]
    schema_message = payload["messages"][2]["content"]

    assert "<complete-chinese-structure-index>" in context
    assert "<exact-local-chinese-window>" in context
    assert "[L4] 第三段是当前请求。" in context
    assert "[L8] 遥远段落的开头" in context
    assert distant_tail not in serialized
    assert '"source": "正念"' in context
    assert "SHOULD_NOT_APPEAR" not in serialized
    assert '"description"' not in schema_message
    assert payload["messages"][3]["content"].count("L4") == 1


def test_deepseek_checkpoint_configuration_binds_window_strategy():
    config = MODULE.configuration(2, 120.0)

    assert config["context_mode"] == MODULE.CONTEXT_MODE
    assert config["context_window_paragraphs"] == MODULE.CONTEXT_WINDOW_PARAGRAPHS
    assert config["outline_prefix_characters"] == MODULE.OUTLINE_PREFIX_CHARACTERS
