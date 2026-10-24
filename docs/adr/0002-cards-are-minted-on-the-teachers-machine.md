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
