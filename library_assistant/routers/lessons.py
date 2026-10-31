"""The AI literacy unit's slides and student handouts, for any staff member to download.

The pipeline builds them and commits them to static/materials (scripts/publish_materials.py),
so a Teacher gets them from the Install, which needs no browser or internet to serve them
(ADR-0006). Every file is sent as a download: a deck's HTML runs its own script, which has no
business running on the assistant's address.
"""

from __future__ import annotations

import html
import sqlite3
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from library_assistant.access import get_clock, get_db
from library_assistant.staff import StaffDep, page
from library_assistant.theme import STATIC_DIR

router = APIRouter()

LESSONS_PATH = "/staff/lessons"
MATERIALS_DIR = STATIC_DIR / "materials"
LESSON_TITLES = (
    "What is this thing?",
    "Follow the Citation",
    "Catch it being wrong",
    "Who sees what I type?",
    "Using AI on assignments",
    "Ask it well",
)
_KINDS = {
    "deck.pdf": "Slides (PDF)",
    "deck.html": "Slides with speaker notes",
    "handout.pdf": "Student handout (PDF)",
}
_MEDIA_TYPES = {".pdf": "application/pdf", ".html": "text/html"}
# Only these names are ever opened, so a request can't reach anything else on disk.
_FILES = {
    f"lesson-{number}-{kind}"
    for number in range(1, len(LESSON_TITLES) + 1)
    for kind in _KINDS
}


def _cell(name: str, label: str) -> str:
    if not (MATERIALS_DIR / name).exists():
        return "<td>Not built yet</td>"
    return f'<td><a href="{LESSONS_PATH}/{name}" download>{html.escape(label)}</a></td>'


@router.get(LESSONS_PATH)
def lessons_page(
    account: StaffDep,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
) -> HTMLResponse:
    rows = "".join(
        f"<tr><td>{number}. {html.escape(title)}</td>"
        + "".join(
            _cell(f"lesson-{number}-{kind}", label) for kind, label in _KINDS.items()
        )
        + "</tr>"
        for number, title in enumerate(LESSON_TITLES, start=1)
    )
    return page(
        "Lessons",
        "<h2>Lessons</h2>"
        "<p>Teach the six lessons of Check the Source with these. Print one handout for "
        "each student, on both sides of the page.</p>"
        "<p>To see the speaker notes, open <strong>Slides with speaker notes</strong> and "
        "press <strong>P</strong>.</p>"
        '<p class="box">Have a school counselor read Lesson 4 before you teach it.</p>'
        "<table><thead><tr><th>Lesson</th>"
        + "".join(f"<th>{html.escape(label)}</th>" for label in _KINDS.values())
        + f"</tr></thead><tbody>{rows}</tbody></table>",
        account=account,
        db=db,
        now=clock,
    )


@router.get(LESSONS_PATH + "/{name}")
def lesson_file(name: str, account: StaffDep) -> FileResponse:
    path = MATERIALS_DIR / name
    if name not in _FILES or not path.exists():
        raise HTTPException(status_code=404, detail="No such lesson file")
    return FileResponse(
        path,
        media_type=_MEDIA_TYPES[path.suffix],
        filename=name,
        headers={"Cache-Control": "no-cache"},
    )
