# Proofreading: Manuscript vs Typeset

AGENTS.md defines two workflows: Translation (A) and Proofread (B).
The workflows below are Proofread mode — English comes from an existing
manuscript and is authoritative. Only flag mechanical/manuscript-level issues.

## Two extraction workflows

### A. Bilingual from DOCX (standard)

When the DOCX manuscript has both Chinese and English in 1:1 paragraph
correspondence, generate `bilingual.dj` directly from the DOCX:

1. `pandoc docx → plain text`
2. Extract Chinese-English pairs from body
3. Apply fixes: italicize Sanskrit on first occurrence, fix `N.Letter` → `N. Letter` spacing
4. Write bilingual.dj
The DOCX English is the authoritative target text. No PDF needed.

**Extraction approach**: write a custom extraction script. The standard
`toolkit/scripts/gen-bilingual.py` expects separate `source.dj` and `target.dj` files;
for DOCX→bilingual extraction, adapt its pattern-matching logic to read from the
pandoc plain-text output instead. For articles where the body has strict
CN→EN→CN→EN alternation, the simple extraction (CN line, blank, EN line, blank)
works directly.

### A2. Bilingual from `.docx.md` (pandoc markdown output)

When working with an already-converted `.docx.md` file (pandoc markdown, not plain
text), use the techniques in `references/docx-md-extraction.md`. Key differences
from plain-text extraction: merged CN+EN on heading lines, `{#anchor}` and
`[text](#link)` artifacts, TOC pairing guards.

### B. Bilingual from PDF (when PDF is the typeset target)
sections that order CN content before EN content (CN heading → CN body → EN heading →
EN body), the simple alternation fails. Use block-based extraction instead:

1. Tag each non-blank line as CN or EN (via `has_cjk()`)
2. Join page-break split paragraphs: merge consecutive same-language paragraphs
   only when the first is long (>30 chars), doesn't end with CJK/ASCII terminal
   punctuation (`[。！？：）.?!]$`), and isn't heading-like (starts with
   `^[\dIVX]+[\.\s]` and <60 chars)
3. Group consecutive same-language items into blocks
4. Walk blocks: for each CN block, pair with the next EN block via `zip()`.
   `min(len(cn), len(en))` handles translator-introduced paragraph splits.

**Page-break splits in pandoc plain-text output**: the DOCX→plain conversion
sometimes splits a Chinese paragraph mid-sentence (e.g. `白居` + `易、苏轼…`).
These appear as two consecutive CN lines separated by a blank. The join heuristic
above catches these reliably. For EN text, page-break splits are rare; the heading
detection (`^[\dIVX]+[\.\s]`, <60 chars) prevents false merges of EN headings
with following EN body paragraphs.
The DOCX English is the authoritative target text. No PDF needed.

### B. Bilingual from PDF (when PDF is the typeset target)

When the PDF English is the typeset "final" version and should be the target:

1. Extract DOCX Chinese paragraphs (source)
2. Extract PDF body text via `pdftotext -layout`
3. Clean PDF: remove slug lines, headers, page numbers, join hyphenation breaks
4. Match DOCX English paragraphs against PDF body to find positions
5. Segment PDF body at matched positions
6. Write bilingual.dj with Chinese source + PDF English target

**Pitfalls in PDF extraction:**
- Consecutive hyphenation breaks (e.g. `thou-` + `sand...al-` + `leviate`) — the join
  loop must be recursive: after joining pair N, check if result still ends with `-`
  and join with line N+2
- Lines with leading whitespace: use `lstrip()` before checking `n[0].islower()`
- Drop-cap artifacts: `L iving` → `Living`
- Trailing section numbers: `...viewpoints. 1)` — the ` 1)` is a PDF section marker
  bleeding into the previous paragraph

### C. Edit suggestions (edit-suggestions.dj)

After generating bilingual.dj, scan for issues and write `edit-suggestions.dj`:

**Format**: follow the original document's section/chapter layout. Group suggestions
under the chapter headings where the issues occur. Use diff-style `-/+` notation.

**What to flag:**
- Garbled Chinese text (merged duplicate edits in source DOCX)
- Repeated words (`the The`)
- Chapter numbering mismatches (e.g. `九` ↔ `VIII`)
- Translator notes in headings (`（某某翻，某某审）`)
- Missing quotes around dialogue/speech

## Common source DOCX issues

- Translator notes in Chinese headings: `（某某翻，某某审）` — delete for publication
- Merged duplicate edits: cut-paste errors where old+new text appear together
- `N.Letter` without space: `2.How` → `2. How`
- `the The` double article
- **Numbering mismatches**: CN and EN headings sometimes disagree (e.g. CN `3．` vs EN `2.`).
  The TOC usually has the correct number — flag the body heading for correction.
- **Doubled names**: `岳麓书院岳麓书院` — cut-paste artifacts in Chinese body text.
- **EN paragraph splits without CN counterpart**: translator sometimes renders one CN
  paragraph as two EN paragraphs. The block-based extractor drops the extra EN paragraph
  (as `min(len_cn, len_en)`). Flag in edit-suggestions so it can be manually merged or
  the CN paragraph can be split.

## Sanskrit italicization

On first occurrence in body text, wrap with `*term*`. Track seen terms across
the full body. Terms: bodhisattva, bodhicitta, samsara, Dharma, karma, nirvana,
Sangha, sutra, Mahayana, Sravaka, Vinaya, Lamrim, Ksitigarbha, Samantabhadra,
Chan, Arhatship, Theravada.

## Proofread scope boundary

When proofreading a DOCX manuscript:
- **DO flag**: typos, double words, double punctuation, numbering mismatches,
  garbled text, translator notes, duplicate names, capitalization errors.
- **Do NOT flag**: em-dash formatting (`—` vs `---`), terminology choices,
  translation style, calques, word order. The manuscript English is authoritative.
- **Do NOT apply fixes** — write `edit-suggestions.dj` only.
- If the user asks for translation review separately, write findings to
  `translation-findings.dj`.
