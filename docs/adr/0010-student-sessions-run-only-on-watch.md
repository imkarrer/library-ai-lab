# Student Sessions run only while an adult is on Watch, and a high-severity Flag sounds an Alarm

Proposed 2026-10-25 (lib-793, lib-ppv). Found while drafting the escalation protocol
(`docs/templates/escalation-protocol.md`, sections 3 and 8), which had to make up for both gaps
with people and a schedule.

A Flag is only as good as the adult who sees it. So the assistant answers Students only while a
Librarian or a Stand-in is **on Watch**: signed in, having pressed **Start watch** on the Live
view or the Flag queue, with that page still open and answering the server. When nobody is on
Watch, Card sign-in and every ask are refused with a calm "paused" message. While someone is on
Watch, a high-severity Flag from either source raises an **Alarm** on every watching page: a
banner that stays, a changed tab title, and a chime that repeats until an adult presses
**Acknowledge**. Nothing leaves the open browser page. No SMS, email, push service, or pager
is involved (ADR-0006).

## On Watch, concretely

- **Who can watch.** A staff account with the Librarian role or the new **Stand-in** role. The
  Counselor role alone does not count, because a Counselor sees only Escalated Flags
  (lib-f24.7), and an adult who cannot see a new un-escalated high-severity Flag is not watching
  for it. A school that wants its counselor to cover gives that account the Stand-in role too.
- **Stand-in.** A role the Librarian grants to any staff account, such as a Teacher, an
  aide, an administrator, or the counselor. A Stand-in can open the Live view and the Flag queue
  and hold a Watch. A Stand-in cannot manage accounts, Registration keys, or Install settings.
  This is the backup the protocol's "Librarian absent" row needed (section 3).
- **Starting a Watch is a deliberate act.** Opening the page is not enough. **Start watch** is a
  button, for two reasons. The adult says "I'm watching" on purpose. And the click is the user
  gesture that browsers require before a page may play sound, so the chime can be tested right
  then: the button plays it once.
- **Heartbeat.** A watching page holds the server-sent event stream that the Live view already
  uses (lib-f24.12). The server sends a ping every 20 s, and the page answers each one with a
  heartbeat request. The Watch lapses when no heartbeat has arrived for the grace period
  (default 90 s, `watch.grace_seconds`). It also lapses when the adult presses **End watch** or
  signs out, or when their staff session expires. A dropped stream does not end the Watch at
  once, so a reconnect does not pause the class. The page answers network events rather than
  its own timers, because browsers slow down timers in background tabs. A Watch in a background
  tab is still a Watch, since the chime can be heard from any tab. A laptop that sleeps stops
  answering, and its Watch lapses.
- **One Watch covers the Install.** ADR-0009 already limits use to one supervised class at a
  time, so the Install does not track which Watch covers which Batch. Several adults may be on
  Watch at once. The gate stays open while any one of them is.
- **No off switch.** No Install setting runs Student Sessions without a Watch. A developer or a
  demo presenter signs in as the Librarian and presses Start watch. Tests start a Watch
  through a fixture.
  *Superseded by "Amendment: supervision mode", below: Live is now the default, not the only
  mode.*

## What a Student sees when nobody is on Watch

- **At Card sign-in.** The Token is checked first. A dead Card still gets lib-f24.1's "this
  card no longer works, ask your teacher" page. A valid Card gets a paused page instead, and no
  Session starts: "The Library Assistant is taking a break until the librarian is ready. Please
  ask the librarian or your teacher." The Card stays valid, so the same scan works once someone
  is on Watch.
- **During a Session.** The chat page follows the Watch state (a small status request or
  event) and shows the same message, with the input disabled and the Student's unsent text left
  in the box. An exchange already being answered when the Watch lapses finishes.
- **A message that arrives anyway** (a race with the lapse) is never answered by the model.
  **The gate never switches off the Watchlist or the Supportive reply.** The message is still
  checked. A high-severity match still gets the Supportive reply and raises its Flag. A
  low-severity match still raises its Flag. Anything else gets the paused message. A Flag raised
  with nobody on Watch is marked *raised unwatched*. Its Alarm sounds on the next Start watch
  (below).
