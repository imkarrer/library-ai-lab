"""Request and answer shapes for Grounded answers. A Session itself is
library_assistant.access.Session."""

from __future__ import annotations

from pydantic import BaseModel


class Citation(BaseModel):
    """A reference in a Grounded answer to the Record it came from."""

    record_id: str
    title: str
    call_number: str

    def line(self) -> str:
        return f"Citation: {self.title} ({self.call_number})"


class AskRequest(BaseModel):
    question: str
