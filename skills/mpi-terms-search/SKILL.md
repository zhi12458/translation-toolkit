---
name: terms-search
description: Full-text search across the MPI term database. Use when translating or looking up Chinese-English Buddhist/MPI terminology.
category: research
---

# Terms Search

Database: `toolkit/terms-database/termlib.duckdb`
CLI: `toolkit/terms-database/search.py`
Server: `toolkit/terms-database/server.py`

## CLI (preferred)

```
toolkit/terms-database/search.py <query> [limit]
```

Multi-word queries are ANDed. Searches both `zh` and `en` columns.

## Python module

```python
import sys
sys.path.insert(0, 'toolkit/terms-database')
from search import search
results = search("空性", limit=5, src="DoT定稿")
# → list of {zh, en, loc, source} dicts
```

Use this inside `execute_code` scripts for batch lookups — no subprocess needed.

## HTTP API (use only when CLI is insufficient)

Start: `python3 toolkit/terms-database/server.py` (port 8910)

- `GET /` — plain HTML UI (form + results table, no CSS)
- `GET /` — plain HTML UI (form + results table, no CSS)
- `GET /search?q=...&loc=...&src=...&limit=...` — JSON `{count, results: [{zh, en, loc, source}]}`
- `GET /sources` — JSON array of `{source, count}` for all source tables

All params optional. Omit `limit` for all results. Query terms are ANDed across zh+en.
Errors return `{"error": "..."}` with HTTP 500 (API) or shown inline (UI).

## Source tables

| src | rows | description |
|---|---|---|
| BAICKZ | 7,679 | Main term bank with example sentences |
| 佛教术语 | 1,795 | Buddhist terminology from 定稿书目术语库 |
| DoT定稿 | 896 | DoT final translation decisions |
| DoT初步 | 412 | DoT preliminary queries |
| 偈颂经文名言 | 263 | Verses and sutra quotes |
| 成语俗语 | 184 | Idioms and common expressions |
| 经论名 | 89 | Sutra/shastra titles |
| 内部特色词 | 87 | MPI internal terminology |
| 海内外建筑名称 | 28+9 | MPI building/place names |
| MPI组织架构 | 4+28 | MPI org structure |
| 导师金句 | 24 | Teacher quotes |
| 静心学堂课程 | 17+20 | Course names |
| 禅意项目 | 14+11 | Zen program terms |
| 公案 | 8 | Chan koans |

## Direct DuckDB

```
duckdb toolkit/terms-database/termlib.duckdb
```

Key tables: `unified_terms_flat` (zh, en, loc, source), individual source tables, `unified_terms` view.

## Rebuilding

Terms data comes from `guide/03 术语库/`. To rebuild:
1. Convert source xlsx/ods → CSV+YAML in `_output/`
2. Rebuild DuckDB from CSVs
3. Materialize `unified_terms_flat` view → table for performance

**Full rebuild pipeline:** See `references/termbase-rebuild.md` (absorbed from the `termbase-management` skill).

## Translation Alignment

When aligning translated djot files against the term database, load `references/translation-alignment.md` for the full workflow. Summary:
1. Extract Chinese terms from `{% "..." %}` glossary blocks in the translated file
2. Batch-search via CLI (`./search.py <term>`). Query each term individually.
3. Prioritize DoT定稿 > 内部特色词 > 佛教术语
4. Fix both glossary comments AND body-text occurrences
5. Verify with grep
