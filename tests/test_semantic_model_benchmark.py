import importlib.util
import copy
import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "semantic-model-benchmark.py"
SPEC = importlib.util.spec_from_file_location("semantic_model_benchmark", MODULE_PATH)
benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = benchmark
SPEC.loader.exec_module(benchmark)
GOLD = benchmark.load_json(ROOT / "tests" / "fixtures" / "semantic-gold.json")
CASES = benchmark.validate_gold(GOLD)


def valid_source_output():
    results = []
    for case in (item for item in CASES if item["track"] == "source_analysis"):
        gold = case["gold"]
        results.append(
            {
                "case_id": case["case_id"],
                "predicates": copy.deepcopy(gold.get("predicates", [])),
                "roles": copy.deepcopy(gold.get("roles", [])),
                "relations": copy.deepcopy(gold.get("relations", [])),
                "scopes": copy.deepcopy(gold.get("scopes", [])),
                "ambiguities": copy.deepcopy(gold.get("ambiguities", [])),
                "must_not_invent": copy.deepcopy(gold.get("must_not_invent", [])),
                "status": "needs_human" if gold.get("ambiguities") else "clear",
            }
        )
    return {"results": results}


def valid_review_output():
    results = []
    for case in (item for item in CASES if item["track"] == "bilingual_review"):
        findings = [
            {
                "code": code,
                "severity": "major",
                "category": (
                    "register"
                    if code == "publication_register"
                    else "terminology"
                    if code == "terminology"
                    else "meaning"
                ),
                "message": "金标所列问题。",
                "constraint": "必须保留原文意义，不得擅增。",
            }
            for code in case["gold"].get("blocking_codes", [])
        ]
        results.append(
            {
                "case_id": case["case_id"],
                "findings": findings,
                "summary": "独立准确性复核完成。",
            }
        )
    return {"results": results}


def make_records(provider, track, output, count=3):
    return [
        {
            "provider": provider,
            "model": benchmark.PROVIDERS[provider]["model"],
            "track": track,
            "run": index,
            "request_sha256": "a" * 64,
            "schema_valid": True,
            "timed_out": False,
            "latency_seconds": float(index),
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            "estimated_cost": None,
            "output": output,
        }
        for index in range(1, count + 1)
    ]


def test_gold_has_two_isolated_tracks_and_permanent_food_case():
    source_cases = [case for case in CASES if case["track"] == "source_analysis"]
    review_cases = [case for case in CASES if case["track"] == "bilingual_review"]
    food = next(case for case in source_cases if case["case_id"] == "food-obtainer-ambiguous-source")

    assert source_cases and review_cases
    assert all("target" not in case for case in source_cases)
    assert any(role["participant"] is None for role in food["gold"]["roles"])
    assert "had_to" in food["gold"]["must_not_invent"]
    assert "could" in food["gold"]["must_not_invent"]


def test_track_payloads_enforce_blind_firewalls():
    source_messages = benchmark.build_messages(CASES, "source_analysis")
    review_messages = benchmark.build_messages(CASES, "bilingual_review")
    source_payload = json.dumps(source_messages, ensure_ascii=False)
    review_payload = json.dumps(review_messages, ensure_ascii=False)

    assert '"target"' not in source_payload
    assert "How many lives" not in source_payload
    assert "source-analysis.json" not in review_payload
    assert "must_preserve" not in review_payload
    assert "How many lives" in review_payload


def test_gold_rejects_nested_target_and_analysis_metadata_canaries():
    nested_target = json.loads(json.dumps(GOLD))
    source_case = next(
        case for case in nested_target["cases"] if case["track"] == "source_analysis"
    )
    source_case["source_context"] = [{"target": "LEAKED ENGLISH DRAFT"}]
    with pytest.raises(benchmark.BenchmarkError, match="source_context"):
        benchmark.validate_gold(nested_target)

    analysis_metadata = json.loads(json.dumps(GOLD))
    review_case = next(
        case for case in analysis_metadata["cases"] if case["track"] == "bilingual_review"
    )
    review_case["metadata"] = {"predicates": ["K3 conclusion"]}
    with pytest.raises(benchmark.BenchmarkError, match="metadata"):
        benchmark.validate_gold(analysis_metadata)


