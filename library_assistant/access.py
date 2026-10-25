"""Card sign-in: Batch registration, Card sign-in, and Revoke.

Binding: ADR-0002. Registration stores nothing but a Token's hash, the Card
number, the Batch's expiry, and its Class label.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

DB_PATH = os.environ.get("LIBRARY_ASSISTANT_DB", "library_assistant.db")

REFUSAL_TEXT = "this card no longer works, ask your teacher"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_clock() -> datetime:
    return datetime.now(UTC)


def get_registration_key() -> str | None:
    return os.environ.get("LIBRARY_ASSISTANT_REGISTRATION_KEY")


def connect(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cards (
            token_hash TEXT PRIMARY KEY,
            card_number TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            class_label TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


_connection: sqlite3.Connection | None = None


def get_db() -> sqlite3.Connection:
    global _connection
    if _connection is None:
        _connection = connect()
    return _connection


class CardSpec(BaseModel):
    token: str
    card_number: str


class BatchRegistration(BaseModel):
    registration_key: str
    cards: list[CardSpec]
    expires_at: datetime
    class_label: str


class RevokeCard(BaseModel):
    registration_key: str
    class_label: str
    card_number: str
    expires_at: datetime


class RevokeBatch(BaseModel):
    registration_key: str
    class_label: str
    expires_at: datetime


router = APIRouter()


def _require_key(presented: str, expected: str | None) -> None:
    if not expected or presented != expected:
        raise HTTPException(status_code=403, detail="invalid registration key")


@router.post("/batches", status_code=201)
def register_batch(
    batch: BatchRegistration,
    db: sqlite3.Connection = Depends(get_db),
    registration_key: str | None = Depends(get_registration_key),
) -> dict[str, int]:
    _require_key(batch.registration_key, registration_key)
    db.executemany(
        "INSERT OR REPLACE INTO cards (token_hash, card_number, expires_at, class_label) "
        "VALUES (?, ?, ?, ?)",
        [
            (
                hash_token(card.token),
                card.card_number,
                batch.expires_at.isoformat(),
                batch.class_label,
            )
            for card in batch.cards
        ],
    )
    db.commit()
    return {"registered": len(batch.cards)}


@router.post("/batches/revoke-card", status_code=200)
def revoke_card(
    revoke: RevokeCard,
    db: sqlite3.Connection = Depends(get_db),
    registration_key: str | None = Depends(get_registration_key),
) -> dict[str, str]:
    _require_key(revoke.registration_key, registration_key)
    db.execute(
        "DELETE FROM cards WHERE class_label = ? AND card_number = ? AND expires_at = ?",
        (revoke.class_label, revoke.card_number, revoke.expires_at.isoformat()),
    )
    db.commit()
    return {"status": "revoked"}


@router.post("/batches/revoke-batch", status_code=200)
def revoke_batch(
    revoke: RevokeBatch,
    db: sqlite3.Connection = Depends(get_db),
    registration_key: str | None = Depends(get_registration_key),
) -> dict[str, str]:
    _require_key(revoke.registration_key, registration_key)
    db.execute(
        "DELETE FROM cards WHERE class_label = ? AND expires_at = ?",
        (revoke.class_label, revoke.expires_at.isoformat()),
    )
    db.commit()
    return {"status": "revoked"}


@router.get("/cards/{token}")
def sign_in(
    token: str,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
) -> PlainTextResponse:
    row = db.execute(
        "SELECT card_number, expires_at, class_label FROM cards WHERE token_hash = ?",
        (hash_token(token),),
    ).fetchone()
    if row is None:
        return PlainTextResponse(REFUSAL_TEXT, status_code=403)
    card_number, expires_at, class_label = row
    expires_at_dt = datetime.fromisoformat(expires_at)
    if clock > expires_at_dt:
        return PlainTextResponse(REFUSAL_TEXT, status_code=403)
    return PlainTextResponse(f"{class_label} / card {card_number}: session active")
