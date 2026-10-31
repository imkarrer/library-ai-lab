"""Staff download the lessons' slides and handouts from /staff/lessons."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from library_assistant.access import connect, get_db
from library_assistant.app import app
from library_assistant.routers import lessons
from library_assistant.staff import create_account


@pytest.fixture
def db():
    return connect(":memory:")


@pytest.fixture
def client(db, tmp_path, monkeypatch):
    monkeypatch.setattr(lessons, "MATERIALS_DIR", tmp_path)
    (tmp_path / "lesson-1-deck.pdf").write_bytes(b"%PDF")
    (tmp_path / "lesson-1-deck.html").write_text("<script>slides()</script>")
    (tmp_path / "secret.txt").write_text("not a lesson")
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _sign_in(client, db, role="teacher"):
    create_account(db, "someone", "correct horse", role)
    client.post(
        "/staff/login",
        data={"username": "someone", "password": "correct horse"},
    )


@pytest.mark.parametrize("role", ["teacher", "librarian", "counselor"])
def test_any_staff_member_sees_every_lesson(client, db, role):
    _sign_in(client, db, role)
    text = client.get(lessons.LESSONS_PATH).text
    for title in lessons.LESSON_TITLES:
        assert title.replace("'", "&#x27;") in text
    assert 'href="/staff/lessons/lesson-1-deck.pdf"' in text


def test_a_file_that_isnt_built_is_not_a_broken_link(client, db):
    _sign_in(client, db)
    text = client.get(lessons.LESSONS_PATH).text
    assert "lesson-2-deck.pdf" not in text and "Not built yet" in text
    assert client.get("/staff/lessons/lesson-2-deck.pdf").status_code == 404


def test_lessons_are_on_the_staff_home(client, db):
    _sign_in(client, db)
    assert f'href="{lessons.LESSONS_PATH}"' in client.get("/staff").text


def test_a_file_downloads_rather_than_opening_on_the_assistants_address(client, db):
    _sign_in(client, db)
    response = client.get("/staff/lessons/lesson-1-deck.html")
    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith("attachment")


def test_only_lesson_files_are_served(client, db):
    _sign_in(client, db)
    for name in ("secret.txt", "..%2Fsecret.txt", "sources.json"):
        assert client.get(f"/staff/lessons/{name}").status_code == 404


def test_lessons_need_a_staff_sign_in(client):
    for path in (lessons.LESSONS_PATH, "/staff/lessons/lesson-1-deck.pdf"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code in (302, 303, 401, 403)


def test_the_titles_match_the_unit():
    unit = Path(__file__).parent.parent / "docs/curriculum/ai-literacy-unit.md"
    text = unit.read_text()
    for number, title in enumerate(lessons.LESSON_TITLES, start=1):
        assert f"## Lesson {number}: {title}" in text
