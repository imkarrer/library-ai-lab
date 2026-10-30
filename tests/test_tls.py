"""HTTPS hardening (library_assistant/tls.py, docs/templates/it-https-rollout.md): a CA
that can vouch only for this Mac, a server certificate that renews itself, and the IT kit
that hands IT what it needs."""

from __future__ import annotations

import ipaddress
from datetime import UTC, datetime, timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.verification import PolicyBuilder, Store, VerificationError
from fastapi.testclient import TestClient

from library_assistant.__main__ import server_options
from library_assistant.access import connect, get_clock, get_db
from library_assistant.app import app
from library_assistant.staff import create_account
from library_assistant.tls import (
    CA_CERT,
    INTERMEDIATE_CERT,
    INTERMEDIATE_KEY,
    SERVER_CERT,
    SERVER_DAYS,
    _issue_server,
    ensure_certificates,
    fingerprint,
)

ADDRESS = "192.0.2.10"  # a documentation address
NOW = datetime(2036, 10, 27, 14, 0, tzinfo=UTC)


def _cert(path) -> x509.Certificate:
    return x509.load_pem_x509_certificate(path.read_bytes())


def _verify(tls_dir, leaf: x509.Certificate, name: str) -> None:
    """Verify as a browser would: trusting only the root, given the intermediate."""
    store = Store([_cert(tls_dir / CA_CERT)])
    intermediate = _cert(tls_dir / INTERMEDIATE_CERT)
    try:
        subject = x509.IPAddress(ipaddress.ip_address(name))
    except ValueError:
        subject = x509.DNSName(name)
    PolicyBuilder().store(store).time(NOW).build_server_verifier(subject).verify(
        leaf, [intermediate]
    )


def test_the_server_certificate_chains_to_the_ca_for_this_address(tmp_path):
    files = ensure_certificates(tmp_path, [ADDRESS], now=NOW)
    assert files.new_ca
    _verify(tmp_path, _cert(files.server_cert), ADDRESS)
    assert oct((tmp_path / INTERMEDIATE_KEY).stat().st_mode & 0o777) == "0o600"
    # The root's key was never written: only the intermediate's and the server's exist.
    keys = sorted(p.name for p in tmp_path.iterdir() if p.suffix == ".key")
    assert keys == ["intermediate.key", "server.key"]
    assert oct(files.server_key.stat().st_mode & 0o777) == "0o600"


def test_the_ca_cannot_vouch_for_any_other_site(tmp_path):
    """The intermediate's Name Constraints permit only this Mac: a certificate signed
    with the key kept on this Mac for another site fails verification."""
    ensure_certificates(tmp_path, [ADDRESS], now=NOW)
    ca = _cert(tmp_path / INTERMEDIATE_CERT)
    ca_key = serialization.load_pem_private_key(
        (tmp_path / INTERMEDIATE_KEY).read_bytes(), None
    )
    constraints = ca.extensions.get_extension_for_class(x509.NameConstraints)
    assert constraints.critical
    # Issued exactly as this Mac's own certificate is, only for another site.
    rogue_dir = tmp_path / "rogue"
    rogue_dir.mkdir()
    _issue_server(rogue_dir, ["bank.example"], ca, ca_key, NOW)
    rogue = _cert(rogue_dir / SERVER_CERT)
    with pytest.raises(VerificationError):
        _verify(tmp_path, rogue, "bank.example")


@pytest.mark.parametrize(
    ("mine", "rogue"),
    [
        (["192.0.2.10"], "192.0.2.99"),  # another address
        (["library.school.example"], "bank.example"),  # another name
        (["library.school.example"], "192.0.2.99"),  # a name-only Mac, an address
    ],
)
def test_every_kind_of_name_is_constrained(tmp_path, mine, rogue):
    ensure_certificates(tmp_path, mine, now=NOW)
    rogue_dir = tmp_path / "rogue"
    rogue_dir.mkdir()
    _issue_server(
        rogue_dir,
        [rogue],
        _cert(tmp_path / INTERMEDIATE_CERT),
        serialization.load_pem_private_key(
            (tmp_path / INTERMEDIATE_KEY).read_bytes(), None
        ),
        NOW,
    )
    _verify(tmp_path, _cert(tmp_path / SERVER_CERT), mine[0])
    with pytest.raises(VerificationError):
        _verify(tmp_path, _cert(rogue_dir / SERVER_CERT), rogue)


