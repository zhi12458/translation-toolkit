# Markdown to Djot Conversion

When source material arrives as `.docx.md` (pandoc-converted from docx), convert to `.dj` for translation workflows.

## Splitting combined articles

If a single markdown file contains multiple articles (common when docx has two talks in one file), split at the article boundary before converting. Use `sed` by line number:

```bash
sed -n '1,218p' combined.md > a1.md
sed -n '220,282p' combined.md > a2.md
```

## TOC stripping

Pandoc docx→md produces a markdown TOC with tab-separated page numbers:

```markdown
[一、对佛教的感悟\t1](#一、对佛教的感悟)
[二、佛教与人类文明\t5](#二、佛教与人类文明)
```

Strip before conversion:

```bash
sed -i '/^\[.*\t.*\](#.*)$/d' input.md
```

Or in Python: skip lines matching `line.startswith("[") and "\t" in line and "](#" in line`.

## Heading anchor cleanup

Pandoc's docx→md conversion adds `{#heading-id}` anchors to every heading:

```markdown
## 1．安宁疗护 {#1．安宁疗护}
```

These must be stripped before markdown→djot conversion, otherwise pandoc's djot writer leaves stray `{#...}` lines in the output:

```bash
sed 's/ {#[^}]*}//g' input.md > clean.md
```

## Conversion command

```bash
pandoc clean.md -f markdown -t djot --wrap=none -o output.dj
```

`--wrap=none` prevents reflow of long paragraphs.

## Post-conversion cleanup

Pandoc may still leave stray `{#...}` lines in djot output. Remove them:

```bash
sed -i '/^{#.*}$/d' output.dj
```

## Pandoc artifacts

- Unicode `——` (U+2014 × 2) → `------` in djot (two em dashes, `---` each). This is correct djot syntax.
- Markdown hard line breaks (trailing `  `) → `\\\n` in djot. Preserves original paragraph structure.
- Pandoc normalizes heading IDs (strips `、` and other punctuation). Ignore; the stray-line cleanup handles it.
