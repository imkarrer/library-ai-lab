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
    return Settings()


def get_catalog(settings: Settings = Depends(get_settings)) -> Catalog:
    """The configured Catalog adapter."""
    return build_catalog(settings)


async def get_http_client(
    settings: Settings = Depends(get_settings),
) -> AsyncIterator[httpx.AsyncClient]:
    """The only outbound HTTP client: scoped to the configured model endpoint (ADR-0006)."""
    async with httpx.AsyncClient(base_url=settings.openai_endpoint) as client:
        yield client


def store_exchange(
    db: sqlite3.Connection,
    session: Session,
    question: str,
    answer: str,
    citations: list[Citation],
    asked_at: datetime,
) -> None:
    """Record one question-and-answer exchange in the Session's transcript."""
    db.execute(
        "INSERT INTO transcripts (session_hash, question, answer, citations, asked_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            session.ref,
            question,
            answer,
            ",".join(citation.record_id for citation in citations),
            asked_at.isoformat(),
        ),
    )
    db.commit()


SessionDep = Annotated[Session, Depends(current_session)]
HttpClientDep = Annotated[httpx.AsyncClient, Depends(get_http_client)]
