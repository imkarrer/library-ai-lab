"""Minting: a pure function that turns a count, a Class label, and an expiry into Cards, a
Roster template, and a Registration payload.

Binding: ADR-0002. The Teacher's machine keeps the Cards' Tokens and the Roster; only the
Registration payload reaches the assistant, and it carries only Token hashes (never a
Token) and no Student data.
"""

from __future__ import annotations

import csv
import html
import io
import secrets
from dataclasses import dataclass
from datetime import datetime

from library_assistant.access import hash_token

PRIVACY_NOTE = (
    "This card doesn't tell the assistant your name. Adults can see what you ask."
)

ROSTER_FIELDNAMES = ["card_number", "students"]


@dataclass(frozen=True)
class Card:
    token: str
    card_number: str


@dataclass(frozen=True)
class MintResult:
    cards: list[Card]
    roster_rows: list[dict[str, str]]
    registration_payload: dict[str, object]


def _make_token() -> str:
    return secrets.token_urlsafe(24)


def mint_cards(count: int, class_label: str, expires_at: datetime) -> MintResult:
    """Mint `count` Cards for one Batch.

    Tokens are drawn from `secrets`, high-entropy and checked unique within the Batch.
    """
    if count < 1:
        raise ValueError("count must be at least 1")

    tokens: set[str] = set()
    cards: list[Card] = []
    while len(cards) < count:
        token = _make_token()
        if token in tokens:
            continue
        tokens.add(token)
        cards.append(Card(token=token, card_number=str(len(cards) + 1)))

    roster_rows = [{"card_number": card.card_number, "students": ""} for card in cards]

    registration_payload = {
        "cards": [
            {"token_hash": hash_token(card.token), "card_number": card.card_number}
            for card in cards
        ],
        "expires_at": expires_at.isoformat(),
        "class_label": class_label,
    }

    return MintResult(
        cards=cards,
        roster_rows=roster_rows,
        registration_payload=registration_payload,
    )


def roster_csv(roster_rows: list[dict[str, str]]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=ROSTER_FIELDNAMES)
    writer.writeheader()
    writer.writerows(roster_rows)
    return buf.getvalue()


def qr_sheet_html(
    cards: list[Card], class_label: str, base_url: str | None = None
) -> str:
    """A printable HTML sheet, one Card per cell, each showing its Card number and a QR
    code that carries the Token (as a sign-in URL if `base_url` is given, else the Token
    alone).
    """
    import qrcode
    import qrcode.image.svg

    def qr_svg(payload: str) -> str:
        img = qrcode.make(payload, image_factory=qrcode.image.svg.SvgImage)
        buf = io.BytesIO()
        img.save(buf)
        return buf.getvalue().decode("utf-8")

    cells = []
    for card in cards:
        sign_in_value = (
            f"{base_url.rstrip('/')}/card#t={card.token}" if base_url else card.token
        )
        cells.append(
            f"""
            <div class="card">
              <div class="card-number">Card {card.card_number}</div>
              <div class="qr">{qr_svg(sign_in_value)}</div>
              <div class="privacy-note">{PRIVACY_NOTE}</div>
            </div>
            """
        )

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{class_label} - Cards</title>
<style>
  body {{ font-family: sans-serif; }}
  .sheet {{ display: flex; flex-wrap: wrap; gap: 0.5in; }}
  .card {{ width: 2in; text-align: center; border: 1px solid #ccc; padding: 0.25in; }}
  .card-number {{ font-weight: bold; margin-bottom: 0.1in; }}
  .privacy-note {{ font-size: 0.7em; margin-top: 0.1in; }}
</style>
</head>
<body>
  <h1>{class_label}</h1>
  <div class="sheet">
    {"".join(cells)}
  </div>
</body>
</html>
"""


def roster_sheet_html(
    cards: list[Card], class_label: str, minted_at: datetime, expires_at: datetime
) -> str:
    """The sealed Roster sheet (ADR-0002): one blank name line per Card number, to be
    filled in by hand, sealed, and kept in the office. It carries no Token, so it cannot
    sign anyone in, and it never reaches the assistant.
    """
    label = html.escape(class_label)
    minted = minted_at.date().isoformat()
    expires = expires_at.date().isoformat()
    rows = "".join(
        f"""
    <div class="card-row">
      <span class="card-number">Card {html.escape(card.card_number)}</span>
      <span class="name-line"></span>
    </div>"""
        for card in cards
    )
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{label} - Sealed Roster</title>
<style>
  body {{ font-family: sans-serif; }}
  .header {{ text-align: center; margin-bottom: 1em; }}
  .class-label {{ font-size: 1.5em; font-weight: bold; }}
  .card-row {{ margin: 0.6em 0; }}
  .card-number {{ font-weight: bold; display: inline-block; width: 5em; }}
  .name-line {{ border-bottom: 1px solid #000; width: 18em; display: inline-block; }}
  .box {{ margin-top: 1.5em; padding: 0.8em; border: 1px solid #999; }}
  .log td {{ border-bottom: 1px solid #000; height: 1.6em; }}
</style>
</head>
<body>
  <div class="header">
    <div class="class-label">{label}</div>
    <div>Minted {minted} &middot; expires {expires}</div>
  </div>
  <div class="roster">{rows}
  </div>
  <div class="box">
    <strong>Sealed Roster.</strong> Write the Student's name beside each Card number you
    hand out, then seal this sheet in an envelope marked with the Class label and dates and
    give it to the office. The office opens it only to identify which Student held a Card
    number when an adult needs to know, records each opening below, and reseals it. Shred
    it when the Batch expires, unless a Hold or an open Flag still needs it.
  </div>
  <table class="log box" width="100%">
    <tr><th align="left">Opened by</th><th align="left">When</th><th align="left">Why</th></tr>
    <tr><td></td><td></td><td></td></tr>
    <tr><td></td><td></td><td></td></tr>
    <tr><td></td><td></td><td></td></tr>
  </table>
</body>
</html>
"""
