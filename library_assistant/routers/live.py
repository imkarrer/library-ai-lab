"""The Live view overview: a tile per active Session (CONTEXT.md).

Binding: ADR-0002 (no Card-to-Student link), ADR-0003 addendum (`no-store`, no copies).
A tile shows only the Class label, Card number, and conversation shape; it never shows a
name, a Token or its stored hash, or Roster data. See `docs/design/live-view.md`.
"""

from __future__ import annotations

import html
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from library_assistant.access import get_clock, get_db
from library_assistant.dependencies import get_catalog
from library_assistant.models import Citation
from library_assistant.staff import LibrarianDep, page

LATEST_QUESTION_LIMIT = 80


@dataclass(frozen=True)
class SessionTile:
    """session_no is the sessions row's SQLite rowid: opaque, and never the hash."""

    session_no: int
    class_label: str
    card_number: str
    last_activity_at: datetime
    message_count: int
    latest_question: str
    flag_severity: str | None = None


@dataclass(frozen=True)
class Exchange:
    """A question-answer exchange with citations."""

    asked_at: datetime
    question: str
    answer: str
    citations: list[Citation]


def _truncate(question: str) -> str:
    if len(question) <= LATEST_QUESTION_LIMIT:
        return question
    return question[:LATEST_QUESTION_LIMIT] + "..."


def active_sessions(db: sqlite3.Connection, now: datetime) -> list[SessionTile]:
    """Sessions whose Card row still exists and has not expired, most recent activity first."""
    rows = db.execute(
        "SELECT sessions.rowid, sessions.session_hash, cards.class_label, "
        "cards.card_number, sessions.started_at "
        "FROM sessions JOIN cards ON cards.token_hash = sessions.token_hash "
        "WHERE cards.expires_at > ?",
        (now.isoformat(),),
    ).fetchall()

    # Get all open flags and their transcript_ids
    flag_rows = db.execute(
        "SELECT flags.transcript_id, flags.severity "
        "FROM flags "
        "WHERE flags.closed_at IS NULL"
    ).fetchall()

    # Map transcript_id to highest severity ('high' > 'low')
    transcript_severity = {}
    for transcript_id, severity in flag_rows:
        current = transcript_severity.get(transcript_id)
        if current is None or (severity == "high" and current != "high"):
            transcript_severity[transcript_id] = severity

    tiles = []
    for session_no, session_hash, class_label, card_number, started_at in rows:
        transcript_rows = db.execute(
            "SELECT id, question, asked_at FROM transcripts WHERE session_hash = ? "
            "ORDER BY asked_at DESC",
            (session_hash,),
        ).fetchall()
        if transcript_rows:
            latest_question = _truncate(transcript_rows[0][1])
            last_activity_at = datetime.fromisoformat(transcript_rows[0][2])
        else:
            latest_question = ""
            last_activity_at = datetime.fromisoformat(started_at)

        # Find the highest severity flag for this session
        flag_severity = None
        for transcript_id, severity in transcript_severity.items():
            # Join with transcripts to match session_hash
            transcript = db.execute(
                "SELECT session_hash FROM transcripts WHERE id = ?", (transcript_id,)
            ).fetchone()
            if transcript and transcript[0] == session_hash:
                # High severity overrides any lower severity
                if severity == "high":
                    flag_severity = "high"
                    break
                # For low severity, only set if no severity yet
                elif severity == "low" and flag_severity is None:
                    flag_severity = "low"

        tiles.append(
            SessionTile(
                session_no=session_no,
                class_label=class_label,
                card_number=card_number,
                last_activity_at=last_activity_at,
                message_count=len(transcript_rows),
                latest_question=latest_question,
                flag_severity=flag_severity,
            )
        )

    tiles.sort(key=lambda tile: tile.last_activity_at, reverse=True)
    return tiles


def _tile_html(tile: SessionTile) -> str:
    classes = ["tile"]
    if tile.flag_severity:
        classes.append(f"flag-{tile.flag_severity}")

    class_attr = " ".join(classes)

    badge = ""
    if tile.flag_severity:
        badge = f'<span class="flag-badge">Flag: {tile.flag_severity}</span>'

    return (
        f'<div class="{class_attr}">'
        f'<a href="/staff/live/sessions/{tile.session_no}">'
        f"<p>{html.escape(tile.class_label)} &middot; card {html.escape(tile.card_number)}</p>"
        f"<p>Last activity: {html.escape(tile.last_activity_at.isoformat())}</p>"
        f"<p>{tile.message_count} message(s)</p>"
        f"<p>{html.escape(tile.latest_question)}</p>"
        f"{badge}"
        "</a></div>"
    )


