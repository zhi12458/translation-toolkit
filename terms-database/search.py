#!/usr/bin/env python3
"""Full-text search over MPI term database. Queries unified_terms_flat via DuckDB LIKE.

Module usage:
    from search import search_terms
    results = search_terms("空性")
    results = search_terms("空性", limit=5, loc="心经", src="佛教术语")
    # returns list of dicts: {zh, en, loc, source}

CLI usage:
    python search.py <query> [limit]
    python search.py 空性 loc:心经 src:公案
"""

import sys
import os
import duckdb

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "termlib.duckdb")


def _connect():
    return duckdb.connect(DB, read_only=True)


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

    sql = f"SELECT zh, en, loc, source FROM unified_terms_flat WHERE {where}"
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

    raw = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20

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
