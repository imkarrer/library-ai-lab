"""Flag management for the Library Assistant.

Binding: ADR-0002. Flags are not linked to Cards, only to transcripts.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


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
            raised_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    return cursor.lastrowid


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
            last_repeat_at
        FROM flags
        WHERE closed_at IS NULL
        ORDER BY raised_at DESC
        """
    ).fetchall()

    return [FlagRow(*row) for row in rows]


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
            last_repeat_at
        FROM flags
        WHERE id = ?
        """,
        (flag_id,),
    ).fetchone()

    if row is None:
        return None
    return FlagRow(*row)


def close_flag(db: sqlite3.Connection, flag_id: int, closed_at: str) -> None:
    """Close a flag by setting closed_at and clearing message_hash."""
    db.execute(
        """
        UPDATE flags
        SET closed_at = ?, message_hash = NULL
        WHERE id = ?
        """,
        (closed_at, flag_id),
    )
    db.commit()
