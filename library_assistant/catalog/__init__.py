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

    def search_strict(self, query: str, k: int) -> list[Record]:
        """`search`, but only Records holding every word of `query`, where an adapter
        can tell. A search for "ants caves" then finds cave ants or nothing, not caves."""
        return self.search(query, k)


def edition_key(record: Record) -> tuple[str, str]:
    """One key for every edition of a book: its title and author, letters only."""
    return (
        re.sub(r"\W+", " ", record.title).strip().lower(),
        re.sub(r"\W+", " ", record.author).strip().lower(),
    )


def search_each(
    catalog: Catalog, terms: Iterable[str], question: str, k: int
) -> list[Record]:
    """Up to `k` Records from a separate search per term, taken from each in turn.

    Searching them together lets one common word fill the list; in turn, every term
    gets a place, and the first term's best book comes first. `question`, the Student's
    own words, goes last and loosely: a model's terms can miss the subject asked about.
    """
    results = [catalog.search_strict(term, k) for term in terms]
    results.append(catalog.search(question, k))
    records: list[Record] = []
    editions: set[tuple[str, str]] = set()
    for rank in range(k):
        for found in results:
            if rank < len(found) and edition_key(found[rank]) not in editions:
                editions.add(edition_key(found[rank]))
                records.append(found[rank])
    return records[:k]
