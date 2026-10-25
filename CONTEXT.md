# Library Assistant

A local AI assistant a school librarian installs on hardware in the building: students ask
about the library's collection under short-lived, pseudonymous access, and the adults in the
building see what is asked and what needs a counselor. It is also the showcase for flox in
education.

## People

**Librarian**:
The staff member who installs and runs the assistant, watches the Live view, and works the
Flag queue. Owns the install.
_Avoid_: admin, operator

**Teacher**:
A staff member who mints Batches for a class, registers them with their own Registration key,
and keeps that class's Roster.
_Avoid_: issuer

**Counselor**:
An optional staff role that receives Escalations. When there is none, the Librarian wears
this hat. A Counselor alone cannot hold a Watch, because they see only Escalated Flags.
_Avoid_: reviewer, moderator

**Stand-in**:
A role the Librarian grants to any staff account so it can open the Live view and Flag queue
and hold a Watch in the Librarian's place. It cannot manage accounts, keys, or settings.
_Avoid_: backup, deputy, substitute

**Student**:
Anyone chatting through a Card. The assistant never knows which student; only the Roster does.
_Avoid_: user, patron

## Access

**Card**:
A printed QR code carrying one Token, with its Card number visible. The thing a Student holds.
_Avoid_: ticket, pass, badge

**Token**:
The secret on a Card. The server stores only its hash.
_Avoid_: code, password, key

**Card number**:
The per-Batch sequence printed on a Card ("card 14"). How adults refer to a Session without
naming anyone.

**Batch**:
The set of Cards minted together for one Class label, sharing one expiry no later than the
end of the school day it is registered on.
_Avoid_: sheet, set

**Class label**:
A non-identifying name for a Batch, such as "Period 3".
_Avoid_: class name, section ID

**Minting**:
Generating a Batch on the Teacher's own machine: Cards to print, a Roster to keep, Token
hashes to register.

**Registration**:
Sending a Batch's Token hashes with their Card numbers, the expiry, and the Class label to the
assistant, under the minting Teacher's Registration key. Nothing about any Student ever
reaches it.

**Registration key**:
A staff account's own secret for Registration, shown once and stored as a hash. It is how the
assistant knows which Teacher registered a Batch.
_Avoid_: API key, token, password

**Roster**:
The Teacher's record of which Student holds which Card number, kept on the Teacher's machine
with a sealed printed copy in the office. It never reaches the assistant.
_Avoid_: mapping, class list

**Session**:
One Card's conversation with the assistant, from first scan until the Batch expires or is
Revoked.
_Avoid_: chat, login

**Revoke**:
Ending Sessions early, for one Card or a whole Batch.

## Conversation

**Catalog**:
The school's own index of its collection, wherever and however it is deployed.
_Avoid_: database, OPAC (unless naming a specific product)

**Record**:
One title's bibliographic description from the Catalog. Never circulation or patron data.
_Avoid_: book, item, document

**Catalog adapter**:
The seam that lets the assistant search one kind of Catalog.
_Avoid_: connector, plugin, integration

**Grounded answer**:
A reply built from Records and carrying Citations to them.

**Citation**:
A reference in a Grounded answer to the Record it came from.

**Purge**:
The end-of-school-day deletion of every transcript except those attached to an open Flag or
under a Hold. It also deletes expired Token hashes and Flag histories past their time.

**Hold**:
A pause on the Purge for every record in a scope (Class labels, a date range, and optionally
Card numbers), set by the Librarian when a records request, court order, or preservation
request arrives, and lifted only by the Librarian. It never expires on its own.
_Avoid_: legal hold, freeze, lock

## Safety

**Live view**:
The Librarian's running view of what Sessions are asking, labelled by Class label and Card
number.
_Avoid_: monitor, surveillance, dashboard

**Flag**:
A recorded concern about one exchange, with a category, a severity, and a reason.
_Avoid_: alert, incident, report

**Rubric**:
The fixed set of Flag categories: self-harm, abuse, bullying, threats of violence.

**Watchlist**:
The curated, versioned phrases and patterns, each with a Rubric category and a severity, that
every Student message is checked against. Always on.
_Avoid_: keyword list, blocklist, filter, backstop

**Oversight**:
An optional model that reviews exchanges against the Rubric after they happen, on its own
Lane, and raises Flags the Watchlist missed.
_Avoid_: moderation, guard, classifier

**Lane**:
A model endpoint dedicated to one job. The Answer lane serves Students; the Oversight lane, if
configured, serves Oversight and never takes capacity from the Answer lane.
_Avoid_: worker, backend, provider

**Flag queue**:
Open Flags waiting for an adult.

**Flag history**:
The append-only account of what happened to one Flag: raised, viewed, escalated, exported,
closed, reopened, each with the staff account and the time, and a reason where one is
required. Kept for a while after the exchange is purged.
_Avoid_: audit log, trail

**Export**:
A staff action that copies a Flag's exchange, or a Hold's transcripts, into a file the school
files in its own records. The assistant keeps no copy, and the school's pupil-records rules
govern the file.
_Avoid_: download, backup, save

**Watch**:
A Librarian's or Stand-in's deliberate, heartbeat-confirmed presence on the Live view or Flag
queue, from Start watch until End watch, sign-out, or a missed heartbeat. Student Sessions
start and continue only while at least one Watch is on.
_Avoid_: shift, duty, monitoring, online

**Alarm**:
The banner, tab title, and repeating chime a high-severity Flag raises on every watching page
until an adult Acknowledges it. It shows no Student words and never leaves the page.
_Avoid_: alert (a Flag is not an alert), notification, page

**Acknowledge**:
An adult saying "I'm on it" to an Alarm: it records who and when and silences the Alarm. It
does not close the Flag.
_Avoid_: dismiss, resolve

**Supportive reply**:
The reply a Student gets instead of an answer when a message matches a high-severity Watchlist
entry: written for its Rubric category, naming an adult in the building, and for self-harm the
988 line. An Install may adjust it within fixed guard rails.
_Avoid_: refusal, canned response

**Escalation**:
An adult handing a Flag to the Counselor.

**Identification**:
An adult learning which Student held a Card number by asking the Teacher who holds the
Roster. Always offline, between adults.
_Avoid_: de-anonymization, lookup

## Rollout

**Install**:
One school's running copy of the assistant, set up by its Librarian.
_Avoid_: deployment, instance, tenant

**Reference deployment**:
The Eau Claire middle school library Install: the first real one, after the demo.