def _exchange_html(exchange: Exchange, catalog) -> str:
    """Render an exchange with citations resolved from the catalog."""
    citation_html = ""
    if exchange.citations:
        citation_html = '<div class="citations">'
        for citation in exchange.citations:
            record = catalog.get(citation.record_id)
            title = record.title if record else citation.record_id
            citation_html += f'<p><a href="/staff/catalog/record/{citation.record_id}">{html.escape(title)}</a></p>'
        citation_html += "</div>"

    return (
        '<div class="exchange">'
        f"<p><strong>Asked at:</strong> {html.escape(exchange.asked_at.isoformat())}</p>"
        f"<p><strong>Question:</strong> {html.escape(exchange.question)}</p>"
        f"<p><strong>Answer:</strong> {html.escape(exchange.answer)}</p>"
        f"{citation_html}"
        "</div>"
    )


def session_detail(
    session_no: int,
    db: sqlite3.Connection,
    catalog,
    now: datetime,
) -> tuple[str, str, list[Exchange]]:
    """Get session detail data for a given session number.

    Returns: (class_label, card_number, exchanges)
    """
    # Get session information
    session_row = db.execute(
        "SELECT sessions.rowid, sessions.session_hash, cards.class_label, "
        "cards.card_number, sessions.started_at "
        "FROM sessions JOIN cards ON cards.token_hash = sessions.token_hash "
        "WHERE sessions.rowid = ?",
        (session_no,),
    ).fetchone()

    if not session_row:
        # Check if it's an ended session (Finished or expired)
        ended_session = db.execute(
            "SELECT 1 FROM sessions WHERE rowid = ?",
            (session_no,),
        ).fetchone()
        if not ended_session:
            raise HTTPException(status_code=404, detail="Session not found")
        else:
            # Session exists but is ended (Finished or expired)
            raise HTTPException(status_code=404, detail="Session not found")

    session_hash = session_row[1]
    class_label = session_row[2]
    card_number = session_row[3]

    # Get exchanges ordered by asked_at ascending (oldest first)
    transcript_rows = db.execute(
        "SELECT asked_at, question, answer, citations FROM transcripts "
        "WHERE session_hash = ? "
        "ORDER BY asked_at ASC",
        (session_hash,),
    ).fetchall()

    exchanges = []
    for asked_at_str, question, answer, citations_str in transcript_rows:
        asked_at = datetime.fromisoformat(asked_at_str)

        # Parse citations
        citations = []
        if citations_str:
            citation_ids = citations_str.split(",")
            for record_id in citation_ids:
                if record_id:
                    # Get the record from catalog to populate citation fields
                    record = catalog.get(record_id)
                    if record:
                        citations.append(
                            Citation(
                                record_id=record_id,
                                title=record.title,
                                call_number=record.call_number,
                            )
                        )
                    else:
                        # If record not found, create citation with minimal info
                        citations.append(
                            Citation(
                                record_id=record_id,
                                title=record_id,
                                call_number=record_id,
                            )
                        )

        exchanges.append(
            Exchange(
                asked_at=asked_at,
                question=question,
                answer=answer,
                citations=citations,
            )
        )

    return class_label, card_number, exchanges


router = APIRouter(prefix="/staff")


@router.get("/live")
def live_view(
    account: LibrarianDep,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
) -> HTMLResponse:
    """The overview: one tile per active Session, no forms or buttons, safe to leave on screen."""
    tiles = active_sessions(db, clock)
    body = (
        "".join(_tile_html(tile) for tile in tiles)
        if tiles
        else "<p>No active Sessions.</p>"
    )
    response = page("Live view", f"<h1>Live view</h1>{body}")
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/live/sessions/{session_no}")
def session_detail_view(
    session_no: int,
    account: LibrarianDep,
    db: sqlite3.Connection = Depends(get_db),
    catalog=Depends(get_catalog),
    clock: datetime = Depends(get_clock),
) -> HTMLResponse:
    """The Session detail view: questions, answers, and Citations."""
    class_label, card_number, exchanges = session_detail(session_no, db, catalog, clock)

    # Build HTML for exchanges
    exchange_html = "".join(_exchange_html(exchange, catalog) for exchange in exchanges)

    # Build page content
    content = (
        f"<h1>Session Detail</h1>"
        f"<p><strong>Class:</strong> {html.escape(class_label)}</p>"
        f"<p><strong>Card:</strong> {html.escape(card_number)}</p>"
        f'<p><a href="/staff/live">← Back to Live view</a></p>'
        f'<div class="exchanges">{exchange_html}</div>'
    )

    response = page("Session Detail", content)
    response.headers["Cache-Control"] = "no-store"
    return response
