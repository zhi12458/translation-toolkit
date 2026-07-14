# Terms Database Alignment

Batch-align translation glossary entries and body text against the MPI terms database.

## Module API (preferred)

Import directly in `execute_code` scripts — no subprocess, no server, no text parsing:

```python
import sys
sys.path.insert(0, 'toolkit/terms-database')
from search import search

results = search("三级修学", limit=5)
results = search("空性", loc="心经", src="DoT定稿", limit=5)
# returns list of {zh, en, loc, source} dicts
```

## Batch lookup pattern

```python
import sys
sys.path.insert(0, 'toolkit/terms-database')
from search import search

terms = ["三无漏学", "八步三禅", "闻思修", ...]
author_sources = {"DoT定稿", "内部特色词", "佛教术语", "经论名"}

for term in terms:
    results = search(term, limit=10)
    relevant = [r for r in results if r["source"] in author_sources]
    for r in relevant:
        print(f"{r['zh']} → {r['en']}  [{r['source']}]")
```

Or filter to a single authoritative source directly:
```python
results = search("三级修学", src="DoT定稿", limit=5)
```

## Priority ranking

When the same term has entries in multiple source tables, prefer:
1. DoT定稿 (highest authority — final translation decisions)
2. 内部特色词 (MPI internal terminology)
3. 佛教术语 (general Buddhist terminology)
4. 经论名 (sutra/shastra titles)

## Alignment workflow

1. Extract all Chinese glossary terms from `{% "TERM" ... %}` blocks in the .dj file
2. Extract body-text domain terms that may not have glossary entries
3. Batch-query each term against the HTTP API
4. Filter results to authoritative source tables
5. Compare DB canonical translation against current file translation
6. Flag mismatches where DB entry differs materially from current
7. Apply fixes with `patch` tool — fix both glossary comments AND body text occurrences
8. Verify with `grep` that no old terms remain

## Pitfalls

- `replace_all` can create doubled words when the surrounding context already contains the replacement string (e.g., "The Eight Steps" → "The The Eight Steps"). Prefer targeted single-replacement patches.
- Start patches from the bottom of the file upward to preserve line numbers.
- Some DB entries are contextual phrases (e.g., "珍惜法缘" → a full sentence), not standalone term translations. Use standalone term entries where available.
