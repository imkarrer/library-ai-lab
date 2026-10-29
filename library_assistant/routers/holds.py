"""The Holds page: set, list, and lift Holds (ADR-0003 addendum, "Holds").

Only the Librarian may see or use it: a Counselor sees only Escalated Flags, and a Hold
would show them more. There is no edit route; to narrow a Hold, set the narrower one and
lift the broad one. The page shows what each Hold holds as a count, never transcript text.
"""

from __future__ import annotations

import html
import sqlite3
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from library_assistant.access import get_clock, get_db
from library_assistant.config import Settings, get_settings
from library_assistant.holds import (
    REASON_KINDS,
    Hold,
    all_holds,
    get_hold,
    held_transcript_count,
    held_transcripts,
    lift_hold,
    set_hold,
)
from library_assistant.staff import LibrarianDep, page

router = APIRouter(prefix="/staff/holds")


def _split(raw: str) -> list[str]:
    return [part for part in raw.split(",") if part.strip()]


def _scope_text(hold: Hold) -> str:
    classes = "all classes" if hold.all_classes else ", ".join(hold.class_labels)
    cards = ", ".join(hold.card_numbers) if hold.card_numbers else "all cards"
    return (
        f"{classes}; {cards}; "
        f"{hold.date_from.isoformat()} to {hold.date_to.isoformat()}"
    )


def _scope_html(hold: Hold) -> str:
    return html.escape(_scope_text(hold))


def _hold_row_html(hold: Hold, now: datetime, held: int) -> str:
    age_days = (now - datetime.fromisoformat(hold.set_at)).days
    if hold.active:
        status = "Review due" if hold.review_marked_at else "Active"
        action = (
            f'<form method="post" action="/staff/holds/{hold.id}/lift">'
            '<label>Lift reason <input name="reason" required></label> '
            "<button>Lift</button></form>"
        )
    else:
        status = f"Lifted {html.escape(hold.lifted_at or '')}: " + html.escape(
            hold.lift_reason or ""
        )
        action = ""
    return (
        "<tr>"
        f"<td>{hold.id}</td>"
        f"<td>{_scope_html(hold)}</td>"
        f"<td>{html.escape(hold.reason_kind)}</td>"
        f"<td>{html.escape(hold.reference)}</td>"
        f"<td>{html.escape(hold.set_by)}, {age_days} days ago</td>"
        f"<td>{held} transcripts</td>"
        f"<td>{status}</td>"
        f'<td><a href="/staff/holds/{hold.id}/export">Export</a> {action}</td>'
        "</tr>"
    )


def _set_form_html() -> str:
    kinds = "".join(
        f'<option value="{html.escape(kind)}">{html.escape(kind)}</option>'
        for kind in REASON_KINDS
    )
    return (
        "<h2>Set a Hold</h2>"
        '<form method="post" action="/staff/holds">'
        '<p><label><input type="checkbox" name="all_classes" value="true"> '
        "All classes</label></p>"
        '<p><label>Class labels (comma-separated) <input name="class_labels">'
        "</label></p>"
        '<p><label>From <input type="date" name="date_from" required></label> '
        '<label>To <input type="date" name="date_to" required></label></p>'
        '<p><label>Card numbers, if known (comma-separated) <input name="card_numbers">'
        "</label></p>"
        f'<p><label>Reason <select name="reason_kind" required>{kinds}</select>'
        "</label></p>"
        '<p><label>Reference <input name="reference" required></label> '
        "Must not name anyone.</p>"
        "<p><button>Set Hold</button></p></form>"
    )


@router.get("")
def holds_page(
    account: LibrarianDep,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    rows = "".join(
        _hold_row_html(hold, clock, held_transcript_count(db, hold, settings))
        for hold in all_holds(db)
    )
    body = (
        "<h1>Holds</h1>"
        "<p>A Hold keeps every record in its scope from the Purge until it is lifted. "
        "It cannot bring back anything already purged.</p>"
        "<table><thead><tr>"
        "<th>Hold</th><th>Scope</th><th>Reason</th><th>Reference</th><th>Set</th>"
        "<th>Holds</th><th>Status</th><th></th>"
        "</tr></thead><tbody>"
        f"{rows}"
        "</tbody></table>"
        f"{_set_form_html()}"
    )
    response = page("Holds", body, account=account, db=db, now=clock)
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("", response_model=None)
def set_hold_route(
    account: LibrarianDep,
    date_from: Annotated[date, Form()],
    date_to: Annotated[date, Form()],
    reason_kind: Annotated[str, Form()],
    reference: Annotated[str, Form()],
    all_classes: Annotated[bool, Form()] = False,
    class_labels: Annotated[str, Form()] = "",
    card_numbers: Annotated[str, Form()] = "",
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
) -> RedirectResponse:
    try:
        set_hold(
            db,
            all_classes=all_classes,
            class_labels=_split(class_labels),
            card_numbers=_split(card_numbers),
            date_from=date_from,
            date_to=date_to,
            reason_kind=reason_kind,
            reference=reference,
            set_at=clock,
            set_by=account.username,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return RedirectResponse("/staff/holds", status_code=303)


@router.get("/{hold_id}/export")
def export_hold(
    hold_id: int,
    account: LibrarianDep,
    db: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Export everything in a Hold's scope as a text/plain attachment: nothing
    outside its scope, and nothing from any other Hold."""
    hold = get_hold(db, hold_id)
    if hold is None:
        raise HTTPException(status_code=404, detail="no such Hold")

    lines = [
        f"Hold: {hold.id}",
        f"Scope: {_scope_text(hold)}",
        f"Reason: {hold.reason_kind}",
        f"Reference: {hold.reference}",
        f"Set by: {hold.set_by} at {hold.set_at}",
        "",
    ]
    for class_label, card_number, asked_at, question, answer in held_transcripts(
        db, hold, settings
    ):
        lines.append(f"Class label: {class_label}")
        lines.append(f"Card number: {card_number}")
        lines.append(f"Timed message at {asked_at}:")
        lines.append(f"  Question: {question}")
        lines.append(f"  Answer: {answer}")
        lines.append("")
    export_content = "\n".join(lines) + "\n"

    response = Response(content=export_content, media_type="text/plain")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Disposition"] = (
        f'attachment; filename="hold-{hold_id}-export.txt"'
    )
    return response


@router.post("/{hold_id}/lift", response_model=None)
def lift_hold_route(
    hold_id: int,
    account: LibrarianDep,
    reason: Annotated[str, Form()],
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
) -> RedirectResponse:
    if get_hold(db, hold_id) is None:
        raise HTTPException(status_code=404, detail="no such Hold")
    try:
        lift_hold(db, hold_id, clock, account.username, reason)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return RedirectResponse("/staff/holds", status_code=303)