- The wording says the assistant is waiting for an adult, not that it is broken or that the
  Student did something wrong. That keeps it honest with Lesson 4 of the curriculum, which tells
  Students that adults see what is asked.

## The Alarm

- **What raises one.** Any high-severity Flag, from the Watchlist or from Oversight. A
  low-severity Flag raises the Flag queue's count and nothing else, with no sound. An Escalated
  Flag also raises an Alarm on the Counselor's Flag page if it is open, whether or not the
  Counselor is on Watch.
- **What it does.** On every watching page (Live view and Flag queue) it shows a banner that
  stays until Acknowledged. It does not fade like a toast. It puts the open-Alarm count in the
  tab title and changes the favicon. It plays a chime that repeats every 30 s until someone
  Acknowledges. The chime is a sound file shipped with the assistant, never fetched (ADR-0006,
  ADR-0007).
- **What it shows.** The category, severity, source, Class label, Card number, and registering
  Teacher (ADR-0002 addendum), with a link to the Flag. It never shows the Student's words.
  The words are one click away on the Flag, so a projected or shared screen does not show
  them.
- **Acknowledge, not close.** Acknowledge records which adult said "I'm on it" and when, and it
  silences the Alarm on every page. The Flag stays open in the Flag queue until it is worked and
  closed, as before. Acknowledging is not acting. The protocol's section 4 still applies.
- **Replay.** A high-severity Flag that nobody has Acknowledged (raised unwatched, raised
  overnight by Oversight, or raised while the only watching page was reloading) sounds its Alarm
  as soon as anyone presses Start watch, before anything else on the page.
- **Desktop notifications** (the browser Notifications API) are an optional extra. They are
  offered only when the page is served over HTTPS and the adult grants permission, and they
  carry the same no-words summary. They are delivered by the adult's own browser and operating
  system, not by a third-party push service. Plain-HTTP intranet Installs get the banner and the
  chime, which are the baseline.

## Out of scope: anything beyond the open page

SMS, email, and phone gateways all reach services outside the school intranet (ADR-0006).
Most school mail is hosted off site even when the relay is local. All of them would also carry
Flag details to devices outside the Install. A hook to an on-site paging or intercom system is
conceivable, but it needs its own ADR naming the system and what it may carry. Until then the
Watch rule is what makes an in-page Alarm enough: if no adult has the page open, Students are
not chatting.

## Every exchange is screened while someone is on Watch

Decided 2026-10-25 (lib-wpg): screening is real time. Every chat interaction is checked and,
when it may involve harm to a Student, reported while the adults who will act on it are
present. Three rules make that hold without an after-hours procedure:

1. **Cards last one school day at most.** Staff issue them, and Registration refuses an
   expiry later than the end of the school day it is registered on. No Session outlives the
   day, so no Student is chatting after the adults have gone.
2. **Sessions run only on Watch** (above), so every exchange happens while an adult is on the
   Live view or Flag queue. The Watchlist screens each message before the model is called.
3. **Each message is screened before the next one runs.** Oversight screens a message in
   parallel with its answer, and the Session's next message waits for that verdict (ADR-0004,
   "Screening is real time and ordered per Session"). So at most one message per Session is
   ever unscreened, and only for seconds. End watch, and the last watcher signing out, wait
   for those in-flight screens to finish; a lapsed heartbeat still ends the Watch, and any
   Flag that lands after it is marked *raised unwatched* and replays its Alarm at the next
   Start watch. That is a failure path, not a schedule.

Each Flag still records `raised_at`, whether it was raised unwatched, and who Acknowledged it
and when, and the Flag queue shows all three. The options considered were a next-morning
check, holding Oversight to Watch hours, and an after-hours Stand-in Watch; real-time
screening inside the Watch replaces all three.

## Considered options

- **Watch = any signed-in staff session.** Simple, but a Librarian who signed in at 8 a.m. and
  walked away still "watches", which is the gap lib-793 describes.
