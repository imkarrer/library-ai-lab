"""The Install's one Watch (ADR-0010, lib-793.2): Start watch, heartbeat, End watch,
sign-out, staff session expiry, and the "is anyone on Watch" check.

Time comes only from the injected clock; no test sleeps, and every await on the event
stream is bounded by STREAM_TIMEOUT.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from library_assistant.access import connect, get_clock, get_db
from library_assistant.app import app
from library_assistant.install_settings import WATCH_GRACE_SECONDS, set_setting
from library_assistant.routers.live import LiveBus, get_live_bus, get_ping_wait
from library_assistant.staff import (
    STAFF_SESSION_COOKIE,
    STAFF_SESSION_LIFETIME,
    create_account,
    set_stand_in,
)
from library_assistant.watch import watch_is_on

# Far in the future, as in tests/test_live_view.py, so no staff session looks expired.
NOW = datetime(2036, 10, 27, 14, 0, tzinfo=UTC)
GRACE = 90
STREAM_TIMEOUT = 5


@pytest.fixture
def db():
    return connect(":memory:")


@pytest.fixture
def clock():
    return {"now": NOW}


@pytest.fixture
def client(db, clock):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_clock] = lambda: clock["now"]
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _sign_in(db, username, role, stand_in=False) -> TestClient:
    """A separate client per staff account, each with its own staff session cookie."""
    account_id = create_account(db, username, "correct horse", role)
    if stand_in:
        set_stand_in(db, account_id, True)
    client = TestClient(app)
    response = client.post(
        "/staff/login",
        data={"username": username, "password": "correct horse"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    client.cookies.set(STAFF_SESSION_COOKIE, response.cookies[STAFF_SESSION_COOKIE])
    return client


@pytest.fixture
def librarian(client, db):
    return _sign_in(db, "librarian-account", "librarian")


def _later(clock, seconds):
    clock["now"] = clock["now"] + timedelta(seconds=seconds)
    return clock["now"]


def test_no_watch_until_start(db, librarian):
    assert not watch_is_on(db, NOW)

    response = librarian.post("/staff/watch/start")

    assert response.status_code == 200
    assert response.json() == {"watching": True, "alarms": []}
    assert response.headers["cache-control"] == "no-store"
    assert watch_is_on(db, NOW)


def test_lapses_after_more_than_grace_without_heartbeat(db, clock, librarian):
    librarian.post("/staff/watch/start")

    assert watch_is_on(db, _later(clock, GRACE))
    assert not watch_is_on(db, _later(clock, 1))


def test_grace_comes_from_install_settings(db, clock, librarian):
    set_setting(db, WATCH_GRACE_SECONDS, 30, account_id=1, now=NOW)
    librarian.post("/staff/watch/start")

    assert watch_is_on(db, _later(clock, 30))
    assert not watch_is_on(db, _later(clock, 1))


def test_heartbeat_keeps_the_watch_on(db, clock, librarian):
    librarian.post("/staff/watch/start")

    for _ in range(10):
        _later(clock, 20)
        response = librarian.post("/staff/watch/heartbeat")
        assert response.status_code == 200
        assert response.json() == {"watching": True}

    # 200 s since Start watch, well past the grace, and still on.
    assert watch_is_on(db, _later(clock, GRACE))
    assert not watch_is_on(db, _later(clock, 1))


def test_heartbeat_after_lapse_does_not_revive(db, clock, librarian):
    librarian.post("/staff/watch/start")
    _later(clock, GRACE + 1)

    response = librarian.post("/staff/watch/heartbeat")

    assert response.status_code == 409
    assert response.json() == {"watching": False}
    assert not watch_is_on(db, clock["now"])
    # Start watch again brings it back.
    librarian.post("/staff/watch/start")
    assert watch_is_on(db, clock["now"])


def test_heartbeat_without_start_does_not_start_one(db, librarian):
    response = librarian.post("/staff/watch/heartbeat")

    assert response.status_code == 409
    assert not watch_is_on(db, NOW)


def test_end_watch_ends_it(db, librarian):
    librarian.post("/staff/watch/start")

    response = librarian.post("/staff/watch/end")

    assert response.status_code == 200
    assert response.json() == {"watching": False}
    assert not watch_is_on(db, NOW)


def test_two_watchers_one_ends_it_stays_on_until_the_second_ends(db, librarian):
    stand_in = _sign_in(db, "aide-account", "teacher", stand_in=True)
    librarian.post("/staff/watch/start")
    stand_in.post("/staff/watch/start")

    librarian.post("/staff/watch/end")
    assert watch_is_on(db, NOW)

    stand_in.post("/staff/watch/end")
    assert not watch_is_on(db, NOW)


def test_one_watcher_lapsing_leaves_the_other_on(db, clock, librarian):
    stand_in = _sign_in(db, "aide-account", "teacher", stand_in=True)
    librarian.post("/staff/watch/start")
    stand_in.post("/staff/watch/start")

    _later(clock, 60)
    stand_in.post("/staff/watch/heartbeat")
    _later(clock, 60)

    assert watch_is_on(db, clock["now"])
    assert librarian.post("/staff/watch/heartbeat").status_code == 409
    assert stand_in.post("/staff/watch/heartbeat").status_code == 200


def test_sign_out_ends_it(db, librarian):
    librarian.post("/staff/watch/start")

    librarian.post("/staff/logout", follow_redirects=False)

    assert not watch_is_on(db, NOW)


def test_sign_out_of_one_watcher_leaves_the_other_on(db, librarian):
    stand_in = _sign_in(db, "aide-account", "teacher", stand_in=True)
    librarian.post("/staff/watch/start")
    stand_in.post("/staff/watch/start")

    stand_in.post("/staff/logout", follow_redirects=False)
    assert watch_is_on(db, NOW)

    librarian.post("/staff/logout", follow_redirects=False)
    assert not watch_is_on(db, NOW)


def test_staff_session_expiry_ends_it(db, clock, librarian):
    expires = NOW + STAFF_SESSION_LIFETIME
    clock["now"] = expires - timedelta(seconds=30)
    librarian.post("/staff/watch/start")
    clock["now"] = expires - timedelta(seconds=10)
    assert librarian.post("/staff/watch/heartbeat").status_code == 200
    assert watch_is_on(db, clock["now"])

    # Inside the grace since the last heartbeat, but the staff session has expired.
    clock["now"] = expires

    assert not watch_is_on(db, clock["now"])
    assert librarian.post("/staff/watch/heartbeat").status_code == 401


@pytest.mark.parametrize("role", ["teacher", "counselor"])
def test_teacher_and_counselor_without_stand_in_cannot_start(db, client, role):
    staff = _sign_in(db, f"{role}-account", role)

    assert staff.post("/staff/watch/start").status_code == 403
    assert staff.post("/staff/watch/heartbeat").status_code == 403
    assert not watch_is_on(db, NOW)


@pytest.mark.parametrize("role", ["teacher", "counselor"])
def test_stand_in_can_start(db, client, role):
    staff = _sign_in(db, f"{role}-account", role, stand_in=True)

    assert staff.post("/staff/watch/start").status_code == 200
    assert watch_is_on(db, NOW)


def test_anonymous_cannot_start(db, client):
    assert client.post("/staff/watch/start").status_code == 401
    assert not watch_is_on(db, NOW)


def test_watch_names_no_session_or_card(db, librarian):
    librarian.post("/staff/watch/start")

    columns = [row[1] for row in db.execute("PRAGMA table_info(watchers)")]

    assert columns == ["account_id", "started_at", "last_heartbeat_at"]


# --- The Live view's event stream pings, and the page answers with a heartbeat.


class _StreamDone(Exception):
    """Ends the otherwise endless stream after its first ping."""


def test_stand_in_stream_pings_and_heartbeat_keeps_watch(db, clock, client):
    stand_in = _sign_in(db, "aide-account", "teacher", stand_in=True)
    stand_in.post("/staff/watch/start")
    waits = []

    async def wait() -> None:
        waits.append(1)
        if len(waits) > 1:
            raise _StreamDone

    app.dependency_overrides[get_ping_wait] = lambda: wait
    app.dependency_overrides[get_live_bus] = LiveBus
    stream_client = TestClient(app, raise_server_exceptions=False)
    stream_client.cookies = stand_in.cookies

    response = stream_client.get("/staff/live/events")

    assert response.status_code == 200
    assert response.text.startswith("event: ping\ndata: {}\n\n")

    # The page answers the ping: past the grace from Start watch, still on.
    _later(clock, 60)
    assert stand_in.post("/staff/watch/heartbeat").status_code == 200
    assert watch_is_on(db, _later(clock, 60))


def test_stream_pings_on_schedule_while_messages_flow():
    """A message does not restart the ping wait, so a busy class still heartbeats."""
    from library_assistant.routers.live import PING, event_stream

    bus = LiveBus()
    tick = asyncio.Event()
    waits = []

    async def wait() -> None:
        waits.append(1)
        await tick.wait()
        tick.clear()

    async def scenario():
        queue = bus.subscribe()
        stream = event_stream(bus, queue, wait)
        received = []
        for n in range(3):
            bus.publish("question", {"session_no": n})
            received.append(await asyncio.wait_for(anext(stream), STREAM_TIMEOUT))
        tick.set()
        received.append(await asyncio.wait_for(anext(stream), STREAM_TIMEOUT))
        await stream.aclose()
        return received

    received = asyncio.run(scenario())

    assert received[-1] == PING
    assert len(waits) == 1


def test_live_pages_answer_pings_with_heartbeat(db, librarian):
    response = librarian.get("/staff/live")

    assert 'addEventListener("ping"' in response.text
    assert "/staff/watch/heartbeat" in response.text
    assert "Start watch" in response.text

    librarian.post("/staff/watch/start")
    assert "End watch" in librarian.get("/staff/live").text
