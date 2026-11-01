"""The staff test page: any staff member asks the assistant, with no Card and no Watch, and
sees what a Student would get and what would happen in class.

A test is not a Session. It writes nothing, so the Purge has nothing to do (ADR-0003), and it
raises no Flag, reaches no Live view, and sounds no Alarm. The answer and the checks are the
Student's own code, so a passing test means something. See ADR-0010, "Amendment: the staff
test page".
"""

from __future__ import annotations

import html
import json
import sqlite3
from collections.abc import AsyncIterator

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from library_assistant.access import NO_STORE, REFUSAL_TEXT, get_db
from library_assistant.catalog import Catalog
from library_assistant.config import Settings
from library_assistant.dependencies import (
    HttpClientDep,
    get_catalog,
    get_settings,
    get_watchlist,
)
from library_assistant.models import AskRequest, books_title
from library_assistant.oversight import (
    OversightUnavailable,
    ScreeningState,
    get_screening_state,
    screen,
)
from library_assistant.routers.session import (
    BANNER_TEXT,
    CHAT_PAGE_HTML,
    ERROR_TEXT,
    _in_flight,
    _ReleasingStream,
    stream_answer,
)
from library_assistant.staff import StaffDep
from library_assistant.supportive_replies import reply_for
from library_assistant.watchlist import Watchlist

router = APIRouter()

TEST_PATH = "/staff/test"

_IN_CLASS_PANEL = """<section class="card-panel in-class" aria-live="polite">
      <h2>What would happen in class</h2>
      <p>This computer can only answer so many questions at once, and Students
      share it. Use this sparingly, especially while a class is using the assistant.</p>
      <div id="in-class"><p>Ask something. Nothing here is saved, and it raises no Flag, even
      if you type something the assistant watches for.</p></div>
    </section>"""

_FOOT = '<a href="/staff">Back to staff pages</a>'

# Asked beside the answer, as Oversight is for a Student. The answer can finish first.
_PAGE_SCRIPT = """<script>
    {
      const inClass = document.getElementById("in-class");
      let latest = 0;
      form.addEventListener("submit", async () => {
        const mine = ++latest;
        const question = document.getElementById("question").value;
        inClass.textContent = "Checking...";
        let lines = ["This check did not finish. Ask again."];
        try {
          const response = await fetch("/staff/test/check", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({ question: question }),
          });
          if (response.ok) lines = (await response.json()).in_class;
        } catch (error) {
          // The line above says so.
        }
        if (mine !== latest) return;
        inClass.replaceChildren(...lines.map((line) => {
          const paragraph = document.createElement("p");
          paragraph.textContent = line;
          return paragraph;
        }));
      });
    }
  </script>"""


def _flag_line(source: str, category: str, severity: str | None) -> str:
    """One check's result, in the words of what would happen to a Student."""
    kind = f"{severity}-severity Flag" if severity else "Flag"
    alarm = " and the Alarm would sound" if severity == "high" else ", with no Alarm"
    return f"{source}: a {kind} for {category.replace('-', ' ')}{alarm}."


@router.get(TEST_PATH)
def test_page(
    account: StaffDep, settings: Settings = Depends(get_settings)
) -> HTMLResponse:
    """The Student's chat page, pointed at the test routes."""
    return HTMLResponse(
        CHAT_PAGE_HTML.format(
            books_title=json.dumps(books_title(settings.demo)),
            banner=BANNER_TEXT,
            who=f"Test &middot; {html.escape(account.username)}",
            below_composer=_IN_CLASS_PANEL,
            foot=_FOOT,
            ask_url=json.dumps(TEST_PATH + "/ask"),
            page_script=_PAGE_SCRIPT,
            refusal_text=json.dumps(REFUSAL_TEXT),
            error_text=json.dumps(ERROR_TEXT),
        ),
        headers=NO_STORE,
    )


@router.post(TEST_PATH + "/ask", response_model=None)
async def test_ask(
    request: AskRequest,
    account: StaffDep,
    http_client: HttpClientDep,
    settings: Settings = Depends(get_settings),
    catalog: Catalog = Depends(get_catalog),
    db: sqlite3.Connection = Depends(get_db),
    watchlist: Watchlist = Depends(get_watchlist),
) -> StreamingResponse | JSONResponse:
    """What a Student would be shown for this question. Records nothing."""
    in_flight_key = f"staff-test:{account.id}"
    if in_flight_key in _in_flight:
        return JSONResponse({"status": "one moment"}, status_code=409, headers=NO_STORE)
    _in_flight.add(in_flight_key)

    high = [
        e.category for e in watchlist.match(request.question) if e.severity == "high"
    ]

    async def supportive() -> AsyncIterator[str]:
        yield reply_for(db, high)

    return _ReleasingStream(
        supportive()
        if high
        else stream_answer(
            http_client,
            settings,
            catalog,
            request.question,
            lambda _text: None,
            lambda _answer, _shown: None,
        ),
        media_type="text/plain",
        headers=NO_STORE,
        card_ref=in_flight_key,
    )


@router.post(TEST_PATH + "/check")
async def test_check(
    request: AskRequest,
    _account: StaffDep,
    settings: Settings = Depends(get_settings),
    watchlist: Watchlist = Depends(get_watchlist),
    state: ScreeningState = Depends(get_screening_state),
) -> JSONResponse:
    """What the Watchlist and Oversight would do with this question, raising nothing."""
    matches = watchlist.match(request.question)
    lines = [_flag_line("Watchlist", e.category, e.severity) for e in matches]
    if not matches:
        lines.append("The Watchlist found nothing.")
    if any(entry.severity == "high" for entry in matches):
        lines.insert(0, "A Student would get the Supportive reply, not an answer.")

    if not settings.oversight_enabled:
        lines.append("Oversight is off on this Install, so it did not check this.")
    elif state.unavailable_since is not None:
        lines.append("Oversight is down, so it did not check this.")
    else:
        try:
            # Its own client: the Oversight endpoint is not the Answer lane's.
            async with httpx.AsyncClient() as client:
                verdict = await screen(client, settings, request.question)
        except OversightUnavailable:
            lines.append("Oversight did not answer, so it did not check this.")
        else:
            if verdict.category is not None:
                lines.append(
                    _flag_line("Oversight", verdict.category, verdict.severity)
                )
            else:
                lines.append("Oversight found nothing.")
    return JSONResponse({"in_class": lines}, headers=NO_STORE)
