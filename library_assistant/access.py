"""Card sign-in: Batch registration, Card sign-in, and Revoke.

Binding: ADR-0002. Registration stores nothing but a Token's hash, the Card
number, the Batch's expiry, and its Class label.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from library_assistant.config import Settings, get_settings
from library_assistant.flag_history import EVENTS
from library_assistant.holds import create_holds_table
from library_assistant.schoolday import school_day_end_for
from library_assistant.watch import gate_is_open

DB_PATH = os.environ.get("LIBRARY_ASSISTANT_DB", "library_assistant.db")

REFUSAL_TEXT = "This card has stopped working. Ask your teacher for a new one."
# Every Student page sends this, so no browser cache keeps a Card or an exchange
# (ADR-0003 addendum).
NO_STORE = {"Cache-Control": "no-store"}

IDLE_TEXT = "this session ended, scan your card again"

# ADR-0010's paused wording: the assistant waits for an adult; nothing is broken.
PAUSED_TEXT = (
    "The Library Assistant is taking a break until the librarian is ready. "
    "Please ask the librarian or your teacher."
)

SESSION_COOKIE = "session"

CARD_PAGE_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="/library.css">
<title>Library Assistant</title>
</head>
<body>
  <p id="status">Signing in...</p>
  <button id="finish" style="display:none">End session</button>
  <p><a href="/about">What happens to what I type</a></p>
  <script>
    const statusEl = document.getElementById("status");
    const finishButton = document.getElementById("finish");

    const match = window.location.hash.match(/t=([^&]+)/);
    // The Token leaves the address bar at once and lives only in this page's memory.
    history.replaceState(null, "", window.location.pathname);
    const RETRY_MS = 5000;
    const signIn = (token) => {
      fetch("/card", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ token: token }),
      }).then(async (response) => {
        if (response.ok) {
          window.location.replace("/chat");
        } else if (response.status === 503) {
          // Nobody is on Watch: a valid Card waits, and this same scan signs in the
          // moment an adult starts watching (ADR-0010). Not a dead Card.
          statusEl.textContent = await response.text();
          setTimeout(() => signIn(token), RETRY_MS);
        } else {
          statusEl.textContent = "This card has stopped working. Ask your teacher for a new one.";
        }
      }).catch(() => {
        statusEl.textContent = "Can't reach the Library Assistant. Trying again...";
        setTimeout(() => signIn(token), RETRY_MS);
      });
    };
    if (match) {
      signIn(decodeURIComponent(match[1]));
    } else {
      statusEl.textContent = "No card token found.";
    }

    finishButton.addEventListener("click", () => {
      fetch("/card/finish", { method: "POST", credentials: "same-origin" }).then(() => {
        statusEl.textContent = "Session ended. You can close this page.";
        finishButton.style.display = "none";
      });
    });
  </script>
</body>
</html>
"""


def utc_iso(moment: datetime) -> str:
    """How a Card's expiry is stored and matched: UTC ISO 8601, so the SQL that compares
    expiries as text (Live view tiles, the Purge) orders them as times (lib-4vf). A Batch
    registered with an offset ("-05:00", as the CLI sends) sorted as expired hours early."""
    return moment.astimezone(UTC).isoformat()


def _expiries_in_utc(conn: sqlite3.Connection) -> None:
    """Convert expiries stored with an offset before lib-4vf; a no-op once done."""
    for table, column in (("cards", "expires_at"), ("flags", "batch_expires_at")):
        rows = conn.execute(
            f"SELECT rowid, {column} FROM {table} WHERE {column} NOT LIKE '%+00:00'"
        ).fetchall()
        for rowid, value in rows:
            conn.execute(
                f"UPDATE {table} SET {column} = ? WHERE rowid = ?",
                (utc_iso(datetime.fromisoformat(value)), rowid),
            )
    conn.commit()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_clock() -> datetime:
    return datetime.now(UTC)


