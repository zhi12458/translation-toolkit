# PDF-to-DOCX Config Patterns

The converter accepts a config dict that maps PDF-specific patterns to DOCX behavior.

## Example config

```python
config = {
    "fonts": {
        "title": "STHeitiSC-Medium",
        "body": "HYShuSongErKW",
        "page_number": "HelveticaNeue",
    },
    "header_sizes": {"section": 18, "sub": 15},
    "body_size": 12,
    "bullet_fonts": ["Wingdings", "Wingdings 2", "Wingdings 3"],
    "page_number_font": "HelveticaNeue",
    "numbered_patterns": [r'^\d+\)', r'^\d+\.'],
    "skip_fonts": ["HelveticaNeue"],
}
```

## Common post-processing patterns

### Compact numbered lists

Split items that flowed together in one PDF paragraph:

```python
def split_compact_list(text: str) -> list[str]:
    parts = re.split(r'(?=\d+\))', text)
    return [p for p in parts if p.strip()]
```

### Verse / poetry lines

Split merged verse at semantic phrase boundaries:

```python
def split_verse(text: str, split_markers: list[str]) -> list[str]:
    pattern = '|'.join(f'(?={m})' for m in split_markers)
    return [p for p in re.split(pattern, text) if p.strip()]
```

### Chinese process steps

Split `一、foo 二、bar` into separate items:

```python
def split_chinese_steps(text: str) -> list[str]:
    parts = re.split(r'(?=[一二三四五六七八九十]、)', text)
    return [p.strip() for p in parts if p.strip()]
```

## Tuning thresholds

- **Y-gap threshold** (typically 20–30 pt): controls how aggressively lines are grouped into paragraphs.
- **Style-change threshold**: break paragraphs on font change, size jump, or bold toggle when the difference exceeds this value.

See `references/troubleshooting.md` for threshold adjustment guidance.
