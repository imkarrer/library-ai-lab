"""The Live view overview: a tile per active Session (CONTEXT.md).

Binding: ADR-0002 (no Card-to-Student link), ADR-0003 addendum (`no-store`, no copies).
A tile shows the Class label, Card number, conversation shape, and the registering
Teacher's display name (ADR-0002 addendum); it never shows a Student's name, a Token or
its stored hash, or Roster data. See `docs/design/live-view.md`.

The pages stay live through the LiveBus: `/ask` publishes to it in process (ADR-0008) and
each open Live view page holds one server-sent event stream from it. The bus keeps
nothing: a message reaches only the streams open when it is published. The same stream
sends a `ping` event every 20 s, which each page answers with a Watch heartbeat
(ADR-0010, `library_assistant.watch`).
"""

from __future__ import annotations

import asyncio
import html
import json
import sqlite3
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from library_assistant.access import (
    get_clock,
    get_db,
    registering_teacher,
    revoke_batch_of_session,
    revoke_card_of_session,
)
from library_assistant.alarm_banner import alarm_banner
from library_assistant.catalog import Catalog
from library_assistant.config import Settings
from library_assistant.dependencies import get_catalog, get_settings
from library_assistant.models import Citation
from library_assistant.oversight import ScreeningState, get_screening_state
from library_assistant.staff import LibrarianDep, StandInDep, page
from library_assistant.watch import is_watching

LATEST_QUESTION_LIMIT = 80

PING_INTERVAL_SECONDS = 20

# A page that stops reading loses messages past this many rather than growing memory.
SUBSCRIBER_QUEUE_LIMIT = 256

Message = tuple[str, dict]


class LiveBus:
    """In-process fan-out from `/ask` to the open Live view streams (ADR-0008)."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[Message]] = set()

    def subscribe(self) -> asyncio.Queue[Message]:
        queue: asyncio.Queue[Message] = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_LIMIT)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Message]) -> None:
        self._subscribers.discard(queue)

    def publish(self, kind: str, data: dict) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait((kind, data))
            except asyncio.QueueFull:
                pass


live_bus = LiveBus()


def get_live_bus() -> LiveBus:
    return live_bus


async def _ping_wait() -> None:
    await asyncio.sleep(PING_INTERVAL_SECONDS)


def get_ping_wait() -> Callable[[], Awaitable[None]]:
    """The wait between pings; tests override it so nothing sleeps."""
    return _ping_wait


def sse_message(kind: str, data: dict) -> str:
    return f"event: {kind}\ndata: {json.dumps(data)}\n\n"


# A named event, not an SSE comment: a page's EventSource never sees a comment, and the
# page answers each ping with a Watch heartbeat.
PING = sse_message("ping", {})


async def event_stream(
    bus: LiveBus,
    queue: asyncio.Queue[Message],
    wait: Callable[[], Awaitable[None]],
    allow: Callable[[str, dict], bool] | None = None,
) -> AsyncIterator[str]:
    """One SSE event per published message, and a `ping` event each time `wait` returns.
    With `allow`, only the messages it passes (a Counselor's stream hears only
    Escalations, never a question or an answer).

    A pending read survives a ping, so no message is lost to one, and a pending ping
    survives a message, so a busy class does not hold back the Watch heartbeat. Closing
    the stream (the page goes away) unsubscribes the queue.
    """
    next_message: asyncio.Future | None = None
    ping: asyncio.Future | None = None
    try:
        while True:
            if next_message is None:
                next_message = asyncio.ensure_future(queue.get())
            if ping is None:
                ping = asyncio.ensure_future(wait())
            done, _ = await asyncio.wait(
                {next_message, ping}, return_when=asyncio.FIRST_COMPLETED
            )
            if next_message in done:
                kind, data = next_message.result()
                next_message = None
                if allow is None or allow(kind, data):
                    yield sse_message(kind, data)
            else:
                done_ping, ping = ping, None
                done_ping.result()  # a failed wait ends the stream, never spins
                yield PING
    finally:
        for task in (next_message, ping):
            if task is not None:
                task.cancel()
        bus.unsubscribe(queue)


@dataclass(frozen=True)
class SessionTile:
    """session_no is the sessions row's SQLite rowid: opaque, and never the hash."""

    session_no: int
    class_label: str
    card_number: str
    last_activity_at: datetime
    message_count: int
    latest_question: str
    registered_by: str | None = None
    flag_severity: str | None = None


