---
marp: true
theme: handout
paginate: true
footer: 'Library Assistant · HTTPS rollout for district IT'
---

# HTTPS for the Library Assistant: rollout for district IT

<p class="lede">Optional hardening: students' questions travel encrypted between their
Chromebooks and the library's Mac. About 15 minutes of IT's time, once, from your desk.
Nobody needs to visit the school.</p>

> **This is a template.** The Library Assistant's **IT kit** page (`/staff/it-kit`, signed
> in as the Librarian) fills in everything marked `[BLANK: …]` for this Mac: its address,
> the certificate, and its fingerprint. Settle every `[VERIFY]` against your console before
> relying on it. Keep filled-in copies out of this public repository.

## What changes

| | Without HTTPS (the default) | With HTTPS |
|---|---|---|
| Address | `http://[BLANK: address]:8000` | `https://[BLANK: address]:8000` |
| Questions on the wire | readable on a wired hop | encrypted end to end |
| What students see | the same pages | the same pages, with a padlock |
| What IT does | nothing | upload one certificate to Google Admin, once |

## What it costs IT

1. **One certificate upload** in the Google Admin console, for the organizational unit
   with the library's Chromebooks. Step-by-step on page 3.
2. **The same certificate on staff computers** that Teachers make Cards on or the
   Librarian watches from, if they are Macs or Windows PCs. Chromebooks are covered by
   step 1. Page 4.
3. **A DHCP reservation** for the Mac, if it doesn't have one already (the network request
   asks for it too). The certificate names the Mac's address, so the address must not
   change.

Nothing else: no firewall change beyond the network request, no agent, no account, no
renewal. The certificate renews itself every year without IT. The call that does all of it
is on page 4.

---

## Why the certificate is safe to trust

The usual objection to a private certificate is right: a root certificate on every
Chromebook could, in the wrong hands, vouch for *any* website. This one can't.

<div class="box">

**It can vouch for one address: the library's Mac.** Nothing else, even if someone stole
everything on that Mac.

</div>

- **Two levels.** You install a root. The root signed exactly one certificate, an
  *intermediate*, and its private key was destroyed in the same second. It was never
  written to disk, so the root can never sign anything again, anywhere.
- **The intermediate is fenced in.** It carries a critical *Name Constraints* extension
  that permits only the Mac's address. Every other DNS name and IP address is excluded.
  Browsers and operating systems enforce constraints on an intermediate, so a certificate
  it signs for any other site is refused.
- **Tested both ways.** The project's tests sign a certificate for another site with the
  intermediate's key and check that verification fails, in Python's verifier and in
  OpenSSL's ("permitted subtree violation").
- **Keys never leave the Mac.** The intermediate's key is readable only by the Mac's
  account that runs the assistant. Only certificates, which are public, are ever served.

To inspect it yourself, download the certificate and run:

```
openssl x509 -in library-assistant-ca.crt -noout -text
```

The constraint is on the intermediate, the second certificate the Mac sends
(`openssl s_client -connect [BLANK: address]:8000 -showcerts`). Read it the same way and
look for `X509v3 Name Constraints: critical`, permitting only `IP:[BLANK: address]` and
`DNS:invalid` (a reserved name that never resolves).

## What IT will ask

**How long is it valid?** The root and intermediate: ten years. The server certificate:
397 days, renewed automatically a month before it expires.

**What if the Mac's address changes?** Its certificate no longer covers it, so the Mac
makes a new pair. The IT kit says so, shows the new certificate, and names the old one to
delete. With a DHCP reservation this doesn't happen.

**Does it touch the internet?** No. Certificates are made on the Mac; nothing is fetched.

**Can we revoke it?** Delete it from Google Admin; devices drop it at their next sync.

---

## Chromebooks: Google Admin, step by step

Do this on a video call with the Librarian, who has the IT kit page open. `[VERIFY]` the
menu names against your console: Google renames them from time to time.

1. **Get the certificate** from the IT kit page, or
   `https://[BLANK: address]:8000/library-assistant-ca.crt` (expect a browser warning:
   nothing trusts it yet).
2. **Check the fingerprint.** Read the SHA-256 fingerprint on the IT kit aloud with the
   Librarian:

   `[BLANK: SHA-256 fingerprint]`

   Compare it with your copy: `openssl x509 -in library-assistant-ca.crt -noout
   -fingerprint -sha256`. If they differ, stop.
3. **Open** the Admin console, then **Devices → Networks → Certificates**.
4. **Pick the organizational unit** on the left that holds the library's student
   Chromebooks. Add the staff Chromebooks' unit too, if staff use Chromebooks.
5. **Add certificate.** Name: *Library Assistant, `[BLANK: school]`*. Upload
   `library-assistant-ca.crt`. Under **Certificate authority**, tick **Chromebook**. Save.
6. **Test one device.** On a Chromebook in that unit, open `chrome://policy` and press
   **Reload policies**, then open:

   `https://[BLANK: address]:8000/it-check`

   It should load **with no warning** and say *"This device trusts the Library
   Assistant"*, with the same fingerprint.
7. **Done.** Other Chromebooks pick it up at their next policy sync, usually within the
   hour.

## If the check page shows a warning

| What you see | Why | Fix |
|---|---|---|
| a "Your connection is not private" warning | policy hasn't reached the device | Reload policies; check the device is in the unit you chose |
| a warning naming the wrong address | the Mac's address changed | the IT kit shows the new certificate: upload it, delete the old |
| the page doesn't load at all | client isolation or a firewall | the network request (`it-network-request.md`) |
| "Open this page over HTTPS" | the address starts with `http://` | type `https://` |

---

## Staff computers

Only the computers where Teachers make Cards, or the Librarian watches the Live view, need
it. On a Chromebook, the Google Admin step already covers them.

| Computer | Managed | By hand |
|---|---|---|
| Mac | an MDM configuration profile with a Certificate payload holding `library-assistant-ca.crt` | open the file, add it to the **System** keychain, open it in Keychain Access and set **When using this certificate** to **Always Trust** |
| Windows | Group Policy: Computer Configuration → Policies → Windows Settings → Security Settings → Public Key Policies → Trusted Root Certification Authorities → Import | double-click the file, **Install Certificate**, Local Machine, **Trusted Root Certification Authorities** |

Chrome and Edge on Mac and Windows use the operating system's trusted certificates, so no
browser setting is needed. Firefox keeps its own list unless enterprise roots are enabled
(`security.enterprise_roots.enabled`). `[VERIFY]` for your Firefox version if staff use
it.

## The 20-minute call

**Before:** whoever installed the assistant has turned HTTPS on. The Librarian has
signed in, opened **IT kit**, and has one student Chromebook at hand.

| Minute | What happens |
|---|---|
| 0–3 | The Librarian shares the IT kit page. IT downloads the certificate. |
| 3–5 | Read the fingerprint aloud together (step 2). |
| 5–12 | IT adds it in Google Admin (steps 3 to 5), sharing their screen if they like. |
| 12–17 | On the student Chromebook: Reload policies, then the check page (step 6). |
| 17–20 | Staff computers, if any; the Librarian downloads the Minting pages again. |

**After:** the Librarian downloads each Teacher's Minting page again from **Keys**, because
the page carries the address and that now starts with `https://`. Cards are made fresh
every day, so nothing else needs reprinting.

**To undo:** turn HTTPS off, and delete the certificate from Google Admin. Download the
Minting pages again.
