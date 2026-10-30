"""Asking in a Session: the chat page and Grounded answers.

The Session comes from the HttpOnly cookie Card sign-in sets, never from the URL, so
no Session id reaches a server log (ADR-0003 addendum). The only outbound call is to
the configured OpenAI-compatible endpoint (ADR-0006).
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import json
import logging
import sqlite3
from collections.abc import Awaitable, Callable
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from starlette.types import Receive, Scope, Send

from library_assistant.access import (
    NO_STORE,
    PAUSED_TEXT,
    REFUSAL_TEXT,
    Session,
    get_clock,
    get_db,
)
from library_assistant.alarms import announce_flag
from library_assistant.catalog import Catalog
from library_assistant.config import Settings
from library_assistant.dependencies import (
    HttpClientDep,
    SessionDep,
    finish_exchange,
    get_catalog,
    get_settings,
    get_watchlist,
    start_exchange,
)
from library_assistant.flags import raise_or_repeat
from library_assistant.install_settings import (
    DEFAULT_OVERSIGHT_DOWN,
    OVERSIGHT_DOWN,
    get_setting,
)
from library_assistant.models import AskRequest, Citation
from library_assistant.oversight import (
    OversightUnavailable,
    ScreeningState,
    Verdict,
    get_screening_state,
    probe,
    screen,
    screening_state,
)
from library_assistant.prompt import SearchLineFilter, build_messages
from library_assistant.routers.live import LiveBus, get_live_bus
from library_assistant.watch import gate_is_open
from library_assistant.watchlist import Watchlist, normalize

# Quoted word for word by the AI literacy unit (docs/curriculum/ai-literacy-unit.md).
BANNER_TEXT = "This can be wrong, check the source."

ERROR_TEXT = "Something went wrong. Ask the librarian."

logger = logging.getLogger(__name__)

# How long the probe waits between asking a down Oversight endpoint whether it is back,
# and the catch-up waits while a Card awaits a verdict.
PROBE_INTERVAL_SECONDS = 15

# ADR-0011's self-harm text verbatim, {counselor} = "a school counselor". One reply for
# every high-severity match until lib-irf.1 makes it per Rubric category. The ADR's **bold**
# is dropped: the chat page shows plain text, so asterisks would reach the Student.
# This is kept for backwards compatibility with tests.
SUPPORTIVE_REPLY = """It sounds like you are going through something really hard. \
You don't have to handle it alone.

Please talk to an adult you trust today, like a school counselor or the librarian.

You can call or text 988 any time, day or night. It is free, and a real person will \
listen. If you might hurt yourself right now, tell an adult near you or call 911.

