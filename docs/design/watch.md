# Watch and supervision

How the adults' presence is known, and what it does to Students. Binding: ADR-0010 and its
"supervision mode" amendment, ADR-0004 (the Watchlist never switches off).

A **Watch** is an adult saying "I'm watching" on purpose, with the server checking they're
still there. The **supervision mode** is the Librarian's setting for how much that matters:

| Mode | Students can chat | Adults |
|---|---|---|
| **Live** (default) | only while at least one Watch is on | stay on the Live view or Flag queue |
| **Periodic review** | any time in the school day; optionally paused when a review is overdue by more than a set time (default: never) | review the Flag queue every `review_every_minutes` (default 120) and press Mark reviewed |
| **Off** | any time in the school day | the school's own policy |

The Watchlist, the Supportive reply, and Flags run in every mode. In every mode, an
unacknowledged high-severity Alarm sounds on the next staff page anyone opens.

```mermaid
flowchart TD
    M{Supervision mode} -- Live --> L{Anyone on Watch?}
    L -- yes --> OPEN[Students chat]
    L -- no --> HELD[Students see the paused message.<br/>Watchlist and Supportive reply still run]
    M -- Periodic --> P{Review overdue by more than<br/>the pause setting? 0 = never}
    P -- no --> OPEN
    P -- yes --> HELD
    M -- Off --> OPEN
```

## Who can watch

The Librarian, or a staff account the Librarian has made a Stand-in. A Counselor alone can't:
they see only Escalated Flags, so they'd miss a new high-severity one. One Watch covers the
whole Install, since there's one supervised class at a time (ADR-0009). Several adults can be
on Watch at once, and Students carry on while any one of them is.

## Start watch and the heartbeat

Opening the page isn't enough: Start watch is a button. The press is the adult saying so on
purpose, and it's the user gesture browsers require before a page may play sound, so the
button plays the chime once as a sound check.

```mermaid
sequenceDiagram
    autonumber
    actor L as Librarian or Stand-in
    participant LV as Live view or Flag queue
    participant A as Assistant
    participant DB as SQLite

    L->>LV: sign in, open the page
    LV->>A: GET /staff/live/events (SSE, held open)
    L->>LV: Start watch
    LV->>LV: play the chime once (sound check)
    LV->>A: start watch
    A->>DB: Watch on: account, started_at
    A-->>LV: replay any unacknowledged high-severity Alarm first
    loop every 20 s
        A-->>LV: ping
        LV->>A: heartbeat
        A->>DB: last_heartbeat_at = now
    end
    Note over LV: A background tab still answers, and the chime<br/>is heard from any tab, so it still counts
```

## Lapse, and coming back

The Watch lapses when no heartbeat has arrived for `watch_grace_seconds` (default 90). A
dropped stream doesn't end it at once, so a reconnect doesn't pause the class. A laptop that
sleeps stops answering, and its Watch lapses. That's intended: the Students' paused page is
how the adult finds out.

```mermaid
sequenceDiagram
    autonumber
    actor L as Librarian
    participant LV as Live view
    participant A as Assistant
    actor S as Student

    Note over LV: the laptop sleeps, no heartbeats
    A->>A: 90 s with no heartbeat: Watch lapsed
    Note over A: Live mode and no other Watch: Students are held
    S->>A: POST /ask
    A-->>S: paused message (Watchlist still checked: a high match still gets the Supportive reply,<br/>and its Flag is marked raised unwatched)
    L->>LV: wakes the laptop, presses Start watch
    A-->>LV: Alarm replay for the unacknowledged raised-unwatched Flag, before anything else
    A-->>S: the chat page reopens
```

## End watch

End watch, signing out, and the staff session expiring all end a Watch. If it's the last
Watch, an on-purpose end waits for any message whose Oversight screen is still in flight, so
no message is left unscreened with nobody present (ADR-0010 rule 3). A lapse can't wait, so a
Flag that lands after it is marked raised unwatched and replays at the next Start watch.

```mermaid
sequenceDiagram
    autonumber
    actor L as Librarian
    participant LV as Live view
    participant A as Assistant
    participant OL as Oversight lane

    L->>LV: End watch (the last Watch)
    LV->>A: end watch
    A->>A: any Card awaiting a verdict?
    alt yes
        A-->>LV: "Finishing screening..."
        OL-->>A: the last verdicts
    end
    A->>A: Watch off. Live mode: Students are held
    A-->>LV: watch ended
```

## Periodic review

In periodic mode nobody holds a heartbeat. The Flag queue shows when it was last reviewed and
when the next review is due, and an adult presses Mark reviewed after working through it.

```mermaid
sequenceDiagram
    autonumber
    actor L as Librarian
    participant FQ as Flag queue
    participant A as Assistant
    actor S as Student

    S->>A: chats through the morning (no Watch needed)
    A->>A: a high-severity Flag: the Student gets the Supportive reply at once
    Note over A: nobody is on a staff page: the Alarm waits
    L->>FQ: opens the Flag queue (10:30, review due 10:30)
    A-->>FQ: Alarm for the unacknowledged Flag, first
    L->>FQ: Acknowledge, work the Flags, press Mark reviewed
    A-->>FQ: "Last reviewed 10:34 by the Librarian, next due 12:34"
    opt the pause setting is on and nobody reviews by 12:34 + the pause
        A-->>S: paused message until the next review
    end
```

The cost of a long interval is the time a disclosure can sit unseen. The Student always gets
the Supportive reply at once; the adults learn of it at the next review. The escalation
protocol template says who reviews and how often (lib-f24.80).

## Settings

All on the Librarian's settings page, each change recorded with who and when (lib-f24.78):

| Setting | Default |
|---|---|
| Supervision mode | Live |
| Review every (periodic) | 120 min |
| Pause Students when a review is overdue by (periodic) | never |
| Heartbeat grace | 90 s |
| Alarm chime / repeat | on / every 30 s |
| When Oversight is down | carry on with the Watchlist alone |
| Session idle limit | none (Students use their own Chromebooks) |

## Beads

| Piece | Bead |
|---|---|
| Settings and the change log | lib-f24.60, lib-f24.78 |
| Watch state, heartbeat, grace | lib-793.2 |
| The gate on sign-in and asks, by mode | lib-793.3 |
| Stand-in role | lib-793.1 |
| Mark reviewed, last and next review | lib-f24.79 |
| Alarm, chime, replay | lib-ppv.1 |
| Escalation protocol per mode | lib-f24.80 |
