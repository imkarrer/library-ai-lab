# SLATE session proposal: AI in the school library, without sending student data away

A draft concurrent-session proposal for [SLATE](https://slateinwi.com/), the Wisconsin school
technology conference run by AWSA (bead lib-4p8). It is written for school leaders and
librarians, not engineers, and reuses the story of the technical talk
([`flox-for-edu.md`](flox-for-edu.md), bead lib-cpa).

**Status: draft.** The target is **SLATE 2027**, because the 2026 call has closed (see
"Timing" below). SLATE doesn't publish its form fields or word limits, so the fields below
follow what the published program shows for each session, and the limits are guesses marked
`[VERIFY]`. Presenters are `[BLANK]`. Vocabulary follows [`CONTEXT.md`](../../CONTEXT.md), with
terms explained in plain language for this audience.

---

## What SLATE asks for, as far as we can confirm

Checked 2026-10-25.

| Item | What we found | Source |
|---|---|---|
| Conference | December 7-9, 2026, Kalahari Resort, Wisconsin Dells: a pre-conference day on Monday, then two main days | [slateinwi.com](https://slateinwi.com/), [schedule](https://slateinwi.com/schedule/) |
| Concurrent session length | 60 minutes. Four rounds on Tuesday and two on Wednesday morning | [schedule](https://slateinwi.com/schedule/) |
| Other formats | Pre-con sessions of 3-4 hours on the Monday | [schedule](https://slateinwi.com/schedule/), [pre-con sessions](https://slateinwi.com/pre-con-sessions/) |
| How to propose | A Qualtrics form titled "SLATE Call for Proposals", linked from "Being a Presenter". That page still says "Call for Proposals for 2024 is now open!", but the form reports "not currently active" | [being a presenter](https://slateinwi.com/being-a-presenter/), [form](https://survey.az1.qualtrics.com/jfe/form/SV_1YMRApjF8WCNok6) |
| 2026 deadline | "Submissions Due April 4, 2026", in SLATE's call email of February 26, 2026, which DPI's CS and digital learning consultant forwarded to a Wisconsin teachers' list | [forwarded call](https://groups.google.com/g/wi-csandit-teachers/c/FAtUHKXAFek) |
| Audience | "Classroom, school, and district leaders" | [being a presenter](https://slateinwi.com/being-a-presenter/) |
| Fields each session shows in the program | Title, presenters, grade range, experience level (Novice, Intermediate, Advanced, Tech Professional), track (DATL = Digital Age Teaching & Learning; LPD = Leadership & PD), audience codes, and a description | [2026 concurrent sessions](https://slateinwi.com/2026-concurrent-sessions/) |
| Audience codes | DA District Administrator, SA School Administrator, CI Curriculum & Instruction, IC Instructional Coach, IT IT Director/Coordinator, TI Technology Integrators, LMS Library Media Specialist, GE Teachers/All Educators | [2026 concurrent sessions](https://slateinwi.com/2026-concurrent-sessions/) |
| Title and abstract word limits | Not published | `[VERIFY]` on the 2027 form |
| Learning objectives required? | Not published | `[VERIFY]` on the 2027 form |
| Do presenters pay registration? | Not stated. The attendee fee is $299, not including pre-cons | [registration](https://slateinwi.com/registration/), `[VERIFY]` |
| Rules for vendor-affiliated presenters | Not published. Vendors such as Apple, Google, and CDW do present concurrent sessions | [2025 concurrent sessions](https://slateinwi.com/2025-concurrent-sessions/), `[VERIFY]` |

### Comparable sessions in recent programs

- **2026** ([program](https://slateinwi.com/2026-concurrent-sessions/)): about 35 of more than
  100 sessions are about AI. The closest to ours are #206, "Everyone is Talking AI - What Are
  School Libraries Bringing to the Conversation?" (LPD, audience SA, DA, IT, LMS, GE); #512,
  "The AI Journey: Bridging the Gap Between Staff Needs and Student Safety" (LPD, Novice); and
  #503, "From Guidance to Practice: AI Implementation in Wisconsin Schools" (DATL).
  Privacy comes up only inside other topics, such as #112 and #509 on IEP writing.
- **2025** ([program](https://slateinwi.com/2025-concurrent-sessions/)): about 82 sessions. We
  found none on locally hosted or offline AI, and none on open source.

So AI and libraries are both familiar topics at SLATE. **AI that runs inside the building and
keeps student text there is not.** That is the session's angle. Lead with it, and don't
present it as one more AI tool.

---

## The proposal

### Title

**AI in the School Library, Without Sending Student Data Away**

Alternatives:
- "Who Can See What Students Ask? A Library AI Built for the Adults in the Building"
- "Our Library's AI Lives in the Building: Privacy, Oversight, and a Live Demo"

### Short description (about 40 words, for the printed program)

A middle school librarian and an engineer demonstrate a library AI assistant that runs on one
computer in the building. Students sign in with an anonymous QR card, adults see every
question, and nothing is sent to a vendor.

### Abstract (152 words; the limit is `[VERIFY]`)

Most AI tools for students send every question to a company's servers, and leave librarians
and counselors with no view of what students ask. We'll show another way: an open-source
library assistant that runs on a single computer in the building and, once installed, needs
no internet. Students scan a short-lived QR card that carries no name, then ask about the
library's own collection, and each answer points to a real book they can find on the shelf.
The librarian watches questions as they arrive. A fixed, reviewable list of warning phrases
flags messages a counselor needs to see, and conversations are deleted at the end of each
school day. A middle school librarian and the engineer who built it will run it live, then
walk through the FERPA and Wisconsin pupil-records reasoning, the escalation protocol, and an
AI literacy unit. You'll leave with free templates for your own board and counsel.

**If the live demo isn't ready when the proposal is due**, replace "will run it live" with
"will show a recorded run," and say why in the session.

### Learning objectives

Participants will be able to:

1. Explain the difference between AI tools that send student questions to a vendor and an
   assistant that keeps them on the school's own network, and the questions to ask a vendor
   about each.
2. Describe three safeguards a school can require of any student-facing AI tool: anonymous
   access, short retention, and flags that adults can review and explain.
3. Adapt the session's open templates (a privacy impact assessment, a retention rule, an
   acceptable-use insert, an escalation protocol, and an AI literacy unit) for their own
   district's review.

### Session details

| Field | Proposed value |
|---|---|
| Format | 60-minute concurrent session |
| Track | LPD (Leadership & PD). DATL is the fallback if the reviewers see it as an instructional session |
| Grade range | 6-12. The unit and the reference library are middle school; the design is not grade-specific |
| Experience level | Novice. No technical background needed |
| Audience codes | LMS, SA, DA, IT, CI |
| Equipment | Projector and screen with HDMI, power at the front, one table. **No venue Wi-Fi needed.** The demo brings its own offline network |

### Presenters

- `[BLANK: presenter 1, name]`, `[BLANK: title]`, `[BLANK: school and district]`: a middle
  school library media specialist in Wisconsin, who leads the session and presents the
  Teacher's and the Librarian's view.
- `[BLANK: presenter 2, name]`, `[BLANK: title]`, `[BLANK: organization]`: the engineer who
  built the assistant. **Disclose the affiliation:** this presenter works at Flox, the company
  whose free tool installs the assistant. The assistant itself is open source and
  free, and nothing is sold in the session.

Contact details go on the form only, not in this repository.

### Biographies (`[BLANK]`, about 50 words each)

- `[BLANK: presenter 1 bio. Lead with years as a school librarian and the grades served]`
- `[BLANK: presenter 2 bio. Lead with the open-source project and say where they work]`

---

## Running order for the 60 minutes

| Minutes | Segment | Who |
|---|---|---|
| 0-5 | Why this matters to us: what students ask a library AI, and who can see it | Librarian |
| 5-12 | The choice most schools are offered: vendor chatbot or nothing | Both |
| 12-30 | **Live demo:** mint Cards for a class, a volunteer scans one and asks, the Live view, a Flag, Revoke, the end-of-day Purge, all with the internet off | Both |
| 30-40 | What the adults do with a Flag: the escalation protocol, and the duty-of-care point that flags support people, they don't replace them | Librarian |
| 40-47 | The paperwork your board will ask for: FERPA, Wis. Stat. 118.125, the retention rule, the AUP insert | Engineer |
| 47-52 | Teaching students to check the source: the AI literacy unit | Librarian |
| 52-60 | Questions, and where to get the templates | Both |

The demo beats, and the rule against typing a real disclosure on stage, are in
[`flox-for-edu.md`](flox-for-edu.md#demo-beats). For this audience, explain flox in one
sentence: "a free tool that installs the assistant the same way on any of the school's
computers, so it doesn't depend on the one person who set it up."

## What the session can honestly show

Each item in the abstract has to be true by the session date, or be cut:

- **Live demo:** depends on lib-f24.9, which is not built as of 2026-10-25.
- **Templates:** exist in [`docs/templates/`](../templates/) as drafts awaiting counsel review.
  Call them drafts in the session.
- **AI literacy unit:** exists in [`docs/curriculum/ai-literacy-unit.md`](../curriculum/ai-literacy-unit.md)
  but hasn't been taught. If it has been taught by December 2027, say so. Otherwise don't
  imply it has.
- **A school using it:** the Reference deployment is planned, not running. Mention it only if
  the district has agreed by the proposal deadline `[VERIFY]`, and never name students or
  show real Flags.

---

## Timing

- **SLATE 2026 is closed to proposals.** Its call went out on February 26, 2026 and closed on
  April 4, 2026 ([forwarded call](https://groups.google.com/g/wi-csandit-teachers/c/FAtUHKXAFek)).
  The program for December 7-9, 2026 is already published
  ([sessions](https://slateinwi.com/2026-concurrent-sessions/)).
- **Target SLATE 2027.** If AWSA follows the 2026 pattern, the call opens in late February
  2027 and closes in early April 2027, for a conference in December 2027 `[VERIFY: 2027 dates
  and deadline; ask the AWSA office through the SLATE contact page,
  https://slateinwi.com/contact-form/, in January 2027 rather than waiting for the email]`.
- **Work back from the deadline:**
  - By **January 2027**: lib-f24.9 passes on the M5 Pro with networking off, and the demo is
    recorded.
  - **January to March 2027**: give the technical talk (lib-cpa) at a smaller event, so the
    proposal can say the session has been given before.
  - By **mid-March 2027**: the co-presenter's district has approved her presenting, the
    `[BLANK]` fields are filled in, and the abstract's word count is checked against the real
    form.
  - **Submit by late March 2027**, a week before the expected deadline.
- **Before then: attend SLATE 2026 (December 7-9, 2026)** if possible. Sit in on #206 (school
  libraries and AI) and #512 (staff needs and student safety), and note how many seats AI
  sessions fill and what questions leaders ask. Registration is $299
  ([registration](https://slateinwi.com/registration/)).
