# Legal analysis: FERPA, Wis. Stat. 118.125, 43.30, and COPPA

> Template, not legal advice. District counsel must review it before the district relies on it.

This is the reasoning behind ADR-0001 to ADR-0003, checked against the primary sources in
October 2026. It covers a Wisconsin public school running a Library Assistant Install. Items
marked `[VERIFY]` could not be confirmed against a primary source.

## Short answer

1. **FERPA and Wis. Stat. 118.125 apply.** While a transcript exists, the school should treat
   it as an education record and a pupil record (a *behavioral record*). It has no name on it,
   but the school can link it to a Student through the Teacher's Roster.
2. **Wis. Stat. 43.30 may also apply.** Its text covers "any library which is in whole or in
   part supported by public funds", which can include a public school library. This corrects
   ADR-0001, which says 43.30 reaches only public libraries. The design satisfies 43.30 as
   well, but counsel should decide which rule governs Identification.
3. **COPPA does not reach the Install** while it is school-run, non-commercial, and
   intranet-only. A commercial operator in the loop would change that.
4. **The design reduces the exposure but does not remove it.** Cards keep names off the
   server (ADR-0002), and the daily Purge means little exists to disclose or produce
   (ADR-0003). Neither takes transcripts outside these laws. The district still needs a
   written retention rule and a records-request procedure (see `retention-policy.md`).

## Facts the analysis assumes

- The Teacher mints Cards on a school machine and keeps the Roster there. Registration sends
  the assistant only Token hashes, an expiry, and a Class label (ADR-0002).
- The assistant stores each Session's transcript under its Class label and Card number. It
  shows them in the Live view and deletes them at the end of the school day, except
  transcripts attached to an open Flag (ADR-0003).
- Identification happens offline: an adult asks the Teacher which Student held a Card number.
- The Install reaches only intranet services, and no cloud model provider is configured
  (ADR-0006). The Catalog adapter returns bibliographic Records and no patron data
  (ADR-0005).

## FERPA (20 U.S.C. 1232g; 34 CFR Part 99)

