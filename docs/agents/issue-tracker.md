# Issue tracker: Beads

Issues and specs for this repo live in **beads** (`bd`, v1.2.2), prefix `lib-`. There is
no second tracker: do not open GitHub issues or write `.scratch/` ticket files. IDs look
like `lib-9v7`; children of a parent look like `lib-a2x.2`.

The Dolt database is the source of truth. `.beads/issues.jsonl` is a passive export;
never edit it or `bd import` from it. Run `bd dolt pull` before a session and
`bd dolt push` after one, but only with the user's go-ahead (conservative profile).

## Conventions

- **Create an issue**: `bd create --title "..." --type task|feature|bug|epic|decision --priority 0-4 --body-file - <<'EOF'` with the body on stdin. Add `--parent <epic-id>` to place it under one of the five epics, and `--labels` for triage roles.
- **Read an issue**: `bd show <id>`; comments with `bd comments <id>`. Add `--json` when you need to parse labels or dependencies.
- **List issues**: `bd list --status open` (tree view), filtered with `--label <role>`, `--parent <id>`; `bd ready` for open and unblocked work.
- **Comment on an issue**: `bd comments add <id> "..."` (or `-f file.md` for long text).
- **Apply / remove labels**: `bd update <id> --add-label <label>` / `--remove-label <label>`.
- **Close**: `bd close <id> --reason "..."`.

Priorities are numbers (`0` critical to `4` backlog), never words.

## Pull requests as a triage surface

**PRs as a request surface: no.** Work is requested through beads, not PRs.

## When a skill says "publish to the issue tracker"

`bd create` one bead per ticket. Specs (`/to-spec`) go in as a `feature` bead under the
relevant epic; tickets (`/to-tickets`) become children of that spec with `--parent`,
created blockers-first so each can be wired with `bd dep add`.

## When a skill says "fetch the relevant ticket"

`bd show <id>` and `bd comments <id>`.

## Blocking

`bd dep add <blocked> <blocker>`: the first argument depends on the second. This reads
backwards from the graph JSON, where `{"from_key": X, "to_key": Y, "type": "blocks"}`
means X is blocked by Y. Check with `bd show <id>` that the edge points the way you meant.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a parent bead with **child** beads as tickets.

- **Map**: `bd create --type epic --labels wayfinder:map` with the Notes / Decisions-so-far / Fog body.
- **Child ticket**: `bd create --parent <map-id> --labels wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`), with the question in the body.
- **Blocking**: `bd dep add <child> <blocker>`. A ticket is unblocked when every blocker is closed.
- **Frontier query**: `bd ready --parent <map-id> --unassigned`; first in ID order wins.
- **Claim**: `bd update <id> --claim`, the session's first write.
- **Resolve**: `bd comments add <id> -f answer.md`, `bd close <id> --reason "<one-line gist>"`, then append a pointer (gist + bead id) to the map's Decisions-so-far with `bd update <map-id> --append-notes "..."`.
