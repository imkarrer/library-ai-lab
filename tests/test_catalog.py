import dataclasses
import sqlite3
from pathlib import Path

from library_assistant.catalog import Record
from library_assistant.catalog.marc import parse_marcxml, to_record
from library_assistant.catalog.sqlite_backend import SqliteCatalog

FIXTURE = Path(__file__).parent / "fixtures" / "catalog" / "fixture.xml"


def _load_catalog() -> SqliteCatalog:
    catalog = SqliteCatalog(sqlite3.connect(":memory:"))
    catalog.load_records(
        to_record(marc_record) for marc_record in parse_marcxml(str(FIXTURE))
    )
    return catalog


def test_record_has_only_bibliographic_fields():
    assert {f.name for f in dataclasses.fields(Record)} == {
        "id",
        "title",
        "author",
        "subjects",
        "summary",
        "call_number",
    }


def test_patron_and_circulation_fields_never_reach_a_record():
    marc_record = next(parse_marcxml(str(FIXTURE)))
    record = to_record(marc_record)
    for value in dataclasses.astuple(record):
        assert "patron" not in value
        assert "hold-queue" not in value


def test_search_returns_known_title_with_all_six_fields():
    catalog = _load_catalog()
    results = catalog.search("wild things", k=5)
    assert len(results) == 1
    record = results[0]
    assert record.id == "loc0001"
    assert record.title == "Where the wild things are / by Maurice Sendak."
    assert record.author == "Sendak, Maurice."
    assert "Monsters" in record.subjects
    assert "wild things" in record.summary
    assert record.call_number == "PZ7.S47 Wh"


def test_get_returns_record_by_id():
    catalog = _load_catalog()
    record = catalog.get("loc0002")
    assert record is not None
    assert record.title == "A wrinkle in time / by Madeleine L'Engle."

    assert catalog.get("no-such-id") is None
