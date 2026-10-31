# library-ai-lab

A local AI assistant a school librarian installs with [flox](https://flox.dev) on hardware in
the building. Students ask about the library's collection using short-lived QR **Cards**
that carry no identity; the librarian watches what is being asked; a deterministic Watchlist,
plus an optional Oversight model when the hardware can spare it, flags messages a counselor
needs to see. Nothing leaves the school network.

It runs on Apple Silicon Macs and on x86_64 or aarch64 Linux. Intel Macs are not supported:
nixpkgs dropped x86_64-darwin, so the environment cannot lock current packages for them.

It is also a showcase for flox in education: the goal is a talk on flox for edu, then a
session at [SLATE](https://slateinwi.com/), Wisconsin's school leadership technology
conference, with a Wisconsin middle school library as the first real Install.

## Status

Running as a demo. The design is settled in [`CONTEXT.md`](CONTEXT.md) (the vocabulary) and
[`docs/adr/`](docs/adr) (the decisions and why). Work is tracked in beads.

## Running it

One command runs the whole stack on this machine (`scripts/stack.py`):

```bash
./stack up --mock    # the fake model (scripts/fake_model.py): no Ollama, answers in a second
./stack up           # both Lanes on flox's own Ollama: gpt-oss:20b answers, qwen3.5:4b screens
./stack up --lan     # listening on the Wi-Fi address, so phones can reach it
./stack up --https   # HTTPS from the stack's own CA; /staff/it-kit has what IT needs
./stack status       # what is running, the sign-in URL, Make Cards, the passwords file
./stack down         # stop everything `up` started (Ctrl-C-safe: it is all in the background)
./stack seed         # the demo cast, settings, and the Teacher's offline Minting page (idempotent)
./stack clear        # down, then delete the stack's database and files
./stack materials    # build the decks and handouts into docs/handout/build; starts nothing
```

Every `up` makes sure the demo cast exists, each username starting with its role: Ms.
Overdue (`librarian.overdue`), Mr. Pop-Quiz (`teacher.popquiz`), and Dr. Hugsworth
(`counselor.hugsworth`). Each password is the word after the dot (`overdue`, `popquiz`,
`hugsworth`), put back on every `up` and listed in `credentials.txt`. It also sets
Live supervision and fills in Period 3's fictional class list (Paige Turner, Justin Time,
...) for Mr. Pop-Quiz in **Make Cards**, the app the assistant serves at `/staff/mint/`:
sign in as him and press **Open Make Cards**. `./stack status` prints its address
(`Make Cards: <url>/staff/mint/`) and lists the cast. The same class goes into
`teacher.popquiz-minting-page.html`, the offline copy with his Registration key built in. The
deck that leads into the demo introduces the same people ([`docs/handout/`](docs/handout/)).
All of it lives in one folder outside the repo,
readable only by you (`--state`, default `~/library-assistant-demo`). The stack leaves alone
anything already answering on its ports, such as an Oversight Ollama started by hand.

`tests/test_integration_flows.py` runs whole school-day journeys (a Card scanned before Watch,
Oversight catching a paraphrase, a Flag going New, Acknowledged, Closed, an Escalation the
Counselor closes, a Revoke) against `./stack up --mock` in a temp folder, in a few seconds:

```bash
flox activate -- python3 -m pytest -q tests/test_integration_flows.py
```

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

## A school's own Catalog

A Librarian signs in, opens **Catalog**, and loads the library system's MARC export (binary
MARC or MARCXML). The load replaces the whole Catalog in one step, so a withdrawn book goes
too, and Students keep searching the old one until the new one is in. It keeps books only,
under the school's own call numbers (852, or Koha's 952), and it doesn't keep the file. See
the [addendum to ADR-0005](docs/adr/0005-catalog-behind-an-adapter.md).

## Demo Catalog

The shipped Catalog adapter is SQLite over MARC
([ADR-0005](docs/adr/0005-catalog-behind-an-adapter.md)). A 270-record sample of real
Library of Congress records (`tests/fixtures/catalog/loc-books-2016-sample.xml`; source and
selection in [its README](tests/fixtures/catalog/README.md)) ships in the repo so a fresh
checkout can search a Catalog with no network. For a demo with a realistic collection, build one from the Library
of Congress open-access MARC distribution — a separate, one-time setup step, never run by the
assistant and never run in CI ([ADR-0006](docs/adr/0006-intranet-only.md)'s demo exception):

```bash
flox activate -- python3 scripts/build_demo_catalog.py --dest catalog.db
```

It reads the Library of Congress "Books All" page, takes the newest year's MARCXML parts
(43 parts of about 70 MB each for 2016, about 3 GB in all), and handles one part at a time:
download, keep only the books a school librarian would recognize on a shelf, load, delete.
Kept: juvenile and adolescent titles (the MARC 008 target-audience byte) with a Dewey number,
or LoC's E (easy), Fic, or B (biography), in the record's 082. Each is labelled the way a
school spine label reads, the class then three letters of the author's surname: `599.74 LEP`,
`FIC SPI`, `B LIN`. It checks free disk against an estimate before starting. It builds into
`catalog.db.building` and swaps it in only when done, so a running demo keeps its Catalog; a
re-run resumes, and `--fresh` cleans out an older Catalog and seeds it again from the start.

Measured on one 2016 part (250,000 records, 2026-10-30): of its 8,019 juvenile titles, 6,066
(76%) were kept. Two thirds of the rest are music (LC class ML), which has no Dewey number.
The figures below are from the earlier build, which kept every juvenile title.

Measured from one real run against the live LoC distribution (`lib-f24.19`), on 2026-10-25,
on an x86_64 AMD Ryzen 7 9800X3D (8 cores / 16 threads) with 30 GiB RAM, under WSL2 on a home
broadband connection. All 43 parts of the 2016 distribution loaded in one run, with no resume:

| Metric | Value |
| --- | --- |
| Download size | 2.91 GiB (3,129,774,145 bytes, 43 parts) |
| On-disk Catalog size | 150 MiB (157,335,552 bytes) |
| Record count (post-filter) | 385,409 records |
| Wall-clock time | 20 min 53 s (1,253 s), including download, filter, and load |

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

## License

The code is source-available under the Business Source License 1.1 (see [`LICENSE`](LICENSE)).
In short:

- A school, a school district, or another public or non-profit educational institution can
  run it in production free of charge, for its own students and staff, installed and
  operated by its own employees.
- Anyone can read, copy, modify, and test it, which is non-production use.
- Any other production use, including installing, configuring, hosting, or supporting it
  for a school as a paid service, needs a commercial license from the Licensor.
- Each version becomes available under the Apache License 2.0 four years after it is
  published.

The snapshot at commit `afdba6e` was published under the Apache License 2.0 and stays
available under it. Later versions are under the Business Source License.

The templates in `docs/templates/` and the curriculum in `docs/curriculum/` are under CC BY
4.0 instead (see [`docs/LICENSE.md`](docs/LICENSE.md)), so districts, counsel, and teachers
can adapt and share them freely.

This summary is not legal advice. The text in `LICENSE` governs.
