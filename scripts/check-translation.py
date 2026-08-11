#!/usr/bin/env python3
"""Deterministic translation checks for the MPI project (TDD-style gate).

Checks the mechanical invariants of a Chinese->English djot translation.
Semantic quality (fluency, register, tone) is NOT checked here — that is the
LLM review layer. This script is the hard gate: it must go green before a
translation is delivered, and it stays in toolkit/scripts/ as a regression
suite so later edits cannot silently break parity.

Severity:
  FAIL — hard invariant broken; gate is red.
  WARN — possible drift worth a reviewer's eye; does not fail the gate.
  SKIP — check lacks an optional input; allowed interactively, but forbidden by
         --strict publication mode.
  PASS — clean.

Checks:
  1. non-empty inputs       — source.dj and target.dj contain actual content
  2. line-count parity      — source.dj and target.dj must have equal lines
  3. blank-line alignment   — every blank/non-blank line matches by index
  4. paragraph parity       — equal number of blank-separated blocks
  5. heading parity         — heading levels match on the same-index line
  6. emphasis preservation  — every *...* in a source line survives on the
                              same-index target line (D5). Target may ADD
                              italics (titles, Sanskrit) — that is fine.
  7. comment parity         — comment markers align on the same-index line
  8. CJK leakage            — no Chinese characters in target (whitelistable)
  9. Chinese punctuation    — no strictly-Chinese punctuation in target
                             (，。、；：？！《》【】（）). Em dash, curly
                             quotes, middot are legal English — not flagged.
  10. bold leakage          — no Markdown ** in target (D5)
  11. digit fidelity        — source numbers appear with matching multiplicity
                              on their corresponding target line
  12. terminology           — source terms from a term map must appear in target
                             with an allowed English rendering (A3 / terms DB).
                             FAIL: term present in source, none of its
                             renderings found in target. WARN: renderings
                             found but fewer times than the source term;
                             strict mode fails coverage below 99%.
  13. bilingual freshness   — bilingual.dj, if present, equals an independently
                              computed rendering from source+target
  14. release governance    — project release policy, independent review state,
                              unresolved findings, and named approval records

Usage:
    check-translation.py <book_dir>
        Uses <book_dir>/source.dj and <book_dir>/target.dj; auto-detects
        bilingual.dj and term-map.yaml (or legacy term-map.md) in the same
        directory.
    check-translation.py <source.dj> <target.dj> [--bilingual FILE]
        Explicit files.

Options:
    --term-map FILE    Term map (default: <book_dir>/term-map.yaml, then legacy
                       term-map.md, if present).
                       Accepted formats:
                         - JSON-syntax YAML 1.2 matching schemas/term-map.schema.json
                         - markdown table rows:  | 菩提心 | bodhicitta |
                         - plain lines:           CN<TAB>EN  or  CN|EN1|EN2
                       Multiple Chinese terms separated by "/" or "、" share
                       one English side; English renderings separated by "/"
                       are alternatives, any of which satisfies the check.
    --allow-cjk LIST   Comma-separated CJK strings permitted in target
                       (e.g. quoted book titles like 《心经》).
    --project FILE     translation-project.yaml release metadata.
    --review-findings FILE
                       review-findings.jsonl status records.
    --strict           Publication mode: require public/sensitive release
                       metadata, independent review, named approval, and fail
                       when any check is skipped.
    --json             Emit machine-readable JSON results.
    --output FILE      Atomically write the JSON report; requires --json.

Exit code: 0 when no check FAILs (WARNs and, outside --strict, SKIPs allowed),
1 otherwise. Invalid or explicitly missing input paths use argparse exit code 2.
"""
import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

CJK_RE = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
    r"\U00020000-\U0002ffff\U00030000-\U000323af]"
)
# Strictly-Chinese punctuation only. Em dash (—), curly quotes (“” ‘’),
# middot (·), and ellipsis are legitimate in English prose.
CN_PUNCT_RE = re.compile(r"[，。、；：？！《》【】（）]")
EMPHASIS_RE = re.compile(r"\*[^*\n]+\*")
HEADING_RE = re.compile(r"^(#{1,6})(?:\s|$)")
BOLD_RE = re.compile(r"\*\*")

PASS, WARN, SKIP, FAIL = "PASS", "WARN", "SKIP", "FAIL"


@dataclass(frozen=True)
class TermPolicy:
    """Normalized policy loaded from the machine-readable term-map interface."""

    allowed: dict
    forbidden: dict
    needs_human: tuple


@dataclass(frozen=True)
class ProjectPolicy:
    """Release-governance fields extracted from translation-project.yaml."""

    author: str
    translator: str
    genre: str
    level: str
    independent_review_required: bool
    review_completed: bool
    reviewer: str
    named_approver_required: bool
    approved: bool
    approver: str
    approval_note: str


def read_lines(path):
    return Path(path).read_text(encoding="utf-8").splitlines()


def paths_refer_to_same_file(first, second):
    try:
        return os.path.samefile(first, second)
    except OSError:
        return Path(first).resolve() == Path(second).resolve()


def atomic_write_report(path, text):
    """Atomically replace a generated JSON report in its destination folder."""
    output = Path(path)
    parent = output.parent
    if not parent.is_dir():
        raise OSError(f"output directory does not exist: {parent}")
    if output.exists() and not output.is_file():
        raise OSError(f"output path is not a regular file: {output}")

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{output.name}.",
            suffix=".tmp",
            dir=parent,
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, output)
        temp_path = None
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass


def is_blank(line):
    return not line.strip()


def count_paras(lines):
    """Blank-separated blocks; leading/trailing blanks ignored."""
    count = 0
    in_block = False
    for line in lines:
        if line.strip():
            if not in_block:
                count += 1
                in_block = True
        else:
            in_block = False
    return count


def reject_unknown_fields(value, allowed, label):
    """Reject fields forbidden by the public JSON Schemas."""
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        raise ValueError(f"{label} has unknown fields: {', '.join(unknown)}")


