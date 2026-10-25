import dataclasses
import sqlite3
from pathlib import Path

from library_assistant.catalog import Record
from library_assistant.catalog.marc import parse_marcxml, to_record
from library_assistant.catalog.sqlite_backend import SqliteCatalog

FIXTURES = Path(__file__).parent / "fixtures" / "catalog"
# Real Library of Congress records; see fixtures/catalog/README.md.
LOC_SAMPLE = FIXTURES / "loc-books-2016-sample.xml"
# Hand-written: the only way to put patron fields into MARC input.
SYNTHETIC_PATRON_FIELDS = FIXTURES / "synthetic-patron-fields.xml"

# LoC's 001 is the LCCN as distributed: space-padded, kept verbatim by to_record.
WRINGER_ID = "   00042606 "
FERDINAND_ID = "   00057791 "
RUBEN_WOLFE_ID = "   00042817 "


def _load_catalog() -> SqliteCatalog:
    catalog = SqliteCatalog(sqlite3.connect(":memory:"))
    catalog.load_records(
        to_record(marc_record) for marc_record in parse_marcxml(str(LOC_SAMPLE))
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
    marc_record = next(parse_marcxml(str(SYNTHETIC_PATRON_FIELDS)))
    assert marc_record.subfields("952", "p") == ["patron-barcode-004821"]
    record = to_record(marc_record)
    for value in dataclasses.astuple(record):
        assert "patron" not in value
        assert "hold-queue" not in value


def test_search_returns_known_title_with_all_six_fields():
    catalog = _load_catalog()
    results = catalog.search("wringer", k=5)
    assert results == [
        Record(
            id=WRINGER_ID,
            title="Wringer /",
            author="Spinelli, Jerry.",
            subjects="Large type books.; Courage; Violence; Pigeons; Large type books.",
            summary=(
                "As Palmer comes of age, he must either accept the violence of being "
                "a wringer at his town's annual Pigeon Day or find the courage to "
                "oppose it."
            ),
            call_number="PZ7.S75663 Wr 2000",
        )
    ]


def test_search_treats_a_students_question_as_text_not_query_syntax():
    catalog = _load_catalog()
    for question in [
        "books like The Story of Ferdinand?",
        'the "Ferdinand" book!',
        "Ferdinand AND OR NOT bull NEAR(",
        "Ferdinand-bull*",
    ]:
        results = catalog.search(question, k=5)
        assert results, question
        assert results[0].id == FERDINAND_ID, question


def test_search_with_no_words_returns_nothing():
    assert _load_catalog().search("?!  ...", k=5) == []


def test_search_ignores_question_filler_words():
    catalog = _load_catalog()
    assert catalog.search("can you recommend some books about it?", k=5) == []
    assert [r.id for r in catalog.search("books about boxing", k=5)] == [RUBEN_WOLFE_ID]
    assert [
        r.id for r in catalog.search("do you have any books about bulls?", k=5)
    ] == [FERDINAND_ID]


def test_get_returns_record_by_id():
    catalog = _load_catalog()
    record = catalog.get(RUBEN_WOLFE_ID)
    assert record is not None
    assert record.title == "Fighting Ruben Wolfe /"
    assert record.author == "Zusak, Markus."
    assert record.subjects == "Boxing; Brothers"
    assert record.call_number == "PZ7.Z837 Fi 2001"

    assert catalog.get("no-such-id") is None
