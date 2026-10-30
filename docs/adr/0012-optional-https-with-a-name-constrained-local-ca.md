# HTTPS is optional, from the Install's own name-constrained CA

Proposed 2026-10-30. Found while writing the network request for district IT
(`docs/templates/it-network-request.md`): the assistant serves plain HTTP on the school
network, so students' questions cross a wired hop unencrypted, and IT will ask.

An Install must work without district IT (constraint of 2026-10-30), and a Chromebook trusts
a private certificate only if IT pushes it through Google Admin. So HTTPS cannot be required.
It is optional hardening, and switching it on costs IT one certificate upload, once:

- **The Install is its own CA, in two levels.** A root, whose private key exists only long
  enough to sign one intermediate and is never written anywhere; and the intermediate, whose
  key stays on the Mac (0600) to renew the server certificate. IT pushes the root.
- **The intermediate can vouch for this Mac and nothing else.** A critical Name Constraints
  extension permits only the Mac's own addresses, and pins every kind of name it doesn't use
  to nothing (DNS to `.invalid`, IP to no address): constraints apply per kind, so permitting
  only an IP would leave every DNS name open. Constraints sit on the intermediate because
  RFC 5280 leaves a trust anchor's own constraints optional, while every verifier enforces an
  intermediate's. Trusting the root therefore lets nobody impersonate another site, even with
  the intermediate's key in hand. Tests sign a certificate for another site with that key and
  check it fails, in Python's verifier and in OpenSSL's.
- **IT acts once.** The root and intermediate last ten years. The server certificate lasts
  397 days and renews itself a month before expiry. Only a change of the Mac's address makes
  a new pair; the IT kit then names the old certificate to delete.
- **The server certificate has no subject**, its names in a critical SAN: OpenSSL checks a
  host-like Common Name against the DNS constraints and would refuse an IP-only Install's own
  certificate.
- **The IT kit** (`/staff/it-kit`, Librarian only) fills in the rollout for this Mac: its
  address, the root's fingerprint and expiry, the download link, and the Google Admin steps.
  `/library-assistant-ca.crt` serves the root (public, like any certificate), and
  `/it-check` tells IT whether a given device trusts it.

ADR-0006 is unchanged: certificates are made on the Mac, nothing fetches anything. The
rollout and the questions IT will ask are in `docs/templates/it-https-rollout.md`.

Not chosen: a public certificate (needs a public DNS name and internet access for renewal,
against ADR-0006); a single self-signed certificate (a root IT must trust for every name,
which a careful IT department should refuse); the Mac's mDNS `.local` name (Chromebooks on
managed networks often don't resolve it).