@dataclass(frozen=True)
class Exchange:
    """A question-answer exchange with citations."""

    asked_at: datetime
    question: str
    answer: str
    citations: list[Citation]
    transcript_id: int | None = None


def _truncate(question: str) -> str:
    if len(question) <= LATEST_QUESTION_LIMIT:
        return question
    return question[:LATEST_QUESTION_LIMIT] + "..."


def active_sessions(db: sqlite3.Connection, now: datetime) -> list[SessionTile]:
    """Sessions whose Card row still exists and has not expired, most recent activity first."""
    rows = db.execute(
        "SELECT sessions.rowid, sessions.session_hash, cards.class_label, "
        "cards.card_number, sessions.started_at, cards.expires_at "
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
    for (
        session_no,
        session_hash,
        class_label,
        card_number,
        started_at,
        card_expires_at,
    ) in rows:
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
                registered_by=registering_teacher(
                    db, class_label, card_number, card_expires_at
                ),
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

    registered_by_html = ""
    if tile.registered_by:
        registered_by_html = (
            f'<p class="registered-by">Registered by '
            f"{html.escape(tile.registered_by)}</p>"
        )

    return (
        f'<div class="{class_attr}" data-session-no="{tile.session_no}" '
        f'data-message-count="{tile.message_count}">'
        f'<a href="/staff/live/sessions/{tile.session_no}">'
        f'<p class="who">{html.escape(tile.class_label)} &middot; '
        f"card {html.escape(tile.card_number)}</p>"
        '<p class="when">Last activity: '
        f"{html.escape(tile.last_activity_at.isoformat())}</p>"
        f'<p class="count">{tile.message_count} message(s)</p>'
        f'<p class="latest">{html.escape(tile.latest_question)}</p>'
        f"{badge}"
        f"{registered_by_html}"
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
        f'<div class="exchange" data-transcript-id="{exchange.transcript_id}">'
        f"<p><strong>Asked at:</strong> {html.escape(exchange.asked_at.isoformat())}</p>"
        f"<p><strong>Question:</strong> {html.escape(exchange.question)}</p>"
        "<p><strong>Answer:</strong> "
        f'<span class="answer">{html.escape(exchange.answer)}</span></p>'
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
        "SELECT id, asked_at, question, answer, citations FROM transcripts "
        "WHERE session_hash = ? "
        "ORDER BY asked_at ASC",
        (session_hash,),
    ).fetchall()

    exchanges = []
    for transcript_id, asked_at_str, question, answer, citations_str in transcript_rows:
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
                transcript_id=transcript_id,
            )
        )

    return class_label, card_number, exchanges


router = APIRouter(prefix="/staff")

# Each ping on the stream is answered with a heartbeat. The page answers network events,
# not its own timers, which browsers slow in background tabs (ADR-0010). A heartbeat from
# an account that is not on Watch changes nothing.
HEARTBEAT_SCRIPT = """  source.addEventListener("ping", () => {
    fetch("/staff/watch/heartbeat", { method: "POST", credentials: "same-origin" })
      .then((response) => {
        document.dispatchEvent(
          new CustomEvent("watch", { detail: { watching: response.ok } })
        );
      });
  });"""

