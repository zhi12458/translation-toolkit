#!/usr/bin/env python3
"""Create blind DeepSeek V4 Flash source analysis for strategy C."""

from __future__ import annotations

import argparse
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
DEFAULT_BATCH_SIZE = 4
DEFAULT_TIMEOUT_SECONDS = 300.0
DEFAULT_RETRIES = 2
MAX_PROVIDER_RESPONSE_BYTES = 16 * 1024 * 1024


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


def build_request_payload(inputs, batch, schema_document: dict) -> dict:
    system_prompt, context_prompt, batch_prompt = shared.build_prompt(inputs, batch)
    paragraph_ids = [paragraph.paragraph_id for paragraph in batch]
    provider_schema = shared.build_provider_schema(schema_document, paragraph_ids)
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
        "response_format": {"type": "json_object"},
    }


def request_batch(inputs, batch, schema_document: dict, credential: Credential, timeout: float) -> str:
    body = json.dumps(
        build_request_payload(inputs, batch, schema_document), ensure_ascii=False
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


def configuration(batch_size: int, timeout: float) -> dict:
    return {
        "provider": PROVIDER,
        "model": MODEL,
        "base_url": BASE_URL,
        "reasoning_effort": "high",
        "batch_size": batch_size,
        "timeout_seconds": timeout,
        "response_format": "json_object",
    }


def build_artifact(inputs, analyses: Sequence[dict], batch_size: int, timeout: float) -> dict:
    project = inputs.project_document
    nullable = shared._nullable_project_string
    return {
        "schema_version": 1,
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
            "request_count": len(shared._batches(inputs.paragraphs, batch_size)),
            "timeout_seconds": timeout,
            "max_completion_tokens": None,
            "rate_limit_tier": None,
            "rate_limit_concurrency": 1,
            "rate_limit_rpm": None,
            "rate_limit_tpm": None,
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
                payload = build_request_payload(inputs, batch, schema_document)
                if payload["model"] != MODEL:
                    raise AnalysisError("generated DeepSeek request is invalid")
            print(
                f"Dry run OK: {len(inputs.paragraphs)} source paragraphs in {len(batches)} serial DeepSeek batches; no credential read and no request sent."
            )
            return 0
        credential = load_credential()
        checkpoint_path = shared._checkpoint_path(Path(output))
        run_configuration = configuration(args.batch_size, args.timeout)
        analyses, completed_count = shared._load_checkpoint(
            checkpoint_path, inputs, batches, schema_document, run_configuration
        )
        completed_batches: list[dict] = []
        if completed_count:
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            completed_batches = checkpoint["completed_batches"]
        for batch_number, batch in enumerate(batches[completed_count:], start=completed_count + 1):
            validated = None
            last_error: AnalysisError | None = None
            for attempt in range(args.retries + 1):
                try:
                    content = request_batch(inputs, batch, schema_document, credential, args.timeout)
                    validated = shared.validate_batch_content(content, batch, schema_document, inputs.source)
                    break
                except AnalysisError as exc:
                    last_error = exc
                    if attempt < args.retries:
                        time.sleep(min(60.0, 2.0**attempt))
            if validated is None:
                assert last_error is not None
                raise last_error
            analyses.extend(validated)
            completed_batches.append(
                {"paragraph_ids": [item.paragraph_id for item in batch], "paragraphs": validated}
            )
            shared._write_checkpoint(checkpoint_path, inputs, run_configuration, completed_batches)
            print(f"Validated DeepSeek source-analysis batch {batch_number}/{len(batches)}.", flush=True)
        expected_ids = [item.paragraph_id for item in inputs.paragraphs]
        if [item["paragraph_id"] for item in analyses] != expected_ids:
            raise AnalysisError("merged DeepSeek source analysis has invalid coverage")
        artifact = build_artifact(inputs, analyses, args.batch_size, args.timeout)
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
