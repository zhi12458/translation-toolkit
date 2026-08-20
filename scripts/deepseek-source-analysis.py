#!/usr/bin/env python3
"""Create blind DeepSeek V4 Flash source analysis for strategy C."""

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
MAX_COMPLETION_TOKENS = 8192
MAX_PROVIDER_RESPONSE_BYTES = 16 * 1024 * 1024
CONTEXT_MODE = "serial-local-window-with-full-coverage"
CONTEXT_WINDOW_PARAGRAPHS = 3
COMPONENT_MODE = "seven-pass-merge"
COMPONENT_FALLBACK_MODE = "single-paragraph-after-batch-retries"
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


class DeepSeekRateLimitError(AnalysisError):
    """Safe DeepSeek 429 signal without a provider response body."""


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
            f"missing DeepSeek credential: set {ENVIRONMENT_VARIABLE} or provide it through the strategy-C secure credential helper"
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


def build_request_payload(inputs, batch, schema_document: dict, component: str) -> dict:
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
    return {
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
        "max_tokens": MAX_COMPLETION_TOKENS,
        "response_format": {"type": "json_object"},
    }


def request_component(
    inputs,
    batch,
    schema_document: dict,
    component: str,
    credential: Credential,
    timeout: float,
) -> str:
    body = json.dumps(
        build_request_payload(inputs, batch, schema_document, component),
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
            "User-Agent": "mpi-translation-toolkit/strategy-c",
        },
    )
    try:
        opener = urllib.request.build_opener(RejectRedirectHandler())
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(MAX_PROVIDER_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise DeepSeekRateLimitError("DeepSeek API rate limit reached") from exc
        raise AnalysisError(f"DeepSeek API request failed with HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AnalysisError("DeepSeek API request failed") from exc
    if len(raw) > MAX_PROVIDER_RESPONSE_BYTES:
        raise AnalysisError("DeepSeek API response exceeded the safe size limit")
    try:
        envelope = json.loads(raw.decode("utf-8"))
        choices = envelope["choices"]
        choice = choices[0]
        content = choice["message"]["content"]
        finish_reason = choice["finish_reason"]
    except (UnicodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise AnalysisError("DeepSeek API returned an invalid response envelope") from exc
    if not isinstance(choices, list) or len(choices) != 1:
        raise AnalysisError("DeepSeek API returned an invalid choice count")
    if finish_reason != "stop":
        raise AnalysisError("DeepSeek API did not finish with stop")
    if not isinstance(content, str) or not content.strip():
        raise AnalysisError("DeepSeek API returned empty structured content")
    return content


def validate_component_content(
    content: str,
    batch,
    schema_document: dict,
    component: str,
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
    return [by_id[paragraph_id] for paragraph_id in expected_ids]


def _contains_ambiguous_status(value: object) -> bool:
    if isinstance(value, dict):
        if value.get("evidence_status") == "ambiguous":
            return True
        return any(_contains_ambiguous_status(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_ambiguous_status(item) for item in value)
    return False


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
                raise AnalysisError(
                    f"DeepSeek source-analysis component {component} failed: {batch_error}"
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
                    raise AnalysisError(
                        "DeepSeek source-analysis component "
                        f"{component} single-paragraph fallback {paragraph.paragraph_id} "
                        f"failed: {single_error}"
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
    combined = json.dumps(
        {"paragraphs": list(merged.values())}, ensure_ascii=False
    )
    return shared.validate_batch_content(
        combined, batch, schema_document, inputs.source
    )


def request_validated_component(
    inputs,
    batch,
    schema_document: dict,
    component: str,
    credential: Credential,
    timeout: float,
    retries: int,
) -> list[dict]:
    """Request one component, retrying the exact same scoped request."""
    last_error: AnalysisError | None = None
    for attempt in range(retries + 1):
        try:
            content = request_component(
                inputs, batch, schema_document, component, credential, timeout
            )
            return validate_component_content(
                content, batch, schema_document, component
            )
        except AnalysisError as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(min(60.0, 2.0**attempt))
    assert last_error is not None
    raise last_error


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
            validated = analyze_batch(
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
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {len(analyses)} validated DeepSeek analyses to {Path(output).resolve()}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
