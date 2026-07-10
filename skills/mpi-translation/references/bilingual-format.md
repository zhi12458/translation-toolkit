# Bilingual DJ Format

## Layout

Each pair: source line immediately followed by target line. Blank line separates pairs.

```
source-line
target-line

source-line
target-line
```

NOT:
```
source-line
              ← WRONG: extra blank between source and target
target-line
```

## Creating initial bilingual from source only

Only non-blank source lines get an empty target placeholder. Blank lines in the
source pass through as-is and serve as natural pair separators.

```
source-A

source-B
```

The blank line between source-A and source-B is an original blank from the
source — do NOT add an extra target+separator for it.

Pitfall: treating blank source lines as content lines creates 3+ consecutive
blank lines (source-blank → target-blank → separator-blank). This is wrong.

## Verification

`non_blank_source_lines × 2 + total_source_lines = bilingual_line_count`
