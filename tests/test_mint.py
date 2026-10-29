import csv
import io
import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from library_assistant.access import (
    connect,
    get_clock,
    get_db,
    hash_token,
)
from library_assistant.app import app
from library_assistant.config import Settings
from library_assistant.install_settings import SUPERVISION_MODE, set_setting
from library_assistant.mint import (
    mint_cards,
    qr_sheet_html,
    roster_csv,
    roster_sheet_html,
)
from library_assistant.schoolday import school_day_end_for
from library_assistant.staff import create_account
from scripts.mint_batch import main, upload_payload, write_batch_files

REGISTRATION_KEY = "s3cret-registration-key"

FIXED_CLOCK = datetime(2027, 1, 15, 14, 0, tzinfo=UTC)
DAY_END = school_day_end_for(FIXED_CLOCK, Settings())


def _expiry() -> datetime:
    return datetime.now(UTC) + timedelta(days=90)


def test_tokens_are_high_entropy_and_unique():
    result = mint_cards(200, "Period 3", _expiry())
    tokens = [card.token for card in result.cards]
    assert len(set(tokens)) == 200
    assert all(len(token) >= 20 for token in tokens)


def test_card_numbers_are_sequential_per_batch():
    result = mint_cards(3, "Period 3", _expiry())
    assert [card.card_number for card in result.cards] == ["1", "2", "3"]


def test_roster_rows_have_card_number_and_empty_students_column():
    result = mint_cards(2, "Period 3", _expiry())
    assert result.roster_rows == [
        {"card_number": "1", "students": ""},
        {"card_number": "2", "students": ""},
    ]


def test_roster_csv_allows_several_names_per_card():
    rows = [{"card_number": "1", "students": "Alice, Bob"}]
    reader = csv.DictReader(io.StringIO(roster_csv(rows)))
    assert next(reader) == {"card_number": "1", "students": "Alice, Bob"}


def test_registration_payload_has_no_roster_or_student_data():
    result = mint_cards(2, "Period 3", _expiry())
    dumped = json.dumps(result.registration_payload).lower()
    assert "student" not in dumped
    assert "roster" not in dumped
    assert set(result.registration_payload) == {"cards", "expires_at", "class_label"}


def test_registration_payload_has_only_hashes():
    """ADR-0002: only Token hashes leave the Teacher's machine, never a Token."""
    result = mint_cards(5, "Period 3", _expiry())
    dumped = json.dumps(result.registration_payload)
    for card in result.cards:
        assert card.token not in dumped
    assert result.registration_payload["cards"] == [
        {"token_hash": hash_token(card.token), "card_number": card.card_number}
        for card in result.cards
    ]


@pytest.fixture
def client():
    db = connect(":memory:")
    teacher_id = create_account(db, "registering-teacher", "correct horse", "teacher")
    db.execute(
        "INSERT INTO registration_keys (account_id, key_hash, rotated_at) "
        "VALUES (?, ?, ?)",
        (teacher_id, hash_token(REGISTRATION_KEY), FIXED_CLOCK.isoformat()),
    )
    db.commit()
    # No Watch is started in this fixture: open the gate directly (lib-793.3).
    set_setting(db, SUPERVISION_MODE, "off", teacher_id, FIXED_CLOCK)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_clock] = lambda: FIXED_CLOCK
    try:
        yield TestClient(app), db
    finally:
        app.dependency_overrides.clear()


def test_round_trip_registration_lets_each_card_start_a_session(client):
    tc, db = client
    expires_at = DAY_END
    result = mint_cards(3, "Period 3", expires_at)

    response = tc.post(
        "/batches",
        json={"registration_key": REGISTRATION_KEY, **result.registration_payload},
    )
    assert response.status_code == 201
    assert response.json() == {"registered": 3}

    stored_hashes = {row[0] for row in db.execute("SELECT token_hash FROM cards")}
    assert stored_hashes == {hash_token(card.token) for card in result.cards}

    for card in result.cards:
        sign_in = tc.post("/card", json={"token": card.token})
        assert sign_in.status_code == 200
        assert "Period 3" in sign_in.text
        assert card.card_number in sign_in.text


@pytest.mark.parametrize(
    "card",
    [
        {"token": "raw-token-1", "card_number": "1"},
        {"token": "raw-token-1", "token_hash": "0" * 64, "card_number": "1"},
        {"token_hash": "not-a-hash", "card_number": "1"},
        {"token_hash": "A" * 64, "card_number": "1"},
    ],
    ids=["raw_token", "raw_token_beside_hash", "not_hex", "uppercase"],
)
def test_batches_refuses_raw_token(client, card):
    """A Registration carrying a raw Token, or anything but a sha256 hex hash, is refused
    and nothing is stored (ADR-0002)."""
    tc, db = client
    response = tc.post(
        "/batches",
        json={
            "registration_key": REGISTRATION_KEY,
            "cards": [card],
            "expires_at": DAY_END.isoformat(),
            "class_label": "Period 3",
        },
    )
    assert response.status_code == 422
    assert db.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 0