def require_nonempty_string(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def heading_signature(lines):
    """Heading level per input line; 0 means the line is not a heading."""
    signature = []
    for line in lines:
        match = HEADING_RE.match(line)
        signature.append(len(match.group(1)) if match else 0)
    return signature


def term_map_from_markdown(text):
    """Parse a term map into {chinese_term: [english_renderings]}."""
    terms = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "\t" in line:
            cn, _, en = line.partition("\t")
            terms[cn.strip()] = [r.strip() for r in en.split("/") if r.strip()]
            continue
        if "|" not in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        cn_cell, en_cell = cells[0], cells[1]
        if not cn_cell or not en_cell or set(cn_cell) <= {"-", " "}:
            continue
        for cn in (c.strip() for c in re.split(r"[/、]", cn_cell) if c.strip()):
            terms[cn] = [r.strip() for r in en_cell.split("/") if r.strip()]
    return terms


def term_policy_from_yaml_json(text):
    """Parse the dependency-free JSON-syntax subset of YAML 1.2.

    JSON is valid YAML 1.2. Restricting the checked interface to this subset
    avoids silently implementing only part of YAML while keeping the public
    filename and JSON Schema contract as ``term-map.yaml``.
    """
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "term-map.yaml must use JSON-compatible YAML syntax: "
            f"{exc.msg} at line {exc.lineno}, column {exc.colno}"
        ) from exc

    if not isinstance(document, dict) or document.get("version") != 1:
        raise ValueError("term-map.yaml must be an object with version: 1")
    reject_unknown_fields(document, {"version", "terms"}, "term-map.yaml")
    entries = document.get("terms")
    if not isinstance(entries, list):
        raise ValueError("term-map.yaml field 'terms' must be an array")

    allowed = {}
    forbidden = {}
    needs_human = set()
    seen_sources = set()
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"term-map.yaml terms[{index}] must be an object")
        reject_unknown_fields(
            entry,
            {
                "source", "sense", "preferred", "allowed", "forbidden",
                "sources", "rationale", "status", "reviewer",
            },
            f"term-map.yaml terms[{index}]",
        )
        source = entry.get("source")
        sense = entry.get("sense")
        preferred = entry.get("preferred")
        status = entry.get("status")
        allowed_values = entry.get("allowed")
        forbidden_values = entry.get("forbidden")
        sources = entry.get("sources")
        rationale = entry.get("rationale")
        reviewer = entry.get("reviewer")
        if not isinstance(source, str) or not source.strip():
            raise ValueError(f"term-map.yaml terms[{index}].source is required")
        if not isinstance(sense, str) or not sense.strip():
            raise ValueError(f"term-map.yaml terms[{index}].sense is required")
        if not isinstance(preferred, str) or not preferred.strip():
            raise ValueError(f"term-map.yaml terms[{index}].preferred is required")
        if status not in {"selected", "needs_human"}:
            raise ValueError(
                f"term-map.yaml terms[{index}].status must be selected or needs_human"
            )
        if not isinstance(allowed_values, list) or not all(
            isinstance(value, str) for value in allowed_values
        ):
            raise ValueError(f"term-map.yaml terms[{index}].allowed must be strings")
        if not isinstance(forbidden_values, list) or not all(
            isinstance(value, str) for value in forbidden_values
        ):
            raise ValueError(f"term-map.yaml terms[{index}].forbidden must be strings")
        if not isinstance(sources, list) or not sources or not all(
            isinstance(value, str) and value.strip() for value in sources
        ):
            raise ValueError(f"term-map.yaml terms[{index}].sources must be non-empty strings")
        if not isinstance(rationale, str):
            raise ValueError(f"term-map.yaml terms[{index}].rationale must be a string")
        if reviewer is not None and not isinstance(reviewer, str):
            raise ValueError(f"term-map.yaml terms[{index}].reviewer must be a string")
        if len(set(allowed_values)) != len(allowed_values):
            raise ValueError(f"term-map.yaml terms[{index}].allowed must be unique")
        if len(set(forbidden_values)) != len(forbidden_values):
            raise ValueError(f"term-map.yaml terms[{index}].forbidden must be unique")

        source = source.strip()
        if source in seen_sources:
            raise ValueError(
                "term-map.yaml supports one selected project sense per source; "
                f"duplicate source: {source}"
            )
        seen_sources.add(source)
        renderings = [preferred.strip(), *(value.strip() for value in allowed_values)]
        allowed.setdefault(source, [])
        forbidden.setdefault(source, [])
        for rendering in renderings:
            if rendering and rendering.casefold() not in {
                value.casefold() for value in allowed[source]
            }:
                allowed[source].append(rendering)
        for rendering in forbidden_values:
            rendering = rendering.strip()
            if rendering and rendering.casefold() not in {
                value.casefold() for value in forbidden[source]
            }:
                forbidden[source].append(rendering)
        if status == "needs_human":
            needs_human.add(source)

    return TermPolicy(allowed, forbidden, tuple(sorted(needs_human)))