def test_a_start_keeps_the_ca_and_renews_the_server_certificate_a_month_early(
    tmp_path,
):
    ensure_certificates(tmp_path, [ADDRESS], now=NOW)
    ca_print = fingerprint(tmp_path / CA_CERT)
    server_print = fingerprint(tmp_path / SERVER_CERT)

    again = ensure_certificates(tmp_path, [ADDRESS], now=NOW + timedelta(days=10))
    assert not again.new_ca
    assert fingerprint(tmp_path / SERVER_CERT) == server_print

    late = NOW + timedelta(days=SERVER_DAYS - 20)
    renewed = ensure_certificates(tmp_path, [ADDRESS], now=late)
    assert not renewed.new_ca
    assert fingerprint(tmp_path / CA_CERT) == ca_print  # IT does nothing
    assert fingerprint(tmp_path / SERVER_CERT) != server_print


def test_a_new_address_makes_a_new_ca_and_keeps_the_old_one_to_name(tmp_path):
    ensure_certificates(tmp_path, [ADDRESS], now=NOW)
    old = fingerprint(tmp_path / CA_CERT)
    moved = ensure_certificates(tmp_path, ["192.0.2.20"], now=NOW)
    assert moved.new_ca
    assert fingerprint(tmp_path / f"previous-{CA_CERT}") == old
    _verify(tmp_path, _cert(moved.server_cert), "192.0.2.20")


def test_the_server_serves_https_when_both_variables_are_set(tmp_path):
    options = server_options(
        {
            "LIBRARY_ASSISTANT_TLS_DIR": str(tmp_path),
            "LIBRARY_ASSISTANT_TLS_NAMES": ADDRESS,
        }
    )
    assert options["ssl_certfile"] == str(tmp_path / SERVER_CERT)
    assert "ssl_certfile" not in server_options({})


@pytest.fixture
def https_install(tmp_path, monkeypatch):
    ensure_certificates(tmp_path, [ADDRESS], now=NOW)
    monkeypatch.setenv("LIBRARY_ASSISTANT_TLS_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARY_ASSISTANT_TLS_NAMES", ADDRESS)
    db = connect(":memory:")
    create_account(db, "librarian.overdue", "overdue", "librarian")
    create_account(db, "teacher.popquiz", "popquiz", "teacher")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_clock] = lambda: NOW
    yield tmp_path
    app.dependency_overrides.clear()


def _signed_in(username: str, password: str) -> TestClient:
    client = TestClient(app)
    client.post("/staff/login", data={"username": username, "password": password})
    return client


def test_the_ca_certificate_is_public_and_its_key_is_never_served(https_install):
    response = TestClient(app).get(f"/{CA_CERT}")
    assert response.status_code == 200
    assert response.content == (https_install / CA_CERT).read_bytes()
    assert b"PRIVATE KEY" not in response.content


def test_the_it_kit_is_filled_in_for_this_mac_and_only_for_the_librarian(
    https_install,
):
    kit = _signed_in("librarian.overdue", "overdue").get("/staff/it-kit")
    assert kit.status_code == 200
    assert f"https://{ADDRESS}:8000" in kit.text
    assert fingerprint(https_install / CA_CERT) in kit.text
    assert "Devices &rarr; Networks &rarr;" in kit.text
    teacher = _signed_in("teacher.popquiz", "popquiz").get(
        "/staff/it-kit", follow_redirects=False
    )
    assert teacher.status_code == 403


def test_the_check_page_says_to_use_https_when_opened_over_http(https_install):
    page = TestClient(app).get("/it-check").text
    assert "Open this page over HTTPS" in page
    trusted = TestClient(app, base_url=f"https://{ADDRESS}:8000").get("/it-check")
    assert "This device trusts the Library Assistant" in trusted.text
    assert fingerprint(https_install / CA_CERT) in trusted.text


def test_with_https_off_the_kit_explains_and_there_is_no_certificate(monkeypatch):
    monkeypatch.delenv("LIBRARY_ASSISTANT_TLS_DIR", raising=False)
    assert TestClient(app).get(f"/{CA_CERT}").status_code == 404
    assert "HTTPS is off" in TestClient(app).get("/it-check").text
