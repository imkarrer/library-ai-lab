# Cards are minted on the Teacher's machine

The Teacher's machine mints each Batch and keeps the Roster; Registration sends the
assistant only Token hashes with their Card numbers, an expiry, and a Class label. The
assistant has never held the link between a Card and a Student, so it cannot disclose one,
and Identification happens
offline between adults. This is defensive FERPA posture: "the server never had it" is a claim
a board, a parent, or DPI can verify; "the server forgot it" is not.

## Considered Options

- **Server mints, Teacher downloads the Roster, server forgets it.** Simpler, but the claim
  rests on the server's behaviour rather than its design.
- **Bind the Card to the district login (OIDC) at scan time.** Real identities on every
  transcript, a per-district IdP integration, and the pupil-records question at full weight.

## Addendum: each Teacher registers with their own key

Proposed 2026-10-25 (lib-90j). Identification starts with "which Teacher holds this Roster?",
but one registration key shared by every Teacher (lib-f24.5) cannot answer it. So each staff
account that mints (a Teacher, or the Librarian) has its own **Registration key**. The
Librarian issues and rotates the keys, and a Teacher can rotate their own. A key is shown
once and stored as a hash. It is kept separate from the account password, so the minting
CLI and the offline Minting page can hold it without holding a login. The shared key goes
away.

Registration itself does not change. The payload is still Token hashes with Card numbers, the
expiry, and the Class label. The registering Teacher is worked out from the key that
authenticated the request, never from the payload. The Batch stores a reference to that staff
account. The Live view, the Flag queue, an Alarm, and the Counselor's view each show
"Registered by" with that Teacher's display name. A deactivated account's key stops working
at once. Its Batches keep the name until they expire, so a Flag never loses its Teacher.

This adds staff data, not Student data. The assistant can now say which Teacher's class a Card
was minted for, which the Class label nearly said already. It still cannot say which Student
held it. "The server never had it" still holds for the Card-to-Student link. Registration
now means "nothing about any Student ever reaches it", in place of "nothing else about the
Batch", and CONTEXT.md says the same.

### Decided: a sealed printed Roster when the Teacher is absent (lib-ay8)

Decided 2026-10-25. Minting also prints a Roster sheet headed with the Class label and the
Batch's dates. The Teacher seals it in an envelope, the office keeps it the way it keeps a
substitute folder, an administrator opens it only for Identification and logs who opened it
and why, and the sheet is shredded when the Batch expires (or when the Hold or open Flag that
needs it ends). The Roster still never reaches the assistant, so "the server never had it"
holds; CONTEXT.md now says the Roster never reaches the assistant rather than never leaving
the Teacher's machine. The product work is one printable sheet in the minting CLI and the
offline Minting page, and nothing on the server.

Considered and not chosen: accepting the stall (Flags found after the class has left wait for
the Teacher), and a second digital holder (fastest, but the widest exposure of the
Card-to-Student link, held in school systems as a pupil record under ADR-0001). Every Flag
shows the registering Teacher and the Batch's registration date, so the right Teacher, or the
right envelope, can be found.

## Addendum: the assistant hands out each Teacher's Minting page, filled in

Decided 2026-10-29 (lib-ers). Pasting a 43-character Registration key into the offline
Minting page was the step no Teacher would do. So the assistant now offers the page as a
download, with its own address and a new Registration key for that account written into the
page's install-config block: the Librarian downloads it for a Teacher from **Keys**, or a
Teacher downloads their own from `/staff`. Downloading issues a new key (the old one is
stored only as a hash, so it cannot be written out), so every earlier copy of that account's
page stops registering.

The page is the repo's `offline-minting.html` byte for byte apart from that block, and a
test holds it to that. Tokens are still made in the Teacher's browser, offline, and only
their hashes are registered, so "the server never had it" still holds for Tokens and for the
Card-to-Student link. What changes is where the Minting code comes from: the assistant now
hands it out. A compromised assistant could hand out a page that leaks Tokens, which the
rejected "server mints" option also allowed. This is accepted because the page is fetched
once, not on every use, and can be compared with the repo's copy. A school that wants the
stricter posture gives Teachers the repo's page and the key separately, as before.

The downloaded file holds a live key, so it is sent with `Cache-Control: no-store`, and the
page tells the Teacher to keep it to themselves. A lost copy is handled like a lost key: the
Librarian downloads a new one, and the lost copy stops working.

## Addendum: the Minting page keeps each Roster on the Teacher's computer for 7 days

Decided 2026-10-29 by the owner (lib-3t8). A Roster typed into the Minting page lived only in
that page, so closing it lost the names, and a Flag raised later could not be traced: it
happened in the demo. The page now keeps each Batch's Roster in its own browser storage on the
Teacher's computer: the Class label, the Batch's dates, and Card number to name, never a Token
or its hash. **Find a Card** answers "who held card N in this Class" from it, and a **Finish**
step says where it is kept and offers the printed copy for the office.

