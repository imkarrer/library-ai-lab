"""Whole journeys through the real stack (lib-eih): `./stack up --mock` in a temp folder,
the fake model on both Lanes, the LoC fixture Catalog, and real HTTP, as a Teacher, the
Librarian, a Counselor, and Students would use it.

Each test is one journey a school day contains. They run against one stack per module, so
the whole file takes a few seconds; add a journey here before changing how one behaves.

The stack's school day runs in a fixed-offset zone where it is about midday now, so
"expires by the end of today's school day" never trips at a real midnight.
"""

from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from library_assistant.mint import mint_cards

REPO = Path(__file__).resolve().parent.parent
PAUSED = "taking a break"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _midday_zone() -> str:
    """An Etc/GMT zone where the local time is now between 11:00 and 13:00."""
    offset = 12 - datetime.now(UTC).hour
    offset = (offset + 12) % 24 - 12  # into -12..11
    # Etc/GMT signs are inverted: Etc/GMT-5 is UTC+5.
    return "Etc/GMT" if offset == 0 else f"Etc/GMT{-offset:+d}"


def _stack(state: Path, *args: str) -> str:
    result = subprocess.run(
        [sys.executable, str(REPO / "scripts/stack.py"), "--state", str(state), *args],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


@dataclass
class Install:
    base: str
    state: Path
    passwords: dict[str, str]
    teacher_key: str

    def staff(self, username: str) -> httpx.Client:
        client = httpx.Client(base_url=self.base, timeout=30, follow_redirects=True)
        response = client.post(
            "/staff/login",
            data={"username": username, "password": self.passwords[username]},
        )
        assert response.status_code == 200, response.text
        return client

    def mint(self, count: int, class_label: str) -> list[str]:
        """Register a Batch as the Teacher's Minting page does; return its Tokens."""
        result = mint_cards(count, class_label, datetime.now(UTC) + timedelta(hours=2))
        response = httpx.post(
            f"{self.base}/batches",
            json={"registration_key": self.teacher_key, **result.registration_payload},
        )
        assert response.status_code == 201, response.text
        return [card.token for card in result.cards]

    def student(self, token: str) -> httpx.Client:
        client = httpx.Client(base_url=self.base, timeout=30, follow_redirects=True)
        response = client.post("/card", json={"token": token})
        assert response.status_code == 200, response.text
        return client


@pytest.fixture(scope="module")
def install(tmp_path_factory) -> Iterator[Install]:
    state = tmp_path_factory.mktemp("stack")
    port, fake_port = _free_port(), _free_port()
    _stack(
        state,
        "up",
        "--mock",
        "--port",
        str(port),
        "--fake-port",
        str(fake_port),
        "--fake-delay-ms",
        "0",
        "--timezone",
        _midday_zone(),
    )
    try:
        passwords = {
            line.split(" ")[0]: line.rsplit(": ", 1)[1]
            for line in (state / "credentials.txt").read_text().splitlines()
        }
        page = (state / "teacher-minting-page.html").read_text()
        config = json.loads(
            re.search(r'id="install-config">(.*?)</script>', page, re.DOTALL).group(1)
        )
        yield Install(
            f"http://127.0.0.1:{port}", state, passwords, config["registration_key"]
        )
    finally:
        _stack(state, "down")


@pytest.fixture
def librarian(install) -> Iterator[httpx.Client]:
    client = install.staff("librarian")
    assert client.post("/staff/watch/start").status_code == 200
    yield client
    client.post("/staff/watch/end")


def _wait_for(check: Callable[[], object], seconds: float = 10) -> object:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(0.2)
    raise AssertionError("timed out waiting")


def _flags(install: Install, class_label: str) -> list[tuple]:
    import sqlite3

    db = sqlite3.connect(install.state / "demo.db")
    try:
        return db.execute(
            "SELECT id, category, severity, source FROM flags WHERE class_label = ? "
            "ORDER BY id",
            (class_label,),
        ).fetchall()
    finally:
        db.close()


# --- Journeys -------------------------------------------------------------------------


def test_a_card_scanned_before_watch_waits_then_answers_with_books(install):
    [token] = install.mint(1, "Journey wait")
    student = httpx.Client(base_url=install.base, timeout=30)

    paused = student.post("/card", json={"token": token})
    assert paused.status_code == 503 and PAUSED in paused.text

    librarian = install.staff("librarian")
    librarian.post("/staff/watch/start")
    try:
        assert student.post("/card", json={"token": token}).status_code == 200
        answer = student.post("/ask", json={"question": "Clifford the big red dog"})
        assert answer.status_code == 200
        assert "Here is a short overview" in answer.text
        assert "SEARCH" not in answer.text
        assert "Books in our library:" in answer.text
        assert "Clifford the big red dog" in answer.text
    finally:
        librarian.post("/staff/watch/end")


def test_end_watch_pauses_a_student_mid_session(install, librarian):
    [token] = install.mint(1, "Journey pause")
    student = install.student(token)
    assert student.post("/ask", json={"question": "volcanoes"}).status_code == 200

    librarian.post("/staff/watch/end")
    paused = student.post("/ask", json={"question": "more volcanoes"})
    assert paused.status_code == 503 and PAUSED in paused.text
    librarian.post("/staff/watch/start")


def test_a_paraphrase_the_watchlist_misses_reaches_the_panel_via_oversight(
    install, librarian
):
    [token] = install.mint(1, "Journey oversight")
    student = install.student(token)

    student.post("/ask", json={"question": "Billy says I stink and makes me cry"})

    [(flag_id, category, severity, source)] = _wait_for(
        lambda: _flags(install, "Journey oversight")
    )
    assert (category, severity, source) == ("bullying", "low", "oversight")
    live = librarian.get("/staff/live").text
    panel = live[live.index('id="open-flags-panel"') : live.index("</section>")]
    assert f'data-flag-id="{flag_id}"' in panel
    assert '<span class="stage">New</span>' in panel
    assert "bullying" not in panel and "stink" not in panel


def test_a_flag_goes_new_acknowledged_closed(install, librarian):
    [token] = install.mint(1, "Journey lifecycle")
    install.student(token).post("/ask", json={"question": "everyone picks on me"})
    [(flag_id, *_)] = _wait_for(lambda: _flags(install, "Journey lifecycle"))

    assert ">New<" in librarian.get(f"/staff/flags/{flag_id}").text
    librarian.post(f"/staff/flags/{flag_id}/acknowledge")
    assert ">Acknowledged<" in librarian.get(f"/staff/flags/{flag_id}").text

    closed = librarian.post(
        f"/staff/flags/{flag_id}/close",
        data={"outcome": "not_a_concern", "reason": "talked it through"},
    )
    assert closed.status_code == 200  # followed to the Flag queue
    assert f'data-flag-id="{flag_id}"' not in librarian.get("/staff/live").text


def test_the_demo_phrase_gets_the_supportive_reply_and_an_alarm(install, librarian):
    [token] = install.mint(1, "Journey alarm")
    reply = install.student(token).post("/ask", json={"question": "library demo flag"})

    assert "988" in reply.text
    [(flag_id, _category, severity, source)] = _flags(install, "Journey alarm")
    assert (severity, source) == ("high", "watchlist")
    pending = librarian.post("/staff/watch/start").json()["alarms"]
    assert flag_id in [alarm["flag_id"] for alarm in pending]
    librarian.post(f"/staff/alarms/{flag_id}/acknowledge")


def test_an_escalated_flag_is_the_counselors_to_close(install, librarian):
    [token] = install.mint(1, "Journey escalate")
    install.student(token).post("/ask", json={"question": "everyone picks on me"})
    [(flag_id, *_)] = _wait_for(lambda: _flags(install, "Journey escalate"))

    librarian.post(
        f"/staff/flags/{flag_id}/escalate", data={"reason": "for the counselor"}
    )
    refused = librarian.post(
        f"/staff/flags/{flag_id}/close", data={"outcome": "handled", "reason": "x"}
    )
    assert refused.status_code == 409

    counselor = install.staff("counselor")
    assert f"/staff/counselor/flags/{flag_id}" in counselor.get("/staff/counselor").text
    done = counselor.post(
        f"/staff/counselor/flags/{flag_id}/close",
        data={"outcome": "handled", "reason": "met with the student"},
    )
    assert done.status_code == 200
    assert f'data-flag-id="{flag_id}"' not in librarian.get("/staff/live").text


def test_a_revoked_card_is_refused_at_its_next_question(install, librarian):
    [token] = install.mint(1, "Journey revoke")
    student = install.student(token)
    session_no = re.search(
        r'data-session-no="(\d+)"[^>]*>\s*<a[^>]*>\s*<p class="who">Journey revoke',
        librarian.get("/staff/live").text,
    )
    assert session_no, "the Student's tile is on the Live view"

    librarian.post(
        f"/staff/live/sessions/{session_no.group(1)}/revoke-card",
        data={"confirm": "yes"},
    )

    refused = student.post("/ask", json={"question": "anything"})
    assert refused.status_code == 403
    assert "stopped working" in refused.text


def test_the_live_view_stream_carries_a_new_flag_row(install, librarian):
    [token] = install.mint(1, "Journey stream")
    seen: list[dict] = []

    with librarian.stream("GET", "/staff/live/events", timeout=15) as stream:
        install.student(token).post("/ask", json={"question": "everyone picks on me"})
        event = None
        for line in stream.iter_lines():
            if line.startswith("event: "):
                event = line.removeprefix("event: ")
            elif line.startswith("data: ") and event == "flag":
                seen.append(json.loads(line.removeprefix("data: ")))
                break

    [row] = seen
    assert row["class_label"] == "Journey stream"
    assert row["severity"] == "low" and "category" not in row
