#!/usr/bin/env python3
"""Run and score the two-track Kimi/DeepSeek semantic benchmark.

Live calls are opt-in and sequential.  The source-analysis track never contains
an English target; the bilingual-review track never contains source-analysis
output.  Provider output is scored exactly as returned: invalid JSON, schema
failure, empty output, and timeout are failures and are never repaired.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GOLD = ROOT / "tests" / "fixtures" / "semantic-gold.json"
PROVIDERS = {
    "kimi": {
        "model": "kimi-k3",
        "endpoint": "https://api.moonshot.cn/v1/chat/completions",
        "environment": "KIMI_API_KEY",
        "keychain_service": "mpi-kimi-review",
    },
    "deepseek": {
        "model": "deepseek-v4-pro",
        "endpoint": "https://api.deepseek.com/chat/completions",
        "environment": "DEEPSEEK_API_KEY",
        "keychain_service": "mpi-deepseek-review",
    },
}
TRACKS = ("source_analysis", "bilingual_review")
EVIDENCE_STATUSES = {"explicit", "contextual_inference", "ambiguous"}
SOURCE_STATUSES = {"clear", "needs_human"}
SEMANTIC_ROLES = {
    "agent", "experiencer", "patient", "theme", "beneficiary", "recipient",
    "instrument", "stimulus", "causer", "source", "goal", "location", "other",
}
RELATION_TYPES = {
    "purpose", "cause", "condition", "result", "contrast", "progression",
    "cost", "concession", "coordination", "temporal", "other",
}
SCOPE_KINDS = {
    "tense", "aspect", "modality", "negation", "quantity", "degree", "other",
}
MAX_PROVIDER_RESPONSE_BYTES = 16 * 1024 * 1024
SEVERITIES = {"critical", "major", "minor", "discussion"}
REVIEW_CATEGORIES = {
    "meaning",
    "omission",
    "addition",
    "terminology",
    "register",
    "other",
}
REVIEW_CODES = {
    "predicate_drift",
    "role_drift",
    "logical_relation",
    "scope",
    "negation_scope",
    "unsupported_tense",
    "unsupported_modality",
    "omission",
    "addition",
    "terminology",
    "coreference_meaning",
    "publication_register",
    "other",
}


class BenchmarkError(RuntimeError):
    """Expected benchmark failure safe to show without provider response text."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"cannot read valid JSON from {path}") from exc
    if not isinstance(value, dict):
        raise BenchmarkError(f"{path} must contain a JSON object")
    return value


def validate_gold(gold: dict[str, Any]) -> list[dict[str, Any]]:
    if gold.get("version") != 1 or not isinstance(gold.get("cases"), list):
        raise BenchmarkError("gold file must have version 1 and a cases array")
    cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for case in gold["cases"]:
        if not isinstance(case, dict):
            raise BenchmarkError("each gold case must be an object")
        case_id = case.get("case_id")
        track = case.get("track")
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise BenchmarkError("gold case_id values must be unique non-empty strings")
        if track not in TRACKS or not isinstance(case.get("source"), str):
            raise BenchmarkError(f"invalid track/source in gold case {case_id}")
        context = case.get("source_context", [case["source"]])
        if not isinstance(context, list) or not context or not all(
            isinstance(item, str) for item in context
        ):
            raise BenchmarkError(
                f"source_context in gold case {case_id} must be non-empty strings"
            )
        if track == "source_analysis" and "target" in case:
            raise BenchmarkError(f"source-only case {case_id} must not contain target")
        if track == "bilingual_review" and not isinstance(case.get("target"), str):
            raise BenchmarkError(f"review case {case_id} requires target")
        metadata = case.get("metadata")
        if metadata is not None:
            allowed_metadata = {"source_origin", "delivery_format", "formality"}
            if (
                not isinstance(metadata, dict)
                or set(metadata) - allowed_metadata
                or not all(isinstance(value, str) for value in metadata.values())
            ):
                raise BenchmarkError(
                    f"metadata in gold case {case_id} contains non-policy fields"
                )
        if not isinstance(case.get("gold"), dict):
            raise BenchmarkError(f"gold annotations missing for {case_id}")
        seen.add(case_id)
        cases.append(case)
    if not all(any(case["track"] == track for case in cases) for track in TRACKS):
        raise BenchmarkError("gold file must contain both independent tracks")
    return cases


