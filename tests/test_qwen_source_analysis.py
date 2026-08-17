import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "qwen-source-analysis.py"
SPEC = importlib.util.spec_from_file_location("qwen_source_analysis", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def make_project(tmp_path: Path, project_id: str = "qwen-test") -> Path:
    project = tmp_path / project_id
    project.mkdir()
    (project / "source.dj").write_text(
        "仅仅为了得到谋生的食粮。\n", encoding="utf-8"
    )
    metadata = json.loads(
        (ROOT / "examples/minimal-article/translation-project.yaml").read_text()
    )
    metadata["project_id"] = project_id
    metadata["release"]["level"] = "draft"
    (project / "translation-project.yaml").write_text(
        json.dumps(metadata, ensure_ascii=False), encoding="utf-8"
    )
    (project / "term-map.yaml").write_text(
        json.dumps({"version": 1, "terms": []}), encoding="utf-8"
    )
    return project


def test_request_is_blind_json_mode_qwen_without_completion_cap(tmp_path):
    project = make_project(tmp_path, "qwen-blind-test")
    # Blindness is proved by the target canary not entering ProjectInputs or payload.
    (project / "target.dj").write_text("LEAKED_ENGLISH_CANARY\n", encoding="utf-8")

    inputs = MODULE.shared.load_project(project)
    schema = MODULE.shared.load_analysis_schema()
    payload = MODULE.build_request_payload(inputs, inputs.paragraphs, schema)
    serialized = json.dumps(payload, ensure_ascii=False)

    assert payload["model"] == "qwen3.8-max"
    assert payload["enable_thinking"] is False
    assert "max_tokens" not in payload
    assert "max_completion_tokens" not in payload
    assert payload["response_format"] == {"type": "json_object"}
    assert "LEAKED_ENGLISH_CANARY" not in serialized


def test_credential_flag_variants_are_rejected_without_echo(capsys):
    try:
        MODULE.parse_args(["project", "--api_key", "SENTINEL_SECRET"])
    except SystemExit as exc:
        assert exc.code == 2
    captured = capsys.readouterr()
    assert "SENTINEL_SECRET" not in captured.err
    assert "not accepted on the command line" in captured.err


def test_provider_prefixed_credential_flag_is_rejected_without_echo(capsys):
    try:
        MODULE.parse_args(["project", "--qwen-api-key=SENTINEL_SECRET"])
    except SystemExit as exc:
        assert exc.code == 2
    captured = capsys.readouterr()
    assert "SENTINEL_SECRET" not in captured.err
    assert "not accepted on the command line" in captured.err


def test_endpoint_flag_is_rejected_without_echo(capsys):
    try:
        MODULE.parse_args(
            ["project", "--base-url=https://SENTINEL.example.invalid/v1"]
        )
    except SystemExit as exc:
        assert exc.code == 2
    captured = capsys.readouterr()
    assert "SENTINEL" not in captured.err
    assert "not accepted on the command line" in captured.err


def test_default_output_is_provider_specific():
    args = MODULE.parse_args(["project"])
    assert args.output is None
    assert MODULE.PROVIDER == "qwencloud"
    assert MODULE.MODEL == "qwen3.8-max"


@pytest.mark.parametrize("value", ["nan", "inf", "0", "-1"])
def test_timeout_must_be_positive_and_finite(value, capsys):
    with pytest.raises(SystemExit) as exc_info:
        MODULE.parse_args(["project", "--timeout", value])
    assert exc_info.value.code == 2
    assert "finite number greater than zero" in capsys.readouterr().err


def test_artifact_records_local_schema_validation_not_provider_strictness(tmp_path):
    project = make_project(tmp_path, "qwen-provenance-test")
    inputs = MODULE.shared.load_project(project)
    endpoint = MODULE.resolve_endpoint(
        {MODULE.WORKSPACE_ID_ENVIRONMENT_VARIABLE: "ws-provenance-123"}
    )
    artifact = MODULE.build_artifact(inputs, [], 1, 30.0, endpoint)
    assert artifact["configuration"]["response_format"] == "json_object"
    assert artifact["configuration"]["strict"] is False
    assert artifact["configuration"]["base_url"] == endpoint.base_url


def test_workspace_id_constructs_official_china_endpoint():
    endpoint = MODULE.resolve_endpoint(
        {MODULE.WORKSPACE_ID_ENVIRONMENT_VARIABLE: "Workspace-123"}
    )
    assert endpoint.workspace_id == "workspace-123"
    assert endpoint.host == "workspace-123.cn-beijing.maas.aliyuncs.com"
    assert endpoint.base_url == (
        "https://workspace-123.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    )
    assert endpoint.api_url == f"{endpoint.base_url}/chat/completions"
    assert endpoint.source == (
        f"environment variable {MODULE.WORKSPACE_ID_ENVIRONMENT_VARIABLE}"
    )


def test_project_base_url_environment_variable_has_priority_and_is_canonicalized():
    endpoint = MODULE.resolve_endpoint(
        {
            MODULE.BASE_URL_ENVIRONMENT_VARIABLE: (
                "https://workspace-a.cn-beijing.maas.aliyuncs.com:443/"
                "compatible-mode/v1/"
            ),
            MODULE.WORKSPACE_ID_ENVIRONMENT_VARIABLE: "workspace-b",
        }
    )
    assert endpoint.workspace_id == "workspace-a"
    assert endpoint.base_url == (
        "https://workspace-a.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    )
    assert endpoint.source == (
        f"environment variable {MODULE.BASE_URL_ENVIRONMENT_VARIABLE}"
    )


def test_invalid_explicit_base_url_does_not_fall_back_to_workspace_id():
    with pytest.raises(MODULE.AnalysisError, match="official allowlist"):
        MODULE.resolve_endpoint(
            {
                MODULE.BASE_URL_ENVIRONMENT_VARIABLE: (
                    "https://attacker.example.invalid/compatible-mode/v1"
                ),
                MODULE.WORKSPACE_ID_ENVIRONMENT_VARIABLE: "workspace-safe",
            }
        )


@pytest.mark.parametrize(
    "base_url",
    [
        "http://workspace-a.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "https://workspace-a.example.invalid/compatible-mode/v1",
        "https://workspace-a.cn-beijing.maas.aliyuncs.com.evil.invalid/compatible-mode/v1",
        "https://workspace-a.extra.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        "https://user:secret@workspace-a.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        "https://workspace-a.cn-beijing.maas.aliyuncs.com:444/compatible-mode/v1",
        "https://workspace-a.cn-beijing.maas.aliyuncs.com/v1",
        "https://workspace-a.cn-beijing.maas.aliyuncs.com/compatible-mode/v1?token=secret",
        "https://workspace-a.cn-beijing.maas.aliyuncs.com/compatible-mode/v1#fragment",
    ],
)
def test_untrusted_or_malformed_base_urls_are_rejected(base_url):
    with pytest.raises(MODULE.AnalysisError):
        MODULE.resolve_endpoint({MODULE.BASE_URL_ENVIRONMENT_VARIABLE: base_url})


@pytest.mark.parametrize(
    "workspace_id",
    ["", "-workspace", "workspace-", "workspace.id", "workspace_id", "a" * 64],
)
def test_invalid_workspace_ids_are_rejected(workspace_id):
    environment = {MODULE.WORKSPACE_ID_ENVIRONMENT_VARIABLE: workspace_id}
    with pytest.raises(MODULE.AnalysisError):
        MODULE.resolve_endpoint(environment)


def test_missing_endpoint_is_rejected_instead_of_using_generic_dashscope():
    with pytest.raises(MODULE.AnalysisError, match="missing Qwen endpoint"):
        MODULE.resolve_endpoint({})


def test_request_revalidates_the_complete_endpoint_before_opening(tmp_path, monkeypatch):
    project = make_project(tmp_path, "qwen-request-endpoint-test")
    inputs = MODULE.shared.load_project(project)
    schema = MODULE.shared.load_analysis_schema()
    safe = MODULE.resolve_endpoint(
        {MODULE.WORKSPACE_ID_ENVIRONMENT_VARIABLE: "workspace-safe"}
    )
    tampered = MODULE.QwenEndpoint(
        base_url=safe.base_url,
        api_url="https://attacker.example.invalid/chat/completions",
        host=safe.host,
        workspace_id=safe.workspace_id,
        source=safe.source,
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("a tampered endpoint must not reach the URL opener")

    monkeypatch.setattr(MODULE.urllib.request, "build_opener", forbidden)
    with pytest.raises(MODULE.AnalysisError, match="changed after validation"):
        MODULE.request_batch(
            inputs,
            inputs.paragraphs,
            schema,
            MODULE.Credential("SENTINEL_SECRET", "test"),
            tampered,
            1.0,
        )


def test_redirect_handler_refuses_to_construct_a_followup_request():
    handler = MODULE.RejectRedirectHandler()
    assert handler.redirect_request(None, None, 302, "Found", {}, "https://evil") is None


def test_dry_run_reports_only_safe_endpoint_metadata_without_key_or_network(
    tmp_path, monkeypatch, capsys
):
    project = make_project(tmp_path, "qwen-dry-run-test")
    monkeypatch.delenv(MODULE.BASE_URL_ENVIRONMENT_VARIABLE, raising=False)
    monkeypatch.setenv(MODULE.WORKSPACE_ID_ENVIRONMENT_VARIABLE, "workspace-dry-run")
    monkeypatch.setenv(MODULE.ENVIRONMENT_VARIABLE, "SENTINEL_SECRET")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("dry-run must not read a credential or send a request")

    monkeypatch.setattr(MODULE, "load_credential", forbidden)
    monkeypatch.setattr(MODULE.urllib.request, "build_opener", forbidden)

    assert MODULE.main([str(project), "--dry-run"]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "SENTINEL_SECRET" not in captured.out
    assert "credential source" not in captured.out
    assert "environment variable QWEN_WORKSPACE_ID" in captured.out
    assert "workspace-dry-run.cn-beijing.maas.aliyuncs.com" in captured.out
    assert "no credential read and no request sent" in captured.out
