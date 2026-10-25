# Retention rule: Library Assistant records

> Template, not legal advice. District counsel must review it before the board adopts it.

Language a school board can adopt as part of its pupil-records rules. Wis. Stat.
[118.125(3)](https://docs.legis.wisconsin.gov/document/statutes/118.125) requires each board to
"adopt rules in writing specifying the content of pupil records and the time during which
pupil records shall be maintained" and to publish them as a class 1 notice under ch. 985. The
reasoning is in `ferpa-analysis.md`. The design decisions are in ADR-0001 (transcripts are
treated as pupil records) and ADR-0003 (Purge at the end of the school day).

---

## Policy `[BLANK: policy number]`: Library Assistant records

### 1. Scope

This rule covers records created by the Library Assistant Install at `[BLANK: school]`:
Session transcripts, Flags, Batch Registrations, and the Rosters Teachers keep for them.

### 2. Definitions

- **Card**: a printed QR code a Student uses to reach the assistant. It carries no name.
- **Roster**: a Teacher's record of which Student holds which Card number.
- **Session transcript**: the messages one Card exchanged with the assistant.
- **Flag**: a recorded concern about one exchange, with a category, a severity, and a reason.
- **Purge**: the automatic deletion described in section 4.
- **Flag history**: the assistant's record of who viewed, escalated, exported, closed, or
  reopened a Flag, when, and why.
- **Export**: a file of a Flag's exchange, or of held transcripts, that staff file in the
  school's own records.
- **Hold**: a pause on the Purge for the records a request covers, described in section 5.

### 3. Classification

While they exist, Session transcripts, Flags, and Rosters are treated as pupil records and,
specifically, as behavioral records under Wis. Stat. 118.125(1)(a). They are also treated as
education records under FERPA (34 CFR Part 99). They are confidential and are disclosed only
as those laws allow.

### 4. Retention

1. **Daily Purge.** Every Session transcript is deleted at the end of the school day it was
   created: `[BLANK: time, e.g., 4:30 p.m.]`. The deletion is automatic.
2. **Flag exception.** A transcript attached to an open Flag is kept until an adult closes the
   Flag. It is then deleted at the next Purge. An open Flag is reviewed within `[BLANK:
   e.g., one school day]` and closed within `[BLANK: e.g., 5 school days]` unless an
   Escalation is still in progress. The assistant marks a Flag overdue after `[BLANK: the
   Install's overdue setting; default 7 days]`. It never closes a Flag on its own.
3. **Export before closing.** Before closing a Flag, staff Export whatever the school must
   keep from the exchange and file it in `[BLANK: the district's student-services or incident
   record]`. The assistant keeps no copy of an Export. Once filed, the Export follows the
   district's rules for that record, and the download is deleted from the staff machine.
4. **Escalations.** When a Flag is escalated, anything the Counselor records about the
   Student is kept in `[BLANK: the district's student-services system]` under the district's
   existing rules for those records. It is not kept in the Library Assistant.
5. **Closed Flags.** After a Flag closes, its exchange is deleted at the next Purge. The
   assistant then keeps only the Flag (category, severity, source, Class label, Card number,
   dates) and its Flag history, with no transcript, for `[BLANK: the Install's history
   setting; default 90 days]` after closing, then deletes them. This period must end well
   within one year after the pupil leaves (Wis. Stat. 118.125(3)).
6. **Registrations.** Token hashes are deleted at the first Purge after the Batch expires or
   is Revoked. The Batch's Class label, Card numbers, and expiry are kept only while a
   transcript, Flag, or Hold refers to them.
7. **Rosters.** A Roster stays on the Teacher's district-issued machine. It is never uploaded
   to the assistant, emailed, or shared. The Teacher deletes it once its Batch has expired, no
   open Flag names one of its Cards, and no Hold covers its Class label and dates.
8. **No other copies.** Transcripts are not backed up or logged anywhere that would outlive
   the Purge. The only copies are Exports staff make under 4.3 and 5.2. The Install's setup
   record shows that model-server request logging and captures are off, and that the
   assistant's data folder is excluded from backups: `[BLANK: where the Install's setup
   record is kept]`.
9. **Changing the window.** A longer retention window requires a board action that states
   the reason and the added records exposure (ADR-0003). It may never exceed the limit for
   behavioral records in Wis. Stat. 118.125(3).

### 5. Records requests

1. **What exists.** Because of the Purge, most requests will find no transcript. Only records
   that exist on the day the request arrives can be produced. A record deleted on schedule
   before a request arrives is not withheld.
2. **Hold.** When a request arrives, the Purge is suspended for every record it reasonably
   covers until the request is resolved. FERPA forbids destroying an education record while a
   request to inspect it is pending (34 CFR 99.10(e)). Wis. Stat. 19.35(5) forbids destroying
   a requested record until the request is granted, or for 60 days after it is denied (90
   for a committed or incarcerated requester), and while a court action on it is pending.
   The Librarian sets a Hold in the assistant the same day, before that day's Purge. The
   Hold names the Class labels and dates the request covers, and the Card numbers once the
   Teacher supplies them. Its reference is `[BLANK: the district's request number]`, never a
   name. The Hold keeps every transcript, Flag, and Flag history in its scope, including
   records created later if its end date is in the future. To produce the records, the
   Librarian Exports them from the Hold.
3. **Lifting a Hold.** Only the Librarian lifts a Hold, and only when `[BLANK: records
   custodian role]` confirms that the request was fulfilled or withdrawn, that 60 days (or
   90) have passed since a denial, or that the court matter has ended. A Hold never expires on
   its own. The assistant marks any Hold older than `[BLANK: default 30 days]` for review.
   After a Hold is lifted, the next Purge applies section 4 to what it held.
4. **Parent or eligible student.** Requests go to `[BLANK: records custodian role]`. To find
   the records, the custodian asks the Teacher for the Student's Card numbers. Behavioral
   records are shown in the presence of a person qualified to explain them, and a copy is
   provided on request (118.125(2)(b)). Response within 45 days (34 CFR 99.10(b)) or
   `[BLANK: shorter district standard]`.
5. **Public records request.** Pupil records are confidential under 118.125(2) and are not
   released under Wis. Stat. 19.35 except as that section permits. Forward such requests to
   `[BLANK: legal custodian]` and counsel, and set a Hold as in 5.2: 19.35(5) applies even
   when the request will be denied.
6. **Subpoena, court order, or law enforcement.** Forward them to counsel the same day. Set
   a Hold as in 5.2.
7. **Emergencies.** A disclosure outside the school because of a health or safety emergency
   follows 34 CFR 99.36 and the district's crisis protocol: `[BLANK: protocol name]`.

### 6. Review

The `[BLANK: role]` reviews this rule each year, and whenever the Install's configuration
changes how long any record is kept.

Adopted: `[BLANK: date]`. Published as a class 1 notice: `[BLANK: date and newspaper]`.
