# Check the Source: an AI literacy unit for the Library Assistant

A five-lesson unit for grades 6-8, taught in 45-minute library periods, alongside a class's
first supervised use of the Library Assistant. Students learn what a language model is and is
not, why it can be confidently wrong, and how a Citation lets them check it against a real
book on a real shelf. They also learn, honestly and without scare tactics, what the assistant
knows about them and who can see what they type.

**Status: draft for review.** Written for a working middle school librarian to review, change,
and teach. Nothing here has been taught yet. Items marked `[VERIFY]` need a person to confirm
them before use. Vocabulary follows [`CONTEXT.md`](../../CONTEXT.md); in student-facing text
the terms are explained the first time they appear.

---

## Before you teach this

The unit assumes the Install is running and these are in place. Do not start Lesson 1's
hands-on part until they are.

- **The escalation protocol is adopted** and you know who works the Flag queue and how fast
  (bead lib-9v7). Students will be told that some messages reach a counselor. That has to be
  true on the day you say it.
- **A school counselor has reviewed the Watchlist** (bead lib-sdo). See
  [ADR-0004](../adr/0004-flags-assist-adults.md): the Watchlist is the only source of an
  immediate Supportive reply.
- **The Catalog is your own collection**, not the Library of Congress demo Catalog. Lessons 2
  and 3 send students to the shelf; a Citation to a Record you don't own teaches the wrong
  lesson. (See "What the unit needs from the product" at the end.)
- **The Teacher has minted a Batch** for the class with an expiry that covers the period, and
  keeps the Roster. Students never write their names anywhere in the assistant.
- **You have a staff demo Batch** (Class label such as "Staff demo") so you can project the
  assistant without using a student Card.
- **You have prepared the Lesson 3 answer set** (below) from your own Catalog, a day or two
  before.

### Pacing and the one-box limit

The assistant runs on one machine in the building. A supervised class with 4-6 questions in
flight at once is what it serves well; 25 students pressing Enter together will wait close to
a minute for the first word ([ADR-0009](../adr/0009-supervised-use-not-whole-school.md)).
Every hands-on activity in this unit is therefore built for **groups of 4-5 sharing one
Card**, which keeps about six Sessions active. This is also better teaching: one student
types, one reads the answer aloud, one follows the Citation, one goes to the shelf.

If a group shares a Card, the Teacher records the whole group against that Card number in the
Roster.

### Where this sits with DPI guidance

