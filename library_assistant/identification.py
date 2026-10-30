"""Identification requests (lib-axb, ADR-0002 addendum): an adult working a Flag asks the
registering Teacher who held the Card, and the Teacher's own Minting page answers it.

The assistant carries the question, never the answer's name. A request says which Flag's
Card (Class label, Card number, the Batch's expiry), whom it is for (the Teacher who
registered the Batch), who asked, and when; the Teacher's reply is only "told them" or "not
in my Rosters". The name is looked up on the Teacher's computer, from the Roster it keeps
(lib-3t8), and passes between the two adults in person: Identification stays offline.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from library_assistant.flag_history import append_event

# What the Teacher answers. Never a name.
TOLD = "told"
NOT_IN_ROSTERS = "not_in_rosters"
ANSWERS = (TOLD, NOT_IN_ROSTERS)


def create_identification_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS identification_requests (
            id INTEGER PRIMARY KEY,
            flag_id INTEGER NOT NULL,
            teacher_account_id INTEGER NOT NULL,
            requested_by_account_id INTEGER NOT NULL,
            requested_at TEXT NOT NULL,
            answer TEXT CHECK (answer IN ('told', 'not_in_rosters')),
            answered_at TEXT
        )
        """
    )


@dataclass(frozen=True)
class Request:
    id: int
    flag_id: int
    teacher: str
    requested_by: str
    requested_by_role: str
    requested_at: str
    answer: str | None
    answered_at: str | None
    class_label: str
    card_number: str
    batch_expires_at: str
    severity: str

    def for_teacher(self) -> dict:
        """What the Teacher's page needs to find the name in its Rosters, and how urgent
        it is: never the Flag's category, reason, or the Student's words."""
        return {
            "request_id": self.id,
            "class_label": self.class_label,
            "card_number": self.card_number,
            "batch_expires_at": self.batch_expires_at,
            "requested_by": self.requested_by,
            "requested_by_role": self.requested_by_role,
            "requested_at": self.requested_at,
            "severity": self.severity,
        }


_SELECT = (
    "SELECT r.id, r.flag_id, teacher.username, asker.username, asker.role, "
    "r.requested_at, r.answer, r.answered_at, f.class_label, f.card_number, "
    "f.batch_expires_at, f.severity "
    "FROM identification_requests r "
    "JOIN flags f ON f.id = r.flag_id "
    "JOIN staff_accounts teacher ON teacher.id = r.teacher_account_id "
    "JOIN staff_accounts asker ON asker.id = r.requested_by_account_id "
)


def flag_teacher_id(db: sqlite3.Connection, flag_id: int) -> int | None:
    row = db.execute(
        "SELECT registered_by_account_id FROM flags WHERE id = ?", (flag_id,)
    ).fetchone()
    return row[0] if row else None


def request_for_flag(db: sqlite3.Connection, flag_id: int) -> Request | None:
    """The Flag's latest request, answered or not."""
    row = db.execute(
        _SELECT + "WHERE r.flag_id = ? ORDER BY r.id DESC", (flag_id,)
    ).fetchone()
    return Request(*row) if row else None


def ask(
    db: sqlite3.Connection, flag_id: int, requested_by: int, at: datetime
) -> Request | None:
    """Ask the Flag's registering Teacher who held the Card. An unanswered request is
    reused, not repeated. None when the Flag has no Teacher on record."""
    teacher_id = flag_teacher_id(db, flag_id)
    if teacher_id is None:
        return None
    pending = request_for_flag(db, flag_id)
    if pending is not None and pending.answer is None:
        return pending
    db.execute(
        "INSERT INTO identification_requests (flag_id, teacher_account_id, "
        "requested_by_account_id, requested_at) VALUES (?, ?, ?, ?)",
        (flag_id, teacher_id, requested_by, at.isoformat()),
    )
    asker = db.execute(
        "SELECT username FROM staff_accounts WHERE id = ?", (requested_by,)
    ).fetchone()[0]
    append_event(
        db, flag_id, "identification_requested", at=at.isoformat(), account=asker
    )
    db.commit()
    return request_for_flag(db, flag_id)


def open_requests_for(db: sqlite3.Connection, teacher_id: int) -> list[Request]:
    """A Teacher's unanswered requests on Flags still open, oldest first."""
    rows = db.execute(
        _SELECT + "WHERE r.teacher_account_id = ? AND r.answer IS NULL "
        "AND f.closed_at IS NULL ORDER BY r.id",
        (teacher_id,),
    ).fetchall()
    return [Request(*row) for row in rows]


def answer(
    db: sqlite3.Connection,
    request_id: int,
    teacher_id: int,
    reply: str,
    at: datetime,
) -> Request | None:
    """Record the Teacher's answer to their own request. None if it is not theirs, is
    already answered, or `reply` is not an answer."""
    if reply not in ANSWERS:
        return None
    row = db.execute(
        "SELECT r.flag_id, s.username FROM identification_requests r "
        "JOIN staff_accounts s ON s.id = r.teacher_account_id "
        "WHERE r.id = ? AND r.teacher_account_id = ? AND r.answer IS NULL",
        (request_id, teacher_id),
    ).fetchone()
    if row is None:
        return None
    flag_id, teacher = row
    db.execute(
        "UPDATE identification_requests SET answer = ?, answered_at = ? WHERE id = ?",
        (reply, at.isoformat(), request_id),
    )
    append_event(
        db,
        flag_id,
        "identification_answered",
        at=at.isoformat(),
        account=teacher,
        outcome=reply,
    )
    db.commit()
    return request_for_flag(db, flag_id)
