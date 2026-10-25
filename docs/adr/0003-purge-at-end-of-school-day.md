# Purge transcripts at the end of each school day

Every transcript is deleted at the end of the school day it was made, except those attached
to an open Flag, which stay until an adult closes the Flag. The Live view is where
observation happens, so same-day retention costs the Librarian nothing, and it keeps the
pupil-records exposure (ADR-0001) close to zero. A longer window can become a setting, but
the shipped default stays a single day and the setting must document the trade-off.

Supersedes the 30-45 day window in the original single-district plan.

## Addendum: holds, Flag lifecycle, and other copies

Decided 2026-10-25 (lib-a2e, lib-ce5, lib-75j). The Purge now has three exceptions instead of
one: an open Flag, a Hold, and an Export the school files in its own records.

### Holds

FERPA forbids destroying an education record "if there is an outstanding request to inspect
and review" it ([34 CFR 99.10(e)](https://www.ecfr.gov/current/title-34/section-99.10)).
Wis. Stat. [19.35(5)](https://docs.legis.wisconsin.gov/document/statutes/19.35) forbids
destroying a requested record until the request is granted, or for 60 days after a denial
(90 for a committed or incarcerated requester), and for as long as a 19.37 court action on it
runs. A Purge that cannot pause breaks both. So:

- **A Hold names a scope, not a Student**: one or more Class labels (or all of them), a date
  range, and, when the Teacher has supplied them, Card numbers. The assistant knows nothing
  else to match on, and a request names a Student, so the custodian translates it through
  the Roster. Class label and dates are enough to set a Hold within minutes, before the
  Card numbers are known. A Hold on one Flag would miss the same day's unflagged
  transcripts, and a Hold on a whole day would keep every class's transcripts.
- **It holds everything in scope**: transcripts, Flags, Flag histories, and the Batch's
  Class label, Card numbers, and expiry, never its Token hashes. An end date in the future
  also holds records made until then, for a preservation request that looks forward.
- **Only the Librarian sets or lifts one**, with a reason kind (inspection request, public
  records request, court order or subpoena, law enforcement or CPS preservation, other) and
  a reference that must not name anyone. A Counselor sees only Escalated Flags, and a Hold
  would show them more. Holds are never edited: to narrow one, set the narrower Hold, then
  lift the broad one.
- **A Hold never expires on its own.** When the law releases a record depends on things the
  assistant cannot see: a grant, a denial plus 60 days, a court order. A Hold older than
  `holds.review_days` (default 30) is marked for review instead.
- **The Purge skips held records** and reports how many it kept under how many Holds. After a
  lift, the next Purge applies the ordinary rules, so a record whose day has passed goes then.
- **It is shown** on a Holds page (scope, reason, age, what it holds), as a count on the Flag
  queue, and as a "held" mark on each held Session and Flag. The Holds page can Export the
  held transcripts, because a parent's inspection needs them in hand.
- **A Hold cannot bring anything back.** A record deleted on schedule before the request
  arrived is not withheld (retention policy 5.1). The Hold must be set before that day's
  Purge.

### Flag lifecycle

- **Every Flag has a Flag history**, append-only: raised (by which Watchlist entry and version,
  or by Oversight), viewed (each time a staff account opens the exchange), escalated,
  exported, closed, and reopened, each with the account and the time. Escalate, close, and
  reopen require a reason. The Flag queue lists Flags without their exchange text, so
  "viewed" means someone read the words.
- **Export before close.** A Flag's page can Export its exchange, Flag, and history as a
  plain-text file the school files in its own records, where its pupil-records rules apply.
  The assistant keeps no copy. Closing shows when the next Purge will delete the exchange.
  Closing a high-severity Flag with no Export needs an explicit "the school does not need
  this exchange". A closed Flag can be reopened until the Purge deletes its exchange.
- **A Flag may stay open as long as an adult needs it**, with no hard limit and no
  auto-close, because closing destroys the exchange and only an adult knows whether the work
  is done. A Flag open longer than `flags.overdue_days` (default 7 days, about the escalation
  protocol's five school days) is marked overdue in the queue and counted in the Purge
  report. Open Flags are not storage: a request to keep an exchange is a Hold, and the
  school's own copy is an Export.
- **The history outlives the exchange, briefly.** At the first Purge after close, the exchange
  is deleted. The Flag and its history, which name a Class label and Card number and so are a
  pupil record, are kept `flags.history_days` (default 90) after close, then deleted. That is
  long enough to answer "who saw this and what was done" for a term, and well inside
  118.125(3)'s one year after the pupil leaves. FERPA does not require it: 34 CFR 99.32(d)
  exempts disclosures to school officials from the disclosure record, so the history is for
  accountability, and short.

### Other copies

The Purge is only as good as the copies it cannot see.

- **Token hashes are deleted at the first Purge after their Batch expires or is Revoked**
  (or their Card is Revoked). An expired hash opens nothing, so deleting it destroys nothing
  an inspection needs. The Batch's Class label, Card numbers, and expiry stay while a Session,
  Flag, or Hold refers to them.
- **Tokens never reach the server in a URL.** A Card's URL carries the Token in the fragment
  (`/card#t=...`), which browsers do not send. The page posts it once, gets an HttpOnly,
  SameSite=Strict cookie that expires with the Card (amended 2026-10-25, lib-f24.82; it was
  "no Max-Age"), and strips the fragment. So no access log, proxy log,
  or Referer can hold a raw Token. The device's browser history may keep the Card URL; the
  Batch's expiry makes it useless.
- **The app controls, and tests**: no log line carries a Token, a hash, or message text (its
  own access log records the route template, status, and duration, never the raw path or
  query); every page that shows a transcript sends `Cache-Control: no-store`; SQLite runs with
  `secure_delete = ON` and no FTS over transcripts, since FTS shadow tables keep traces; each
  Purge ends with `wal_checkpoint(TRUNCATE)`; the app makes no backups. A test plants a canary
  sentence, runs the Purge, and finds it in no log and no byte of the database, `-wal`, or
  `-shm` file.
- **The Install documents what the app cannot see**: the model server's own logs and caches
  (llama-server without `-v`, `--log-prompts-dir`, or `--slot-save-path`, and with
  `--no-slots`; llama-swap with `captureBuffer: 0`, `logToStdout: proxy`, and no file-backed
  `store`), reachable only from the assistant's host; the state directory excluded from Time
  Machine and any district backup; guest or kiosk browser profiles on shared library
  machines; and Exports deleted from Downloads once filed. A person checks these once on the
  Install's hardware, because only a real run shows what a real server writes.
