# Design docs

ADRs (`docs/adr/`) record **why** each decision was made. These docs show **how** the
pieces fit at runtime: what happens, in what order, to one Student message, one Session, and
one Flag. They introduce no new decisions. Where a diagram has to choose something no ADR
settles, it says so under "Open questions", and the choice becomes a decision bead before
anyone builds it.

Vocabulary is `CONTEXT.md`'s. Each step names the bead that builds it, and "on main" marks
what already runs, so a diagram also shows how far the build has got.

| Doc | Answers |
|---|---|
| [Student message flow](student-message-flow.md) | What happens to one message, from the chat box to the reply and the Flag queue. Can a Student keep prompting after a Flag? |
| [Session lifecycle](session-lifecycle.md) | How a Session starts, what pauses it, what ends it, and what happens to its words afterwards. |

When a bead changes a flow drawn here, it updates the diagram in the same PR.
