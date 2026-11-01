"""Test helper for signing in as a staff role."""

from __future__ import annotations

from fastapi.testclient import TestClient

from library_assistant.staff import (
    STAFF_SESSION_COOKIE,
    create_account,
    set_stand_in,
)


def sign_in_as(client, db, role, stand_in=False) -> TestClient:
    account_id = create_account(db, f"{role}-account", "correct horse", role)
    if stand_in:
        set_stand_in(db, account_id, True)
    response = client.post(
        "/staff/login",
        data={"username": f"{role}-account", "password": "correct horse"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    client.cookies.set(STAFF_SESSION_COOKIE, response.cookies[STAFF_SESSION_COOKIE])
    return client
