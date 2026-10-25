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
            closed_at
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
            closed_at
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
