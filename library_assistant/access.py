"""Card sign-in: Batch registration, Card sign-in, and Revoke.

Binding: ADR-0002. Registration stores nothing but a Token's hash, the Card
number, the Batch's expiry, and its Class label.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

DB_PATH = os.environ.get("LIBRARY_ASSISTANT_DB", "library_assistant.db")

REFUSAL_TEXT = "this card no longer works, ask your teacher"

SESSION_COOKIE = "session"

CARD_PAGE_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Library Assistant</title>
</head>
<body>
  <p id="status">Signing in...</p>
  <button id="finish" style="display:none">Finished</button>
  <script>
    const statusEl = document.getElementById("status");
    const finishButton = document.getElementById("finish");

    const match = window.location.hash.match(/t=([^&]+)/);
    if (match) {
      const token = decodeURIComponent(match[1]);
      fetch("/card", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ token: token }),
      }).then((response) => {
        history.replaceState(null, "", window.location.pathname);
        if (response.ok) {
          window.location.replace("/chat");
        } else {
          statusEl.textContent = "This card no longer works, ask your teacher.";
        }
      });
    } else {
      statusEl.textContent = "No card token found.";
    }

    finishButton.addEventListener("click", () => {
      fetch("/card/finish", { method: "POST", credentials: "same-origin" }).then(() => {
        statusEl.textContent = "Finished.";
        finishButton.style.display = "none";
      });
    });
  </script>
</body>
</html>
"""


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
    # A Session is one Card's conversation. Only the hash of its id is stored, so the
    # database alone cannot be replayed as a cookie; the Card row is checked on every
    # request, so a Revoke or the Batch's expiry ends the Session at once.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_hash TEXT PRIMARY KEY,
            token_hash TEXT NOT NULL,
            started_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS transcripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_hash TEXT NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            citations TEXT NOT NULL,
            asked_at TEXT NOT NULL
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


class TokenPayload(BaseModel):
    token: str


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
def sign_in_token_in_path_refused(token: str) -> PlainTextResponse:
    """A Token in the URL path reaches server logs, so it is always refused.

    Binding: ADR-0003 addendum. Cards carry their Token in the `/card#t=...` fragment,
    which browsers never send; this route exists only to refuse any Token the server does see.
    """
    return PlainTextResponse(REFUSAL_TEXT, status_code=403)


@router.get("/card", response_model=None)
def card_page(request: Request) -> HTMLResponse | PlainTextResponse:
    if "token" in request.query_params:
        return PlainTextResponse(REFUSAL_TEXT, status_code=403)
    return HTMLResponse(CARD_PAGE_HTML)


@router.post("/card")
def post_sign_in(
    payload: TokenPayload,
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
) -> PlainTextResponse:
    if "token" in request.query_params:
        return PlainTextResponse(REFUSAL_TEXT, status_code=403)
    token_hash = hash_token(payload.token)
    row = db.execute(
        "SELECT card_number, expires_at, class_label FROM cards WHERE token_hash = ?",
        (token_hash,),
    ).fetchone()
    if row is None:
        return PlainTextResponse(REFUSAL_TEXT, status_code=403)
    card_number, expires_at, class_label = row
    expires_at_dt = datetime.fromisoformat(expires_at)
    if clock > expires_at_dt:
        return PlainTextResponse(REFUSAL_TEXT, status_code=403)
    session_id = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO sessions (session_hash, token_hash, started_at) VALUES (?, ?, ?)",
        (hash_token(session_id), token_hash, clock.isoformat()),
    )
    db.commit()
    sign_in_response = PlainTextResponse(
        f"{class_label} / card {card_number}: session active"
    )
    sign_in_response.set_cookie(
        key=SESSION_COOKIE,
        value=session_id,
        httponly=True,
        samesite="strict",
    )
    return sign_in_response


@router.post("/card/finish")
def finish_session(
    request: Request,
    response: Response,
    db: sqlite3.Connection = Depends(get_db),
) -> dict[str, str]:
    """Ends this device's Session and clears its cookie. The Card itself is not Revoked."""
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        db.execute(
            "DELETE FROM sessions WHERE session_hash = ?", (hash_token(session_id),)
        )
        db.commit()
    response.delete_cookie(SESSION_COOKIE, httponly=True, samesite="strict")
    return {"status": "finished"}


@dataclass(frozen=True)
class Session:
    """One Card's conversation, as the rest of the app sees it.

    `ref` is the hash of the cookie's Session id: safe to store beside transcripts,
    useless as a cookie.
    """

    ref: str
    card_number: str
    class_label: str
    expires_at: datetime


def current_session(
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
) -> Session:
    """The Session this request's cookie names, or 403 with the Card refusal.

    The Card row is re-read every time, so Revoking a Card or Batch, or the Batch
    expiring, ends its Sessions immediately.
    """
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        raise HTTPException(status_code=403, detail=REFUSAL_TEXT)
    session_hash = hash_token(session_id)
    row = db.execute(
        "SELECT cards.card_number, cards.class_label, cards.expires_at "
        "FROM sessions JOIN cards ON cards.token_hash = sessions.token_hash "
        "WHERE sessions.session_hash = ?",
        (session_hash,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=403, detail=REFUSAL_TEXT)
    card_number, class_label, expires_at = row
    expires_at_dt = datetime.fromisoformat(expires_at)
    if clock > expires_at_dt:
        raise HTTPException(status_code=403, detail=REFUSAL_TEXT)
    return Session(
        ref=session_hash,
        card_number=card_number,
        class_label=class_label,
        expires_at=expires_at_dt,
    )
