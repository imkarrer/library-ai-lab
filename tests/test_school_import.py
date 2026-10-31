"""Loading a school's own Catalog: its MARC export replaces what Students search."""

import io
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pymarc import Field, Leader, Record, Subfield

from library_assistant.access import connect, get_clock, get_db
from library_assistant.app import app
from library_assistant.catalog import Record as CatalogRecord
from library_assistant.catalog.marc import NotMarc, read_export, to_school_record
from library_assistant.catalog.school_import import (
    ImportRefused,
    import_school_catalog,
)
from library_assistant.catalog.sqlite_backend import SqliteCatalog
from library_assistant.config import Settings
from library_assistant.dependencies import get_settings
from library_assistant.staff import STAFF_SESSION_COOKIE, create_account

FIXTURES = Path(__file__).parent / "fixtures" / "catalog"
NOW = datetime(2036, 11, 3, 9, 0, tzinfo=UTC)
PASSWORD = "correct horse"


def _marc(
    title: str,
    number: str = "1",
    call_number: tuple[str, str] | None = ("599.77", "GIB"),
    record_type: str = "a",
    barcode: str = "T 00042",
) -> bytes:
    """One binary MARC record, as a library system exports it."""
    record = Record(leader=Leader(f"00000n{record_type}m a2200000 a 4500"))
    record.add_field(
        Field(tag="245", subfields=[Subfield("a", title)]),
        Field(tag="100", subfields=[Subfield("a", "Gibbons, Gail,")]),
    )
    record.add_ordered_field(Field(tag="001", data=number))
    if call_number:
        record.add_field(
            Field(
                tag="852",
                subfields=[
                    Subfield("h", call_number[0]),
                    Subfield("i", call_number[1]),
                    Subfield("p", barcode),
                    Subfield("9", "19.99"),
                ],
            )
        )
    return record.as_marc()


def _load(dest: Path, data: bytes, **options):
    return import_school_catalog(io.BytesIO(data), dest, "ms.overdue", NOW, **options)


def _catalog(dest: Path) -> SqliteCatalog:
    return SqliteCatalog.open(str(dest))


def test_a_book_keeps_the_schools_own_call_number(tmp_path):
    dest = tmp_path / "catalog.db"
    _load(dest, _marc("Wolves /"))
    [record] = _catalog(dest).search("wolves", k=5)
    assert record.call_number == "599.77 GIB"
    assert record.author == "Gibbons, Gail,"


def test_koha_keeps_its_call_number_in_952():
    record = Record(leader=Leader("00000nam a2200000 a 4500"))
    record.add_field(
        Field(tag="245", subfields=[Subfield("a", "Wolves /")]),
        Field(tag="952", subfields=[Subfield("o", "FIC GEO")]),
    )
    [marc_record] = read_export(io.BytesIO(record.as_marc()))
    assert to_school_record(marc_record).call_number == "FIC GEO"


def test_a_book_with_no_holding_falls_back_on_its_own_numbers(tmp_path):
    record = Record(leader=Leader("00000nam a2200000 a 4500"))
    record.add_field(
        Field(tag="245", subfields=[Subfield("a", "Wolves /")]),
        Field(tag="082", subfields=[Subfield("a", "599.773")]),
        Field(tag="100", subfields=[Subfield("a", "Gibbons, Gail,")]),
    )
    dest = tmp_path / "catalog.db"
    _load(dest, record.as_marc())
    assert _catalog(dest).search("wolves", k=5)[0].call_number == "599.773 GIB"


def test_nothing_but_the_bibliographic_fields_reaches_the_file(tmp_path):
    dest = tmp_path / "catalog.db"
    _load(dest, _marc("Wolves /", barcode="T-BARCODE-77"))
    assert b"T-BARCODE-77" not in dest.read_bytes()
    assert b"19.99" not in dest.read_bytes()


def test_a_patron_field_in_an_export_never_reaches_a_record():
    export = (FIXTURES / "synthetic-patron-fields.xml").open("rb")
    with export:
        [marc_record] = read_export(export)
    assert "patron-barcode-004821" not in repr(to_school_record(marc_record))


def test_marcxml_exports_load_too(tmp_path):
    dest = tmp_path / "catalog.db"
    load = _load(dest, (FIXTURES / "loc-books-2016-sample.xml").read_bytes())
    assert load.books > 200
    assert _catalog(dest).count() == load.books


def test_older_marc8_exports_read_as_proper_letters(tmp_path):
    # 245 $a "Caf\xe2e /" is MARC-8 for an acute e, its accent before its letter.
    field = b"\x1f" + b"aCaf\xe2e /\x1e"
    holding = b"\x1f" + b"h599\x1fiGIB\x1e"
    body = b"10" + field + b"  " + holding + b"\x1d"
    directory = (
        b"245" + b"%04d" % (len(field) + 2) + b"00000"
        b"852" + b"%04d" % (len(holding) + 2) + b"%05d" % (len(field) + 2)
    )
    base = 24 + len(directory) + 1
    length = base + len(body)
    leader = b"%05dnam  22%05d a 4500" % (length, base)
    dest = tmp_path / "catalog.db"
    _load(dest, leader + directory + b"\x1e" + body)
    titles = sqlite3.connect(dest).execute("SELECT title FROM records").fetchall()
    assert titles == [("Café /",)]


def test_dvds_and_equipment_are_left_out_and_counted(tmp_path):
    dest = tmp_path / "catalog.db"
    load = _load(
        dest,
        _marc("Wolves /")
        + _marc("Wolves on DVD", "2", record_type="g")
        + _marc("Projector cart", "3", record_type="r"),
    )
    assert (load.books, load.left_out) == (1, 2)


