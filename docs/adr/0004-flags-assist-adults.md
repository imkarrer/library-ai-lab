# Flags come from a Watchlist always, and from Oversight screening every message when configured

Every Student message is checked against the Watchlist, a curated, versioned set of phrases
and patterns for each Rubric category. It needs no inference and can't be switched off, so
every Install has a floor that is explainable (the Flag names the entry that matched) and
testable. On top of it, an Install can configure **Oversight**: a model that reviews each
exchange against the Rubric on its own Lane, separate from the Answer lane that serves
Students. Oversight is shaped like bead-loop's lanes: one endpoint per job, a lock per
shared resource, and a backlog that is held rather than failed when its endpoint is down.

When Oversight is configured, it screens every message in real time, in parallel with the
answer, and a Session's next message waits for the current one's verdict ("Screening is real
time and ordered per Session", below). Where it runs:

- **Its own hardware** (a second box, such as two M5s): the better choice, since screening
  never contends with answering.
- **Sharing the Answer lane's box**: only when both models fit in memory together and the box
  can run both at once acceptably, which hardware detection (lib-06g) checks.
- **Not configured, or the box can't hold both models**: the Watchlist alone.

High-severity Flags, from either source, return a Supportive reply rather than a refusal,
since a refusal teaches a Student not to say it again. A Supportive reply can only come
from the Watchlist, because Oversight's verdict can land after the answer has streamed. The Counselor role is optional:
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
- An Oversight Flag arrives within seconds of its message, before that Session can send
  another. The Flag queue shows which source raised each Flag and when.

## Addendum: sharing the Answer lane's box

Decided 2026-10-24 (lib-f24.16), for lib-f24.14; partly superseded 2026-10-25 by "Screening
is real time and ordered per Session" at the end of this addendum, which wins where they
disagree. Memory fitting is not enough. On one Apple
Silicon box the two models share one GPU and one unified-memory bus, and decode is bandwidth
bound. Metal does not partition the GPU between processes, so any overlap slows the Student's
request. That is the reason for the lock.

**Idle is counted in the process, not polled from the server.** The assistant is the Answer
lane's only client (ADR-0006, ADR-0008), and a Student request reaches the process before it
reaches the server. So a counter the chat handler raises on admission (before the Catalog
search, since retrieval may use the box too) and lowers in a `finally` when the answer
finishes or fails is never late. Polling is late by its interval and races a request that is
being admitted. It also cannot see work queued in the assistant, `/metrics` is off by default
in llama-server, and llama-swap puts `/slots` behind `/upstream/<model>`. The Answer lane is
idle when that counter has been zero for a short quiet period (default 2 s), so a burst
does not start and cancel Oversight on every gap. `/health` is used only to tell a down
endpoint (the item is held, per lib-f24.10) from a busy one.

**A Student cancels Oversight and never waits on it.** Admission cancels any Oversight call in
progress and goes straight on to the Answer lane, without waiting for the cancel to finish.
The cancelled item goes back to the head of the backlog. It is held, not failed, as
bead-loop does, so it costs no retry count. Oversight requests always use `stream: true` and
cap their input and `max_tokens` (default 256), because a hang-up stops generation only
when the server notices it:

- llama-server ([`server-queue.cpp`](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/server-queue.cpp),
  `server_response_reader::stop`): a closed socket posts a `CANCEL` task to the front of the
  queue, and that task releases the slot. The socket is checked at each streamed token, and
  during prefill once every `HTTP_POLLING_SECONDS` (1 s). The cancel runs after the batch in
  progress, at most `-b` = 2048 tokens. There is no cancel endpoint, and
  `/v1/chat/completions/control` only ends reasoning.
- mlx_lm.server ([`server.py`](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/server.py)):
  a failed stream write sets `ctx.stop()`, and the server checks that between tokens. So a
  hang-up is noticed only after the first token, and a non-streamed request runs to its end.
- llama-swap ([`internal/swaputil/http.go`](https://github.com/mostlygeek/llama-swap/blob/main/internal/swaputil/http.go))
  proxies with the client's context, so a hang-up cancels the upstream request too.

Worst case, using ADR-0009's 2,700 tok/s prefill (~0.9 s for a cached grounded query):

- **Cancelled:** about 1 s to notice plus one 2,048-token batch (0.76 s) on llama-server, or
  the rest of a ≤3,000-token Oversight prefill (≤1.1 s) on MLX. That is ≤ 2 s of overlap in
  the worst case, and tens of milliseconds once Oversight is decoding. Running the
  Oversight server with `-b 512` cuts llama-server's batch term to 0.19 s.
- **Allowed to finish:** the whole Oversight prefill plus its decode. ADR-0009 has no decode
  figure. At 256 tokens and an assumed 30-60 tok/s that is 5-10 s on top of a ~1 s first
  token. A reasoning model's output is unbounded. So we cancel.

**The lock is one gate in one process.** `AnswerLaneGate` lives in the FastAPI process and
holds the Student count, the idle event, and the single Oversight lease, which is the
running Oversight task. It is shaped like bead-loop's lanes: the scarce thing is the box,
there is one lock per box, and a lane with nothing to do sleeps until woken
(`wait_for_work`) rather than polling. The Oversight worker waits for idle, takes the lease,
runs one item as a task, and releases the lease in a `finally`. Cancellation is the only way
the lease is taken back. Because the lock is in memory, a second process would have its own
gate. So the process takes an exclusive non-blocking `flock` on a file in its state
directory, as bead-loop's `try_lock` does (`src/lanes.rs`), and shared-box Oversight stays
off in a process that does not get the flock. That includes `uvicorn --workers N`.

**Shared mode is the safe default.** Shared mode applies when the two lanes' base URLs name
the same host, or when `oversight.shared_box = true`. Through llama-swap the two models must
be in one resident set (a `matrix` set, or a group with `swap: false`). By default llama-swap
runs one model at a time, so an Oversight request would evict the Answer model and cost
every Student a reload. On startup and after each Oversight call the assistant checks
llama-swap's `/running` for the Answer model. If it is missing, the assistant holds
Oversight with that reason and does not retry it. If Oversight shares the Answer model's own
llama-server, it is pinned to one slot (`id_slot`) so that it does not evict the Students'
cached prefixes.

**Screening is real time and ordered per Session.** Decided 2026-10-25 (lib-wpg), and it
supersedes the rest of this addendum where they disagree. Every chat interaction is screened
and reported while the adults who will act on it are present (ADR-0010):

- **In parallel with the answer.** When a Student's message arrives, the Watchlist runs
  first, as before. Then the Answer lane and the Oversight lane both start on it at once;
  Oversight does not wait for the answer, and the answer does not wait for Oversight.
- **The next message waits for the current screen.** A Session's next message is not
  admitted, to the Watchlist, the Answer lane, or Oversight, until Oversight's verdict on its
  current message is recorded. The chat page shows "one moment" meanwhile. One Session never
  waits on another Session's screening.
- **Nothing is cancelled to make room.** Because an Oversight verdict gates its own Session,
  an Oversight call is never cancelled when another Student asks. On a shared box the two
  lanes contend for the accelerator while both run; that cost is accepted, and it is why a
  second box is the better Oversight lane and why hardware detection (lib-06g) must plan for
  both models resident and busy at once.
- **When Oversight is down,** the Session's next message waits, the Live view says screening
  is unavailable, and after `oversight.unavailable_seconds` (default 30) the Librarian chooses
  between pausing Sessions and continuing on the Watchlist alone, recorded on every exchange
  admitted that way. Oversight not configured at all means the Watchlist alone, as before.
  *Superseded by "Oversight down does not hold Students", below.*

So the shared-box rules above that let Oversight yield, wait for an idle Answer lane, be
cancelled by a Student's arrival, or drain after class no longer apply. The in-process count of
Student requests and the `flock` stay useful for the Live view and for refusing a second
process. lib-f24.10 still keeps any unscreened exchange through the Purge, as a safety net that
should not be needed.

**Tests are deterministic and use fakes.** A fake OpenAI server runs each request from a
script (prefill gate, tokens, per-token gate) and is driven by `asyncio.Event`s, not by
sleeps. It records start, first token, end, and disconnect against an injected clock. The
gate takes the clock and its quiet period as parameters. Overlap assertions read the fake's
interval log. One test uses a real loopback socket (uvicorn on port 0) to prove that
cancelling the Oversight task closes the connection, because only a closed connection frees
the server's slot. The real-server bound (≤ 2 s) is measured once by hand on the target
Install hardware, not in CI.

## Addendum: Oversight down does not hold Students

Decided 2026-10-25 by the owner (lib-f24.70): "human intervention is async". This supersedes
the "When Oversight is down" rule above. Making Students wait at "one moment" until a
Librarian notices and chooses ties the class to the slowest step, an adult's reaction, while
the Watchlist, the floor every Install has, keeps running regardless.

- **Carry on at once with the Watchlist alone.** When a screen fails (a connection error, a
  timeout, or two unparseable replies), that message is released and marked
  `screening = watchlist_alone`, and so is every exchange admitted while Oversight stays down.
  The Card's next message is admitted as soon as its answer ends, as it would be with
  Oversight off.
- **The adults are told, and act when they can.** The Live view shows that screening is
  unavailable and since when. A Librarian or Stand-in can pause Sessions from there whenever
  they choose, and resume them. Pausing is never automatic unless the Install chose it: the
  `oversight_down` setting (lib-f24.77) is `carry_on` by default, and `pause` pauses Sessions
  when Oversight goes down and lifts that pause when it recovers. A pause an adult chose lifts
  only when an adult resumes.
- **Screening catches up.** The assistant keeps probing the Oversight endpoint. When it
  answers again, the exchanges admitted while it was down are screened, oldest first, and
  each Flag that results shows its raised time against the exchange's time. Until it is
  screened, such an exchange survives the Purge, like any other unscreened exchange. Live
  Students take priority over the catch-up, which runs only while no Card is awaiting a
  verdict.
- **ADR-0010 rule 3** ("each message is screened before the next one runs") therefore holds
  only while Oversight is up. While it is down, the Watchlist still screens every message
  before the model is called, as it does on every Install without Oversight.

`oversight.unavailable_seconds` goes away.
