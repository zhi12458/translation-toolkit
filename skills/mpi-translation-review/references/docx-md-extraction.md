# Extracting `.docx.md` to `source.dj` + `bilingual.dj`

When the input is a `.docx.md` file (already pandoc markdown, not plain text), the
extraction differs from the standard DOCX→plain workflow. The markdown preserves
formatting artifacts that need specific handling.

## CN/EN boundary detection in merged lines

Pandoc markdown often merges CN and EN text on heading lines where the DOCX had
multiple runs in the same paragraph:

```
# **三、重视文化教育，重塑人生价值** Prioritize Cultural Education; Reshape Life Values {#三、...}
```

The boundary regex must account for whitespace on BOTH sides of `**` markers:

```python
# WRONG: \** then \s* — fails when there's space BEFORE * (值 *Realizing)
r'[\u4e00-\u9fff](?:\*{0,2})\s*([A-Za-z])'

# WRONG: \s* then \** — fails when there's space AFTER ** (值** Prioritize)
r'[\u4e00-\u9fff]\s*\**([A-Za-z])'

# CORRECT: whitespace on both sides of optional *
r'[\u4e00-\u9fff]\s*\**\s*([A-Za-z])'
```

Include CJK punctuation ranges in the character class:
`[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]`

## Anchor stripping

Strip BOTH `{#anchor}` (pandoc heading anchors) AND `[text](#link)` (markdown TOC links)
before further processing:

```python
def strip_anchors(s):
    s = re.sub(r'\{#[^}]*\}', '', s)           # {#anchor}
    s = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', s)  # [text](#link) → text
    return s
```

## TOC handling — two critical guards

### Guard 1: Don't pair TOC CN entries with following EN lines

TOC entries often look like CN-heading-followed-by-EN (the standard pair pattern),
but the following EN is actually the next TOC entry or heading:

```
[一、营造禅意氛围，优化工作环境\t1](#anchor)
[二、重视慈善关爱...]
...
1、Create a Chan(Zen) Atmosphere; Optimize Your Environment
2、Focus on Compassion and Care; Build Good Relationships
```

If the last CN TOC entry is followed by a blank line then the first EN TOC entry,
the "CN → blank → EN" heading pattern will consume the first EN TOC entry.
Guard against this:

```python
def is_toc_line(line, cn_raw):
    if re.search(r'\[.*\]\(.*\)', line):  # markdown link
        return True
    if re.search(r'\t\d+', cn_raw):       # tab + page number
        return True
    return False
```

Skip the CN→EN and CN→blank→EN patterns when `is_toc_line()` returns True.
These CN TOC entries should stay unpaired (en='') and get their EN from the
separate EN TOC list.

### Guard 2: Pair TOC EN entries forward, not backward

EN TOC entries appear as standalone non-CJK lines. They must be paired with
the FIRST unpaired CN (not the last):

```python
# CORRECT: forward iteration
for j in range(len(pairs)):
    if not pairs[j][1] and has_cjk(pairs[j][0]):
        pairs[j] = (pairs[j][0], en)
        break

# WRONG: reverse iteration (pairs last-first, shifting everything)
for j in range(len(pairs)-1, -1, -1):
    ...
```

## Orphaned trailing `*` from italic splits

When a line has italicized EN text (`*Realizing Ultimate Value*`) and the split
point is at the `R` (after the opening `*` is consumed by the CN cleanup), the
EN text retains a trailing `*`: `Realizing Ultimate Value*`. Strip it:

```python
def clean_en(s):
    s = re.sub(r'^\d+[、,.]\s*', '', s)
    s = re.sub(r'\*+$', '', s)                # orphaned italic close
    return s.strip()
```

## `clean_cn` — operation order matters

Strip leading numbers BEFORE heading markers. A line like `1. # **营造禅意...`
starts with a digit, so `^#+\s*\**` won't match until the number is gone:

```python
def clean_cn(s):
    s = re.sub(r'^\d+\.\s*', '', s)           # leading number FIRST
    s = re.sub(r'^#+\s*\**', '', s)           # then heading markers
    s = re.sub(r'\**\s*$', '', s)             # trailing **
    s = re.sub(r'\t\d+$', '', s)              # trailing page number
    return s.strip()
```

## Full extraction recipe

1. Read `.docx.md` text
2. For each line: strip anchors, detect CJK/EN
3. CJK lines: try `split_cnen()` first (merged CN+EN). If that gives EN, use it.
   Otherwise look ahead for EN on next line or next+blank — but SKIP if TOC-like.
4. EN-only lines: pair forward with first unpaired CN.
5. Clean: strip heading markers, leading numbers, trailing page numbers.
6. Write `source.dj` (CN only) and `bilingual.dj` with proper markdown structure.

## bilingual.dj output format

Must follow the project convention (see reference bilingual.dj in any completed article):

```
# CN Title
# EN Title

---CN Subtitle
---EN Subtitle

CN Author
EN Author

- CN TOC item 1
- CN TOC item 2
...

- EN TOC item 1
- EN TOC item 2
...

CN body paragraph
EN body paragraph

CN section heading            ← plain text, no # prefix
EN section heading

...

CN sub-heading                ← plain text, e.g. "1. 创造精神财富"
EN sub-heading
```

- Title: `# ` prefix on both CN and EN
- Subtitle: `---` prefix (3 dashes, no space after)
- Author: plain text, one pair
- TOC: `- ` bullet, CN block then EN block (not interleaved), blank line between blocks
- Body headings: plain text, no `#` or `##` markers. Hierarchy conveyed by numbering:
  `一、二、三、` for major sections, `1. 2. 3.` for sub-sections
- Body paragraphs: interleaved (CN line, EN line, blank)
- `source.dj` uses `# Title`, `---subtitle`, `## section headings` — different from bilingual.dj which uses plain body headings