I am a library computer, so a person can help with this better than I can. An adult here \
may check in with you, because they care how you are doing."""

# Import our new supportive reply handling
from library_assistant.supportive_replies import (
    reply_for,
)

CHAT_PAGE_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="/library.css">
<title>Library Assistant</title>
</head>
<body>
  <p class="banner" role="note">{banner}</p>
  <p>{class_label} &middot; card {card_number}</p>
  <form id="ask">
    <input id="question" name="question" size="50" autocomplete="off" required>
    <button>Ask</button>
  </form>
  <div id="answer"></div>
  <p><button id="finish">End session</button></p>
  <p><a href="/about">What happens to what I type</a></p>
  <script>
    document.getElementById("finish").addEventListener("click", () => {{
      fetch("/card/finish", {{ method: "POST", credentials: "same-origin" }}).then(() => {{
        document.body.textContent = "Session ended. You can close this page.";
      }});
    }});
    const form = document.getElementById("ask");
    const answer = document.getElementById("answer");
    const REFUSAL_TEXT = {refusal_text};
    const ERROR_TEXT = {error_text};
    form.addEventListener("submit", async (event) => {{
      event.preventDefault();
      const questionInput = document.getElementById("question");
      const askButton = form.querySelector("button");
      const question = questionInput.value;
      answer.textContent = "";
      // Disable Ask button immediately on submit
      questionInput.disabled = true;
      askButton.disabled = true;
      
      // Retry loop for 409 "one moment" responses
      let retryCount = 0;
      let response;
      while (true) {{
        response = await fetch("/ask", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          credentials: "same-origin",
          body: JSON.stringify({{ question: question }}),
        }});
        
        if (response.status === 409) {{
          const data = await response.json();
          if (data.status === "one moment") {{
            // Show "One moment..." in the answer area
            answer.textContent = "One moment...";
            // Keep the question input enabled and its value unchanged
            // Keep Ask button disabled
            retryCount++;
            // Wait 2 seconds before retrying
            await new Promise(resolve => setTimeout(resolve, 2000));
            continue; // Retry the same question
          }}
        }}
        // If not 409 "one moment", break the loop
        break;
      }}
      
      if (response.status === 503) {{
        const data = await response.json();
        answer.textContent = data.detail;
        // Paused: the question stays in the box to send again once Sessions resume.
        questionInput.disabled = false;
        askButton.disabled = false;
        return;
      }}
      if (response.status === 403) {{
        const data = await response.json();
        answer.textContent = data.detail;
        // Keep question disabled as today
        document.getElementById("question").disabled = true;
        return;
      }}
      if (response.status !== 200) {{
        answer.textContent = ERROR_TEXT;
        // Re-enable question input on error
        questionInput.disabled = false;
        askButton.disabled = false;
        return;
      }}
      // Stream the response as today
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      try {{
        for (;;) {{
          const {{ done, value }} = await reader.read();
          if (done) break;
          answer.textContent += decoder.decode(value, {{ stream: true }});
        }}
      }} catch (error) {{
        // The connection dropped mid-answer: say so, and let the Student ask again.
        answer.textContent += (answer.textContent ? "\n\n" : "") + ERROR_TEXT;
      }}
      // Re-enable Ask button after successful stream
      questionInput.disabled = false;
      askButton.disabled = false;
    }});
  </script>
</body>
</html>
"""

# Card refs (Token hashes) with a message in flight: one per Card, across all its
# Sessions (decision lib-f24.65). Process memory only (one process, ADR-0008); never
# logged or stored (ADR-0002).
_in_flight: set[str] = set()

# Oversight tasks that are running for in-flight messages.
# These are kept in a set to maintain strong references and prevent cancellation.
_oversight_tasks: set[asyncio.Task] = set()

# Screens that are in-flight (running Oversight tasks) for in-flight messages.
# These are kept in a set to maintain strong references and prevent cancellation.
_screens: set[asyncio.Task] = set()

# The probe-and-catch-up task while Oversight is down or catching up, and the catch-up's
# screen call in progress, which a Card that starts awaiting a verdict cancels: live
# Students come first (ADR-0004 addendum).
_probe_task: asyncio.Task | None = None
_catch_up_call: asyncio.Future | None = None


async def _probe_wait() -> None:
    await asyncio.sleep(PROBE_INTERVAL_SECONDS)


def get_probe_wait() -> Callable[[], Awaitable[None]]:
    """The wait between probes; tests override it so nothing sleeps."""
    return _probe_wait


def get_now() -> Callable[[], datetime]:
    """The clock for work that outlives the request (the probe and the catch-up)."""
    return get_clock


def _record_verdict(
    db: sqlite3.Connection,
    transcript_id: int,
    class_label: str,
    card_number: str,
    batch_expires_at: str,
    message_hash: str,
    verdict: Verdict,
    at: datetime,
    screening: str,
    bus: LiveBus,
    clock: Callable[[], datetime],
) -> None:
    """Store the verdict on its exchange, and raise its Flag (or a repeat) on a concern:
    a new high-severity Flag sounds the Alarm on the open staff pages (ADR-0010)."""
    db.execute(
        "UPDATE transcripts SET verdict = ?, screened_at = ?, screening = ? WHERE id = ?",
        (
            json.dumps(
                {
                    "category": verdict.category,
                    "severity": verdict.severity,
                    "reason": verdict.reason,
                }
            ),
            at.isoformat(),
            screening,
            transcript_id,
        ),
    )
    db.commit()
    if verdict.category:
        # Check if the gate is open (i.e., a Watch is active)
        gate_open = gate_is_open(db, clock)
        flag_id, is_repeat = raise_or_repeat(
            db,
            transcript_id,
            class_label,
            card_number,
            batch_expires_at,
            message_hash,
            verdict.category,
            verdict.severity,
            "oversight",
            at.isoformat(),
            reason=verdict.reason,
            raised_unwatched=not gate_open,
        )
        announce_flag(db, bus.publish, flag_id, is_repeat)


