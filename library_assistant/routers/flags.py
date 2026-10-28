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

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from library_assistant.access import get_clock, get_db, last_review_at, review_due_at
from library_assistant.config import Settings, get_settings
from library_assistant.flag_history import append_event, get_history
from library_assistant.flags import (
    OUTCOMES,
    FlagRow,
    close_flag,
    get_flag,
    is_overdue,
    open_flags,
    reopen_flag,
)
from library_assistant.staff import StaffDep, StandInDep, page

router = APIRouter(prefix="/staff")


def _queue_row_html(flag: FlagRow, overdue: bool) -> str:
    return (
        "<tr>"
        f"<td>{html.escape(flag.raised_at)}</td>"
        f"<td>{html.escape(flag.category)}</td>"
        f"<td>{html.escape(flag.severity)}</td>"
        f"<td>{html.escape(flag.source)}</td>"
        f"<td>{html.escape(str(flag.entry_id or ''))}</td>"
        f"<td>{html.escape(flag.class_label)}</td>"
        f"<td>{html.escape(flag.card_number)}</td>"
        f"<td>{'Overdue' if overdue else ''}</td>"
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


def _get_settings_dict(db: sqlite3.Connection) -> dict[str, str]:
    """Get all settings as a dictionary."""
    rows = db.execute("SELECT key, value FROM install_settings").fetchall()
    return dict(rows)


@router.post("/flags/reviewed", response_model=None)
def mark_reviewed(
    account: StandInDep,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
) -> RedirectResponse:
    """Mark that a flag review has been performed."""
    # Record the review
    db.execute(
        "INSERT INTO flag_reviews (account_id, reviewed_at) VALUES (?, ?)",
        (account.id, clock.isoformat()),
    )
    db.commit()
    # Redirect back to the flag queue
    return RedirectResponse("/staff/flags", status_code=303)


@router.get("/flags")
def flag_queue(
    account: QueueDep,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    # Get all settings
    settings_dict = _get_settings_dict(db)

    # Get review information
    last_review = last_review_at(db)
    due_at = review_due_at(db, settings_dict, clock)

    flags = [flag for flag in open_flags(db) if _visible_to(account, flag)]
    rows = "".join(
        _queue_row_html(flag, is_overdue(flag, clock, settings.flags_overdue_days))
        for flag in flags
    )

    # Build header information
    header_info = ""
    supervision_mode = settings_dict.get("supervision_mode", "live")
    if supervision_mode == "periodic":
        if last_review:
            # Format last review time and username
            last_review_str = last_review.strftime("%H:%M")
            # Get username for the last review (we'll need to get this from account_id)
            last_review_account = db.execute(
                "SELECT username FROM staff_accounts WHERE id = (SELECT account_id FROM flag_reviews WHERE reviewed_at = ?)",
                (last_review.isoformat(),),
            ).fetchone()
            last_review_username = (
                last_review_account[0] if last_review_account else "Unknown"
            )
            header_info += (
                f"Last reviewed {last_review_str} by {last_review_username}, "
            )

        if due_at:
            due_str = due_at.strftime("%H:%M")
            header_info += f"next due {due_str}"

            # Add "overdue" if past due
            if clock > due_at:
                header_info += " (overdue)"

    body = (
        f"<h1>Flag queue</h1><p>{header_info}</p>"
        if header_info
        else ""
        "<table><thead><tr>"
        "<th>Raised at</th><th>Category</th><th>Severity</th><th>Source</th>"
        "<th>Entry</th><th>Class</th><th>Card</th><th></th><th></th>"
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
    clock: datetime = Depends(get_clock),
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
    append_event(db, flag_id, "viewed", at=clock.isoformat(), account=account.username)
    history_rows = "".join(
        "<tr>"
        f"<td>{html.escape(event.at)}</td>"
        f"<td>{html.escape(event.event)}</td>"
        f"<td>{html.escape(event.account or '')}</td>"
        f"<td>{html.escape(event.outcome or '')}</td>"
        f"<td>{html.escape(event.reason or '')}</td>"
        "</tr>"
        for event in get_history(db, flag_id)
    )
    outcome_options = "".join(
        f'<option value="{html.escape(outcome)}">{html.escape(outcome)}</option>'
        for outcome in OUTCOMES
    )
    action = "reopen" if flag.closed_at is not None else "close"
    button = "Reopen" if flag.closed_at is not None else "Close"
    form = (
        f'<form method="post" action="/staff/flags/{flag.id}/{action}">'
        + (
            '<p><label>Outcome <select name="outcome" required>'
            f"{outcome_options}</select></label></p>"
            if action == "close"
            else ""
        )
        + '<p><label>Reason <input name="reason" required></label></p>'
        + f"<p><button>{button}</button></p></form>"
    )
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
        f"<tr><th>Repeats</th><td>{flag.repeat_count}</td></tr>"
        "</tbody></table>"
        f"<p><strong>Question</strong></p><p>{html.escape(question)}</p>"
        f"<p><strong>Answer</strong></p><p>{html.escape(answer)}</p>"
        f"{form}"
        "<h2>History</h2>"
        "<table><thead><tr>"
        "<th>At</th><th>Event</th><th>Account</th><th>Outcome</th><th>Reason</th>"
        "</tr></thead><tbody>"
        f"{history_rows}"
        "</tbody></table>"
    )
    response = page("Flag", body)
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/flags/{flag_id}/close", response_model=None)
def close_flag_route(
    flag_id: int,
    account: StandInDep,
    outcome: Annotated[str, Form()],
    reason: Annotated[str, Form()],
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
) -> RedirectResponse:
    flag = get_flag(db, flag_id)
    if flag is None:
        raise HTTPException(status_code=404, detail="no such flag")
    try:
        close_flag(db, flag_id, clock.isoformat(), account.username, outcome, reason)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return RedirectResponse("/staff/flags", status_code=303)


@router.post("/flags/{flag_id}/reopen", response_model=None)
def reopen_flag_route(
    flag_id: int,
    account: StandInDep,
    reason: Annotated[str, Form()],
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
) -> RedirectResponse:
    flag = get_flag(db, flag_id)
    if flag is None:
        raise HTTPException(status_code=404, detail="no such flag")
    try:
        reopen_flag(db, flag_id, clock.isoformat(), account.username, reason)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return RedirectResponse(f"/staff/flags/{flag_id}", status_code=303)
