"""Request and answer shapes for Grounded answers. A Session itself is
library_assistant.access.Session."""

from __future__ import annotations

from pydantic import BaseModel


def books_title(demo: bool) -> str:
    """What the books under an answer are called, on every page that shows them."""
    if demo:
        return "Books in our library (for this demo, our library is the Library of Congress)"
    return "Books in our library"


class Citation(BaseModel):
    """A reference in a Grounded answer to the Record it came from."""

    record_id: str
    title: str
    call_number: str
    author: str = ""
    where: str = ""
    why: str = ""


class AskRequest(BaseModel):
    question: str
