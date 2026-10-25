"""Dependency injection for the Library Assistant."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import Annotated

from fastapi import Depends, HTTPException

from library_assistant.catalog import Catalog
from library_assistant.config import Settings, build_catalog
from library_assistant.models import Session

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


SessionDep = Annotated[Session, Depends(get_session)]
