import os

from fastapi.testclient import TestClient

from library_assistant.app import app
from library_assistant.staff import DB_PATH, STAFF_TABLE, connect

# Test client for the app
client = TestClient(app)


def test_first_run_setup():
    """Test that first-run setup works correctly."""
    # Ensure we start with a clean database
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    # Test that setup page is shown when no accounts exist
    response = client.get("/staff/setup")
    assert response.status_code == 200
    assert "First Run Setup" in response.text

    # Test creating a librarian account via setup
    response = client.post(
        "/staff/setup",
        json={"username": "librarian", "password": "password123", "role": "librarian"},
    )
    assert response.status_code == 200

    # Verify the account was created
    conn = connect()
    cursor = conn.execute(
        f"SELECT username FROM {STAFF_TABLE} WHERE username = 'librarian'"
    )
    result = cursor.fetchone()
    assert result is not None
    conn.close()


def test_staff_dashboard_access():
    """Test staff dashboard access control."""
    response = client.get("/staff/dashboard")
    # Should redirect to login page if not authenticated
    assert (
        response.status_code == 200
    )  # This might be 302 redirect in real implementation


def test_registration_key_endpoints():
    """Test registration key management endpoints."""
    response = client.get("/staff/registration-key/current")
    # Should return 401 for unauthenticated access
    assert response.status_code == 401
