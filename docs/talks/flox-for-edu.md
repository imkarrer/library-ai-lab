# Flox for edu: school tech that outlives the person who built it

A 20-25 minute talk for a technical audience: school IT staff, ed-tech coordinators,
technology integrators, and the one teacher in every building who writes scripts. The
Library Assistant is the worked example. This is the first of two talks (bead lib-cpa); the
SLATE session ([`slate-proposal.md`](slate-proposal.md), bead lib-4p8) reuses its story for
school leaders and librarians.

**Status: draft.** No event is chosen yet, and the live demo depends on the M5 Pro offline
demo (bead lib-f24.9), which is not built. Items marked `[VERIFY]` need a person to confirm
them before the talk. Vocabulary follows [`CONTEXT.md`](../../CONTEXT.md).

**Presenters.** Two roles. The *Engineer* builds the Library Assistant and works at Flox. The
*Librarian* is a working middle school librarian who plays the Teacher and the Librarian in
the demo. Both are named on the event's own form, not here. Say plainly that the Engineer
works at Flox, in the first two minutes.

---

## What is true today, and what the talk needs

Say this on stage too, because a technical audience will ask.

| Piece | State on 2026-10-25 | Needed for the talk |
|---|---|---|
| Design: vocabulary and ADR-0001 to ADR-0009 | Done | Slides 6-8 quote it |
| flox environment (`.flox/env/manifest.toml`) | Python 3.12 and uv, a venv built on activate, one service running uvicorn | The local model server as a second service (lib-f24.9) |
| Application | A FastAPI app with a `/health` route and one test | Minting, Registration, Grounded answer, Live view, Watchlist and Flag queue, Revoke, Purge |
| Demo Catalog | Not built (lib-f24.3) | Built online from Library of Congress MARC records before the talk (ADR-0006) |
| Offline demo on the M5 Pro | Not built (lib-f24.9, blocked by Grounded answer and Flagging) | The runbook works end to end with networking off |
| Reference deployment | None; Eau Claire is the planned first Install | Not needed. Do not imply a school is using it |

**Rule for the deck:** a slide may show only what has run on the demo machine. If lib-f24.9
is not done when the event's deadline arrives, pitch the talk without the live demo (see
"If the demo is not ready") and say so in the abstract.

---

## Running order (22 minutes, plus Q&A)

| Slides | Segment | Minutes | Who |
|---|---|---|---|
| 1-3 | The problem | 4 | Librarian, then Engineer |
| 4-5 | Flox in two minutes | 2 | Engineer |
| 6-8 | The Library Assistant | 4 | Engineer |
| 9 | Live demo | 8 | Both |
| 10-11 | What transfers to your tools | 3 | Engineer |
| 12 | What's not built, and how to help | 1 | Both |
|  | Q&A | 3 or more | Both |

---

## Slides and speaker notes

### Slide 1: Title

**On the slide:** "School tech that outlives the person who built it." Subtitle: "flox, and a
local AI assistant for a middle school library." Both presenters' names (from the event
form). The repo URL.

**Notes (Engineer, 30 s):** Introduce each presenter in one sentence. "I work at Flox, so weigh
what I say about it accordingly. Everything you'll see is open source, and the repo is
public."

### Slide 2: The tool that left with its builder

**On the slide:** A short, generic list of school tools: the robotics lab's laptop setup, the
CS class's Python install, the scheduling script, the library's label-printing helper.
Under it: "Works great. Until its builder takes a job in the next district."

**Notes (Librarian, 90 s):** Tell it from the building's side. Every school has a tool that one
person set up and nobody else understands, and it breaks on the first OS update after they
leave. Most of the room has inherited one. Ask for a show of hands. Don't name a real
colleague or district.

### Slide 3: The other way schools get tools: send the data to a vendor

**On the slide:** "Option A: a commercial AI chatbot. Student questions go to a vendor.
Option B: nothing." Then: "Neither lets the adults in the building see what students ask,
or notice when a student needs a counselor."

**Notes (Engineer, 2 min):** This is the gap the Library Assistant fills, taken from the
lib-f24 problem statement. Keep it about structure rather than any one company: a hosted
product puts student text on someone else's servers, under a contract the district may never
read again. For a recent, concrete case of exposure at a K-12 vendor, use the late-2024
PowerSchool breach `[VERIFY: dates, scope, and a primary source, such as the company's
notice or a state agency advisory, before it goes on a slide]`. Don't cite figures you
haven't checked.

The two problems are connected. Schools reach for hosted software partly because self-hosted
software dies when its builder leaves. Fix that, and Option C, "run it in the building,"
becomes realistic.

### Slide 4: Flox in two minutes

**On the slide:** The project's real manifest, cut down:

```toml
[install]
python.pkg-path = "python312"
uv.pkg-path = "uv"

[services.assistant]
command = "uvicorn library_assistant.app:app --host 127.0.0.1 --port 8000"

[options]
systems = ["aarch64-darwin", "aarch64-linux", "x86_64-linux"]
```

