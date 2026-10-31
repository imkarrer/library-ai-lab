"""The shipped Catalog adapter: MARC loaded into SQLite, searched with FTS5."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable
from dataclasses import astuple, dataclass

from library_assistant.catalog import Record, edition_key

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
        "did",
        "does",
        "find",
        "for",
        "give",
        "have",
        "how",
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
        "s",
        "show",
        "some",
        "something",
        "the",
        "to",
        "want",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
        "you",
    ]
)


# How much each column counts in a match, in _FIELDS order: a word in the title or the
# subject headings says what a book is about, one in the summary only that it comes up.
_COLUMN_WEIGHTS = (0.0, 10.0, 2.0, 5.0, 1.0, 0.0)

# Editions of one book share a title and author: rows fetched per Record returned, so
# the duplicates dropped still leave `k`.
_ROWS_PER_RECORD = 4


@dataclass(frozen=True)
class CatalogImport:
    """One load of a school's export: when, by whom, and how much of it was kept."""

    loaded_at: str
    loaded_by: str
    books: int
    left_out: int


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
        # Red wolves, not every red thing: any one word only if no book has them all.
        return self.search_strict(query, k) or self._matching(query, " OR ", k)

    def search_strict(self, query: str, k: int) -> list[Record]:
        return self._matching(query, " AND ", k)

    def _matching(self, query: str, joiner: str, k: int) -> list[Record]:
        # A Student's question is not FTS5 syntax: quote each word so punctuation,
        # quotes, and words like AND or NEAR are matched as text, never parsed.
        terms = [
            term
            for term in re.findall(r"\w+", query)
            if term.lower() not in _FILLER_WORDS
        ]
        if not terms:
            return []
        match = joiner.join(f'"{term}"' for term in terms)
        weights = ", ".join(str(weight) for weight in _COLUMN_WEIGHTS)
        rows = self._connection.execute(
            "SELECT id, title, author, subjects, summary, call_number "
            f"FROM records WHERE records MATCH ? ORDER BY bm25(records, {weights}) "
            "LIMIT ?",
            (match, k * _ROWS_PER_RECORD),
        ).fetchall()
        records: list[Record] = []
        editions: set[tuple[str, str]] = set()
        for row in rows:
            record = Record(*row)
            if edition_key(record) not in editions:
                editions.add(edition_key(record))
                records.append(record)
        return records[:k]

    def count(self) -> int:
        return self._connection.execute("SELECT count(*) FROM records").fetchone()[0]

    def record_import(self, last_import: CatalogImport) -> None:
        """Note where these Records came from, in the file they came with."""
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS catalog_import "
            "(loaded_at TEXT, loaded_by TEXT, books INTEGER, left_out INTEGER)"
        )
        self._connection.execute(
            "INSERT INTO catalog_import VALUES (?, ?, ?, ?)", astuple(last_import)
        )
        self._connection.commit()

    def last_import(self) -> CatalogImport | None:
        """The school export this Catalog was loaded from; None for any other Catalog."""
        try:
            row = self._connection.execute(
                "SELECT loaded_at, loaded_by, books, left_out FROM catalog_import"
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        return CatalogImport(*row) if row else None

    def close(self) -> None:
        self._connection.close()

    def get(self, id: str) -> Record | None:
        row = self._connection.execute(
            "SELECT id, title, author, subjects, summary, call_number "
            "FROM records WHERE id = ?",
            (id,),
        ).fetchone()
        return Record(*row) if row else None
