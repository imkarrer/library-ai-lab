#!/usr/bin/env python3
"""Build the demo Catalog from Library of Congress open-access MARC records.

A separate setup command, never run by the assistant itself (ADR-0006's demo
exception). It reads the LoC MDSConnect "Books All" page, takes the newest
year's MARCXML parts (BooksAll.<year>.partNN.xml.gz), and for each part:
downloads it, keeps only the books a school librarian would recognize on a
shelf (juvenile or adolescent by the 008 target-audience byte, with a Dewey
number, E, FIC, or B: `is_shelf_ready`), loads them into a SQLite Catalog,
and deletes the part. Run once, on the presenter's machine, before the demo:

    python3 scripts/build_demo_catalog.py --dest catalog.db

The build writes <dest>.building and replaces <dest> only when every part is
in, so the demo keeps its current Catalog until then. Resuming: re-running
continues <dest>.building, skipping parts already loaded (done.txt in
--download-dir) and continuing a partially downloaded part. --fresh throws
away a build in progress, and with it an existing <dest>, and starts over:
the way to clean an older Catalog and reseed it.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# Run as `python3 scripts/build_demo_catalog.py`, Python puts scripts/ on the import
# path, not the repo root, so library_assistant would not import.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from library_assistant.catalog.marc import (
    is_shelf_ready,
    parse_marcxml,
    to_record,
)
from library_assistant.catalog.sqlite_backend import SqliteCatalog

BOOKS_ALL_INDEX_URL = "https://www.loc.gov/cds/products/MDSConnect-books_all.html"

# loc.gov answers Python's default User-Agent with 403 Forbidden (checked
# 2026-10-25), so every request names this tool.
USER_AGENT = (
    "library-assistant-demo-catalog/0 (+https://github.com/imkarrer/library-ai-lab)"
)

# Each part is about 70 MB compressed (checked 2026-10-25; 43 parts for 2016,
# about 3 GB in all). Only one part is on disk at a time, so the build needs
# room for the largest part plus the growing Catalog. One real run
# (lib-f24.19, 2026-10-25; full figures in README.md) produced a 157,335,552
# byte Catalog; the estimate below is that figure with about 2x headroom.
ESTIMATED_LARGEST_PART_BYTES = 100_000_000
ESTIMATED_CATALOG_BYTES = 300_000_000


def estimate_required_bytes() -> int:
    return ESTIMATED_LARGEST_PART_BYTES + ESTIMATED_CATALOG_BYTES


def check_disk_space(destination: Path, required_bytes: int) -> None:
    """Refuse to start if free space at `destination` is below estimate."""
    free_bytes = shutil.disk_usage(destination.parent).free
    if free_bytes < required_bytes:
        raise SystemExit(
            f"not enough disk space to build the demo Catalog: "
            f"{free_bytes:,} bytes free at {destination.parent}, "
            f"need an estimated {required_bytes:,} bytes. "
            "Free up space or point --dest and --download-dir at a larger volume."
        )


_PART_LINK_RE = re.compile(
    r'href="([^"]*BooksAll\.(\d{4})\.part\d+\.xml\.gz)"', re.IGNORECASE
)


def parse_index_links(html: str, base_url: str) -> list[str]:
    """The newest year's MARCXML part links on the Books All page, in order.

    Older years, the single "combined" file, and the binary MARC (.utf8.gz,
    .marc8.gz) files are skipped: `load_school_records` parses MARCXML
    (library_assistant/catalog/marc.py), and the parts keep one file on disk
    at a time.
    """
    matches = [
        (match.group(1), match.group(2)) for match in _PART_LINK_RE.finditer(html)
    ]
    if not matches:
        return []
    newest_year = max(year for _, year in matches)
    links: list[str] = []
    for href, year in matches:
        url = urllib.parse.urljoin(base_url, href)
        if year == newest_year and url not in links:
            links.append(url)
    return links


def fetch_index_links(index_url: str = BOOKS_ALL_INDEX_URL) -> list[str]:
    request = urllib.request.Request(index_url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request) as response:
        html = response.read().decode("utf-8", errors="replace")
    links = parse_index_links(html, index_url)
    if not links:
        raise SystemExit(
            f"no BooksAll.<year>.partNN.xml.gz links found at {index_url}; "
            "the Library of Congress may have changed the page."
        )
    return links


def download_resumable(url: str, dest: Path) -> None:
    """Download `url` to `dest`, resuming from `dest`'s current size.

    If the server ignores the Range request (200 instead of 206), the file is
    downloaded again from the start rather than appended to.
    """
    resume_from = dest.stat().st_size if dest.exists() else 0
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    if resume_from:
        request.add_header("Range", f"bytes={resume_from}-")
    with urllib.request.urlopen(request) as response:
        mode = "ab" if resume_from and response.status == 206 else "wb"
        with dest.open(mode) as out:
            shutil.copyfileobj(response, out)


def load_school_records(marcxml_path: Path, catalog: SqliteCatalog) -> int:
    """Filter `marcxml_path` to the shelf-ready juvenile titles, load into `catalog`.

    Pure apart from the filesystem read of `marcxml_path`; no network. This
    is what tests/test_build_demo_catalog.py exercises against the fixture.
    """
    records = [
        to_record(marc_record)
        for marc_record in parse_marcxml(str(marcxml_path))
        if is_shelf_ready(marc_record)
    ]
    catalog.load_records(records)
    return len(records)


def start_build(dest: Path, download_dir: Path, fresh: bool) -> Path:
    """Where this run builds: <dest>.building, new or (unless `fresh`) resumed.

    A finished <dest> with no build in progress is left alone unless `fresh`; a done.txt
    with no build beside it belongs to an older build and is cleared, or every part
    would be skipped into an empty Catalog."""
    building = dest.with_name(dest.name + ".building")
    download_dir.mkdir(parents=True, exist_ok=True)
    done_list = download_dir / "done.txt"
    if fresh:
        building.unlink(missing_ok=True)
        done_list.unlink(missing_ok=True)
    elif not building.exists():
        if dest.exists():
            raise SystemExit(
                f"{dest} is already built. To clean it and seed it again from the "
                "Library of Congress, run with --fresh."
            )
        done_list.unlink(missing_ok=True)
    return building


def finish_build(building: Path, dest: Path, download_dir: Path) -> None:
    """Swap the finished build in for <dest> in one step, and clear its progress."""
    os.replace(building, dest)
    (download_dir / "done.txt").unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=Path("catalog.db"))
    parser.add_argument("--download-dir", type=Path, default=Path("marc-dist-download"))
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="start over: discard a build in progress and replace an existing --dest",
    )
    args = parser.parse_args(argv)

    building = start_build(args.dest, args.download_dir, fresh=args.fresh)
    check_disk_space(args.dest, estimate_required_bytes())
    done_list = args.download_dir / "done.txt"
    done = set(done_list.read_text().split()) if done_list.exists() else set()
    catalog = SqliteCatalog.open(str(building))
    total = 0
    downloaded_bytes = 0
    for file_url in fetch_index_links():
        name = Path(urllib.parse.urlparse(file_url).path).name
        if name in done:
            print(f"Skipping {name}: already loaded")
            continue
        file_path = args.download_dir / name
        print(f"Downloading {file_url} -> {file_path}")
        download_resumable(file_url, file_path)
        downloaded_bytes += file_path.stat().st_size
        added = load_school_records(file_path, catalog)
        total += added
        with done_list.open("a") as out:
            out.write(name + "\n")
        file_path.unlink()
        print(f"  loaded {added} shelf-ready records ({total} total)")
    finish_build(building, args.dest, args.download_dir)
    print(
        f"Done: {total} records in {args.dest} "
        f"({downloaded_bytes:,} bytes downloaded this run, "
        f"{args.dest.stat().st_size:,} bytes on disk)"
    )


if __name__ == "__main__":
    main()
