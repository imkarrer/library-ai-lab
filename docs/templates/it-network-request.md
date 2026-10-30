---
marp: true
theme: handout
paginate: true
footer: 'Library Assistant · network request for district IT'
---

# Network request: let student devices reach the Library Assistant (template)

> **This is a template.** The Librarian fills every `[BLANK: …]` and hands pages 1 to 3 to
> the district's network staff. Page 4 is for whoever talks to them: the questions they
> will ask, and true answers. Settle every `[VERIFY]` before you rely on it. Keep the
> filled-in copy, which holds your network's real addresses, in a district-controlled
> place, never in this public repository.

The Library Assistant needs only one thing from the network, and only on some networks: that
student devices can open a web page on one computer in the library. Everything else (the
model, the catalog, blocking its own internet access) the computer does by itself.

You need this page only if the installer's reachability test said "Chromebooks can't reach
this computer on this network". That message almost always means **client isolation**.

## Page 1. The request

**From:** `[BLANK: Librarian's name]`, `[BLANK: school]` library
**Device:** one Mac, `[BLANK: model]`, MAC address `[BLANK: Wi-Fi or Ethernet MAC]`

**What it is.** The Library Assistant: an AI research helper that runs entirely on this
Mac. Students open it in a browser on their school devices. It does not use the internet;
the Mac blocks its own outbound traffic and the app pauses students if that block ever
fails.

**What we're asking for: one inbound path, to one machine, on one port.**

| From | To | Port | Direction |
|---|---|---|---|
| student devices (`[BLANK: student SSID or VLAN]`) | this Mac only, `[BLANK: reserved IP]` | TCP `[BLANK: 8000]` | inbound to the Mac only |

Nothing else. In particular:

- **Keep client isolation on.** Students still can't reach each other. This is an
  exception for one destination, not turning isolation off.
- **Outbound from this Mac: none needed.** Deny it all if you like; the Mac already does.
- **The Mac never connects to student devices.** It only answers them.

**Also needed:**

1. **A DHCP reservation** for this Mac, so its address doesn't change. The QR cards and the
   teacher's card-making page carry the address.
2. **The content filter allows it.** If Chromebooks go through a filter (`[BLANK: GoGuardian,
   Securly, Lightspeed, or the Google Admin URL blocklist]`), allow
   `http://[BLANK: reserved IP]:[BLANK: 8000]/`.

---

## Page 2. Ways to do it, safest first

Pick whichever your equipment supports. Each gives student devices that one path and
nothing more.

### A. Plug the Mac into a wired port (usually the cleanest)

Treat it like a printer or a library catalog server. Wireless client isolation usually
applies only between Wi-Fi clients on the same network. Traffic to a wired host on another
VLAN goes through your router or firewall, where a normal rule controls it.

1. Patch the Mac into a wired port on a staff or server VLAN, `[BLANK: VLAN]`.
2. Reserve its address in DHCP.
3. Add a firewall rule: allow student VLAN → Mac IP, TCP `[BLANK: 8000]`. Deny the rest
   from students to that VLAN, as you do today.
4. Optional: deny everything outbound from the Mac's IP.

### B. An isolation exception on the wireless controller

Many controllers let isolated clients reach a short list of allowed hosts, which is how
they reach printers and gateways. Add this Mac's MAC or IP to that list, and if you can,
limit it to the one port. The setting's name differs by vendor and firmware. These are the
names to look for, not instructions. `[VERIFY]` against your controller's documentation:

| Vendor | Where to look |
|---|---|
| Cisco Meraki | SSID settings, Layer 2 isolation, and its allow list |
| Ruckus | WLAN client isolation, and its isolation whitelist |
| Ubiquiti UniFi | client device isolation, and the allowed or pre-authorized hosts list |
| Aruba | deny inter-user traffic, with an exception in the user role's ACL |
| Cisco Catalyst 9800 | peer-to-peer blocking, with a policy that allows this host |
| Juniper Mist | WLAN isolation settings, with an allowed-hosts or policy rule |

### Not this

- **Turning client isolation off** for the student network. That exposes every student
  device to every other one, which is what isolation is for.
- **Putting the Mac on the guest network.** Guest networks are usually the most isolated,
  and student devices usually aren't on them.

---

## Page 3. Check it, and undo it

### How to check it worked

1. On a student Chromebook, open `http://[BLANK: reserved IP]:[BLANK: 8000]/health`. It
   shows `{"status":"ok"}`.
2. From that Chromebook, another student device is still unreachable (isolation is still
   on).
3. On the Mac, the installer's reachability test now passes, and the app reports no
   internet access.

### How to undo it

Delete the firewall rule, or the isolation exception, and the DHCP reservation. Nothing on
the Mac depends on the district's configuration beyond those.

---

## Page 4. For whoever talks to IT: the questions they'll ask

**"Why does it need this at all?"** Students reach it from their own devices. On most
student Wi-Fi, isolation stops one device from opening a page on another, which is right
for student devices and wrong for this one server.

**"Is the traffic encrypted?"** By default, no, and say so plainly: the page is plain
HTTP on the school network. Wi-Fi encryption (WPA2 or WPA3) protects the radio hop; a wired
hop is unencrypted. What travels is students' research questions with a card number, never
a name. HTTPS is optional hardening: one certificate upload in Google Admin, about 15
minutes, once, from IT's desk. The certificate can vouch only for this Mac, so trusting it
lets nobody impersonate another site. Hand them `it-https-rollout.md`, which the
assistant's IT kit page fills in.

**"Can it reach the internet?"** No. The Mac's own firewall blocks outbound traffic. Every
few minutes the app checks it can't reach outside addresses, and if it can, it pauses
students and shows the Librarian a warning. Updates go through a short window that opens
only for the updater, only to the update servers, with students paused. `[VERIFY]`: these
are being built (bead lib-17x). Describe only what is installed on the day.

**"What can a student reach on it?"** One web port. The staff pages on that port need a
staff password. The Mac's other services should be off: confirm Remote Login, Screen
Sharing, and File Sharing are off in System Settings, General, Sharing. `[VERIFY]` on the
Mac before the conversation.

**"Could it be used to attack students?"** It starts no connections to student devices. The
rule is one-way: students to the Mac, with replies only. A stateful firewall enforces that.

**"Someone could spoof its address."** Tie the DHCP reservation to its MAC address, and use
802.1X or port security on the wired port if you have them.

**"What data is on it?"** Students' questions, without names, deleted at the end of every
school day (ADR-0003); Flags, kept while an adult works on them; staff accounts. Teachers
keep the list of who holds which card on their own computers (ADR-0002). The privacy
impact assessment (`compliance/pia-template.md`) has the detail.

**"Who maintains it?"** The Librarian, from a browser: updates are a button, and a
diagnostics download (versions and health, no student text) goes to the maintainer when
something breaks. Nobody needs remote access to the Mac.

**"Do we need to manage it in our MDM?"** No, but you may. If the district enrols it, the
assistant runs the same either way.
