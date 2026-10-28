"""The Flag queue and Flag page (CONTEXT.md).

Binding: ADR-0003 addendum. The queue never shows exchange text, only the Flag's own
fields; the Flag page shows the transcript's question and answer but is `no-store`,
so neither view leaves a copy behind.
"""

from __future__ import annotations

import html
import sqlite3
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from library_assistant.access import get_clock, get_db
from library_assistant.flags import FlagRow, close_flag, get_flag, open_flags
from library_assistant.staff import StaffDep, StandInDep, page

router = APIRouter(prefix="/staff")


def _queue_row_html(flag: FlagRow) -> str:
    return (
        "<tr>"
        f"<td>{html.escape(flag.raised_at)}</td>"
        f"<td>{html.escape(flag.category)}</td>"
        f"<td>{html.escape(flag.severity)}</td>"
        f"<td>{html.escape(flag.source)}</td>"
        f"<td>{html.escape(str(flag.entry_id or ''))}</td>"
        f"<td>{html.escape(flag.class_label)}</td>"
        f"<td>{html.escape(flag.card_number)}</td>"
        f'<td><a href="/staff/flags/{flag.id}">View</a></td>'
        "</tr>"
    )


def _queue_access(account: StaffDep) -> StaffDep:
    """Librarian and Stand-in see the whole queue; a Counselor sees only Escalated
    Flags (ADR-0010, lib-f24.7); everyone else is refused."""
    if (
        account.role != "librarian"
        and not account.is_stand_in
        and account.role != "counselor"
    ):
        raise HTTPException(status_code=403, detail="not available to your role")
    return account


QueueDep = Annotated[StaffDep, Depends(_queue_access)]


def _visible_to(account: StaffDep, flag: FlagRow) -> bool:
    if account.role == "librarian" or account.is_stand_in:
        return True
    return flag.category == "escalated"


@router.get("/flags")
def flag_queue(
    account: QueueDep,
    db: sqlite3.Connection = Depends(get_db),
) -> HTMLResponse:
    flags = [flag for flag in open_flags(db) if _visible_to(account, flag)]
    rows = "".join(_queue_row_html(flag) for flag in flags)
    body = (
        "<h1>Flag queue</h1>"
        "<table><thead><tr>"
        "<th>Raised at</th><th>Category</th><th>Severity</th><th>Source</th>"
        "<th>Entry</th><th>Class</th><th>Card</th><th></th>"
        "</tr></thead><tbody>"
        f"{rows}"
        "</tbody></table>"
    )
    return page("Flag queue", body)


@router.get("/flags/{flag_id}")
def flag_page(
    flag_id: int,
    account: QueueDep,
    db: sqlite3.Connection = Depends(get_db),
) -> HTMLResponse:
    flag = get_flag(db, flag_id)
    if flag is None:
        raise HTTPException(status_code=404, detail="no such flag")
    if not _visible_to(account, flag):
        raise HTTPException(status_code=403, detail="not available to your role")
    transcript = db.execute(
        "SELECT question, answer FROM transcripts WHERE id = ?",
        (flag.transcript_id,),
    ).fetchone()
    question, answer = transcript if transcript else ("", "")
    body = (
        "<h1>Flag</h1>"
        "<table><tbody>"
        f"<tr><th>Raised at</th><td>{html.escape(flag.raised_at)}</td></tr>"
        f"<tr><th>Category</th><td>{html.escape(flag.category)}</td></tr>"
        f"<tr><th>Severity</th><td>{html.escape(flag.severity)}</td></tr>"
        f"<tr><th>Source</th><td>{html.escape(flag.source)}</td></tr>"
        f"<tr><th>Entry</th><td>{html.escape(str(flag.entry_id or ''))}</td></tr>"
        f"<tr><th>Class</th><td>{html.escape(flag.class_label)}</td></tr>"
        f"<tr><th>Card</th><td>{html.escape(flag.card_number)}</td></tr>"
        "</tbody></table>"
        f"<p><strong>Question</strong></p><p>{html.escape(question)}</p>"
        f"<p><strong>Answer</strong></p><p>{html.escape(answer)}</p>"
        '<form method="post" action="/staff/flags/'
        f'{flag.id}/close"><button>Close</button></form>'
    )
    response = page("Flag", body)
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/flags/{flag_id}/close", response_model=None)
def close_flag_route(
    flag_id: int,
    account: StandInDep,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
) -> RedirectResponse:
    flag = get_flag(db, flag_id)
    if flag is None:
        raise HTTPException(status_code=404, detail="no such flag")
    close_flag(db, flag_id, clock.isoformat())
    return RedirectResponse("/staff/flags", status_code=303)
