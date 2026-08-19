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