def project_policy_from_yaml_json(text):
    """Parse release controls from JSON-compatible translation-project.yaml."""
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "translation-project.yaml must use JSON-compatible YAML syntax: "
            f"{exc.msg} at line {exc.lineno}, column {exc.colno}"
        ) from exc
    if not isinstance(document, dict):
        raise ValueError("translation-project.yaml must contain an object")

    required_top_level = {
        "project_id", "title", "author", "translator", "genre", "audience",
        "register", "cultural_bridge", "sanskrit", "versions", "release",
    }
    missing_top_level = sorted(required_top_level - document.keys())
    if missing_top_level:
        raise ValueError(
            "translation-project.yaml missing fields: " + ", ".join(missing_top_level)
        )
    reject_unknown_fields(
        document,
        required_top_level | {"scriptures"},
        "translation-project.yaml",
    )

    require_nonempty_string(document.get("project_id"), "translation-project.yaml project_id")
    require_nonempty_string(document.get("title"), "translation-project.yaml title")
    author = require_nonempty_string(
        document.get("author"), "translation-project.yaml author"
    )
    translator = require_nonempty_string(
        document.get("translator"), "translation-project.yaml translator"
    )
    require_nonempty_string(document.get("audience"), "translation-project.yaml audience")
    genre = document.get("genre")
    release = document.get("release")
    if genre not in {
        "oral_talk", "written_article", "book", "guided_meditation", "qa",
        "scripture", "other",
    }:
        raise ValueError("translation-project.yaml genre is invalid")
    if not isinstance(release, dict):
        raise ValueError("translation-project.yaml release object is required")

    register = document.get("register")
    reject_unknown_fields(register, {"voice", "formality"}, "translation-project.yaml register")
    require_nonempty_string(register.get("voice"), "translation-project.yaml register.voice")
    if register.get("formality") not in {
        "conversational", "neutral", "formal", "liturgical",
    }:
        raise ValueError("translation-project.yaml register.formality is invalid")

    cultural_bridge = document.get("cultural_bridge")
    reject_unknown_fields(
        cultural_bridge, {"policy", "notes"}, "translation-project.yaml cultural_bridge"
    )
    if cultural_bridge.get("policy") not in {
        "none", "minimal_inline", "first_mention", "footnotes_only",
    }:
        raise ValueError("translation-project.yaml cultural_bridge.policy is invalid")
    if "notes" in cultural_bridge and not isinstance(cultural_bridge["notes"], str):
        raise ValueError("translation-project.yaml cultural_bridge.notes must be a string")

    sanskrit = document.get("sanskrit")
    reject_unknown_fields(
        sanskrit, {"diacritics", "first_mention", "notes"},
        "translation-project.yaml sanskrit",
    )
    if not isinstance(sanskrit.get("diacritics"), bool):
        raise ValueError("translation-project.yaml sanskrit.diacritics must be boolean")
    if sanskrit.get("first_mention") not in {
        "english_only", "english_and_sanskrit", "sanskrit_and_english",
    }:
        raise ValueError("translation-project.yaml sanskrit.first_mention is invalid")
    if "notes" in sanskrit and not isinstance(sanskrit["notes"], str):
        raise ValueError("translation-project.yaml sanskrit.notes must be a string")

    scriptures = document.get("scriptures", [])
    if not isinstance(scriptures, list):
        raise ValueError("translation-project.yaml scriptures must be an array")
    for index, scripture in enumerate(scriptures, start=1):
        label = f"translation-project.yaml scriptures[{index}]"
        reject_unknown_fields(
            scripture,
            {"work", "source_version", "target_version", "citation_policy"},
            label,
        )
        for field in ("work", "source_version", "target_version"):
            if not isinstance(scripture.get(field), str):
                raise ValueError(f"{label}.{field} must be a string")
        if "citation_policy" in scripture and not isinstance(
            scripture["citation_policy"], str
        ):
            raise ValueError(f"{label}.citation_policy must be a string")

    versions = document.get("versions")
    reject_unknown_fields(
        versions, {"toolkit_commit", "termbase", "model", "skills"},
        "translation-project.yaml versions",
    )
    toolkit_commit = require_nonempty_string(
        versions.get("toolkit_commit"),
        "translation-project.yaml versions.toolkit_commit",
    )
    if len(toolkit_commit) < 7:
        raise ValueError(
            "translation-project.yaml versions.toolkit_commit must have at least 7 characters"
        )
    require_nonempty_string(
        versions.get("termbase"), "translation-project.yaml versions.termbase"
    )
    if "model" in versions and not isinstance(versions["model"], str):
        raise ValueError("translation-project.yaml versions.model must be a string")
    if "skills" in versions and (
        not isinstance(versions["skills"], dict)
        or not all(isinstance(value, str) for value in versions["skills"].values())
    ):
        raise ValueError("translation-project.yaml versions.skills must map to strings")

    level = release.get("level")
    independent_required = release.get("independent_review_required")
    named_required = release.get("named_approver_required", False)
    if level not in {"draft", "internal", "public", "sensitive"}:
        raise ValueError("translation-project.yaml release.level is invalid")
    if not isinstance(independent_required, bool):
        raise ValueError(
            "translation-project.yaml release.independent_review_required must be boolean"
        )
    if not isinstance(named_required, bool):
        raise ValueError(
            "translation-project.yaml release.named_approver_required must be boolean"
        )
    reject_unknown_fields(
        release,
        {
            "level", "independent_review_required", "named_approver_required",
            "independent_review", "approval",
        },
        "translation-project.yaml release",
    )

    review = release.get("independent_review", {})
    approval = release.get("approval", {})
    if not isinstance(review, dict) or not isinstance(approval, dict):
        raise ValueError("translation-project.yaml review and approval must be objects")
    reject_unknown_fields(
        review, {"completed", "reviewer"},
        "translation-project.yaml release.independent_review",
    )
    reject_unknown_fields(
        approval, {"approved", "approver", "note"},
        "translation-project.yaml release.approval",
    )
    review_completed = review.get("completed", False)
    reviewer = review.get("reviewer", "")
    approved = approval.get("approved", False)
    approver = approval.get("approver", "")
    approval_note = approval.get("note", "")
    if not isinstance(review_completed, bool) or not isinstance(reviewer, str):
        raise ValueError("independent_review requires boolean completed and string reviewer")
    if not isinstance(approved, bool) or not isinstance(approver, str):
        raise ValueError("approval requires boolean approved and string approver")
    if not isinstance(approval_note, str):
        raise ValueError("approval.note must be a string")

    return ProjectPolicy(
        author=author,
        translator=translator,
        genre=genre,
        level=level,
        independent_review_required=independent_required,
        review_completed=review_completed,
        reviewer=reviewer.strip(),
        named_approver_required=named_required,
        approved=approved,
        approver=approver.strip(),
        approval_note=approval_note,
    )


def review_findings_from_jsonl(text):
    """Parse review-findings.jsonl records against the public schema."""
    findings = []
    required = {
        "finding_id", "paragraph_id", "severity", "category", "message",
        "suggestion", "status", "reviewer",
    }
    allowed = required | {"resolution_note"}
    categories = {
        "meaning", "omission", "addition", "terminology", "scripture",
        "register", "fluency", "format", "other",
    }
    seen_ids = set()
    for line_number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            finding = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"review-findings.jsonl line {line_number}: {exc.msg}"
            ) from exc
        if not isinstance(finding, dict) or not required <= finding.keys():
            missing = sorted(required - finding.keys()) if isinstance(finding, dict) else []
            raise ValueError(
                f"review-findings.jsonl line {line_number} missing fields: {missing}"
            )
        reject_unknown_fields(
            finding, allowed, f"review-findings.jsonl line {line_number}"
        )
        for field in ("finding_id", "paragraph_id", "message", "reviewer"):
            require_nonempty_string(
                finding.get(field),
                f"review-findings.jsonl line {line_number} {field}",
            )
        if finding["finding_id"] in seen_ids:
            raise ValueError(
                f"review-findings.jsonl line {line_number} duplicates finding_id "
                f"{finding['finding_id']}"
            )
        seen_ids.add(finding["finding_id"])
        if not isinstance(finding.get("suggestion"), str):
            raise ValueError(
                f"review-findings.jsonl line {line_number} suggestion must be a string"
            )
        if "resolution_note" in finding and not isinstance(
            finding["resolution_note"], str
        ):
            raise ValueError(
                f"review-findings.jsonl line {line_number} resolution_note must be a string"
            )
        if finding["severity"] not in {"critical", "major", "minor", "discussion"}:
            raise ValueError(
                f"review-findings.jsonl line {line_number} has invalid severity"
            )
        if finding["category"] not in categories:
            raise ValueError(
                f"review-findings.jsonl line {line_number} has invalid category"
            )
        if finding["status"] not in {"open", "resolved", "rejected", "deferred"}:
            raise ValueError(
                f"review-findings.jsonl line {line_number} has invalid status"
            )
        findings.append(finding)
    return findings


