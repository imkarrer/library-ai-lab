"""The IT kit: what district IT needs to switch Chromebooks to HTTPS, filled in for this
Install (docs/templates/it-https-rollout.md).

- `/library-assistant-ca.crt`: the Install's CA certificate, for IT to upload to Google
  Admin. Public: a certificate is meant to be shared, and its key never leaves the Mac.
- `/it-check`: open it on a Chromebook; it says whether that device trusts this Install.
- `/staff/it-kit` (Librarian): the rollout steps with this Mac's address, the certificate's
  fingerprint and expiry, and both links, printable, so the Librarian can hand it over or
  read it out on a call.
"""

from __future__ import annotations

import html
import os
import sqlite3
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from library_assistant.access import get_clock, get_db
from library_assistant.staff import LibrarianDep, page
from library_assistant.theme import THEME_LINK
from library_assistant.tls import CA_CERT, TLS_NAMES_ENV, ca_cert_path, describe

router = APIRouter()

CA_PATH = f"/{CA_CERT}"
CHECK_PATH = "/it-check"


def _https_address() -> str | None:
    names = [n.strip() for n in os.environ.get(TLS_NAMES_ENV, "").split(",") if n]
    if ca_cert_path() is None or not names:
        return None
    port = os.environ.get("LIBRARY_ASSISTANT_PORT", "8000")
    host = f"[{names[0]}]" if ":" in names[0] else names[0]
    return f"https://{host}:{port}"


@router.get(CA_PATH)
def ca_certificate() -> FileResponse:
    path = ca_cert_path()
    if path is None:
        raise HTTPException(status_code=404, detail="HTTPS is off on this Install")
    return FileResponse(
        path,
        media_type="application/x-x509-ca-cert",
        filename=CA_CERT,
        headers={"Cache-Control": "no-cache"},
    )


CHECK_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Library Assistant: certificate check</title>{theme}</head>
<body><main class="page"><section class="card-panel it-check">{body}</section></main>
</body></html>"""


@router.get(CHECK_PATH)
def it_check(request: Request) -> HTMLResponse:
    """For IT, on a Chromebook: does this device trust the Install? No sign-in needed."""
    path = ca_cert_path()
    if path is None:
        body = (
            "<h1>HTTPS is off</h1><p>This Library Assistant serves plain HTTP, so there "
            "is no certificate to check.</p>"
        )
    elif request.url.scheme != "https":
        body = (
            "<h1>Open this page over HTTPS</h1><p>This is the plain-HTTP address. Open "
            f"<strong>{html.escape(_https_address() or '')}{CHECK_PATH}</strong> "
            "instead.</p>"
        )
    else:
        info = describe(path)
        body = (
            "<h1>This device trusts the Library Assistant</h1>"
            "<p>If you reached this page <strong>without clicking past a warning</strong>, "
            "and the address bar shows no &ldquo;Not secure&rdquo; label, the certificate "
            "is installed correctly on this device.</p>"
            "<p>If you did see a warning, the certificate is not installed on this device "
            "yet: check it is in the device's organizational unit, then reload policies "
            "(<code>chrome://policy</code>, <em>Reload policies</em>).</p>"
            "<table><tbody>"
            f"<tr><th>Certificate authority</th><td>{html.escape(info['subject'])}</td></tr>"
            f"<tr><th>SHA-256 fingerprint</th><td><code>{info['sha256']}</code></td></tr>"
            "</tbody></table>"
        )
    return HTMLResponse(
        CHECK_HTML.format(theme=THEME_LINK, body=body),
        headers={"Cache-Control": "no-store"},
    )


def _kit_body() -> str:
    path = ca_cert_path()
    if path is None:
        return (
            "<h1>IT kit: HTTPS</h1>"
            '<p class="lede">HTTPS is off. It is optional hardening: students\' '
            "questions travel encrypted between their Chromebooks and this computer.</p>"
            '<div class="help"><p>Turning it on needs district IT once, to push one '
            "certificate to the Chromebooks through Google Admin (about 15 minutes for "
            "them). Ask whoever set up this Library Assistant to turn HTTPS on; this page "
            "then fills in everything IT needs.</p></div>"
        )
    info = describe(path)
    address = _https_address() or ""
    previous = path.with_name(f"previous-{CA_CERT}")
    replaced = (
        '<div class="banner"><p><strong>This computer\'s address changed, so its '
        "certificate is new.</strong> IT must upload the new certificate below and "
        f"delete the old one ({html.escape(describe(previous)['subject'])}, fingerprint "
        f"<code>{describe(previous)['sha256']}</code>) from Google Admin.</p></div>"
        if previous.exists()
        else ""
    )
    return f"""<h1>IT kit: HTTPS</h1>
