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

### Open: a Roster backup when the Teacher is absent (lib-ay8)

Not decided here. The assistant never touches a Roster under any of these options, so
per-Teacher keys fit each one. What changes is where the Roster may live, and the CONTEXT.md
line "It never leaves the Teacher's machine".

1. **Accept the stall.** No copy. When the Teacher is away, the administrator phones them
   (section 5 of the escalation protocol).
   *Consequence:* ADR-0002 and CONTEXT.md stand as written. In imminent danger the Student is
   usually still in the supervised room. The cost falls on Flags found after the class has
   left, such as Oversight Flags and next-morning checks, and on a Teacher on a field trip
   with no signal.
2. **A sealed printed copy in the office.** The minting CLI and Minting page also print a
   Roster sheet headed with the Class label and the Batch's dates. The Teacher seals it, the
   office keeps it, an administrator opens it only for Identification and logs who opened it,
   and the sheet is shredded when the Batch expires.
   *Consequence:* the Roster leaves the Teacher's machine but never reaches the assistant, so
   the ADR's claim survives. CONTEXT.md becomes "never reaches the assistant". This adds a
   paper process that the office has to run. Product work: one printable sheet and nothing
   on the server.
3. **A second digital holder.** The Teacher saves the Roster CSV to a school-controlled place
   that a named second adult can open, such as a co-teacher's machine or a restricted share.
   *Consequence:* Identification is fastest, but the copy lives in school systems (possibly a
   cloud drive), where it is a pupil record under ADR-0001 with its own retention. It is also
   the broadest exposure of a Card-to-Student link. The assistant is unchanged.

Under every option the Flag shows the registering Teacher and the Batch's registration date,
so the right Teacher, or the right envelope, can be found.
