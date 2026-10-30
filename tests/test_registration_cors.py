"""CORS on /batches alone, so the offline Minting page can register from file:// (ADR-0002)."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from registration_helpers import batch_cards

from library_assistant.access import connect, get_clock, get_db, issue_registration_key
from library_assistant.app import app
from library_assistant.config import Settings
from library_assistant.schoolday import school_day_end_for
from library_assistant.staff import create_account

FIXED_CLOCK = datetime(2027, 1, 15, 14, 0, tzinfo=UTC)
# A page opened from a file:// URL sends this Origin.
FILE_ORIGIN = "null"


@pytest.fixture
def client():
    db = connect(":memory:")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_clock] = lambda: FIXED_CLOCK
    account_id = create_account(db, "teacher", "correct horse", "teacher")
    key = issue_registration_key(db, account_id, FIXED_CLOCK)
    try:
        yield TestClient(app), key
    finally:
        app.dependency_overrides.clear()


def _preflight(tc: TestClient, path: str, **extra: str):
    return tc.options(
        path,
        headers={
            "Origin": FILE_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
            **extra,
        },
    )


def _register(tc: TestClient, key: str):
    return tc.post(
        "/batches",
        headers={"Origin": FILE_ORIGIN},
        json={
            "registration_key": key,
            "cards": batch_cards(("token-1", "1")),
            "expires_at": school_day_end_for(FIXED_CLOCK, Settings()).isoformat(),
            "class_label": "Period 3",
        },
    )


def test_preflight_for_batches_allows_a_json_post(client):
    tc, _key = client
    response = _preflight(tc, "/batches")
    assert response.status_code == 204
    assert response.headers["access-control-allow-origin"] == "*"
    assert response.headers["access-control-allow-methods"] == "POST"
    assert "content-type" in response.headers["access-control-allow-headers"]
    assert "access-control-allow-credentials" not in response.headers


def test_preflight_answers_chromes_private_network_question(client):
    tc, _key = client
    response = _preflight(
        tc, "/batches", **{"Access-Control-Request-Private-Network": "true"}
    )
    assert response.headers["access-control-allow-private-network"] == "true"


def test_registration_response_is_readable_cross_origin(client):
    tc, key = client
    response = _register(tc, key)
    assert response.status_code == 201
    assert response.headers["access-control-allow-origin"] == "*"


def test_refusal_is_readable_cross_origin_so_the_page_can_say_why(client):
    tc, _key = client
    response = _register(tc, "wrong-key")
    assert response.status_code == 403
    assert response.headers["access-control-allow-origin"] == "*"


@pytest.mark.parametrize("path", ["/batches/revoke-card", "/staff/login", "/health"])
def test_no_other_route_answers_cors(client, path):
    tc, _key = client
    assert "access-control-allow-origin" not in _preflight(tc, path).headers
    assert "access-control-allow-origin" not in tc.get(path).headers