<p class="lede">Everything district IT needs to make Chromebooks trust this Library
Assistant. Print this page, or read it out on a call. About 15 minutes of IT's time, once.</p>
{replaced}
<section class="card-panel">
<h2>This Library Assistant</h2>
<table><tbody>
<tr><th>Address</th><td><code>{html.escape(address)}</code></td></tr>
<tr><th>Certificate</th><td><a href="{CA_PATH}" download>{CA_CERT}</a>
(<code>{html.escape(address)}{CA_PATH}</code>)</td></tr>
<tr><th>Certificate authority</th><td>{html.escape(info["subject"])}</td></tr>
<tr><th>SHA-256 fingerprint</th><td><code>{info["sha256"]}</code></td></tr>
<tr><th>Valid until</th><td>{info["not_after"]}</td></tr>
<tr><th>Check page</th><td><code>{html.escape(address)}{CHECK_PATH}</code></td></tr>
</tbody></table>
<p>Trusting this certificate lets nobody impersonate another site. Its own key was
destroyed the moment it was made, after signing one intermediate certificate whose Name
Constraints permit this computer's address and nothing else. Only that intermediate's key
is kept, on this computer, to renew the server certificate each year.</p>
</section>
<section class="card-panel">
<h2>For IT: Chromebooks, in Google Admin</h2>
<ol>
<li>Download the certificate above (or from the address in the table).</li>
<li>Check its SHA-256 fingerprint matches the one above, read out by the librarian.</li>
<li>In the Google Admin console, open <strong>Devices &rarr; Networks &rarr;
Certificates</strong>.</li>
<li>On the left, pick the organizational unit with the library's student Chromebooks (and
staff Chromebooks, if staff use them).</li>
<li><strong>Add certificate</strong>: name it <em>Library Assistant</em>, upload
<code>{CA_CERT}</code>, and under <em>Certificate authority</em> tick
<strong>Chromebook</strong>. Save.</li>
<li>On one Chromebook in that unit, open <code>chrome://policy</code> and press
<strong>Reload policies</strong>, then open the check page above. It should load with no
warning.</li>
</ol>
<p>Other Chromebooks pick it up on their own, usually within the hour. Nothing else changes
on the network.</p>
</section>
<section class="card-panel">
<h2>For IT: staff computers (the ones Teachers make Cards on, and the Live view's)</h2>
<ul>
<li><strong>Mac, managed:</strong> a configuration profile with a Certificate payload
holding <code>{CA_CERT}</code>.</li>
<li><strong>Mac, by hand:</strong> open the certificate, add it to the System keychain,
and set <em>When using this certificate</em> to <em>Always Trust</em>.</li>
<li><strong>Windows:</strong> Group Policy, <em>Computer Configuration &rarr; Policies
&rarr; Windows Settings &rarr; Security Settings &rarr; Public Key Policies &rarr; Trusted
Root Certification Authorities</em>, Import.</li>
</ul>
</section>
<section class="card-panel">
<h2>For the librarian: after IT says the check page works</h2>
<ol>
<li>Download each Teacher's Minting page again (<a href="/staff/keys">Keys</a>): the
address in it is now <code>https://</code>. Cards made from an old page stop working.</li>
<li>Make the day's Cards as usual. Cards from before today have expired anyway.</li>
</ol>
<p>The certificate renews itself every year; IT does nothing again unless this computer's
address changes.</p>
</section>"""


@router.get("/staff/it-kit")
def it_kit(
    account: LibrarianDep,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
) -> HTMLResponse:
    return page(
        "IT kit",
        f'<div class="it-kit">{_kit_body()}</div>',
        account=account,
        db=db,
        now=clock,
    )
