# PDF-vs-DOCX Proofread Workflow

Compare typeset PDF against the authoritative DOCX manuscript. Catch
discrepancies introduced during typesetting: dropped words, terminology
drift, repositioned phrases, extra content.

## Pattern

The existing `scripts/proofread-pdf.py` is article-specific (hardcoded to
佛教徒的人生态度). For each new article, create a similarly-shaped script:

```
translate-files/<article>/<name>-<hash>.py
```

Hash = `md5('translate-files/<article>')[:6]`

## Script Structure

1. Convert DOCX to plain text: `pandoc docx -f docx -t plain --wrap=none`
2. Convert PDF to plain text: `pdftotext -layout pdf`
3. Extract body from DOCX — find body start marker (first sentence of body)
4. Extract body from PDF — find same marker, filter out:
   - Page slugs: `文章名.*indd \d+`
   - Headers: `The Mindful Peace Academy Collection`, article title
   - Page numbers: `^\d{1,3}$`
   - Section numerals: `^(I|II|III|IV)$`
   - Section name lines: `^(Three Basic Elements|...|Conclusion)$`
5. Join hyphenated line breaks (`word-` at end + lowercase continuation)
6. Fix PDF artifacts: `L iving` → `Living`, `T\s+he` → `The`
7. Normalize both (collapse whitespace, unify quotes/dashes)
8. Compare with difflib.SequenceMatcher or sentence-level substring search

## Pitfalls

- PDF hyphen joining drops the hyphen: `self-knowing` → `selfknowing`.
  This causes cascading word-level diff failures. Use sentence-level or
  chunk-based matching instead of word-by-word comparison.
- Section headers (I, II, III) may be present in DOCX body but filtered
  from PDF — not real discrepancies.
- The existing `scripts/proofread-pdf.py` is hardcoded for 佛教徒的人生态度.
  Do NOT reuse it for other articles without rewriting the body-start
  markers and filter patterns. Create article-specific scripts instead.
- `git diff --word-diff` fails when one file is multi-line and the other
  is single-line. Normalize both to single-line first.

## Example

`translate-files/正念禅修十要素/ten-elements-c7fcd9.py` — extracts cleaned
body from both sources, outputs to `/tmp/` for side-by-side diffing.
