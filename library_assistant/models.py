"""Data models for the Library Assistant."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


# Session models
class Session(BaseModel):
    """A student's conversation session."""

    session_id: str
    card_number: str
    class_label: str
    started_at: datetime
    expires_at: datetime


class Citation(BaseModel):
    """A reference to a Record in a Grounded answer."""

    call_number: str


class AskRequest(BaseModel):
    """Request to ask a question in a session."""

    question: str


class GroundedAnswer(BaseModel):
    """A streamed answer with citations."""

    answer: str
    citations: list[Citation]
