import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[1] / "terms-database" / "search.py"
SERVER_PATH = Path(__file__).parents[1] / "terms-database" / "server.py"
SPEC = importlib.util.spec_from_file_location("mpi_terms_search", MODULE_PATH)
terms_search = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(terms_search)


@pytest.fixture
def search_db(tmp_path, monkeypatch):
    db_path = tmp_path / "terms.sqlite"
    con = sqlite3.connect(db_path)
    con.execute(
        """CREATE TABLE terms(
            rowid INTEGER PRIMARY KEY,
            zh TEXT,
            en TEXT,
            loc TEXT,
            source TEXT
        )"""
    )

    rows = [
        # Insert enough broad, low-authority matches first to reproduce the old
        # default-LIMIT failure where an authoritative exact match was hidden.
        (
            f"与空性相关的长条目{i:02d}",
            f"broad emptiness example {i}",
            "其他文章",
            "BAICKZ",
        )
        for i in range(25)
    ]
    rows.extend(
        [
            ("空性", "other exact", "心经讲义", "BAICKZ"),
            ("空性", "sutra exact", "心经讲义", "经论名"),
            ("空性", "buddhist exact", "心经禅观", "佛教术语"),
            ("空性", "internal exact", "心经讲义", "内部特色词"),
            ("空性", "dot exact first", "心经定稿", "DoT定稿"),
            ("空性", "dot exact second", "心经定稿", "DoT定稿"),
            ("般若法门的深入修持", "long specific", "讲义", "BAICKZ"),
            ("般若法门", "short authoritative", "讲义", "DoT定稿"),
            ("修般若", "shorter", "讲义", "佛教术语"),
            ("缘起", "dependent origination", "中论讲义", "佛教术语"),
            ("十二缘起", "twelve links of dependent origination", None, "DoT定稿"),
        ]
    )
    con.executemany(
        "INSERT INTO terms(zh, en, loc, source) VALUES (?, ?, ?, ?)", rows
    )
    con.commit()
    con.close()

    monkeypatch.setattr(terms_search, "DB", str(db_path))
    return terms_search


def test_exact_matches_and_authority_precede_earlier_broad_rows(search_db):
    results = search_db.search("空性")

    assert [row["en"] for row in results[:6]] == [
        "dot exact first",
        "dot exact second",
        "internal exact",
        "buddhist exact",
        "sutra exact",
        "other exact",
    ]
    assert all(row["zh"] == "空性" for row in results[:6])


def test_default_limit_keeps_authoritative_exact_candidates_visible(search_db):
    results = search_db.search("空性")

    assert len(results) == 20
    assert results[0]["source"] == "DoT定稿"
    assert any(row["source"] == "内部特色词" for row in results)
    assert any(row["source"] == "佛教术语" for row in results)
    assert any(row["source"] == "经论名" for row in results)


def test_nonexact_matches_prefer_longer_more_specific_chinese(search_db):
    results = search_db.search("般若", limit=None)

    assert [row["en"] for row in results] == [
        "long specific",
        "short authoritative",
        "shorter",
    ]


def test_rowid_is_the_stable_tie_breaker(search_db):
    first = search_db.search("空性", src="DoT定稿", limit=None)
    second = search_db.search("空性", src="DoT定稿", limit=None)

    assert [row["en"] for row in first] == ["dot exact first", "dot exact second"]
    assert second == first


def test_database_connection_is_read_only_and_creates_no_sidecars(search_db):
    db_path = Path(search_db.DB)
    con = search_db._connect()
    try:
        with pytest.raises(sqlite3.OperationalError):
            con.execute("CREATE TABLE should_not_exist(value TEXT)")
    finally:
        con.close()

    assert not Path(f"{db_path}-wal").exists()
    assert not Path(f"{db_path}-shm").exists()


def test_server_reuses_read_only_search_connection():
    server_text = SERVER_PATH.read_text(encoding="utf-8")

    assert "return s._connect()" in server_text
    assert "journal_mode=WAL" not in server_text


def test_multiword_query_and_loc_source_filters_are_preserved(search_db):
    assert search_db.search("dependent origination", src="佛教术语") == [
        {
            "zh": "缘起",
            "en": "dependent origination",
            "loc": "中论讲义",
            "source": "佛教术语",
        }
    ]
    assert search_db.search("空性", loc="禅观", limit=None) == [
        {
            "zh": "空性",
            "en": "buddhist exact",
            "loc": "心经禅观",
            "source": "佛教术语",
        }
    ]
    assert search_db.search("dependent missing") == []


def test_filter_only_and_limit_boundaries(search_db):
    results = search_db.search("", src="DoT定稿", limit=None)

    assert results
    assert all(row["source"] == "DoT定稿" for row in results)
    assert search_db.search("空性", limit=0) == []
    assert search_db.search("不存在的词", limit=None) == []


@pytest.mark.parametrize(
    "argv",
    [
        ["terms-search", "空性", "src:佛教术语", "loc:心经", "1"],
        ["terms-search", "空性 src:佛教术语 loc:心经", "1"],
    ],
)
def test_cli_accepts_unquoted_filters_and_legacy_quoted_query(
    search_db, monkeypatch, capsys, argv
):
    monkeypatch.setattr(
        sys,
        "argv",
        argv,
    )

    search_db.main()
    output = capsys.readouterr().out

    assert "Results: 1" in output
    assert "en: buddhist exact" in output
    assert "src: 佛教术语" in output
