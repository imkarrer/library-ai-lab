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

## Oversight Flags after the class leaves

The Watch gates Student Sessions, not Oversight. ADR-0004 lets Oversight drain its backlog
after class. So an Oversight Flag can arrive when nobody is on Watch, and then it is marked
*raised unwatched* and replays at the next Start watch. Who must see it, and how soon, is
**lib-wpg, which is not decided here**. The design works with each option:

1. **Next-morning check (protocol section 8 as written).** Oversight drains whenever it can.
   Unwatched Flags wait for the first Start watch of the next school day, and the Alarm
   replays first thing.
   *Consequence:* nothing new to build, but a Flag about a Student who has gone home can wait
   about 15 hours overnight and about 60 hours over a weekend. The school's
   after-hours procedure never starts, because nobody knows yet.
2. **Hold Oversight to Watch hours.** A setting (`oversight.run_while = "watch"`) keeps the
   Oversight worker idle unless someone is on Watch. Every Oversight Flag then reaches an adult
   who is present. The Librarian can stay on Watch for a while after the last class so the
   backlog drains.
   *Consequence:* no Flag ever lands on an empty room, and the delay for a 3 p.m. exchange is
   the same as option 1 or longer. On a shared box it loses the after-class drain that ADR-0004
   counts on, so the backlog carried through the Purge (lib-f24.10) grows. More transcripts are
   kept overnight, which is ADR-0001 exposure.
3. **An after-hours Watch.** A named adult, such as the administrator on duty, holds a
   Stand-in Watch from a school device on the intranet until a set time, and the Alarm reaches
   them. The Watch gate does not care what time it is. Student Sessions would open during that
   Watch too, so this option also needs a setting that lets an after-hours Watch cover Oversight
   only.
   *Consequence:* the after-hours procedure can start the same evening. But it needs a
   person on duty, and it only works from home if the district treats its VPN as the
   intranet, which ADR-0006 would have to say. Weekends stay uncovered unless someone is
   rostered.

Whichever is chosen, each Flag records `raised_at`, whether it was raised unwatched, and who
Acknowledged it and when. The Flag queue shows all three.

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