def source_response_schema() -> dict[str, Any]:
    role = {
        "type": "object",
        "additionalProperties": False,
        "required": ["predicate", "role", "participant", "evidence_status"],
        "properties": {
            "predicate": {"type": "string"},
            "role": {"type": "string", "enum": sorted(SEMANTIC_ROLES)},
            "participant": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "evidence_status": {
                "type": "string",
                "enum": sorted(EVIDENCE_STATUSES),
            },
        },
    }
    result = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "case_id",
            "predicates",
            "roles",
            "relations",
            "scopes",
            "ambiguities",
            "must_not_invent",
            "status",
        ],
        "properties": {
            "case_id": {"type": "string"},
            "predicates": {"type": "array", "items": {"type": "string"}},
            "roles": {"type": "array", "items": role},
            "relations": {
                "type": "array",
                "items": {"type": "string", "enum": sorted(RELATION_TYPES)},
            },
            "scopes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["kind", "marker", "scope"],
                    "properties": {
                        "kind": {
                            "type": "string",
                            "enum": sorted(SCOPE_KINDS),
                        },
                        "marker": {
                            "anyOf": [{"type": "string"}, {"type": "null"}]
                        },
                        "scope": {"type": "string"},
                    },
                },
            },
            "ambiguities": {"type": "array", "items": {"type": "string"}},
            "must_not_invent": {"type": "array", "items": {"type": "string"}},
            "status": {"type": "string", "enum": sorted(SOURCE_STATUSES)},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["results"],
        "properties": {"results": {"type": "array", "items": result}},
    }


