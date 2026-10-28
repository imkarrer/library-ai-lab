"""Schema test for ADR-0003: no full-text index holds transcript text.

An FTS virtual table keeps shadow tables that survive a DELETE on the transcripts
table it indexes, so the Purge would not be able to remove every copy.
"""

from library_assistant.access import connect


def test_no_full_text_index_on_transcripts():
    db = connect(":memory:")
    rows = db.execute(
        "SELECT name, type, sql FROM sqlite_master WHERE name LIKE '%transcript%'"
    ).fetchall()

    assert any(name == "transcripts" and type_ == "table" for name, type_, _ in rows)
    assert not any("fts" in name.lower() for name, _, _ in rows)
    assert not any(sql and "VIRTUAL TABLE" in sql.upper() for _, _, sql in rows)


def test_every_app_connection_sets_secure_delete():
    assert connect(":memory:").execute("PRAGMA secure_delete").fetchone() == (1,)
