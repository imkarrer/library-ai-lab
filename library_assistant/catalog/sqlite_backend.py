"""The shipped Catalog adapter: MARC loaded into SQLite, searched with FTS5."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable

from library_assistant.catalog import Record

_FIELDS = ("id", "title", "author", "subjects", "summary", "call_number")

# Words a Student's question carries that say nothing about the collection. Without
# this, "books about friendship?" matches any Record containing "books" or "about".
_FILLER_WORDS = frozenset(
    [
        "a",
        "about",
        "an",
        "and",
        "any",
        "are",
        "book",
        "books",
        "can",
        "do",
        "find",
        "for",
        "give",
        "have",
        "i",
        "in",
        "is",
        "it",
        "like",
        "me",
        "my",
        "of",
        "on",
        "or",
        "recommend",
        "show",
        "some",
        "something",
        "the",
        "to",
        "want",
        "what",
        "with",
        "you",
    ]
)


class SqliteCatalog:
    """A Catalog backed by a SQLite FTS5 table of Records."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._connection.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS records USING fts5({', '.join(_FIELDS)})"
        )

    @classmethod
    def open(cls, path: str) -> SqliteCatalog:
        # FastAPI builds a request's Catalog in a worker thread and the streamed answer
        # searches it on the event loop's: one request at a time uses each connection,
        # so SQLite's same-thread guard only stood in the way (lib-30v).
        return cls(sqlite3.connect(path, check_same_thread=False))

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
        # A Student's question is not FTS5 syntax: quote each word so punctuation,
        # quotes, and words like AND or NEAR are matched as text, never parsed.
        terms = [
            term
            for term in re.findall(r"\w+", query)
            if term.lower() not in _FILLER_WORDS
        ]
        if not terms:
            return []
        match = " OR ".join(f'"{term}"' for term in terms)
        rows = self._connection.execute(
            "SELECT id, title, author, subjects, summary, call_number "
            "FROM records WHERE records MATCH ? ORDER BY rank LIMIT ?",
            (match, k),
        ).fetchall()
        return [Record(*row) for row in rows]

    def get(self, id: str) -> Record | None:
        row = self._connection.execute(
            "SELECT id, title, author, subjects, summary, call_number "
            "FROM records WHERE id = ?",
            (id,),
        ).fetchone()
        return Record(*row) if row else None