def _rendering_pattern(rendering):
    """Compile a case-insensitive whole-rendering pattern for English prose."""
    rendering = rendering.strip()
    body = r"\s+".join(re.escape(part) for part in rendering.split())
    left = r"(?<!\w)" if rendering and rendering[0].isalnum() else ""
    right = r"(?!\w)" if rendering and rendering[-1].isalnum() else ""
    return re.compile(left + body + right, re.IGNORECASE)


def _rendering_spans(text, renderings):
    """Return non-overlapping matches, preferring longer allowed renderings."""
    claimed = []
    for rendering in sorted(renderings, key=len, reverse=True):
        for match in _rendering_pattern(rendering).finditer(text):
            span = match.span()
            if any(span[0] < used[1] and used[0] < span[1] for used in claimed):
                continue
            claimed.append(span)
    return claimed


def check_line_count(src, tgt):
    ok = len(src) == len(tgt)
    return (PASS if ok else FAIL,
            f"source={len(src)} target={len(tgt)}", [])


def check_non_empty(src, tgt):
    source_content = sum(not is_blank(line) for line in src)
    target_content = sum(not is_blank(line) for line in tgt)
    ok = source_content > 0 and target_content > 0
    return (
        PASS if ok else FAIL,
        f"source non-blank={source_content} target non-blank={target_content}",
        [],
    )


def check_blank_alignment(src, tgt):
    if len(src) != len(tgt):
        return FAIL, "cannot align blank lines while line counts differ", []
    mismatches = [
        i
        for i, (source_line, target_line) in enumerate(zip(src, tgt), start=1)
        if is_blank(source_line) != is_blank(target_line)
    ]
    return (
        PASS if not mismatches else FAIL,
        "all blank lines aligned"
        if not mismatches
        else "blank/non-blank mismatch at "
        + ", ".join(f"L{i}" for i in mismatches[:10]),
        mismatches,
    )


def check_paras(src, tgt):
    s, t = count_paras(src), count_paras(tgt)
    return (PASS if s == t else FAIL,
            f"source={s} target={t}", [])


def check_headings(src, tgt):
    source_signature = heading_signature(src)
    target_signature = heading_signature(tgt)
    mismatches = []
    for i in range(max(len(source_signature), len(target_signature))):
        source_level = source_signature[i] if i < len(source_signature) else None
        target_level = target_signature[i] if i < len(target_signature) else None
        if source_level != target_level:
            mismatches.append((i + 1, source_level, target_level))
    return (
        PASS if not mismatches else FAIL,
        "all heading levels aligned by line"
        if not mismatches
        else "; ".join(
            f"L{i}: H{source_level or 0} vs H{target_level or 0}"
            for i, source_level, target_level in mismatches[:10]
        ),
        mismatches,
    )


def check_emphasis(src, tgt):
    """D5 preservation: source emphasis multiplicity survives on the same line.

    Target may add emphasis for titles/Sanskrit, so its count may be higher.
    """
    missing = []
    for i, (s, t) in enumerate(zip(src, tgt), 1):
        source_count = len(EMPHASIS_RE.findall(s))
        target_count = len(EMPHASIS_RE.findall(t))
        if target_count < source_count:
            missing.append((i, source_count, target_count, s, t))
    return (PASS if not missing else FAIL,
            "all source emphasis preserved"
            if not missing else
            f"{len(missing)} source line(s) lost emphasis: "
            + ", ".join(
                f"L{i} ({source_count}->{target_count})"
                for i, source_count, target_count, _, _ in missing[:10]
            ),
            missing)


def check_comments(src, tgt):
    """Compare ordered comment delimiters and reject malformed comments."""

    def signature_and_errors(lines):
        signature = []
        errors = []
        depth = 0
        for line_number, line in enumerate(lines, start=1):
            tokens = tuple(re.findall(r"\{%|%\}", line))
            signature.append(tokens)
            for token in tokens:
                if token == "{%":
                    depth += 1
                elif depth == 0:
                    errors.append(f"L{line_number}: closing %}} without opening {{%")
                else:
                    depth -= 1
        if depth:
            errors.append(f"end of file: {depth} unclosed {{% delimiter(s)")
        return signature, errors

    source_signature, source_errors = signature_and_errors(src)
    target_signature, target_errors = signature_and_errors(tgt)
    if source_errors or target_errors:
        details = [f"source {error}" for error in source_errors]
        details.extend(f"target {error}" for error in target_errors)
        return FAIL, "; ".join(details), details

    mismatches = []
    for i in range(max(len(source_signature), len(target_signature))):
        source_markers = source_signature[i] if i < len(source_signature) else None
        target_markers = target_signature[i] if i < len(target_signature) else None
        if source_markers != target_markers:
            mismatches.append((i + 1, source_markers, target_markers))
    return (
        PASS if not mismatches else FAIL,
        "all comment markers aligned by line"
        if not mismatches
        else "; ".join(
            f"L{i}: {source_markers} vs {target_markers}"
            for i, source_markers, target_markers in mismatches[:10]
        ),
        mismatches,
    )


ANCHOR_RE = re.compile(r"\{#[^{}\n]*\}")
LINK_DEST_RE = re.compile(r"(?<=\])\([^()\n]*\)")
LINK_TGT_RE = re.compile(r"\[\d+\]\(\s*#")


def strip_structural(text):
    """Remove djot anchors {#...}, link destinations (...), and image paths —
    structural markup that may legitimately contain Chinese."""
    return LINK_DEST_RE.sub("", ANCHOR_RE.sub("", text))


def check_cjk(tgt, allow=()):
    bad = []
    for i, line in enumerate(tgt, 1):
        stripped = strip_structural(line)
        for token in allow:
            stripped = stripped.replace(token, "")
        if CJK_RE.search(stripped):
            bad.append((i, line))
    return (PASS if not bad else FAIL,
            "clean" if not bad else f"{len(bad)} line(s) contain CJK outside anchors/links: "
            + ", ".join(f"L{i}" for i, _ in bad[:10]),
            bad)


def check_cn_punct(tgt, allow=()):
    bad = []
    for i, line in enumerate(tgt, 1):
        stripped = strip_structural(line)
        for token in allow:
            stripped = stripped.replace(token, "")
        if CN_PUNCT_RE.search(stripped):
            bad.append((i, line))
    return (PASS if not bad else FAIL,
            "clean" if not bad else f"{len(bad)} line(s) contain Chinese punctuation: "
            + ", ".join(f"L{i}" for i, _ in bad[:10]),
            bad)