def test_a_book_with_nowhere_to_walk_is_left_out(tmp_path):
    dest = tmp_path / "catalog.db"
    load = _load(dest, _marc("Wolves /") + _marc("Lost /", "2", call_number=None))
    assert (load.books, load.left_out) == (1, 1)


def test_a_damaged_record_is_counted_and_the_rest_load(tmp_path):
    dest = tmp_path / "catalog.db"
    load = _load(dest, _marc("Wolves /") + b"00030nam  2200000 a 4500xxxxxx\x1d")
    assert (load.books, load.left_out) == (1, 1)


def test_an_export_with_no_id_still_gets_one(tmp_path):
    record = Record(leader=Leader("00000nam a2200000 a 4500"))
    record.add_field(
        Field(tag="245", subfields=[Subfield("a", "Wolves /")]),
        Field(tag="852", subfields=[Subfield("h", "599")]),
    )
    dest = tmp_path / "catalog.db"
    _load(dest, record.as_marc())
    assert _catalog(dest).get("school-1").title == "Wolves /"


def test_a_load_replaces_everything_so_a_withdrawn_book_goes(tmp_path):
    dest = tmp_path / "catalog.db"
    _load(dest, _marc("Wolves /") + _marc("Whales /", "2"))
    _load(dest, _marc("Whales /", "2") + _marc("Otters /", "3"))
    assert _catalog(dest).search("wolves", k=5) == []
    assert _catalog(dest).count() == 2


@pytest.mark.parametrize("data", [b"title,author\nWolves,Gibbons\n", b"", b"<html"])
def test_a_file_that_is_not_marc_changes_nothing(tmp_path, data):
    dest = tmp_path / "catalog.db"
    _load(dest, _marc("Wolves /"))
    with pytest.raises(ImportRefused):
        _load(dest, data)
    assert _catalog(dest).count() == 1
    assert sorted(p.name for p in tmp_path.iterdir()) == ["catalog.db"]


def test_a_file_much_smaller_than_the_last_load_needs_saying_so(tmp_path):
    dest = tmp_path / "catalog.db"
    whole = b"".join(_marc(f"Book {n} /", str(n)) for n in range(10))
    _load(dest, whole)
    with pytest.raises(ImportRefused, match="only part of your collection"):
        _load(dest, _marc("One shelf /"))
    assert _catalog(dest).count() == 10
    _load(dest, _marc("One shelf /"), allow_smaller=True)
    assert _catalog(dest).count() == 1


def test_a_first_load_replaces_a_larger_sample_without_asking(tmp_path):
    dest = tmp_path / "catalog.db"
    sample = _catalog(dest)
    sample.load_records(
        [CatalogRecord(str(n), f"Sample {n}", "", "", "", "599") for n in range(10)]
    )
    sample.close()
    _load(dest, _marc("Wolves /"))
    assert _catalog(dest).count() == 1


def test_read_export_refuses_what_it_cannot_read():
    with pytest.raises(NotMarc):
        list(read_export(io.BytesIO(b"<not xml")))


@pytest.fixture
def staff(tmp_path):
    db = connect(":memory:")
    create_account(db, "ms.overdue", PASSWORD, "librarian")
    create_account(db, "mr.popquiz", PASSWORD, "teacher")
    settings = Settings(catalog_path=str(tmp_path / "catalog.db"))
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_clock] = lambda: NOW
    try:
        yield TestClient(app), tmp_path / "catalog.db"
    finally:
        app.dependency_overrides.clear()


def _sign_in(client: TestClient, username: str = "ms.overdue") -> None:
    response = client.post(
        "/staff/login",
        data={"username": username, "password": PASSWORD},
        follow_redirects=False,
    )
    assert STAFF_SESSION_COOKIE in response.cookies


def _upload(client: TestClient, data: bytes, **form):
    return client.post(
        "/staff/catalog", files={"export": ("collection.mrc", data)}, data=form
    )


def test_the_librarian_loads_an_export_and_sees_it(staff):
    client, dest = staff
    _sign_in(client)
    response = _upload(client, _marc("Wolves /") + _marc("A DVD", "2", record_type="g"))
    assert response.status_code == 200
    assert "Loaded 1 books." in response.text
    assert "Left out 1 other entries" in response.text
    assert "loaded November 3, 2036 by ms.overdue" in response.text
    assert _catalog(dest).count() == 1


def test_a_refused_file_says_why_on_the_page(staff):
    client, dest = staff
    _sign_in(client)
    response = _upload(client, b"title,author\n")
    assert response.status_code == 400
    assert "isn&#x27;t a MARC export" in response.text
    assert not dest.exists()


def test_the_box_lets_a_smaller_file_through(staff):
    client, dest = staff
    _sign_in(client)
    _upload(client, b"".join(_marc(f"Book {n} /", str(n)) for n in range(4)))
    assert _upload(client, _marc("One /")).status_code == 400
    assert _upload(client, _marc("One /"), allow_smaller="yes").status_code == 200
    assert _catalog(dest).count() == 1


def test_a_sample_catalog_says_it_is_not_the_librarys(staff):
    client, dest = staff
    _catalog(dest).close()
    _sign_in(client)
    assert "not your library" in client.get("/staff/catalog").text


def test_with_no_catalog_the_page_says_so(staff):
    client, _ = staff
    _sign_in(client)
    assert "No Catalog is loaded yet" in client.get("/staff/catalog").text


def test_a_teacher_cannot_load_a_catalog(staff):
    client, dest = staff
    _sign_in(client, "mr.popquiz")
    assert client.get("/staff/catalog").status_code == 403
    assert _upload(client, _marc("Wolves /")).status_code == 403
    assert not dest.exists()


def test_the_catalog_page_needs_a_sign_in(staff):
    client, dest = staff
    _upload(client, _marc("Wolves /"))
    assert not dest.exists()