# The overview's one control: Start watch / End watch for this account (ADR-0010). It
# changes no Session, so the overview stays safe to leave on screen or share.
WATCH_CONTROL = """<p id="watch"><span id="watch-status">__STATUS__</span>
<button id="watch-toggle" type="button" data-watching="__WATCHING__">__LABEL__</button></p>
<script>
(() => {
  const button = document.getElementById("watch-toggle");
  const status = document.getElementById("watch-status");
  const show = (watching) => {
    button.dataset.watching = watching ? "yes" : "no";
    button.textContent = watching ? "End watch" : "Start watch";
    status.textContent = watching ? "You are on Watch." : "You are not on Watch.";
  };
  document.addEventListener("watch", (event) => show(event.detail.watching));
  button.addEventListener("click", () => {
    const action = button.dataset.watching === "yes" ? "end" : "start";
    // The click is the gesture a browser needs before sound: the sound check.
    if (action === "start" && window.alarmChime) window.alarmChime();
    fetch("/staff/watch/" + action, { method: "POST", credentials: "same-origin" })
      .then((response) => response.json())
      .then((data) => {
        // Unacknowledged Alarms replay at Start watch, before anything else.
        if (data.alarms) {
          document.dispatchEvent(new CustomEvent("alarm-replay", { detail: data.alarms }));
        }
        show(data.watching);
      });
  });
})();
</script>"""


def _watch_control(watching: bool) -> str:
    return (
        WATCH_CONTROL.replace(
            "__STATUS__", "You are on Watch." if watching else "You are not on Watch."
        )
        .replace("__WATCHING__", "yes" if watching else "no")
        .replace("__LABEL__", "End watch" if watching else "Start watch")
    )


# Inline on purpose: the Live view loads no external script. Text from events is set with
# textContent, never parsed as HTML.
OVERVIEW_SCRIPT = """<script>
(() => {
  const LIMIT = __LIMIT__;
  const tiles = document.getElementById("tiles");
  const shorten = (q) => (q.length <= LIMIT ? q : q.slice(0, LIMIT) + "...");
  const line = (cls) => {
    const p = document.createElement("p");
    p.className = cls;
    return p;
  };
  const newTile = (data) => {
    const tile = document.createElement("div");
    tile.className = "tile";
    tile.dataset.sessionNo = data.session_no;
    tile.dataset.messageCount = "0";
    const link = document.createElement("a");
    link.href = "/staff/live/sessions/" + encodeURIComponent(data.session_no);
    for (const cls of ["who", "when", "count", "latest"]) link.append(line(cls));
    tile.append(link);
    return tile;
  };
  const source = window.staffEvents || (window.staffEvents = new EventSource("/staff/live/events"));
__HEARTBEAT__
  source.addEventListener("question", (event) => {
    const data = JSON.parse(event.data);
    const empty = document.getElementById("no-sessions");
    if (empty) empty.remove();
    const selector = '[data-session-no="' + Number(data.session_no) + '"]';
    const tile = tiles.querySelector(selector) || newTile(data);
    const count = Number(tile.dataset.messageCount || "0") + 1;
    tile.dataset.messageCount = String(count);
    tile.querySelector(".who").textContent =
      data.class_label + " \\u00b7 card " + data.card_number;
    tile.querySelector(".when").textContent = "Last activity: " + data.asked_at;
    tile.querySelector(".count").textContent = count + " message(s)";
    tile.querySelector(".latest").textContent = shorten(data.question);
    tiles.prepend(tile);
  });
  // Screening went down or came back: the status line and its button are the server's.
  source.addEventListener("screening", () => location.reload());
})();
</script>""".replace("__LIMIT__", str(LATEST_QUESTION_LIMIT)).replace(
    "__HEARTBEAT__", HEARTBEAT_SCRIPT
)

