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
A staff member who mints Batches for a class and keeps that class's Roster.
_Avoid_: issuer

**Counselor**:
An optional staff role that receives Escalations. When there is none, the Librarian wears
this hat.
_Avoid_: reviewer, moderator

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
The set of Cards minted together for one Class label, sharing one expiry.
_Avoid_: sheet, set

**Class label**:
A non-identifying name for a Batch, such as "Period 3".
_Avoid_: class name, section ID

**Minting**:
Generating a Batch on the Teacher's own machine: Cards to print, a Roster to keep, Token
hashes to register.

**Registration**:
Sending a Batch's Token hashes with their Card numbers, the expiry, and the Class label to the
assistant. Nothing else about the Batch ever reaches it.

**Roster**:
The Teacher's record of which Student holds which Card number. It never leaves the Teacher's
machine.
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
The end-of-school-day deletion of every transcript except those attached to an open Flag.

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

**Supportive reply**:
The fixed reply a Student gets when an exchange raises a high-severity Flag: talk to a
counselor or trusted adult, and the 988 line.
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
