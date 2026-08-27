# library-ai-lab

Project tracking and school-facing documentation for an on-premises AI assistant in a
Wisconsin middle school library.

The goal is a system that is genuinely useful to librarians and students while exporting
**zero** student data — no vendor, no API keys, no DPA to negotiate, because there is no
third party in the loop at all.

## Two repos, two jobs

This project spans two repositories on purpose.

| | [`imkarrer/workstation`](https://github.com/imkarrer/workstation) | [`imkarrer/library-ai-lab`](https://github.com/imkarrer/library-ai-lab) (this repo) |
|---|---|---|
| Holds | nix-darwin + flox config, `ai/` lab, benchmark suite | Beads task graph, plan, board brief, compliance packet |
| Role | Reference implementation and daily driver | Project management and school-facing artifacts |

Both repos are public. The split is about separation of concerns rather than secrecy:
`workstation` is a personal machine configuration that happens to double as the reference
implementation, while the school program — budget, DPI consultation, compliance, curriculum
— has its own lifecycle and its own audience. Everything in `workstation/ai/` is
deliberately generic and structured so it can be lifted out with `git subtree split` when
the school hardware arrives.

### What must not be committed here

Being public is fine for the plan and the task graph, and arguably good for them — a school
board can read exactly what is being proposed, and other districts can copy it. It is not
fine for operational detail. Keep out of both repos:

- Network topology, VLAN layout, and firewall rules for the school
- Any secret material (the OIDC client secret belongs in `sops-nix`)
- Chat logs, flagged-event records, and anything else traceable to a student
- A completed privacy impact assessment naming real systems and staff

The compliance packet task (Epic E) produces a **template and the legal reasoning**, which
belong here. The filled-in version, with real names and real network detail, needs a
private home — a district-controlled repo or document store.

## Where the work is tracked

Tasks live in [beads](https://github.com/steveyegge/beads), a Git-backed issue tracker
with a real dependency graph — which matters here because the ordering constraints are
the whole point. Thirty-seven issues across five epics:

| Epic | Scope |
|---|---|
| A — Workstation runtime | Local inference on the M5 Pro. Unblocks all other technical work. |
| B — Benchmark suite | Which runtime to ship, and is MLX genuinely active. |
| C — Hardware validation | Gate the ~$5,400 purchase on measurement, not extrapolation. |
| D — Library system | Catalog RAG, chat UI, safety pipeline. |
| E — School program | DPI consultation, board approval, compliance, escalation protocol. |

Epic E is non-technical, fully parallel, and should start immediately — DPI consultation
and board scheduling have long lead times that the technical work does not, and board
approval gates the purchase decision.

`docs/beads-graph.json` is the canonical graph definition that seeded the tracker.
`docs/plan.md` is the full plan with the reasoning behind each decision.

## Working with the tracker

```bash
bd ready          # what can be worked right now, nothing blocking it
bd list           # everything, as a tree
bd show <id>      # one issue with its dependencies
bd stats          # counts by status
```

Beads stores issues in an **embedded Dolt database**, and `.beads/embeddeddolt/` is
gitignored. Committing this repo does *not* sync your issues. Cross-machine sync is:

```bash
bd dolt push      # after making changes
bd dolt pull      # before starting work
```

`.beads/issues.jsonl` is committed as a human-readable export and a recovery path. It is
not the source of truth and is not the sync mechanism.

## Picking this up on the Mac

See [`docs/handoff.md`](docs/handoff.md).