def test_kimi_uses_strict_schema_while_deepseek_uses_json_object():
    messages = benchmark.build_messages(CASES, "source_analysis")
    kimi = benchmark.request_payload("kimi", "source_analysis", messages)
    deepseek = benchmark.request_payload("deepseek", "source_analysis", messages)

    assert kimi["response_format"]["type"] == "json_schema"
    assert kimi["response_format"]["json_schema"]["strict"] is True
    assert kimi["max_completion_tokens"] == 32_768
    assert "max_tokens" not in kimi
    assert "thinking" not in kimi
    assert deepseek["response_format"] == {"type": "json_object"}
    assert deepseek["max_tokens"] == 32_768
    assert deepseek["thinking"] == {"type": "enabled"}
    assert kimi["reasoning_effort"] == deepseek["reasoning_effort"] == "high"

    # Moonshot's strict MFJS validator rejects enum-only nodes even though
    # generic JSON Schema permits them.  Every benchmark enum therefore needs
    # an explicit string type on the wire.
    def enum_nodes(value):
        if isinstance(value, dict):
            if "enum" in value:
                yield value
            for child in value.values():
                yield from enum_nodes(child)
        elif isinstance(value, list):
            for child in value:
                yield from enum_nodes(child)

    schema = kimi["response_format"]["json_schema"]["schema"]
    nodes = list(enum_nodes(schema))
    assert nodes
    assert all(node.get("type") == "string" for node in nodes)


def test_cli_does_not_accept_or_echo_api_key(capsys):
    with pytest.raises(SystemExit):
        benchmark.parse_args(
            ["--live", "--output", "report.json", "--api-key", "never-echo-this"]
        )
    captured = capsys.readouterr()
    assert "never-echo-this" not in captured.out + captured.err
    assert "not accepted on the command line" in captured.err

    with pytest.raises(SystemExit):
        benchmark.parse_args(
            ["--live", "--output", "report.json", "--api_key", "underscore-secret-canary"]
        )
    captured = capsys.readouterr()
    assert "underscore-secret-canary" not in captured.out + captured.err

    with pytest.raises(SystemExit):
        benchmark.parse_args(["--live", "--runs", "1", "--output", "report.json"])


@pytest.mark.parametrize(
    "failure",
    [OSError("keychain-secret-canary"), subprocess.TimeoutExpired("security", 10)],
)
def test_keychain_failures_are_safely_wrapped(monkeypatch, failure):
    monkeypatch.delenv("KIMI_API_KEY", raising=False)
    monkeypatch.setattr(benchmark.sys, "platform", "darwin")
    monkeypatch.setattr(benchmark.shutil, "which", lambda command: "/usr/bin/security")
    monkeypatch.setattr(
        benchmark.subprocess, "run", mock.Mock(side_effect=failure)
    )

    with pytest.raises(benchmark.BenchmarkError) as caught:
        benchmark.load_credential("kimi")

    message = str(caught.value)
    assert "could not read the kimi credential from Keychain" in message
    assert "keychain-secret-canary" not in message


def test_validate_response_rejects_missing_case_without_repair():
    output = valid_source_output()
    output["results"].pop()
    with pytest.raises(benchmark.BenchmarkError, match="coverage"):
        benchmark.validate_response(output, CASES, "source_analysis")


def test_scoring_applies_hard_gates_and_allows_role_swapping():
    records = []
    records += make_records("kimi", "source_analysis", valid_source_output())
    records += make_records("deepseek", "source_analysis", valid_source_output())
    records += make_records("kimi", "bilingual_review", valid_review_output())
    records += make_records("deepseek", "bilingual_review", valid_review_output())

    report = benchmark.build_report(GOLD, CASES, records)

    assert report["summaries"]["source_analysis"]["kimi"]["hard_gate_pass"] is True
    assert report["summaries"]["bilingual_review"]["deepseek"]["hard_gate_pass"] is True
    # An exact tie is inconclusive rather than being broken by provider order.
    assert report["selection"]["source_analysis"] is None
    assert report["selection"]["bilingual_review"] is None
    assert report["selection_is_provisional"] is True


