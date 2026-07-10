# Translation Alignment Workflow

How to align translated djot files against the MPI terms database.

## When

After producing a first-pass translation, or when the user asks to check terminology. Any time a `.dj` file contains glossary-style `{% "..." %}` blocks with Chinese→English term pairs.

## Steps

1. Read the full translated file. Extract all Chinese terms from `{% "TERM" (pinyin) = ENGLISH ... %}` blocks.

2. Start the search server: `python3 $MPI_PROJECT_ROOT/terms-search/server.py &` (port 8910). It may already be running — check with `curl -s http://localhost:8910/`.

3. Batch-search each term via the HTTP API:
   ```
   curl -s "http://localhost:8910/search?q=TERM&limit=5"
   ```
   Prefer `src=DoT定稿` filter for authoritative hits, but also check without filter to catch 内部特色词 and 佛教术语 entries.

4. For each term, compare the database `en` against the file's translation. A mismatch exists when the core term translation differs (ignore explanatory commentary in glossary blocks).

5. Priority order for which source to trust:
   - DoT定稿 (highest authority — final translation decisions)
   - 内部特色词 (MPI internal terminology)
   - 佛教术语 (general Buddhist terms)
   - 经论名 (sutra/shastra titles)

6. Apply fixes with `patch` tool. Fix BOTH the glossary comment AND all body-text occurrences. Use `replace_all=true` for terms that appear identically in multiple places.

7. After fixing, grep for remaining old forms to verify nothing was missed.

## Pitfalls

- Glossary blocks often include commentary after the term (pinyin, explanations). Compare only the core term translation, not the full comment.
- Some terms appear in body text without glossary blocks — scan the body for domain terms too.
- The search.py CLI does NOT support `src:` or `loc:` filter syntax directly; use the HTTP API or direct DuckDB queries instead.
- Replace-all can create double articles ("the The Eight Steps...") when body text already has the article before the term. Check each replacement site.
- Escaped quotes in patch old_string/new_string cause false "Escape-drift" errors. Use unescaped `"` characters from the actual file content.
- Terms may have different translations in different contexts (e.g., standalone 心灯 = "lamp of awakening" vs compound 点亮心灯 = "illuminate one's heart"). Use the standalone form for glossary entries.
- Sutra quote conventions (e.g., Diamond Sutra "lives" not "bodies" for 身体布施) are not always in the database. Apply standard English Buddhist idiom.

## Example

Searching 三无漏学:
```
curl -s "http://localhost:8910/search?q=三无漏学&limit=5"
→ DoT定稿: "three uncontaminated forms of training"
→ Current file: "the three undefiled studies"
→ MISMATCH → fix
```

## Report

After alignment, the user may ask for a report. Save it as `alignment-report.dj` in the project directory with:
- Summary line (source breakdown)
- Per-term before/after table with source annotation
- "Not Changed" section listing terms checked and found acceptable
