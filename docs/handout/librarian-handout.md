---
marp: true
theme: handout
paginate: true
footer: 'Library Assistant · for school librarians'
---

# Library Assistant

<p class="lede">A research helper for students that runs on one computer in your school.
Students don't sign in with their names, you can see what they ask, and their questions stay
in the building.</p>

## What it does

Students type a question about whatever they're researching: snow leopards, the Dust Bowl,
fractions. The assistant writes a short overview in plain language, then lists books on that
subject from your own catalog, with call numbers.

It runs on a computer on your school network. After setup it doesn't need the internet, and
it never sends student questions to an outside company.

Students sign in by scanning a QR card with a number on it instead of a name. The teacher
keeps the list of who has which card.

You see every question as students ask it, and the assistant flags messages that suggest a
student may be at risk.

## A class period

1. The teacher prints a sheet of QR cards on their own computer. Each card has a number,
   like "card 14". The teacher keeps the list of names and numbers and gives a sealed copy to
   the office. That list never goes into the assistant.
2. Students scan their cards on their Chromebooks and start asking questions.
3. Each answer comes in two parts: what the AI knows about the topic, then books in your
   library that cover it. Every answer ends with this reminder:

<div class="quote">

This can be wrong, check the source.

</div>

4. The cards stop working at the end of the school day. The next class gets new ones.

<div class="box">

We split the answer in two on purpose. AI can sound sure of itself and still be wrong, so the
overview is only a starting point. Students check it against the books, and that sends them
to the shelves.

</div>

---

## What you see

The Live view gives you a tile for each student who's chatting. A tile shows the class, the
card number ("Period 3 · card 14"), and the latest question. It never shows a name. Click a
tile to follow that conversation as it happens.

To stop a student, turn off their card from their page, or turn off every card in the class.
The student sees "This card has stopped working. Ask your teacher for a new one." Nothing
tells them an adult did it.

## Safety

Before the AI sees a message, the assistant checks it against a list of warning phrases for
self-harm, abuse, bullying, and threats of violence. We wrote the list for the way middle
schoolers actually write, slang and misspellings included ("kms"), and your counselor can
review it. Every flag shows the phrase that triggered it.

| When a message has… | The student sees… | Adults see… |
|---|---|---|
| no warning phrase | the normal answer | the question on the Live view |
| a lower-concern phrase | the normal answer | a flag in the Flag queue |
| a serious phrase | a supportive reply instead of an answer, pointing them to a counselor or another adult they trust, and to the 988 line for self-harm | a flag, plus an alarm on your screen (a banner and a chime) that shows the class and card number but not the student's words |

We wrote the supportive replies for students, with a different one for each kind
of concern. The flags tell you who needs an adult. Someone still follows up in person, using
your school's own escalation steps.

### How closely you supervise

You pick one of three settings:

- **Live** (the default). Students can chat only while you, or another adult you've named,
  have the Live view open and have pressed Start watch.
- **Periodic review.** Students can chat any time during the school day, and you check the
  flags on a schedule you set, such as every two hours.
- **Off.** Your school's own supervision policy applies.

The phrase check and the supportive reply run under all three.

---

## Student privacy

<div class="box">

The assistant never learns which student is which. A board, a parent, or the state can check
a claim that we never had students' names. Nobody can check a claim that we deleted them.

</div>

- No names go into the system. Cards carry numbers, and the teacher keeps the list that
  matches numbers to students.
- The assistant deletes every conversation at the end of the school day. It keeps one longer
  only while an adult is still working on a flag about it, or while a legal hold applies,
  such as an open records request.
- The AI model runs on the school's computer. The assistant doesn't send questions to an AI
  company, a cloud service, or an advertiser.
- Students have no accounts or email addresses in the system, and nothing connects one day's
  questions to the next.

## What you need

- A capable computer in the building. Our demo runs on one Apple Silicon laptop. How many
  students it can serve at once depends on the machine, and a setup tool helps you pick an
  AI model that fits it.
- Help from your district's IT staff to put it on the school network. Students don't need
  internet access to use it.
- Flox, a free tool that installs the assistant the same way on any computer, so the setup
  doesn't depend on one person.
- No license fees and no per-student cost. The assistant is open source, under the Apache 2.0
  license, so anyone can read exactly what it does with student questions.

## Templates for your district

Your board and legal counsel will have questions, so the project includes draft templates
you can adapt with them:

- a privacy impact assessment
- a retention policy that explains why one school day is enough
- an insert for your acceptable-use policy
- an escalation protocol that walks adults through what to do with a flag
- an AI literacy unit for grades 6 to 8, where students follow citations to the shelf, catch
  the AI making mistakes, and learn that adults can see what they ask

---

## Questions to ask about any AI tool for students

Ask these of any AI product a vendor offers your students, including this one.

1. Where do students' questions go? Whose servers, and in which country? Does the vendor
   use them to train its AI?
2. Who can read the questions? Can school staff? Can the vendor's staff?
3. How long does the vendor keep them, and can your school delete them when it wants to?
4. Could someone identify a student from what's stored, through an account, an email
   address, a device, or a school login?
5. If a student writes something worrying, does an adult in the building find out? How
   quickly? Can someone explain why it was flagged?
6. Who decides the safety rules, and can your counselor see and change them?
7. What does the tool tell students about its own mistakes? Does it point them to sources
   they can check?

## Where the project is

We're still building the Library Assistant. Today's demo ran on one laptop, and we're
planning a first pilot in a Wisconsin middle school library. The templates are drafts that
still need legal review, so treat them as a starting point rather than legal advice.

## Contact

<!-- CONTACT: replace this paragraph with how librarians reach the project (an email
address, a web page, or a QR code to one). Do not print without it. -->
**Contact details to be added before printing.**

Share this sheet with your district's technology and privacy staff.
