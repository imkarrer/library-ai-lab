"""Session operations: asking questions and managing transcripts.

Binding: ADR-0003 (transcript purge), ADR-0006 (intranet-only).
"""

from __future__ import annotations

import json
import sqlite3

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from library_assistant.catalog import Catalog
from library_assistant.config import Settings
from library_assistant.dependencies import (
    HttpClientDep,
    SessionDep,
    get_catalog,
    get_clock,
    get_db,
    get_settings,
    store_exchange,
)
from library_assistant.models import AskRequest, Citation

# Banner text constant as required by the AI literacy unit
BANNER_TEXT = "This can be wrong, check the source."


router = APIRouter(prefix="/session")


@router.post("/{session_id}/ask")
async def ask(
    session_id: str,
    request: AskRequest,
    session: SessionDep,
    http_client: HttpClientDep,
    settings: Settings = Depends(get_settings),
    catalog: Catalog = Depends(get_catalog),
    db: sqlite3.Connection = Depends(get_db),
    clock=Depends(get_clock),
) -> StreamingResponse:
    """Ask a question in a Session and stream a Grounded answer with Citations."""
    records = catalog.search(request.question, k=4)
    citations = [Citation(call_number=record.call_number) for record in records]

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
                delta = json.loads(payload)["choices"][0]["delta"].get("content", "")
                if delta:
                    answer_parts.append(delta)
                    yield delta

        for citation in citations:
            yield f"\nCitation: {citation.call_number}"

        store_exchange(
            db,
            session_id,
            request.question,
            "".join(answer_parts),
            citations,
            clock,
        )

    return StreamingResponse(generate(), media_type="text/plain")
