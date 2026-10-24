# library-ai-lab

A local AI assistant a school librarian installs with [flox](https://flox.dev) on hardware in
the building. Students ask about the library's collection using short-lived QR **Cards**
that carry no identity; the librarian watches what is being asked; a deterministic Watchlist,
plus an optional Oversight model when the hardware can spare it, flags messages a counselor
needs to see. Nothing leaves the school network.

It is also a showcase for flox in education: the goal is a talk on flox for edu, then a
session at [SLATE](https://slateinwi.com/), Wisconsin's school leadership technology
conference, with a Wisconsin middle school library as the first real Install.

## Status

Pre-code. The design is settled in [`CONTEXT.md`](CONTEXT.md) (the vocabulary) and
[`docs/adr/`](docs/adr) (the decisions and why). Work is tracked in beads.

## How it protects students

- **Cards are minted on the Teacher's machine.** The assistant receives only Token hashes,
  an expiry, and a class label such as "Period 3". It has never held a student's name
  ([ADR-0002](docs/adr/0002-cards-are-minted-on-the-teachers-machine.md)).
- **Transcripts are purged at the end of each school day**, except those attached to an open
  Flag ([ADR-0003](docs/adr/0003-purge-at-end-of-school-day.md)).
- **Flags assist the adults.** A deterministic Watchlist is always on. An Oversight model
  can be added on a second box, or on the same box when it never slows students down.
  High-severity disclosures get a supportive reply, not a refusal
  ([ADR-0004](docs/adr/0004-flags-assist-adults.md)).
- **Intranet only.** The model and the catalog are services on the school's own network; no
  cloud provider is configured anywhere ([ADR-0006](docs/adr/0006-intranet-only.md)).

## What must not be committed here

This repo is public, which is right for the code, the templates, and the reasoning. Keep out:

- Any Install's network topology, VLAN layout, or firewall rules
- Secret material of any kind
- Transcripts, Flags, Rosters, and anything else traceable to a student
- A completed privacy impact assessment naming real systems and staff

Templates and legal reasoning belong here; filled-in versions belong in a
district-controlled store.

## Working with the tracker

Issues live in [beads](https://github.com/steveyegge/beads) (prefix `lib-`). The embedded Dolt
database is gitignored and syncs through `refs/dolt/data` on the remote:

```bash
bd dolt pull      # before starting work
bd ready          # unblocked work
bd show <id>      # one issue with its dependencies
bd dolt push      # after making changes
```

`.beads/issues.jsonl` is a committed, human-readable export, not the source of truth.
