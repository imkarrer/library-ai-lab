"""The Catalog adapter seam. Vocabulary and binding: CONTEXT.md, docs/adr/0005.

A Catalog adapter returns Records only: bibliographic description, never
circulation, holds, fines, or patron data.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Record:
    """One title's bibliographic description from the Catalog."""

    id: str
    title: str
    author: str
    subjects: str
    summary: str
    call_number: str


class Catalog(Protocol):
    """The seam that lets the assistant search one kind of Catalog."""

    def search(self, query: str, k: int) -> list[Record]: ...

    def get(self, id: str) -> Record | None: ...


def edition_key(record: Record) -> tuple[str, str]:
    """One key for every edition of a book: its title and author, letters only."""
    return (
        re.sub(r"\W+", " ", record.title).strip().lower(),
        re.sub(r"\W+", " ", record.author).strip().lower(),
    )


def search_each(catalog: Catalog, queries: Iterable[str], k: int) -> list[Record]:
    """Up to `k` Records from a separate search per query, taken from each in turn.

    Searching them together lets one common word fill the list; in turn, every query
    gets a place, and the first query's best book comes first.
    """
    results = [catalog.search(query, k) for query in queries]
    records: list[Record] = []
    editions: set[tuple[str, str]] = set()
    for rank in range(k):
        for found in results:
            if rank < len(found) and edition_key(found[rank]) not in editions:
                editions.add(edition_key(found[rank]))
                records.append(found[rank])
    return records[:k]
