"""ADR-0003 addendum, "Other copies": the Purge is only as good as the copies it cannot see.

A canary sentence goes through sign-in, an ask (fake model), a Flag, and a Purge with every
logger at DEBUG; afterwards it is in no log line and no byte of the database, -wal, or -shm
file. The app's own access log names route templates, never a raw path or query.
"""

import logging
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from library_assistant.access import (
    NO_STORE,
    SESSION_COOKIE,
    connect,
    get_clock,
    get_db,
    hash_token,
)
from library_assistant.access_log import UNMATCHED
from library_assistant.app import app
from library_assistant.catalog import Catalog, Record
from library_assistant.config import Settings
from library_assistant.dependencies import get_catalog, get_settings
from library_assistant.flags import close_flag, raise_flag
from library_assistant.install_settings import SUPERVISION_MODE, set_setting
from library_assistant.purge import purge
from library_assistant.staff import create_account

REPO = Path(__file__).resolve().parent.parent
REGISTRATION_KEY = "s3cret-registration-key"
TOKEN = "token-canary-card-14"
CARD_NUMBER = "14"
# Far in the future: the sign-in cookie expires with the Card, compared with the real clock.
NOW = datetime(2036, 11, 3, 9, 0, tzinfo=UTC)
EXPIRES = NOW + timedelta(hours=6)
CANARY = "heliotrope canary sentence 7f3a9c"
ANSWER_CANARY = "marigold canary answer 2b8e"

RECORD = Record(
    id="00057791",
    title="The story of Ferdinand /",
    author="Leaf, Munro,",
    subjects="Bulls -- Fiction",
    summary="A bull who would rather smell flowers than fight.",
    call_number="PZ10.3.L47 St",
)


class FakeCatalog(Catalog):
    def search(self, query: str, k: int) -> list[Record]:
        return [RECORD]

    def get(self, id: str) -> Record | None:
        return RECORD if id == RECORD.id else None


