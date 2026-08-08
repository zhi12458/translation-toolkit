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
  PASS — clean.

Checks:
  1. line-count parity      — source.dj and target.dj must have equal lines
  2. paragraph parity       — equal number of blank-separated blocks
  3. heading parity         — equal # of lines starting with each heading level
  4. emphasis preservation  — every *...* in a source line survives on the
                              same-index target line (D5). Target may ADD
                              italics (titles, Sanskrit) — that is fine.
  5. comment parity         — equal {% ... %} blocks (D5)
  6. CJK leakage           — no Chinese characters in target (whitelistable)
  7. Chinese punctuation   — no strictly-Chinese punctuation in target
                             (，。、；：？！《》【】（）). Em dash, curly
                             quotes, middot are legal English — not flagged.
  8. bold leakage          — no Markdown ** in target (D5)
  9. digit fidelity        — every arabic number in source appears in target
  10. terminology          — source terms from a term map must appear in target
                             with an allowed English rendering (A3 / terms DB).
                             FAIL: term present in source, none of its
                             renderings found in target. WARN: renderings
                             found but fewer times than the source term.
  11. bilingual freshness  — bilingual.dj, if present, equals a regeneration
                             from source+target

Usage:
    check-translation.py <book_dir>
        Uses <book_dir>/source.dj and <book_dir>/target.dj; auto-detects
        bilingual.dj and term-map.md in the same directory.
    check-translation.py <source.dj> <target.dj> [--bilingual FILE]
        Explicit files.

Options:
    --term-map FILE    Term map (default: <book_dir>/term-map.md if present).
                       Accepted formats:
                         - markdown table rows:  | 菩提心 | bodhicitta |
                         - plain lines:           CN<TAB>EN  or  CN|EN1|EN2
                       Multiple Chinese terms separated by "/" or "、" share
                       one English side; English renderings separated by "/"
                       are alternatives, any of which satisfies the check.
    --allow-cjk LIST   Comma-separated CJK strings permitted in target
                       (e.g. quoted book titles like 《心经》).
    --json             Emit machine-readable JSON results.