Then: `flox activate --start-services` (short form: `flox activate -s`).

**Notes (Engineer, 60 s):** Flox is an environment manager built on Nix. The manifest says
what the tool needs. The lock file (`manifest.lock`) records the exact versions. Both live in
the repo next to the code. Anyone who clones the repo and runs `flox activate` gets the same
Python and the same tools, on a Mac or a Linux box, with no container and no admin image.
`[services]` means the environment also starts the program and keeps it running. Sources:
[environments](https://flox.dev/docs/concepts/environments/) and
[services](https://flox.dev/docs/concepts/services/) in the flox docs.

### Slide 5: Why that matters to a school

**On the slide:** Three lines.
- "The setup is a file in the repo, not in someone's head."
- "The same file runs on the librarian's Mac and the district's Linux server."
- "The next person runs one command."

**Notes (Engineer, 60 s):** This answers slide 2. The builder's knowledge is in the manifest,
so it stays when they leave. Be honest about the limits. The manifest lists Apple Silicon
Macs and 64-bit Linux. It doesn't list Intel Macs (`x86_64-darwin`), which many schools still
have, and on Windows it would mean WSL `[VERIFY: flox's current Windows support in its docs
before the talk]`. FloxHub's Personal tier is free, and Team is $20 per seat per month
([pricing](https://flox.dev/pricing/), checked 2026-10-25) `[VERIFY: still current on the
talk date]`. A school using a public repo needs neither.

### Slide 6: The worked example

**On the slide:** One sentence from the README: "A local AI assistant a school librarian
installs with flox on hardware in the building." Under it, four pillars: **Cards with no
identity**, **daily Purge**, **deterministic Watchlist**, **intranet only**.

**Notes (Engineer, 60 s):** Students ask about the library's own collection, and every answer
cites real Records that a student can find on the shelf. Each pillar is one ADR, and the next
two slides cover them.

### Slide 7: The assistant never knows who

**On the slide:** A diagram. On the Teacher's laptop, Minting makes Cards (to print) and a
Roster (which stays on the laptop). An arrow to the assistant carries only "Token hashes,
Card numbers, expiry, Class label." A Student scans a Card and appears as "Period 3, card 14."

**Notes (Engineer, 60 s):** ADR-0002. "The server never had it" is a claim a board or a parent
can check. "The server forgot it" isn't. Identification is offline, between adults: someone
asks the Teacher who held card 14. Then ADR-0003: every transcript is deleted at the end of
the school day, except those attached to an open Flag. Adults watch in the Live view, so one
day's retention costs the Librarian nothing. The legal reasoning (FERPA, and Wis. Stat.
118.125 and 43.30) is in [`docs/templates/compliance/`](../templates/compliance/). This talk
isn't the place to argue it, but say it exists.

### Slide 8: Flags help the adults, and nothing leaves the building

**On the slide:** On the left: "Watchlist: curated phrases, always on, names the entry that
matched." On the right: "Model endpoint and Catalog on the school network. No cloud provider
configured."

**Notes (Engineer, 60 s):** ADR-0004: the Watchlist is deterministic, so every Flag is
explainable and testable, and a miss is a bug you can fix. An optional Oversight model can
raise more Flags when there is spare hardware, but it never slows a Student down. A
high-severity Flag gives the Student a Supportive reply (talk to a counselor or trusted
adult, and call or text 988), not a refusal. ADR-0006: no cloud provider is configured
anywhere, so "what happens to our students' data?" becomes a question a firewall rule
answers. ADR-0009: one box serves a supervised class, not the whole school at once. Don't
overclaim.

### Slide 9: Live demo (8 minutes)

See "Demo beats" below. The slide itself is a title card and a screenshot with Wi-Fi off.

### Slide 10: What transfers to your tools

**On the slide:** A short checklist.
1. Put the setup in a manifest in the repo, with its lock file.
2. Make the program a `[services]` entry, so starting it is one command.
3. Pin the language and tools with flox. Let the language's own installer fetch libraries,
   but only during setup.
4. Do anything that needs the internet in a separate, one-off step, then run with it off.
5. List the platforms you support in `[options] systems`, so nobody has to guess.

**Notes (Engineer, 2 min):** Each item maps to something in this repo. Item 3 describes how the
project works today: flox supplies Python 3.12 and uv, and on first activation the hook runs
`uv pip install` from `requirements.txt`. That first activation needs the internet, and
nothing after it does. Item 4 is ADR-0006's one exception, building the demo Catalog from
Library of Congress records.

### Slide 11: Other school tools this fits

**On the slide:** Examples, labelled as ideas and not tested:
- A CS class's Python or Jupyter setup, identical on every lab machine
- A local model server for a class that studies AI, without student accounts on a vendor site
- An offline reference library for a building with poor connectivity
- The robotics team's toolchain, handed from coach to coach

**Notes (Engineer, 60 s):** Say plainly that these are untested. The point is the pattern on
slide 10, not these particular packages. Flox's own
[local-model walkthrough with Ollama](https://flox.dev/popular-packages/llms-in-your-project-with-ollama-flox/)
is the nearest published example. Flox's site has no education or public-sector material
today: on 2026-10-25 its [case studies](https://flox.dev/case-studies/) were two AI companies,
and its sitemap had no education pages. This talk fills that gap rather than repeating an
existing program.

### Slide 12: What's not built, and how to help

**On the slide:** The status table from the top of this document, cut to three rows, plus the
repo URL and "Next: a session at SLATE, with a working school librarian."

**Notes (Both, 60 s):** The Librarian closes: "We want this in a real school library. If your
building would try it, or you'd review the Watchlist or the compliance templates, find us
afterwards." Don't announce a pilot school or a date that hasn't been agreed.

---

## Demo beats

The demo follows the lib-f24.9 runbook, which doesn't exist yet. These beats are what the
runbook has to support. Rehearse each one on the demo machine before submitting the talk.

**Before the talk (offstage, online):** Build the demo Catalog from Library of Congress MARC
records (lib-f24.3's builder, ADR-0006). Run `flox activate` once so the venv and packages are
in place. Print a backup sheet of the demo Batch in case the printer or projector fails.

| Beat | Who | What the audience sees | Line to say |
|---|---|---|---|
| 0. Networking off | Engineer | Wi-Fi off in the laptop's menu bar. The laptop and the volunteers' phones join a travel router that has no uplink. | "From here on, nothing in this room can reach the internet." |
| 1. Start it | Engineer | `flox activate -s` starts the assistant and the local model server. | "Once flox is on the machine, that's the whole install." |
| 2. Mint Cards | Librarian, as Teacher | Mint a Batch for the Class label "Demo" on the Teacher's machine and show the QR sheet. Show that the Roster file stays on that machine. | "The assistant gets hashes. The names stay with me." |
| 3. Scan | A volunteer | Someone in the front row scans a Card with a phone and lands in a chat with no login. | |
| 4. Ask | The volunteer | They ask for a book like one they loved. The answer cites Records from the Catalog. | "Every answer points to a real Record you can check." |
| 5. Live view | Librarian | The projected Live view shows "Demo, card 3" and the question. | "This is what I watch during class." |
| 6. A Flag | Librarian | Send a scripted message that matches a Watchlist entry. The Flag appears in the queue with its category, its severity, and the entry that matched. | "The Flag names the entry that matched. Nothing is guessed." |
| 7. Revoke | Librarian | Revoke card 3 from the Live view. The volunteer's phone says the Card no longer works. | |
| 8. Purge | Engineer | Run the Purge by hand. The transcripts are gone, and the flagged one stays until its Flag is closed. | "At the end of the school day, this happens on its own." |

**Choosing the Flag message.** Don't type a self-harm or abuse disclosure on stage, even as a
demo. Use a low-severity entry, such as a bullying phrase, so the Flag appears without a
Supportive reply. Show the Supportive reply on a screenshot instead, and say why. The starter
Watchlist (lib-f24.15) may need an entry for this, or a demo-only entry that ships disabled in
an Install's config `[VERIFY: decide in lib-f24.9 or lib-f24.15]`.

**Two things lib-f24.9 has to settle:**
- **Phones need a network.** "Networking off" can't mean no network at all, because the
  volunteer's phone has to reach the laptop. The demo needs a local network with no internet
  uplink, such as a travel router, and the service has to listen on that interface. Today the
  manifest binds uvicorn to `127.0.0.1`, which a phone can't reach `[VERIFY: lib-f24.9
  runbook]`. The phones' cellular data must be off too, or the audience can fairly say the
  demo wasn't offline.
- **Model size and speed.** The M5 Pro has 24 GB, and the bead asks for roughly a 9B model at
  Q4. ADR-0009's speed figures are for an M5 Max. Time the first token on the M5 Pro, and
  quote that number, not the ADR's, if anyone asks.

**If the demo is not ready.** Once lib-f24.9 passes, record a full run as a screen capture and
play it with live narration. If lib-f24.9 hasn't passed by the event's submission deadline,
pitch the talk as a design walk-through. Slides 1-8 and 10-12 stand without the demo, and the
abstract must not promise one.

**If the demo fails on stage.** Switch to the recording at the beat that failed. Don't debug in
front of the room.

---

## Choosing the event

Not chosen yet (lib-cpa: "pick the event"). Look for a regional ed-tech or IT meetup, a user
group, or a K-12 IT directors' gathering, ideally after the demo works and before the SLATE
deadline (see the timing note in [`slate-proposal.md`](slate-proposal.md))
`[VERIFY: candidate events and their deadlines]`. A talk that has already been given makes the
SLATE proposal stronger.

## Before you give this talk

- [ ] lib-f24.9 passes on the M5 Pro with networking off, and the recording exists
- [ ] Every `[VERIFY]` above is resolved, or the claim is cut
- [ ] Slide 1 discloses the Engineer's employer
- [ ] The Librarian has cleared co-presenting with their district `[VERIFY]`
- [ ] No slide or recording shows a real Student, Roster, school network, or staff member
