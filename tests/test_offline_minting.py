"""Offline Minting page: a headless check (Node, not a browser) that runs the page's own
<script> blocks verbatim and compares their output to the server's hash_token().

Binding: ADR-0002. The Registration upload must carry no Roster data.
"""

import json
import re
import subprocess
from pathlib import Path

import pytest

from library_assistant.access import hash_token

PAGE_PATH = Path(__file__).resolve().parent.parent / "offline-minting.html"

NODE_STUB_DOCUMENT = """
global.crypto = require('node:crypto').webcrypto;
global.document = {
  addEventListener: function () {},
  getElementById: function () {
    return { addEventListener: function () {}, classList: { add: function () {}, remove: function () {} } };
  },
  createElement: function () { return { classList: { add: function () {} }, style: {} }; },
  createElementNS: function () { return {}; },
  body: { appendChild: function () {}, removeChild: function () {} },
};
"""


def _extract_script(html: str, script_id: str) -> str:
    match = re.search(rf'<script id="{script_id}">(.*?)</script>', html, re.DOTALL)
    assert match, f'<script id="{script_id}"> not found in offline-minting.html'
    return match.group(1)


def _run_node(js: str) -> str:
    result = subprocess.run(
        ["node", "-e", js], check=False, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.fixture(scope="module")
def page_html() -> str:
    return PAGE_PATH.read_text()


@pytest.fixture(scope="module")
def qrcode_lib_script(page_html: str) -> str:
    return _extract_script(page_html, "qrcode-lib")


@pytest.fixture(scope="module")
def app_logic_script(page_html: str) -> str:
    return _extract_script(page_html, "app-logic")


def test_offline_minting_page_exists(page_html: str) -> None:
    assert "Offline Minting Page" in page_html
    assert "generateToken" in page_html
    assert "sha256" in page_html
    assert "Download Roster CSV" in page_html
    assert "Registration" in page_html


def test_offline_minting_vendors_qrcode_library(page_html: str) -> None:
    """The MIT-licensed qrcode-generator library is vendored inline, licence notice intact."""
    assert "Copyright (c) 2009 Kazuhiko Arase" in page_html
    assert "Licensed under the MIT license" in page_html
    # The actual library code, not just a notice: its constructor and SVG renderer.
    assert "createSvgTag" in page_html
    assert "getModuleCount" in page_html


def test_offline_minting_hash_matches_cli(app_logic_script: str) -> None:
    """The page's sha256() must produce the same hex digest as the server's hash_token()."""
    token = "test-token-12345"
    js = f"""
{NODE_STUB_DOCUMENT}
{app_logic_script}
(async () => {{
  const h = await sha256({json.dumps(token)});
  process.stdout.write(h);
}})();
"""
    page_hash = _run_node(js).strip()
    assert page_hash == hash_token(token)


def test_offline_minting_hash_matches_cli_for_generated_token(
    app_logic_script: str,
) -> None:
    """generateToken() output, hashed by the page, must also match the server's hash_token()."""
    js = f"""
{NODE_STUB_DOCUMENT}
{app_logic_script}
(async () => {{
  const token = await generateToken();
  const h = await sha256(token);
  process.stdout.write(JSON.stringify({{token, hash: h}}));
}})();
"""
    payload = json.loads(_run_node(js))
    assert payload["hash"] == hash_token(payload["token"])


def test_offline_minting_qr_code_encodes_the_token(
    qrcode_lib_script: str, app_logic_script: str
) -> None:
    """generateQRCodeSVG() renders a real QR code (from the vendored library), not a stub."""
    js = f"""
{NODE_STUB_DOCUMENT}
{qrcode_lib_script}
{app_logic_script}
const svg = generateQRCodeSVG('a-token');
process.stdout.write(svg);
"""
    svg = _run_node(js)
    assert svg.startswith("<svg")
    assert "path" in svg


def test_offline_minting_upload_carries_no_roster_data(app_logic_script: str) -> None:
    """The Registration payload carries Token hashes and Card numbers, never a Token or
    Roster (student) data (ADR-0002)."""
    js = f"""
{NODE_STUB_DOCUMENT}
{app_logic_script}
(async () => {{
  const result = await generateCards(3, 'Period 3', '23:59');
  process.stdout.write(JSON.stringify({{
    payload: result.registrationPayload,
    tokens: result.cards.map(c => c.token),
  }}));
}})();
"""
    out = json.loads(_run_node(js))
    payload = out["payload"]
    assert set(payload.keys()) == {"cards", "expires_at", "class_label"}
    for card, token in zip(payload["cards"], out["tokens"], strict=True):
        assert set(card.keys()) == {"token_hash", "card_number"}
        assert card["token_hash"] == hash_token(token)
    dumped = json.dumps(payload)
    assert "students" not in dumped
    assert not any(token in dumped for token in out["tokens"])


def test_offline_minting_sealed_roster_sheet_has_no_token_or_hash(
    app_logic_script: str,
) -> None:
    """The sealed Roster sheet lists Card numbers only, never a Token or its hash."""
    js = f"""
{NODE_STUB_DOCUMENT}
{app_logic_script}
(async () => {{
  const result = await generateCards(4, 'Period 3', '23:59');
  const cardNumbers = result.cards.map(c => c.cardNumber);
  const sheet = generateSealedRosterSheet(
    cardNumbers, 'Period 3', dateStamp(result.startDate), dateStamp(result.expiresAt)
  );
  process.stdout.write(JSON.stringify({{sheet, tokens: result.cards.map(c => c.token), hashes: result.cards.map(c => c.tokenHash)}}));
}})();
"""
    payload = json.loads(_run_node(js))
    sheet = payload["sheet"]
    assert "shred" in sheet.lower()
    assert "fold and seal" in sheet.lower()
    assert "opening log" in sheet.lower()
    for token in payload["tokens"]:
        assert token not in sheet
    for digest in payload["hashes"]:
        assert digest not in sheet


def test_offline_minting_only_one_network_call(page_html: str) -> None:
    """Only the Registration upload (fetch) ever leaves the machine; no other script src/href."""
    assert page_html.count("fetch(") == 1
    assert "<script src=" not in page_html
    assert '<link rel="stylesheet" href="http' not in page_html


def test_page_has_until_time_input_default_1530(page_html: str) -> None:
    """ADR-0010 rule 1: a Card lasts at most one school day, so Expiry is a time today."""
    assert 'id="until"' in page_html
    assert 'type="time" id="until"' in page_html
    assert 'value="15:30"' in page_html
    assert "Cards stop working at (today)" in page_html


def test_page_has_no_days_input(page_html: str) -> None:
    """The old "Expiry (days from now)" number input is gone, not left alongside `until`."""
    assert 'id="days"' not in page_html
    assert "Expiry (days from now)" not in page_html


def test_generate_uses_until_not_days(app_logic_script: str) -> None:
    """generateCards computes expiresAt from today's date and the until time, and mints
    nothing when that time has already passed."""
    js = f"""
{NODE_STUB_DOCUMENT}
{app_logic_script}
(async () => {{
  const future = await generateCards(2, 'Period 3', '23:59');
  const past = await generateCards(2, 'Period 3', '00:00');
  const now = new Date();
  process.stdout.write(JSON.stringify({{
    futureCardCount: future.cards ? future.cards.length : null,
    futureExpiresSameDay: future.expiresAt
      ? new Date(future.expiresAt).toDateString() === now.toDateString()
      : null,
    pastHasError: Boolean(past.error),
    pastHasCards: Boolean(past.cards),
  }}));
}})();
"""
    payload = json.loads(_run_node(js))
    assert payload["futureCardCount"] == 2
    assert payload["futureExpiresSameDay"] is True
    assert payload["pastHasError"] is True
    assert payload["pastHasCards"] is False


def test_qr_codes_carry_the_sign_in_url_not_a_bare_token(
    qrcode_lib_script: str, app_logic_script: str
) -> None:
    """A phone's camera must open the chat: each QR code carries <address>/card#t=<Token>."""
    js = f"""
{NODE_STUB_DOCUMENT}
{qrcode_lib_script}
{app_logic_script}
const encoded = [];
generateQRCodeSVG = (data) => {{ encoded.push(data); return '<svg></svg>'; }};
(async () => {{
  const result = await generateCards(2, 'Period 3', '23:59');
  generateQRSheet(result.cards, 'Period 3', normaliseBase('192.0.2.10:8000/'));
  process.stdout.write(JSON.stringify({{encoded, tokens: result.cards.map(c => c.token)}}));
}})();
"""
    out = json.loads(_run_node(js))
    assert out["encoded"] == [
        f"http://192.0.2.10:8000/card#t={token}" for token in out["tokens"]
    ]


def test_normalise_base_adds_a_scheme_and_drops_trailing_slashes(
    app_logic_script: str,
) -> None:
    js = f"""
{NODE_STUB_DOCUMENT}
{app_logic_script}
process.stdout.write(JSON.stringify([
  normaliseBase(' library.school.example:8000 '),
  normaliseBase('https://library.school.example//'),
  normaliseBase('HTTP://192.0.2.10:8000'),
]));
"""
    assert json.loads(_run_node(js)) == [
        "http://library.school.example:8000",
        "https://library.school.example",
        "HTTP://192.0.2.10:8000",
    ]


def _submit(app_logic_script: str, fake_fetch: str) -> dict:
    js = f"""
{NODE_STUB_DOCUMENT}
{app_logic_script}
const calls = [];
global.fetch = {fake_fetch};
(async () => {{
  const result = await generateCards(2, 'Period 3', '23:59');
  const outcome = await submitRegistration(
    'http://192.0.2.10:8000', 'the-key', result.registrationPayload
  );
  process.stdout.write(JSON.stringify({{
    outcome, calls, tokens: result.cards.map(c => c.token)
  }}));
}})();
"""
    return json.loads(_run_node(js))


def test_registration_posts_hashes_to_the_assistants_batches_route(
    app_logic_script: str,
) -> None:
    out = _submit(
        app_logic_script,
        "async (url, init) => { calls.push({url, body: init.body}); "
        "return {ok: true, status: 201}; }",
    )
    assert out["outcome"] == {"ok": True}
    [call] = out["calls"]
    assert call["url"] == "http://192.0.2.10:8000/batches"
    body = json.loads(call["body"])
    assert body["registration_key"] == "the-key"
    assert not any(token in call["body"] for token in out["tokens"])


def test_registration_refusal_tells_the_teacher_why(app_logic_script: str) -> None:
    detail = "A Batch must expire by the end of today's school day."
    out = _submit(
        app_logic_script,
        "async () => ({ok: false, status: 422, "
        f"json: async () => ({{detail: {json.dumps(detail)}}})}})",
    )
    assert out["outcome"] == {"error": detail}


def test_wrong_registration_key_is_named(app_logic_script: str) -> None:
    out = _submit(
        app_logic_script,
        "async () => ({ok: false, status: 403, json: async () => ({detail: 'x'})})",
    )
    assert "Registration key" in out["outcome"]["error"]


def test_unreachable_assistant_names_the_address(app_logic_script: str) -> None:
    out = _submit(app_logic_script, "async () => { throw new TypeError('Failed'); }")
    assert "http://192.0.2.10:8000" in out["outcome"]["error"]


def test_roster_csv_lists_every_card_number(app_logic_script: str) -> None:
    js = f"""
{NODE_STUB_DOCUMENT}
{app_logic_script}
(async () => {{
  const result = await generateCards(3, 'Period 3', '23:59');
  process.stdout.write(generateCSV(result.rosterRows));
}})();
"""
    assert _run_node(js).splitlines() == ["card_number,students", "1,", "2,", "3,"]


def test_cards_download_is_a_whole_page_with_the_sheet(app_logic_script: str) -> None:
    js = f"""
{NODE_STUB_DOCUMENT}
{app_logic_script}
process.stdout.write(cardsDocument('Period <3>', '<div class="qr-sheet">SHEET</div>'));
"""
    page = _run_node(js)
    assert page.startswith("<!DOCTYPE html>")
    assert "SHEET" in page
    assert "<title>Period &lt;3&gt; - Cards</title>" in page


def test_one_form_asks_for_the_address_and_key_before_making_cards(
    page_html: str,
) -> None:
    """Cards are registered before they are shown, so the form asks for both up front."""
    step1 = page_html[page_html.index('id="step1"') : page_html.index('id="step2"')]
    assert 'id="assistant-url"' in step1
    assert 'id="registration-key"' in step1
    assert 'id="step3"' not in page_html
    assert "Download Cards" in page_html
