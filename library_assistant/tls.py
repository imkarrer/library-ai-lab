"""HTTPS for an Install: optional hardening (docs/templates/it-https-rollout.md).

The Install is its own certificate authority, and a deliberately weak one, in two levels:

- **The root**, the certificate district IT pushes to Chromebooks. Its private key exists
  only for the moment it takes to sign the intermediate, then is thrown away: nothing else
  can ever be signed by it, on this Mac or anywhere.
- **The intermediate**, signed by the root, carries a critical Name Constraints extension
  permitting only this Mac's own addresses. Its key stays on the Mac (0600) to renew the
  server certificate. Every certificate verifier enforces constraints on an intermediate
  (RFC 5280 leaves them optional on a root itself), so even a stolen key can vouch for
  this Mac and nothing else: trusting the root lets nobody impersonate another site.

The root and intermediate last ten years, so IT pushes once. The server certificate lasts
397 days and is renewed here, at start, a month before it expires: renewal never involves
IT. If the Mac's address changes, the intermediate no longer covers it and a new pair is
made; IT pushes the new root (the IT kit says so, and names the old one to remove).

Nothing here reaches the network (ADR-0006): keys are made on this Mac and never leave it.
Only the root certificate, which is public, is served, for IT to download.
"""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

CA_CERT = "library-assistant-ca.crt"  # the root: what IT pushes
INTERMEDIATE_CERT = "intermediate.crt"
INTERMEDIATE_KEY = "intermediate.key"
SERVER_CERT = "server.crt"  # the server certificate, then the intermediate
SERVER_KEY = "server.key"

CA_DAYS = 3650
SERVER_DAYS = 397
RENEW_BEFORE = timedelta(days=30)

# The assistant's process reads these (library_assistant/__main__.py, routers/it_kit.py).
TLS_DIR_ENV = "LIBRARY_ASSISTANT_TLS_DIR"
TLS_NAMES_ENV = "LIBRARY_ASSISTANT_TLS_NAMES"


@dataclass(frozen=True)
class TlsFiles:
    directory: Path
    names: tuple[str, ...]
    new_ca: bool

    @property
    def ca_cert(self) -> Path:
        return self.directory / CA_CERT

    @property
    def server_cert(self) -> Path:
        return self.directory / SERVER_CERT

    @property
    def server_key(self) -> Path:
        return self.directory / SERVER_KEY


def _general_name(name: str) -> x509.GeneralName:
    try:
        return x509.IPAddress(ipaddress.ip_address(name))
    except ValueError:
        return x509.DNSName(name)


def _subtree(name: str) -> x509.GeneralName:
    """A Name Constraints subtree that permits exactly `name`: one IP (/32 or /128), or
    one DNS name (a DNS subtree also permits its subdomains, which this Mac never
    issues)."""
    try:
        address = ipaddress.ip_address(name)
    except ValueError:
        return x509.DNSName(name)
    return x509.IPAddress(ipaddress.ip_network(address))


# Name Constraints apply to each kind of name separately: constraining only IP addresses
# leaves every DNS name allowed. So both kinds are always constrained, and a kind this Mac
# doesn't use is pinned to nothing: DNS to the reserved `.invalid` domain (RFC 2606), IP
# to no address at all.
_NO_DNS = x509.DNSName("invalid")
_NO_IP = (
    x509.IPAddress(ipaddress.IPv4Network((0, 0))),
    x509.IPAddress(ipaddress.IPv6Network((0, 0))),
)


def _constraints(names: Sequence[str]) -> x509.NameConstraints:
    permitted = [_subtree(n) for n in names]
    excluded: list[x509.GeneralName] = []
    if not any(isinstance(n, x509.DNSName) for n in permitted):
        permitted.append(_NO_DNS)
    if not any(isinstance(n, x509.IPAddress) for n in permitted):
        excluded.extend(_NO_IP)
    return x509.NameConstraints(
        permitted_subtrees=permitted, excluded_subtrees=excluded or None
    )


def _write_private(path: Path, data: bytes) -> None:
    path.write_bytes(data)
    path.chmod(0o600)


def _key_pem(key: ec.EllipticCurvePrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _pem(cert: x509.Certificate) -> bytes:
    return cert.public_bytes(serialization.Encoding.PEM)


def _load_cert(path: Path) -> x509.Certificate:
    return x509.load_pem_x509_certificate(path.read_bytes())


def ca_permits(intermediate: x509.Certificate, names: Sequence[str]) -> bool:
    """True if the intermediate's Name Constraints permit exactly these names."""
    try:
        constraints = intermediate.extensions.get_extension_for_class(
            x509.NameConstraints
        ).value
    except x509.ExtensionNotFound:
        return False
    return constraints == _constraints(names)


_CA_KEY_USAGE = x509.KeyUsage(
    digital_signature=False,
    content_commitment=False,
    key_encipherment=False,
    data_encipherment=False,
    key_agreement=False,
    key_cert_sign=True,
    crl_sign=True,
    encipher_only=False,
    decipher_only=False,
)


def _ca_name(label: str, kind: str) -> x509.Name:
    return x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Library Assistant"),
            x509.NameAttribute(
                NameOID.COMMON_NAME, f"Library Assistant {kind} ({label})"[:64]
            ),
        ]
    )


