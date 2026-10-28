"""Holds: a pause on the Purge for every record in a scope (ADR-0003 addendum, "Holds").

A Hold names a scope, never a Student: Class labels (or all of them), a range of school
dates, and optionally Card numbers (ADR-0002). Only the Librarian sets or lifts one. A Hold
is never edited and never expires on its own: one older than `holds.review_days` is marked
for review instead. The Purge keeps whatever is in an active Hold's scope and nothing more.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from library_assistant.config import Settings
from library_assistant.schoolday import school_date

# ADR-0003 addendum: the kinds of request a Hold answers.
REASON_KINDS = (
    "inspection request",
    "public records request",
    "court order or subpoena",
    "law enforcement or CPS preservation",
    "other",
)

_COLUMNS = (
    "id, all_classes, class_labels, card_numbers, date_from, date_to, reason_kind, "
    "reference, set_at, set_by, lifted_at, lifted_by, lift_reason, review_marked_at"
)


@dataclass(frozen=True)
class Hold:
    id: int
    all_classes: bool
    class_labels: tuple[str, ...]
    card_numbers: tuple[str, ...]  # empty: every Card in the Class labels
    date_from: date
    date_to: date
    reason_kind: str
    reference: str
    set_at: str
    set_by: str
    lifted_at: str | None
    lifted_by: str | None
    lift_reason: str | None
    review_marked_at: str | None

    @property
    def active(self) -> bool:
        return self.lifted_at is None

    def covers(self, class_label: str, card_number: str, day: date) -> bool:
        """Whether a record of this Class label, Card number, and school date is in scope."""
        if not self.date_from <= day <= self.date_to:
            return False
        if not self.all_classes and class_label not in self.class_labels:
            return False
        return not self.card_numbers or card_number in self.card_numbers


def create_holds_table(db: sqlite3.Connection) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS holds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            all_classes INTEGER NOT NULL CHECK (all_classes IN (0, 1)),
            class_labels TEXT NOT NULL,
            card_numbers TEXT NOT NULL,
            date_from TEXT NOT NULL,
            date_to TEXT NOT NULL,
            reason_kind TEXT NOT NULL,
            reference TEXT NOT NULL,
            set_at TEXT NOT NULL,
            set_by TEXT NOT NULL,
            lifted_at TEXT,
            lifted_by TEXT,
            lift_reason TEXT,
            review_marked_at TEXT
        )
        """
    )
    # Holds are never edited (ADR-0003 addendum): to narrow one, set the narrower Hold,
    # then lift the broad one. A lift is final.
    db.execute(
        """
        CREATE TRIGGER IF NOT EXISTS holds_never_edited
        BEFORE UPDATE OF all_classes, class_labels, card_numbers, date_from, date_to,
            reason_kind, reference, set_at, set_by ON holds
        BEGIN
            SELECT RAISE(ABORT, 'a Hold is never edited');
        END
        """
    )
    db.execute(
        """
        CREATE TRIGGER IF NOT EXISTS holds_lift_is_final
        BEFORE UPDATE OF lifted_at, lifted_by, lift_reason ON holds
        WHEN OLD.lifted_at IS NOT NULL
        BEGIN
            SELECT RAISE(ABORT, 'a Hold is lifted only once');
        END
        """
    )


def _row_to_hold(row: tuple) -> Hold:
    return Hold(
        id=row[0],
        all_classes=bool(row[1]),
        class_labels=tuple(json.loads(row[2])),
        card_numbers=tuple(json.loads(row[3])),
        date_from=date.fromisoformat(row[4]),
        date_to=date.fromisoformat(row[5]),
        reason_kind=row[6],
        reference=row[7],
        set_at=row[8],
        set_by=row[9],
        lifted_at=row[10],
        lifted_by=row[11],
        lift_reason=row[12],
        review_marked_at=row[13],
    )


def _clean(values: list[str] | tuple[str, ...]) -> list[str]:
    return sorted({value.strip() for value in values if value.strip()})