- **Watch = the page is visible (Page Visibility API).** Too strict. A Librarian at the desk
  working in another window pauses the class. And it adds nothing a chime does not already
  cover.
- **Pause Sessions on an unacknowledged Alarm.** Tempting, but it punishes the other 24
  Students for one Flag, and it tells the room that something happened. Not chosen. The Alarm
  repeats instead.
- **Email or SMS fallback.** Ruled out by ADR-0006 (above).

## Consequences

- The protocol's Rule 1 ("no Student uses the assistant unless a named adult is watching") is
  now enforced by the product, not only by the schedule. The section 3 schedule still stands for
  *how often* the adult looks at Flags that are not high severity.
- Staff accounts gain a Stand-in role, and Flags gain `raised_unwatched`, an Acknowledgement,
  and its time. Neither touches Student data.
- A Watch is staff data. It is kept with the staff account, never with a Session, and the
  Purge does not need it.
- A Librarian whose laptop sleeps pauses the class within the grace period. That is intended,
  and the Students' paused page is how the adult finds out.
- Sound is tested by hand once, when an Install is set up: the Start watch chime is the test.
  CI cannot hear.

## Amendment: supervision mode

Decided 2026-10-25 by the owner (lib-f24.77): "make all of these guardrails like watch
configurable; the librarian may not care, or may want to check every 2 hr". This supersedes
"No off switch" above. A school knows its own supervision better than the product does, and
a Librarian who runs the queue on a schedule shouldn't have to sit on a heartbeat to keep a
class chatting.

**The Librarian sets a supervision mode.** Every change is recorded with the account and the
time.

| Mode | Students can chat | Adults are expected to |
|---|---|---|
| **Live** (the default for a new Install) | Only while someone is on Watch, as above | Stay on the Live view or Flag queue |
| **Periodic review** | Any time in the school day. Optionally, they pause when a review is more than a set time overdue (default: never) | Review the Flag queue every `reviews_every_minutes` (default 120) and press Mark reviewed |
| **Off** | Any time in the school day | Whatever the school's own policy says |

**Also settings now:** the heartbeat grace period (`watch_grace_seconds`, 90), the Alarm chime
(on or off) and how often it repeats (30 s), what happens when Oversight is down (carry on
or pause, ADR-0004 addendum), and the Session idle limit (default none, since Students use
their own Chromebooks).

**Not settings, in any mode:**
- the Watchlist, and the Supportive reply on a high-severity match (ADR-0004, ADR-0011);
- every Flag is recorded, and an unacknowledged high-severity Alarm sounds on the next staff
  page anyone opens, as it replays at Start watch;
- Cards last at most one school day, and a Card has at most one message in flight;
- the privacy decisions: ADR-0002, ADR-0003, ADR-0006.

**What it costs.** In periodic or off mode, a disclosure can sit unseen until the next
review. The Student still gets the Supportive reply at once; the adults learn of it later.
Rule 2 of "Every exchange is screened while someone is on Watch" above then holds only in
Live mode, and the escalation protocol's Rule 1 becomes school policy rather than something
the product enforces. The template says who reviews and how often in each mode (lib-f24.80).

## Amendment: every Flag reaches whoever is on Watch at once

Decided 2026-10-29 by the owner (lib-4m7). "A low-severity Flag raises the Flag queue's count
and nothing else" left the adult on Watch unaware of it: they watch the Live view, and the
count sat on another page. Now every new Flag, low-severity too, appears the moment it is
raised as a row in an **Open Flags** panel on the watching pages (the Live view and the
Session detail), and its Session's tile marker updates without a refresh. Closing a Flag
takes its row away; reopening one puts it back.

What does not change: only a high-severity Flag sounds the Alarm (banner, tab title,
favicon, chime). A low-severity Flag stays silent; it is a row, not a sound. A panel row
shows severity, Class label, Card number, time, and source, never the category, the reason,
or the Student's words, so the Live view stays safe to share (`docs/design/live-view.md`);
the Flag's page, one click away, has the rest. A Counselor's stream carries none of it.