DETAIL_SCRIPT = """<script>
(() => {
  const SESSION_NO = __SESSION_NO__;
  const exchanges = document.getElementById("exchanges");
  const labelled = (label, cls) => {
    const p = document.createElement("p");
    const strong = document.createElement("strong");
    strong.textContent = label;
    const value = document.createElement("span");
    if (cls) value.className = cls;
    p.append(strong, " ", value);
    return [p, value];
  };
  const find = (id) =>
    exchanges.querySelector('[data-transcript-id="' + Number(id) + '"]');
  const source = window.staffEvents || (window.staffEvents = new EventSource("/staff/live/events"));
__HEARTBEAT__
  source.addEventListener("question", (event) => {
    const data = JSON.parse(event.data);
    if (data.session_no !== SESSION_NO || find(data.transcript_id)) return;
    const div = document.createElement("div");
    div.className = "exchange";
    div.dataset.transcriptId = data.transcript_id;
    const [askedP, asked] = labelled("Asked at:");
    asked.textContent = data.asked_at;
    const [questionP, question] = labelled("Question:");
    question.textContent = data.question;
    const [answerP] = labelled("Answer:", "answer");
    div.append(askedP, questionP, answerP);
    exchanges.append(div);
  });
  // The answer as it is written: each delta is appended to its exchange's answer,
  // and the answer event below replaces that with the finished answer and Citations.
  source.addEventListener("delta", (event) => {
    const data = JSON.parse(event.data);
    if (data.session_no !== SESSION_NO) return;
    const div = find(data.transcript_id);
    if (!div) return;
    div.querySelector(".answer").textContent += data.text;
  });
  source.addEventListener("answer", (event) => {
    const data = JSON.parse(event.data);
    if (data.session_no !== SESSION_NO) return;
    const div = find(data.transcript_id);
    if (!div) return;
    div.querySelector(".answer").textContent = data.answer;
    const old = div.querySelector(".citations");
    if (old) old.remove();
    if (!data.citations.length) return;
    const list = document.createElement("div");
    list.className = "citations";
    for (const citation of data.citations) {
      const p = document.createElement("p");
      const link = document.createElement("a");
      link.href = "/staff/catalog/record/" + encodeURIComponent(citation.record_id);
      link.textContent = citation.title;
      p.append(link);
      list.append(p);
    }
    div.append(list);
  });
})();
</script>""".replace("__HEARTBEAT__", HEARTBEAT_SCRIPT)


def _screening_mode_form(mode: str, label: str) -> str:
    return (
        '<form method="post" action="/staff/live/screening-mode">'
        f'<input type="hidden" name="mode" value="{mode}">'
        f'<button type="submit">{label}</button></form>'
    )


def _screening_html(state: ScreeningState, timezone: str) -> str:
    """While Oversight is down, since when (school time) and a Pause Sessions button;
    while Sessions are paused, a Resume button (ADR-0004 addendum)."""
    parts = []
    if state.unavailable_since is not None:
        since = state.unavailable_since.astimezone(ZoneInfo(timezone))
        parts.append(
            '<p class="screening-unavailable" role="status">'
            f"Screening is unavailable since {since:%H:%M}.</p>"
        )
    if state.paused:
        parts.append(
            '<p class="sessions-paused" role="status">Sessions are paused.</p>'
        )
        parts.append(_screening_mode_form("resume", "Resume Sessions"))
    elif state.unavailable_since is not None:
        parts.append(_screening_mode_form("pause", "Pause Sessions"))
    return f'<div id="screening">{"".join(parts)}</div>' if parts else ""


