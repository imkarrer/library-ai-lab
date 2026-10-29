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
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from library_assistant.access import (
    get_clock,
    get_db,
    last_review_at,
    registering_teacher,
    review_due_at,
)
from library_assistant.alarm_banner import alarm_banner
from library_assistant.alarms import acknowledgement, announce_escalation
from library_assistant.config import Settings, get_settings
from library_assistant.flag_history import append_event, get_history
from library_assistant.flags import (
    OUTCOMES,
    FlagRow,
    close_flag,
    escalate_flag,
    get_flag,
    is_overdue,
    open_flags,
    reopen_flag,
)
from library_assistant.holds import active_hold_count
from library_assistant.purge import next_purge_at
from library_assistant.routers.live import LiveBus, get_live_bus
from library_assistant.staff import (
    LibrarianDep,
    StaffAccount,
    StaffDep,
    StandInDep,
    page,
    require_role,
)

router = APIRouter(prefix="/staff")


def _queue_row_html(flag: FlagRow, overdue: bool, teacher: str | None) -> str:
    return (
        "<tr>"
        f"<td>{html.escape(flag.raised_at)}</td>"
        f"<td>{html.escape(flag.category)}</td>"
        f"<td>{html.escape(flag.severity)}</td>"
        f"<td>{html.escape(flag.source)}</td>"
        f"<td>{html.escape(str(flag.entry_id or ''))}</td>"
        f"<td>{html.escape(flag.class_label)}</td>"
        f"<td>{html.escape(flag.card_number)}</td>"
        f"<td>{html.escape(teacher or '')}</td>"
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
    return flag.escalated_at is not None


def _acknowledged(db: sqlite3.Connection, flag_id: int) -> str:
    """Who Acknowledged the Flag's Alarm and when (ADR-0010), or blank."""
    ack = acknowledgement(db, flag_id)
    return html.escape(f"{ack[0]} at {ack[1]}") if ack else ""


def _counselor_exists(db: sqlite3.Connection) -> bool:
    return (
        db.execute(
            "SELECT 1 FROM staff_accounts WHERE role = 'counselor' LIMIT 1"
        ).fetchone()
        is not None
    )


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
        _queue_row_html(
            flag,
            is_overdue(flag, clock, settings.flags_overdue_days),
            registering_teacher(
                db, flag.class_label, flag.card_number, flag.batch_expires_at
            ),
        )
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

    # The active Hold count, for those who may work the whole queue (ADR-0003
    # addendum); a Counselor sees only Escalated Flags, and Holds would show them more.
    holds_info = ""
    if account.role == "librarian" or account.is_stand_in:
        holds_info = f"<p>Active Holds: {active_hold_count(db)}</p>"

    body = (
        "<h1>Flag queue</h1>"
        + alarm_banner(db, account, clock)
        + (f"<p>{header_info}</p>" if header_info else "")
        + holds_info
        + "<table><thead><tr>"
        "<th>Raised at</th><th>Category</th><th>Severity</th><th>Source</th>"
        "<th>Entry</th><th>Class</th><th>Card</th><th>Registered by</th>"
        "<th></th><th></th>"
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
    settings: Settings = Depends(get_settings),
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
    teacher = registering_teacher(
        db, flag.class_label, flag.card_number, flag.batch_expires_at
    )
    action = "reopen" if flag.closed_at is not None else "close"
    button = "Reopen" if flag.closed_at is not None else "Close"
    # A high-severity Flag that has not been exported needs the closer's explicit
    # confirmation, since closing it is what lets the Purge delete its exchange.
    needs_confirm = action == "close" and flag.severity == "high" and not flag.exported
    confirm_notice = (
        f"<p>Not yet exported. Next Purge: "
        f"{html.escape(next_purge_at(clock, settings).isoformat())}</p>"
        '<p><label><input type="checkbox" name="confirm" value="true"> '
        "The school does not need this exchange</label></p>"
        if needs_confirm
        else ""
    )
    form = (
        f'<form method="post" action="/staff/flags/{flag.id}/{action}">'
        + (
            '<p><label>Outcome <select name="outcome" required>'
            f"{outcome_options}</select></label></p>"
            if action == "close"
            else ""
        )
        + confirm_notice
        + '<p><label>Reason <input name="reason" required></label></p>'
        + f"<p><button>{button}</button></p></form>"
    )

    # Only the Librarian escalates, and only when a Counselor exists (ADR-0004).
    escalation_form = ""
    if (
        account.role == "librarian"
        and flag.closed_at is None
        and flag.escalated_at is None
        and _counselor_exists(db)
    ):
        escalation_form = (
            "<h2>Escalate</h2>"
            f'<form method="post" action="/staff/flags/{flag.id}/escalate">'
            '<p><label>Reason <input name="reason" required></label></p>'
            "<p><button>Escalate</button></p></form>"
        )
    body = (
        "<h1>Flag</h1>"
        f"{alarm_banner(db, account, clock)}"
        "<table><tbody>"
        f"<tr><th>Raised at</th><td>{html.escape(flag.raised_at)}</td></tr>"
        f"<tr><th>Category</th><td>{html.escape(flag.category)}</td></tr>"
        f"<tr><th>Severity</th><td>{html.escape(flag.severity)}</td></tr>"
        f"<tr><th>Source</th><td>{html.escape(flag.source)}</td></tr>"
        f"<tr><th>Entry</th><td>{html.escape(str(flag.entry_id or ''))}</td></tr>"
        f"<tr><th>Class</th><td>{html.escape(flag.class_label)}</td></tr>"
        f"<tr><th>Card</th><td>{html.escape(flag.card_number)}</td></tr>"
        f"<tr><th>Registered by</th><td>{html.escape(teacher or '')}</td></tr>"
        f"<tr><th>Repeats</th><td>{flag.repeat_count}</td></tr>"
        f"<tr><th>Raised unwatched</th><td>{'yes' if flag.raised_unwatched else ''}</td></tr>"
        f"<tr><th>Acknowledged</th><td>{_acknowledged(db, flag.id)}</td></tr>"
        "</tbody></table>"
        f'<p><a href="/staff/flags/{flag.id}/export">Export</a></p>'
        f"<p><strong>Question</strong></p><p>{html.escape(question)}</p>"
        f"<p><strong>Answer</strong></p><p>{html.escape(answer)}</p>"
        f"{form}"
        f"{escalation_form}"
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
    confirm: Annotated[bool, Form()] = False,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    flag = get_flag(db, flag_id)
    if flag is None:
        raise HTTPException(status_code=404, detail="no such flag")

    # A high-severity Flag that has not been exported needs the closer's explicit
    # confirmation, since closing it is what lets the Purge delete its exchange.
    if flag.severity == "high" and not flag.exported and not confirm:
        due_at = next_purge_at(clock, settings)
        raise HTTPException(
            status_code=400,
            detail=(
                "this high-severity Flag has not been exported; confirm to close "
                f"it anyway. Next Purge: {due_at.isoformat()}"
            ),
        )

    try:
        close_flag(db, flag_id, clock.isoformat(), account.username, outcome, reason)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return RedirectResponse("/staff/flags", status_code=303)


@router.get("/flags/{flag_id}/export")
def export_flag(
    flag_id: int,
    account: StaffDep,
    db: sqlite3.Connection = Depends(get_db),
) -> Response:
    """Export one Flag as a text/plain attachment: its own fields and its
    transcript's timed exchange, never a Token or hash or another Session's text."""
    flag = get_flag(db, flag_id)
    if flag is None:
        raise HTTPException(status_code=404, detail="no such flag")

    # A Counselor exports only an Escalated Flag; a Teacher exports nothing
    # (ADR-0003 addendum).
    if account.role == "teacher" or (
        account.role == "counselor" and flag.escalated_at is None
    ):
        raise HTTPException(status_code=403, detail="not available to your role")

    transcript = db.execute(
        "SELECT question, answer, asked_at FROM transcripts WHERE id = ?",
        (flag.transcript_id,),
    ).fetchone()
    question, answer, asked_at = transcript if transcript else ("", "", flag.raised_at)

    lines = [
        f"Class label: {flag.class_label}",
        f"Card number: {flag.card_number}",
        f"Date: {flag.raised_at}",
        f"Category: {flag.category}",
        f"Severity: {flag.severity}",
        f"Source: {flag.source}",
    ]
    teacher = registering_teacher(
        db, flag.class_label, flag.card_number, flag.batch_expires_at
    )
    if teacher:
        lines.append(f"Registered by: {teacher}")
    if flag.entry_id:
        lines.append(f"Matched entry: {flag.entry_id}")
    lines.append("")
    lines.append(f"Timed message at {asked_at}:")
    lines.append(f"  Question: {question}")
    lines.append(f"  Answer: {answer}")
    lines.append("")
    lines.append("History:")
    for event in get_history(db, flag_id):
        lines.append(
            f"  {event.at} {event.event} by {event.account or ''}"
            + (f" outcome={event.outcome}" if event.outcome else "")
            + (f" reason={event.reason}" if event.reason else "")
        )
    export_content = "\n".join(lines) + "\n"

    db.execute("UPDATE flags SET exported = 1 WHERE id = ?", (flag_id,))
    db.commit()

    response = Response(content=export_content, media_type="text/plain")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Disposition"] = (
        f'attachment; filename="flag-{flag_id}-export.txt"'
    )
    return response


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


@router.post("/flags/{flag_id}/escalate", response_model=None)
def escalate_flag_route(
    flag_id: int,
    account: LibrarianDep,
    reason: Annotated[str, Form()] = "",
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
    bus: LiveBus = Depends(get_live_bus),
) -> RedirectResponse:
    """Escalate a Flag to the Counselor (ADR-0004: only when a Counselor exists). An
    open Counselor page hears of it at once, with no exchange text (ADR-0010)."""
    if not _counselor_exists(db):
        raise HTTPException(status_code=409, detail="no counselor account exists")
    flag = get_flag(db, flag_id)
    if flag is None:
        raise HTTPException(status_code=404, detail="no such flag")
    if flag.escalated_at is not None:
        raise HTTPException(status_code=409, detail="flag is already escalated")
    if not reason.strip():
        raise HTTPException(status_code=400, detail="reason required")
    escalate_flag(db, flag_id, clock.isoformat(), account.id, account.username, reason)
    announce_escalation(db, bus.publish, flag_id)
    return RedirectResponse(f"/staff/flags/{flag_id}", status_code=303)


@router.get("/counselor")
def counselor_flag_queue(
    account: Annotated[StaffAccount, Depends(require_role("counselor"))],
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """Counselor-only: show only Escalated Flags, each with Class label, Card number,
    Registered by (the lookup lib-90j.2 adds), category, severity and raised_at,
    linking to GET /staff/counselor/flags/{id}. (ADR-0004 addendum)"""
    # Get all open flags that are escalated
    escalated_flags = [flag for flag in open_flags(db) if flag.escalated_at is not None]

    def _counselor_queue_row_html(
        flag: FlagRow, overdue: bool, teacher: str | None
    ) -> str:
        return (
            "<tr>"
            f"<td>{html.escape(flag.raised_at)}</td>"
            f"<td>{html.escape(flag.category)}</td>"
            f"<td>{html.escape(flag.severity)}</td>"
            f"<td>{html.escape(flag.source)}</td>"
            f"<td>{html.escape(str(flag.entry_id or ''))}</td>"
            f"<td>{html.escape(flag.class_label)}</td>"
            f"<td>{html.escape(flag.card_number)}</td>"
            f"<td>{html.escape(teacher or '')}</td>"
            f"<td>{'Overdue' if overdue else ''}</td>"
            f'<td><a href="/staff/counselor/flags/{flag.id}">View</a></td>'
            "</tr>"
        )

    rows = "".join(
        _counselor_queue_row_html(
            flag,
            is_overdue(flag, clock, settings.flags_overdue_days),
            registering_teacher(
                db, flag.class_label, flag.card_number, flag.batch_expires_at
            ),
        )
        for flag in escalated_flags
    )

    body = (
        "<h1>Counselor flag queue</h1>"
        f"{alarm_banner(db, account, clock)}"
        "<table><thead><tr>"
        "<th>Raised at</th><th>Category</th><th>Severity</th><th>Source</th>"
        "<th>Entry</th><th>Class</th><th>Card</th><th>Registered by</th>"
        "<th></th><th></th>"
        "</tr></thead><tbody>"
        f"{rows}"
        "</tbody></table>"
    )
    return page("Counselor flag queue", body)


@router.get("/counselor/flags/{flag_id}")
def counselor_flag_page(
    flag_id: int,
    account: Annotated[StaffAccount, Depends(require_role("counselor"))],
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """Counselor-only: show a Flag detail page with Cache-Control: no-store,
    and record 'viewed' with lib-ce5.1's history function. 404 for a Flag that is not escalated."""
    flag = get_flag(db, flag_id)
    if flag is None:
        raise HTTPException(status_code=404, detail="no such flag")
    if flag.escalated_at is None:
        raise HTTPException(status_code=404, detail="flag is not escalated")

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
    teacher = registering_teacher(
        db, flag.class_label, flag.card_number, flag.batch_expires_at
    )
    action = "reopen" if flag.closed_at is not None else "close"
    button = "Reopen" if flag.closed_at is not None else "Close"
    # A high-severity Flag that has not been exported needs the closer's explicit
    # confirmation, since closing it is what lets the Purge delete its exchange.
    needs_confirm = action == "close" and flag.severity == "high" and not flag.exported
    confirm_notice = (
        f"<p>Not yet exported. Next Purge: "
        f"{html.escape(next_purge_at(clock, settings).isoformat())}</p>"
        '<p><label><input type="checkbox" name="confirm" value="true"> '
        "The school does not need this exchange</label></p>"
        if needs_confirm
        else ""
    )
    form = (
        f'<form method="post" action="/staff/flags/{flag.id}/{action}">'
        + (
            '<p><label>Outcome <select name="outcome" required>'
            f"{outcome_options}</select></label></p>"
            if action == "close"
            else ""
        )
        + confirm_notice
        + '<p><label>Reason <input name="reason" required></label></p>'
        + f"<p><button>{button}</button></p></form>"
    )

    # Only the Librarian escalates, and only when a Counselor exists (ADR-0004).
    escalation_form = ""
    if (
        account.role == "librarian"
        and flag.closed_at is None
        and flag.escalated_at is None
        and _counselor_exists(db)
    ):
        escalation_form = (
            "<h2>Escalate</h2>"
            f'<form method="post" action="/staff/flags/{flag.id}/escalate">'
            '<p><label>Reason <input name="reason" required></label></p>'
            "<p><button>Escalate</button></p></form>"
        )
    body = (
        "<h1>Flag</h1>"
        f"{alarm_banner(db, account, clock)}"
        "<table><tbody>"
        f"<tr><th>Raised at</th><td>{html.escape(flag.raised_at)}</td></tr>"
        f"<tr><th>Category</th><td>{html.escape(flag.category)}</td></tr>"
        f"<tr><th>Severity</th><td>{html.escape(flag.severity)}</td></tr>"
        f"<tr><th>Source</th><td>{html.escape(flag.source)}</td></tr>"
        f"<tr><th>Entry</th><td>{html.escape(str(flag.entry_id or ''))}</td></tr>"
        f"<tr><th>Class</th><td>{html.escape(flag.class_label)}</td></tr>"
        f"<tr><th>Card</th><td>{html.escape(flag.card_number)}</td></tr>"
        f"<tr><th>Registered by</th><td>{html.escape(teacher or '')}</td></tr>"
        f"<tr><th>Repeats</th><td>{flag.repeat_count}</td></tr>"
        f"<tr><th>Raised unwatched</th><td>{'yes' if flag.raised_unwatched else ''}</td></tr>"
        f"<tr><th>Acknowledged</th><td>{_acknowledged(db, flag.id)}</td></tr>"
        "</tbody></table>"
        f'<p><a href="/staff/flags/{flag.id}/export">Export</a></p>'
        f"<p><strong>Question</strong></p><p>{html.escape(question)}</p>"
        f"<p><strong>Answer</strong></p><p>{html.escape(answer)}</p>"
        f"{form}"
        f"{escalation_form}"
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
