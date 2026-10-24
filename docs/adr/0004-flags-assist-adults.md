# Flags come from a Watchlist always, and from Oversight only when it costs Students nothing

Every Student message is checked against the Watchlist, a curated, versioned set of phrases
and patterns for each Rubric category. It needs no inference and can't be switched off, so
every Install has a floor that is explainable (the Flag names the entry that matched) and
testable. On top of it, an Install can configure **Oversight**: a model that reviews each
exchange against the Rubric on its own Lane, separate from the Answer lane that serves
Students. Oversight is shaped like bead-loop's lanes: one endpoint per job, a lock per
shared resource, and a backlog that is held rather than failed when its endpoint is down.

Oversight must never cost Students anything:

- **Its own hardware** (a second box, such as two M5s): it runs continuously.
- **Sharing the Answer lane's box**: it runs only when both models fit in memory together
  *and* the Answer lane is idle. It yields the accelerator whenever a Student is waiting, and
  drains its backlog in the gaps and after class, always before the Purge.
- **Not configured, or the box can't hold both models**: the Watchlist alone.

High-severity Flags, from either source, return a Supportive reply rather than a refusal,
since a refusal teaches a 12-year-old not to say it again. A Supportive reply can only come
from the Watchlist, because Oversight runs after the answer. The Counselor role is optional:
the Librarian can work the Flag queue and escalate by hand. The product and its docs describe
flagging as help for the adults' duty of care, never as a substitute for it.

## Considered Options

- **A model pass on every exchange, inline.** It catches euphemism and context ("I don't want
  to be here anymore") that patterns miss, but on one box it roughly halves the class that box
  can serve (ADR-0009).
- **Watchlist only.** No contention at all, but it gives up what a model catches on hardware
  that could afford it.

## Consequences

- The Watchlist is still the safety-critical artifact, because it is the only source on most
  Installs and the only source of an immediate Supportive reply. A miss is a Watchlist bug.
- Hardware detection decides whether Oversight can share the box. The default is off unless
  both models fit.
- An Oversight Flag can arrive minutes or hours after the exchange. The Flag queue shows which
  source raised each Flag and when.
