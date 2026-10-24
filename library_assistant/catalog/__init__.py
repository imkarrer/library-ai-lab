"""The Catalog adapter seam. Vocabulary and binding: CONTEXT.md, docs/adr/0005.

A Catalog adapter returns Records only: bibliographic description, never
circulation, holds, fines, or patron data.
"""

from __future__ import annotations

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
