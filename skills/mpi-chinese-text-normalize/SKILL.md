---
name: chinese-text-normalize
description: Normalize Chinese markdown files — remove extraneous mid-sentence line breaks from fixed-width exports while preserving TOC structures, section headers, and intentional paragraph breaks.
---

When Chinese text has hard line breaks at a fixed width (~20-25 chars) — common in PDF exports, OCR output, or poorly-converted documents — use this skill to join them into flowing paragraphs.

## Triggers

- User asks to "fix line breaks" or "remove extraneous breaks" in Chinese text
- Chinese markdown files with lines that break mid-sentence at a consistent short width
- Files with vertical TOC (single-char-per-line 【】 sections) that need preservation

## Approach

Run `scripts/normalize_breaks.py <directory>` — it processes all .md files in the directory.

The script handles three file patterns:

1. **Vertical TOC + fixed-width body** — Preserves the decorative single-char TOC section, joins body paragraphs, strips inline page numbers (standalone digits like "3", "4")
2. **Outline TOC with stray breaks** — Preserves numbered outline items (一、...、1、...、...... separators), joins body paragraphs
3. **Already in paragraph format** — No change (safe to run idempotently)

### What it preserves

- Vertical TOC: single CJK/punctuation lines with 【】 brackets
- Section headers: 【...】、## ...、# ...、一、二、三、...、1、2、3、...
- Outline TOC entries: short numbered lines, lines with ...... separators
- Blank lines as paragraph separators

### What it removes

- Mid-sentence hard line breaks (joins consecutive CJK body lines)
- Inline page numbers (standalone 1-2 digit lines)
- Trailing blank lines

## Beyond the script: bold fragments, conjoined paragraphs, encoding

The script handles simple fixed-width body text. Some PDF→markdown conversions produce more complex artifacts that need manual multi-pass Python scripts via `execute_code`:

### Bold marker fragmentation

`**...text...**` blocks split across blank lines with stray `**` at fragment boundaries:

```
**第三条 特色——依据五大要素，构建次第修学。营造良好氛围，提供有效**

引导。
```

**Fix**: Join fragments, remove stray `**` from join point, add closing `**` to final result. See `references/bold-fragments.md` for full pattern catalog and multi-pass workflow.

**Critical pitfall**: Do NOT join lines where BOTH the first and second line are complete bold blocks (start+end with `**`). These are separate entries, not fragments:
```
**第一条 ...之道。**    ← complete bold item
                        ← blank line
**第二条 ...合一。**    ← complete bold item (DON'T JOIN)
```

### Conjoined paragraphs

Separate paragraphs/sections merged into one line — opposite problem to the script. Common in song lyrics, dense instructional sections. Requires semantic splitting. See `references/bold-fragments.md`.

### Encoding artifacts

`川` (U+5DDD) replacing `"` (curly quote) — search-and-replace: `" 道理川` → `"道理"`, `" 自己的川` → `"自己的"`.

### Multi-pass approach

1. **Pass 1**: Join word fragments split by blank lines (conservative — only when current line doesn't end with `。！？` or is NOT a complete bold block)
2. **Pass 2**: Split obviously conjoined paragraphs (manual string replacements for known patterns)
3. **Pass 3**: Fix stray bold markers, encoding artifacts, stray page numbers
4. Verify after each pass; revert with `git checkout` if over-aggressive

### Heuristic pitfalls

- **Short-line join** (< 15 chars): Over-joins section headers with body, Q&A pairs (`正念是什么？\n\n就是...`). Only use for clear word-fragment continuations.
- **Bold-end join**: Lines ending with `**` are ambiguous — either broken bold fragment or complete bold item. Check if the content before `**` forms a complete sentence (ends with `。`).

## Pitfalls

- **TOC detection boundaries**: The vertical TOC end is detected by finding the first line with 3+ CJK characters. If a page number like "2" sits between TOC and body, it lands in the TOC section — harmless but visible.
- **Section headers without markers**: Plain-text section titles (e.g., "生命可以被设计的依据") without 【】 or number prefixes won't be detected as headers. They'll form standalone paragraphs separated by blank lines, which is fine as long as blank lines exist around them.
- **Wiki-link TOC files**: Files like a course index with [[wiki links]] are NOT prose and should be excluded. The script has no special handling — skip those files manually or restore from git.
- **Not for mixed CJK/English prose**: The script treats any line with CJK characters as body text. Mixed-language documents may need manual review.