Wisconsin DPI's [AI Guidance Hub](https://dpi.wi.gov/imt/ai-guidance/wisconsins-dpi-ai-guidance-hub)
describes a human-AI-human workflow: a person sets the purpose, AI assists, a person reviews
and owns the result ([DPI glossary](https://dpi.wi.gov/imt/ai-guidance/glossary), "H → AI →
H"). Its [Ethical Use in the Classroom](https://dpi.wi.gov/imt/ai-guidance/educators/ethical-use)
page gives a four-step classroom routine: **Question, Check, Compare, Decide**. This unit uses
that routine as its verification habit, so students hear the same words other Wisconsin
teachers use.

DPI's glossary also defines the two ideas the unit is built on: a **hallucination** is
"confident but incorrect or fabricated AI output", and **RAG** (retrieval-augmented
generation) is a technique "where the model looks up documents first, then writes using those
sources", which "reduces hallucinations". The Library Assistant's Grounded answers are RAG over
your Catalog. Reduces, not removes: that gap is what Lesson 3 is about.

---

## Unit at a glance

| Lesson | Title | Students leave able to... | Hands-on |
|---|---|---|---|
| 1 | What is this thing? | Explain that a language model predicts likely next words, and why that can sound sure while being wrong | Card talk; first questions in groups |
| 2 | Follow the Citation | Tell an answer's two parts apart, and trace Books in our library from Citation to Record to call number to shelf | Citation relay to the stacks |
| 3 | Catch it being wrong | Use Question, Check, Compare, Decide to sort overview claims into checked, wrong, and not in our books | Answer audit against the shelf |
| 4 | Who sees what I type? | Say what the Card is, what the assistant does not know, who can see questions, and what happens to a worrying message | Scenario sort, no assistant needed |
| 5 | Using AI on assignments | Read an assignment's AI Use Tier and write an honest disclosure line | Tier sort; disclosure for their Lesson 3 work |

If you only get four periods, fold Lesson 5 into the last 15 minutes of Lesson 4 and hand the
Tier sort to the classroom teacher.

### Standards

The unit maps to the **Wisconsin Standards for Information and Technology Literacy (2025)**,
adopted by the State Superintendent in 2025 and published December 2025
([DPI ITL standards page](https://dpi.wi.gov/imt/it-literacy-standards);
[standards document, .docx](https://dpi.wi.gov/media/27176)). They replace the 2017 ITL
standards. The 2025 document has no grade bands. Each performance indicator has three
progression levels, Exploring (`.e`), Developing (`.d`), and Implementing (`.i`), and the
district decides which level fits which grade. This unit targets **Developing** for grades
6-8. `[VERIFY]` that your district has adopted the 2025 ITL standards (local adoption is
voluntary in Wisconsin) and agrees that Developing is the right level for your grades.

| Code | Wisconsin ITL 2025 performance indicator (quoted) | Lessons |
|---|---|---|
| IA1.a.d | "Examine and compare emerging technologies by analyzing their purpose, potential impact, advantages and limitations..." | 1, 3 |
| IA2.a.d | "Use a guided inquiry-based process to generate questions and demonstrate a variety of search strategies to access information in multiple formats." | 2 |
| IA2.b.d | "Demonstrate the ability to evaluate a variety of information sources for accuracy and validity, bias, and credibility, recognizing the need for multiple viewpoints." | 3 |
| IA2.c.d | "Organize and cite selected information independently, utilizing a recognized format and demonstrating an understanding of attribution." | 2, 5 |
| DC1.a.d | "Demonstrate responsible online behaviors by evaluating information (including AI-generated) and protecting personal data." | 1, 3, 4 |
| DC1.b.d | "Compare sources of online content and evaluate their purpose, authorship, and potential bias." | 3 |
| DC1.c.d | "Demonstrate awareness of emotional and social impacts of digital engagement, using tools and strategies for self-regulation." | 4 |
| DC2.a.d | "Apply ethical behavior when using digital tools by giving credit and avoiding plagiarism, including with AI generated content." | 5 |
| DC2.b.d | "Explain how generative AI, machine learning, and large language models function in various sectors and discuss its potential societal impacts." | 1 |

Where it helps, the unit also maps to the **AASL Standards Framework for Learners** (2018),
quoted from the [framework chart](https://ride.ri.gov/Portals/0/Uploads/Documents/Instruction-and-Assessment-World-Class-Standards/Other-Subjects/180206-AASL-framework-for-learners-2.pdf)
(a copy hosted by the Rhode Island Department of Education; AASL's own site is
[standards.aasl.org](https://standards.aasl.org/)). AASL published a
[second edition in September 2025](https://www.ala.org/news/2025/09/aasl-announces-publication-second-edition-national-school-library-standards-learners)
that keeps the six Shared Foundations. `[VERIFY]` that the competency codes below are
unchanged in the second edition.

| Code | AASL learner competency (quoted) | Lessons |
|---|---|---|
| I.A.1 | "Formulating questions about a personal interest or a curricular topic." | 1, 2 |
| IV.A.3 | "Making critical choices about information sources to use." | 2, 3 |
| IV.B.3 | "Systematically questioning and assessing the validity and accuracy of information." | 3 |
| V.A.2 | "Reflecting and questioning assumptions and possible misconceptions." | 1, 3 |
| VI.A.3 | "Evaluating information for accuracy, validity, social and cultural context, and appropriateness for need." | 3 |
| VI.B.2 | "Acknowledging authorship and demonstrating respect for the intellectual property of others." | 5 |
| VI.D.3 | "Inspiring others to engage in safe, responsible, ethical, and legal information behaviors." | 4 |

---

## Lesson 1: What is this thing?

### Objectives

Students will be able to:

- Describe a language model as a program that writes by predicting likely next words, learned
  from a very large amount of text.
- Name two things it is not: a search engine that looks facts up, and a person who knows them.
- Explain in their own words why it can sound sure and still be wrong.
- Point to the "this can be wrong, check the source" banner and say what it asks them to do.

### Materials

- Projector with the assistant open on a staff demo Card.
- Printed group Cards from the Teacher's Batch (one per group of 4-5).
- Sentence strips for the warm-up (below), or a whiteboard.
- Exit ticket half-sheets.

### Plan (45 minutes)

1. **Warm-up: finish the sentence (7 min).** Write sentence starts on the board and have the
   class call out the next word:
   - "Once upon a ..."
   - "Peanut butter and ..."
   - "The capital of Wisconsin is ..."
   - "The author of *[a title in your collection]* is ..."

   The first three come fast and are almost always the same. The last one splits the room, and
   some guesses will be confident and wrong. Say: *"You just did what a language model does.
   You picked the word that usually comes next. When you'd seen the pattern a lot, you were
   right. When you hadn't, you still answered. Some of you sounded sure."*

2. **What a language model is (8 min).** Plain version for the board:
   > A language model read an enormous amount of text and learned which words tend to follow
   > which. When you ask it something, it writes an answer one piece at a time, each time
   > picking a likely next piece.

   Then two "is not" statements:
   - **It does not look things up** unless something hands it sources. On its own it is
     remembering patterns, not checking facts.
   - **It does not know when it is wrong.** It sounds the same when it is right and when it is
     guessing. People call a confident wrong answer a *hallucination*.

   Ask: *"If it sounds equally sure either way, how could you tell?"* Collect answers. Land on:
   you check it against something real.

3. **How this assistant is different (5 min).** Project the assistant. Point out:
   - The **banner**: "this can be wrong, check the source." It never goes away, on purpose.
   - Every answer has **two parts**. First, a short overview the model writes from what it
     already knows. That part can be wrong and has no Citations: it is the model talking.
     Then **Books in our library**: real books from *our library's Catalog* that match the
     question, each with a **Citation** (title and call number) taken straight from the
     Catalog, so none of them is made up. (Lesson 2 is all about these.) If the library has
     nothing, it says so: "The library's catalog has nothing on this yet."
   - It runs on a computer in this building. Your questions don't go to a company on the
     internet.

   Ask one live question on the demo Card, such as "Do we have any books about the Titanic?"
   Read the overview aloud, then point at Books in our library without opening them yet.

4. **Card talk (7 min).** Before any student scans anything, the short version of Lesson 4.
   Keep it calm and matter-of-fact:
   - *"This Card lets your group use the assistant for this period. It has a number on it.
     It does not have your name in it, and the assistant never learns your name."*
   - *"The librarian can see the questions people ask, with the Card number. That's so I can
     help, the same way I can see what you're looking at when you ask me at the desk."*
   - *"Ask it about books and topics. Don't type your full name, address, or phone number into
     it, or anyone else's."*
   - *"The Card stops working at the end of the period."*
   - *"We'll talk more about what happens to what you type in a later lesson."*

5. **First questions in groups (12 min).** Hand out one Card per group. Roles: *typer*,
   *reader* (reads the answer aloud), *checker* (looks at the Citations), *recorder*. Rotate
   after each question. Each group asks two questions:
   - One about a topic they care about: "What do we have about ...?"
   - One readers'-advisory question: "I liked *[title]*. What should I read next?"

   The recorder writes down, for each answer: did it have Citations? How many? Did it sound
   sure?

6. **Exit ticket (6 min).** See below. Collect Cards.

### Formative check

Exit ticket, three items:

1. True or false, and why: "If the assistant sounds really sure, the answer is right."
2. Finish the sentence: "A language model writes by ..."
3. The banner says "this can be wrong, check the source." What is *the source*? (Looking for:
   the Record or the book it cited, not "the internet" or "the AI".)

Item 3 tells you who is ready for Lesson 2 and who needs the Record idea retaught.

### What to watch for

- **"So it's useless?"** Some students swing from trusting it completely to dismissing it.
  Name the middle: you can ask it about almost anything, math included, and the overview is
  often a good start, but it can be wrong about anything too. The books it lists are real and
  are how you check. Checking is how you use it well, not a sign that it's broken.
- **"It's alive / it's thinking."** Don't argue philosophy. Return to the warm-up: it is very
  good at next words. Ask what it would need to *know* something.
- **Personal details in questions.** Watch the Live view during step 5. If a student types a
  full name or other identifying detail, it is a teaching moment, not a discipline one.
- **Testing the edges.** Middle schoolers will try to make it say something rude or silly.
  Expect it and redirect. If a message is about hurting themselves or someone else, or about
  being hurt, follow the escalation protocol. Treat it as real until the counselor says
  otherwise, even if the student says they were joking.
- **Slow answers.** If answers take a long time, too many Sessions are asking at once. Stagger
  groups rather than switching to individual Cards.

---

## Lesson 2: Follow the Citation

### Objectives

Students will be able to:

- Identify the two parts of an answer: the overview (the model's own words, no Citations) and
  Books in our library (real Records, each with a Citation).
- Open a Citation and read the Record: title, author, subjects, summary, call number.
- Use the call number to find the book on the shelf and confirm it is what the Record says.
- Explain the difference between "the assistant said it" and "the Record says it".

### Materials

- Projector with the assistant on the staff demo Card.
- One Card per group of 4-5.
- "Citation trail" worksheet (one per group): columns for *question*, *what the answer
  claimed*, *Citation title*, *call number*, *found on shelf? (Y / checked out / not there)*,
  *does the book match the claim?*
- Access to your regular Catalog search (OPAC) as a backup for books that are checked out.

### Plan (45 minutes)

1. **Recall (4 min).** Ask two or three students to answer Lesson 1's exit ticket item 3 aloud.
   Fix the idea: the source is the Record, and behind the Record is a real book.

2. **Anatomy of an answer (10 min).** On the projector, ask a question you already know the
   answer to, from your collection. Walk through it slowly:
   - Read **part 1, the overview.** Underline each claim on the board ("Volcanoes form where
     ...", "The biggest eruption was ..."). Say: *"These are the model's own words. Nothing here
     has a Citation, on purpose. That's why the banner is there."*
   - Read **part 2, Books in our library.** Open each Citation. Show the Record: title, author,
     subjects, summary, call number. Say: *"These came straight from our Catalog. The assistant
     didn't write them, so they can't be made up. They're real books we own."*
   - Following a Citation works on part 2: it takes you to a real book. Checking part 1 means
     taking its claims to those books, which is Lesson 3.
   - Point out what a Record is **not**: it is a description of a title, not the book itself,
     and it does not say whether the book is on the shelf right now.

3. **Model the trail (5 min).** Walk to the shelf with one call number while the class watches
   (or narrate it with a photo if the stacks are out of sight). Pull the book. Read the back
   cover or table of contents aloud. Does it match what the assistant said?

4. **Citation relay (20 min).** Groups ask the assistant three questions from a short list
   you give them, chosen so Books in our library will list books you own. For each answer:
   - the *reader* reads the overview aloud,
   - the *checker* opens the Citations under Books in our library and copies the title and
     call number,
   - the *runner* goes to the shelf,
   - the *recorder* fills in the Citation trail.

   If the book is checked out, the runner checks your OPAC instead and marks "checked out".
   That still counts: the Record is real.

5. **Debrief (6 min).** Ask: *"Did every book in Books in our library turn out to be real? Did
   the books seem to be about what the overview said?"* Collect examples on the board. Save
   any overview claim the books didn't back up for Lesson 3.

### Formative check

Hand each student a printed answer with two Citations (prepared from your Catalog) and ask:

1. Which part of this answer is the model's own words, and which part came from our Catalog?
2. Write the call number you would walk to.
3. Circle one claim in the overview. Which book from Books in our library would you check it
   against?

### What to watch for

- **Treating the Citation as the proof.** A Citation proves the book is real and that we own
  it. It does not prove the overview is right: the overview was written before the books
  were found. Students who stop at "it listed books" are ready for Lesson 3.
- **"The book isn't there."** Checked-out books, mis-shelved books, and lost books all happen.
  Use it: the Record told you the library owns it, the shelf told you where it is today. Those
  are different questions, and the assistant can't answer the second one.
- **Runners wandering.** Give runners a time limit per trip; the relay works better with a
  steady pace than with long searches.
- **Readers' advisory answers.** "Books like *Wonder*" answers are opinions built from Records
  (subjects, summaries). They can be checked for *does this book exist here and is it about
  what it says*, not for *will I like it*.

---

## Lesson 3: Catch it being wrong

The heart of the unit. Students audit a set of assistant answers, some live and some prepared:
they take the claims in each overview (part 1) to the books listed under Books in our library
(part 2) and the shelf, and sort the claims by what they find.

### Objectives

Students will be able to:

- Use **Question, Check, Compare, Decide** to verify the claims in an answer's overview.
- Sort each overview claim as **checked** (a book in our library backs it up), **wrong** (a
  book contradicts it), or **not in our books** (nothing we own covers it, so it stays
  unchecked here), and recognise the honest "The library's catalog has nothing on this yet."
- Explain why the overview can be wrong even when every listed book is real.
- Say why any subject is fair to ask about, and why the books are how you check.

### Materials

- **Prepared answer set** (librarian makes this ahead; see below), printed, one set per group.
- One Card per group for the live round.
- "Answer audit" sheet: for each overview claim, *Question / Check / Compare / Decide* boxes
  and a verdict: ✔ checked (a book backs it up), ✘ wrong (a book contradicts it), ○ not in
  our books.
- Poster or slide of DPI's four steps
  ([Ethical Use in the Classroom](https://dpi.wi.gov/imt/ai-guidance/educators/ethical-use)):
  - **Question:** What does the answer claim? What might be missing?
  - **Check:** What evidence supports it? Which claims need checking?
  - **Compare:** Check it against reliable sources (here: the Record, then the book).
  - **Decide:** What is trustworthy, what needs fixing, what shouldn't be used?

#### Preparing the answer set

You need 8-10 answers, each with its Citations, drawn from your own Catalog. Collect real ones
on your staff demo Card during the week before; most will be correct. For the ones that
aren't, you have two honest options:

- **Real mistakes you caught.** Save any answer whose overview got a fact wrong that one of
  the listed books corrects. These are the best material.
- **Edited answers, labelled as edited.** Take a correct answer and change one overview claim
  (a wrong date, a wrong cause, a mixed-up name). Mark these on your key. Tell students
  afterwards which ones you edited and why: you were showing them the kinds of mistakes to
  look for. Never edit Books in our library: those come from the Catalog, and the lesson
  depends on students trusting that they are real.

Aim for a mix: overviews whose claims the books back up, two with a claim a book contradicts,
one or two with claims none of our books covers, and one where Books in our library says
"The library's catalog has nothing on this yet." That last one matters: an honest "nothing
here" is a good answer, and the overview on its own is then unchecked.

Do not try to trick the assistant into errors in front of students. It teaches that the game
is beating the machine, when the habit you want is checking it.

### Plan (45 minutes)

1. **Why real books don't make the overview right (7 min).** Recap the two parts: the model
   writes the overview from what it already knows, then the Catalog is searched and the books
   are listed. Ask: *"If every book is real, how could the answer still be wrong?"* Draw out:
   - the overview was written **before** the books were found, so nothing forced it to agree
     with them;
   - it can **sound sure** about a date, a name, or a cause and still be guessing;
   - the books can be **about the topic but not the claim**: a book on volcanoes may say
     nothing about the eruption the overview described;
   - the **Record itself** can be thin (a one-line summary), so you may need the book.

   Then the capability envelope, said plainly: you can ask it about almost any subject, math
   included, and the overview is often a useful start. It can be wrong about any of it,
   multi-step math especially, so check the steps yourself or in a book. Finding books in
   our collection and suggesting what to read next is where it is strongest, because that
   part comes straight from our Catalog.

2. **Model one audit (5 min).** Project one prepared answer that has a problem. Think aloud
   through the four steps. Land on a verdict and say why.

3. **Audit the prepared set (15 min).** Groups work through the printed set with the answer
   audit sheet. For any answer where Compare needs the book, a runner goes to the shelf.

4. **Live round (10 min).** Each group asks the assistant two questions of its own and audits
   the answers the same way. Encourage one question near the edge of the collection ("Do we
   have anything about *[topic you know you don't own]*?") to see how it handles "not found".

5. **Share and reveal (8 min).** Each group reports its most interesting verdict. Reveal the
   key, including which answers you edited. Ask: *"Which kind of mistake was hardest to
   catch?"* (Usually: an overview claim sitting above a list of real books on the same topic,
   because the books make the whole answer look checked.)

### Formative check

On one new printed answer, each student individually writes:

1. One claim from the overview.
2. Which book from Books in our library they would check it against (the Record, the book,
   or both).
3. A verdict (✔ ✘ ○) and one sentence of reasoning.

Look for students who check the claim against a book rather than just noting that books were
listed.

### What to watch for

- **Over-correction.** Some students will mark everything wrong. Ask them to show the line in
  the Record or book that contradicts the claim. "It's AI so it's probably wrong" is not a
  verdict.
- **Students who find a real error you missed.** Celebrate it, write it down, and tell whoever
  maintains the assistant (it may be a prompt or Catalog problem).
- **Low-severity Flags in the Live view.** Topic questions about history (wars, violence) or
  health can match the Watchlist at low severity. The student still gets a normal answer;
  you'll see a Flag. Close it once you've looked, per your protocol.
- **"It said the library's catalog has nothing, but I know we have that book."** Good catch:
  the search terms the model chose didn't match the words in the book's Record. Show them how
  to search your OPAC with different words. It's a lesson in search terms, not only in AI.

---

## Lesson 4: Who sees what I type?

This lesson needs no assistant time. It is about the Card, what the assistant knows, who can
see questions, and what happens when a message is worrying. Tone matters more here than
anywhere else in the unit: honest, specific, calm. The goal is that a student who needs help
is *more* likely to ask for it, not less.

### Objectives

Students will be able to:

- Explain what the Card is and what it does not contain.
- State that the assistant does not know their name, and who does know which Card they had.
- Say who can see their questions and how long questions are kept.
- Describe what happens if they type something that worries the adults, and name a trusted
  adult and the 988 Lifeline.

### Materials

- A printed sample Card (from a staff demo Batch).
- "Who can see it?" scenario cards (below), one set per group.
- The Supportive reply text, printed or on a slide. Show it; don't trigger it.
- Your school's counselor names and how to reach them.

### Plan (45 minutes)

1. **The Card, up close (8 min).** Pass around the sample Card. Ask: *"What's on it?"* (A QR
   code and a number.) Explain:
   - The QR code holds a secret that lets the Card start a **Session**, which is one Card's
     conversation with the assistant.
   - The assistant only keeps a scrambled version of that secret, plus the Card number, the
     class label ("Period 3"), and when the Card stops working.
   - **The assistant never gets your name.** Your teacher keeps a list on their own computer of
     who had which Card number. That list never goes to the assistant.
   - Cards stop working at the end of the period, or earlier if an adult turns one off.

2. **Who can see what (10 min).** Draw three columns on the board: *The assistant*, *The
   librarian*, *Your teacher's list*. Fill in together:

   | The assistant | The librarian | Your teacher's list |
   |---|---|---|
   | Your questions and its answers | Questions as they're asked, labelled "Period 3, Card 14", never a name | Which student had Card 14 |
   | The Card number and class label | The answers | Nothing you typed |
   | Not your name | Not your name, unless they ask your teacher | |

   Then, how long: *"Everything you typed is deleted at the end of the school day. The one
   exception is a message an adult needs to follow up on. That one is kept until they've
   finished."* (This is the daily Purge and the open-Flag exception,
   [ADR-0003](../adr/0003-purge-at-end-of-school-day.md).)

   And where: *"It all stays on a computer in this building. It doesn't go to a company."*

3. **When a message worries the adults (12 min).** Say it straight:
   > Sometimes people type things to a computer they wouldn't say out loud, like that they want
   > to hurt themselves, that someone is hurting them, that they're being bullied, or that
   > they're thinking about hurting someone. The assistant checks every message for things like
   > that. If it finds one, it doesn't answer the usual way. It shows a message that says to
   > talk to a counselor or a trusted adult, and gives the 988 number. And it lets the
   > librarian know, and the librarian may bring in the school counselor.
   >
   > That's not to get anyone in trouble. It's because the adults here would rather know.

   Show the Supportive reply on a slide. Then be honest about the parts that might surprise
   them:
   - **An adult can find out who had the Card.** If the librarian or counselor needs to check
     in with someone, they can ask the teacher who had that Card number. That conversation
     happens between adults, not inside the assistant.
   - **Sometimes an adult checks in even if the assistant answered normally.** Not every
     concern shows the special reply; some just let an adult know.
   - **The assistant can miss things.** It is not a counselor. If something is wrong, talking
     to a person is always the better way. Name your counselors and where to find them.

   Introduce **988**: the 988 Suicide & Crisis Lifeline. You can call or text 988, or chat at
   [988lifeline.org](https://988lifeline.org/). It is free, confidential, and open 24/7
   (per 988lifeline.org).

4. **"Who can see it?" sort (10 min).** Groups get scenario cards and decide, for each: who can
   see this, and what happens next? Suggested scenarios:
   - "A student asks for books about sharks."
   - "A student types their full name and address into a question."
   - "A student asks for books about grief because their grandpa died."
   - "A student types 'I want to disappear' and nothing else."
   - "A student asks the assistant to write their whole book report."
   - "A student shares their Card with a friend in another class."
   - "It's 4 p.m. What is still saved from this morning's questions?"

   Debrief the ones groups disagreed on.

5. **Close (5 min).** Ask each student to write the name of one adult in the building they
   could talk to. Collect anonymously or not at all; this is for them.

### Formative check

Four quick items (thumbs, whiteboards, or a half-sheet):

1. Does the assistant know your name? (No.)
2. Who can connect Card 14 to a student? (The teacher with the list, when another adult asks.)
3. When is what you typed deleted? (End of the school day, unless an adult is following up.)
4. If you or a friend are not okay, name two places to go. (A trusted adult or counselor; 988.)

### What to watch for

- **Do not demonstrate the Supportive reply live.** Typing a Watchlist phrase on a staff
  Card still raises a real Flag. Show the text on a slide. If a student tries it "to see what
  happens", follow your protocol anyway, and talk to them privately and gently afterward.
- **A student who goes quiet or asks a pointed follow-up** ("So the counselor would find out
  who?") may be asking for themselves. Answer honestly, then find a private moment. Let your
  counselor know.
- **Don't overpromise privacy.** Avoid "nobody will ever know". The accurate version is: no
  name in the assistant, the librarian sees questions, adults can find out who had a Card when
  they need to help, everything is deleted daily except what an adult is following up.
- **Don't oversell the safety net.** The Watchlist checks for phrases, and it will miss some.
  Say so. The message is "talk to a person", not "the computer will catch it".
- **Grief and hard-topic questions are fine.** A student asking for books about a death in the
  family, anxiety, or divorce is using the library well. Make sure students hear that asking
  about hard topics is welcome; the concern is about someone being in danger, not about the
  topic.

---

## Lesson 5: Using AI on assignments

### Objectives

Students will be able to:

- Read an assignment's AI Use Tier and say what it allows.
- Write a disclosure line that says what AI they used, for what, what they kept or changed,
  and how they checked it.
- Explain why disclosing is about honesty and credit, not about getting caught.

### Materials

- Tier poster (below).
- Tier sort cards: 8-10 short assignment descriptions from your partner teachers.
- Students' Lesson 3 audit sheets.
- Disclosure line half-sheets.

### The AI Use Tiers

This unit uses three tiers, matching the AUP insert planned for every Install (bead lib-oft.3):

| Tier | What it means for a student | Example |
|---|---|---|
| **Human-Only** | No AI tools for this work. Your own thinking, your own words. | An in-class quiz; a personal reflection |
| **AI-Assist** | You may use AI for a step the teacher names (brainstorming, finding sources, checking grammar). You must check what it gave you and disclose it. | Using the Library Assistant to find books for a research project |
| **AI-Optional** | You may use AI more freely, and you still disclose it and check it. You are responsible for everything you turn in. | A practice activity on how AI answers compare to sources |

Where these names come from: DPI's [Policy & Governance](https://dpi.wi.gov/imt/ai-guidance/administrators/policy)
page includes a sample "quick use matrix" that uses **"Human-Only"** for high-stakes
assessments and **"AI-assist"** for brainstorming and outlining, with disclosure required.
I could not find **"AI-Optional"** on DPI's current AI guidance pages, and DPI does not publish
the three tiers as a named set. `[VERIFY]` the tier names against your district's adopted
AUP language before teaching; if your district uses different levels (Sheboygan Area School
District's [AI Levels](https://dpi.wi.gov/sites/default/files/imce/imt/pdf/Sheboygan_Area_School_District_AI_LEVELS.pdf),
hosted on DPI's site, is one Wisconsin example), teach those instead.

### The disclosure line

Adapted from DPI's copy-ready disclosure box
([Policy & Governance](https://dpi.wi.gov/imt/ai-guidance/administrators/policy);
[Ethical Use in the Classroom](https://dpi.wi.gov/imt/ai-guidance/educators/ethical-use)),
with the wording simplified for grades 6-8:

> **AI use:** I used ______ (tool) to ______ (what for) on ______ (date). I kept ______ and
> changed ______. I checked it by ______.

Example: *"AI use: I used the Library Assistant to find books about volcanoes on March 3. I kept
two of the books it suggested and skipped one that was about earthquakes. I checked it by
finding both books on the shelf and reading their tables of contents."*

When the assignment is Human-Only, the line is: *"AI use: none."*

### Plan (45 minutes)

1. **Why disclose? (7 min).** Ask: *"When you use a quote from a book, why do you cite it?"*
   (Credit, so others can check, honesty.) The same reasons apply to AI. Add one more: AI can be
   wrong, so the reader needs to know which parts to double-check.

2. **The tiers (8 min).** Walk through the poster. Emphasize: the teacher sets the tier for each
   assignment, and it can be different from class to class. When in doubt, ask.

3. **Tier sort (12 min).** Groups read the assignment cards and decide which tier each probably
   is and why. There may not be one right answer; the reasoning is the point. Share and compare.

4. **Write a disclosure line (12 min).** Each student writes a disclosure line for their
   Lesson 3 audit work, as if it were an AI-Assist assignment. Pairs swap and check: does it
   say what tool, what for, what was kept or changed, and how it was checked?

5. **Close the unit (6 min).** Return to Lesson 1's exit ticket question: *"If the assistant
   sounds really sure, is the answer right?"* Ask students to answer again, now with a reason
   and a way to check.

### Formative check

The disclosure line itself. A complete line has all four parts: tool, purpose, kept/changed,
how checked. "How checked" is the part most often left vague ("I looked it up"); push for
specifics ("found it on the shelf at 551.21").

### What to watch for

- **Disclosure as confession.** Students may think admitting AI use means admitting cheating.
  Frame it the way citing a book is framed: what good researchers do.
- **Tier confusion across classes.** Students will hear different rules from different
  teachers. That's expected; the tier is a property of the assignment, not the student.
- **Library Assistant vs. other AI tools.** Students will ask about tools they use at home.
  The tiers and the disclosure line apply to all of them. What's different about the Library
  Assistant is that it cites your Catalog and keeps nothing past the school day; other tools may
  not do either.

---

## Background for the librarian

### What the assistant is good at, honestly

From the project's planning notes (bead lib-0ov; `docs/plan.md` at commit `68abceb`, "Quality
versus a frontier model, honestly"):

- **Catalog search and readers' advisory:** about as good as the large commercial assistants,
  because the answer depends on your Records, not on model size. When it's wrong here, the cause
  is usually a thin Record or a retrieval miss.
- **Research help and source evaluation:** a real but modest gap compared with the large
  commercial models.
- **Any subject, math included:** decided for the product (lib-f24.27). Students may ask about
  anything; the overview is the model's own words and can be wrong, multi-step math
  especially. The books listed under it are how students check, and for math, working the
  steps themselves or in a textbook.
- Transcription is mentioned in the planning notes as a strength of local models, but the
  Library Assistant does not offer it to students and this unit does not cover it. (The notes
  cite 6.32% English word error rate for Parakeet TDT v3 against 7.83% for Whisper; public
  leaderboard summaries give 7.83% for Whisper large-v3-turbo and about 7.44% for large-v3.
  `[VERIFY]` before quoting either figure anywhere.)

### What the adults can see, in product terms

For your own reference when students ask:

- **Card**: a printed QR code with one Token and a visible Card number. The assistant stores
  only the Token's hash, the Card number, the Class label, and the expiry
  ([ADR-0002](../adr/0002-cards-are-minted-on-the-teachers-machine.md)).
- **Roster**: the Teacher's record of who held which Card number. It never leaves the
  Teacher's machine. **Identification** (learning who had a Card) is always offline, between
  adults.
- **Live view**: you see questions as they arrive, labelled by Class label and Card number.
  Teacher and Counselor accounts cannot open it.
- **Flags**: a Watchlist match raises a Flag in the Flag queue. High severity: the student sees
  the Supportive reply and the model is not called. Low severity: the student gets a normal
  answer and sees nothing different. If Oversight is configured, it may raise a Flag minutes
  or hours later ([ADR-0004](../adr/0004-flags-assist-adults.md)).
- **Purge**: every transcript is deleted at the end of the school day, except those attached
  to an open Flag ([ADR-0003](../adr/0003-purge-at-end-of-school-day.md)).
- **Intranet only**: the model and the Catalog run on the school network
  ([ADR-0006](../adr/0006-intranet-only.md)).

### Further reading

- DPI, [Wisconsin's DPI Artificial Intelligence Guidance Hub](https://dpi.wi.gov/imt/ai-guidance/wisconsins-dpi-ai-guidance-hub).
- DPI, [Know the Risks: AI in PK-12 Education](https://dpi.wi.gov/digital-learning/ai-guidance/know-risks-ai-pk-12-education):
  AI "can produce information that sounds confident but is inaccurate, incomplete, outdated, or
  entirely fabricated."
- DPI, [Equity & Ethics](https://dpi.wi.gov/imt/ai-guidance/administrators/equity-ethics):
  recommends teaching "how systems rely on patterns/probabilities rather than true
  understanding" so learners can spot confident but incorrect answers.
- DPI, [Artificial Intelligence Guidance Glossary](https://dpi.wi.gov/imt/ai-guidance/glossary).

---

## What the unit needs from the product

Things this unit relies on that the current beads do not yet specify. Each is a candidate for
a bead or for a line in an existing one.

1. **Citations that show the call number.** Lessons 2 and 3 walk from Citation to shelf. lib-f24.4
   says Citations "link to" Records and lib-f24.3 gives Records a call number, but nothing says
   the call number is visible in the answer or on the Record page a Citation opens.
2. **A Catalog of the school's own collection before student use.** The demo Catalog is Library
   of Congress records (lib-f24.3, lib-f24.18). Citations to titles the library doesn't own
   break the shelf-check lessons. The reference deployment needs an adapter or import for the
   school's real Catalog before the unit runs.
3. **A way to see the Supportive reply without raising a Flag.** Lesson 4 shows students the
   exact text. lib-f24.6 defines when it appears but not its wording, and there is no staff-side
   preview, so the only way to see it is to trigger a real Flag. Needs: the final wording
   (reviewed by a counselor, per lib-sdo / lib-9v7) and a staff page that displays it.
4. **A student-facing "what happens to what I type" page.** Lesson 4's facts (no name, librarian
   sees questions, daily Purge, worrying messages reach an adult) should be one tap away in the
   Session, in plain language, so students aren't relying on memory of a lesson. Not in any bead.
5. **Plain-language text on the printed Card.** lib-f24.2's QR sheet prints the QR and Card
   number. A short line ("No name inside. The librarian can see your questions. Expires at the
   end of class.") would reinforce Lesson 1's Card talk.
6. **A "this answer looks wrong" button.** Lesson 3 trains students to catch errors; the product
   gives them nowhere to report one. A flag-for-the-librarian on an answer (separate from
   safety Flags) would close the loop and give the prompt-tuning work (lib-f24.17) real cases.
   Watch the vocabulary: this is not a **Flag** in the CONTEXT.md sense.
7. **Visible distinction between a cited claim and an uncited one.** *Answered by the
   two-part design (lib-f24.27):* the overview is uncited by design and Books in our library
   carries every Citation, so the parts themselves mark the difference. Lessons 2 and 3 now
   teach to that.
8. **Roster support for groups sharing a Card.** The unit uses one Card per group of 4-5 to stay
   inside ADR-0009's capacity. lib-f24.2's Roster template has one student column per Card
   number. It needs room for several names, or guidance that the Teacher writes them in.
9. **Banner wording, locked.** The unit quotes "this can be wrong, check the source" as the
   banner text (lib-f24.4). If the wording changes, this unit changes with it; consider
   treating it as fixed copy with a test.
10. **AI Use Tier names reconciled with the AUP insert.** lib-oft.3 adopts "DPI's AI Use Tiers
    (Human-Only / AI-Assist / AI-Optional)". DPI's current pages use "Human-Only" and
    "AI-assist" but not "AI-Optional", and do not present a three-tier set. The AUP insert and
    this unit should use the same names, and say where they come from.
11. **Expected behavior for math and off-collection questions.** *Answered by the two-part
    design (lib-f24.27):* any subject is fair, math included; the overview answers and can be
    wrong, and Books in our library lists what the Catalog has, or says "The library's catalog
    has nothing on this yet."
