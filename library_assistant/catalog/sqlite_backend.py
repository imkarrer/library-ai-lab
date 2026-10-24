"""The shipped Catalog adapter: MARC loaded into SQLite, searched with FTS5."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable

from library_assistant.catalog import Record

_FIELDS = ("id", "title", "author", "subjects", "summary", "call_number")


class SqliteCatalog:
    """A Catalog backed by a SQLite FTS5 table of Records."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._connection.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS records USING fts5({', '.join(_FIELDS)})"
        )

    @classmethod
    def open(cls, path: str) -> SqliteCatalog:
        return cls(sqlite3.connect(path))

    def load_records(self, records: Iterable[Record]) -> None:
        self._connection.executemany(
            f"INSERT INTO records ({', '.join(_FIELDS)}) VALUES "
            f"({', '.join('?' for _ in _FIELDS)})",
            [
                (
                    record.id,
                    record.title,
                    record.author,
                    record.subjects,
                    record.summary,
                    record.call_number,
                )
                for record in records
            ],
        )
        self._connection.commit()

    def search(self, query: str, k: int) -> list[Record]:
        rows = self._connection.execute(
            "SELECT id, title, author, subjects, summary, call_number "
            "FROM records WHERE records MATCH ? ORDER BY rank LIMIT ?",
            (query, k),
        ).fetchall()
        return [Record(*row) for row in rows]

    def get(self, id: str) -> Record | None:
        row = self._connection.execute(
            "SELECT id, title, author, subjects, summary, call_number "
            "FROM records WHERE id = ?",
            (id,),
        ).fetchone()
        return Record(*row) if row else None