def set_hold(
    db: sqlite3.Connection,
    *,
    all_classes: bool,
    class_labels: list[str],
    card_numbers: list[str],
    date_from: date,
    date_to: date,
    reason_kind: str,
    reference: str,
    set_at: datetime,
    set_by: str,
) -> int:
    """Record a new Hold and return its id. Raises ValueError on an unusable scope."""
    labels = [] if all_classes else _clean(class_labels)
    if not all_classes and not labels:
        raise ValueError("a Hold needs at least one Class label, or all of them")
    if date_from > date_to:
        raise ValueError("a Hold's from date must not be after its to date")
    if reason_kind not in REASON_KINDS:
        raise ValueError(f"unknown reason kind: {reason_kind!r}")
    if not reference.strip():
        raise ValueError("a Hold needs a reference")
    cursor = db.execute(
        "INSERT INTO holds (all_classes, class_labels, card_numbers, date_from, date_to, "
        "reason_kind, reference, set_at, set_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            int(all_classes),
            json.dumps(labels),
            json.dumps(_clean(card_numbers)),
            date_from.isoformat(),
            date_to.isoformat(),
            reason_kind,
            reference.strip(),
            set_at.isoformat(),
            set_by,
        ),
    )
    db.commit()
    return cursor.lastrowid


def lift_hold(
    db: sqlite3.Connection,
    hold_id: int,
    lifted_at: datetime,
    lifted_by: str,
    reason: str,
) -> None:
    """Lift an active Hold. The next Purge applies the ordinary rules to its records."""
    if not reason.strip():
        raise ValueError("lifting a Hold needs a reason")
    hold = get_hold(db, hold_id)
    if hold is None:
        raise LookupError(f"no such Hold: {hold_id}")
    if not hold.active:
        raise ValueError("this Hold is already lifted")
    db.execute(
        "UPDATE holds SET lifted_at = ?, lifted_by = ?, lift_reason = ? WHERE id = ?",
        (lifted_at.isoformat(), lifted_by, reason.strip(), hold_id),
    )
    db.commit()


def get_hold(db: sqlite3.Connection, hold_id: int) -> Hold | None:
    row = db.execute(
        f"SELECT {_COLUMNS} FROM holds WHERE id = ?", (hold_id,)
    ).fetchone()
    return None if row is None else _row_to_hold(row)


def all_holds(db: sqlite3.Connection) -> list[Hold]:
    """Every Hold, active ones first, newest first within each."""
    rows = db.execute(
        f"SELECT {_COLUMNS} FROM holds ORDER BY lifted_at IS NOT NULL, set_at DESC, id DESC"
    ).fetchall()
    return [_row_to_hold(row) for row in rows]


def active_holds(db: sqlite3.Connection) -> list[Hold]:
    rows = db.execute(
        f"SELECT {_COLUMNS} FROM holds WHERE lifted_at IS NULL ORDER BY id"
    ).fetchall()
    return [_row_to_hold(row) for row in rows]


def active_hold_count(db: sqlite3.Connection) -> int:
    return db.execute("SELECT COUNT(*) FROM holds WHERE lifted_at IS NULL").fetchone()[
        0
    ]


def holding(
    holds: list[Hold],
    class_label: str,
    card_number: str,
    asked_at: str,
    settings: Settings,
) -> list[Hold]:
    """The active Holds whose scope covers a transcript."""
    if not holds:
        return []
    day = school_date(datetime.fromisoformat(asked_at), settings)
    return [
        hold
        for hold in holds
        if hold.active and hold.covers(class_label, card_number, day)
    ]


def held_transcript_count(
    db: sqlite3.Connection, hold: Hold, settings: Settings
) -> int:
    """How many stored transcripts are in a Hold's scope: what it holds."""
    rows = db.execute(
        "SELECT class_label, card_number, asked_at FROM transcripts"
    ).fetchall()
    return sum(
        1
        for class_label, card_number, asked_at in rows
        if hold.covers(
            class_label,
            card_number,
            school_date(datetime.fromisoformat(asked_at), settings),
        )
    )


def mark_holds_for_review(
    db: sqlite3.Connection, now: datetime, review_days: int
) -> int:
    """Mark each active Hold set more than `review_days` ago for review, once.

    A Hold never expires on its own (ADR-0003 addendum); this is what happens instead.
    Returns how many Holds were newly marked. The caller commits.
    """
    cutoff = now - timedelta(days=review_days)
    marked = 0
    for hold in active_holds(db):
        if (
            hold.review_marked_at is None
            and datetime.fromisoformat(hold.set_at) < cutoff
        ):
            db.execute(
                "UPDATE holds SET review_marked_at = ? WHERE id = ?",
                (now.isoformat(), hold.id),
            )
            marked += 1
    return marked
