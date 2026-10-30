# HTTPS by default, with a publicly trusted certificate from Let's Encrypt

Accepted 2026-10-30; not built yet. Supersedes ADR-0012 as the default. ADR-0012's local CA
stays as the fallback.

ADR-0012's certificate is safe, but a device trusts it only after district IT pushes it,
and an Install must work without IT. Volunteers' phones at a conference never trust it at
all. A certificate from a CA every device already trusts removes both problems. Let's
Encrypt issues one for free, for any name whose DNS we control, without ever connecting to
the Mac.

## Decision

- **The project buys one domain**, `[BLANK: domain]`, and runs its DNS. Placeholders below
  use `assistant.example`.
- **Each Install gets an opaque ID** (`k7f3q9`) and one wildcard certificate,
  `*.k7f3q9.assistant.example`. The ID says nothing about the school, because every
  certificate is published in Certificate Transparency logs. A name like
  `eauclaire-north` would list our schools for anyone to read.
- **The name carries the address**: `192-0-2-10.k7f3q9.assistant.example` resolves to
  `192.0.2.10`, as Plex does with `plex.direct`. A new DHCP address needs no DNS change and
  no new certificate; the Install only changes the name its Cards and Minting pages carry.
  Our DNS service answers these names by parsing them, so no record is ever written per
  address.
- **Let's Encrypt checks the domain by DNS (the DNS-01 challenge)**, never by connecting to
  the Mac, so the Mac is never reachable from the internet. Each Install gets acme-dns-style
  credentials that can write its own challenge record (`_acme-challenge.k7f3q9`) and
  nothing else. Nothing on the Mac can change any other name.
- **Renewal is the one standing exception to ADR-0006.** Certificates last 90 days today,
  and the CA/Browser Forum's schedule shortens them to 47 days by 2029, so the Mac needs a
  short outbound window roughly monthly. The window is the updater's (the 2026-10-30
  deployment plan): opened by the Mac's own firewall, for the ACME client only, only to
  Let's Encrypt and our acme-dns endpoint, with Students paused while it is open. The app's
  internet self-check treats that window, and only it, as expected. Renewal is attempted
  from 30 days before expiry, so a school whose internet is down for a while loses nothing.
- **The local CA (ADR-0012) is the fallback**: for a school that allows no outbound window
  at all, and for when our DNS service or Let's Encrypt is unreachable for weeks. The IT kit
  says which an Install is using.

## What can go wrong, and what we do

| Risk | Mitigation |
|---|---|
| A school's resolver or filter refuses public names that point to private addresses (DNS rebinding protection, such as Cisco Umbrella's option) | The installer's reachability test (from a Chromebook) catches it. The fix is one exception for `assistant.example` (IT, a one-line ask in `it-network-request.md`) or the local CA. |
| The school's internet is down, so the name doesn't resolve | Long TTLs. The Live view shows the IP address, which still works over plain HTTP. |
| Our DNS service is down | Existing Installs keep working while resolvers cache. Run it on two providers. |
| A credential on one Mac leaks | It can write that Install's challenge record and no other. Revoke it and issue a new one. |
| The certificate's private key leaks | It covers one Install's names only. Revoke it through ACME and issue a new one at the next window. |

## The demo

The venue has no internet (runbook, Step 4), so:

1. **At home, online:** `./stack up --lan --public-cert` issues the certificate for the
   travel router's subnet. It lasts 90 days, so issue it within a month of the talk.
2. **At the venue:** the travel router answers the Install's name itself (GL.iNet and
   OpenWrt routers take a custom DNS entry), because no public DNS is reachable.
   Volunteers' phones open `https://192-0-2-10.k7f3q9.assistant.example:8000` and get a
   padlock, with no certificate to install.
3. **On stage:** point at the padlock. *"Every Chromebook in your district already trusts
   this. IT installs nothing."*

Phones set to strict private DNS (Android "Private DNS" with a provider set, or iCloud
Private Relay) ignore the router's DNS. Check the volunteers' phones before the talk, or
have them use a phone we hand them.

## Implementation, in order

1. Buy the domain; run an authoritative DNS service that answers the address-in-the-name
   form, and an acme-dns endpoint, on two providers.
2. `library_assistant/acme.py`: request and renew the wildcard certificate (DNS-01) through
   the window; serve it the way ADR-0012's certificate is served. Cards, Minting pages, and
   the QR codes carry the address-in-the-name host.
3. `./stack up --public-cert` for the demo; the router entry in the runbook.
4. The IT kit and `it-network-request.md` gain the DNS-rebinding exception, and describe
   the local CA as the fallback.
5. A deck slide: the padlock on a volunteer's phone, and the line above.

Not chosen: one shared wildcard certificate for every Install (its key would sit on every
Mac); per-address A records (each new DHCP address would need a DNS write); HTTP-01
challenges (they need the Mac reachable from the internet, against ADR-0006).
