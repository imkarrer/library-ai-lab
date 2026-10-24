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
   e.g., one school day]` and closed within `[BLANK: e.g., 10 school days]` unless an
   Escalation is still in progress.
3. **Escalations.** When a Flag is escalated, anything the Counselor records about the
   Student is kept in `[BLANK: the district's student-services system]` under the district's
   existing rules for those records. It is not kept in the Library Assistant.
4. **Closed Flags.** After a Flag closes, the assistant keeps only `[BLANK: e.g., category,
   severity, source, dates, no transcript]` for `[BLANK: period]`, for program review.
5. **Registrations.** Token hashes, expiry, and Class label are deleted after the Batch
   expires: `[BLANK: e.g., at the next Purge]`.
6. **Rosters.** A Roster stays on the Teacher's district-issued machine. It is never uploaded
   to the assistant, emailed, or shared. The Teacher deletes it once its Batch has expired and
   no open Flag names one of its Cards.
7. **No other copies.** Transcripts are not backed up, exported, or logged anywhere that would
   outlive the Purge. This includes model-server logs and database backups.
8. **Changing the window.** A longer retention window requires a board action that states
   the reason and the added records exposure (ADR-0003). It may never exceed the limit for
   behavioral records in Wis. Stat. 118.125(3).

### 5. Records requests

1. **What exists.** Because of the Purge, most requests will find no transcript. Only records
   that exist on the day the request arrives can be produced. A record deleted on schedule
   before a request arrives is not withheld.
2. **Hold.** When a request arrives, the Purge is suspended for every record it reasonably
   covers until the request is resolved. FERPA forbids destroying an education record while a
   request to inspect it is pending (34 CFR 99.10(e)). Wis. Stat. 19.35(5) forbids destroying
   a requested record until the request is granted, or for 60 days after it is denied. The
   Librarian places the hold the same day: `[BLANK: how, until the product ships a hold
   feature]`.
3. **Parent or eligible student.** Requests go to `[BLANK: records custodian role]`. To find
   the records, the custodian asks the Teacher for the Student's Card numbers. Behavioral
   records are shown in the presence of a person qualified to explain them, and a copy is
   provided on request (118.125(2)(b)). Response within 45 days (34 CFR 99.10(b)) or
   `[BLANK: shorter district standard]`.
4. **Public records request.** Pupil records are confidential under 118.125(2) and are not
   released under Wis. Stat. 19.35 except as that section permits. Forward such requests to
   `[BLANK: legal custodian]` and counsel.
5. **Subpoena, court order, or law enforcement.** Forward them to counsel the same day. Hold
   the records as in 5.2.
6. **Emergencies.** A disclosure outside the school because of a health or safety emergency
   follows 34 CFR 99.36 and the district's crisis protocol: `[BLANK: protocol name]`.

### 6. Review

The `[BLANK: role]` reviews this rule each year, and whenever the Install's configuration
changes how long any record is kept.

Adopted: `[BLANK: date]`. Published as a class 1 notice: `[BLANK: date and newspaper]`.