def check_bold(tgt):
    bad = []
    for i, line in enumerate(tgt, 1):
        if BOLD_RE.search(line):
            bad.append((i, line))
    return (PASS if not bad else FAIL,
            "clean" if not bad else f"{len(bad)} line(s) contain ** : "
            + ", ".join(f"L{i}" for i, _ in bad[:10]),
            bad)


_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
         "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
         "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
         "eighty", "ninety"]
_MONTH_NAMES = {
    1: "january", 2: "february", 3: "march", 4: "april", 5: "may",
    6: "june", 7: "july", 8: "august", 9: "september", 10: "october",
    11: "november", 12: "december",
}
_ORDINAL_WORDS = {
    1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth",
    6: "sixth", 7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth",
    11: "eleventh", 12: "twelfth", 13: "thirteenth", 14: "fourteenth",
    15: "fifteenth", 16: "sixteenth", 17: "seventeenth",
    18: "eighteenth", 19: "nineteenth", 20: "twentieth",
    21: "twenty-first", 22: "twenty-second", 23: "twenty-third",
    24: "twenty-fourth", 25: "twenty-fifth", 26: "twenty-sixth",
    27: "twenty-seventh", 28: "twenty-eighth", 29: "twenty-ninth",
    30: "thirtieth", 31: "thirty-first",
}


