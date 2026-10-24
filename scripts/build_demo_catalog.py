#!/usr/bin/env python3
"""Build the demo Catalog from Library of Congress open-access MARC records.

A separate setup command, never run by the assistant itself (ADR-0006's demo
exception). It streams the LoC MARC distribution one file at a time, keeps
only juvenile and adolescent titles (the 008 target-audience byte), and
loads them into a SQLite Catalog. Run once, on the presenter's machine,
before the demo:

    python3 scripts/build_demo_catalog.py --dest catalog.db

Resuming: re-running with the same --download-dir continues any partially
downloaded file instead of restarting it.
"""

from __future__ import annotations

import argparse
import re
import shutil
import urllib.parse
import urllib.request
from pathlib import Path

from library_assistant.catalog.marc import is_juvenile, parse_marcxml, to_record
from library_assistant.catalog.sqlite_backend import SqliteCatalog

MARC_DIST_INDEX_URL = "https://www.loc.gov/cds/products/marcDist.php"

# About 25M records across the full LoC open-access distribution (all
# formats, 1968-2014). Used only to size the disk preflight; the measured
# figures from one real run belong in README.md, not here.
ESTIMATED_SOURCE_RECORDS = 25_000_000
ESTIMATED_BYTES_PER_RECORD = 2_000
# The filtered SQLite Catalog is much smaller than the source files it is
# built from, but both must fit on disk at once during the build.
ESTIMATED_SOURCE_AND_CATALOG_BYTES = (
    ESTIMATED_SOURCE_RECORDS * ESTIMATED_BYTES_PER_RECORD
)


def estimate_required_bytes() -> int:
    return ESTIMATED_SOURCE_AND_CATALOG_BYTES


def check_disk_space(destination: Path, required_bytes: int) -> None:
    """Refuse to start if free space at `destination` is below estimate."""
    free_bytes = shutil.disk_usage(destination.parent).free
    if free_bytes < required_bytes:
        raise SystemExit(
            f"not enough disk space to build the demo Catalog: "
            f"{free_bytes:,} bytes free at {destination.parent}, "
            f"need an estimated {required_bytes:,} bytes. "
            "Free up space or point --download-dir at a larger volume."
        )


_FILE_LINK_RE = re.compile(r'href="([^"]+\.xml)"', re.IGNORECASE)


def parse_index_links(html: str, base_url: str) -> list[str]:
    """Pull MARCXML distribution file links out of the index page's HTML.

    Only the MARCXML files are listed: `load_juvenile_records` parses
    MARCXML (library_assistant/catalog/marc.py), not binary MARC (ISO 2709).
    """
    return [
        urllib.parse.urljoin(base_url, match.group(1))
        for match in _FILE_LINK_RE.finditer(html)
    ]


def fetch_index_links(index_url: str = MARC_DIST_INDEX_URL) -> list[str]:
    with urllib.request.urlopen(index_url) as response:
        html = response.read().decode("utf-8", errors="replace")
    return parse_index_links(html, index_url)


def download_resumable(url: str, dest: Path) -> None:
    """Download `url` to `dest`, resuming from `dest`'s current size."""
    resume_from = dest.stat().st_size if dest.exists() else 0
    request = urllib.request.Request(url)
    if resume_from:
        request.add_header("Range", f"bytes={resume_from}-")
    with urllib.request.urlopen(request) as response:
        mode = "ab" if resume_from else "wb"
        with dest.open(mode) as out:
            shutil.copyfileobj(response, out)


def load_juvenile_records(marcxml_path: Path, catalog: SqliteCatalog) -> int:
    """Filter `marcxml_path` to juvenile/adolescent titles, load into `catalog`.

    Pure apart from the filesystem read of `marcxml_path`; no network. This
    is what tests/test_build_demo_catalog.py exercises against the fixture.
    """
    juvenile_records = (
        to_record(marc_record)
        for marc_record in parse_marcxml(str(marcxml_path))
        if is_juvenile(marc_record)
    )
    count = 0
    for record in juvenile_records:
        catalog.load_records([record])
        count += 1
    return count


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=Path("catalog.db"))
    parser.add_argument("--download-dir", type=Path, default=Path("marc-dist-download"))
    args = parser.parse_args(argv)

    check_disk_space(args.dest, estimate_required_bytes())

    args.download_dir.mkdir(parents=True, exist_ok=True)
    catalog = SqliteCatalog.open(str(args.dest))
    total = 0
    for file_url in fetch_index_links():
        file_path = args.download_dir / Path(urllib.parse.urlparse(file_url).path).name
        print(f"Downloading {file_url} -> {file_path}")
        download_resumable(file_url, file_path)
        added = load_juvenile_records(file_path, catalog)
        total += added
        print(f"  loaded {added} juvenile/adolescent records ({total} total)")
    print(f"Done: {total} records in {args.dest}")


if __name__ == "__main__":
    main()
