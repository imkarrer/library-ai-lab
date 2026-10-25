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
    """The Registration payload must carry Tokens and Card numbers, never Roster (student) data."""
    js = f"""
{NODE_STUB_DOCUMENT}
{app_logic_script}
(async () => {{
  const result = await generateCards(3, 'Period 3', '23:59');
  process.stdout.write(JSON.stringify(result.registrationPayload));
}})();
"""
    payload = json.loads(_run_node(js))
    assert set(payload.keys()) == {"cards", "expires_at", "class_label"}
    for card in payload["cards"]:
        assert set(card.keys()) == {"token", "card_number"}
    assert "students" not in json.dumps(payload)


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
