"""Dependencies for Grounded answers: settings, the Catalog, the model client, and the
transcript. The database, clock, and Session come from library_assistant.access, so
Card sign-in and asking share one store and one notion of time.
"""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated

import httpx
from fastapi import Depends

from library_assistant.access import Session, current_session
from library_assistant.catalog import Catalog
from library_assistant.config import Settings, build_catalog
from library_assistant.models import Citation


def get_settings() -> Settings:
    return Settings.from_env()


def get_catalog(settings: Settings = Depends(get_settings)) -> Catalog:
    """The configured Catalog adapter."""
    return build_catalog(settings)


async def get_http_client(
    settings: Settings = Depends(get_settings),
) -> AsyncIterator[httpx.AsyncClient]:
    """The only outbound HTTP client: scoped to the configured model endpoint (ADR-0006)."""
    async with httpx.AsyncClient(base_url=settings.openai_endpoint) as client:
        yield client


def start_exchange(
    db: sqlite3.Connection, session: Session, question: str, asked_at: datetime
) -> int:
    """Record a question the moment it is admitted, so the Live view sees it at once.

    The Class label and Card number are copied onto the row: a Revoke deletes the Card's
    row, and the exchange must still say whose Session it was. Returns the row's id.
    """
    cursor = db.execute(
        "INSERT INTO transcripts "
        "(session_hash, class_label, card_number, question, answer, citations, asked_at) "
        "VALUES (?, ?, ?, ?, '', '', ?)",
        (
            session.ref,
            session.class_label,
            session.card_number,
            question,
            asked_at.isoformat(),
        ),
    )
    db.commit()
    return cursor.lastrowid


def finish_exchange(
    db: sqlite3.Connection,
    transcript_id: int,
    answer: str,
    citations: list[Citation],
) -> None:
    """Fill in the answer and its Citations once the reply has streamed."""
    db.execute(
        "UPDATE transcripts SET answer = ?, citations = ? WHERE id = ?",
        (
            answer,
            ",".join(citation.record_id for citation in citations),
            transcript_id,
        ),
    )
    db.commit()


SessionDep = Annotated[Session, Depends(current_session)]
HttpClientDep = Annotated[httpx.AsyncClient, Depends(get_http_client)]
