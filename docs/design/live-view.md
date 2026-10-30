# Live view

The Librarian's running view of what Sessions are asking (`CONTEXT.md`), and the place
observation happens, which is why same-day retention costs nothing (ADR-0003). It has two
levels: an **overview** of every active Session, and a **Session detail** page you click
into to watch one conversation as it happens. Binding: ADR-0002 (no Card-to-Student link),
ADR-0007 (our own thin UI), ADR-0010 (Watch, Alarm), ADR-0003 addendum (`no-store`, no
copies).

Decided 2026-10-25 by the owner: the overview and click-through are the Live view for every
Install, not a demo mode. The words are shown. A Librarian locks their workstation when
they step away, as they would with any pupil record on screen.

## What each level shows

| | Overview `/staff/live` | Session detail `/staff/live/sessions/{n}` |
|---|---|---|
| Who | Librarian (and Stand-in, lib-793.1) | Same |
| One row per | Active Session, most recent activity first | Exchange, oldest first |
| Shows | Class label, Card number, time since last activity, message count, latest question (80 chars), Flag marker | Each question, its answer streaming in as it's written, Citations |
| Controls | **Start watch / End watch** only (ADR-0010): nothing that changes a Session, so it's safe to leave on screen or share | Revoke this Card, Revoke the Batch, each behind a confirm |
| Never shows | A name, a Token or hash, Roster data, a Flag's category or reason | The same |

`n` is the Session's row number in the database: opaque, and never the Session's hash.

```mermaid
flowchart LR
    O[Overview<br/>a tile per active Session<br/>only Start watch] -- click a tile --> D[Session detail<br/>questions, streaming answers,<br/>Citations]
    D -- back --> O
    D -- Revoke, confirmed --> R[Card or Batch Revoked<br/>its next ask is refused]
    R --> O
```

## How it stays live

Everything runs in the one process (ADR-0008), so `/ask` hands each event straight to an
in-process bus, and every open Live view page holds one server-sent event stream. Nothing
polls the database, and token text never goes anywhere but the open stream and, at the end,
the transcript.

```mermaid
sequenceDiagram
    autonumber
    actor L as Librarian
    participant LV as Live view page
    participant A as Assistant
    participant Bus as LiveBus (in process)
    actor S as Student

    L->>LV: open /staff/live
    LV->>A: GET /staff/live (tiles rendered)
    LV->>A: GET /staff/live/events (SSE, held open)
    A->>Bus: subscribe
    S->>A: POST /ask "what do snow leopards eat?"
    A->>Bus: question {session n, Class label, Card number, question}
    Bus-->>LV: event: question
    LV->>LV: card 2's tile moves to the top, latest question updated
    L->>LV: click card 2
    LV->>A: GET /staff/live/sessions/n (exchanges so far)
    loop each token of the answer
        A->>Bus: token {session n, text}
        Bus-->>LV: event: token
        LV->>LV: append to the answer in progress
    end
    A->>Bus: answer {session n, final answer, Citations}
    Bus-->>LV: event: answer, replaces the streamed text
    Note over A,LV: a `ping` event every 20 s keeps the stream open,<br/>and the page answers each with a Watch heartbeat (lib-793.2).<br/>The Alarm rides this stream too: alarm, silenced, flag_count (lib-ppv.1),<br/>and the Open Flags panel: flag, flag_closed (lib-4m7)
```

A high-severity Flag on a watching page raises the Alarm banner without any words
(ADR-0010), and the Session's tile gets a Flag marker by severity only. The words are one
click away, on the Session detail page or the Flag's own page.

Every open Flag, low-severity included, is also a row in the **Open Flags** panel at the
top of the overview and the Session detail (ADR-0010 amendment, lib-4m7): severity, Class
label, Card number, time, and source, high-severity first, each a link to the Flag. Rows
arrive and leave over the same stream (`flag`, `flag_closed`), and the tile marker follows
them, so nothing waits for a refresh. Like the tiles, a row never shows the category.

One exception to "never shows a Flag's category": the Alarm banner names it ("Alarm: high
self-harm (watchlist)"), as ADR-0010's "What it shows" says. The banner appears only for a
high-severity Flag and only until it is Acknowledged; Acknowledge before sharing the screen.

## The conference demo

Two volunteers chat on their phones while the presenter screen-shares the overview. The
demo uses the Live view exactly as a school would (lib-f24.63's runbook has the steps):

```mermaid
sequenceDiagram
    autonumber
    actor P as Presenter (Librarian)
    participant Scr as Shared screen: Live view
    actor V1 as Volunteer 1
    actor V2 as Volunteer 2
    participant A as Assistant on the M5

    P->>A: mint 3 Cards, "Conference demo", until the end of the talk
    P->>Scr: sign in, open /staff/live, Start watch, share the screen
    V1->>A: scan Card 1 and ask about their favourite animal
    V2->>A: scan Card 2 and ask about theirs
    A-->>Scr: two tiles appear
    P->>Scr: click Volunteer 1's tile
    A-->>Scr: the answer streams in with its Citations
    V2->>A: "library demo flag" (the demo-only Watchlist entry)
    A-->>V2: Supportive reply
    A-->>Scr: Alarm banner (no words), Flag marker on card 2's tile
    P->>Scr: Acknowledge, then Revoke card 2 from its Session page
    V2->>A: one more question
    A-->>V2: "This card has stopped working. Ask your teacher for a new one."
```

Two volunteers is about what the M5 serves comfortably (the owner's estimate).
lib-f24.74 and lib-f24.75 measure it, and if a supervised class needs more than ADR-0009
assumes, an ADR-0009 addendum records the real number.

## Beads

| Piece | Bead | Stage |
|---|---|---|
| Overview tiles | lib-f24.47 | local |
| Session detail | lib-f24.71 | local |
| Live updates (tiles, detail) over SSE | lib-f24.48 | frontier |
| Answers stream token by token | lib-f24.72 | frontier |
| Revoke from the Session detail | lib-f24.49 | local |
| Flag marker on tiles | lib-f24.73 | local |
| Open Flags panel, live tile markers | lib-4m7 | frontier |
| Conference runbook | lib-f24.63 | frontier |
| Capacity: probe, then measure on the M5 | lib-f24.74, lib-f24.75 | local, human |
