#!/usr/bin/env python3
"""Create blind DeepSeek V4 Flash source analysis for strategy M."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import getpass
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import socket
import ssl
import subprocess
import sys
import time
from typing import Mapping, Sequence
import urllib.error
import urllib.request


REPOSITORY = Path(__file__).resolve().parents[1]
SHARED_SCRIPT = REPOSITORY / "scripts" / "kimi-source-analysis.py"
BASE_URL = "https://api.deepseek.com"
API_URL = f"{BASE_URL}/chat/completions"
MODEL = "deepseek-v4-flash"
PROVIDER = "deepseek"
ENVIRONMENT_VARIABLE = "DEEPSEEK_API_KEY"
KEYCHAIN_SERVICE = "mpi-deepseek-review"
DEFAULT_BATCH_SIZE = 2
DEFAULT_TIMEOUT_SECONDS = 300.0
DEFAULT_RETRIES = 5
TRANSIENT_BATCH_RETRY_LIMIT = 2
MAX_COMPLETION_TOKENS = 8192
MAX_PROVIDER_RESPONSE_BYTES = 16 * 1024 * 1024
CONTEXT_MODE = "serial-local-window-with-full-coverage"
CONTEXT_WINDOW_PARAGRAPHS = 3
COMPONENT_MODE = "seven-pass-merge"
COMPONENT_FALLBACK_MODE = "single-paragraph-after-batch-retries"
COMPLETION_RECOVERY_MODE = "omit-max-completion-tokens-after-empty-or-length"
TRANSIENT_BATCH_RECOVERY_MODE = "retry-same-batch-after-exhausted-transient-component"
CROSS_COMPONENT_RECONCILIATION_MODE = (
    "union-validated-temporal-markers-into-must-preserve"
)
COMPONENT_EVIDENCE_PREVALIDATION_MODE = (
    "verbatim-source-evidence-before-component-acceptance"
)
COMPONENT_FIELDS = {
    "core": ("predicates", "relations"),
    "temporal": ("temporal_relations",),
    "operator_negation_modality": ("operators",),
    "operator_quantity_degree": ("operators",),
    "operator_tense_aspect_other": ("operators",),
    "reference": ("references_and_ellipsis", "elliptical_subject"),
    "constraints": (
        "cultural_allusions",
        "competing_interpretations",
        "must_preserve",
        "must_not_invent",
        "status",
    ),
}
COMPONENT_INSTRUCTIONS = {
    "core": """只生成 predicates 和 relations。选择最多八个最可能影响翻译的实义谓词，区分 agent、experiencer、patient、theme、cause、instrument、state_holder 等角色；原文未明示的参与者必须为 null，不能概括成人们或众生。关系证据必须逐字来自当前段落。""",
    "temporal": """只生成 temporal_relations。逐项识别时间先后、时点、持续、完成、重复，以及时、后、才、已、仍、再等标记。marker 必须逐字来自当前段落。""",
    "operator_negation_modality": """只生成 operators，并且只记录 negation 或 modality。最多选择三个最可能影响英译的否定或情态作用域；marker 必须逐字来自当前段落。""",
    "operator_quantity_degree": """只生成 operators，并且只记录 quantity 或 degree。最多选择三个最可能影响英译的数量或程度作用域；marker 必须逐字来自当前段落。""",
    "operator_tense_aspect_other": """只生成 operators，并且只记录 tense、aspect 或 other。最多选择两个最可能影响英译的时态、体或其他作用域；marker 必须逐字来自当前段落。""",
    "reference": """只生成 references_and_ellipsis 和 elliptical_subject。分析指代、承前主语和省略；格言、文言压缩句、对仗句必须反问谁行动或承担状态，并分开 agent、state_holder、cause、instrument。智不住三有，悲不住涅槃中的修行者承担不住的状态，智慧与慈悲是原因或凭借，不能提升为英文主语。""",
    "constraints": """只生成 cultural_allusions、competing_interpretations、must_preserve、must_not_invent 和 status。must_preserve 必须逐字包含本段所有时间时体标记及每个 cultural_allusions.expression。成语、格言、经论引语、文言固定结构和历史指涉都必须列入 cultural_allusions，external_research_required 固定为 true。独善其身必须区分孟子语境的修养守志与后起的自私贬义。任何竞争解释未决时 status 为 needs_human。""",
}
COMPONENT_CONTEXT_WINDOWS = {
    "core": 1,
    "temporal": 0,
    "operator_negation_modality": 0,
    "operator_quantity_degree": 0,
    "operator_tense_aspect_other": 0,
    "reference": 3,
    "constraints": 0,
}
OPERATOR_COMPONENT_RULES = {
    "operator_negation_modality": (("negation", "modality"), 3),
    "operator_quantity_degree": (("quantity", "degree"), 3),
    "operator_tense_aspect_other": (("tense", "aspect", "other"), 2),
}


def _load_shared():
    spec = importlib.util.spec_from_file_location("mpi_source_analysis_shared", SHARED_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("source-analysis shared validator is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


shared = _load_shared()
AnalysisError = shared.AnalysisError
Credential = shared.Credential


class DeepSeekTransientError(AnalysisError):
    """A provider failure that is safe to retry without changing semantics."""

    diagnostic_code = "deepseek_transient_failure"

    def __init__(self, message: str, **metadata: object):
        super().__init__(message)
        self.diagnostic_metadata = metadata


class DeepSeekRateLimitError(DeepSeekTransientError):
    """Safe DeepSeek 429 signal without a provider response body."""

    diagnostic_code = "deepseek_rate_limit"


class DeepSeekTransportError(DeepSeekTransientError):
    """Safe transport failure without a provider response body."""

    diagnostic_code = "deepseek_transport_failure"


class DeepSeekCompletionRecoveryError(DeepSeekTransientError):
    """A response that may recover when the explicit completion cap is omitted."""

    diagnostic_code = "deepseek_completion_recovery"


class DeepSeekHTTPError(DeepSeekTransientError):
    """A retryable HTTP status without a provider response body."""

    diagnostic_code = "deepseek_http_transient"


class DeepSeekDeterministicValidationError(AnalysisError):
    """A provider-body-free description of a deterministic local gate failure."""

    diagnostic_code = "deepseek_source_analysis_validation"

    def __init__(self, **metadata: str):
        super().__init__("DeepSeek source analysis failed deterministic validation")
        self.diagnostic_metadata = metadata


class ComponentAnalysisError(AnalysisError):
    """Adds safe component context while preserving the original cause chain."""

    def __init__(
        self,
        message: str,
        *,
        component: str,
        paragraph_id: str | None = None,
        fallback: str | None = None,
    ):
        super().__init__(message)
        self.component = component
        self.paragraph_id = paragraph_id
        self.fallback = fallback


class RejectRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def load_credential(environ: Mapping[str, str] | None = None) -> Credential:
    environment = os.environ if environ is None else environ
    key = environment.get(ENVIRONMENT_VARIABLE, "").strip()
    if key:
        return Credential(key, f"environment variable {ENVIRONMENT_VARIABLE}")
    account = getpass.getuser()
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-a", account, "-s", KEYCHAIN_SERVICE, "-w"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AnalysisError("DeepSeek credential lookup failed") from exc
    key = result.stdout.strip() if result.returncode == 0 else ""
    if not key:
        raise AnalysisError(
            f"missing DeepSeek credential: set {ENVIRONMENT_VARIABLE} or provide it through the strategy-M secure credential helper"
        )
    return Credential(key, f"macOS Keychain ({KEYCHAIN_SERVICE}/{account})")


def build_component_schema(
    schema_document: dict, paragraph_ids: Sequence[str], component: str
) -> dict:
    if component not in COMPONENT_FIELDS:
        raise AnalysisError("unknown DeepSeek source-analysis component")
    paragraph_source = schema_document["properties"]["paragraphs"]["items"]
    fields = ("paragraph_id", *COMPONENT_FIELDS[component])
    paragraph_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": list(fields),
        "properties": {
            field: copy.deepcopy(paragraph_source["properties"][field])
            for field in fields
        },
    }
    paragraph_schema["properties"]["paragraph_id"] = {
        "type": "string",
        "enum": list(paragraph_ids),
    }
    if component in OPERATOR_COMPONENT_RULES:
        allowed_kinds, maximum = OPERATOR_COMPONENT_RULES[component]
        operator_schema = paragraph_schema["properties"]["operators"]
        operator_schema["maxItems"] = maximum
        operator_schema["items"]["properties"]["kind"]["enum"] = list(
            allowed_kinds
        )
    return shared._mfjs_wire_schema(
        {
            "type": "object",
            "additionalProperties": False,
            "required": ["paragraphs"],
            "properties": {
                "paragraphs": {"type": "array", "items": paragraph_schema}
            },
        }
    )


def build_request_payload(
    inputs,
    batch,
    schema_document: dict,
    component: str,
    max_completion_tokens: int | None = MAX_COMPLETION_TOKENS,
) -> dict:
    _unused_system, context_prompt, batch_prompt = shared.build_windowed_prompt(
        inputs,
        batch,
        context_window_paragraphs=COMPONENT_CONTEXT_WINDOWS[component],
    )
    paragraph_ids = [paragraph.paragraph_id for paragraph in batch]
    provider_schema = build_component_schema(schema_document, paragraph_ids, component)
    system_prompt = f"""你是资深中文语义分析员，负责为中英佛法翻译建立盲态源义框架。你不是译者，不得生成英文初稿或改写原文。只依据给出的中文窗口、项目背景和相关术语；所有自由文本用中文，所有 evidence、marker、expression 和 clause 必须逐字复制对应当前段落。没有相关现象时输出空数组，不得虚构。

