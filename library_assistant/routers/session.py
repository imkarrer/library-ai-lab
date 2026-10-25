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

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, StreamingResponse

from library_assistant.access import get_clock, get_db
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

# Quoted word for word by the AI literacy unit (docs/curriculum/ai-literacy-unit.md).
BANNER_TEXT = "This can be wrong, check the source."

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
    form.addEventListener("submit", async (event) => {{
      event.preventDefault();
      const question = document.getElementById("question").value;
      answer.textContent = "";
      const response = await fetch("/ask", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        credentials: "same-origin",
        body: JSON.stringify({{ question: question }}),
      }});
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      for (;;) {{
        const {{ done, value }} = await reader.read();
        if (done) break;
        answer.textContent += decoder.decode(value, {{ stream: true }});
      }}
    }});
  </script>
</body>
</html>
"""

router = APIRouter()


@router.get("/chat")
def chat_page(session: SessionDep) -> HTMLResponse:
    """The Student's page: the banner, a question box, and the streamed answer."""
    return HTMLResponse(
        CHAT_PAGE_HTML.format(
            banner=BANNER_TEXT,
            class_label=html.escape(session.class_label),
            card_number=html.escape(session.card_number),
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.post("/ask")
async def ask(
    request: AskRequest,
    session: SessionDep,
    http_client: HttpClientDep,
    settings: Settings = Depends(get_settings),
    catalog: Catalog = Depends(get_catalog),
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
) -> StreamingResponse:
    """Ask a question in a Session and stream a Grounded answer with Citations."""
    transcript_id = start_exchange(db, session, request.question, clock)
    records = catalog.search(request.question, k=4)
    citations = [
        Citation(
            record_id=record.id, title=record.title, call_number=record.call_number
        )
        for record in records
    ]

    context = "\n\n".join(
        f"{record.title} ({record.call_number}): {record.summary}" for record in records
    )
    messages = [
        {
            "role": "system",
            "content": "Answer the student's question using only these Records:\n"
            + context,
        },
        {"role": "user", "content": request.question},
    ]

    async def generate():
        answer_parts: list[str] = []
        shown: list[Citation] = []
        # finally: a model error or a hang-up still records what the Student saw.
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
                        answer_parts.append(delta)
                        yield delta

            for citation in citations:
                yield "\n" + citation.line()
                shown.append(citation)
        finally:
            finish_exchange(db, transcript_id, "".join(answer_parts), shown)

    return StreamingResponse(
        generate(), media_type="text/plain", headers={"Cache-Control": "no-store"}
    )
