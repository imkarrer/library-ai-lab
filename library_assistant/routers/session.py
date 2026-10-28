"""Asking in a Session: the chat page and Grounded answers.

The Session comes from the HttpOnly cookie Card sign-in sets, never from the URL, so
no Session id reaches a server log (ADR-0003 addendum). The only outbound call is to
the configured OpenAI-compatible endpoint (ADR-0006).
"""

from __future__ import annotations

import html
import json
import sqlite3
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from starlette.types import Receive, Scope, Send

from library_assistant.access import (
    NO_STORE,
    REFUSAL_TEXT,
    Session,
    get_clock,
    get_db,
)
from library_assistant.catalog import Catalog
from library_assistant.config import Settings
from library_assistant.dependencies import (
    HttpClientDep,
    SessionDep,
    finish_exchange,
    get_catalog,
    get_settings,
    start_exchange,
)
from library_assistant.models import AskRequest, Citation
from library_assistant.prompt import SearchLineFilter, build_messages
from library_assistant.routers.live import LiveBus, get_live_bus

# Quoted word for word by the AI literacy unit (docs/curriculum/ai-literacy-unit.md).
BANNER_TEXT = "This can be wrong, check the source."

ERROR_TEXT = "Something went wrong. Ask the librarian."

CHAT_PAGE_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Library Assistant</title>
<style>
  body {{ font-family: sans-serif; max-width: 40em; margin: 1em auto; }}
  .banner {{ background: #fff4ce; border: 1px solid #c9a400; padding: 0.5em; }}
  #answer {{ white-space: pre-wrap; margin-top: 1em; }}
</style>
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
      for (;;) {{
        const {{ done, value }} = await reader.read();
        if (done) break;
        answer.textContent += decoder.decode(value, {{ stream: true }});
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
) -> StreamingResponse | JSONResponse:
    """Ask a question in a Session and stream a Grounded answer with Citations.

    A Card has one message in flight at a time: another one gets 409 "one moment"
    before it is recorded, checked or sent anywhere.

    The Live view hears of the question and the answer through the LiveBus; the events
    carry the Session's row number, never its hash.
    """
    card_ref = session.card_ref
    if card_ref in _in_flight:
        return JSONResponse({"status": "one moment"}, status_code=409, headers=NO_STORE)
    _in_flight.add(card_ref)
    try:
        return _answer(request, session, http_client, settings, catalog, db, clock, bus)
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
) -> StreamingResponse:
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

    # First, we build the messages for the research prompt
    messages = build_messages(request.question)

    # Then we stream the model response
    async def generate():
        answer_parts: list[str] = []
        shown: list[Citation] = []
        # finally: a model error or a hang-up still records what the Student saw.
        try:
            # Create a single filter instance for the entire streaming process
            filter_instance = SearchLineFilter()

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
                        answer_parts.append(delta)

                        # Use the filter to handle search lines
                        output = filter_instance.feed(delta)
                        if output:
                            yield output

            # After streaming, extract search terms from the full response
            remaining_text, search_terms = filter_instance.finish()

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

            # Also yield any remaining text that wasn't handled by the filter
            if remaining_text:
                yield remaining_text
        finally:
            try:
                answer = "".join(answer_parts)
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
                _in_flight.discard(session.card_ref)

    return _ReleasingStream(
        generate(),
        media_type="text/plain",
        headers=NO_STORE,
        card_ref=session.card_ref,
    )