def _publish_screening(bus: LiveBus) -> None:
    """Tell the Live view that screening went down or came back."""
    bus.publish(
        "screening", {"unavailable": screening_state.unavailable_since is not None}
    )


def _oversight_down(
    db: sqlite3.Connection,
    settings: Settings,
    bus: LiveBus,
    now: Callable[[], datetime],
    wait: Callable[[], Awaitable[None]],
) -> None:
    """Note that Oversight stopped answering, and make sure the probe runs."""
    state = screening_state
    if state.unavailable_since is None:
        state.unavailable_since = now()
        oversight_down = get_setting(db, OVERSIGHT_DOWN, DEFAULT_OVERSIGHT_DOWN)
        if oversight_down == "pause" and not state.paused:
            state.paused = True
            state.paused_by_setting = True
        _publish_screening(bus)
    global _probe_task
    if _probe_task is None or _probe_task.done():
        _probe_task = asyncio.create_task(
            _probe_and_catch_up(db, settings, bus, now, wait)
        )


def _oversight_up(bus: LiveBus) -> None:
    state = screening_state
    state.unavailable_since = None
    if state.paused_by_setting:
        state.paused = False
        state.paused_by_setting = False
    _publish_screening(bus)


def _oldest_unscreened(db: sqlite3.Connection) -> tuple | None:
    """The oldest exchange admitted on the Watchlist alone and not yet screened, with
    its Card's expiry for a Flag ('' once the Card is gone)."""
    return db.execute(
        "SELECT transcripts.id, transcripts.class_label, transcripts.card_number, "
        "transcripts.question, COALESCE(cards.expires_at, '') "
        "FROM transcripts "
        "LEFT JOIN sessions ON sessions.session_hash = transcripts.session_hash "
        "LEFT JOIN cards ON cards.token_hash = sessions.token_hash "
        "WHERE transcripts.screening = 'watchlist_alone' "
        "AND transcripts.screened_at IS NULL "
        "ORDER BY transcripts.asked_at, transcripts.id LIMIT 1"
    ).fetchone()


def start_catch_up_if_needed(
    db: sqlite3.Connection,
    settings: Settings,
    bus: LiveBus,
    now: Callable[[], datetime],
    wait: Callable[[], Awaitable[None]],
) -> bool:
    """Start catch-up if Oversight is enabled and there are unscreened exchanges.

    Returns True if catch-up was started, False otherwise.
    Does not set unavailable_since as Oversight is not known to be down.
    """
    if not settings.oversight_enabled:
        return False

    if _oldest_unscreened(db) is None:
        return False

    global _probe_task
    if _probe_task is None or _probe_task.done():
        _probe_task = asyncio.create_task(
            _probe_and_catch_up(db, settings, bus, now, wait)
        )
    return True


async def screens_settled(timeout: float) -> None:
    """Wait for any in-flight oversight screens to complete, up to the given timeout."""
    if not _screens:
        return
    await asyncio.wait(_screens, timeout=timeout)


async def _probe_and_catch_up(
    db: sqlite3.Connection,
    settings: Settings,
    bus: LiveBus,
    now: Callable[[], datetime],
    wait: Callable[[], Awaitable[None]],
) -> None:
    """Probe until Oversight answers, then screen the exchanges admitted while it was
    down, oldest first and one at a time, only while no Card awaits a verdict. Ends
    when none is left; a failure on the way goes back to probing."""
    global _catch_up_call
    # Its own client: the Oversight endpoint is not the Answer lane's.
    async with httpx.AsyncClient() as client:
        while True:
            if screening_state.unavailable_since is not None:
                await wait()
                if not await probe(client, settings):
                    continue
                _oversight_up(bus)
            row = _oldest_unscreened(db)
            if row is None:
                return
            if _oversight_tasks:
                await wait()
                continue
            transcript_id, class_label, card_number, question, expires_at = row
            call = asyncio.ensure_future(screen(client, settings, question))
            _catch_up_call = call
            try:
                await asyncio.wait({call})
            finally:
                _catch_up_call = None
                call.cancel()
            if call.cancelled():
                # A Card started awaiting a verdict: this exchange is screened later.
                continue
            try:
                verdict = call.result()
            except OversightUnavailable:
                _oversight_down(db, settings, bus, now, wait)
                continue
            # No Flag on an exchange that is gone (the Purge keeps unscreened ones, so
            # this is only a guard).
            if db.execute(
                "SELECT 1 FROM transcripts WHERE id = ?", (transcript_id,)
            ).fetchone():
                _record_verdict(
                    db,
                    transcript_id,
                    class_label,
                    card_number,
                    expires_at,
                    hashlib.sha256(normalize(question).encode()).hexdigest(),
                    verdict,
                    now(),
                    "watchlist_alone",
                    bus,
                    now,
                )


