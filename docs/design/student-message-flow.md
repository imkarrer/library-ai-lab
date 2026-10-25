# Student message flow

What happens to one Student message, from the chat box to the reply, the Live view, and the
Flag queue. Binding: ADR-0003 (Purge), ADR-0004 (Watchlist and Oversight), ADR-0006
(intranet only), ADR-0010 (Watch and Alarm), ADR-0011 (Supportive reply).

**Short answer to "can they keep prompting?"** Yes, in every case except three: nobody is on
Watch, Oversight hasn't yet returned its verdict on their previous message, or the Session
has ended. A Flag never stops a Session. Not even a high-severity one does that: ADR-0010
rejected pausing on an Alarm because it would punish the other Students and tell the room
something happened. An adult acts in person instead. The [table below](#can-a-student-keep-prompting)
gives every case.

## The checks, in order

Every message passes the same gates, in this order. A gate that refuses stops the message
there.

```mermaid
flowchart TD
    A[POST /ask with the Session cookie] --> B{Session valid?<br/>Card not expired or Revoked,<br/>not idle past the limit}
    B -- no --> B1[Card refusal or<br/>'scan your card again']
    B -- yes --> C{Anyone on Watch?}
    C -- no --> C1[Watchlist still runs.<br/>Otherwise the paused message.<br/>No model call]
    C -- yes --> D{Oversight on, and the previous<br/>message not yet screened?}
    D -- yes --> D1[409 'one moment'<br/>Nothing is checked or recorded]
    D -- no --> E[Record the exchange<br/>Live view shows the question]
    E --> F{Watchlist match?}
    F -- high --> F1[Supportive reply + Flag + Alarm<br/>No Catalog, no model]
    F -- low --> F2[Flag, silent to the Student]
    F -- none --> G
    F2 --> G[Catalog search + Answer lane<br/>Grounded answer streams back]
    G --> H{Oversight on?}
    H -- yes --> H1[Verdict recorded. A concern<br/>raises a Flag, silent to the Student.<br/>The next message is admitted]
    H -- no --> I[Done. The next message<br/>is admitted at once]
```

| Gate | Built by | On main? |
|---|---|---|
| Session cookie, Card expiry and Revoke | lib-f24.1, lib-75j.3 | yes |
| Idle limit | lib-f24.60, lib-f24.61 | no |
| Watch gate | lib-793.2, lib-793.3 | no |
| "One moment" while screening | lib-f24.54, lib-f24.56 | no |
| Exchange recorded on arrival | lib-f24.34 | no: today it is recorded after the answer |
| Watchlist, Flag, Supportive reply | lib-f24.35, lib-f24.36, lib-f24.37 | no |
| Catalog search and Grounded answer | lib-f24.3, lib-f24.4 | yes |
| Oversight verdict | lib-f24.52 to lib-f24.55 | no |
| Alarm | lib-ppv.1 | no |

## 1. No match: the common case

Most messages on most Installs. The Watchlist finds nothing, the answer streams, and the
Student can ask again at once.

```mermaid
sequenceDiagram
    autonumber
    actor S as Student
    participant P as Chat page
    participant A as Assistant /ask
    participant DB as SQLite
    participant W as Watchlist
    participant C as Catalog
    participant AL as Answer lane
    participant LV as Live view (Librarian)

    S->>P: types a question, presses Ask
    P->>A: POST /ask with the HttpOnly session cookie
    A->>DB: Session and Card still valid? Anyone on Watch?
    DB-->>A: yes, yes
    A->>DB: start_exchange: question, Class label, Card number
    DB-->>LV: new row appears (SSE), Class label and Card number, never a name
    A->>W: match(question)
    W-->>A: no entries
    A->>C: search(question, k=4)
    C-->>A: Records
    A->>AL: chat/completions, stream, Records as context
    loop each token
        AL-->>A: token
        A-->>P: token
    end
    A-->>P: Citation lines
    A->>DB: finish_exchange: answer, Citations
    P-->>S: answer with Citations, under "This can be wrong, check the source."
    Note over S,P: The Ask box is free again: the next message starts at step 1
```

## 2. Low-severity match

The Student sees nothing different. The Flag waits in the Flag queue for an adult. There is
no Alarm and no sound: the queue's count goes up (ADR-0010, "What raises one").

```mermaid
sequenceDiagram
    autonumber
    actor S as Student
    participant A as Assistant /ask
    participant DB as SQLite
    participant W as Watchlist
    participant AL as Answer lane
    participant FQ as Flag queue (Librarian)

    S->>A: POST /ask
    A->>DB: start_exchange
    A->>W: match(question)
    W-->>A: entry "x", low severity
    A->>DB: raise_flag(source=watchlist, entry x, Watchlist version)
    DB-->>FQ: open-Flag count +1, no exchange text in the queue
    A->>AL: Catalog search, then the Grounded answer as in flow 1
    AL-->>S: normal answer
    Note over S: Nothing shows the Student a Flag was raised.<br/>Lesson 4 has already told them adults see what is asked
```

## 3. High-severity match

The Supportive reply replaces the answer: no Catalog search and no model call. Every
matching entry raises its own Flag, and the Student gets one reply chosen by ADR-0011's
order: self-harm, threats of violence, abuse, bullying. An Alarm sounds on every watching
page. **The Session carries on.** The Student can keep typing, and each message goes through
the same checks again.

```mermaid
sequenceDiagram
    autonumber
    actor S as Student
    participant A as Assistant /ask
    participant DB as SQLite
    participant W as Watchlist
    participant WP as Watching pages (Live view, Flag queue)
    actor L as Librarian or Stand-in

    S->>A: POST /ask
    A->>DB: start_exchange
    A->>W: match(question)
    W-->>A: entry "y", high severity, category self-harm
    A->>DB: raise_flag(source=watchlist, entry y)
    A-->>S: Supportive reply for self-harm: an adult in the building, 988, 911
    A->>DB: finish_exchange: the Supportive reply is the answer
    DB-->>WP: Alarm: banner, tab title, chime every 30 s<br/>category, Class label, Card number, no Student words
    L->>WP: Acknowledge ("I'm on it")
    WP->>DB: who and when. The Flag stays open
    WP-->>WP: Alarm silenced on every page
    Note over L,S: The adult goes to "card 14" in person (escalation protocol).<br/>The product never pauses the Session for this
    S->>A: next message: the full checks again, from the top
```

## 4. With Oversight configured

Oversight screens each message beside its answer, on its own Lane (ADR-0004, "Screening is
real time and ordered per Session"). The Student gets the answer as fast as without
Oversight. What changes is the **next** message: it is not admitted until the verdict on
this one is recorded. Another Session never waits on this one.

```mermaid
sequenceDiagram
    autonumber
    actor S as Student
    participant P as Chat page
    participant A as Assistant /ask
    participant DB as SQLite
    participant AL as Answer lane
    participant OL as Oversight lane
    participant FQ as Flag queue

    S->>P: message 1
    P->>A: POST /ask
    A->>DB: start_exchange, screening = oversight, screened_at empty
    Note over A: Watchlist first, as in flows 1 to 3
    par at the same moment
        A->>AL: Grounded answer request
        AL-->>P: answer streams
    and
        A->>OL: screen(message 1 only)
    end
    S->>P: message 2, before the verdict
    P->>A: POST /ask
    A->>DB: message 1 screened yet?
    DB-->>A: no
    A-->>P: 409 "one moment": not checked, not recorded
    P-->>S: "One moment..." with their text still in the box
    OL-->>A: verdict on message 1
    A->>DB: store verdict, screened_at
    alt verdict names a category
        A->>DB: raise_flag(source=oversight, reason)
        DB-->>FQ: Flag (Alarm if high), marked as raised by Oversight with its time
        Note over S: No Supportive reply: the answer has already streamed (ADR-0004)
    else no concern
        Note over A: nothing more
    end
    P->>A: retry message 2 (every 2 s)
    A-->>P: admitted: the full checks from the top
```

The gap is usually a second or two, because screening one short message is fast next to
writing an answer. An Oversight call is never cancelled to make room for another Student.

## 5. Oversight configured but down

The next message waits instead of going unscreened. After `oversight.unavailable_seconds`
(default 30), the Librarian decides.

```mermaid
sequenceDiagram
    autonumber
    actor S as Student
    participant A as Assistant /ask
    participant OL as Oversight lane
    participant LV as Live view
    actor L as Librarian

    A->>OL: screen(message 1)
    OL--xA: connection error or timeout (after one retry)
    A->>LV: "Screening is unavailable"
    S->>A: message 2
    A-->>S: 409 "one moment" (message 1 is still unscreened)
    Note over A,LV: unavailable_seconds pass on the clock
    A->>LV: offer: pause Sessions, or continue on the Watchlist alone
    alt Librarian chooses pause
        L->>LV: pause
        S->>A: message 2 retry
        A-->>S: 503 paused message
    else Librarian chooses Watchlist alone
        L->>LV: Watchlist alone
        S->>A: message 2 retry
        A-->>S: admitted. The exchange is marked screening = watchlist_alone
    end
    OL-->>A: first verdict after recovery
    A->>LV: back to normal
```

Message 1 stays unscreened until Oversight recovers. The Purge keeps it until then
(lib-f24.58).

## 6. Nobody on Watch

Students chat only while an adult is on Watch (ADR-0010). The chat page follows the Watch
state and disables the box. A message that races the lapse still gets the Watchlist and,
for a high-severity match, the Supportive reply. The safety net never switches off.

```mermaid
sequenceDiagram
    autonumber
    actor S as Student
    participant P as Chat page
    participant A as Assistant /ask
    participant W as Watchlist
    participant DB as SQLite

    Note over P: Watch status shows nobody on Watch. Input disabled, the unsent text kept
    S->>P: a message sent anyway (a race with the lapse)
    P->>A: POST /ask
    A->>DB: anyone on Watch?
    DB-->>A: no
    A->>W: match(question)
    alt high severity
        A->>DB: raise_flag, marked raised unwatched
        A-->>S: Supportive reply
    else low severity
        A->>DB: raise_flag, marked raised unwatched
        A-->>S: paused message
    else no match
        A-->>S: paused message. No model call
    end
    Note over DB: An unacknowledged high-severity Flag sounds its Alarm<br/>at the next Start watch, before anything else
```

## Can a Student keep prompting?

| Situation | Next message | Why |
|---|---|---|
| No match | Admitted at once (once the verdict lands, with Oversight on) | Flow 1 |
| Low-severity Watchlist Flag | Admitted. The Student never learns of the Flag | Flow 2 |
| High-severity Watchlist Flag | Admitted. Every message is checked again | Flow 3. ADR-0010 rejected pausing on an Alarm |
| Oversight Flag | Admitted once the verdict is recorded, which is the moment the Flag is raised | Flow 4 |
| Oversight still screening the previous message | "One moment" until the verdict | Flow 4, ADR-0004 |
| Oversight down | Waits. After 30 s the Librarian chooses pause or Watchlist alone | Flow 5 |
| Nobody on Watch | Paused message. Watchlist and Supportive reply still run | Flow 6, ADR-0010 |
| Card Revoked, or Batch expired (end of the school day at the latest) | Refused: "this card no longer works, ask your teacher" | [Session lifecycle](session-lifecycle.md) |
| Idle past the Librarian's limit (default 20 min) | Refused: "scan your card again". The Card still works | [Session lifecycle](session-lifecycle.md) |
| Student pressed Finished | That device's Session ends. The Card still works | [Session lifecycle](session-lifecycle.md) |

## Open questions found while drafting

Each one needs a decision before the bead that meets it is built.

1. **Two messages at once without Oversight.** Today the chat page doesn't disable Ask while
   an answer streams, and `/ask` will start a second answer for the same Session in
   parallel. With Oversight off, nothing in the design orders a Session's messages. Should a
   Session have at most one message in flight whether or not Oversight is on? That would
   also stop one Card from hogging the box ADR-0009 sizes for a class.
2. **The same high-severity phrase, repeated.** A Student who types it three times raises
   three Flags and, under lib-ppv.1 as written, three Alarms. Does an open, unacknowledged
   Alarm for the same Card absorb the next one, or does each Flag chime?
3. **Oversight on a message that already got a Supportive reply.** lib-f24.54 still screens
   it, so ordering stays uniform, which may raise a second Flag on the same exchange. Keep
   that, or skip Oversight when the Watchlist already matched high?
4. **What "one moment" looks like when it lasts.** With Oversight down, a Student can sit at
   "one moment" for up to `unavailable_seconds` before the Librarian is even asked. Should the
   page say more after some seconds, or is the paused message the only other state?
