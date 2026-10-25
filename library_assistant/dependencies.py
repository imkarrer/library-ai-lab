"""Dependency injection for the Library Assistant."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException

from library_assistant.catalog import Catalog
from library_assistant.config import Settings, build_catalog
from library_assistant.models import Citation, Session

DB_PATH = os.environ.get("LIBRARY_ASSISTANT_DB", "library_assistant.db")


def get_clock() -> datetime:
    """Get current time in UTC."""
    return datetime.now()


def get_db() -> sqlite3.Connection:
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            card_number TEXT NOT NULL,
            class_label TEXT NOT NULL,
            started_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS transcripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            citations TEXT NOT NULL,
            asked_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def get_settings() -> Settings:
    """Get application settings."""
    return Settings()


def get_session(
    session_id: str,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
) -> Session:
    """Get a session by ID, or raise if invalid."""
    row = db.execute(
        "SELECT card_number, class_label, started_at, expires_at FROM sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()

    if row is None:
        raise HTTPException(status_code=400, detail="invalid session")

    card_number, class_label, started_at, expires_at = row
    expires_at_dt = datetime.fromisoformat(expires_at)

    if clock > expires_at_dt:
        raise HTTPException(status_code=400, detail="session expired")

    return Session(
        session_id=session_id,
        card_number=card_number,
        class_label=class_label,
        started_at=datetime.fromisoformat(started_at),
        expires_at=expires_at_dt,
    )


def get_catalog(settings: Settings = Depends(get_settings)) -> Catalog:
    """Get the configured Catalog adapter."""
    return build_catalog(settings)


async def get_http_client(
    settings: Settings = Depends(get_settings),
) -> AsyncIterator[httpx.AsyncClient]:
    """The only outbound HTTP client: scoped to the configured model endpoint."""
    async with httpx.AsyncClient(base_url=settings.openai_endpoint) as client:
        yield client


def store_exchange(
    db: sqlite3.Connection,
    session_id: str,
    question: str,
    answer: str,
    citations: list[Citation],
    asked_at: datetime,
) -> None:
    """Record one question-and-answer exchange in the Session's transcript."""
    db.execute(
        "INSERT INTO transcripts (session_id, question, answer, citations, asked_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            session_id,
            question,
            answer,
            ",".join(citation.call_number for citation in citations),
            asked_at.isoformat(),
        ),
    )
    db.commit()


SessionDep = Annotated[Session, Depends(get_session)]
HttpClientDep = Annotated[httpx.AsyncClient, Depends(get_http_client)]
