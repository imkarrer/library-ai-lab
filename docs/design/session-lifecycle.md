# Session lifecycle

How one Card's Session starts, what pauses it, what ends it, and what happens to its words
afterwards. Binding: ADR-0002 (minting and Registration), ADR-0003 and its addendum (Purge,
Tokens never in a URL), ADR-0010 (Watch, Cards last one school day).

## States

```mermaid
stateDiagram-v2
    [*] --> Registered: Teacher mints the Batch and registers its Token hashes
    Registered --> Refused: scan after expiry or Revoke
    Registered --> Paused: scan, nobody on Watch (no Session yet)
    Paused --> Registered: an adult presses Start watch, scan again
    Registered --> Active: scan while someone is on Watch
    Active --> Waiting: Oversight on, message sent
    Waiting --> Active: verdict recorded
    Active --> PausedInSession: the last Watch ends or lapses
    PausedInSession --> Active: an adult starts a Watch
    Active --> Ended: Finished, idle limit, Revoke, or Batch expiry
    Waiting --> Ended: Revoke or Batch expiry
    PausedInSession --> Ended: idle limit, Revoke, or Batch expiry
    Ended --> Active: same Card scanned again, if it is still valid
    Ended --> [*]
    Refused --> [*]
```

| State | What the Student sees | Built by | On main? |
|---|---|---|---|
| Refused | "this card no longer works, ask your teacher" | lib-f24.1 | yes |
| Paused (at sign-in) | "The Library Assistant is taking a break until the librarian is ready." The Card stays valid | lib-793.3 | no |
| Active | The chat page | lib-f24.1, lib-f24.4 | yes |
| Waiting | "One moment..." with their text kept | lib-f24.54, lib-f24.56 | no |
| PausedInSession | The same break message, input disabled, unsent text kept | lib-793.3 | no |
| Ended | Finished: "You can close this page". Idle: "scan your card again". Revoke or expiry: the Card refusal | lib-f24.1, lib-f24.61 | Finished, Revoke, expiry: yes. Idle: no |

**A Flag is not a state.** Neither a Watchlist nor an Oversight Flag moves a Session
anywhere. An adult who wants a Student to stop can Revoke that Card from the Live view
(lib-f24.49). The other Cards in the Batch keep working.

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
    B->>A: POST /card with the Token in the body
    A->>DB: Token hash registered? Batch expired? Revoked?
    alt dead Card
        A-->>B: 403 "this card no longer works, ask your teacher"
    else nobody on Watch (lib-793.3)
        A-->>B: paused page. No Session row. The same scan works later
    else valid
        A->>DB: new Session: only the hash of its id is stored
        A-->>B: HttpOnly, SameSite=Strict cookie, no Max-Age
        B->>B: strip the fragment from the address bar
        B->>A: GET /chat
    end
```

Every later request rechecks the Card row. So a Revoke, or the Batch reaching its expiry,
ends the Session at the next request. No Session outlives the school day, because
Registration refuses an expiry past it (lib-f24.44).

## What ends a Session

| Cause | Who | Effect on the Card | Built by |
|---|---|---|---|
| Finished button | Student | None: the Card can start a new Session | lib-f24.1 (on main) |
| Idle past the limit (default 20 min, 0 = none) | The Librarian sets the limit | None: scan again | lib-f24.60, lib-f24.61 |
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