def numeric_ordinal(n):
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def number_to_words(n):
    if n < 20:
        return _ONES[n]
    if n < 100:
        return (_TENS[n // 10] + ("-" + _ONES[n % 10] if n % 10 else ""))
    if n < 1000:
        return _ONES[n // 100] + " hundred" + (
            (" " + number_to_words(n % 100)) if n % 100 else "")
    if n < 1000000:
        return number_to_words(n // 1000) + " thousand" + (
            (" " + number_to_words(n % 1000)) if n % 1000 else "")
    return number_to_words(n // 1000000) + " million" + (
        (" " + number_to_words(n % 1000000)) if n % 1000000 else "")


def decimal_text(value):
    text = format(Decimal(value), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def decimal_to_words(value):
    text = decimal_text(value)
    if "." not in text:
        return number_to_words(int(text))
    whole, fraction = text.split(".", 1)
    return number_to_words(int(whole)) + " point " + " ".join(
        _ONES[int(digit)] for digit in fraction
    )


def accepted_number_spellings(
    n, unit, approximate=False, date_unit="", ordinal_context=False
):
    """All English spellings that legitimately render source number n.

    unit: "" (plain), "万" (×10^4), or "亿" (×10^8). The target may keep the
    digits ("1,200"), spell them ("twelve hundred"), or scale the unit
    ("13 million" for 1300万, "18 billion" for 180亿).
    """
    number = Decimal(str(n))
    number_is_integer = number == number.to_integral_value()
    integer = int(number) if number_is_integer else None
    cands = set()

    # Plain numbers may keep their source value. Chinese magnitude units must
    # not: accepting the raw coefficient made "180亿 -> 180" a false PASS.
    if not unit:
        cands.update({decimal_text(number), decimal_to_words(number)})
        if integer in {100, 1000, 1000000, 1000000000}:
            cands.add({
                100: "a hundred",
                1000: "a thousand",
                1000000: "a million",
                1000000000: "a billion",
            }[integer])
        if integer is not None and 100 <= integer < 10000 and integer % 100 == 0:
            cands.add(f"{integer // 100} hundred")
            cands.add(number_to_words(integer // 100) + " hundred")
        if integer is not None and date_unit == "月" and integer in _MONTH_NAMES:
            cands.add(_MONTH_NAMES[integer])
        if integer is not None and date_unit in {"日", "号", "世纪"} and integer in _ORDINAL_WORDS:
            cands.add(_ORDINAL_WORDS[integer])
            cands.add(numeric_ordinal(integer))
        if integer is not None and ordinal_context and integer >= 0:
            cands.add(numeric_ordinal(integer))
            if integer in _ORDINAL_WORDS:
                cands.add(_ORDINAL_WORDS[integer])
        if integer is not None and date_unit == "年" and 1000 <= integer <= 2099 and integer % 100:
            cands.add(
                number_to_words(integer // 100) + " " + number_to_words(integer % 100)
            )

    factor = Decimal(10 ** 4 if unit == "万" else 10 ** 8 if unit == "亿" else 1)
    value = number * factor
    if unit:
        absolute = decimal_text(value)
        if approximate:
            cands.update({
                f"{absolute}+",
                f"over {absolute}",
                f"more than {absolute}",
            })
        else:
            cands.add(absolute)
            cands.add(decimal_to_words(value))
        for divisor, suffix in ((10 ** 9, "billion"), (10 ** 6, "million"),
                                (10 ** 3, "thousand")):
            if value < divisor:
                continue
            quotient = value / Decimal(divisor)
            scaled = decimal_text(quotient)
            if len(scaled.partition(".")[2]) > 3:
                continue
            if approximate:
                cands.update({
                    f"{scaled}+ {suffix}",
                    f"over {scaled} {suffix}",
                    f"more than {scaled} {suffix}",
                })
            else:
                cands.add(f"{scaled} {suffix}")
                cands.add(decimal_to_words(quotient) + " " + suffix)
                if quotient == 1:
                    cands.add(f"a {suffix}")
    return cands


SOURCE_NUMBER_RE = re.compile(
    r"(?<!\d)"
    r"(?P<ordinal>第)?"
    r"(?P<number>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)"
    r"(?:\s*(?P<approximate>多)?\s*(?P<unit>[万亿]))?"
    r"(?P<date_unit>世纪|[年月日号])?"
)


def source_content_nums(src_text):
    """Return numeric mentions, excluding structural anchors and TOC pages.

    Each item is ``(number, unit, approximate, date_unit, ordinal_context)``.
    Date context lets ``8月`` match ``August``; ordinal context lets ``第71位``
    match ``71st`` while still requiring every mention on its corresponding
    target line.
    """
    stripped = strip_structural(LINK_TGT_RE.sub("", src_text))
    mentions = []
    for match in SOURCE_NUMBER_RE.finditer(stripped):
        numeric = Decimal(match.group("number").replace(",", ""))
        number = int(numeric) if numeric == numeric.to_integral_value() else numeric
        mentions.append((
            number,
            match.group("unit") or "",
            bool(match.group("approximate")),
            match.group("date_unit") or "",
            bool(match.group("ordinal")),
        ))
    return mentions


def _normalized_number_target(text):
    # Remove only thousands separators. Prose commas must continue to delimit
    # separate number phrases for boundary checks.
    normalized = re.sub(r"(?<=\d),(?=\d)", "", text.lower())
    return re.sub(r"[\u2010-\u2015]", "-", normalized)


def _candidate_pattern(candidate):
    normalized = candidate.lower().replace(",", "")
    parts = [re.escape(part) for part in re.split(r"[\s-]+", normalized) if part]
    body = r"[\s-]+".join(parts)
    # A terminal period is ordinary list/sentence punctuation ("1."). A dot
    # followed by another digit is a decimal continuation and must not let
    # source 1 match target 1.5.
    return re.compile(
        r"(?<![a-z0-9.])" + body + r"(?![a-z0-9]|\.\d)"
    )


_NUMBER_SCALE_WORDS = {
    "hundred", "thousand", "million", "billion", "trillion",
    "quadrillion", "dozen", "score",
}
_NUMBER_PHRASE_WORDS = {
    *(_ONES),
    *(word for word in _TENS if word),
    *(_ORDINAL_WORDS.values()),
    *_NUMBER_SCALE_WORDS,
    "point",
}
_ADJACENT_TOKEN_RE = r"[a-z]+|\d+(?:\.\d+)?"


def _previous_adjacent_token(text, position):
    match = re.search(
        rf"(?P<token>{_ADJACENT_TOKEN_RE})(?P<separator>[\s-]+)$",
        text[:position],
    )
    if match is None:
        return None
    return match.group("token"), match.start("token"), match.group("separator")


def _next_adjacent_token(text, position):
    match = re.match(
        rf"(?P<separator>[\s-]+)(?P<token>{_ADJACENT_TOKEN_RE})",
        text[position:],
    )
    if match is None:
        return None
    return (
        match.group("token"),
        position + match.end("token"),
        match.group("separator"),
    )


def _is_number_phrase_token(token):
    return token in _NUMBER_PHRASE_WORDS or bool(
        re.fullmatch(r"\d+(?:\.\d+)?", token)
    )


def _is_complete_number_span(text, span, candidate):
    """Reject candidates embedded inside a larger English number phrase."""
    candidate_tokens = re.findall(r"[a-z]+|\d+(?:\.\d+)?", candidate.lower())
    if not any(_is_number_phrase_token(token) for token in candidate_tokens):
        # Named months (for example "August") are date renderings, not a
        # component of the adjacent English number phrase.
        return True
    previous = _previous_adjacent_token(text, span[0])
    following = _next_adjacent_token(text, span[1])
    candidate_is_digits = len(candidate_tokens) == 1 and bool(
        re.fullmatch(r"\d+(?:\.\d+)?", candidate_tokens[0])
    )
    for adjacent in (previous, following):
        if adjacent is None or not _is_number_phrase_token(adjacent[0]):
            continue
        adjacent_is_digits = bool(re.fullmatch(r"\d+(?:\.\d+)?", adjacent[0]))
        if candidate_is_digits and adjacent_is_digits and "-" in adjacent[2]:
            # Numeric hyphens/en-dashes commonly delimit ranges or ISO dates;
            # each source mention will claim its own span below.
            continue
        return False

    # English compounds such as "one hundred and twenty" use "and" between
    # a scale word and the final component. Do not let the final component or
    # the scaled prefix satisfy a smaller source number.
    if previous is not None and previous[0] == "and":
        before_and = _previous_adjacent_token(text, previous[1])
        if before_and is not None and before_and[0] in _NUMBER_SCALE_WORDS:
            return False
    if following is not None and following[0] == "and":
        candidate_words = set(re.findall(r"[a-z]+", candidate.lower()))
        if candidate_words & _NUMBER_SCALE_WORDS:
            return False
    return True


def _claim_number_span(target_text, candidates, claimed_spans):
    for candidate in sorted(candidates, key=len, reverse=True):
        for match in _candidate_pattern(candidate).finditer(target_text):
            span = match.span()
            if any(span[0] < used[1] and used[0] < span[1] for used in claimed_spans):
                continue
            if not _is_complete_number_span(target_text, span, candidate):
                continue
            claimed_spans.append(span)
            return True
    return False


TARGET_DIGIT_RE = re.compile(r"(?<![a-z0-9.])\d+(?:\.\d+)?(?![a-z0-9]|\.\d)")


def check_digits(src, tgt, strict=False):
    missing = []
    extras = []
    for line_number, source_line in enumerate(src, start=1):
        target_line = tgt[line_number - 1] if line_number <= len(tgt) else ""
        normalized_target = _normalized_number_target(target_line)
        claimed_spans = []
        for n, unit, approximate, date_unit, ordinal_context in source_content_nums(source_line):
            candidates = accepted_number_spellings(
                n, unit, approximate, date_unit, ordinal_context
            )
            if _claim_number_span(normalized_target, candidates, claimed_spans):
                continue
            label = (
                f"{'第' if ordinal_context else ''}{decimal_text(n)}"
                f"{'多' if approximate else ''}{unit}{date_unit}"
            )
            missing.append(f"L{line_number}:{label}")
        for match in TARGET_DIGIT_RE.finditer(normalized_target):
            span = match.span()
            if any(span[0] < used[1] and used[0] < span[1] for used in claimed_spans):
                continue
            extras.append(f"L{line_number}:{match.group(0)}")

    if missing:
        return FAIL, f"missing in target: {', '.join(missing)}", missing + extras
    if extras:
        # Chinese number words (for example 第五、五百、百问) are not yet
        # parsed comprehensively.  Their legitimate English renderings may use
        # Arabic digits, so treating every unclaimed target digit as a strict
        # failure would create false reds.  Keep this visible for human review
        # until the source-side parser can claim those forms reliably.
        return WARN, f"extra target digit(s); verify Chinese-number rendering: {', '.join(extras)}", extras
    return PASS, "all present with no extra target digits", []


def check_terminology(src, tgt, terms, strict=False):
    """A3: source term present -> some allowed rendering present in target.

    FAIL when no rendering is found at all; WARN when found but under-counted
    (inflections, line wraps, or a genuine drift the reviewer should verify).
    """
    if terms is None:
        return SKIP, "no term map provided", []
    if isinstance(terms, TermPolicy):
        allowed_terms = terms.allowed
        forbidden_terms = terms.forbidden
        needs_human = terms.needs_human
    else:
        allowed_terms = terms
        forbidden_terms = {}
        needs_human = ()
    if not allowed_terms:
        return SKIP, "term map is empty", []
    src_text = "\n".join(src)
    tgt_text = " ".join(tgt).lower()
    fails, warns, unresolved = [], [], []
    checked = 0
    for cn, renderings in sorted(allowed_terms.items()):
        n = src_text.count(cn)
        if n == 0:
            continue
        checked += 1
        forbidden_hits = [
            rendering
            for rendering in forbidden_terms.get(cn, [])
            if _rendering_pattern(rendering).search(tgt_text)
        ]
        if forbidden_hits:
            fails.append(f"{cn} uses forbidden rendering(s): {forbidden_hits}")
            continue
        if cn in needs_human:
            unresolved.append(f"{cn} requires a human term decision")
            continue
        hits = len(_rendering_spans(tgt_text, renderings))
        if hits == 0:
            fails.append(f"{cn} ({n}× in source) — none of {renderings} found in target")
        elif hits < n:
            coverage = hits / n
            message = (
                f"{cn} ({n}× in source, {hits}× rendered; "
                f"{coverage:.1%} coverage) — verify"
            )
            if strict and coverage < 0.99:
                fails.append(message)
            else:
                warns.append(message)
    if checked == 0:
        status, detail = SKIP, "term map has no terms present in source"
    elif fails:
        status, detail = FAIL, f"{checked} term(s) checked; " + "; ".join(fails)
    elif unresolved:
        status, detail = SKIP, f"{checked} term(s) checked; " + "; ".join(unresolved)
    elif warns:
        status, detail = WARN, f"{checked} term(s) checked; " + "; ".join(warns)
    else:
        status, detail = PASS, f"{checked} term(s) checked; all consistent"
    return status, detail, fails + unresolved + warns


def check_release_governance(project, findings, strict=False):
    """Verify auditable review and approval records, not semantic correctness."""
    if project is None:
        return SKIP, "no translation-project.yaml provided", []

    protected_release = (
        strict
        or project.level in {"public", "sensitive"}
        or project.genre == "scripture"
    )
    failures = []
    missing = []
    if strict and project.level not in {"public", "sensitive"}:
        failures.append(
            "strict publication mode requires release.level public or sensitive"
        )
    if protected_release and not project.independent_review_required:
        failures.append(
            "public/sensitive/scripture release must require independent review"
        )
    if protected_release and not project.named_approver_required:
        failures.append(
            "public/sensitive/scripture release must require named approval"
        )

    review_required = project.independent_review_required or protected_release
    approval_required = project.named_approver_required or protected_release
    if review_required:
        if not project.review_completed or not project.reviewer:
            missing.append("independent review completion and reviewer")
        elif project.reviewer.casefold() == project.translator.casefold():
            failures.append("independent reviewer must differ from the translator")
        if findings is None:
            missing.append("review-findings.jsonl")
    if approval_required:
        if not project.approved:
            failures.append("release approval is not approved")
        if not project.approver:
            missing.append("named approver")

    unresolved = []
    for finding in findings or []:
        if (
            finding["severity"] in {"critical", "major"}
            and finding["status"] in {"open", "deferred"}
        ):
            unresolved.append(
                f"{finding['finding_id']} ({finding['severity']}/{finding['status']})"
            )
    governance_warnings = []
    if unresolved:
        unresolved_detail = (
            "unresolved release-blocking findings: " + ", ".join(unresolved)
        )
        if strict or protected_release:
            failures.append(unresolved_detail)
        else:
            governance_warnings.append(unresolved_detail)

    if failures:
        return FAIL, "; ".join(failures + missing), failures + missing
    if missing:
        return SKIP, "missing governance record(s): " + ", ".join(missing), missing
    if governance_warnings:
        return WARN, "; ".join(governance_warnings), governance_warnings
    if review_required or approval_required:
        return PASS, "independent review and named approval records are complete", []
    return PASS, f"{project.level} release does not require independent approval", []


def check_bilingual(src, tgt, bilingual_path):
    if bilingual_path is None or not Path(bilingual_path).is_file():
        return SKIP, "no bilingual.dj present", []

    actual = Path(bilingual_path).read_text(encoding="utf-8").splitlines()
    if not any(not is_blank(line) for line in src):
        return FAIL, "cannot verify bilingual output for an empty source", []
    if not any(not is_blank(line) for line in tgt):
        return FAIL, "cannot verify bilingual output for an empty target", []
    if len(src) != len(tgt):
        return FAIL, "cannot verify bilingual output while line counts differ", []

    blank_mismatches = [
        i
        for i, (source_line, target_line) in enumerate(zip(src, tgt), start=1)
        if is_blank(source_line) != is_blank(target_line)
    ]
    if blank_mismatches:
        return (
            FAIL,
            "cannot verify bilingual output; blank lines differ at "
            + ", ".join(f"L{i}" for i in blank_mismatches[:10]),
            blank_mismatches,
        )

    # Intentionally implemented independently of gen-bilingual.py so a defect
    # in the generator cannot automatically make the freshness check green.
    expected = []
    for source_line, target_line in zip(src, tgt):
        if is_blank(source_line):
            expected.append("")
        else:
            expected.extend([source_line, target_line, ""])
    if actual == expected:
        return PASS, f"{len(actual)} lines match a regeneration", []
    return FAIL, f"stale: {Path(bilingual_path)} differs from source+target regeneration", []


def run_checks(
    src,
    tgt,
    bilingual=None,
    term_map=None,
    allow_cjk=(),
    project=None,
    review_findings=None,
    strict=False,
):
    return [
        ("non-empty inputs", *check_non_empty(src, tgt)),
        ("line-count parity", *check_line_count(src, tgt)),
        ("blank-line alignment", *check_blank_alignment(src, tgt)),
        ("paragraph parity", *check_paras(src, tgt)),
        ("heading parity", *check_headings(src, tgt)),
        ("emphasis preservation", *check_emphasis(src, tgt)),
        ("comment parity", *check_comments(src, tgt)),
        ("CJK leakage", *check_cjk(tgt, allow_cjk)),
        ("Chinese punctuation", *check_cn_punct(tgt, allow_cjk)),
        ("bold leakage", *check_bold(tgt)),
        ("digit fidelity", *check_digits(src, tgt, strict=strict)),
        ("terminology", *check_terminology(src, tgt, term_map, strict=strict)),
        ("bilingual freshness", *check_bilingual(src, tgt, bilingual)),
        (
            "release governance",
            *check_release_governance(project, review_findings, strict=strict),
        ),
    ]


def main():
    ap = argparse.ArgumentParser(description="Deterministic translation checks")
    ap.add_argument("paths", nargs="+", help="book dir, or source.dj target.dj")
    ap.add_argument("--bilingual", default=None, help="bilingual.dj to verify")
    ap.add_argument("--term-map", default=None, help="term map file")
    ap.add_argument("--project", default=None,
                    help="translation-project.yaml release metadata")
    ap.add_argument("--review-findings", default=None,
                    help="review-findings.jsonl to verify")
    ap.add_argument("--allow-cjk", default="", help="comma-separated CJK whitelist")
    ap.add_argument("--strict", action="store_true",
                    help=(
                        "publication mode: require release governance and fail "
                        "if any check is skipped"
                    ))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--output", type=Path,
                    help="atomically write JSON report (requires --json)")
    args = ap.parse_args()

    if args.output is not None and not args.json:
        ap.error("--output requires --json")

    if args.bilingual is not None and not Path(args.bilingual).is_file():
        ap.error(f"explicit bilingual file does not exist: {args.bilingual}")
    if args.term_map is not None and not Path(args.term_map).is_file():
        ap.error(f"explicit term map does not exist: {args.term_map}")
    if args.project is not None and not Path(args.project).is_file():
        ap.error(f"explicit project file does not exist: {args.project}")
    if args.review_findings is not None and not Path(args.review_findings).is_file():
        ap.error(f"explicit review findings do not exist: {args.review_findings}")

    if len(args.paths) == 1 and Path(args.paths[0]).is_dir():
        d = Path(args.paths[0])
        src, tgt = d / "source.dj", d / "target.dj"
        bilingual = args.bilingual or d / "bilingual.dj"
        if args.term_map:
            term_map = Path(args.term_map)
        else:
            term_map = next(
                (candidate for candidate in (d / "term-map.yaml", d / "term-map.md")
                 if candidate.is_file()),
                None,
            )
        project_path = (
            Path(args.project)
            if args.project
            else d / "translation-project.yaml"
            if (d / "translation-project.yaml").is_file()
            else None
        )
        findings_path = (
            Path(args.review_findings)
            if args.review_findings
            else d / "review-findings.jsonl"
            if (d / "review-findings.jsonl").is_file()
            else None
        )
        label = str(d)
    elif len(args.paths) == 2:
        src, tgt = Path(args.paths[0]), Path(args.paths[1])
        bilingual = Path(args.bilingual) if args.bilingual else None
        term_map = Path(args.term_map) if args.term_map else None
        project_path = Path(args.project) if args.project else None
        findings_path = Path(args.review_findings) if args.review_findings else None
        label = f"{src} -> {tgt}"
    else:
        ap.error("pass a book directory, or source.dj target.dj")

    if not src.is_file() or not tgt.is_file():
        ap.error(f"missing source or target: {src} / {tgt}")
    protected_paths = [src, tgt]
    if bilingual is not None:
        protected_paths.append(Path(bilingual))
    if term_map is not None:
        protected_paths.append(Path(term_map))
    if project_path is not None:
        protected_paths.append(Path(project_path))
    if findings_path is not None:
        protected_paths.append(Path(findings_path))
    if args.output is not None and any(
        paths_refer_to_same_file(args.output, protected)
        for protected in protected_paths
    ):
        ap.error(
            "--output must differ from source, target, bilingual, term map, "
            "project, and review findings"
        )

    src_lines = read_lines(src)
    tgt_lines = read_lines(tgt)
    allow = [t.strip() for t in args.allow_cjk.split(",") if t.strip()]
    terms = None
    if term_map and Path(term_map).is_file():
        term_map_path = Path(term_map)
        term_map_text = term_map_path.read_text(encoding="utf-8")
        if term_map_path.suffix.lower() in {".yaml", ".yml"}:
            try:
                terms = term_policy_from_yaml_json(term_map_text)
            except ValueError as exc:
                ap.error(str(exc))
        else:
            terms = term_map_from_markdown(term_map_text)

    project = None
    if project_path is not None:
        try:
            project = project_policy_from_yaml_json(
                Path(project_path).read_text(encoding="utf-8")
            )
        except ValueError as exc:
            ap.error(str(exc))
    findings = None
    if findings_path is not None:
        try:
            findings = review_findings_from_jsonl(
                Path(findings_path).read_text(encoding="utf-8")
            )
        except ValueError as exc:
            ap.error(str(exc))

    checks = run_checks(
        src_lines,
        tgt_lines,
        bilingual,
        terms,
        allow,
        project,
        findings,
        args.strict,
    )
    failed = [name for name, status, *_ in checks if status == FAIL]
    warned = [name for name, status, *_ in checks if status == WARN]
    skipped = [name for name, status, *_ in checks if status == SKIP]
    blocked = bool(failed or (args.strict and skipped))
    mode = "strict" if args.strict else "draft"
    if blocked:
        overall = FAIL
    elif warned or skipped:
        overall = WARN
    else:
        overall = PASS

    if args.json:
        report = {
            "target": label,
            "mode": mode,
            "overall": overall,
            "passed": [c[0] for c in checks if c[1] == PASS],
            "warned": warned,
            "skipped": skipped,
            "failed": failed,
            "strict": args.strict,
            "ok": not blocked,
            "approval": {
                "approved": project.approved if project else False,
                "approver": project.approver if project else "",
                "note": project.approval_note if project else "",
            },
            "details": {c[0]: {"status": c[1], "detail": c[2]} for c in checks},
        }
        rendered_report = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output is None:
            sys.stdout.write(rendered_report)
        else:
            try:
                atomic_write_report(args.output, rendered_report)
            except OSError as exc:
                print(f"failed to write QA report atomically: {exc}", file=sys.stderr)
                sys.exit(1)
    else:
        print(f"check-translation.py — {label}\n")
        for name, status, detail, *_ in checks:
            print(f"[{status:4}] {name}: {detail}")
        summary = "ALL CHECKS PASSED"
        if skipped or warned:
            qualifiers = []
            if warned:
                qualifiers.append(f"warnings: {', '.join(warned)}")
            if skipped:
                qualifiers.append(f"skips: {', '.join(skipped)}")
            summary = "PASSED with " + "; ".join(qualifiers)
        if args.strict and skipped and not failed:
            summary = f"STRICT FAILED: skipped checks: {', '.join(skipped)}"
        if failed:
            summary = f"FAILED: {', '.join(failed)}"
        print(f"\n{summary}")

    sys.exit(1 if blocked else 0)


if __name__ == "__main__":
    main()