def _make_ca(
    directory: Path, names: Sequence[str], label: str, now: datetime
) -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
    """Write a root (key discarded) and a name-constrained intermediate (key kept)."""
    root_key = ec.generate_private_key(ec.SECP256R1())
    root_name = _ca_name(label, "local CA")
    root = (
        x509.CertificateBuilder()
        .subject_name(root_name)
        .issuer_name(root_name)
        .public_key(root_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=CA_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=1), critical=True)
        .add_extension(_CA_KEY_USAGE, critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(root_key.public_key()),
            critical=False,
        )
        .sign(root_key, hashes.SHA256())
    )
    key = ec.generate_private_key(ec.SECP256R1())
    intermediate = (
        x509.CertificateBuilder()
        .subject_name(_ca_name(label, "intermediate"))
        .issuer_name(root_name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=CA_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(_CA_KEY_USAGE, critical=True)
        .add_extension(
            _constraints(names),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()),
            critical=False,
        )
        .sign(root_key, hashes.SHA256())
    )
    del root_key  # never written anywhere: the root can sign nothing more
    (directory / CA_CERT).write_bytes(_pem(root))
    (directory / INTERMEDIATE_CERT).write_bytes(_pem(intermediate))
    _write_private(directory / INTERMEDIATE_KEY, _key_pem(key))
    return intermediate, key


def _issue_server(
    directory: Path,
    names: Sequence[str],
    issuer: x509.Certificate,
    issuer_key: ec.EllipticCurvePrivateKey,
    now: datetime,
) -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    cert = (
        x509.CertificateBuilder()
        # No subject: OpenSSL checks a Common Name that looks like a host against the
        # DNS constraints, and "192.0.2.10" is not under `.invalid`. The names are in the
        # SAN, critical as RFC 5280 requires of a certificate with an empty subject.
        .subject_name(x509.Name([]))
        .issuer_name(issuer.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=SERVER_DAYS))
        .add_extension(
            x509.SubjectAlternativeName([_general_name(n) for n in names]),
            critical=True,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_key.public_key()),
            critical=False,
        )
        .sign(issuer_key, hashes.SHA256())
    )
    _write_private(directory / SERVER_KEY, _key_pem(key))
    # The chain a browser needs: this certificate, then the intermediate.
    (directory / SERVER_CERT).write_bytes(_pem(cert) + _pem(issuer))


def _server_is_current(directory: Path, names: Sequence[str], now: datetime) -> bool:
    if not (directory / SERVER_CERT).exists() or not (directory / SERVER_KEY).exists():
        return False
    cert = _load_cert(directory / SERVER_CERT)
    if cert.not_valid_after_utc - now < RENEW_BEFORE:
        return False
    sans = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    return set(sans) == {_general_name(n) for n in names}


def ensure_certificates(
    directory: Path,
    names: Sequence[str],
    label: str = "",
    now: datetime | None = None,
) -> TlsFiles:
    """The CA and server certificate for `names` (this Mac's addresses), made or renewed
    as needed. `new_ca` says a CA was made, which IT then has to push."""
    if not names:
        raise ValueError("HTTPS needs at least one address or name for this computer")
    names = tuple(dict.fromkeys(names))
    now = now or datetime.now(UTC)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    new_ca = False
    root_path = directory / CA_CERT
    cert_path, key_path = directory / INTERMEDIATE_CERT, directory / INTERMEDIATE_KEY
    if root_path.exists() and cert_path.exists() and key_path.exists():
        issuer = _load_cert(cert_path)
        issuer_key = serialization.load_pem_private_key(key_path.read_bytes(), None)
        if not ca_permits(issuer, names):
            # A new address: the old intermediate cannot vouch for it. Keep the old root
            # beside the new, so the IT kit can say which certificate to remove.
            root_path.replace(directory / f"previous-{CA_CERT}")
            issuer, issuer_key = _make_ca(directory, names, label or names[0], now)
            new_ca = True
    else:
        issuer, issuer_key = _make_ca(directory, names, label or names[0], now)
        new_ca = True
    if new_ca or not _server_is_current(directory, names, now):
        _issue_server(directory, names, issuer, issuer_key, now)
    return TlsFiles(directory, names, new_ca)


def fingerprint(cert_path: Path) -> str:
    """SHA-256 of the certificate, as IT tools show it: AB:CD:..."""
    digest = _load_cert(cert_path).fingerprint(hashes.SHA256()).hex().upper()
    return ":".join(digest[i : i + 2] for i in range(0, len(digest), 2))


def describe(cert_path: Path) -> dict[str, str]:
    cert = _load_cert(cert_path)
    return {
        "subject": cert.subject.rfc4514_string(),
        "not_after": cert.not_valid_after_utc.date().isoformat(),
        "sha256": fingerprint(cert_path),
    }


def configured_tls(environ: Mapping[str, str] | None = None) -> TlsFiles | None:
    """The Install's certificates if HTTPS is on (both variables set), made or renewed."""
    environ = os.environ if environ is None else environ
    directory, names = environ.get(TLS_DIR_ENV), environ.get(TLS_NAMES_ENV)
    if not directory or not names:
        return None
    return ensure_certificates(
        Path(directory), [n.strip() for n in names.split(",") if n.strip()]
    )


def ca_cert_path(environ: Mapping[str, str] | None = None) -> Path | None:
    """The CA certificate to serve, without making anything: None if HTTPS is off."""
    environ = os.environ if environ is None else environ
    directory = environ.get(TLS_DIR_ENV)
    if not directory or not environ.get(TLS_NAMES_ENV):
        return None
    path = Path(directory) / CA_CERT
    return path if path.exists() else None
