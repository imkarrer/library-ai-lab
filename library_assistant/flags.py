"""Flag management for the Library Assistant.

Binding: ADR-0002. Flags are not linked to Cards, only to transcripts.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from library_assistant.flag_history import append_event

# Close requires one of these (ADR-0003 addendum, "Flag lifecycle").
OUTCOMES = ("not_a_concern", "handled", "escalated_to_counselor", "other")


@dataclass(frozen=True)
class FlagRow:
    """A flag record from the flags table."""

    id: int
    transcript_id: int
    class_label: str
    card_number: str
    batch_expires_at: str
    message_hash: str | None
    category: str
    severity: str
    source: str
    entry_id: str | None
    watchlist_version: str | None
    reason: str | None
    raised_at: str
    closed_at: str | None
    repeat_count: int
    last_repeat_at: str | None
    # Set only by an Export, never by closing: the high-severity close gate reads it.
    exported: int | None
    escalated_at: str | None
    escalated_by: int | None


def raise_flag(
    db: sqlite3.Connection,
    transcript_id: int,
    class_label: str,
    card_number: str,
    batch_expires_at: str,
    message_hash: str | None,
    category: str,
    severity: str,
    source: str,
    raised_at: str,
    entry_id: str | None = None,
    watchlist_version: str | None = None,
    reason: str | None = None,
) -> int:
    """Raise a new flag and return its ID."""
    cursor = db.execute(
        """
        INSERT INTO flags (
            transcript_id,
            class_label,
            card_number,
            batch_expires_at,
            message_hash,
            category,
            severity,
            source,
            entry_id,
            watchlist_version,
            reason,
            raised_at,
            exported
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (
            transcript_id,
            class_label,
            card_number,
            batch_expires_at,
            message_hash,
            category,
            severity,
            source,
            entry_id,
            watchlist_version,
            reason,
            raised_at,
        ),
    )
    db.commit()
    flag_id = cursor.lastrowid
    append_event(
        db,
        flag_id,
        "raised",
        at=raised_at,
        source=source,
        entry_id=entry_id,
        watchlist_version=watchlist_version,
    )
    return flag_id


def raise_or_repeat(
    db: sqlite3.Connection,
    transcript_id: int,
    class_label: str,
    card_number: str,
    batch_expires_at: str,
    message_hash: str | None,
    category: str,
    severity: str,
    source: str,
    raised_at: str,
    entry_id: str | None = None,
    watchlist_version: str | None = None,
    reason: str | None = None,
) -> tuple[int, bool]:
    """Raise a new flag or increment repeat count if same flag already exists.

    Returns (flag_id, is_repeat) where is_repeat is True if this was a repeat.
    """
    # Check if there's an existing open flag with the same criteria
    existing_flag = db.execute(
        """
        SELECT id, repeat_count, last_repeat_at FROM flags
        WHERE class_label = ? AND card_number = ? AND batch_expires_at = ? 
        AND message_hash = ? AND category = ? AND closed_at IS NULL
        """,
        (
            class_label,
            card_number,
            batch_expires_at,
            message_hash,
            category,
        ),
    ).fetchone()

    if existing_flag:
        flag_id, repeat_count, _last_repeat_at = existing_flag
        # Update the repeat count and last repeat time
        db.execute(
            """
            UPDATE flags 
            SET repeat_count = ?, last_repeat_at = ? 
            WHERE id = ?
            """,
            (repeat_count + 1, raised_at, flag_id),
        )
        # Add a record to flag_repeats table
        db.execute(
            """
            INSERT INTO flag_repeats (flag_id, transcript_id, repeated_at) 
            VALUES (?, ?, ?)
            """,
            (flag_id, transcript_id, raised_at),
        )
        db.commit()
        append_event(
            db,
            flag_id,
            "repeated",
            at=raised_at,
            repeat_count=repeat_count + 1,
        )
        return (flag_id, True)
    else:
        # No existing flag, raise a new one
        flag_id = raise_flag(
            db,
            transcript_id,
            class_label,
            card_number,
            batch_expires_at,
            message_hash,
            category,
            severity,
            source,
            raised_at,
            entry_id,
            watchlist_version,
            reason,
        )
        return (flag_id, False)