@router.get("/live")
def live_view(
    account: StandInDep,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
    settings: Settings = Depends(get_settings),
    state: ScreeningState = Depends(get_screening_state),
) -> HTMLResponse:
    """The overview: one tile per active Session, safe to leave on screen. Its only
    controls are the Watch button and, while screening is unavailable or Sessions are
    paused, Pause (or Resume) Sessions."""
    tiles = active_sessions(db, clock)
    body = (
        "".join(_tile_html(tile) for tile in tiles)
        if tiles
        else '<p id="no-sessions">No active Sessions.</p>'
    )
    watch_control = _watch_control(is_watching(db, account.id, clock))
    screening = _screening_html(state, settings.school_timezone)
    response = page(
        "Live view",
        f"<h1>Live view</h1>{alarm_banner(db, account, clock)}{watch_control}"
        f'{screening}<div id="tiles">{body}</div>{OVERVIEW_SCRIPT}',
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/live/screening-mode")
def screening_mode(
    account: StandInDep,
    mode: str = Form(...),
    state: ScreeningState = Depends(get_screening_state),
    bus: LiveBus = Depends(get_live_bus),
) -> RedirectResponse:
    """Pause or resume Sessions, an adult's choice whenever they make it (ADR-0004
    addendum: a Librarian or Stand-in). Process memory only; nothing is stored."""
    if mode not in ("pause", "resume"):
        raise HTTPException(status_code=400, detail="mode must be pause or resume")
    state.paused = mode == "pause"
    state.paused_by_setting = False
    bus.publish("screening", {"unavailable": state.unavailable_since is not None})
    return RedirectResponse("/staff/live", status_code=303)


@router.get("/live/events")
async def live_events(
    account: StandInDep,
    bus: LiveBus = Depends(get_live_bus),
    wait: Callable[[], Awaitable[None]] = Depends(get_ping_wait),
) -> StreamingResponse:
    """The Live view's server-sent event stream: one event per LiveBus message."""
    queue = bus.subscribe()
    return StreamingResponse(
        event_stream(bus, queue, wait),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/live/sessions/{session_no}")
def session_detail_view(
    session_no: int,
    account: StandInDep,
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
        f"<h1>Session Detail</h1>{alarm_banner(db, account, clock)}"
        f"<p><strong>Class:</strong> {html.escape(class_label)}</p>"
        f"<p><strong>Card:</strong> {html.escape(card_number)}</p>"
        f'<p><a href="/staff/live">← Back to Live view</a></p>'
        f'<div class="exchanges" id="exchanges">{exchange_html}</div>'
        f"{DETAIL_SCRIPT.replace('__SESSION_NO__', str(session_no))}"
        f'<form method="post" action="/staff/live/sessions/{session_no}/revoke-card">'
        f'<label><input type="checkbox" name="confirm" value="yes" required> '
        f"Yes, revoke card {html.escape(card_number)}</label>"
        '<button type="submit">Revoke this Card</button>'
        "</form>"
        f'<form method="post" action="/staff/live/sessions/{session_no}/revoke-batch">'
        f'<label><input type="checkbox" name="confirm" value="yes" required> '
        f"Yes, revoke every Card in {html.escape(class_label)}</label>"
        '<button type="submit">Revoke this Batch</button>'
        "</form>"
    )

    response = page("Session Detail", content)
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/live/sessions/{session_no}/revoke-card")
def revoke_card_of_session_endpoint(
    session_no: int,
    account: LibrarianDep,
    confirm: str | None = Form(None),
    db: sqlite3.Connection = Depends(get_db),
) -> RedirectResponse:
    """Revoke the Card behind a Session; refuses without the confirmation checkbox."""
    if not confirm:
        raise HTTPException(status_code=400, detail="confirmation required")
    if not revoke_card_of_session(db, session_no):
        raise HTTPException(status_code=404, detail="Card already gone")
    return RedirectResponse("/staff/live", status_code=303)


@router.get("/catalog/record/{record_id}")
def catalog_record(
    record_id: str,
    account: StandInDep,
    catalog: Catalog = Depends(get_catalog),
) -> HTMLResponse:
    """Show a Record's details from the Catalog."""
    record = catalog.get(record_id)
    if record is None:
        return HTMLResponse("<h1>Not Found</h1>", status_code=404)

    # Render the record details in a page
    content = (
        f"<h1>Record Details</h1>"
        f"<p><strong>Title:</strong> {html.escape(record.title)}</p>"
        f"<p><strong>Author:</strong> {html.escape(record.author)}</p>"
        f"<p><strong>Subjects:</strong> {html.escape(record.subjects)}</p>"
        f"<p><strong>Summary:</strong> {html.escape(record.summary)}</p>"
        f"<p><strong>Call Number:</strong> {html.escape(record.call_number)}</p>"
        f'<p><a href="/staff/live">← Back to Live view</a></p>'
    )

    response = page("Record Details", content)
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/live/sessions/{session_no}/revoke-batch")
def revoke_batch_of_session_endpoint(
    session_no: int,
    account: LibrarianDep,
    confirm: str | None = Form(None),
    db: sqlite3.Connection = Depends(get_db),
) -> RedirectResponse:
    """Revoke every Card in the Batch behind a Session; refuses without the checkbox."""
    if not confirm:
        raise HTTPException(status_code=400, detail="confirmation required")
    if not revoke_batch_of_session(db, session_no):
        raise HTTPException(status_code=404, detail="Card already gone")
    return RedirectResponse("/staff/live", status_code=303)