class _ReleasingStream(StreamingResponse):
    """Releases the Card's in-flight marker however the response ends, including a
    connection dropped before the body iterator ever starts (its finally never runs)."""

    def __init__(self, *args, card_ref: str, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._card_ref = card_ref

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            _in_flight.discard(self._card_ref)


router = APIRouter()


@router.get("/chat")
def chat_page(session: SessionDep) -> HTMLResponse:
    """The Student's page: the banner, a question box, and the streamed answer."""
    return HTMLResponse(
        CHAT_PAGE_HTML.format(
            banner=BANNER_TEXT,
            class_label=html.escape(session.class_label),
            card_number=html.escape(session.card_number),
            refusal_text=json.dumps(REFUSAL_TEXT),
            error_text=json.dumps(ERROR_TEXT),
        ),
        headers=NO_STORE,
    )


@router.get("/status")
def status(
    session: SessionDep,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
) -> JSONResponse:
    """Tells the chat page whether the gate is paused or active (ADR-0010)."""
    return JSONResponse({"paused": not gate_is_open(db, clock)}, headers=NO_STORE)


@router.post("/ask", response_model=None)
async def ask(
    request: AskRequest,
    session: SessionDep,
    http_client: HttpClientDep,
    settings: Settings = Depends(get_settings),
    catalog: Catalog = Depends(get_catalog),
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
    bus: LiveBus = Depends(get_live_bus),
    watchlist: Watchlist = Depends(get_watchlist),
    state: ScreeningState = Depends(get_screening_state),
    now: Callable[[], datetime] = Depends(get_now),
    probe_wait: Callable[[], Awaitable[None]] = Depends(get_probe_wait),
) -> StreamingResponse | JSONResponse:
    """Ask a question in a Session and stream a Grounded answer with Citations.

    A Card has one message in flight at a time: another one gets 409 "one moment"
    before it is recorded, checked or sent anywhere.

    Every admitted message is checked against the Watchlist (ADR-0004): each match
    raises a Flag, or repeats the open one for the same message. A high-severity match
    gets SUPPORTIVE_REPLY instead of an answer, with no Catalog search and no model call.

    The Live view hears of the question, each piece of the answer as the Student is
    shown it (`delta`), and the finished answer through the LiveBus; the events carry
    the Session's row number, never its hash.

    While Oversight is down the message skips it and is marked `watchlist_alone`, to be
    screened once it is back. While Sessions are paused, a message the Watchlist does
    not answer with a Supportive reply gets 503 and PAUSED_TEXT (ADR-0004 addendum).
    """
    card_ref = session.card_ref
    if card_ref in _in_flight:
        return JSONResponse({"status": "one moment"}, status_code=409, headers=NO_STORE)
    _in_flight.add(card_ref)
    try:
        return _answer(
            request,
            session,
            http_client,
            settings,
            catalog,
            db,
            clock,
            bus,
            watchlist,
            state,
            now,
            probe_wait,
        )
    except BaseException:
        _in_flight.discard(card_ref)
        raise


def _answer(
    request: AskRequest,
    session: Session,
    http_client: httpx.AsyncClient,
    settings: Settings,
    catalog: Catalog,
    db: sqlite3.Connection,
    clock: datetime,
    bus: LiveBus,
    watchlist: Watchlist,
    state: ScreeningState,
    now: Callable[[], datetime],
    probe_wait: Callable[[], Awaitable[None]],
) -> StreamingResponse:
    # The gate (lib-793.3, ADR-0010): the Watchlist and the Supportive reply run in
    # every mode; a closed gate otherwise gets the paused response, like `state.paused`.
    gate_open = gate_is_open(db, clock)
    # Oversight down: carry on at once with the Watchlist alone (ADR-0004 addendum).
    use_oversight = settings.oversight_enabled and state.unavailable_since is None
    watchlist_alone = settings.oversight_enabled and not use_oversight
    transcript_id = start_exchange(db, session, request.question, clock)
    session_no = db.execute(
        "SELECT rowid FROM sessions WHERE session_hash = ?", (session.ref,)
    ).fetchone()[0]
    bus.publish(
        "question",
        {
            "session_no": session_no,
            "transcript_id": transcript_id,
            "class_label": session.class_label,
            "card_number": session.card_number,
            "question": request.question,
            "asked_at": clock.isoformat(),
        },
    )

    # The Card is released once its answer has ended and, with Oversight up, once its
    # verdict is recorded or Oversight has failed: whichever comes last.
    pending = {"answer": True, "verdict": use_oversight}

    def settle(part: str) -> None:
        pending[part] = False
        if not any(pending.values()):
            _in_flight.discard(session.card_ref)

    def finish(answer: str, shown: list[Citation]) -> None:
        """Record what the Student saw, tell the Live view, and release the Card."""
        try:
            finish_exchange(db, transcript_id, answer, shown)
            bus.publish(
                "answer",
                {
                    "session_no": session_no,
                    "transcript_id": transcript_id,
                    "answer": answer,
                    "citations": [citation.model_dump() for citation in shown],
                },
            )
        finally:
            settle("answer")

    def publish_delta(text: str) -> None:
        """Tell the Live view of answer text as the Student is shown it: SEARCH lines
        never, the Supportive reply only whole (its answer event). Memory and the open
        stream only: never logged, and stored only as the finished transcript."""
        bus.publish(
            "delta",
            {"session_no": session_no, "transcript_id": transcript_id, "text": text},
        )

    # Check Watchlist matches first
    matches = watchlist.match(request.question)
    message_hash = hashlib.sha256(normalize(request.question).encode()).hexdigest()

    # Handle Watchlist matches - raise flags for all matches regardless of severity
    for entry in matches:
        flag_id, is_repeat = raise_or_repeat(
            db,
            transcript_id,
            session.class_label,
            session.card_number,
            session.expires_at.isoformat(),
            message_hash,
            entry.category,
            entry.severity,
            "watchlist",
            clock.isoformat(),
            entry_id=entry.id,
            watchlist_version=watchlist.version,
            raised_unwatched=not gate_open,
        )
        announce_flag(db, bus.publish, flag_id, is_repeat)

    # First, we build the messages for the research prompt
    messages = build_messages(request.question)

    # Then we stream the model response
    async def generate():
        shown_parts: list[str] = []
        shown: list[Citation] = []
        # finally: a model error or a hang-up still records what the Student saw.
        try:
            # Create a single filter instance for the entire streaming process
            filter_instance = SearchLineFilter()

            # The response's 200 is already sent, so a model server that is down or
            # drops the stream cannot become an error status: the Student is told in
            # the answer instead, and the log names the error class, never the question.
            try:
                async with http_client.stream(
                    "POST",
                    "/chat/completions",
                    json={
                        "model": settings.openai_model,
                        "messages": messages,
                        "stream": True,
                    },
                ) as response:
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        payload = line.removeprefix("data: ")
                        if payload == "[DONE]":
                            break
                        delta = json.loads(payload)["choices"][0]["delta"].get(
                            "content", ""
                        )
                        if delta:
                            # Use the filter to handle search lines
                            output = filter_instance.feed(delta)
                            if output:
                                shown_parts.append(output)
                                publish_delta(output)
                                yield output
            except httpx.HTTPError as error:
                logger.warning("model request failed: %s", type(error).__name__)
                yield ("\n\n" if shown_parts else "") + ERROR_TEXT
                return

            # After streaming, extract search terms from the full response
            remaining_text, search_terms = filter_instance.finish()

            # Yield any remaining text that wasn't handled by the filter, before the
            # citations, so the Student sees the overview whole before the books.
            if remaining_text:
                shown_parts.append(remaining_text)
                publish_delta(remaining_text)
                yield remaining_text

            # If no search terms, search with the original question
            search_query = " ".join(search_terms) if search_terms else request.question

            # Now search the catalog
            records = catalog.search(search_query, k=4)
            citations = [
                Citation(
                    record_id=record.id,
                    title=record.title,
                    call_number=record.call_number,
                )
                for record in records
            ]

            # Yield the citations
            if records:
                yield "\n\nBooks in our library:"
                for citation in citations:
                    yield "\n" + citation.line()
            else:
                yield "\n\nThe library's catalog has nothing on this yet. Ask the librarian."

            # Copy the citations to shown list
            shown = citations.copy()
        finally:
            finish("".join(shown_parts), shown)

    # The Oversight task starts at the same moment as the Answer request (or the
    # Supportive reply): a Supportive reply still gets screened.
    oversight_task: asyncio.Task | None = None
    if watchlist_alone:
        # screened_at stays NULL: the catch-up screens it once Oversight is back.
        db.execute(
            "UPDATE transcripts SET screening = ? WHERE id = ?",
            ("watchlist_alone", transcript_id),
        )
        db.commit()
    if use_oversight:
        db.execute(
            "UPDATE transcripts SET screening = ? WHERE id = ?",
            ("oversight", transcript_id),
        )
        db.commit()

        async def _run_oversight():
            """Screen the message and record the verdict; never cancelled (see
            `_oversight_tasks`), so the Card stays in-flight until this records."""
            try:
                # Its own client: the Oversight endpoint is not the Answer lane's.
                async with httpx.AsyncClient() as oversight_client:
                    verdict = await screen(oversight_client, settings, request.question)
                _record_verdict(
                    db,
                    transcript_id,
                    session.class_label,
                    session.card_number,
                    session.expires_at.isoformat(),
                    message_hash,
                    verdict,
                    clock,
                    "oversight",
                    bus,
                    clock,
                )
            except OversightUnavailable:
                # The Watchlist already ran. The message is released as soon as its
                # answer ends, and screened when Oversight is back (ADR-0004 addendum).
                db.execute(
                    "UPDATE transcripts SET screening = ? WHERE id = ?",
                    ("watchlist_alone", transcript_id),
                )
                db.commit()
                _oversight_down(db, settings, bus, now, probe_wait)
            finally:
                _oversight_tasks.discard(oversight_task)
                _screens.discard(oversight_task)
                settle("verdict")

        # A Card now awaits a verdict: the catch-up gives way to it.
        if _catch_up_call is not None:
            _catch_up_call.cancel()
        oversight_task = asyncio.create_task(_run_oversight())
        _oversight_tasks.add(oversight_task)
        _screens.add(oversight_task)

    # Handle high severity matches specially - they get supportive reply
    high_severity_matches = [entry for entry in matches if entry.severity == "high"]
    if high_severity_matches:
        # Every time, repeats included; nothing reaches the Catalog or the model.
        async def supportive():
            # ADR-0011: one reply, by precedence, with the Install's overrides.
            reply_text = reply_for(
                db, [entry.category for entry in high_severity_matches]
            )

            try:
                yield reply_text
            finally:
                finish(reply_text, [])
                if oversight_task is not None:
                    await oversight_task

        return _ReleasingStream(
            supportive(),
            media_type="text/plain",
            headers=NO_STORE,
            card_ref=session.card_ref,
        )

    if state.paused or not gate_open:
        # Paused by an adult (or by oversight_down = pause, or a closed gate): the
        # Watchlist ran above and a high-severity match got its Supportive reply;
        # nothing reaches the model.
        async def paused():
            try:
                yield json.dumps({"detail": PAUSED_TEXT})
            finally:
                finish(PAUSED_TEXT, [])
                if oversight_task is not None:
                    await oversight_task

        return _ReleasingStream(
            paused(),
            status_code=503,
            media_type="application/json",
            headers=NO_STORE,
            card_ref=session.card_ref,
        )

    if oversight_task is not None:
        # The Answer lane streams through `generate()`; once its body is fully sent,
        # we still hold the Card until the Oversight task records its verdict.
        async def generate_with_oversight():
            async for item in generate():
                yield item
            await oversight_task

        return _ReleasingStream(
            generate_with_oversight(),
            media_type="text/plain",
            headers=NO_STORE,
            card_ref=session.card_ref,
        )

    return _ReleasingStream(
        generate(),
        media_type="text/plain",
        headers=NO_STORE,
        card_ref=session.card_ref,
    )