Exit code: 0 when no check FAILs (WARNs allowed), 1 otherwise.
"""
import argparse
import json
import re
import sys
from pathlib import Path

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
# Strictly-Chinese punctuation only. Em dash (—), curly quotes (“” ‘’),
# middot (·), and ellipsis are legitimate in English prose.
CN_PUNCT_RE = re.compile(r"[，。、；：？！《》【】（）]")
EMPHASIS_RE = re.compile(r"\*[^*\n]+\*")
COMMENT_RE = re.compile(r"\{%[\s\S]*?%\}")
HEADING_RE = re.compile(r"^(#{1,6})(?:\s|$)")
BOLD_RE = re.compile(r"\*\*")
DIGIT_RE = re.compile(r"\d+")

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


def read_lines(path):
    return Path(path).read_text(encoding="utf-8").splitlines()


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


def heading_counts(lines):
    counts = {i: 0 for i in range(1, 7)}
    for line in lines:
        m = HEADING_RE.match(line)
        if m:
            counts[len(m.group(1))] += 1
    return counts


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


def check_line_count(src, tgt):
    ok = len(src) == len(tgt)
    return (PASS if ok else FAIL,
            f"source={len(src)} target={len(tgt)}", [])


def check_paras(src, tgt):
    s, t = count_paras(src), count_paras(tgt)
    return (PASS if s == t else FAIL,
            f"source={s} target={t}", [])


def check_headings(src, tgt):
    s, t = heading_counts(src), heading_counts(tgt)
    diffs = [f"H{i}: {s[i]} vs {t[i]}" for i in range(1, 7) if s[i] != t[i]]
    return (PASS if not diffs else FAIL,
            "; ".join(diffs) if diffs else "all levels match", diffs)


def check_emphasis(src, tgt):
    """D5 preservation: source emphasis must survive on the same line.

    Target may add emphasis for titles/Sanskrit, so counts need not match.
    """
    missing = []
    for i, (s, t) in enumerate(zip(src, tgt), 1):
        if EMPHASIS_RE.search(s) and not EMPHASIS_RE.search(t):
            missing.append((i, s, t))
    return (PASS if not missing else FAIL,
            "all source emphasis preserved"
            if not missing else
            f"{len(missing)} source line(s) lost emphasis: "
            + ", ".join(f"S{i}" for i, _, _ in missing[:10]),
            missing)


def check_comments(src, tgt):
    s, t = len(COMMENT_RE.findall("\n".join(src))), len(COMMENT_RE.findall("\n".join(tgt)))
    return (PASS if s == t else FAIL,
            f"source={s} target={t}", [])


ANCHOR_RE = re.compile(r"\{#[^{}]*\}|\(\s*#?[^{}\n]*\)")
LINK_TGT_RE = re.compile(r"\[\d+\]\(\s*#")


def strip_structural(text):
    """Remove djot anchors {#...}, link destinations (...), and image paths —
    structural markup that may legitimately contain Chinese."""
    return ANCHOR_RE.sub("", text)


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


def check_cn_punct(tgt):
    bad = []
    for i, line in enumerate(tgt, 1):
        if CN_PUNCT_RE.search(line):
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


_ONES = ["", "one", "two", "three", "four", "five", "six", "seven", "eight",
         "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
         "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
         "eighty", "ninety"]


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


def accepted_number_spellings(n, unit):
    """All English spellings that legitimately render source number n.

    unit: "" (plain), "万" (×10^4), or "亿" (×10^8). The target may keep the
    digits ("1,200"), spell them ("twelve hundred"), or scale the unit
    ("13 million" for 1300万, "18 billion" for 180亿).
    """
    cands = {str(n), number_to_words(n)}
    if 100 <= n < 10000 and n % 100 == 0:  # "twelve hundred"
        cands.add(f"{n // 100} hundred")
        cands.add(number_to_words(n // 100) + " hundred")
    value = n * (10 ** 4 if unit == "万" else 10 ** 8 if unit == "亿" else 1)
    if value != n:
        cands.add(str(value))
        cands.add(number_to_words(value))
        for divisor, suffix in ((10 ** 9, "billion"), (10 ** 6, "million"),
                                (10 ** 3, "thousand")):
            if value % divisor == 0 and value // divisor > 0:
                cands.add(f"{value // divisor} {suffix}")
                cands.add(number_to_words(value // divisor) + " " + suffix)
    return cands


def source_content_nums(src_text):
    """(number, unit) pairs from the source, excluding TOC page numbers
    ([N](#...)) that the project convention intentionally drops."""
    stripped = LINK_TGT_RE.sub("", src_text)
    out = []
    for m in re.finditer(r"\d+(?:\s*(?:多\s*)?[万亿])?", stripped):
        tok = m.group(0)
        unit = tok[-1] if tok[-1] in "万亿" else ""
        out.append((int(re.sub(r"\D", "", tok)), unit))
    return out


def check_digits(src, tgt):
    src_nums = source_content_nums("\n".join(src))
    tgt_text = " ".join(tgt).lower().replace(",", "")
    missing = []
    for n, unit in src_nums:
        if any(s.lower() in tgt_text
               for s in accepted_number_spellings(n, unit)):
            continue
        missing.append(str(n) + unit)
    return (PASS if not missing else FAIL,
            "all present" if not missing else f"missing in target: {', '.join(missing)}",
            missing)


def check_terminology(src, tgt, terms):
    """A3: source term present -> some allowed rendering present in target.

    FAIL when no rendering is found at all; WARN when found but under-counted
    (inflections, line wraps, or a genuine drift the reviewer should verify).
    """
    if not terms:
        return PASS, "no term map provided; skipped", []
    src_text = "\n".join(src)
    tgt_text = " ".join(tgt).lower()
    fails, warns = [], []
    checked = 0
    for cn, renderings in sorted(terms.items()):
        n = src_text.count(cn)
        if n == 0:
            continue
        checked += 1
        hits = sum(tgt_text.count(r.lower()) for r in renderings)
        if hits == 0:
            fails.append(f"{cn} ({n}× in source) — none of {renderings} found in target")
        elif hits < n:
            warns.append(f"{cn} ({n}× in source, {hits}× rendered) — verify")
    if fails:
        status, detail = FAIL, f"{checked} term(s) checked; " + "; ".join(fails)
    elif warns:
        status, detail = WARN, f"{checked} term(s) checked; " + "; ".join(warns)
    else:
        status, detail = PASS, f"{checked} term(s) checked; all consistent"
    return status, detail, fails + warns


def check_bilingual(src, tgt, bilingual_path):
    if bilingual_path is None or not Path(bilingual_path).exists():
        return PASS, "no bilingual.dj present; skipped", []
    actual = Path(bilingual_path).read_text(encoding="utf-8").splitlines()
    expected = []
    for s, t in zip(src, tgt):
        if s == "":
            expected.append("")
        else:
            expected.extend([s, t, ""])
    if expected and expected[-1] != "":
        expected.append("")
    if actual == expected:
        return PASS, f"{len(actual)} lines match a regeneration", []
    return FAIL, f"stale: {Path(bilingual_path)} differs from source+target regeneration", []


def run_checks(src, tgt, bilingual=None, term_map=None, allow_cjk=()):
    return [
        ("line-count parity", *check_line_count(src, tgt)),
        ("paragraph parity", *check_paras(src, tgt)),
        ("heading parity", *check_headings(src, tgt)),
        ("emphasis preservation", *check_emphasis(src, tgt)),
        ("comment parity", *check_comments(src, tgt)),
        ("CJK leakage", *check_cjk(tgt, allow_cjk)),
        ("Chinese punctuation", *check_cn_punct(tgt)),
        ("bold leakage", *check_bold(tgt)),
        ("digit fidelity", *check_digits(src, tgt)),
        ("terminology", *check_terminology(src, tgt, term_map)),
        ("bilingual freshness", *check_bilingual(src, tgt, bilingual)),
    ]


def main():
    ap = argparse.ArgumentParser(description="Deterministic translation checks")
    ap.add_argument("paths", nargs="+", help="book dir, or source.dj target.dj")
    ap.add_argument("--bilingual", default=None, help="bilingual.dj to verify")
    ap.add_argument("--term-map", default=None, help="term map file")
    ap.add_argument("--allow-cjk", default="", help="comma-separated CJK whitelist")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if len(args.paths) == 1 and Path(args.paths[0]).is_dir():
        d = Path(args.paths[0])
        src, tgt = d / "source.dj", d / "target.dj"
        bilingual = args.bilingual or d / "bilingual.dj"
        term_map = args.term_map or d / "term-map.md"
        label = str(d)
    elif len(args.paths) == 2:
        src, tgt = Path(args.paths[0]), Path(args.paths[1])
        bilingual = Path(args.bilingual) if args.bilingual else None
        term_map = Path(args.term_map) if args.term_map else None
        label = f"{src} -> {tgt}"
    else:
        ap.error("pass a book directory, or source.dj target.dj")

    if not src.exists() or not tgt.exists():
        ap.error(f"missing source or target: {src} / {tgt}")

    src_lines = read_lines(src)
    tgt_lines = read_lines(tgt)
    allow = [t for t in args.allow_cjk.split(",") if t.strip()]
    terms = {}
    if term_map and Path(term_map).exists():
        terms = term_map_from_markdown(Path(term_map).read_text(encoding="utf-8"))

    checks = run_checks(src_lines, tgt_lines, bilingual, terms, allow)
    failed = [name for name, status, *_ in checks if status == FAIL]
    warned = [name for name, status, *_ in checks if status == WARN]

    if args.json:
        print(json.dumps({
            "target": label,
            "passed": [c[0] for c in checks if c[1] == PASS],
            "warned": warned,
            "failed": failed,
            "details": {c[0]: {"status": c[1], "detail": c[2]} for c in checks},
        }, ensure_ascii=False, indent=2))
    else:
        print(f"check-translation.py — {label}\n")
        for name, status, detail, *_ in checks:
            print(f"[{status:4}] {name}: {detail}")
        summary = "ALL CHECKS PASSED"
        if warned:
            summary = f"PASSED with warnings: {', '.join(warned)}"
        if failed:
            summary = f"FAILED: {', '.join(failed)}"
        print(f"\n{summary}")

    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    main()
