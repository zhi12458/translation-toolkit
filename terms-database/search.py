#!/usr/bin/env python3
"""Full-text search over MPI term database (SQLite).

Module usage:
    from search import search
    results = search("空性")
    results = search("空性", limit=5, loc="心经", src="佛教术语")
    # returns list of dicts: {zh, en, loc, source}

CLI usage:
    toolkit/terms-database/search.py <query> [limit]
    toolkit/terms-database/search.py 空性 loc:心经 src:公案
"""

import os
import json
import sqlite3
import sys
from pathlib import Path

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "termlib.sqlite")


def _connect():
    # termlib.sqlite is a versioned static asset. Immutable read-only mode
    # avoids WAL/SHM sidecars and also works when the toolkit is mounted
    # read-only for translators.
    uri = f"{Path(DB).resolve().as_uri()}?mode=ro&immutable=1"
    return sqlite3.connect(uri, uri=True)


def _search_rows(con, query, loc=None, src=None, limit=None):
    terms = query.split() if query else []
    clauses = []
    params = []

    for t in terms:
        like = f"%{t}%"
        clauses.append("(zh LIKE ? OR en LIKE ?)")
        params.extend([like, like])

    where = " AND ".join(clauses) if clauses else "1=1"

    if loc:
        where += " AND loc LIKE ?"
        params.append(f"%{loc}%")
    if src:
        where += " AND source = ?"
        params.append(src)

    # Keep result selection deterministic and put the most useful terminology
    # candidates first.  Exact Chinese matches outrank phrase/example rows;
    # otherwise a longer Chinese entry is usually the more specific match.
    # Source authority is the documented MPI priority, and rowid provides a
    # stable final tie-breaker for duplicate entries.
    exact_query = query.strip() if query else ""
    sql = f"""
        SELECT zh, en, loc, source
        FROM terms
        WHERE {where}
        ORDER BY
            CASE WHEN ? <> '' AND trim(zh) = ? THEN 0 ELSE 1 END,
            length(trim(zh)) DESC,
            CASE source
                WHEN 'DoT定稿' THEN 0
                WHEN '内部特色词' THEN 1
                WHEN '佛教术语' THEN 2
                WHEN '经论名' THEN 3
                ELSE 4
            END,
            rowid ASC
    """
    params.extend([exact_query, exact_query])
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)

    return con.execute(sql, params).fetchall()


def search(query, loc=None, src=None, limit=20):
    """Search the terms database. Returns list of {zh, en, loc, source} dicts.

    query: str — space-separated search terms (AND logic)
    loc: str — filter by loc column (LIKE match)
    src: str — filter by source column (exact match)
    limit: int — max results (default 20)

    Results are deterministic: exact Chinese matches first, then longer Chinese
    entries, documented source authority, and finally insertion rowid.
    """
    con = _connect()
    try:
        rows = _search_rows(con, query, loc=loc, src=src, limit=limit)
        return [
            {"zh": zh, "en": en, "loc": loc_val or "", "source": src_val}
            for zh, en, loc_val, src_val in rows
        ]
    finally:
        con.close()


def main():
    if len(sys.argv) < 2:
        print("Usage: terms-search <query> [limit]")
        print("  queries: '空性', 'emptiness 中观'")
        print()
        print("Special prefixes (can be standalone or combined with query):")
        print("  loc:<source>  — filter by loc (e.g. loc:心经)")
        print("  src:<table>   — filter by source table (e.g. src:佛教术语)")
        print()
        print("Examples:")
        print("  terms-search 空性")
        print("  terms-search 'suffering 苦' loc:心经")
        print("  terms-search src:公案")
        sys.exit(1)

    # Preserve the legacy quoted-query + optional-limit interface while also
    # accepting the documented unquoted filter form:
    #   terms-search 空性 loc:心经 src:佛教术语 5
    raw_parts = sys.argv[1:]
    json_output = False
    if "--json" in raw_parts:
        raw_parts = [part for part in raw_parts if part != "--json"]
        json_output = True
    limit = 20
    if len(raw_parts) > 1:
        try:
            limit = int(raw_parts[-1])
            raw_parts = raw_parts[:-1]
        except ValueError:
            pass
    raw = " ".join(raw_parts)

    loc_filter = None
    src_filter = None
    query_parts = []

    for token in raw.split():
        if token.startswith("loc:"):
            loc_filter = token[4:]
        elif token.startswith("src:"):
            src_filter = token[4:]
        else:
            query_parts.append(token)

    query_str = " ".join(query_parts)

    if not query_str and not loc_filter and not src_filter:
        print("No search terms or filters. Usage: terms-search <query> [limit]")
        return

    results = search(query_str, loc=loc_filter, src=src_filter, limit=limit)

    if json_output:
        print(json.dumps(results, ensure_ascii=False, sort_keys=True))
        return

    if not results:
        print(f"No results for: {raw}")
        return

    print(f"Results: {len(results)}")
    print()
    for r in results:
        print(f"zh: {r['zh']}")
        print(f"en: {r['en']}")
        print(f"loc: {r['loc'] or '-'}  |  src: {r['source']}")
        print()


if __name__ == "__main__":
    main()
