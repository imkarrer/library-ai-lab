# Planet Nix 2027 proposal: Bring Nix to school

A draft submission for [PlanetNix 2027](https://sessionize.com/planet-nix-2027), the Nix
conference Flox hosts beside SCALE. The talk itself is
[`docs/handout/planet-nix-deck.md`](../handout/planet-nix-deck.md); this file is what goes into
the call for proposals. Vocabulary follows [`CONTEXT.md`](../../CONTEXT.md).

**Status: draft.** The form sits behind a Sessionize login, so its fields and word limits
below are guesses marked `[VERIFY]`. Presenter details are `[BLANK]`.

---

## What the call asks for

Checked 2026-11-05 on [sessionize.com/planet-nix-2027](https://sessionize.com/planet-nix-2027).

| Item | What the page says |
|---|---|
| Event | April 1–2, 2027, Pasadena Convention Center, two tracks over two days |
| Deadline | **December 23, 2026, 11:59 PM Pacific** |
| Formats | Workshop (90 minutes), long talk (45), short talk (25), lightning talk (5) |
| Limit | Several submissions are allowed; one accepted talk or workshop per speaker |
| Topics | "Any topic in the orbit of Nix", all skill levels. Its examples include "deploying a fleet of NixOS machines at work" and "converting friends and family to Nix" |
| Slides, video, links | Not mentioned. Put links in the notes to the organizers (below) |
| Form fields and limits | Not visible without a login `[VERIFY]` |

---

## The proposal

### Format

**Short talk, 25 minutes.** The deck runs about 15 minutes, and the live demo about 8
([`demo-runbook.md`](../demo-runbook.md)). A long talk would need material the project doesn't
have yet. If the form asks for a fallback, offer a lightning talk on pinning 14 GB of weights.

### Title

**Bring Nix to school: a library AI in one closure**

Alternatives:
- "Two LLMs, no names, no cloud: shipping a school library's AI with Nix"
- "14 GB of pinned weights and a librarian who will never type `nix`"

### Abstract (about 180 words; the limit is `[VERIFY]`)

A research assistant built for a middle school library runs on one Mac on the shelf: two
local LLMs, no student names, no cloud, and every conversation deleted at the end of the
school day. The person who installs it is the school librarian, who will never type `nix`.
That turns every privacy promise into a packaging problem: "stays in the building" means
nothing is fetched after setup, and "one thing to keep running" means one environment.

This talk shows how it ships as a single Flox environment. The app is a `flox build` package
whose Python libraries all come from the catalog, and the one library the catalog lacked is
built from source, with an expression ready to propose to nixpkgs. The two models are agent-stacks model packages (in development): 14 GB
of weights pinned by digest, served from a read-only store, and refusing to download at
activation. The app calls them like any process would, because it isn't an agent client: it
is the harness.

It starts with the people who brought Nix to school first, includes a live demo with the
network off, and ends with what Nix still needs before a whole district can adopt it.

### What attendees take away

1. How to pin multi-gigabyte model weights as fixed-output derivations without holding them in
   memory, and how to make activation fail instead of silently downloading a missing blob.
2. How a model package with a `serve` command lets any process manager run a model, not only
   an agent's launcher.
3. How to package a Python web app so the tests run on exactly what ships, with `flox build`
   and catalog Python.
4. Where Nix stands in schools today (labs, exams, laptops) and what's missing before a district
   can adopt it: declared egress, a way to ship large weights, and a fleet story.

### Level

**Intermediate.** Assumes you know what a derivation and a closure are. No AI background
needed.

### Outline

| Minutes | Segment |
|---|---|
| 0–2 | Who brought Nix to school first: EPITA's labs, a NixOS exam, Nixbook |
| 2–6 | The library, the constraints, and why each one is a packaging problem |
| 6–13 | The Install: the app as a package, the models as packages, "we are the harness", policy you can grep for |
| 13–21 | **Live demo, network off:** Cards for a class, a volunteer asks, the Live view, a Flag, the end-of-day Purge |
| 21–24 | From one library to a district, and what's next |
| 24–25 | Questions |

### Notes to the organizers (private)

- **Code:** github.com/imkarrer/library-ai-lab, public, with about 980 tests in one gate.
- **Deck:** `docs/handout/planet-nix-deck.md` in the same repository (Marp source).
- **Demo recording:** `[BLANK: link to an unlisted 2–3 minute recording of the runbook, made
  before submitting]`. The same recording is the on-stage backup if the live demo fails.
- **What runs today and what's in development:** the app's `flox build` package and its
  catalog Python run today. Model packages follow agent-stacks Proposal 0002
  (github.com/agent-stacks/agent-stacks-spec, PR #7), which is still under review. A prototype
  in the repository pins model weights the same way, proven so far on a small model. The talk
  will say plainly which parts have shipped by April.
- **No school runs it yet.** It is built for a Wisconsin middle school library, and the talk
  won't imply a deployment.
- **Affiliation:** the speaker works at Flox. This is a personal project, free for schools to run
  (Business Source License, with a free-use grant for schools).
- **Room needs:** a projector with HDMI and power at the front. **No venue Wi-Fi:** the demo
  brings its own offline network.

### Speaker bio (`[BLANK]`, about 60 words)

`[BLANK: lead with the project, then say you work at Flox. Name the library-ai-lab repository.]`

---

## Before submitting

- [ ] Record the demo following the runbook, and put the link in the notes above
- [ ] Log in to Sessionize and check the form's fields and limits; trim the abstract to fit
- [ ] Check each `[APRIL]` note in the deck, and reword the abstract's "in development" if
      Proposal 0002 has merged
- [ ] Fill in the bio
- [ ] Submit by December 23, 2026, 11:59 PM Pacific
