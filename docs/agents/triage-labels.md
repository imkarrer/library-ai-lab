# Triage Labels

The skills speak in terms of five canonical triage roles. This file maps those roles to the actual label strings used in this repo's issue tracker.

| Label in mattpocock/skills | Label in our tracker | Meaning                                  |
| -------------------------- | -------------------- | ---------------------------------------- |
| `needs-triage`             | `needs-triage`       | Maintainer needs to evaluate this issue  |
| `needs-info`               | `needs-info`         | Waiting on reporter for more information |
| `ready-for-agent`          | `ready-for-agent`    | Fully specified, ready for an AFK agent  |
| `ready-for-human`          | `ready-for-human`    | Requires human implementation            |
| `wontfix`                  | `wontfix`            | Will not be actioned                     |

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the corresponding label string from this table.

These are bd labels: apply with `bd update <id> --add-label <label>`, query with `bd list --label <label>`. `ready-for-agent` means fully briefed. Handing a bead to the local bead-loop is a separate step: the `delegate:local` label (see the `delegate` skill).

## Who works a bead

| Label | Who | Meaning |
| --- | --- | --- |
| `delegate:local` | bead-loop | Code sized for one session. The loop always starts it on the local stage; Claude Sonnet is only its escalation path after the local attempts fail. Never add `stage:*` labels to send a bead straight to Sonnet. |
| `frontier` | A person driving a Claude session by hand | Work that needs a frontier model and a human steering it: safety-critical content, legal and policy drafts, design notes, research decisions. Never also `delegate:local`. |
| `ready-for-human` | A person | Needs hands, judgement, or access no agent has: hardware, schools, people, events. |

A bead too big for one Sonnet session gets split before it is labelled `delegate:local`.