# The counts each Purge run records beside its time (PurgeReport's fields).
PURGE_RUN_COUNTS = (
    "deleted",
    "kept_for_flags",
    "kept_unscreened",
    "kept_for_holds",
    "holds",
    "overdue_flags",
)


def _add_missing_columns(
    conn: sqlite3.Connection,
    table: str,
    columns: tuple[str, ...],
    definition: str = "INTEGER",
) -> None:
    """Add columns an older database's table lacks: NULL on old rows, unless
    `definition` gives a default."""
    present = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    for column in columns:
        if column not in present:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


FLAG_HISTORY_SQL = """
        CREATE TABLE IF NOT EXISTS flag_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            flag_id INTEGER NOT NULL,
            event TEXT NOT NULL CHECK (event IN ({events})),
            at TEXT NOT NULL,
            account TEXT,
            reason TEXT,
            outcome TEXT,
            source TEXT,
            entry_id TEXT,
            watchlist_version TEXT,
            repeat_count INTEGER
        )
        """


def _create_flag_history(conn: sqlite3.Connection) -> None:
    """Create flag_history, or rebuild an older one whose CHECK lacks a newer event.

    SQLite cannot alter a CHECK, so the rows move to a fresh table, in order.
    """
    events = ", ".join(f"'{event}'" for event in EVENTS)
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'flag_history'"
    ).fetchone()
    if row is not None and all(f"'{event}'" in row[0] for event in EVENTS):
        return
    if row is not None:
        conn.execute("ALTER TABLE flag_history RENAME TO flag_history_old")
    conn.execute(FLAG_HISTORY_SQL.format(events=events))
    if row is not None:
        conn.execute("INSERT INTO flag_history SELECT * FROM flag_history_old")
        conn.execute("DROP TABLE flag_history_old")
    conn.commit()


