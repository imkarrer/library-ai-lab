#!/usr/bin/env python3
"""Mint a Batch of Cards for one Class and write the printable sheet, the Roster CSV, and
the Registration payload. With --url and --registration-key, also registers the Batch
through Card sign-in's endpoint.

    python3 scripts/mint_batch.py --count 24 --class-label "Period 3" --days 90 --out-dir out

Binding: ADR-0002. The Roster CSV and the QR sheet (which carries each Card's Token) stay
on this machine; only the Registration payload is ever sent anywhere.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jinja2 import Template

from library_assistant.mint import mint_cards, qr_sheet_html, roster_csv


def _slug(class_label: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", class_label).strip("_")


def write_batch_files(
    out_dir: Path,
    class_label: str,
    cards,
    roster_rows,
    registration_payload: dict[str, object],
    base_url: str | None,
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = _slug(class_label)
    paths = {
        "html": out_dir / f"{slug}-cards.html",
        "csv": out_dir / f"{slug}-roster.csv",
        "json": out_dir / f"{slug}-registration.json",
        "roster": out_dir / f"{slug}-roster-printable.html",
    }
    paths["html"].write_text(qr_sheet_html(cards, class_label, base_url=base_url))
    paths["csv"].write_text(roster_csv(roster_rows))
    paths["json"].write_text(json.dumps(registration_payload, indent=2))

    # Generate the printable roster sheet
    roster_template_path = Path("templates/roster_sheet.html")
    if roster_template_path.exists():
        with roster_template_path.open() as f:
            template = Template(f.read())
        roster_html = template.render(
            class_label=class_label,
            start_date=registration_payload["expires_at"].split("T")[0],
            end_date=registration_payload["expires_at"].split("T")[0],
            cards=cards,
        )
        paths["roster"].write_text(roster_html)

    return paths


def upload_payload(
    url: str, registration_key: str, registration_payload: dict[str, object]
) -> None:
    import httpx

    body = {"registration_key": registration_key, **registration_payload}
    response = httpx.post(url, json=body)
    response.raise_for_status()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--class-label", required=True)
    parser.add_argument(
        "--days", type=int, default=90, help="Batch expiry, days from now"
    )
    parser.add_argument("--out-dir", type=Path, default=Path("."))
    parser.add_argument("--url", help="Registration endpoint, e.g. http://host/batches")
    parser.add_argument("--registration-key")
    parser.add_argument("--print", action="store_true", help="Print the roster sheet")
    args = parser.parse_args(argv)

    expires_at = datetime.now(UTC) + timedelta(days=args.days)
    result = mint_cards(args.count, args.class_label, expires_at)
    paths = write_batch_files(
        args.out_dir,
        args.class_label,
        result.cards,
        result.roster_rows,
        result.registration_payload,
        base_url=args.url.rsplit("/batches", 1)[0] if args.url else None,
    )
    for name, path in paths.items():
        print(f"wrote {name}: {path}")

    if args.print:
        if "roster" in paths:
            print(paths["roster"].read_text())
        else:
            print("Roster template not found")

    if args.url and args.registration_key:
        upload_payload(args.url, args.registration_key, result.registration_payload)
        print(f"registered {len(result.cards)} cards at {args.url}")
    elif args.url or args.registration_key:
        parser.error("--url and --registration-key must be given together")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
