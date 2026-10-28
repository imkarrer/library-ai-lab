"""Install settings: Librarian-only knobs stored in the `install_settings` table.

Binding: ADR-0010. Only the Librarian manages Install settings.
"""

from __future__ import annotations

import html
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from library_assistant.access import get_db
from library_assistant.staff import LibrarianDep, page

SESSION_IDLE_MINUTES = "session_idle_minutes"

MAX_SESSION_IDLE_MINUTES = 480

SETTINGS_FORM = """<h1>Install settings</h1>
{message}
<form method="post" action="/staff/settings">
  <p><label>Session idle minutes (0-480, 0 means no limit)
     <input name="session_idle_minutes" type="number" min="0" max="480"
            value="{session_idle_minutes}" required></label></p>
  <p><button>Save</button></p>
</form>"""


def get_int_setting(db: sqlite3.Connection, key: str, default: int) -> int:
    row = db.execute(
        "SELECT value FROM install_settings WHERE key = ?", (key,)
    ).fetchone()
    if row is None:
        return default
    return int(row[0])


def set_setting(db: sqlite3.Connection, key: str, value: object) -> None:
    db.execute(
        "INSERT OR REPLACE INTO install_settings (key, value) VALUES (?, ?)",
        (key, str(value)),
    )
    db.commit()


router = APIRouter(prefix="/staff")


@router.get("/settings")
def settings_page(
    account: LibrarianDep, db: sqlite3.Connection = Depends(get_db)
) -> HTMLResponse:
    idle_minutes = get_int_setting(db, SESSION_IDLE_MINUTES, 0)
    return page(
        "Install settings",
        SETTINGS_FORM.format(
            message="", session_idle_minutes=html.escape(str(idle_minutes))
        ),
    )


@router.post("/settings", response_model=None)
def update_settings(
    account: LibrarianDep,
    session_idle_minutes: Annotated[int, Form()],
    db: sqlite3.Connection = Depends(get_db),
) -> RedirectResponse:
    if not 0 <= session_idle_minutes <= MAX_SESSION_IDLE_MINUTES:
        raise HTTPException(
            status_code=400,
            detail=f"session_idle_minutes must be between 0 and {MAX_SESSION_IDLE_MINUTES}",
        )
    set_setting(db, SESSION_IDLE_MINUTES, session_idle_minutes)
    return RedirectResponse("/staff/settings", status_code=303)
