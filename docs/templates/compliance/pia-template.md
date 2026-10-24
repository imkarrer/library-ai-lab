# Privacy impact assessment: Library Assistant

> Template, not legal advice. District counsel must review it before the district relies on it.

This follows the five-row PIA mini-template in DPI's
[AI Toolkits for Educators](https://dpi.wi.gov/imt/ai-guidance/educators/toolkits): Purpose,
Data, Risk, Access, Communication. The sign-off block comes from DPI's
[example PIA](https://dpi.wi.gov/sites/default/files/imce/imt/pdf/Example_Privacy_Impact_Assessment_PIA_Template_1.pdf).
DPI asks districts to "Require Privacy Impact Assessment (PIA) / Data Protection Impact
Assessment (DPIA) for new tools"
([Policy & Governance](https://dpi.wi.gov/imt/ai-guidance/administrators/policy)).

The text below already describes how the Library Assistant handles data. Fill in each
`[BLANK: …]` with the district's own details. **Keep the filled-in copy in a district-controlled
store, not in this public repository.**

## 1. Purpose

*What learning or operational need does the tool solve? Who benefits?*

Students in a supervised class ask questions about the school library's collection. They get
Grounded answers that cite the library's own Catalog Records. The Librarian sees what is being
asked in the Live view. Messages that suggest self-harm, abuse, bullying, or threats of
violence raise a Flag for an adult.

- Install location: `[BLANK: school and room]`
- Classes and grades in scope: `[BLANK]`. Supervised class use only, not whole-school
  self-serve (ADR-0009).
- Instructional purpose: `[BLANK: e.g., research unit, readers' advisory]`

## 2. Data

*What PII is collected? Optional vs. required? Storage location and duration?*

| Data | Where it lives | Who can see it | How long |
|---|---|---|---|
| Roster (which Student holds which Card number) | Teacher's machine only; never sent to the assistant | That Teacher | `[BLANK: until the Batch expires and no open Flag names one of its Cards]` |
| Printed Card (QR with one Token, Card number) | Student's hand during class | Student | Until the Batch expiry: `[BLANK: e.g., end of period]` |
| Token hash, Batch expiry, Class label (e.g., "Period 3") | Assistant server | System only | Until the Batch expires `[VERIFY: deletion of expired hashes]` |
| Session transcript (Student messages, replies), labelled by Class label and Card number | Assistant server | Librarian (Live view) | Purged at the end of the school day |
| Flag (category, severity, reason, source, time) and its transcript | Assistant server | Librarian, Counselor | Until an adult closes the Flag, then deleted at the next Purge |
| Catalog Records | Catalog on the intranet | Everyone using the assistant | Ongoing; bibliographic only, never circulation or patron data (ADR-0005) |

- **No names, student IDs, logins, or email addresses reach the assistant.** Registration
  sends only Token hashes, an expiry, and a Class label (ADR-0002).
- **Optional data:** whatever a Student types. The AUP insert tells Students not to type
  names or contact details. Anything they do type is still Purged.
- **Optional Oversight lane:** if configured, a second model on the intranet reviews
  exchanges after they happen and may raise Flags (ADR-0004). It sees the same transcripts
  and keeps nothing beyond the Purge. Configured here: `[BLANK: yes / no]`
- **Network:** the Install reaches only intranet services: its model endpoint and its
  Catalog. No cloud provider is configured (ADR-0006). The district demonstrates this with a
  firewall rule: `[BLANK: who verified egress is blocked, and when; keep the rule itself out
  of this document]`
- **Places transcripts could outlive the Purge**, each to be confirmed by the district:
  - Model server request logs: `[BLANK: off, or purged the same day]`
  - Backups of the assistant's database: `[BLANK: excluded, or kept no longer than one day]`
  - Web or proxy access logs (they hold library-machine addresses, not names):
    `[BLANK: retention]`
  - Browser history on shared library machines (it may hold a Card URL until expiry):
    `[BLANK: kiosk or guest profile?]`

**DPI vendor-vetting items.** DPI's checklist asks for a signed Wisconsin Student Data
Privacy Agreement, no training on student data, and deletion at contract end
([Toolkits](https://dpi.wi.gov/imt/ai-guidance/educators/toolkits)). There is no vendor, so
there is no agreement to sign. The models run inference only and are not trained on Student
messages. Deletion is the daily Purge. Model weights come from: `[BLANK: source, and how
updates are brought in without opening egress]`

## 3. Risk

*Top 3 risks (privacy, security, equity). Mitigations?*

| Risk | Mitigation | Owner |
|---|---|---|
| **Privacy:** a transcript gets tied to a Student (through the Roster, or because the Student typed a name) | Roster stays on the Teacher's machine. Identification only for a Flag, offline, between licensed staff. Daily Purge. AUP rule against typing names. | `[BLANK: Teacher, Librarian]` |
| **Security:** a lost or shared Card, a compromised server, or a network path out | Short Batch expiry, Revoke for one Card or a whole Batch, hashes only on the server, intranet only. The server is kept in the library. | `[BLANK: Librarian, district IT]` |
| **Safety and equity:** the Watchlist misses a disclosure, or Flags the wrong thing; the model gives a wrong answer | Watchlist always on, plus optional Oversight. A Supportive reply (988 line, trusted adult) instead of a refusal. Adults keep their duty of care. Citations on every answer, and "check the source" framing. Supervised use. | `[BLANK: Librarian, Counselor]` |

Accessibility review (WCAG 2.1 AA, as DPI recommends): `[BLANK: date, reviewer]`

## 4. Access

*Roles and permissions, audit logs, admin controls, export and deletion process.*

| Role | Can do | Cannot do |
|---|---|---|
| Librarian (`[BLANK: role title]`) | Run the Install, Live view, Flag queue, Revoke, Escalate | See any Roster |
| Teacher | Mint Batches, keep the Roster, answer an Identification request | See transcripts other than through the Librarian |
| Counselor (optional; otherwise the Librarian) | Receive Escalations, close Flags | — |
| Student | Use one Card for one Session | See other Sessions |

- Audit log of who viewed or closed a Flag: `[VERIFY: not yet specified in the ADRs]`
- Export: transcripts are not exported. An Escalation that needs a lasting record moves into
  the district's existing student-services records under their own rules: `[BLANK: which
  system]`
- Deletion: the automatic daily Purge. Records named in a pending records request are held
  (see `retention-policy.md`).

## 5. Communication

*Family notice, consent (if needed), classroom disclosure language.*

- Family notice: `[BLANK: letter or newsletter date]`. Say what Students use, that names never
  reach the assistant, that transcripts are deleted daily, and how Flags reach a counselor.
- Consent: COPPA does not apply to a school-run, non-commercial, intranet-only Install (see
  `ferpa-analysis.md`). The district may still choose to give notice or allow families to opt
  out: `[BLANK: district decision]`
- FERPA annual notice covers this record type: `[BLANK: yes / date updated]`
- Classroom disclosure: the AUP insert (`aup-insert.md`) and the DPI assignment disclosure
  box.
- Legal basis: FERPA (34 CFR Part 99), Wis. Stat. 118.125, possibly Wis. Stat. 43.30,
  [Wis. Stat. 134.98](https://docs.legis.wisconsin.gov/document/statutes/134.98) (breach
  notice), the district AUP and the retention rule.

## Approvals

Prepared by: `[BLANK]` Date: `[BLANK]` | Legal review: `[BLANK]` |
Superintendent: `[BLANK]` | School Board: `[BLANK]`

Review again after 30 and 90 days of student use, and whenever an Install adds Oversight,
changes the Purge window, or adds any service outside the intranet.