@pytest.fixture
def fake_model(monkeypatch):
    """Answers every model call with the answer canary, at the httpx transport level."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = (
            b'data: {"choices":[{"delta":{"content":"'
            + ANSWER_CANARY.encode()
            + b'"}}]}\n\n'
            b"data: [DONE]\n\n"
        )
        return httpx.Response(
            200, content=body, headers={"content-type": "text/event-stream"}
        )

    monkeypatch.setattr(
        httpx.AsyncHTTPTransport, "handle_async_request", handle_async_request
    )


@pytest.fixture
def every_logger_at_debug():
    """Every logger that exists, and the root, at DEBUG; restored afterwards."""
    loggers = [logging.getLogger()] + [
        logger
        for logger in logging.root.manager.loggerDict.values()
        if isinstance(logger, logging.Logger)
    ]
    levels = [logger.level for logger in loggers]
    for logger in loggers:
        logger.setLevel(logging.DEBUG)
    yield
    for logger, level in zip(loggers, levels, strict=True):
        logger.setLevel(level)


@pytest.fixture
def app_db(request, tmp_path):
    """The app on a real database file, in the given journal mode."""
    db_path = tmp_path / "assistant.db"
    db = connect(str(db_path))
    db.execute(f"PRAGMA journal_mode = {request.param}")
    teacher_id = create_account(db, "registering-teacher", "correct horse", "teacher")
    db.execute(
        "INSERT INTO registration_keys (account_id, key_hash, rotated_at) "
        "VALUES (?, ?, ?)",
        (teacher_id, hash_token(REGISTRATION_KEY), NOW.isoformat()),
    )
    db.commit()
    # No Watch is started in this fixture: open the gate directly (lib-793.3).
    set_setting(db, SUPERVISION_MODE, "off", teacher_id, NOW)
    clock = {"now": NOW}
    settings = Settings(
        openai_endpoint="http://model.example.com:8080", openai_model="llama3"
    )
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_catalog] = lambda: FakeCatalog()
    app.dependency_overrides[get_clock] = lambda: clock["now"]
    try:
        yield db, db_path, settings
    finally:
        app.dependency_overrides.clear()
        db.close()


@pytest.fixture
def access_client():
    db = connect(":memory:")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_clock] = lambda: NOW
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _access_lines(caplog) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == "library_assistant.access"
    ]


@pytest.mark.parametrize("app_db", ["delete", "wal"], indirect=True)
def test_canary_leaves_no_log_line_and_no_byte_after_the_purge(
    app_db, fake_model, every_logger_at_debug, caplog
):
    db, db_path, settings = app_db
    caplog.set_level(logging.DEBUG)
    client = TestClient(app)

    # Sign-in
    registered = client.post(
        "/batches",
        json={
            "registration_key": REGISTRATION_KEY,
            "cards": [{"token": TOKEN, "card_number": CARD_NUMBER}],
            "expires_at": EXPIRES.isoformat(),
            "class_label": "Period 3",
        },
    )
    assert registered.status_code == 201
    signed_in = client.post("/card", json={"token": TOKEN})
    assert signed_in.status_code == 200
    session_id = signed_in.cookies[SESSION_COOKIE]
    assert signed_in.headers["cache-control"] == "no-store"

    # Ask, with the fake model
    answer = client.post("/ask", json={"question": CANARY})
    assert answer.status_code == 200
    assert ANSWER_CANARY in answer.text
    (transcript_id,) = db.execute("SELECT id FROM transcripts").fetchone()

    # Flag, then close it so the Purge may delete the exchange
    message_hash = hash_token(CANARY)
    flag_id = raise_flag(
        db,
        transcript_id=transcript_id,
        class_label="Period 3",
        card_number=CARD_NUMBER,
        batch_expires_at=EXPIRES.isoformat(),
        message_hash=message_hash,
        category="self-harm",
        severity="high",
        source="watchlist",
        raised_at=NOW.isoformat(),
        entry_id="entry-1",
        watchlist_version="v1",
        reason="watchlist match",
    )
    close_flag(
        db,
        flag_id,
        closed_at=(NOW + timedelta(hours=1)).isoformat(),
        account="librarian",
        outcome=_an_outcome(),
        reason="handled with the student's teacher",
    )

    # Purge, two days on
    report = purge(db, NOW + timedelta(days=2), settings)
    assert report.deleted == 1
    assert db.execute("SELECT COUNT(*) FROM transcripts").fetchone()[0] == 0

    # No log line carries the canary, the Token, a hash, or the Session id.
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert _access_lines(caplog), "the access log should have recorded the requests"
    for secret in (
        CANARY,
        ANSWER_CANARY,
        TOKEN,
        hash_token(TOKEN),
        message_hash,
        session_id,
        hash_token(session_id),
    ):
        assert secret not in logged

    # No byte of the database, -wal, or -shm file holds the canary, with the
    # connection still open (closing it would checkpoint and hide a leftover -wal).
    wal = Path(f"{db_path}-wal")
    assert not wal.exists() or wal.stat().st_size == 0
    for path in (db_path, wal, Path(f"{db_path}-shm")):
        if path.exists():
            content = path.read_bytes()
            for canary in (CANARY, ANSWER_CANARY):
                assert canary.encode() not in content, f"{canary!r} found in {path}"


def _an_outcome() -> str:
    from library_assistant.flags import OUTCOMES

    return next(iter(OUTCOMES))


def test_access_log_records_route_template_status_and_duration(access_client, caplog):
    caplog.set_level(logging.INFO, logger="library_assistant.access")

    response = access_client.get("/cards/a-raw-token-value?card=99")

    assert response.status_code == 403
    (line,) = _access_lines(caplog)
    method, template, status, duration = line.split(" ")
    assert (method, template, status) == ("GET", "/cards/{token}", "403")
    assert duration.endswith("ms") and float(duration.removesuffix("ms")) >= 0
    assert "a-raw-token-value" not in line
    assert "card=99" not in line


def test_access_log_never_writes_the_query(access_client, caplog):
    caplog.set_level(logging.INFO, logger="library_assistant.access")

    access_client.get("/card?token=a-raw-token-value")

    (line,) = _access_lines(caplog)
    assert line.split(" ")[:3] == ["GET", "/card", "403"]
    assert "a-raw-token-value" not in line


def test_access_log_names_no_raw_path_for_an_unmatched_request(access_client, caplog):
    caplog.set_level(logging.INFO, logger="library_assistant.access")

    access_client.get("/no-such-page/14")

    (line,) = _access_lines(caplog)
    assert line.split(" ")[:3] == ["GET", UNMATCHED, "404"]
    assert "14" not in line.split(" ")[1]


def test_uvicorn_access_log_off_in_the_shipped_start_command():
    manifest = tomllib.loads((REPO / ".flox/env/manifest.toml").read_text())
    command = manifest["services"]["assistant"]["command"]
    start = next(
        line for line in command.splitlines() if "library_assistant.app:app" in line
    )
    assert "uvicorn" in start
    assert "--no-access-log" in start


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/card", None),
        ("GET", "/card?token=x", None),
        ("GET", "/cards/x", None),
        ("POST", "/card", {"token": "unknown"}),
        ("POST", "/card/finish", None),
        ("GET", "/chat", None),
        ("POST", "/ask", {"question": "bulls?"}),
    ],
)
def test_every_student_page_sends_no_store(access_client, method, path, body):
    response = access_client.request(method, path, json=body)
    assert response.headers["cache-control"] == NO_STORE["Cache-Control"]
