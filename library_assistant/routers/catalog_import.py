"""The Catalog page: what Students search, and loading the school's own export."""

from __future__ import annotations

import html
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from library_assistant.access import get_clock, get_db
from library_assistant.catalog.school_import import (
    ImportRefused,
    import_school_catalog,
)
from library_assistant.catalog.sqlite_backend import SqliteCatalog
from library_assistant.config import Settings
from library_assistant.dependencies import get_settings
from library_assistant.staff import LibrarianDep, StaffAccount, page

router = APIRouter(prefix="/staff/catalog")

LOAD_FORM = """<h2>Load your library's Catalog</h2>
<ol>
  <li>In your library system, export your whole collection as MARC records and save the
  file. In Destiny, look for Export Titles.</li>
  <li>Choose that file here. It replaces everything Students search, so a book you
  withdrew goes too. Students can keep working while it loads.</li>
</ol>
<form method="post" action="/staff/catalog" enctype="multipart/form-data">
  <p><input type="file" name="export" required></p>
  <p><label><input type="checkbox" name="allow_smaller" value="yes"> This file is much
  smaller than my last one, and that's right</label></p>
  <p><button>Load Catalog</button></p>
</form>
<p class="catalog-note">The assistant keeps only each book's title, author, subjects, summary, and
call number. It does not keep the file, and it never learns who has a book. A large
collection can take a minute. Load a new export whenever you've added or withdrawn
books: your library system stays the real record, and this is a copy of it.</p>"""


def _status_html(catalog_path: str) -> str:
    """What Students are searching now, and how fresh it is."""
    if not Path(catalog_path).exists():
        return "<p>No Catalog is loaded yet, so Students won't see any books.</p>"
    catalog = SqliteCatalog.open(catalog_path)
    try:
        books, last = catalog.count(), catalog.last_import()
    finally:
        catalog.close()
    if last is None:
        return (
            f"<p>Students are searching a sample of <strong>{books:,}</strong> books, "
            "not your library's. Load your Catalog below to replace it.</p>"
        )
    loaded = datetime.fromisoformat(last.loaded_at).strftime("%B %-d, %Y")
    return (
        f"<p>Students are searching <strong>{books:,}</strong> books from your library "
        f"system, loaded {loaded} by {html.escape(last.loaded_by)}.</p>"
    )


def _catalog_page(
    account: StaffAccount,
    db: sqlite3.Connection,
    now: datetime,
    settings: Settings,
    message: str = "",
    status_code: int = 200,
) -> HTMLResponse:
    notice = f'<p class="notice" role="status">{html.escape(message)}</p>'
    body = (
        "<h1>Catalog</h1>"
        f"{notice if message else ''}"
        f"{_status_html(settings.catalog_path)}"
        f"{LOAD_FORM}"
    )
    return page("Catalog", body, status_code, account=account, db=db, now=now)


@router.get("")
def catalog_page(
    account: LibrarianDep,
    loaded: int | None = None,
    left_out: int = 0,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """Librarian-only: what Students search, and the form to load a new export."""
    message = ""
    if loaded is not None:
        message = f"Loaded {loaded:,} books."
        if left_out:
            message += (
                f" Left out {left_out:,} other entries: DVDs, equipment, and anything "
                "with no title or call number."
            )
    return _catalog_page(account, db, clock, settings, message)


@router.post("", response_model=None)
def load_catalog(
    account: LibrarianDep,
    export: Annotated[UploadFile, File()],
    allow_smaller: Annotated[str, Form()] = "",
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Librarian-only: replace the Catalog with an export; a refused file changes nothing."""
    try:
        load = import_school_catalog(
            export.file,
            Path(settings.catalog_path),
            account.username,
            clock,
            allow_smaller=allow_smaller == "yes",
        )
    except ImportRefused as refusal:
        return _catalog_page(account, db, clock, settings, str(refusal), 400)
    return RedirectResponse(
        f"/staff/catalog?loaded={load.books}&left_out={load.left_out}",
        status_code=303,
    )