**Education records.** Under [34 CFR 99.3](https://www.ecfr.gov/current/title-34/section-99.3),
education records are records "directly related to a student" and "maintained by an
educational agency or institution or by a party acting for the agency or institution."
Personally identifiable information (PII) includes "information that, alone or in combination,
is linked or linkable to a specific student" (para. (f)). It also includes information
requested by someone the school reasonably believes knows the student's identity (para. (g)).

**Application.** A transcript filed under "Period 3, card 14" is linkable: the school holds
the Roster that links it to a Student. The server never holding the link is a strong security
property. It is not a FERPA exemption, because FERPA looks at what the *institution* can link.
The exclusion for records in "the sole possession of the maker" (99.3(b)(1)) does not fit
either: the Librarian sees transcripts in the Live view, and Identification shows a Roster
entry to another adult. The Roster is therefore an education record too.

**Consequences while a record exists:**

- A parent or eligible student may inspect it. The school must comply "within a reasonable
  period of time, but not more than 45 days" after the request
  ([34 CFR 99.10(b)](https://www.ecfr.gov/current/title-34/section-99.10)).
- The school "shall not destroy any education records if there is an outstanding request to
  inspect and review" them (99.10(e)). **The daily Purge must yield to a pending request.**
- Disclosure inside the school is allowed to "other school officials, including teachers,
  ... whom the agency or institution has determined to have legitimate educational
  interests" ([34 CFR 99.31(a)(1)(i)(A)](https://www.ecfr.gov/current/title-34/section-99.31)).
  This covers Identification and Escalation to the Counselor. Disclosure outside the school
  in an emergency falls under 99.31(a)(10) and
  [99.36](https://www.ecfr.gov/current/title-34/section-99.36).

**How the ADRs answer it.** ADR-0002 keeps the link off the server, so a breach of the server
exposes no names. ADR-0003 keeps the record set small: most days, a parent request finds
nothing left except open Flags. What remains for the district: setting a Hold on the Purge for
records named in a pending request (designed in ADR-0003's addendum, not yet built), and the
annual FERPA notice covering this record type.

## Wis. Stat. 118.125 (pupil records)

**Definitions.** [118.125(1)(d)](https://docs.legis.wisconsin.gov/document/statutes/118.125)
defines pupil records as "all records relating to individual pupils maintained by a school".
Behavioral records under 118.125(1)(a) expressly include "records of conversations" and any
pupil record that is not a progress record. A transcript is a record of a conversation. The
teacher-notes exclusion (118.125(1)(d)1.) fails for the same reason as FERPA's sole-possession
exclusion: the notes must not be "available to others."

**Consequences:**

- All pupil records "shall be confidential" except as the statute allows (118.125(2)). A
  parent or guardian of a minor pupil may see behavioral records "in the presence of a person
  qualified to explain and interpret the records" and get a copy (118.125(2)(b)).
- Licensed staff and other officials the board has found to have "legitimate educational
  interests, including safety interests" may access them (118.125(2)(d)). This is the state
  basis for Identification and Escalation.
- **Retention is the board's call, by written rule.** Under 118.125(3) each board "shall adopt
  rules in writing specifying the content of pupil records and the time during which pupil
  records shall be maintained", and must publish them as a class 1 notice. Behavioral records
  have a *maximum* (one year after the pupil leaves) and no minimum. A same-day Purge is
  lawful if the board adopts it as a rule.
- The general records-destruction rule for school districts,
  [19.21(6)](https://docs.legis.wisconsin.gov/document/statutes/19.21) (7-year default,
  60 days' notice to the historical society), "does not apply to pupil records under s.
  118.125".

**Correction to ADR-0001.** ADR-0001 cites "a 60-day response window." The text of 118.125
sets no response deadline. FERPA's deadline is 45 days. The 60-day figures nearby are
19.21(6)'s notice to the historical society and
[19.35(5)](https://docs.legis.wisconsin.gov/document/statutes/19.35), which bars destroying a
record after a public-records request until it is granted or for 60 days after a denial.

**If counsel concludes transcripts are *not* pupil records** (for example, because the
transcript alone does not identify anyone), they are still district public records under
[19.32(2)](https://docs.legis.wisconsin.gov/document/statutes/19.32). That would bring them
under 19.21(6): kept at least 7 years unless a Public Records Board schedule sets a shorter
period. The daily Purge would then need an adopted general records schedule that covers it.
`[VERIFY: which PRB schedule and series, if any, covers short-lived chat transcripts]`
(see [DPI records management](https://dpi.wi.gov/libraries/records)). Treating transcripts as
pupil records is both the more protective reading and the one that makes the daily Purge
straightforward.

## Wis. Stat. 43.30 (library records)

The usual view, which ADR-0001 adopts, is that 43.30 governs public libraries and not school
libraries. The text does not support that view cleanly:

- [43.30(1m)](https://docs.legis.wisconsin.gov/document/statutes/43.30) covers "Records of
  any library which is in whole or in part supported by public funds, including the records
  of a public library system, indicating the identity of any individual who borrows or uses
  the library's documents or other materials, resources, or services."
- The section's title, "Public library records," is not law:
  "titles ... are not part of the statutes"
  ([990.001(6)](https://docs.legis.wisconsin.gov/document/statutes/990.001)).
- DPI's AI guidance lists "Chapter 43.30" among the laws district AI tools must respect
  ([DPI Policy & Governance](https://dpi.wi.gov/imt/ai-guidance/administrators/policy);
  [DPI Toolkits](https://dpi.wi.gov/imt/ai-guidance/educators/toolkits)).
- `[VERIFY]`: no court decision or Attorney General opinion on whether 43.30 reaches a
  public school library was found.

**If 43.30 applies.** A record that indicates who used a library service may be disclosed only
by court order, to people "acting within the scope of their duties in the administration of
the library," to people the individual authorizes, to custodial parents of a child under 16
(43.30(4)), or to law enforcement for surveillance records. The server holds nothing that
indicates identity, which satisfies 43.30 on its own terms. Identification is the open
question: once a Roster entry is joined to a transcript, a Counselor who learns the identity
is arguably not "administering the library." Under 118.125(2)(d) that same disclosure is
plainly allowed. **Counsel should decide how the two statutes interact for Identification.**

## COPPA (15 U.S.C. 6501-6506; 16 CFR Part 312)

[16 CFR 312.2](https://www.ecfr.gov/current/title-16/section-312.2) defines an *operator*
as one who runs a website or online service "operated for commercial purposes." It excludes
"any nonprofit entity that would otherwise be exempt from coverage under Section 5 of the
Federal Trade Commission Act." The FTC's FAQ says COPPA "applies to commercial websites and
online services and not to nonprofit entities"
([FTC COPPA FAQ, B.5](https://www.ftc.gov/business-guidance/resources/complying-coppa-frequently-asked-questions)).
A public school district running its own Install with no vendor, no advertising, and no sale
is not operating "for commercial purposes." `[VERIFY: no FTC statement found that addresses a
public school district acting as its own operator.]` The definition also speaks of "a website
located on the internet or an online service," which an intranet-only Install arguably is
not. Counsel need not rely on that second argument.

**How the ADRs answer it.** ADR-0001 says never to add a commercial operator. ADR-0006 keeps
the Install off the internet. If a district later points the Answer lane at a commercial API,
COPPA applies to that vendor. The school can then consent as the parent's agent only "in the
educational context" (FTC FAQ, N.1). DPI's vetting checklist would also return: a signed
data privacy agreement, no training on student data, and deletion at contract end. With no
vendor, those three are met by construction.

## Context only: Common School Fund (Wis. Stat. 43.70(3))

[43.70(3)](https://docs.legis.wisconsin.gov/document/statutes/43.70) limits library aid to
library books and instructional materials. It adds that "a school district may use the moneys
... to purchase school library computers and related software if the school board consults
with the person who supervises the school district's libraries." The hardware must be housed
in the school library, and the district must keep purchase records and report them to the
state superintendent. This is a funding rule, not a privacy rule. The earlier plan also cited
PI 8.01(2)(h) and a long-range library plan as conditions `[VERIFY]`.

## Summary

| Rule | What it needs | Design answer | Left to the district |
|---|---|---|---|
| FERPA | Access within 45 days; no destruction during a request; internal disclosure only for legitimate interest | Names never on the server; daily Purge; Holds (ADR-0003 addendum) | Setting Holds; annual notice |
| 118.125 | Confidentiality; board-adopted written retention rule | Same; Identification only between licensed staff | Adopt `retention-policy.md` as a rule; class 1 notice |
| 43.30 (if it applies) | Identity-revealing use records disclosed only on listed grounds | The server holds no identity | Counsel's view on Identification |
| COPPA | Applies to commercial operators | No vendor; intranet only | Keep it that way |
