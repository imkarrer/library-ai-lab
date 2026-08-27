# Handoff: picking this up on the M5 Pro

The task graph was created on a Linux machine. This is what it takes to continue on the Mac.

## 1. Install beads

Version matters — the graph was built with 1.2.2, and the `bd create --graph` schema is
newer than most documentation you will find.

```bash
gh release download v1.2.2 --repo steveyegge/beads \
  --pattern 'beads_1.2.2_darwin_arm64.tar.gz'
tar xzf beads_1.2.2_darwin_arm64.tar.gz
mkdir -p ~/.local/bin && mv bd ~/.local/bin/bd && chmod +x ~/.local/bin/bd
bd version   # expect: bd version 1.2.2
```

Once the graph is confirmed working, add `bd` to `workstation`'s base flox env so it is
declarative like everything else rather than a stray binary in `~/.local/bin`.

## 2. Clone and hydrate

```bash
git clone git@github.com:imkarrer/library-ai-lab.git
cd library-ai-lab
```

The clone gives you the repo but **not** the issues. `.beads/embeddeddolt/` is gitignored,
so the Dolt database does not travel with a normal `git clone`. It rides along in a
separate ref, `refs/dolt/data`, which has already been pushed. Pull it:

```bash
bd dolt pull
bd stats     # expect: Total 37, Ready 14, Blocked 23
```

**Prefer this path.** Issue IDs are content-hashed, so rebuilding from the graph
definition would produce a different set of IDs and silently fork the tracker.

Only if `bd dolt pull` fails outright, rebuild from the committed definition:

```bash
bd init --non-interactive --prefix lib --role maintainer
bd create --graph docs/beads-graph.json
bd stats     # expect: Total 37, Ready 14, Blocked 23
bd dolt push --force
```

Verifying this round-trip is itself a tracked task: **"Verify beads cross-machine sync."**
Create a throwaway bead on the Mac, `bd dolt push`, and confirm it comes back. Then close
the bead out.

## 3. Sanity-check the graph

```bash
bd ready
```

You should see 14 items: the five epics plus nine unblocked tasks. If `bd ready` instead
shows things like "Add darwin/ai.nix" or "Dogfood review," the dependency edges got
inverted — in beads, `{"from_key": "X", "to_key": "Y", "type": "blocks"}` means **X is
blocked by Y**, which is the opposite of how it reads.

## 4. Start here

The first technical bead is **"Add ollama-app cask to workstation"** (P0, Epic A). It
unblocks four other tasks and everything in the benchmark suite downstream of them.

```bash
bd ready
bd show <id>
bd update <id> --status in_progress
```

In parallel, and genuinely more urgent in calendar terms, Epic E has four P0 items with no
technical blockers at all: the DPI consultation, the board brief, the escalation protocol,
and the quality preflight. The DPI conversation and board scheduling have lead times
measured in weeks, and board approval is one of three gates on the purchase decision.

## 5. Two things not to get wrong

**Do not install the Homebrew `ollama` formula or nixpkgs `pkgs.ollama`.** Only the
`ollama-app` cask ships the real MLX backend. If the formula is present alongside the cask
it wins the `/opt/homebrew/bin/ollama` symlink and brew only warns "skipping link," leaving
you silently on a binary that is missing `llama-server`. Details are in the a1 and a3 beads.

**Do not switch to Determinate Nix.** flox does not support it, and this is already the
documented rule in the `workstation` repo.

## Note on git identity

This repo has a local-only git identity set (`Isaac Karrer <isaac.karrer@gmail.com>`)
because the Linux session had no global git config. Your Mac's global config will not be
affected, but if you would rather inherit it, run:

```bash
git config --local --unset user.name
git config --local --unset user.email
```