Each kept Roster deletes itself 7 days after its Batch was made: long enough to trace a Flag
found the next day or after a weekend (Flags are overdue after 7 days open), short enough that
names do not collect in a browser. The Teacher can delete one sooner. The Roster still never
reaches the assistant, so "the server never had it" holds. What changes is that a digital copy
of a pupil record now sits on the Teacher's computer for a week instead of only in a file the
Teacher chose to keep; a school that does not want that tells Teachers to use the page in a
private browser window, which keeps nothing, and to keep the printed Roster.

## Addendum: Identification requests carry the question, never the name

Decided 2026-10-29 by the owner (lib-axb): "make it as easy as possible for the counselor to
know who to talk to." The adult working a Flag (the Librarian, a Stand-in, or the Counselor who
owns an Escalated Flag) presses **Ask the Teacher who held it** on the Flag page. The request
names the Flag's Class label, Card number, and Batch expiry, the Teacher who registered the
Batch, who asked, and when. The Teacher sees it on `/staff`, and their Minting page, which
reads its Teacher's open requests with the Registration key it already carries, matches each
one against the Rosters kept on that computer (the addendum above) and shows the name **on
the Teacher's screen only**. The Teacher answers **I've told them** or **Not in my Rosters**,
and the name passes between the two adults in person. The assistant records the request and
the answer in the Flag's History, never a name, so "the server never had it" still holds. A
high-severity Flag's panel says not to wait for the answer: find the Teacher now.

So that a Flag found after the Batch's day still knows whom to ask, each Flag now keeps the
registering Teacher's account when it is raised: the Purge deletes an expired Card's row, and
with it the only other record of who registered the Batch. This adds staff data to a Flag,
which the ADR-0002 addendum on Registration keys already showed on it, and nothing about a
Student.


## Addendum: Make Cards, an app the assistant serves

Decided 2026-10-30 by the owner. A downloaded Minting page is a file with a live key in it:
it can be forwarded, left in Downloads, or opened by anyone at that computer, and a Teacher
opening an HTML file from Downloads has no sign that it is genuine. So the assistant now
serves the Minting page itself, as **Make Cards** at `/staff/mint/`, to a signed-in Teacher
or Librarian (`library_assistant/mint_app.py`). It is the same page with no key in it: it
registers Batches and reads and answers Identification requests through the app's own
routes, as the signed-in account. Chrome and Edge offer to install it (a manifest, an icon,
and a service worker), so it opens from the Chromebook shelf, the Dock, or the Start menu,
with nothing downloaded and nothing for IT to approve. Not a native app: Chromebooks cannot
run one, signing one costs money every year, and managed computers often block installing
one, which would need IT.

What does not change: Tokens are made in the Teacher's browser and only their hashes are
registered, the Roster stays in that browser for 7 days, and names never reach the
assistant. "The server never had it" still holds for Tokens and for the Card-to-Student
link.

What changes is that the Minting code is trusted on every load, not once per download.
A compromised assistant could serve a page that leaks Tokens, as the earlier addendum
accepted for the download. Three things bound it:

- **A Content-Security-Policy** on the page lets it run only its own two inline scripts,
  named by their SHA-256 hashes, and send requests only to the assistant
  (`connect-src 'self'`). An injected script does not run, and the page cannot send a
  Token or a name to any other address.
- **The page is the repo's `offline-minting.html`** except its install-config block and four
  `<head>` lines (manifest, icons, theme colour); a test holds it to that. The script
  hashes in the policy can be compared with the repo's copy.
- **The downloaded page stays** as the fallback, for a school that wants the code fixed at
  download time, and for a computer that is offline from the assistant.

Consequences:

- Rosters kept by the app live in the browser's storage for the assistant's address, not the
  downloaded file's, so Rosters made with a downloaded page do not appear in the app. They
  expire within 7 days; a Teacher switching keeps the file for a week. If the assistant's
  address changes (HTTP to HTTPS, or a new address), Rosters kept under the old one do not
  appear under the new one either; the printed sealed Roster covers that.
- Installing needs a secure context: HTTPS (ADR-0013, or ADR-0012's local CA where IT pushed
  it) or `localhost`. Over plain HTTP at a network address the app works the same in a tab,
  without Install and without its kept copy. Browsers give `crypto.subtle` only to secure
  contexts, so the page carries its own SHA-256 for that case, held to Python's `hashlib` by
  the tests.
- The service worker keeps one copy of the page, fetched network-first, so the app opens
  without the assistant for **Find a Card**. It never keeps a sign-in page or an error in
  its place. Making Cards still needs the assistant, since a Card is registered before it is
  shown.
- A staff session lasts 12 hours, so the app asks the Teacher to sign in again most days;
  signing in returns them to Make Cards.
- In the demo stack alone, `LIBRARY_ASSISTANT_DEMO_CLASS` prefills Mr. Pop-Quiz's fictional
  class. It is read only when `LIBRARY_ASSISTANT_DEMO` is on.