def test_scoring_can_select_different_providers_by_track():
    records = []
    records += make_records("kimi", "source_analysis", valid_source_output())
    records += make_records("deepseek", "source_analysis", valid_source_output())
    records[-1]["schema_valid"] = False
    records[-1]["output"] = None
    records += make_records("kimi", "bilingual_review", valid_review_output())
    records[-1]["schema_valid"] = False
    records[-1]["output"] = None
    records += make_records("deepseek", "bilingual_review", valid_review_output())

    report = benchmark.build_report(GOLD, CASES, records)
    assert report["selection"]["source_analysis"] == "kimi"
    assert report["selection"]["bilingual_review"] == "deepseek"


def test_invalid_schema_and_timeout_count_as_failures():
    records = make_records("kimi", "source_analysis", valid_source_output())
    records[1] = {
        **records[1],
        "schema_valid": False,
        "output": None,
        "error": "failed",
    }
    records[2] = {
        **records[2],
        "schema_valid": False,
        "timed_out": True,
        "output": None,
        "error": "timeout",
    }

    summary = benchmark.summarize_group(records, CASES, "source_analysis")
    assert summary["schema_valid_rate"] == pytest.approx(1 / 3, abs=1e-6)
    assert summary["timeout_rate"] == pytest.approx(1 / 3, abs=1e-6)
    assert benchmark.passes_gate(summary, GOLD["hard_gates"]["source_analysis"], "source_analysis") is False

    one_run = benchmark.summarize_group(records[:1], CASES, "source_analysis")
    assert one_run["run_count_valid"] is False
    assert not benchmark.passes_gate(
        one_run, GOLD["hard_gates"]["source_analysis"], "source_analysis"
    )


def test_live_schema_failure_keeps_provider_usage_and_cost(monkeypatch):
    monkeypatch.setattr(
        benchmark, "load_credential", lambda provider: f"{provider}-test-key"
    )
    calls = {}

    def fake_call_provider(provider, track, messages, credential, timeout):
        key = (provider, track)
        calls[key] = calls.get(key, 0) + 1
        output = (
            valid_source_output()
            if track == "source_analysis"
            else valid_review_output()
        )
        if key == ("kimi", "source_analysis") and calls[key] == 1:
            output = {"not_results": []}
        return {
            "output": output,
            "latency_seconds": 1.25,
            "response_model": benchmark.PROVIDERS[provider]["model"],
            "system_fingerprint": "test-fingerprint",
            "usage": {"prompt_tokens": 100, "completion_tokens": 200},
        }

    monkeypatch.setattr(benchmark, "call_provider", fake_call_provider)
    pricing = {
        "kimi-k3": {"input_per_million": 1.0, "output_per_million": 2.0},
        "deepseek-v4-pro": {
            "input_per_million": 1.0,
            "output_per_million": 2.0,
        },
    }

    records = benchmark.run_live(GOLD, CASES, 3, 10.0, pricing)
    failed = next(
        record
        for record in records
        if record["provider"] == "kimi"
        and record["track"] == "source_analysis"
        and record["run"] == 1
    )

    assert failed["schema_valid"] is False
    assert failed["usage"] == {"prompt_tokens": 100, "completion_tokens": 200}
    assert failed["estimated_cost"] == 0.0005
    assert failed["latency_seconds"] == 1.25
    assert failed["error"] == "schema_invalid"
    assert "output" not in failed


