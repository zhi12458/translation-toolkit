---
name: pptx-translate
description: Translate PowerPoint files between Chinese and English — extract strings to YAML, translate, quality review, and write back with font-shrink + auto-fit for layout.
category: productivity
---

# PPTX Translation

Translate `.pptx` files between Chinese and English. Covers the full pipeline: extraction → translation → review → write-back.

## Workflow

### 1. Extract strings to YAML

Run `toolkit/scripts/extract.py original.pptx strings.yaml`. Produces YAML with entries:

```yaml
- slide: 1
  shape: 0
  run: 0
  kind: title
  zh: 开启生命的富足
  en: ""
```

- `slide` — 1-based slide number
- `shape` — 0-based shape index within slide
- `run` — 0-based paragraph index within text frame (or computed index for tables)
- `kind` — `title` | `subtitle` | `center_title` | `body` | `table` | `notes`
- `zh` — source text
- `en` — translation target (initially empty)

Table `run` index formula: `num_rows * col + row`. Reverse with `row = run % num_rows`, `col = run // num_rows`.

Speaker notes use `shape: -1`.

### 2. Translate

**Do NOT call external translation APIs.** Translate directly — the agent IS the model. The user corrects this: "Why do you call external models to do it? You can do it yourself!"

Fill in the `en` field for every entry. Batch if needed, but translate in your response, not via API calls.

Terminology guidance for Buddhist/gratitude content:
- 感恩=gratitude, 缘起=dependent origination, 众生=sentient beings
- 因缘=causes and conditions, 三宝=Three Jewels, 福报=merit/blessings
- 座上=formal practice, 座下=daily life practice, 共修=group practice
- 上报四重恩=repaying the four great kindnesses

### 3. Quality review

Scan for:
- Terminology consistency (same zh term → same en term throughout)
- Ellipsis convention — English uses 3 dots `...`, zh may use 6
- Buddhist term accuracy
- Missing translations
- Overly literal renderings

### 4. Write back with layout fixes

Run `toolkit/scripts/build.py strings.yaml original.pptx translated.pptx`.

The script:
- Replaces text in matching paragraphs (clears all runs, sets first run)
- Replaces table cell text (using row/col from computed index)
- Reduces font size by 18% (`FONT_SCALE = 0.82`) on all translated shapes and tables
- Sets `auto_size = TEXT_TO_FIT_SHAPE` on text frames to handle overflow
- English text is ~1.3–1.5× longer than Chinese — font shrink + auto-fit handles most cases

## Alternate scripts

The absorbed `pptx-translation` skill had alternate script names: `extract_pptx.py` and `build_pptx.py`. These are functionally equivalent to `extract.py` and `build.py` with minor formatting differences (docstrings, variable naming). If the primary scripts fail, the alternates are available in the archive at `~/.hermes/skills/.archive/pptx-translation/scripts/`.

## Pitfalls

- "run" in the YAML is actually the **paragraph index** within a text frame, not the OOXML text-run index. python-pptx iterates paragraphs, not runs.
- Font shrink only applies to runs that have an explicit `font.size` — inherited sizes from paragraph/layout defaults are skipped.
- After write-back, verify with `python -m markitdown translated.pptx` to check text landed correctly.
- Tables: font shrink is applied per-cell text frame. Each cell is its own text frame.
- markitdown may fail with `ModuleNotFoundError: dotenv` — run `pip install python-dotenv` first.

## Scripts

- `toolkit/scripts/extract.py` — extract strings from PPTX to YAML
- `toolkit/scripts/build.py` — write translations back with font shrink + auto-fit