def open_flags(db: sqlite3.Connection) -> list[FlagRow]:
    """Get all open flags (where closed_at is NULL), newest first."""
    rows = db.execute(
        """
        SELECT 
            id,
            transcript_id,
            class_label,
            card_number,
            batch_expires_at,
            message_hash,
            category,
            severity,
            source,
            entry_id,
            watchlist_version,
            reason,
            raised_at,
            closed_at,
            repeat_count,
            last_repeat_at,
            exported,
            escalated_at,
            escalated_by
        FROM flags
        WHERE closed_at IS NULL
        ORDER BY raised_at DESC
        """
    ).fetchall()

    return [FlagRow(*row) for row in rows]


def is_overdue(flag: FlagRow, now: datetime, overdue_days: int) -> bool:
    """A Flag open longer than `overdue_days` is overdue (ADR-0003 addendum)."""
    if flag.closed_at is not None:
        return False
    return datetime.fromisoformat(flag.raised_at) < now - timedelta(days=overdue_days)


def get_flag(db: sqlite3.Connection, flag_id: int) -> FlagRow | None:
    """Get a flag by ID, or None if not found."""
    row = db.execute(
        """
        SELECT 
            id,
            transcript_id,
            class_label,
            card_number,
            batch_expires_at,
            message_hash,
            category,
            severity,
            source,
            entry_id,
            watchlist_version,
            reason,
            raised_at,
            closed_at,
            repeat_count,
            last_repeat_at,
            exported,
            escalated_at,
            escalated_by
        FROM flags
        WHERE id = ?
        """,
        (flag_id,),
    ).fetchone()

    if row is None:
        return None
    return FlagRow(*row)


def close_flag(
    db: sqlite3.Connection,
    flag_id: int,
    closed_at: str,
    account: str,
    outcome: str,
    reason: str,
) -> None:
    """Close a flag by setting closed_at and clearing message_hash.

    Requires an outcome from the fixed `OUTCOMES` list and a one-line reason
    (ADR-0003 addendum, "Flag lifecycle").
    """
    if outcome not in OUTCOMES:
        raise ValueError(f"unknown close outcome: {outcome!r}")
    if not reason.strip():
        raise ValueError("close requires a reason")
    db.execute(
        """
        UPDATE flags
        SET closed_at = ?, message_hash = NULL
        WHERE id = ?
        """,
        (closed_at, flag_id),
    )
    db.commit()
    append_event(
        db,
        flag_id,
        "closed",
        at=closed_at,
        account=account,
        outcome=outcome,
        reason=reason,
    )


def reopen_flag(
    db: sqlite3.Connection,
    flag_id: int,
    reopened_at: str,
    account: str,
    reason: str,
) -> None:
    """Reopen a closed flag.

    Requires a reason, and is refused once the Purge has deleted the flag's exchange
    (ADR-0003 addendum, "Flag lifecycle").
    """
    if not reason.strip():
        raise ValueError("reopen requires a reason")
    flag = get_flag(db, flag_id)
    if flag is None:
        raise ValueError("no such flag")
    transcript = db.execute(
        "SELECT 1 FROM transcripts WHERE id = ?", (flag.transcript_id,)
    ).fetchone()
    if transcript is None:
        raise ValueError("the exchange has already been purged")
    db.execute("UPDATE flags SET closed_at = NULL WHERE id = ?", (flag_id,))
    db.commit()
    append_event(
        db, flag_id, "reopened", at=reopened_at, account=account, reason=reason
    )


def escalate_flag(
    db: sqlite3.Connection,
    flag_id: int,
    at: str,
    account_id: int,
    account: str,
    reason: str,
) -> None:
    """Mark a Flag Escalated and append the event; its Rubric category is kept."""
    db.execute(
        "UPDATE flags SET escalated_at = ?, escalated_by = ? WHERE id = ?",
        (at, account_id, flag_id),
    )
    append_event(db, flag_id, "escalated", at=at, account=account, reason=reason)
    db.commit()