def test_live_http_failure_is_classified_without_response_body(monkeypatch):
    monkeypatch.setattr(
        benchmark, "load_credential", lambda provider: f"{provider}-test-key"
    )

    def fake_call_provider(provider, track, messages, credential, timeout):
        if provider == "kimi" and track == "source_analysis":
            raise benchmark.BenchmarkError(
                "kimi returned HTTP 400; response body suppressed"
            )
        return {
            "output": (
                valid_source_output()
                if track == "source_analysis"
                else valid_review_output()
            ),
            "latency_seconds": 1.0,
            "response_model": benchmark.PROVIDERS[provider]["model"],
            "system_fingerprint": "test-fingerprint",
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        }

    monkeypatch.setattr(benchmark, "call_provider", fake_call_provider)
    records = benchmark.run_live(GOLD, CASES, 3, 10.0, {})
    failures = [
        record
        for record in records
        if record["provider"] == "kimi"
        and record["track"] == "source_analysis"
    ]
    assert len(failures) == 3
    assert all(record["error"] == "http_400" for record in failures)
    assert all(record["timed_out"] is False for record in failures)


def test_report_rejects_missing_or_mismatched_three_run_groups():
    records = []
    for provider in benchmark.PROVIDERS:
        records += make_records(provider, "source_analysis", valid_source_output())
        records += make_records(provider, "bilingual_review", valid_review_output())
    missing = records[:-1]
    with pytest.raises(benchmark.BenchmarkError, match="exactly runs"):
        benchmark.build_report(GOLD, CASES, missing)

    mismatched = json.loads(json.dumps(records))
    mismatched[1]["request_sha256"] = "b" * 64
    with pytest.raises(benchmark.BenchmarkError, match="same normalized request"):
        benchmark.build_report(GOLD, CASES, mismatched)

    cross_provider = json.loads(json.dumps(records))
    deepseek_source = next(
        record for record in cross_provider
        if record["provider"] == "deepseek" and record["track"] == "source_analysis"
    )
    for record in cross_provider:
        if record["provider"] == "deepseek" and record["track"] == "source_analysis":
            record["request_sha256"] = "c" * 64
    assert deepseek_source
    with pytest.raises(benchmark.BenchmarkError, match="both providers"):
        benchmark.build_report(GOLD, CASES, cross_provider)


def test_ambiguity_label_cannot_hide_an_explicit_invented_agent():
    output = valid_source_output()
    food = next(
        result for result in output["results"]
        if result["case_id"] == "food-obtainer-ambiguous-source"
    )
    agent = next(
        role for role in food["roles"]
        if role["predicate"] == "得到" and role["role"] == "agent"
    )
    agent.update(participant="人们", evidence_status="explicit")
    records = make_records("kimi", "source_analysis", output)

    summary = benchmark.summarize_group(records, CASES, "source_analysis")
    assert "得到.agent" in food["ambiguities"]  # canary remains present
    assert summary["ambiguity_preservation_rate"] < 1.0
    assert not benchmark.passes_gate(
        summary, GOLD["hard_gates"]["source_analysis"], "source_analysis"
    )


def test_control_case_minor_finding_counts_as_false_positive():
    output = valid_review_output()
    control = next(
        result for result in output["results"]
        if result["case_id"] == "active-passive-control"
    )
    control["findings"] = [
        {
            "code": "role_drift",
            "severity": "minor",
            "category": "meaning",
            "message": "误报。",
            "constraint": "无须修改。",
        }
    ]
    summary = benchmark.summarize_group(
        make_records("deepseek", "bilingual_review", output),
        CASES,
        "bilingual_review",
    )
    assert summary["control_false_positive_rate"] > 0


def test_cli_scores_saved_runs_and_writes_atomically(tmp_path):
    records = []
    for provider in benchmark.PROVIDERS:
        records += make_records(provider, "source_analysis", valid_source_output())
        records += make_records(provider, "bilingual_review", valid_review_output())
    saved = tmp_path / "runs.json"
    saved.write_text(json.dumps({"runs": records}, ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "report.json"

    assert benchmark.main(["--input-runs", str(saved), "--output", str(output)]) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["selection"]["source_analysis"] is None  # exact tie
    assert report["summaries"]["source_analysis"]["kimi"]["hard_gate_pass"]
    assert not list(tmp_path.glob(".report.json.*"))
