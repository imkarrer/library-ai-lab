import gzip
import io
import sqlite3
from pathlib import Path

import pytest

from library_assistant.catalog.sqlite_backend import SqliteCatalog
from scripts.build_demo_catalog import (
    check_disk_space,
    download_resumable,
    load_juvenile_records,
    parse_index_links,
)

# Real Library of Congress records; see fixtures/catalog/README.md.
LOC_SAMPLE = (
    Path(__file__).parent / "fixtures" / "catalog" / "loc-books-2016-sample.xml"
)
# 250 of the sample's 270 records carry a juvenile or adolescent 008/22 code.
LOC_SAMPLE_JUVENILE_COUNT = 250


def test_load_juvenile_records_keeps_only_juvenile_and_adolescent(tmp_path):
    catalog = SqliteCatalog(sqlite3.connect(":memory:"))
    count = load_juvenile_records(LOC_SAMPLE, catalog)
    assert count == LOC_SAMPLE_JUVENILE_COUNT
    # The three questions (j) and Fighting Ruben Wolfe (d) are kept.
    assert catalog.get("   00049673 ") is not None
    assert catalog.get("   00042817 ") is not None
    # How to be a domestic goddess (e) and Botanical materia medica (blank) are not.
    assert catalog.get("   00456254 ") is None
    assert catalog.get("   00000002 ") is None
    assert "   00456254 " not in [r.id for r in catalog.search("domestic goddess", k=5)]


def test_check_disk_space_refuses_when_free_space_is_below_estimate(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "shutil.disk_usage",
        lambda _path: type("Usage", (), {"free": 10})(),
    )
    with pytest.raises(SystemExit, match="not enough disk space"):
        check_disk_space(tmp_path / "catalog.db", required_bytes=1_000_000)


def test_check_disk_space_allows_when_free_space_is_sufficient(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "shutil.disk_usage",
        lambda _path: type("Usage", (), {"free": 1_000_000_000})(),
    )
    check_disk_space(tmp_path / "catalog.db", required_bytes=1_000_000)


BOOKS_ALL_PAGE = """
<a href="/cds/downloads/MDSConnect/BooksAll.2016.combined.xml.gz">combined</a>
<a href="/cds/downloads/MDSConnect/BooksAll.2016.part01.utf8.gz">utf8</a>
<a href="/cds/downloads/MDSConnect/BooksAll.2016.part01.xml.gz">xml 1</a>
<a href="/cds/downloads/MDSConnect/BooksAll.2016.part02.xml.gz">xml 2</a>
<a href="/cds/downloads/MDSConnect/BooksAll.2014.part01.xml.gz">old xml</a>
<a href="/cds/downloads/ModernMARC.pdf">notes</a>
"""


def test_parse_index_links_takes_newest_year_xml_parts_only():
    links = parse_index_links(
        BOOKS_ALL_PAGE,
        base_url="https://www.loc.gov/cds/products/MDSConnect-books_all.html",
    )
    assert links == [
        "https://www.loc.gov/cds/downloads/MDSConnect/BooksAll.2016.part01.xml.gz",
        "https://www.loc.gov/cds/downloads/MDSConnect/BooksAll.2016.part02.xml.gz",
    ]


def test_parse_index_links_finds_nothing_on_an_unrelated_page():
    assert parse_index_links('<a href="notes.pdf">x</a>', "https://example.org/") == []


def test_load_juvenile_records_reads_gzipped_marcxml(tmp_path):
    part = tmp_path / "BooksAll.2016.part01.xml.gz"
    part.write_bytes(gzip.compress(LOC_SAMPLE.read_bytes()))
    catalog = SqliteCatalog(sqlite3.connect(":memory:"))
    assert load_juvenile_records(part, catalog) == LOC_SAMPLE_JUVENILE_COUNT
    assert catalog.get("   00057791 ").title == "The story of Ferdinand /"


class _FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, status: int):
        super().__init__(body)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_download_resumable_appends_on_206(tmp_path, monkeypatch):
    dest = tmp_path / "part.xml.gz"
    dest.write_bytes(b"abc")
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda request: _FakeResponse(b"def", 206)
    )
    download_resumable("https://example.org/part.xml.gz", dest)
    assert dest.read_bytes() == b"abcdef"


def test_download_resumable_restarts_when_range_is_ignored(tmp_path, monkeypatch):
    dest = tmp_path / "part.xml.gz"
    dest.write_bytes(b"abc")
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda request: _FakeResponse(b"abcdef", 200)
    )
    download_resumable("https://example.org/part.xml.gz", dest)
    assert dest.read_bytes() == b"abcdef"
