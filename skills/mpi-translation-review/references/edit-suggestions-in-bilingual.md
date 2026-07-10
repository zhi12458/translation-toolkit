# Edit Suggestions in bilingual.dj

When the user asks to add edit suggestions directly into bilingual.dj, use this
two-tier approach.

## Two files

- `bilingual.dj` — clean: inline corrections applied, NO `{% %}` comment lines
- `commented.dj` — same content + `{% ... %}` comment lines interleaved

This lets the user diff them side by side.

## Inline corrections

Apply directly to the English text. These are fixes the reviewer is confident about:

- Typos, mechanical issues (Chinese punctuation in EN, double periods, stray `*`, unbalanced quotes)
- Grammar fixes (subject-verb agreement, missing articles)
- Wording improvements (clunky literal translations → idiomatic English)

Apply with `patch` (mode='replace'). Verify uniqueness before
replacing — many EN paragraphs are long single lines, so match a unique
substring. Never use regex-based string replacement in `execute_code`.

## `{% %}` comment lines

For translation decisions worth documenting but not "correct" per se:

```
CN paragraph
EN paragraph
{% reason for the choice, alternative renderings %}
(blank)
```

The comment goes AFTER the EN line (before the blank separator). One comment per
issue. Keep them terse.

What to comment on:
- Literal translation of idioms (`单线程` → "single-threaded")
- Translation choices that differ from literal meaning (`精神利益` → "nourishing the spirit")
- Standard Buddhist terminology (`正命` → "Right Livelihood")
- Glosses added/dropped (`道场` — "(Dojo)" parenthetical removed)
- Idiom translations (`甘之若饴` → "as sweet as syrup")
- Paired terms where one rendering influences the other (`魔性` → "demon-nature" to parallel "Buddha-nature")
- Scripture citations with Sanskrit titles (`普贤行愿品` → "Gaṇḍavyūha Sūtra")

What NOT to comment on:
- Obvious corrections (typos, grammar)
- Names, dates, simple connectives
- Standard renderings with no interesting choice

## Pitfalls

- **Never split a paragraph mid-sentence** with a `{% %}` comment. Comments go
  AFTER the full EN paragraph, before the blank separator. If a string
  replacement inserts `\n{% %}` in the middle of a paragraph, it breaks the
  interleaved structure.

- **Check for merged comments**: after inserting, scan for `{% ... %} ` followed
  by EN text on the same line. These must be split so the EN text continues on
  the next line.

- **Collapse triple+ blank lines**: comment insertions can create extra blanks.
  Run `re.sub(r'\n\n\n+', '\n\n', text)` after all insertions.
