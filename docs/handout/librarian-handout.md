---
marp: true
theme: handout
paginate: true
footer: 'Library Assistant · a take-home summary for school librarians'
---

# Library Assistant

<p class="lede">An AI research helper for students that lives on one computer in your
building. Students stay anonymous, you see what they ask, and nothing is sent to a
company.</p>

## The idea in one minute

- **Students ask it anything** they're researching: snow leopards, the Dust Bowl, how
  fractions work. It gives a short, plain-language overview, then lists **books in your own
  library** on that subject, with call numbers.
- **It runs inside the school.** One computer on the school network does all the work. Once
  it's set up, it needs no internet, and student questions never leave the building.
- **No student accounts, no names.** Students sign in by scanning a QR card that carries a
  number, not a name. Only the teacher knows which student holds which card.
- **The adults stay in the loop.** You see every question as it's asked. Messages that
  suggest a student may be at risk are flagged for an adult the moment they arrive.

## What a class period looks like

1. **The teacher prints a sheet of QR cards** for the class on their own computer. Each card
   has a number ("card 14"). The teacher keeps the list of who has which card, and a sealed
   copy goes to the office. **That list never goes into the assistant.**
2. **Students scan their card** on their Chromebook and start asking.
3. **Each answer has two parts:** what the AI knows about the subject, and the books in
   your library to check it against. Every answer carries the reminder:

<div class="quote">

This can be wrong, check the source.

</div>

4. **Cards stop working by the end of the school day.** Tomorrow's class gets new cards.

<div class="box">

**Why the two parts?** The overview is a starting point, and AI can be confidently wrong.
The books are how students check it, which turns every question into a lesson in verifying
sources and a trip to the shelves.

</div>

---

## What you see as the librarian

**The Live view** shows one tile for each student who is chatting, labelled by class and
card number ("Period 3 · card 14"), never by name. Each tile shows their latest question.
Click a tile to watch that conversation as it happens, answers and all.

From a student's page you can **turn off their card** ("Revoke"), or the whole class's
cards. The student just sees *"This card has stopped working. Ask your teacher for a new
one."* They aren't told an adult switched it off.

## Keeping students safe

**Every message is checked before the AI sees it** against a list of warning phrases for
self-harm, abuse, bullying, and threats of violence. The list is written for how middle
schoolers actually talk (slang, misspellings, "kms"), and your school's counselor can review
it. Each flag says which phrase matched, so it can always be explained.

| If a message… | The student gets… | The adults get… |
|---|---|---|
| matches nothing | the normal answer | the question on the Live view |
| matches a lower-concern phrase | the normal answer | a **Flag** waiting in the Flag queue |
| matches a serious phrase | a **supportive reply** instead of an answer: talk to a counselor or trusted adult, and the **988** line for self-harm | a Flag, and an **alarm** on the librarian's screen: a banner and a chime, showing the class and card number but **never the student's words** |

The supportive reply is written for 11-to-13-year-olds, and different for each kind of
concern. The flags **help the adults do their duty of care; they don't replace it.** An adult
follows up in person, using the school's own escalation steps.

### You choose how closely to supervise

- **Live** (the default): students can chat only while you, or another adult you've
  named, has the Live view open and has pressed **Start watch**.
- **Periodic review:** students can chat any time in the school day, and you review the
  flags on a schedule you set, such as every two hours.
- **Off:** supervision is left to your school's own policy.

In every mode, the warning-phrase check and the supportive reply stay on.

---

## Student privacy, by design

<div class="box">

The assistant is built so that it **never knows which student is which.** "We never had it"
is a promise a board, a parent, or the state can check. "We deleted it" is not.

</div>

- **No names anywhere in the system.** Cards carry a number. The list linking numbers to
  students stays with the teacher, with a sealed copy in the office.
- **Conversations are deleted at the end of every school day.** The only exceptions: an
  exchange attached to an open flag, which an adult is still working on; and records under a
  legal hold, for example while a records request is pending.
- **Nothing leaves the building.** The AI model runs on the school's own computer. No
  student question is sent to an AI company, a cloud service, or an advertiser.
- **Nothing to track students with.** There are no student accounts, no email addresses,
  and no history that follows a student from day to day.

## What it takes to run

- **One capable computer in the building.** The demo you saw runs on a single laptop
  (an Apple Silicon Mac). How many students can ask at once depends on the machine; a
  built-in tool will help pick the right AI model for the hardware you have.
- **Your district's IT team,** to put it on the school network. Students need no internet
  for it to work.
- **Flox,** a free tool that installs the assistant the same way on any computer, so it
  doesn't depend on the one person who set it up.
- **No license fees and no per-student pricing.** The assistant is free.

## The paperwork kit

Your board and counsel will have questions. The project comes with **draft templates** to
adapt with your district's own counsel:

- a privacy impact assessment
- a retention rule (why one school day is enough)
- an acceptable-use policy insert
- an escalation protocol: what adults do with a flag, step by step
- an AI literacy unit for grades 6 to 8: teaching students to follow the citation, catch the
  AI being wrong, and know that adults can see what's asked

---

## Questions to ask about any AI tool for students

Whether or not you ever use this assistant, these questions are worth asking of any AI
product a vendor offers your students:

1. **Where do students' questions go?** To whose servers, in which country? Are they used to
   train the vendor's AI?
2. **Who can read them?** Can school staff see what students ask? Can the vendor's staff?
3. **How long are they kept,** and can the school delete them on its own schedule?
4. **Can a student be identified** from what's stored: by account, email, device, or
   school login?
5. **What happens when a student says something worrying?** Does an adult in the building
   find out, how fast, and can anyone explain why it was flagged?
6. **Who reviews the safety rules,** and can your counselor see and change them?
7. **What do students see** when the AI might be wrong? Does it point them to sources they
   can check?

## Where things stand

The Library Assistant is new and still being built. What you saw today is a working demo
on one laptop. A first pilot in a Wisconsin middle school library is planned. The templates
are drafts waiting for legal review: treat them as a starting point, not legal advice.

## Get in touch

<!-- CONTACT: replace this paragraph with how librarians reach the project (an email
address, a web page, or a QR code to one). Do not print without it. -->
**Contact details to be added before printing.**

Bring this sheet to your district's technology and privacy conversations. The questions on
this page work for any AI tool, not just this one.