本次组件：{component}
{COMPONENT_INSTRUCTIONS[component]}

只返回严格符合所给 JSON Schema 的原生 JSON 对象，不得包裹 Markdown。"""
    schema_prompt = """必须严格按照下面的 JSON Schema 返回。顶层只能有 paragraphs，不能添加 analysis、summary、metadata、schema_version 或其他字段。
<required-json-schema>
""" + json.dumps(provider_schema, ensure_ascii=False, separators=(",", ":")) + """
</required-json-schema>"""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context_prompt},
            {"role": "user", "content": schema_prompt},
            {"role": "user", "content": batch_prompt},
        ],
        "stream": False,
        "thinking": {"type": "enabled"},
        "reasoning_effort": "high",
        "response_format": {"type": "json_object"},
    }
    if max_completion_tokens is not None:
        payload["max_tokens"] = max_completion_tokens
    return payload


def request_component(
    inputs,
    batch,
    schema_document: dict,
    component: str,
    credential: Credential,
    timeout: float,
    max_completion_tokens: int | None = MAX_COMPLETION_TOKENS,
) -> str:
    body = json.dumps(
        build_request_payload(
            inputs,
            batch,
            schema_document,
            component,
            max_completion_tokens=max_completion_tokens,
        ),
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {credential.value}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "mpi-translation-toolkit/strategy-m",
        },
    )
    try:
        opener = urllib.request.build_opener(RejectRedirectHandler())
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(MAX_PROVIDER_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise DeepSeekRateLimitError("DeepSeek API rate limit reached") from exc
        if exc.code in {408, 409, 425} or 500 <= exc.code <= 599:
            raise DeepSeekHTTPError(
                f"DeepSeek API request failed with HTTP {exc.code}",
                http_status=exc.code,
            ) from exc
        raise AnalysisError(f"DeepSeek API request failed with HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
        if isinstance(reason, (TimeoutError, socket.timeout)):
            transport_kind = "timeout"
        elif isinstance(reason, ssl.SSLError):
            transport_kind = "tls"
        elif isinstance(
            reason,
            (ConnectionAbortedError, ConnectionRefusedError, ConnectionResetError),
        ):
            transport_kind = "connection"
        else:
            transport_kind = "network"
        raise DeepSeekTransportError(
            "DeepSeek API request failed", transport_kind=transport_kind
        ) from exc
    if len(raw) > MAX_PROVIDER_RESPONSE_BYTES:
        raise AnalysisError("DeepSeek API response exceeded the safe size limit")
    try:
        envelope = json.loads(raw.decode("utf-8"))
        choices = envelope["choices"]
        choice = choices[0]
        message = choice["message"]
        content = message["content"]
        finish_reason = choice["finish_reason"]
    except (UnicodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise AnalysisError("DeepSeek API returned an invalid response envelope") from exc
    if not isinstance(choices, list) or len(choices) != 1:
        raise AnalysisError("DeepSeek API returned an invalid choice count")
    reasoning_content = message.get("reasoning_content")
    reasoning_bytes = (
        len(reasoning_content.encode("utf-8"))
        if isinstance(reasoning_content, str)
        else 0
    )
    usage = envelope.get("usage")
    completion_tokens = (
        usage.get("completion_tokens") if isinstance(usage, dict) else None
    )
    completion_metadata = (
        f"finish_reason={finish_reason}, reasoning_bytes={reasoning_bytes}, "
        "completion_tokens="
        f"{completion_tokens if isinstance(completion_tokens, int) else 'unknown'}"
    )
    if finish_reason == "length":
        raise DeepSeekCompletionRecoveryError(
            f"DeepSeek API reached the completion limit ({completion_metadata})",
            finish_reason="length",
            reasoning_bytes=reasoning_bytes,
            completion_tokens=completion_tokens,
        )
    if finish_reason != "stop":
        raise AnalysisError("DeepSeek API did not finish with stop")
    if not isinstance(content, str) or not content.strip():
        raise DeepSeekCompletionRecoveryError(
            f"DeepSeek API returned empty structured content ({completion_metadata})",
            finish_reason=finish_reason,
            reasoning_bytes=reasoning_bytes,
            completion_tokens=completion_tokens,
        )
    return content


def _walk_error_chain(exc: BaseException):
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def transient_cause(exc: BaseException) -> DeepSeekTransientError | None:
    for item in _walk_error_chain(exc):
        if isinstance(item, DeepSeekTransientError):
            return item
    return None


def safe_diagnostic(exc: BaseException) -> dict | None:
    for item in _walk_error_chain(exc):
        if isinstance(item, DeepSeekDeterministicValidationError):
            return {
                "schema_version": 1,
                "code": item.diagnostic_code,
                "retryable": False,
                **item.diagnostic_metadata,
            }
    transient = transient_cause(exc)
    if transient is None:
        return None
    diagnostic: dict[str, object] = {
        "schema_version": 1,
        "code": transient.diagnostic_code,
        "retryable": True,
    }
    for item in _walk_error_chain(exc):
        if isinstance(item, ComponentAnalysisError):
            diagnostic["component"] = item.component
            if item.paragraph_id is not None:
                diagnostic["paragraph_id"] = item.paragraph_id
            if item.fallback is not None:
                diagnostic["fallback"] = item.fallback
            break
    for key in (
        "transport_kind",
        "http_status",
        "finish_reason",
        "reasoning_bytes",
        "completion_tokens",
    ):
        value = transient.diagnostic_metadata.get(key)
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            diagnostic[key] = value
    return diagnostic


_VALIDATION_FIELD_RE = re.compile(
    r"^source analysis field \$\.paragraphs\[(L[1-9][0-9]*)\]"
    r"(?:\.([a-z_]+(?:\[[0-9]+\])?(?:\.[a-z_]+(?:\[[0-9]+\])?)*))? "
)
_VALIDATION_CATEGORIES = (
    ("has too many items", "item_limit"),
    ("is too short", "minimum_length"),
    ("is too long", "maximum_length"),
    ("has an invalid format", "invalid_format"),
    ("is below its minimum", "minimum_value"),
    ("is not above its exclusive minimum", "exclusive_minimum"),
    ("is not verbatim source evidence", "nonverbatim_evidence"),
    ("must be Chinese analytical text", "analysis_language"),
    ("cannot mark a null participant explicit", "null_explicit_participant"),
    ("cannot mark a null referent explicit", "null_explicit_referent"),
    ("lacks evidence for an explicit role", "explicit_role_evidence"),
    ("lacks evidence for an explicit relation", "explicit_relation_evidence"),
    ("lacks a marker for an explicit operator", "explicit_operator_marker"),
    ("lacks evidence for an explicit reference", "explicit_reference_evidence"),
    ("is not supported by its own evidence", "participant_evidence_support"),
    ("omits source marker", "temporal_relation_coverage"),
    ("omits temporal marker", "temporal_preservation_coverage"),
    ("promotes an explicit cause", "causal_role_promotion"),
    ("must identify an agent or state_holder", "actor_state_holder_coverage"),
    ("omits a compressed parallel clause", "compressed_clause_coverage"),
    ("does not separate cause or instrument", "causal_role_separation"),
    ("omits known allusion", "known_allusion_coverage"),
    ("omits cultural allusion", "allusion_preservation_coverage"),
)


def deterministic_validation_metadata(exc: AnalysisError) -> dict[str, str] | None:
    """Reduce a local validation error to allowlisted structural metadata."""
    message = str(exc)
    match = _VALIDATION_FIELD_RE.match(message)
    if match is None:
        return None
    category = next(
        (code for fragment, code in _VALIDATION_CATEGORIES if fragment in message),
        "field_validation",
    )
    metadata = {"paragraph_id": match.group(1), "category": category}
    if match.group(2) is not None:
        metadata["field"] = match.group(2)
    return metadata


def validate_component_content(
    content: str,
    batch,
    schema_document: dict,
    component: str,
    complete_source: str,
) -> list[dict]:
    try:
        document = json.loads(content)
    except json.JSONDecodeError as exc:
        raise AnalysisError("DeepSeek source-analysis component is not valid JSON") from exc
    expected_ids = [paragraph.paragraph_id for paragraph in batch]
    component_schema = build_component_schema(
        schema_document, expected_ids, component
    )
    shared._validate_instance(document, component_schema)
    paragraphs = document["paragraphs"]
    actual_ids = [paragraph["paragraph_id"] for paragraph in paragraphs]
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != set(expected_ids):
        raise AnalysisError(
            "DeepSeek source-analysis component has invalid paragraph coverage"
        )
    by_id = {paragraph["paragraph_id"]: paragraph for paragraph in paragraphs}
    ordered = [by_id[paragraph_id] for paragraph_id in expected_ids]
    for paragraph, partial in zip(batch, ordered, strict=True):
        validate_component_source_evidence(
            partial, paragraph.text, complete_source, component
        )
    return ordered


def validate_component_source_evidence(
    partial: dict,
    paragraph_text: str,
    complete_source: str,
    component: str,
) -> None:
    """Reject nonverbatim evidence before accepting a generated component."""
    path = f"$.paragraphs[{partial['paragraph_id']}]"
    if component == "core":
        for predicate_index, predicate in enumerate(partial["predicates"]):
            predicate_path = f"{path}.predicates[{predicate_index}]"
            shared._require_source_evidence(
                predicate["evidence"], paragraph_text, f"{predicate_path}.evidence"
            )
            for role_index, participant in enumerate(predicate["participants"]):
                role_path = f"{predicate_path}.participants[{role_index}]"
                source = (
                    paragraph_text
                    if participant["evidence_status"] == "explicit"
                    else complete_source
                )
                shared._require_source_evidence(
                    participant["evidence"], source, f"{role_path}.evidence"
                )
                if participant["evidence_status"] == "explicit":
                    shared._require_source_evidence(
                        participant["participant"],
                        paragraph_text,
                        f"{role_path}.participant",
                    )
        for relation_index, relation in enumerate(partial["relations"]):
            shared._require_source_evidence(
                relation["evidence"],
                paragraph_text,
                f"{path}.relations[{relation_index}].evidence",
            )
        return
    if component == "temporal":
        for index, relation in enumerate(partial["temporal_relations"]):
            shared._require_source_evidence(
                relation["marker"],
                paragraph_text,
                f"{path}.temporal_relations[{index}].marker",
            )
        return
    if component.startswith("operator_"):
        for index, operator in enumerate(partial["operators"]):
            shared._require_source_evidence(
                operator["marker"],
                paragraph_text,
                f"{path}.operators[{index}].marker",
            )
        return
    if component == "reference":
        for index, reference in enumerate(partial["references_and_ellipsis"]):
            reference_path = f"{path}.references_and_ellipsis[{index}]"
            shared._require_source_evidence(
                reference["expression"],
                paragraph_text,
                f"{reference_path}.expression",
            )
            shared._require_source_evidence(
                reference["evidence"],
                complete_source,
                f"{reference_path}.evidence",
            )
        for index, ellipsis in enumerate(partial["elliptical_subject"]):
            ellipsis_path = f"{path}.elliptical_subject[{index}]"
            shared._require_source_evidence(
                ellipsis["clause"], paragraph_text, f"{ellipsis_path}.clause"
            )
            shared._require_source_evidence(
                ellipsis["predicate"],
                ellipsis["clause"],
                f"{ellipsis_path}.predicate",
            )
            shared._require_source_evidence(
                ellipsis["subject_evidence"],
                complete_source,
                f"{ellipsis_path}.subject_evidence",
            )
            for role_index, binding in enumerate(ellipsis["role_bindings"]):
                role_path = f"{ellipsis_path}.role_bindings[{role_index}]"
                shared._require_source_evidence(
                    binding["evidence"], complete_source, f"{role_path}.evidence"
                )
                if binding["evidence_status"] == "explicit":
                    shared._require_source_evidence(
                        binding["participant"],
                        paragraph_text,
                        f"{role_path}.participant",
                    )
        return
    if component == "constraints":
        for index, allusion in enumerate(partial["cultural_allusions"]):
            shared._require_source_evidence(
                allusion["expression"],
                paragraph_text,
                f"{path}.cultural_allusions[{index}].expression",
            )
        for index, interpretation in enumerate(
            partial["competing_interpretations"]
        ):
            interpretation_path = f"{path}.competing_interpretations[{index}]"
            for evidence_index, evidence in enumerate(
                interpretation["supporting_evidence"]
                + interpretation["counterevidence"]
            ):
                shared._require_source_evidence(
                    evidence,
                    complete_source,
                    f"{interpretation_path}.evidence[{evidence_index}]",
                )


def _contains_ambiguous_status(value: object) -> bool:
    if isinstance(value, dict):
        if value.get("evidence_status") == "ambiguous":
            return True
        return any(_contains_ambiguous_status(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_ambiguous_status(item) for item in value)
    return False


def reconcile_temporal_markers(analyses: Sequence[dict]) -> int:
    """Preserve validated temporal markers across independently generated fields."""
    added = 0
    for analysis in analyses:
        must_preserve = analysis["must_preserve"]
        for relation in analysis["temporal_relations"]:
            marker = relation["marker"]
            if not any(marker in item for item in must_preserve):
                must_preserve.append(marker)
                added += 1
    return added


def analyze_batch(
    inputs,
    batch,
    schema_document: dict,
    credential: Credential,
    timeout: float,
    retries: int,
) -> list[dict]:
    merged = {
        paragraph.paragraph_id: {"paragraph_id": paragraph.paragraph_id}
        for paragraph in batch
    }
    for component in COMPONENT_FIELDS:
        try:
            partials = request_validated_component(
                inputs,
                batch,
                schema_document,
                component,
                credential,
                timeout,
                retries,
            )
        except AnalysisError as batch_error:
            if len(batch) == 1:
                raise ComponentAnalysisError(
                    f"DeepSeek source-analysis component {component} failed: {batch_error}",
                    component=component,
                ) from batch_error
            partials = []
            for paragraph in batch:
                single = (paragraph,)
                try:
                    partials.extend(
                        request_validated_component(
                            inputs,
                            single,
                            schema_document,
                            component,
                            credential,
                            timeout,
                            retries,
                        )
                    )
                except AnalysisError as single_error:
                    raise ComponentAnalysisError(
                        "DeepSeek source-analysis component "
                        f"{component} single-paragraph fallback {paragraph.paragraph_id} "
                        f"failed: {single_error}",
                        component=component,
                        paragraph_id=paragraph.paragraph_id,
                        fallback="single-paragraph",
                    ) from single_error
        for partial in partials:
            paragraph_id = partial.pop("paragraph_id")
            for field, value in partial.items():
                if field in merged[paragraph_id] and isinstance(value, list):
                    merged[paragraph_id][field].extend(value)
                else:
                    merged[paragraph_id][field] = value
    for analysis in merged.values():
        if _contains_ambiguous_status(analysis):
            analysis["status"] = "needs_human"
    reconcile_temporal_markers(list(merged.values()))
    combined = json.dumps(
        {"paragraphs": list(merged.values())}, ensure_ascii=False
    )
    try:
        return shared.validate_batch_content(
            combined, batch, schema_document, inputs.source
        )
    except AnalysisError as exc:
        metadata = deterministic_validation_metadata(exc)
        if metadata is None:
            raise
        raise DeepSeekDeterministicValidationError(**metadata) from exc


def request_validated_component(
    inputs,
    batch,
    schema_document: dict,
    component: str,
    credential: Credential,
    timeout: float,
    retries: int,
) -> list[dict]:
    """Request one component, dropping the cap only after a recoverable completion."""
    last_error: AnalysisError | None = None
    omit_completion_cap = False
    for attempt in range(retries + 1):
        try:
            content = request_component(
                inputs,
                batch,
                schema_document,
                component,
                credential,
                timeout,
                None if omit_completion_cap else MAX_COMPLETION_TOKENS,
            )
            return validate_component_content(
                content, batch, schema_document, component, inputs.source
            )
        except AnalysisError as exc:
            last_error = exc
            if attempt < retries:
                if isinstance(exc, DeepSeekCompletionRecoveryError):
                    if not omit_completion_cap:
                        paragraph_ids = ",".join(
                            paragraph.paragraph_id for paragraph in batch
                        )
                        print(
                            "DeepSeek completion recovery: omitting the explicit "
                            f"completion cap for {component} [{paragraph_ids}].",
                            flush=True,
                        )
                    omit_completion_cap = True
                time.sleep(min(60.0, 2.0**attempt))
    assert last_error is not None
    raise last_error


def analyze_batch_with_transient_recovery(
    inputs,
    batch,
    schema_document: dict,
    credential: Credential,
    timeout: float,
    retries: int,
    *,
    transient_batch_retry_limit: int = TRANSIENT_BATCH_RETRY_LIMIT,
) -> list[dict]:
    """Retry the unchanged batch only after an exhausted transient failure."""
    for attempt in range(transient_batch_retry_limit + 1):
        try:
            return analyze_batch(
                inputs, batch, schema_document, credential, timeout, retries
            )
        except AnalysisError as exc:
            diagnostic = safe_diagnostic(exc)
            if (
                diagnostic is None
                or diagnostic.get("retryable") is not True
                or attempt >= transient_batch_retry_limit
            ):
                raise
            paragraph_ids = ",".join(item.paragraph_id for item in batch)
            print(
                "DeepSeek transient batch recovery: retrying unchanged batch "
                f"[{paragraph_ids}] after {diagnostic['code']} "
                f"({attempt + 1}/{transient_batch_retry_limit}).",
                flush=True,
            )
            time.sleep(min(60.0, 10.0 * (2**attempt)))
    raise AssertionError("unreachable transient batch recovery state")


def configuration(batch_size: int, timeout: float, retries: int) -> dict:
    return {
        "provider": PROVIDER,
        "model": MODEL,
        "base_url": BASE_URL,
        "reasoning_effort": "high",
        "batch_size": batch_size,
        "timeout_seconds": timeout,
        "response_format": "json_object",
        "max_completion_tokens": MAX_COMPLETION_TOKENS,
        "retry_limit": retries,
        "context_mode": CONTEXT_MODE,
        "context_window_paragraphs": CONTEXT_WINDOW_PARAGRAPHS,
        "component_mode": COMPONENT_MODE,
        "component_fallback_mode": COMPONENT_FALLBACK_MODE,
        "completion_recovery_mode": COMPLETION_RECOVERY_MODE,
        "analysis_components": list(COMPONENT_FIELDS),
        "component_context_windows": COMPONENT_CONTEXT_WINDOWS,
    }


def build_artifact(
    inputs, analyses: Sequence[dict], batch_size: int, timeout: float, retries: int
) -> dict:
    project = inputs.project_document
    nullable = shared._nullable_project_string
    return {
        "schema_version": 3,
        "project": {
            "project_id": project["project_id"].strip(),
            "title": nullable(project, "title"),
            "source_origin": nullable(project, "source_origin"),
            "delivery_format": nullable(project, "delivery_format"),
            "external_semantic_review": nullable(project, "external_semantic_review") or "allow",
        },
        "source_sha256": inputs.source_sha256,
        "project_sha256": inputs.project_sha256,
        "term_map_sha256": inputs.term_map_sha256,
        "provider": PROVIDER,
        "model": MODEL,
        "configuration": {
            "base_url": BASE_URL,
            "reasoning_effort": "high",
            "response_format": "json_object",
            "strict": False,
            "serial": True,
            "batch_size": batch_size,
            "request_count": len(shared._batches(inputs.paragraphs, batch_size))
            * len(COMPONENT_FIELDS),
            "timeout_seconds": timeout,
            "max_completion_tokens": MAX_COMPLETION_TOKENS,
            "retry_limit": retries,
            "rate_limit_tier": None,
            "rate_limit_concurrency": 1,
            "rate_limit_rpm": None,
            "rate_limit_tpm": None,
            "context_mode": CONTEXT_MODE,
            "context_window_paragraphs": CONTEXT_WINDOW_PARAGRAPHS,
            "component_mode": COMPONENT_MODE,
            "component_fallback_mode": COMPONENT_FALLBACK_MODE,
            "completion_recovery_mode": COMPLETION_RECOVERY_MODE,
            "transient_batch_recovery_mode": TRANSIENT_BATCH_RECOVERY_MODE,
            "transient_batch_retry_limit": TRANSIENT_BATCH_RETRY_LIMIT,
            "cross_component_reconciliation_mode": (
                CROSS_COMPONENT_RECONCILIATION_MODE
            ),
            "component_evidence_prevalidation_mode": (
                COMPONENT_EVIDENCE_PREVALIDATION_MODE
            ),
            "analysis_components": list(COMPONENT_FIELDS),
            "component_context_windows": COMPONENT_CONTEXT_WINDOWS,
        },
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "paragraphs": list(analyses),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    raw = list(sys.argv[1:] if argv is None else argv)
    if any("key" in item.casefold() or "token" in item.casefold() or "secret" in item.casefold() for item in raw if item.startswith("-")):
        parser.error("API credentials are not accepted on the command line")
    parser.add_argument("project_directory")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(raw)
    if args.batch_size <= 0:
        parser.error("--batch-size must be greater than zero")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be a finite number greater than zero")
    if args.retries < 0:
        parser.error("--retries must not be negative")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        inputs = shared.load_project(args.project_directory)
        schema_document = shared.load_analysis_schema()
        batches = shared._batches(inputs.paragraphs, args.batch_size)
        output = shared.validate_output_path(
            inputs, args.output or inputs.directory / "source-analysis.json"
        )
        if args.dry_run:
            for batch in batches:
                for component in COMPONENT_FIELDS:
                    payload = build_request_payload(
                        inputs, batch, schema_document, component
                    )
                    if payload["model"] != MODEL:
                        raise AnalysisError("generated DeepSeek request is invalid")
            print(
                f"Dry run OK: {len(inputs.paragraphs)} source paragraphs in {len(batches)} serial DeepSeek batches and {len(COMPONENT_FIELDS)} components; no credential read and no request sent."
            )
            return 0
        credential = load_credential()
        checkpoint_path = shared._checkpoint_path(Path(output))
        run_configuration = configuration(args.batch_size, args.timeout, args.retries)
        analyses, completed_count = shared._load_checkpoint(
            checkpoint_path, inputs, batches, schema_document, run_configuration
        )
        completed_batches: list[dict] = []
        if completed_count:
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            completed_batches = checkpoint["completed_batches"]
        for batch_number, batch in enumerate(batches[completed_count:], start=completed_count + 1):
            validated = analyze_batch_with_transient_recovery(
                inputs,
                batch,
                schema_document,
                credential,
                args.timeout,
                args.retries,
            )
            analyses.extend(validated)
            completed_batches.append(
                {"paragraph_ids": [item.paragraph_id for item in batch], "paragraphs": validated}
            )
            shared._write_checkpoint(checkpoint_path, inputs, run_configuration, completed_batches)
            print(f"Validated DeepSeek source-analysis batch {batch_number}/{len(batches)}.", flush=True)
        expected_ids = [item.paragraph_id for item in inputs.paragraphs]
        if [item["paragraph_id"] for item in analyses] != expected_ids:
            raise AnalysisError("merged DeepSeek source analysis has invalid coverage")
        artifact = build_artifact(
            inputs, analyses, args.batch_size, args.timeout, args.retries
        )
        shared.assert_inputs_unchanged(inputs)
        shared.atomic_write_json(Path(output), artifact, schema_document)
        checkpoint_path.unlink(missing_ok=True)
    except AnalysisError as exc:
        diagnostic = safe_diagnostic(exc)
        if diagnostic is not None:
            print(
                "diagnostic-json:"
                + json.dumps(diagnostic, ensure_ascii=True, separators=(",", ":")),
                file=sys.stderr,
            )
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {len(analyses)} validated DeepSeek analyses to {Path(output).resolve()}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
