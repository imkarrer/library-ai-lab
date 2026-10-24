import sqlite3
from pathlib import Path

import pytest

from library_assistant.catalog.sqlite_backend import SqliteCatalog
from scripts.build_demo_catalog import (
    check_disk_space,
    load_juvenile_records,
    parse_index_links,
)

FIXTURE = Path(__file__).parent / "fixtures" / "catalog" / "fixture.xml"


def test_load_juvenile_records_keeps_only_juvenile_and_adolescent(tmp_path):
    catalog = SqliteCatalog(sqlite3.connect(":memory:"))
    count = load_juvenile_records(FIXTURE, catalog)
    assert count == 2
    assert catalog.get("loc0001") is not None
    assert catalog.get("loc0002") is not None
    assert catalog.get("loc0003") is None


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


def test_parse_index_links_resolves_relative_xml_links():
    html = '<a href="batch-2014-1.xml">batch 1</a> <a href="notes.pdf">notes</a>'
    links = parse_index_links(
        html, base_url="https://www.loc.gov/cds/products/marcDist.php"
    )
    assert links == ["https://www.loc.gov/cds/products/batch-2014-1.xml"]