def test_upload_payload_sends_no_roster_data(monkeypatch):
    result = mint_cards(2, "Period 3", _expiry())
    sent = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

    def fake_post(url, json):
        sent["url"] = url
        sent["json"] = json
        return FakeResponse()

    monkeypatch.setattr("httpx.post", fake_post)
    upload_payload(
        "http://intranet/batches", REGISTRATION_KEY, result.registration_payload
    )

    assert sent["url"] == "http://intranet/batches"
    assert sent["json"]["registration_key"] == REGISTRATION_KEY
    dumped = json.dumps(sent["json"]).lower()
    assert "student" not in dumped
    assert "roster" not in dumped


def test_cli_writes_html_csv_and_json(tmp_path):
    result = mint_cards(2, "Period 3", _expiry())
    paths = write_batch_files(
        tmp_path,
        "Period 3",
        result.cards,
        result.roster_rows,
        result.registration_payload,
        base_url=None,
        minted_at=datetime.now(UTC),
        expires_at=_expiry(),
    )

    html = paths["html"].read_text()
    assert "Period 3" in html
    assert "Card 1" in html
    assert "Card 2" in html
    assert "doesn't tell the assistant your name" in html

    csv_content = paths["csv"].read_text()
    assert "card_number,students" in csv_content
    assert "1," in csv_content

    payload_text = paths["json"].read_text()
    assert json.loads(payload_text) == result.registration_payload
    for card in result.cards:
        assert card.token not in payload_text


def test_qr_sheet_encodes_sign_in_url_when_base_url_given():
    result = mint_cards(1, "Period 3", _expiry())
    html = qr_sheet_html(result.cards, "Period 3", base_url="http://intranet")
    assert "<svg" in html


def _sheet(count: int = 3, class_label: str = "Period 3") -> tuple[str, list]:
    minted_at = datetime(2026, 11, 2, 8, 0, tzinfo=UTC)
    expires_at = datetime(2026, 11, 2, 15, 30, tzinfo=UTC)
    result = mint_cards(count, class_label, expires_at)
    sheet = roster_sheet_html(result.cards, class_label, minted_at, expires_at)
    return sheet, result.cards


def test_roster_sheet_lists_every_card_number_and_no_token_or_hash():
    sheet, cards = _sheet(24)
    for card in cards:
        assert f"Card {card.card_number}<" in sheet
        assert card.token not in sheet
        assert hash_token(card.token) not in sheet


def test_roster_sheet_shows_minting_and_expiry_dates():
    minted_at = datetime(2026, 11, 2, 8, 0, tzinfo=UTC)
    expires_at = datetime(2026, 11, 6, 15, 30, tzinfo=UTC)
    result = mint_cards(1, "Period 3", expires_at)
    sheet = roster_sheet_html(result.cards, "Period 3", minted_at, expires_at)
    assert "Minted 2026-11-02" in sheet
    assert "expires 2026-11-06" in sheet


def test_roster_sheet_escapes_the_class_label():
    sheet, _ = _sheet(1, class_label="<script>x</script>")
    assert "<script>x</script>" not in sheet
    assert "&lt;script&gt;" in sheet


def test_cli_writes_the_roster_sheet_wherever_it_runs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no templates/ here: the sheet must not depend on cwd
    minted_at = datetime.now(UTC)
    expires_at = minted_at + timedelta(hours=6)
    result = mint_cards(2, "Period 3", expires_at)
    paths = write_batch_files(
        tmp_path / "out",
        "Period 3",
        result.cards,
        result.roster_rows,
        result.registration_payload,
        base_url=None,
        minted_at=minted_at,
        expires_at=expires_at,
    )
    sheet = paths["roster"].read_text()
    assert "Card 1<" in sheet and "Card 2<" in sheet
    payload = json.loads(paths["json"].read_text())
    assert payload == result.registration_payload
    assert "Sealed Roster" not in json.dumps(payload)


def test_cli_default_expiry_is_today_at_1530(tmp_path, monkeypatch, capsys):
    """Test that the default --until is today at 15:30."""
    monkeypatch.setattr(
        "scripts.mint_batch._now", lambda: datetime(2026, 11, 2, 10, 0, tzinfo=UTC)
    )
    code = main(
        ["--count", "1", "--class-label", "Period 3", "--out-dir", str(tmp_path)]
    )
    assert code == 0
    captured = capsys.readouterr()
    assert "wrote json:" in captured.out
    payload = json.loads(tmp_path.joinpath("Period_3-registration.json").read_text())
    assert payload["expires_at"] == "2026-11-02T15:30:00+00:00"


def test_cli_until_in_the_past_exits_2(tmp_path, monkeypatch, capsys):
    """Test that --until in the past causes exit code 2."""
    monkeypatch.setattr(
        "scripts.mint_batch._now", lambda: datetime(2026, 11, 2, 16, 0, tzinfo=UTC)
    )
    code = main(
        [
            "--count",
            "1",
            "--class-label",
            "Period 3",
            "--until",
            "15:30",
            "--out-dir",
            str(tmp_path),
        ]
    )
    assert code == 2
    captured = capsys.readouterr()
    assert "--until is already past for today" in captured.err
