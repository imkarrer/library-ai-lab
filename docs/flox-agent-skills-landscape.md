# Landscape: Flox + Agent Skills projectors

Canonical write-up (citations, `flox-agent` launch injector, `share/flox/<agent>/` layout):

**[flox-agent-skills/docs/prior-art.md](file:///Users/imkarrer/src/flox-agent-skills/docs/prior-art.md)** in `~/src/flox-agent-skills`.

That report supersedes the shorter notes that used to live here. Summary:

- No public GitHub or catalog name collision on `flox-agent-skills`.
- Flox owns **content** (`flox/flox-skills`, catalog `flox/skills-flox`) and a **launch-time** injector (`flox/flox-agent` / `flox-ai`) that deliberately does **not** write `~/.cursor/skills` or `~/.claude/skills`.
- Official packs live under `$FLOX_ENV/share/flox/<agent>/` and strip auto-discovery trees. Installing `flox/skills-flox` does **not** feed this projector’s `share/skills` scan without an adapter.
- `npx skills` already writes the same harness dirs; coexist, don’t fight basenames.
- Unique claim: **on `flox activate`, project `SKILL.md` into dirs harnesses already scan.**
