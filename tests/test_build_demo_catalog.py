import gzip
import io
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from library_assistant.catalog.sqlite_backend import SqliteCatalog
from scripts.build_demo_catalog import (
    check_disk_space,
    download_resumable,
    finish_build,
    load_school_records,
    parse_index_links,
    start_build,
)

# Real Library of Congress records; see fixtures/catalog/README.md.
LOC_SAMPLE = (
    Path(__file__).parent / "fixtures" / "catalog" / "loc-books-2016-sample.xml"
)
# 250 of the sample's 270 records carry a juvenile or adolescent 008/22 code, and 242 of
# those a Dewey number, E, FIC, or B a school librarian would shelve by.
LOC_SAMPLE_SHELF_READY_COUNT = 242


def test_load_school_records_keeps_only_shelf_ready_juvenile_books(tmp_path):
    catalog = SqliteCatalog(sqlite3.connect(":memory:"))
    count = load_school_records(LOC_SAMPLE, catalog)
    assert count == LOC_SAMPLE_SHELF_READY_COUNT
    # The three questions (j) and Fighting Ruben Wolfe (d) are kept.
    assert catalog.get("00049673") is not None
    assert catalog.get("00042817") is not None
    # How to be a domestic goddess (e) and Botanical materia medica (blank) are not.
    assert catalog.get("00456254") is None
    assert catalog.get("00000002") is None
    assert "00456254" not in [r.id for r in catalog.search("domestic goddess", k=5)]
    # Juvenile, but shelved only by LoC's own number (Pooh, PZ5.G3168): not kept.
    assert catalog.get("00269808") is None


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


def test_load_school_records_reads_gzipped_marcxml(tmp_path):
    part = tmp_path / "BooksAll.2016.part01.xml.gz"
    part.write_bytes(gzip.compress(LOC_SAMPLE.read_bytes()))
    catalog = SqliteCatalog(sqlite3.connect(":memory:"))
    assert load_school_records(part, catalog) == LOC_SAMPLE_SHELF_READY_COUNT
    assert catalog.get("00057791").title == "The story of Ferdinand /"


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


def test_builder_runs_as_the_readme_documents():
    # The README runs `python3 scripts/build_demo_catalog.py` from the repo root, where
    # Python puts scripts/, not the root, on the import path. --help imports everything
    # and touches no network.
    repo_root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, "scripts/build_demo_catalog.py", "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        env={"PATH": os.environ.get("PATH", "")},
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--download-dir" in result.stdout


def test_a_build_leaves_the_current_catalog_until_it_is_done(tmp_path):
    dest, downloads = tmp_path / "catalog.db", tmp_path / "downloads"
    dest.write_text("the catalog the demo is using")
    building = start_build(dest, downloads, fresh=True)
    assert building == tmp_path / "catalog.db.building"
    assert dest.read_text() == "the catalog the demo is using"
    building.write_text("the new catalog")
    (downloads / "done.txt").write_text("BooksAll.2016.part01.xml.gz\n")
    finish_build(building, dest, downloads)
    assert dest.read_text() == "the new catalog"
    assert not building.exists() and not (downloads / "done.txt").exists()


def test_a_built_catalog_is_only_rebuilt_with_fresh(tmp_path):
    dest, downloads = tmp_path / "catalog.db", tmp_path / "downloads"
    dest.write_text("built")
    with pytest.raises(SystemExit, match="--fresh"):
        start_build(dest, downloads, fresh=False)


def test_an_interrupted_build_resumes_and_fresh_starts_over(tmp_path):
    dest, downloads = tmp_path / "catalog.db", tmp_path / "downloads"
    building = start_build(dest, downloads, fresh=False)
    building.write_text("part 1 loaded")
    (downloads / "done.txt").write_text("BooksAll.2016.part01.xml.gz\n")
    assert start_build(dest, downloads, fresh=False) == building
    assert (downloads / "done.txt").exists()
    start_build(dest, downloads, fresh=True)
    assert not building.exists() and not (downloads / "done.txt").exists()


def test_an_older_builds_progress_list_is_not_trusted(tmp_path):
    """A done.txt with no build beside it would skip every part into an empty Catalog."""
    dest, downloads = tmp_path / "catalog.db", tmp_path / "downloads"
    downloads.mkdir()
    (downloads / "done.txt").write_text("BooksAll.2016.part01.xml.gz\n")
    start_build(dest, downloads, fresh=False)
    assert not (downloads / "done.txt").exists()