def connect(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    # Enable secure_delete to overwrite deleted data with zeros
    conn.execute("PRAGMA secure_delete = ON")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cards (
            token_hash TEXT PRIMARY KEY,
            card_number TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            class_label TEXT NOT NULL,
            registered_by_account_id INTEGER REFERENCES staff_accounts (id)
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
            started_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00+00:00'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS transcripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_hash TEXT NOT NULL,
            class_label TEXT NOT NULL,
            card_number TEXT NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            citations TEXT NOT NULL,
            asked_at TEXT NOT NULL,
            verdict TEXT,
            screened_at TEXT,
            screening TEXT NOT NULL DEFAULT 'none' CHECK (screening IN ('none','oversight','watchlist_alone'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS flags (
            id INTEGER PRIMARY KEY,
            transcript_id INTEGER NOT NULL,
            class_label TEXT NOT NULL,
            card_number TEXT NOT NULL,
            batch_expires_at TEXT NOT NULL,
            message_hash TEXT,
            category TEXT NOT NULL,
            severity TEXT NOT NULL,
            source TEXT NOT NULL CHECK (source IN ('watchlist','oversight')),
            entry_id TEXT,
            watchlist_version TEXT,
            reason TEXT,
            raised_at TEXT NOT NULL,
            closed_at TEXT,
            repeat_count INTEGER NOT NULL DEFAULT 0,
            last_repeat_at TEXT,
            exported INTEGER NOT NULL DEFAULT 0,
            escalated_at TEXT,
            escalated_by INTEGER,
            raised_unwatched INTEGER NOT NULL DEFAULT 0,
            acknowledged_at TEXT,
            acknowledged_by INTEGER,
            escalation_acknowledged_at TEXT,
            escalation_acknowledged_by INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS flag_repeats (
            flag_id INTEGER NOT NULL,
            transcript_id INTEGER NOT NULL,
            repeated_at TEXT NOT NULL
        )
        """
    )
    # The append-only Flag history (ADR-0003 addendum, "Flag lifecycle"). Written and
    # read only through library_assistant.flag_history.
    _create_flag_history(conn)
    # Staff accounts and their sessions (library_assistant.staff). As with a Student's
    # Session, only the hash of the staff session id is stored.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS staff_accounts (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('librarian', 'teacher', 'counselor')),
            is_stand_in INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS staff_sessions (
            session_hash TEXT PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES staff_accounts (id),
            expires_at TEXT NOT NULL
        )
        """
    )
    # The Install's one Watch (library_assistant.watch, ADR-0010): a row per staff account
    # on Watch. Staff data, never a Session or a Card; the Purge does not need it.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS watchers (
            account_id INTEGER PRIMARY KEY REFERENCES staff_accounts (id),
            started_at TEXT NOT NULL,
            last_heartbeat_at TEXT NOT NULL
        )
        """
    )
    # Each Teacher's or the Librarian's own Registration key (ADR-0002 addendum,
    # "each Teacher registers with their own key"). Rotating replaces this row, so the
    # old key's hash is simply gone.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS registration_keys (
            account_id INTEGER PRIMARY KEY REFERENCES staff_accounts (id),
            key_hash TEXT NOT NULL,
            rotated_at TEXT NOT NULL
        )
        """
    )
    # The Purge run record: one row per run, with its report (library_assistant.purge).
    # Its existence for a day end also stops the Purge running twice for it.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS purge_runs (
            ran_at TEXT NOT NULL
        )
        """
    )
    _add_missing_columns(conn, "purge_runs", PURGE_RUN_COUNTS)
    # An older flags table predates the Export record; its Flags read as not exported.
    _add_missing_columns(conn, "flags", ("exported", "escalated_by"))
    if "escalated_at" not in {r[1] for r in conn.execute("PRAGMA table_info(flags)")}:
        conn.execute("ALTER TABLE flags ADD COLUMN escalated_at TEXT")
    # An older flags table predates the gate; its Flags read as raised while watched.
    _add_missing_columns(
        conn, "flags", ("raised_unwatched",), "INTEGER NOT NULL DEFAULT 0"
    )
    # An older flags table predates the Alarm (ADR-0010): who Acknowledged it and when,
    # and the same for the Counselor's Alarm on an Escalated Flag. Staff data only.
    _add_missing_columns(
        conn, "flags", ("acknowledged_by", "escalation_acknowledged_by")
    )
    _add_missing_columns(
        conn, "flags", ("acknowledged_at", "escalation_acknowledged_at"), "TEXT"
    )
    # An older staff_accounts table predates deactivation; its accounts stay active.
    _add_missing_columns(
        conn, "staff_accounts", ("is_active",), "INTEGER NOT NULL DEFAULT 1"
    )
    # Holds (ADR-0003 addendum): a scope the Purge keeps; never a Student.
    create_holds_table(conn)
    # Install settings (library_assistant.install_settings). Only the Librarian manages
    # these (ADR-0010).
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS install_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    # Track changes to install settings
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS setting_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT NOT NULL,
            account_id INTEGER NOT NULL,
            changed_at TEXT NOT NULL
        )
        """
    )
    # Track flag reviews
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS flag_reviews (
            account_id INTEGER NOT NULL,
            reviewed_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    _expiries_in_utc(conn)
    return conn


_connection: sqlite3.Connection | None = None


def get_db() -> sqlite3.Connection:
    global _connection
    if _connection is None:
        _connection = connect()
    return _connection


def last_review_at(db: sqlite3.Connection) -> datetime | None:
    """Get the timestamp of the most recent flag review."""
    row = db.execute(
        "SELECT reviewed_at FROM flag_reviews ORDER BY reviewed_at DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    return datetime.fromisoformat(row[0])


def review_due_at(
    db: sqlite3.Connection, settings_db_values: dict[str, str], now: datetime
) -> datetime | None:
    """Get the due time for the next flag review, or None if not in periodic mode."""
    # Check if we're in periodic mode
    supervision_mode = settings_db_values.get("supervision_mode", "live")
    if supervision_mode != "periodic":
        return None

    # Get the last review time
    last_review = last_review_at(db)
    if last_review is None:
        return None

    # Get the review interval from settings
    try:
        reviews_every_minutes = int(
            settings_db_values.get("reviews_every_minutes", "120")
        )
    except (ValueError, TypeError):
        reviews_every_minutes = 120  # Default value

    # Calculate the due time
    due_time = last_review + timedelta(minutes=reviews_every_minutes)
    return due_time


class CardSpec(BaseModel):
    """One Card in a Registration: its Token's hash, never the Token (ADR-0002).

    Unknown fields are refused, so a payload that still carries a raw `token` gets a
    422 rather than being accepted.
    """

    model_config = ConfigDict(extra="forbid")

    token_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
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


def account_for_registration_key(db: sqlite3.Connection, key: str) -> int | None:
    """The active staff account whose Registration key this is, or None.

    None when the key was never issued, was rotated away, or belongs to an account the
    Librarian has deactivated: a deactivated account's key stops working at once
    (ADR-0002 addendum), though its hash row stays.
    """
    row = db.execute(
        "SELECT registration_keys.account_id FROM registration_keys "
        "JOIN staff_accounts ON staff_accounts.id = registration_keys.account_id "
        "WHERE registration_keys.key_hash = ? AND staff_accounts.is_active = 1",
        (hash_token(key),),
    ).fetchone()
    return row[0] if row else None


def registering_teacher(
    db: sqlite3.Connection, class_label: str, card_number: str, expires_at: str
) -> str | None:
    """The display name of the Teacher (or Librarian) who registered this Batch.

    Looked up by the Batch's own class label, card number, and expiry, never by the
    staff account's current state: a deactivated account's name still shows on a
    Batch that has not expired, so a Flag or a Live view row never loses its Teacher
    (ADR-0002 addendum).
    """
    row = db.execute(
        "SELECT staff_accounts.username FROM cards "
        "JOIN staff_accounts ON staff_accounts.id = cards.registered_by_account_id "
        "WHERE cards.class_label = ? AND cards.card_number = ? AND cards.expires_at = ?",
        (class_label, card_number, expires_at),
    ).fetchone()
    return row[0] if row else None


def issue_registration_key(
    db: sqlite3.Connection, account_id: int, clock: datetime
) -> str:
    """Mint a fresh Registration key for an account, replacing any key it already had."""
    key = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO registration_keys (account_id, key_hash, rotated_at) VALUES (?, ?, ?) "
        "ON CONFLICT (account_id) DO UPDATE SET "
        "key_hash = excluded.key_hash, rotated_at = excluded.rotated_at",
        (account_id, hash_token(key), clock.isoformat()),
    )
    db.commit()
    return key


def _account_for_key_or_403(db: sqlite3.Connection, key: str) -> int:
    account_id = account_for_registration_key(db, key)
    if account_id is None:
        raise HTTPException(status_code=403, detail="invalid registration key")
    return account_id


@router.post("/batches", status_code=201)
def register_batch(
    batch: BatchRegistration,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
    settings: Settings = Depends(get_settings),
) -> dict[str, int]:
    account_id = _account_for_key_or_403(db, batch.registration_key)
    end = school_day_end_for(clock, settings)
    if clock >= end:
        raise HTTPException(
            status_code=422,
            detail="Registration is closed: today's school day has ended.",
        )
    if batch.expires_at > end:
        raise HTTPException(
            status_code=422,
            detail="A Batch must expire by the end of today's school day.",
        )
    db.executemany(
        "INSERT OR REPLACE INTO cards "
        "(token_hash, card_number, expires_at, class_label, registered_by_account_id) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            (
                card.token_hash,
                card.card_number,
                utc_iso(batch.expires_at),
                batch.class_label,
                account_id,
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
) -> dict[str, str]:
    _account_for_key_or_403(db, revoke.registration_key)
    db.execute(
        "DELETE FROM cards WHERE class_label = ? AND card_number = ? AND expires_at = ?",
        (revoke.class_label, revoke.card_number, utc_iso(revoke.expires_at)),
    )
    db.commit()
    return {"status": "revoked"}


@router.post("/batches/revoke-batch", status_code=200)
def revoke_batch(
    revoke: RevokeBatch,
    db: sqlite3.Connection = Depends(get_db),
) -> dict[str, str]:
    _account_for_key_or_403(db, revoke.registration_key)
    db.execute(
        "DELETE FROM cards WHERE class_label = ? AND expires_at = ?",
        (revoke.class_label, utc_iso(revoke.expires_at)),
    )
    db.commit()
    return {"status": "revoked"}


def revoke_card_of_session(db: sqlite3.Connection, session_no: int) -> bool:
    """Revoke the Card behind a Session. False if the Card is already gone."""
    row = db.execute(
        "SELECT token_hash FROM sessions WHERE rowid = ?", (session_no,)
    ).fetchone()
    if not row:
        return False
    (token_hash,) = row
    cursor = db.execute("DELETE FROM cards WHERE token_hash = ?", (token_hash,))
    db.commit()
    return cursor.rowcount > 0


def revoke_batch_of_session(db: sqlite3.Connection, session_no: int) -> int:
    """Revoke every Card in the Batch behind a Session. 0 if the Card is already gone."""
    row = db.execute(
        "SELECT token_hash FROM sessions WHERE rowid = ?", (session_no,)
    ).fetchone()
    if not row:
        return 0
    (token_hash,) = row
    card_row = db.execute(
        "SELECT class_label, expires_at FROM cards WHERE token_hash = ?",
        (token_hash,),
    ).fetchone()
    if not card_row:
        return 0
    class_label, expires_at = card_row
    cursor = db.execute(
        "DELETE FROM cards WHERE class_label = ? AND expires_at = ?",
        (class_label, expires_at),
    )
    db.commit()
    return cursor.rowcount


@router.get("/cards/{token}")
def sign_in_token_in_path_refused(token: str) -> PlainTextResponse:
    """A Token in the URL path reaches server logs, so it is always refused.

    Binding: ADR-0003 addendum. Cards carry their Token in the `/card#t=...` fragment,
    which browsers never send; this route exists only to refuse any Token the server does see.
    """
    return PlainTextResponse(REFUSAL_TEXT, status_code=403, headers=NO_STORE)


@router.get("/card", response_model=None)
def card_page(request: Request) -> HTMLResponse | PlainTextResponse:
    if "token" in request.query_params:
        return PlainTextResponse(REFUSAL_TEXT, status_code=403, headers=NO_STORE)
    return HTMLResponse(CARD_PAGE_HTML, headers=NO_STORE)


@router.post("/card")
def post_sign_in(
    payload: TokenPayload,
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
) -> PlainTextResponse:
    if "token" in request.query_params:
        return PlainTextResponse(REFUSAL_TEXT, status_code=403, headers=NO_STORE)
    token_hash = hash_token(payload.token)
    row = db.execute(
        "SELECT card_number, expires_at, class_label FROM cards WHERE token_hash = ?",
        (token_hash,),
    ).fetchone()
    if row is None:
        return PlainTextResponse(REFUSAL_TEXT, status_code=403, headers=NO_STORE)
    card_number, expires_at, class_label = row
    expires_at_dt = datetime.fromisoformat(expires_at)
    if clock > expires_at_dt:
        return PlainTextResponse(REFUSAL_TEXT, status_code=403, headers=NO_STORE)

    if not gate_is_open(db, clock):
        return PlainTextResponse(PAUSED_TEXT, status_code=503, headers=NO_STORE)

    # If the request already carries a `session` cookie, delete that sessions row
    # before creating the new one, so the previous Student's Session on this device ends
    session_id = secrets.token_urlsafe(32)
    if SESSION_COOKIE in request.cookies:
        old_session_id = request.cookies[SESSION_COOKIE]
        db.execute(
            "DELETE FROM sessions WHERE session_hash = ?", (hash_token(old_session_id),)
        )

    db.execute(
        "INSERT INTO sessions (session_hash, token_hash, started_at, last_seen_at) "
        "VALUES (?, ?, ?, ?)",
        (hash_token(session_id), token_hash, clock.isoformat(), clock.isoformat()),
    )
    db.commit()
    sign_in_response = PlainTextResponse(
        f"{class_label} / card {card_number}: session active", headers=NO_STORE
    )
    # The new cookie gets `expires=` the Card's expires_at, so the browser drops it
    # when the Card stops working. It is still HttpOnly, SameSite=Strict.
    sign_in_response.set_cookie(
        key=SESSION_COOKIE,
        value=session_id,
        httponly=True,
        samesite="strict",
        # A cookie's expires= must be GMT; a Batch registered by the CLI carries an offset.
        expires=expires_at_dt.astimezone(UTC),
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
    response.headers.update(NO_STORE)
    response.delete_cookie(SESSION_COOKIE, httponly=True, samesite="strict")
    return {"status": "finished"}


@dataclass(frozen=True)
class Session:
    """One Card's conversation, as the rest of the app sees it.

    `ref` is the hash of the cookie's Session id: safe to store beside transcripts,
    useless as a cookie.

    `card_ref` is the Card's Token hash, so rules keyed on the Card (one message in
    flight) hold across every Session it has. It lives in memory only: never rendered,
    logged or stored anywhere new (ADR-0002), hence kept out of the repr.
    """

    ref: str
    card_number: str
    class_label: str
    expires_at: datetime
    card_ref: str = field(repr=False)


def current_session(
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
) -> Session:
    """The Session this request's cookie names, or 403 with the Card refusal.

    The Card row is re-read every time, so Revoking a Card or Batch, or the Batch
    expiring, ends its Sessions immediately.
    """
    # Imported here, not at module level: install_settings imports get_db from this
    # module, so importing it up top would be circular.
    from library_assistant.install_settings import SESSION_IDLE_MINUTES, get_int_setting

    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        raise HTTPException(status_code=403, detail=REFUSAL_TEXT, headers=NO_STORE)
    session_hash = hash_token(session_id)
    row = db.execute(
        "SELECT cards.card_number, cards.class_label, cards.expires_at, "
        "sessions.last_seen_at, sessions.token_hash "
        "FROM sessions JOIN cards ON cards.token_hash = sessions.token_hash "
        "WHERE sessions.session_hash = ?",
        (session_hash,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=403, detail=REFUSAL_TEXT, headers=NO_STORE)
    card_number, class_label, expires_at, last_seen_at, token_hash = row
    expires_at_dt = datetime.fromisoformat(expires_at)
    if clock > expires_at_dt:
        raise HTTPException(status_code=403, detail=REFUSAL_TEXT, headers=NO_STORE)

    idle_minutes = get_int_setting(db, SESSION_IDLE_MINUTES, 0)
    if idle_minutes > 0:
        idle_for = clock - datetime.fromisoformat(last_seen_at)
        if idle_for > timedelta(minutes=idle_minutes):
            db.execute("DELETE FROM sessions WHERE session_hash = ?", (session_hash,))
            db.commit()
            raise HTTPException(status_code=403, detail=IDLE_TEXT, headers=NO_STORE)
    db.execute(
        "UPDATE sessions SET last_seen_at = ? WHERE session_hash = ?",
        (clock.isoformat(), session_hash),
    )
    db.commit()

    return Session(
        ref=session_hash,
        card_number=card_number,
        class_label=class_label,
        expires_at=expires_at_dt,
        card_ref=token_hash,
    )
