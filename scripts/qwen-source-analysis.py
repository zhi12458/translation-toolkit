#!/usr/bin/env python3
"""Blind Qwen3.8-Max candidate for MPI Chinese source semantic analysis.

Qwen is an independent fallback provider: it starts from the same Chinese-only
inputs and never resumes or mixes Kimi batches.  The default output is kept
provider-specific until a complete, locally validated artifact is deliberately
promoted to the canonical source-analysis.json.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import getpass
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Mapping, Sequence
import urllib.error
import urllib.parse
import urllib.request


REPOSITORY = Path(__file__).resolve().parents[1]
KIMI_SCRIPT = REPOSITORY / "scripts" / "kimi-source-analysis.py"
MODEL = "qwen3.8-max"
PROVIDER = "qwencloud"
KEYCHAIN_SERVICE = "mpi-qwen-review"
ENVIRONMENT_VARIABLE = "DASHSCOPE_API_KEY"
BASE_URL_ENVIRONMENT_VARIABLE = "QWEN_BASE_URL"
WORKSPACE_ID_ENVIRONMENT_VARIABLE = "QWEN_WORKSPACE_ID"
OFFICIAL_HOST_SUFFIX = ".cn-beijing.maas.aliyuncs.com"
COMPATIBLE_MODE_PATH = "/compatible-mode/v1"
DEFAULT_TIMEOUT_SECONDS = 300.0
DEFAULT_BATCH_SIZE = 1
DEFAULT_RETRIES = 2
MAX_PROVIDER_RESPONSE_BYTES = 16 * 1024 * 1024


def _load_shared():
    spec = importlib.util.spec_from_file_location("mpi_kimi_shared", KIMI_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("source-analysis shared validator is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


shared = _load_shared()
AnalysisError = shared.AnalysisError
Credential = shared.Credential


class QwenRateLimitError(AnalysisError):
    """Safe Qwen 429 signal; provider response bodies are never exposed."""


class RejectRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Prevent bearer credentials from following a cross-host redirect."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class QwenEndpoint:
    """A validated Alibaba Cloud China workspace endpoint."""

    base_url: str
    api_url: str
    host: str
    workspace_id: str
    source: str


def validate_workspace_id(value: str) -> str:
    """Return a canonical DNS-label workspace ID or reject it safely."""

    workspace_id = value.strip().casefold()
    if not re.fullmatch(
        r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", workspace_id
    ):
        raise AnalysisError("Qwen workspace ID is invalid")
    return workspace_id


def validate_base_url(value: str, source: str) -> QwenEndpoint:
    """Validate and canonicalize the exact official China compatible endpoint."""

    try:
        parsed = urllib.parse.urlsplit(value.strip())
        port = parsed.port
    except ValueError as exc:
        raise AnalysisError("Qwen base URL is invalid") from exc
    if parsed.scheme.casefold() != "https":
        raise AnalysisError("Qwen base URL must use HTTPS")
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise AnalysisError("Qwen base URL has an invalid authority")
    if port not in (None, 443):
        raise AnalysisError("Qwen base URL uses a disallowed port")
    if parsed.query or parsed.fragment:
        raise AnalysisError("Qwen base URL must not contain a query or fragment")
    if parsed.path not in {COMPATIBLE_MODE_PATH, f"{COMPATIBLE_MODE_PATH}/"}:
        raise AnalysisError("Qwen base URL has an invalid compatible-mode path")

    host = parsed.hostname.casefold()
    if not host.endswith(OFFICIAL_HOST_SUFFIX):
        raise AnalysisError("Qwen base URL host is not on the official allowlist")
    workspace_label = host[: -len(OFFICIAL_HOST_SUFFIX)]
    workspace_id = validate_workspace_id(workspace_label)
    if workspace_label != workspace_id:
        raise AnalysisError("Qwen base URL workspace host is invalid")

    base_url = f"https://{host}{COMPATIBLE_MODE_PATH}"
    return QwenEndpoint(
        base_url=base_url,
        api_url=f"{base_url}/chat/completions",
        host=host,
        workspace_id=workspace_id,
        source=source,
    )


def resolve_endpoint(environ: Mapping[str, str] | None = None) -> QwenEndpoint:
    """Resolve an endpoint without accepting any command-line override."""

    environment = os.environ if environ is None else environ
    configured_url = environment.get(BASE_URL_ENVIRONMENT_VARIABLE, "").strip()
    if configured_url:
        return validate_base_url(
            configured_url,
            f"environment variable {BASE_URL_ENVIRONMENT_VARIABLE}",
        )

    configured_workspace = environment.get(
        WORKSPACE_ID_ENVIRONMENT_VARIABLE, ""
    ).strip()
    if configured_workspace:
        workspace_id = validate_workspace_id(configured_workspace)
        return validate_base_url(
            f"https://{workspace_id}{OFFICIAL_HOST_SUFFIX}{COMPATIBLE_MODE_PATH}",
            f"environment variable {WORKSPACE_ID_ENVIRONMENT_VARIABLE}",
        )

    raise AnalysisError(
        "missing Qwen endpoint: set the project-approved "
        f"{BASE_URL_ENVIRONMENT_VARIABLE} or {WORKSPACE_ID_ENVIRONMENT_VARIABLE}"
    )


def load_credential(environ: Mapping[str, str] | None = None) -> Credential:
    environment = os.environ if environ is None else environ
    key = environment.get(ENVIRONMENT_VARIABLE, "").strip()
    if key:
        return Credential(key, f"environment variable {ENVIRONMENT_VARIABLE}")

    account = getpass.getuser()
    try:
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-a",
                account,
                "-s",
                KEYCHAIN_SERVICE,
                "-w",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AnalysisError("Qwen credential lookup failed") from exc
    key = result.stdout.strip() if result.returncode == 0 else ""
    if not key:
        raise AnalysisError(
            f"missing Qwen credential: set {ENVIRONMENT_VARIABLE} or Keychain "
            f"service {KEYCHAIN_SERVICE} for the current account"
        )
    return Credential(key, f"macOS Keychain ({KEYCHAIN_SERVICE}/{account})")


def build_request_payload(inputs, batch, schema_document: dict) -> dict:
    system_prompt, context_prompt, batch_prompt = shared.build_prompt(inputs, batch)
    return {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context_prompt},
            {"role": "user", "content": batch_prompt},
        ],
        "stream": False,
        "enable_thinking": False,
        # Alibaba Cloud Model Studio documents JSON Mode for the Qwen3.8-Max
        # series, not provider-enforced arbitrary JSON Schema.  The complete
        # project schema, exact paragraph coverage, and source evidence are
        # therefore enforced locally by validate_batch_content().
        "response_format": {"type": "json_object"},
    }


def request_batch(
    inputs,
    batch,
    schema_document: dict,
    credential: Credential,
    endpoint: QwenEndpoint,
    timeout: float,
) -> str:
    verified_endpoint = validate_base_url(endpoint.base_url, endpoint.source)
    if verified_endpoint != endpoint:
        raise AnalysisError("Qwen endpoint changed after validation")
    payload = build_request_payload(inputs, batch, schema_document)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        endpoint.api_url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {credential.value}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        opener = urllib.request.build_opener(RejectRedirectHandler())
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(MAX_PROVIDER_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise QwenRateLimitError("Qwen API rate limit reached") from exc
        raise AnalysisError(f"Qwen API request failed with HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AnalysisError("Qwen API request failed") from exc
    if len(raw) > MAX_PROVIDER_RESPONSE_BYTES:
        raise AnalysisError("Qwen API response exceeded the safe size limit")
    try:
        document = json.loads(raw.decode("utf-8"))
        choices = document["choices"]
        choice = choices[0]
        finish_reason = choice["finish_reason"]
        content = choice["message"]["content"]
    except (UnicodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise AnalysisError("Qwen API returned an invalid response envelope") from exc
    if not isinstance(choices, list) or len(choices) != 1:
        raise AnalysisError("Qwen API returned an invalid choice count")
    if finish_reason != "stop":
        raise AnalysisError("Qwen API did not finish with stop")
    if not isinstance(content, str) or not content.strip():
        raise AnalysisError("Qwen API returned empty structured content")
    return content


def _configuration(
    batch_size: int, timeout: float, endpoint: QwenEndpoint
) -> dict:
    return {
        "provider": PROVIDER,
        "model": MODEL,
        "base_url": endpoint.base_url,
        "reasoning_effort": "disabled",
        "batch_size": batch_size,
        "timeout_seconds": timeout,
        "response_format": "json_object",
    }


def build_artifact(
    inputs,
    analyses: Sequence[dict],
    batch_size: int,
    timeout: float,
    endpoint: QwenEndpoint,
) -> dict:
    project = inputs.project_document
    nullable = shared._nullable_project_string
    return {
        "schema_version": 1,
        "project": {
            "project_id": project["project_id"].strip(),
            "title": nullable(project, "title"),
            "source_origin": nullable(project, "source_origin"),
            "delivery_format": nullable(project, "delivery_format"),
            "external_semantic_review": (
                nullable(project, "external_semantic_review") or "allow"
            ),
        },
        "source_sha256": inputs.source_sha256,
        "project_sha256": inputs.project_sha256,
        "term_map_sha256": inputs.term_map_sha256,
        "provider": PROVIDER,
        "model": MODEL,
        "configuration": {
            "base_url": endpoint.base_url,
            "reasoning_effort": "disabled",
            "response_format": "json_object",
            "strict": False,
            "serial": True,
            "batch_size": batch_size,
            "request_count": len(shared._batches(inputs.paragraphs, batch_size)),
            "timeout_seconds": timeout,
            "max_completion_tokens": None,
            "rate_limit_tier": None,
            "rate_limit_concurrency": None,
            "rate_limit_rpm": None,
            "rate_limit_tpm": None,
        },
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "paragraphs": list(analyses),
    }


def _looks_like_credential_flag(argument: str) -> bool:
    if not argument.startswith("-"):
        return False
    name = argument.split("=", 1)[0].lstrip("-").casefold().replace("_", "-")
    sensitive_names = {
        "api-key",
        "apikey",
        "key",
        "token",
        "access-token",
        "credential",
        "credentials",
        "secret",
        "api-secret",
        "auth",
        "authorization",
        "password",
        "bearer-token",
        "private-key",
    }
    return name in sensitive_names or any(
        name.endswith(f"-{suffix}") for suffix in sensitive_names
    )


def _looks_like_endpoint_flag(argument: str) -> bool:
    if not argument.startswith("-"):
        return False
    name = argument.split("=", 1)[0].lstrip("-").casefold().replace("_", "-")
    endpoint_names = {
        "url",
        "base-url",
        "api-url",
        "endpoint",
        "host",
        "workspace",
        "workspace-id",
    }
    return name in endpoint_names or any(
        name.endswith(f"-{suffix}") for suffix in endpoint_names
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run blind Qwen3.8-Max fallback source analysis."
    )
    raw = list(sys.argv[1:] if argv is None else argv)
    if any(_looks_like_credential_flag(argument) for argument in raw):
        parser.error(
            "API credentials are not accepted on the command line; use "
            f"{ENVIRONMENT_VARIABLE} or macOS Keychain"
        )
    if any(
        _looks_like_endpoint_flag(argument) or "://" in argument
        for argument in raw
    ):
        parser.error(
            "API endpoints and workspace IDs are not accepted on the command line; "
            f"use {BASE_URL_ENVIRONMENT_VARIABLE} or "
            f"{WORKSPACE_ID_ENVIRONMENT_VARIABLE}"
        )
    parser.add_argument("project_directory")
    parser.add_argument(
        "--output",
        type=Path,
        help="output path (default: PROJECT/source-analysis-qwen.json)",
    )
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
        endpoint = resolve_endpoint()
        output = shared.validate_output_path(
            inputs, args.output or inputs.directory / "source-analysis-qwen.json"
        )
        if args.dry_run:
            for batch in batches:
                payload = build_request_payload(inputs, batch, schema_document)
                if payload["model"] != MODEL:
                    raise AnalysisError("generated Qwen request is invalid")
            print(
                f"Dry run OK: {len(inputs.paragraphs)} source paragraphs in "
                f"{len(batches)} serial Qwen batches; model: {MODEL}; endpoint "
                f"source: {endpoint.source}; endpoint host: {endpoint.host}; "
                "no credential read and no request sent."
            )
            return 0

        credential = load_credential()
        configuration = _configuration(args.batch_size, args.timeout, endpoint)
        checkpoint_path = shared._checkpoint_path(Path(output))
        analyses, completed_count = shared._load_checkpoint(
            checkpoint_path, inputs, batches, schema_document, configuration
        )
        completed_batches: list[dict] = []
        if completed_count:
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            completed_batches = checkpoint["completed_batches"]
            print(
                f"Resuming after {completed_count}/{len(batches)} validated Qwen batches.",
                flush=True,
            )
        for batch_number, batch in enumerate(
            batches[completed_count:], start=completed_count + 1
        ):
            validated_batch = None
            last_error: AnalysisError | None = None
            for attempt in range(args.retries + 1):
                try:
                    content = request_batch(
                        inputs,
                        batch,
                        schema_document,
                        credential,
                        endpoint,
                        args.timeout,
                    )
                    validated_batch = shared.validate_batch_content(
                        content, batch, schema_document, inputs.source
                    )
                    break
                except AnalysisError as exc:
                    last_error = exc
                    if attempt < args.retries:
                        if isinstance(exc, QwenRateLimitError):
                            time.sleep(min(60.0, 2.0 ** attempt))
                        print(
                            f"Qwen batch {batch_number}/{len(batches)} failed validation; "
                            f"retrying ({attempt + 1}/{args.retries}).",
                            flush=True,
                        )
            if validated_batch is None:
                assert last_error is not None
                raise last_error
            analyses.extend(validated_batch)
            completed_batches.append(
                {
                    "paragraph_ids": [paragraph.paragraph_id for paragraph in batch],
                    "paragraphs": validated_batch,
                }
            )
            shared._write_checkpoint(
                checkpoint_path, inputs, configuration, completed_batches
            )
            print(
                f"Validated Qwen source-analysis batch {batch_number}/{len(batches)}.",
                flush=True,
            )

        expected_ids = [paragraph.paragraph_id for paragraph in inputs.paragraphs]
        actual_ids = [analysis["paragraph_id"] for analysis in analyses]
        if actual_ids != expected_ids:
            raise AnalysisError("merged Qwen source analysis has invalid coverage")
        artifact = build_artifact(
            inputs, analyses, args.batch_size, args.timeout, endpoint
        )
        shared.assert_inputs_unchanged(inputs)
        shared.atomic_write_json(Path(output), artifact, schema_document)
        checkpoint_path.unlink(missing_ok=True)
    except AnalysisError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {len(analyses)} validated Qwen analyses to {Path(output).resolve()}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
