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


def test_an_older_flag_history_gains_the_acknowledged_event(tmp_path):
    """An Install's database from before lib-msq rebuilds its history CHECK on connect,
    keeping its rows, so an Acknowledgement can be recorded."""
    import sqlite3

    from library_assistant.access import connect
    from library_assistant.flag_history import append_event

    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute(
        "CREATE TABLE flag_history (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "flag_id INTEGER NOT NULL, event TEXT NOT NULL CHECK (event IN ('raised', "
        "'viewed', 'closed', 'reopened', 'repeated', 'escalated', 'exported')), "
        "at TEXT NOT NULL, account TEXT, reason TEXT, outcome TEXT, source TEXT, "
        "entry_id TEXT, watchlist_version TEXT, repeat_count INTEGER)"
    )
    old.execute(
        "INSERT INTO flag_history (flag_id, event, at) VALUES (1, 'raised', 't0')"
    )
    old.commit()
    old.close()

    db = connect(str(path))
    append_event(db, 1, "acknowledged", at="t1", account="librarian")

    assert db.execute("SELECT event FROM flag_history ORDER BY id").fetchall() == [
        ("raised",),
        ("acknowledged",),
    ]
