"""Loading a school's own Catalog from its library system's MARC export.

A one-way copy (ADR-0005 addendum): the library system stays the record of what the
library owns, and each load replaces the whole Catalog, so a withdrawn book goes with no
bookkeeping. Students search the old Catalog until the new one is swapped in. The export
is read and never kept.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from library_assistant.catalog import Record
from library_assistant.catalog.marc import (
    NotMarc,
    is_book,
    read_export,
    to_school_record,
)
from library_assistant.catalog.sqlite_backend import CatalogImport, SqliteCatalog


class ImportRefused(ValueError):
    """Why a file was not loaded, in words for the Librarian. Nothing changed."""


def _books(source: BinaryIO) -> tuple[list[Record], int]:
    """The export's books a Student could walk to, and how many entries were left out."""
    books: list[Record] = []
    left_out = 0
    try:
        for number, marc_record in enumerate(read_export(source), start=1):
            record = to_school_record(marc_record)
            if is_book(marc_record) and record.title and record.call_number:
                books.append(record if record.id else _numbered(record, number))
            else:
                left_out += 1
    except NotMarc as error:
        raise ImportRefused(
            "That file isn't a MARC export. Export your collection from your library "
            "system as MARC records and try again."
        ) from error
    return books, left_out


def _numbered(record: Record, number: int) -> Record:
    """A Record needs an id for its Citation, and not every export has a 001."""
    return replace(record, id=f"school-{number}")


def _last_load(dest: Path) -> CatalogImport | None:
    if not dest.exists():
        return None
    catalog = SqliteCatalog.open(str(dest))
    try:
        return catalog.last_import()
    finally:
        catalog.close()


def import_school_catalog(
    source: BinaryIO,
    dest: Path,
    loaded_by: str,
    now: datetime,
    allow_smaller: bool = False,
) -> CatalogImport:
    """Replace the Catalog at `dest` with the books in `source`, all at once.

    Raises ImportRefused, with `dest` untouched, for a file with no books, or one less
    than half the size of the school's last load: most likely one shelf's export, not the
    collection. `allow_smaller` is the Librarian saying it is meant.
    """
    books, left_out = _books(source)
    if not books:
        raise ImportRefused(
            "That file has no books with a call number in it, so nothing changed."
        )
    last = _last_load(dest)
    if last is not None and len(books) < last.books / 2 and not allow_smaller:
        raise ImportRefused(
            f"That file has {len(books):,} books and your Catalog has {last.books:,}, so "
            "it may be only part of your collection. Nothing changed. If it is right, "
            "tick the box and load it again."
        )
    load = CatalogImport(now.isoformat(), loaded_by, len(books), left_out)
    handle, building = tempfile.mkstemp(dir=dest.parent, prefix=f"{dest.name}.")
    os.close(handle)
    try:
        catalog = SqliteCatalog.open(building)
        catalog.load_records(books)
        catalog.record_import(load)
        catalog.close()
        os.replace(building, dest)
    finally:
        Path(building).unlink(missing_ok=True)
    return load
