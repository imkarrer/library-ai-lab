"""Each request gets its own SQLite connection: one shared across the thread pool broke."""

import threading
from collections import Counter

import pytest

from library_assistant import access


@pytest.fixture
def db_file(tmp_path, monkeypatch):
    path = tmp_path / "library_assistant.db"
    monkeypatch.setattr(access, "DB_PATH", str(path))
    monkeypatch.setattr(access, "_schema_ready", False)
    return path


def test_each_request_gets_its_own_connection_to_the_same_file(db_file):
    first, second = access.get_db(), access.get_db()
    assert first is not second
    first.execute(
        "INSERT INTO staff_accounts (username, password_hash, role, created_at) "
        "VALUES ('librarian.overdue', 'x', 'librarian', '2026-11-05T00:00:00+00:00')"
    )
    first.commit()
    assert second.execute("SELECT COUNT(*) FROM staff_accounts").fetchone() == (1,)


def test_every_connection_overwrites_what_it_deletes(db_file):
    # ADR-0003: the Purge's deletes are zeroed on disk, whichever connection runs them.
    assert access.get_db().execute("PRAGMA secure_delete").fetchone() == (1,)


def test_the_journal_stays_a_rollback_journal(db_file):
    # WAL keeps old page images in a -wal file that secure_delete never zeroes.
    assert access.get_db().execute("PRAGMA journal_mode").fetchone() == ("delete",)


def test_the_schema_is_made_once_not_per_request(db_file, monkeypatch):
    made = []
    real_connect = access.connect
    monkeypatch.setattr(
        access, "connect", lambda *a, **k: made.append(1) or real_connect(*a, **k)
    )
    for _ in range(3):
        access.get_db()
    assert len(made) == 1


def test_threads_at_once_never_trip_over_each_other(db_file):
    # Shared, this query failed thousands of times with "bad parameter or other API
    # misuse": the Live view's stream and Make Cards' poll both run current_staff.
    access.get_db()
    errors: Counter[str] = Counter()

    def request() -> None:
        for _ in range(300):
            try:
                access.get_db().execute(
                    "SELECT id FROM staff_accounts WHERE username = ?", ("x",)
                ).fetchone()
            except Exception as error:  # noqa: BLE001 - counting is the test
                errors[type(error).__name__] += 1

    threads = [threading.Thread(target=request) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
