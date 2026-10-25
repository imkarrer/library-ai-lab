# Session lifecycle

How one Card's Session starts, what pauses it, what ends it, and what happens to its words
afterwards. Binding: ADR-0002 (minting and Registration), ADR-0003 and its addendum (Purge,
Tokens never in a URL), ADR-0010 (Watch, Cards last one school day, supervision mode).

Students use their own Chromebooks (owner, 2026-10-25), so by default a Session lasts until
its Card stops working or the Student ends it. A shared library computer is covered by the
End session button and by a new sign-in ending that device's previous Session.

## States

```mermaid
stateDiagram-v2
    [*] --> Registered: Teacher mints the Batch and registers its Token hashes
    Registered --> Refused: scan after expiry or Revoke
    Registered --> Paused: scan while the supervision mode holds Students (no Session yet)
    Paused --> Registered: the hold lifts (Start watch, or a review), scan again
    Registered --> Active: scan while the mode lets Students chat
    Active --> Waiting: Oversight on, message sent
    Waiting --> Active: verdict recorded
    Active --> PausedInSession: the mode starts holding Students (the last Watch ends, a review falls overdue)
    PausedInSession --> Active: the hold lifts
    Active --> Ended: End session, another Card signs in on this device, idle limit if set, Revoke, or Batch expiry
    Waiting --> Ended: Revoke or Batch expiry
    PausedInSession --> Ended: End session, idle limit if set, Revoke, or Batch expiry
    Ended --> Active: same Card scanned again, if it still works
    Ended --> [*]
    Refused --> [*]
```

| State | What the Student sees | Built by | On main? |
|---|---|---|---|
| Refused | "This card has stopped working. Ask your teacher for a new one." Same words for expired and Revoked, so a Revoke is never announced | lib-f24.1, lib-f24.81 | old wording: yes |
| Paused (at sign-in) | "The Library Assistant is taking a break until the librarian is ready." The Card stays valid | lib-793.3, lib-f24.78 | no |
| Active | The chat page | lib-f24.1, lib-f24.4 | yes |
| Waiting | "One moment..." with their text kept | lib-f24.54, lib-f24.56 | no |
| PausedInSession | The same break message, input disabled, unsent text kept | lib-793.3 | no |
| Ended | End session: "Session ended. You can close this page." Ended on this device or idle: "This session ended. Scan your card again." Revoke or expiry: the Card refusal | lib-f24.1, lib-f24.81 to lib-f24.83, lib-f24.61 | "Finished" wording: yes. The rest: no |

**A Flag is not a state.** Neither a Watchlist nor an Oversight Flag moves a Session
anywhere. An adult who wants a Student to stop can Revoke that Card from the Session detail
page in the Live view (lib-f24.49). The other Cards in the Batch keep working.

## Sign-in

The Token never reaches the server in a URL (ADR-0003 addendum). The QR code carries it in
the fragment, which browsers don't send, and the page posts it once.

```mermaid
sequenceDiagram
    autonumber
    actor S as Student
    participant B as Browser
    participant A as Assistant
    participant DB as SQLite

    S->>B: scans the Card: /card#t=TOKEN
    B->>A: GET /card (no fragment sent)
    A-->>B: card page
    B->>A: POST /card with the Token in the body (and any old session cookie)
    A->>DB: Token hash registered? Batch expired? Revoked?
    alt dead Card
        A-->>B: 403 "This card has stopped working. Ask your teacher for a new one."
    else the supervision mode holds Students (lib-793.3)
        A-->>B: paused page. No Session row. The same scan works later
    else valid
        opt this browser already holds a Session (a shared computer, lib-f24.82)
            A->>DB: end that previous Session
        end
        A->>DB: new Session: only the hash of its id is stored
        A-->>B: HttpOnly, SameSite=Strict cookie that expires with the Card
        B->>B: strip the fragment from the address bar
        B->>A: GET /chat
    end
```

Every later request rechecks the Card row. So a Revoke, or the Batch reaching its expiry,
ends the Session at the next request, whatever the cookie says. The cookie's own expiry
(lib-f24.82) only means the browser drops it at the same moment. No Session outlives the
school day, because Registration refuses an expiry past it (lib-f24.44).

## What ends a Session

| Cause | Who | Effect on the Card | Built by |
|---|---|---|---|
| End session button | Student | None: the Card can start a new Session | lib-f24.1 (on main as "Finished"), lib-f24.81 |
| Another Card signs in on the same device | The next Student at a shared computer | None: the first Card still works on its own device | lib-f24.82 |
| Idle past a limit, if the Librarian sets one (default: none) | The Librarian | None: scan again | lib-f24.60, lib-f24.61 |
| Revoke this Card | Librarian, from the Session detail page in the Live view | Dead for good | lib-f24.49 (the registration-key route is on main) |
| Revoke the Batch | Librarian, from the Session detail page in the Live view | Every Card in the Batch dead | lib-f24.49 |
| Batch expiry | Set at minting, no later than the end of the school day | Dead | lib-f24.1 (on main), lib-f24.44 |

## What happens to the words afterwards

```mermaid
sequenceDiagram
    autonumber
    participant DB as SQLite
    participant PG as Purge (in the process)
    actor L as Librarian

    Note over DB: During the day: transcripts, with Class label and Card number, never a name
    PG->>PG: end of the school day (or at startup after a missed one)
    PG->>DB: delete every transcript from before the day's end
    Note over PG,DB: except: an open Flag's exchange, a Hold's scope (lib-a2e.1),<br/>a message Oversight has not yet screened
    L->>DB: close a Flag (after Export if the school needs the exchange)
    PG->>DB: next Purge deletes that exchange. The Flag and its history stay flags.history_days
    PG->>DB: Token hashes of expired or Revoked Batches go too (lib-75j.1)
```

| Step | Built by | On main? |
|---|---|---|
| Daily Purge, the startup run, open-Flag exception | lib-f24.40 to lib-f24.43 | no |
| Unscreened exception | lib-f24.58 | no |
| Holds | lib-a2e.1 | no |
| Flag history, Export, close | lib-ce5.1 | no |
| Token hashes and Flag histories swept | lib-75j.1 | no |
| No copies in logs, WAL, or backups | lib-75j.2 | no |