def review_response_schema() -> dict[str, Any]:
    finding = {
        "type": "object",
        "additionalProperties": False,
        "required": ["code", "severity", "category", "message", "constraint"],
        "properties": {
            "code": {"type": "string", "enum": sorted(REVIEW_CODES)},
            "severity": {"type": "string", "enum": sorted(SEVERITIES)},
            "category": {
                "type": "string",
                "enum": sorted(REVIEW_CATEGORIES),
            },
            "message": {"type": "string"},
            "constraint": {"type": "string"},
        },
    }
    result = {
        "type": "object",
        "additionalProperties": False,
        "required": ["case_id", "findings", "summary"],
        "properties": {
            "case_id": {"type": "string"},
            "findings": {"type": "array", "items": finding},
            "summary": {"type": "string"},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["results"],
        "properties": {"results": {"type": "array", "items": result}},
    }


def public_cases(cases: list[dict[str, Any]], track: str) -> list[dict[str, Any]]:
    """Remove gold annotations and enforce the track's information firewall."""
    selected: list[dict[str, Any]] = []
    for case in cases:
        if case["track"] != track:
            continue
        clean: dict[str, Any] = {
            "case_id": case["case_id"],
            "source_context": case.get("source_context", [case["source"]]),
            "source": case["source"],
        }
        if track == "bilingual_review":
            clean["target"] = case["target"]
            if "metadata" in case:
                clean["metadata"] = case["metadata"]
        selected.append(clean)
    serialized = json.dumps(selected, ensure_ascii=False)
    if track == "source_analysis" and any("target" in item for item in selected):
        raise BenchmarkError("source-analysis firewall violation")
    if "source-analysis.json" in serialized or "must_preserve" in serialized:
        raise BenchmarkError("benchmark request contains another model's analysis")
    return selected


def build_messages(cases: list[dict[str, Any]], track: str) -> list[dict[str, str]]:
    clean = public_cases(cases, track)
    if track == "source_analysis":
        task = (
            "只依据中文及所给上下文做源义分析。逐案列出实义谓词、语义角色、分句关系、"
            "作用域、歧义和不得擅补的信息。省略或未知参与者可为 null；不得为了填字段而"
            "虚构角色。不要翻译成英文。"
        )
        schema = source_response_schema()
    else:
        task = (
            "独立比较中文和英文，检查谓词、语义角色、逻辑关系、作用域、时体、情态、"
            "否定、数量、遗漏、增加、术语及所声明交付形态的明显语域错误。只用中文报告"
            "真实问题和意义修正约束，不生成最终英文措辞。正确的主动被动转换不得误报。"
        )
        schema = review_response_schema()
    return [
        {
            "role": "system",
            "content": (
                "你是中英佛教文本语义评测器。必须输出 json，并严格遵守给定结构；"
                "保留歧义，不猜测缺失信息。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"任务：{task}\n\n待分析案例：\n"
                f"{json.dumps(clean, ensure_ascii=False, indent=2)}\n\n"
                f"输出 JSON Schema：\n{json.dumps(schema, ensure_ascii=False)}"
            ),
        },
    ]


def validate_response(value: Any, cases: list[dict[str, Any]], track: str) -> None:
    if not isinstance(value, dict) or set(value) != {"results"}:
        raise BenchmarkError("response must contain only a results array")
    results = value["results"]
    if not isinstance(results, list):
        raise BenchmarkError("results must be an array")
    expected_ids = [case["case_id"] for case in cases if case["track"] == track]
    actual_ids: list[str] = []
    for result in results:
        if not isinstance(result, dict):
            raise BenchmarkError("each result must be an object")
        if track == "source_analysis":
            required = {
                "case_id", "predicates", "roles", "relations", "scopes",
                "ambiguities", "must_not_invent", "status",
            }
            if set(result) != required or result.get("status") not in SOURCE_STATUSES:
                raise BenchmarkError("invalid source-analysis result fields")
            for field in ("predicates", "relations", "ambiguities", "must_not_invent"):
                if not isinstance(result[field], list) or not all(
                    isinstance(item, str) for item in result[field]
                ):
                    raise BenchmarkError(f"{field} must be an array of strings")
            if any(item not in RELATION_TYPES for item in result["relations"]):
                raise BenchmarkError("relations contains an invalid relation type")
            if not isinstance(result["scopes"], list):
                raise BenchmarkError("scopes must be an array")
            for scope in result["scopes"]:
                if not isinstance(scope, dict) or set(scope) != {"kind", "marker", "scope"}:
                    raise BenchmarkError("invalid scope object")
                if scope["kind"] not in SCOPE_KINDS:
                    raise BenchmarkError("invalid scope kind")
                if scope["marker"] is not None and not isinstance(scope["marker"], str):
                    raise BenchmarkError("scope marker must be string or null")
                if not isinstance(scope["scope"], str):
                    raise BenchmarkError("scope value must be a string")
            if not isinstance(result["roles"], list):
                raise BenchmarkError("roles must be an array")
            for role in result["roles"]:
                if not isinstance(role, dict) or set(role) != {
                    "predicate", "role", "participant", "evidence_status"
                }:
                    raise BenchmarkError("invalid semantic role object")
                if not isinstance(role["predicate"], str) or not isinstance(role["role"], str):
                    raise BenchmarkError("role predicate/name must be strings")
                if role["role"] not in SEMANTIC_ROLES:
                    raise BenchmarkError("invalid semantic role")
                if role["participant"] is not None and not isinstance(role["participant"], str):
                    raise BenchmarkError("role participant must be string or null")
                if role["evidence_status"] not in EVIDENCE_STATUSES:
                    raise BenchmarkError("invalid evidence_status")
        else:
            if set(result) != {"case_id", "findings", "summary"}:
                raise BenchmarkError("invalid bilingual-review result fields")
            if not isinstance(result["summary"], str) or not isinstance(result["findings"], list):
                raise BenchmarkError("invalid review summary/findings")
            for finding in result["findings"]:
                if not isinstance(finding, dict) or set(finding) != {
                    "code", "severity", "category", "message", "constraint"
                }:
                    raise BenchmarkError("invalid finding fields")
                if finding["code"] not in REVIEW_CODES or finding["severity"] not in SEVERITIES:
                    raise BenchmarkError("invalid finding code/severity")
                if finding["category"] not in REVIEW_CATEGORIES:
                    raise BenchmarkError("invalid finding category")
                if not all(isinstance(finding[key], str) and finding[key] for key in ("message", "constraint")):
                    raise BenchmarkError("finding message/constraint must be non-empty strings")
        case_id = result.get("case_id")
        if not isinstance(case_id, str) or case_id in actual_ids:
            raise BenchmarkError("result case_id values must be unique strings")
        actual_ids.append(case_id)
    if actual_ids != expected_ids:
        raise BenchmarkError("response case coverage/order does not match the request")


def load_credential(provider: str) -> str:
    config = PROVIDERS[provider]
    environment = config["environment"]
    value = os.environ.get(environment, "").strip()
    if value:
        return value
    if sys.platform == "darwin" and shutil.which("security"):
        try:
            completed = subprocess.run(
                [
                    "security",
                    "find-generic-password",
                    "-a",
                    getpass.getuser(),
                    "-s",
                    config["keychain_service"],
                    "-w",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise BenchmarkError(
                f"could not read the {provider} credential from Keychain"
            ) from exc
        if completed.returncode == 0 and completed.stdout.strip():
            return completed.stdout.strip()
    raise BenchmarkError(
        f"missing credential for {provider}; configure {environment} or its Keychain service"
    )


def request_payload(provider: str, track: str, messages: list[dict[str, str]]) -> dict[str, Any]:
    config = PROVIDERS[provider]
    payload: dict[str, Any] = {
        "model": config["model"],
        "messages": messages,
        "reasoning_effort": "high",
        "max_tokens": 32_768,
    }
    if provider == "kimi":
        payload["max_completion_tokens"] = payload.pop("max_tokens")
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": f"mpi_semantic_benchmark_{track}",
                "strict": True,
                "schema": source_response_schema() if track == "source_analysis" else review_response_schema(),
            },
        }
    else:
        payload["thinking"] = {"type": "enabled"}
        payload["response_format"] = {"type": "json_object"}
    return payload


def call_provider(
    provider: str,
    track: str,
    messages: list[dict[str, str]],
    credential: str,
    timeout: float,
) -> dict[str, Any]:
    payload = request_payload(provider, track, messages)
    request = urllib.request.Request(
        PROVIDERS[provider]["endpoint"],
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {credential}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(MAX_PROVIDER_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise BenchmarkError(f"{provider} returned HTTP {exc.code}; response body suppressed") from exc
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        nested_reason = getattr(exc, "reason", None)
        reason = (
            "timeout"
            if isinstance(exc, (TimeoutError, socket.timeout))
            or isinstance(nested_reason, (TimeoutError, socket.timeout))
            else "network_failure"
        )
        raise BenchmarkError(f"{provider} request failed: {reason}; response body suppressed") from exc
    if len(body) > MAX_PROVIDER_RESPONSE_BYTES:
        raise BenchmarkError(f"{provider} response exceeds the safe size limit")
    latency = time.monotonic() - started
    try:
        envelope = json.loads(body)
        choice = envelope["choices"][0]
        if choice.get("finish_reason") == "length":
            raise BenchmarkError(f"{provider} response was truncated")
        message = choice["message"]
        content = message["content"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise BenchmarkError(f"{provider} returned an invalid API envelope") from exc
    if not isinstance(content, str) or not content.strip():
        raise BenchmarkError(f"{provider} returned empty content")
    try:
        output = json.loads(content)
    except json.JSONDecodeError as exc:
        raise BenchmarkError(f"{provider} content was not valid JSON") from exc
    usage = envelope.get("usage", {})
    if not isinstance(usage, dict):
        usage = {}
    return {
        "output": output,
        "latency_seconds": latency,
        "response_model": envelope.get("model"),
        "system_fingerprint": envelope.get("system_fingerprint"),
        "usage": {
            "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
            "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
        },
    }


def estimate_cost(model: str, usage: dict[str, int], pricing: dict[str, Any]) -> float | None:
    rate = pricing.get(model)
    if not isinstance(rate, dict):
        return None
    input_rate = rate.get("input_per_million")
    output_rate = rate.get("output_per_million")
    if not isinstance(input_rate, (int, float)) or not isinstance(output_rate, (int, float)):
        return None
    return round(
        usage["prompt_tokens"] * float(input_rate) / 1_000_000
        + usage["completion_tokens"] * float(output_rate) / 1_000_000,
        8,
    )


def run_live(
    gold: dict[str, Any],
    cases: list[dict[str, Any]],
    runs: int,
    timeout: float,
    pricing: dict[str, Any],
) -> list[dict[str, Any]]:
    credentials = {provider: load_credential(provider) for provider in PROVIDERS}
    records: list[dict[str, Any]] = []
    for track in TRACKS:
        messages = build_messages(cases, track)
        request_sha256 = hashlib.sha256(
            json.dumps(messages, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        for provider in PROVIDERS:
            for run_number in range(1, runs + 1):
                base = {
                    "provider": provider,
                    "model": PROVIDERS[provider]["model"],
                    "track": track,
                    "run": run_number,
                    "request_sha256": request_sha256,
                    "schema_valid": False,
                    "timed_out": False,
                }
                started = time.monotonic()
                response: dict[str, Any] | None = None
                try:
                    response = call_provider(
                        provider, track, messages, credentials[provider], timeout
                    )
                    validate_response(response["output"], cases, track)
                except BenchmarkError as exc:
                    elapsed = time.monotonic() - started
                    message = str(exc).lower()
                    if response is not None:
                        # The provider returned billable output, but it failed
                        # the unmodified local contract.  Keep this distinct
                        # from transport/API rejection so a malformed wire
                        # schema cannot be misreported as poor model quality.
                        error_code = "schema_invalid"
                    elif "timeout" in message:
                        error_code = "timeout"
                    else:
                        http_marker = " returned http "
                        if http_marker in message:
                            suffix = message.split(http_marker, 1)[1]
                            status = suffix.split(";", 1)[0].strip()
                            error_code = (
                                f"http_{status}"
                                if status.isdigit() and len(status) == 3
                                else "provider_failure"
                            )
                        else:
                            error_code = "provider_failure"
                    failed_record = {
                        **base,
                        "timed_out": error_code == "timeout",
                        "latency_seconds": elapsed,
                        "error": error_code,
                    }
                    # A provider call can succeed (and incur billable tokens)
                    # even when the unmodified output then fails local schema
                    # validation. Preserve its usage/cost telemetry without
                    # treating or storing the invalid output as a valid run.
                    if response is not None:
                        failed_record.update(
                            {
                                "latency_seconds": response["latency_seconds"],
                                "usage": response["usage"],
                                "estimated_cost": estimate_cost(
                                    base["model"], response["usage"], pricing
                                ),
                                "response_model": response["response_model"],
                                "system_fingerprint": response["system_fingerprint"],
                            }
                        )
                    records.append(failed_record)
                    continue
                cost = estimate_cost(base["model"], response["usage"], pricing)
                records.append(
                    {
                        **base,
                        "schema_valid": True,
                        "latency_seconds": response["latency_seconds"],
                        "usage": response["usage"],
                        "estimated_cost": cost,
                        "response_model": response["response_model"],
                        "system_fingerprint": response["system_fingerprint"],
                        "output": response["output"],
                    }
                )
    return records


def f1(expected: set[Any], actual: set[Any]) -> float:
    if not expected and not actual:
        return 1.0
    if not expected or not actual:
        return 0.0
    true_positive = len(expected & actual)
    precision = true_positive / len(actual)
    recall = true_positive / len(expected)
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def role_key(role: dict[str, Any]) -> tuple[Any, ...]:
    return (
        role.get("predicate"),
        role.get("role"),
        role.get("participant"),
        role.get("evidence_status"),
    )


def outputs_by_case(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not record.get("schema_valid"):
        return {}
    return {item["case_id"]: item for item in record["output"]["results"]}


def source_scores(records: list[dict[str, Any]], cases: list[dict[str, Any]]) -> dict[str, float]:
    predicate_scores: list[float] = []
    role_scores: list[float] = []
    relation_scores: list[float] = []
    scope_scores: list[float] = []
    ambiguity_hits = 0
    ambiguity_total = 0
    source_cases = [case for case in cases if case["track"] == "source_analysis"]
    for record in records:
        indexed = outputs_by_case(record)
        for case in source_cases:
            actual = indexed.get(case["case_id"])
            gold = case["gold"]
            if actual is None:
                predicate_scores.append(0.0)
                role_scores.append(0.0)
                relation_scores.append(0.0)
                scope_scores.append(0.0)
                ambiguity_total += len(gold.get("ambiguities", []))
                continue
            predicate_scores.append(f1(set(gold.get("predicates", [])), set(actual["predicates"])))
            role_scores.append(
                f1(
                    {role_key(role) for role in gold.get("roles", [])},
                    {role_key(role) for role in actual["roles"]},
                )
            )
            relation_scores.append(
                f1(set(gold.get("relations", [])), set(actual["relations"]))
            )
            scope_scores.append(
                f1(
                    {
                        json.dumps(item, ensure_ascii=False, sort_keys=True)
                        for item in gold.get("scopes", [])
                    },
                    {
                        json.dumps(item, ensure_ascii=False, sort_keys=True)
                        for item in actual["scopes"]
                    },
                )
            )
            for ambiguity in gold.get("ambiguities", []):
                ambiguity_total += 1
                predicate, _, role_name = ambiguity.partition(".")
                matching = [
                    role for role in actual["roles"]
                    if role["predicate"] == predicate and role["role"] == role_name
                ]
                # A prose ambiguity label cannot excuse a role asserted as an
                # explicit fact. Every matching role must itself preserve the
                # uncertainty; a nullable ambiguous role is required when the
                # gold marks that slot as unknown.
                preserved = bool(matching) and all(
                    role["participant"] is None
                    and role["evidence_status"] == "ambiguous"
                    for role in matching
                )
                ambiguity_hits += int(preserved)
    return {
        "predicate_f1": round(statistics.fmean(predicate_scores), 6) if predicate_scores else 0.0,
        "role_f1": round(statistics.fmean(role_scores), 6) if role_scores else 0.0,
        "relation_f1": round(statistics.fmean(relation_scores), 6) if relation_scores else 0.0,
        "scope_f1": round(statistics.fmean(scope_scores), 6) if scope_scores else 0.0,
        "ambiguity_preservation_rate": round(ambiguity_hits / ambiguity_total, 6) if ambiguity_total else 1.0,
    }


def review_scores(records: list[dict[str, Any]], cases: list[dict[str, Any]]) -> dict[str, float]:
    expected_total = 0
    recalled = 0
    control_total = 0
    control_false_positive = 0
    review_cases = [case for case in cases if case["track"] == "bilingual_review"]
    for record in records:
        indexed = outputs_by_case(record)
        for case in review_cases:
            expected = set(case["gold"].get("blocking_codes", []))
            actual_result = indexed.get(case["case_id"])
            actual = set()
            any_finding = False
            if actual_result:
                any_finding = bool(actual_result["findings"])
                actual = {
                    finding["code"]
                    for finding in actual_result["findings"]
                    if finding["severity"] in {"critical", "major"}
                }
            expected_total += len(expected)
            recalled += len(expected & actual)
            if case["gold"].get("control"):
                control_total += 1
                control_false_positive += int(any_finding)
    return {
        "blocking_recall": round(recalled / expected_total, 6) if expected_total else 1.0,
        "control_false_positive_rate": round(control_false_positive / control_total, 6) if control_total else 0.0,
    }


def field_consistency(records: list[dict[str, Any]], cases: list[dict[str, Any]], track: str) -> float:
    valid = [record for record in records if record.get("schema_valid")]
    expected_runs = len(records)
    if len(valid) != expected_runs or expected_runs < 2:
        return 0.0 if expected_runs else 0.0
    indexed_runs = [outputs_by_case(record) for record in valid]
    comparisons: list[bool] = []
    for case in (item for item in cases if item["track"] == track):
        values = [indexed[case["case_id"]] for indexed in indexed_runs]
        if track == "source_analysis":
            fields = ("predicates", "roles", "relations", "scopes", "ambiguities", "must_not_invent", "status")
            for field in fields:
                canonical = [json.dumps(value[field], ensure_ascii=False, sort_keys=True) for value in values]
                comparisons.append(len(set(canonical)) == 1)
        else:
            finding_fields = [
                sorted(
                    (
                        finding["code"],
                        finding["severity"],
                        finding["category"],
                        " ".join(finding["constraint"].split()),
                    )
                    for finding in value["findings"]
                )
                for value in values
            ]
            comparisons.append(len({json.dumps(item) for item in finding_fields}) == 1)
    return round(sum(comparisons) / len(comparisons), 6) if comparisons else 0.0


def summarize_group(
    records: list[dict[str, Any]], cases: list[dict[str, Any]], track: str
) -> dict[str, Any]:
    total = len(records)
    valid = sum(bool(record.get("schema_valid")) for record in records)
    timeouts = sum(bool(record.get("timed_out")) for record in records)
    latencies = [float(record["latency_seconds"]) for record in records if "latency_seconds" in record]
    costs = [record["estimated_cost"] for record in records if record.get("estimated_cost") is not None]
    summary: dict[str, Any] = {
        "runs": total,
        "required_runs": 3,
        "run_count_valid": total == 3,
        "schema_valid_rate": round(valid / total, 6) if total else 0.0,
        "timeout_rate": round(timeouts / total, 6) if total else 0.0,
        "field_consistency_rate": field_consistency(records, cases, track),
        "median_latency_seconds": round(statistics.median(latencies), 6) if latencies else None,
        "max_latency_seconds": round(max(latencies), 6) if latencies else None,
        "total_estimated_cost": round(sum(costs), 8) if costs else None,
        "median_estimated_cost_per_run": (
            round(statistics.median(costs), 8) if costs else None
        ),
        "cost_currency": "pricing-file units" if costs else None,
    }
    if track == "source_analysis":
        summary.update(source_scores(records, cases))
    else:
        summary.update(review_scores(records, cases))
    return summary


def passes_gate(summary: dict[str, Any], gate: dict[str, Any], track: str) -> bool:
    if not summary.get("run_count_valid"):
        return False
    if summary["schema_valid_rate"] < float(gate.get("schema_valid_rate", 1.0)):
        return False
    if summary["timeout_rate"] > float(gate.get("max_timeout_rate", 0.0)):
        return False
    if track == "source_analysis":
        return summary["ambiguity_preservation_rate"] >= float(
            gate.get("ambiguity_preservation_rate", 1.0)
        )
    return (
        summary["blocking_recall"] >= float(gate.get("blocking_recall", 1.0))
        and summary["control_false_positive_rate"]
        <= float(gate.get("max_control_false_positive_rate", 0.0))
    )


def select_provider(summaries: dict[str, dict[str, Any]], track: str) -> str | None:
    eligible = [(provider, summary) for provider, summary in summaries.items() if summary["hard_gate_pass"]]
    if not eligible:
        return None
    if track == "source_analysis":
        key = lambda item: (
            item[1]["role_f1"],
            item[1]["relation_f1"],
            item[1]["scope_f1"],
            item[1]["field_consistency_rate"],
            item[1]["predicate_f1"],
        )
    else:
        key = lambda item: (
            item[1]["blocking_recall"],
            -item[1]["control_false_positive_rate"],
            item[1]["field_consistency_rate"],
        )
    ranked = sorted(eligible, key=key, reverse=True)
    if len(ranked) > 1 and key(ranked[0]) == key(ranked[1]):
        return None
    return ranked[0][0]


def build_report(gold: dict[str, Any], cases: list[dict[str, Any]], records: list[dict[str, Any]]) -> dict[str, Any]:
    allowed_pairs = {(provider, track) for provider in PROVIDERS for track in TRACKS}
    grouped_runs: dict[tuple[str, str], list[dict[str, Any]]] = {
        pair: [] for pair in allowed_pairs
    }
    for record in records:
        provider = record.get("provider")
        track = record.get("track")
        pair = (provider, track)
        if pair not in grouped_runs:
            raise BenchmarkError("run contains an unknown provider or track")
        if record.get("model") != PROVIDERS[provider]["model"]:
            raise BenchmarkError("run model does not match its provider configuration")
        if not isinstance(record.get("run"), int) or isinstance(record.get("run"), bool):
            raise BenchmarkError("run number must be an integer")
        request_sha256 = record.get("request_sha256")
        if (
            not isinstance(request_sha256, str)
            or len(request_sha256) != 64
            or any(character not in "0123456789abcdef" for character in request_sha256)
        ):
            raise BenchmarkError("run request_sha256 must be a lowercase SHA-256 digest")
        grouped_runs[pair].append(record)
    for pair, group in grouped_runs.items():
        if sorted(record["run"] for record in group) != [1, 2, 3]:
            raise BenchmarkError(
                f"{pair[0]}/{pair[1]} must contain exactly runs 1, 2, and 3"
            )
        if len({record["request_sha256"] for record in group}) != 1:
            raise BenchmarkError(
                f"{pair[0]}/{pair[1]} runs must use the same normalized request"
            )
    for track in TRACKS:
        track_digests = {
            grouped_runs[(provider, track)][0]["request_sha256"]
            for provider in PROVIDERS
        }
        if len(track_digests) != 1:
            raise BenchmarkError(
                f"both providers must use the same normalized request for {track}"
            )
    gates = gold.get("hard_gates", {})
    summaries: dict[str, dict[str, dict[str, Any]]] = {}
    selections: dict[str, str | None] = {}
    for track in TRACKS:
        summaries[track] = {}
        for provider in PROVIDERS:
            group = grouped_runs[(provider, track)]
            summary = summarize_group(group, cases, track)
            summary["hard_gate_pass"] = passes_gate(
                summary, gates.get(track, {}), track
            )
            summaries[track][provider] = summary
        selections[track] = select_provider(summaries[track], track)
    return {
        "version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "gold_sha256": hashlib.sha256(
            json.dumps(gold, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "selection_is_provisional": True,
        "selection": selections,
        "summaries": summaries,
        "runs": records,
    }


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    raw_arguments = list(sys.argv[1:] if argv is None else argv)
    def looks_like_credential_flag(argument: str) -> bool:
        if not argument.startswith("-"):
            return False
        name = argument.split("=", 1)[0].lstrip("-").casefold().replace("_", "-")
        return name in {
            "api-key", "apikey", "key", "token", "access-token",
            "credential", "credentials", "secret", "api-secret", "auth",
            "authorization",
        }

    if any(looks_like_credential_flag(argument) for argument in raw_arguments):
        parser.error(
            "API credentials are not accepted on the command line; use the "
            "provider environment variable or macOS Keychain"
        )
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live", action="store_true", help="make opt-in provider calls")
    mode.add_argument("--input-runs", type=Path, help="score a saved JSON report containing a runs array")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--pricing", type=Path, help="optional per-million-token rate JSON")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(raw_arguments)
    if args.runs != 3:
        parser.error("--runs must be exactly 3 for the model-admission benchmark")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.runs < 1 or args.timeout <= 0:
            raise BenchmarkError("runs and timeout must be positive")
        gold = load_json(args.gold)
        cases = validate_gold(gold)
        pricing = load_json(args.pricing) if args.pricing else {}
        if args.live:
            records = run_live(gold, cases, args.runs, args.timeout, pricing)
        else:
            saved = load_json(args.input_runs)
            records = saved.get("runs")
            if not isinstance(records, list):
                raise BenchmarkError("input-runs must contain a runs array")
            for record in records:
                if not isinstance(record, dict):
                    raise BenchmarkError("each saved run must be an object")
                if record.get("schema_valid"):
                    validate_response(record.get("output"), cases, record.get("track"))
        report = build_report(gold, cases, records)
        atomic_write_json(args.output.resolve(), report)
    except BenchmarkError as exc:
        print(f"semantic benchmark: {exc}", file=sys.stderr)
        return 1
    print(f"semantic benchmark report: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
