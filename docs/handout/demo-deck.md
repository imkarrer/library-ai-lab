---
marp: true
theme: deck
paginate: true
footer: 'Library Assistant'
---

<!-- _class: lead -->
<!-- _paginate: false -->
<!-- _footer: '' -->

# Library Assistant

<p class="lede">A research helper for students that runs on one computer in your school. No
names, adults can see every question, and nothing leaves the building.</p>

<p class="muted">An open-source project · still being built · the demo runs on this laptop</p>

---

## Students already ask AI chatbots

- Their questions go to **a company's servers**, often under an account with their name on it.
- **No adult in the building** sees what they ask.
- If a student writes something worrying, **nobody here finds out**.
- The answer sounds sure of itself, and **points them nowhere they can check**.

<div class="box">

A school library is the right place for a better version: a librarian, a catalog full of
sources, and adults whose job is to help students learn to check what they read.

</div>

---

## What it does

Students ask about whatever they're researching: snow leopards, the Dust Bowl, fractions.
Every answer comes in two parts:

1. **An overview** in plain language, from the AI.
2. **Books from your own catalog** on that subject, with call numbers.

<div class="quote">

This can be wrong, check the source.

</div>

<p class="muted">Every answer ends with that line. The overview is a starting point; the books
send them to the shelves.</p>

---

## Three promises

<div class="cards">
<div class="card-panel">
<h3>No names</h3>
<p>Students scan a QR card with a number on it. The teacher keeps the list of who has which
card, on their own computer. The assistant never sees it.</p>
</div>
<div class="card-panel">
<h3>Gone every day</h3>
<p>Every conversation is deleted at the end of the school day, unless an adult is still
working on a flag about it.</p>
</div>
<div class="card-panel">
<h3>Stays in the building</h3>
<p>The AI runs on a school computer. No question goes to an AI company, a cloud service, or
an advertiser.</p>
</div>
</div>

<p class="muted">We can't prove we deleted a name. We can show we never had one.</p>

---

## When a student needs an adult

| A message with… | The student sees… | Adults see… |
|---|---|---|
| nothing worrying | the normal answer | the question on the Live view |
| a smaller worry | the normal answer | a <span class="chip sev-low">Low</span> or <span class="chip sev-medium">Medium</span> flag, right away |
| a serious worry | a supportive reply, pointing to a counselor and, for self-harm, the 988 line | a <span class="chip sev-high">High</span> flag, a banner and a chime |

Every flag goes **New → Acknowledged → Closed**, and records who did what. Escalated, it
belongs to the counselor until they close it.

---

## "Who was card 4?"

The assistant only knows a card number. Finding the student takes two adults:

<div class="steps">
<div class="card-panel"><strong>The counselor</strong><p>opens the flag and presses <em>Ask the
teacher who held it</em>.</p></div>
<div class="card-panel"><strong>The teacher</strong><p>sees the request. Their own page looks
the name up in the class list on their computer.</p></div>
<div class="card-panel"><strong>In person</strong><p>The teacher tells the counselor, then
presses <em>I've told them</em>.</p></div>
<div class="card-panel"><strong>On the record</strong><p>The flag shows who asked, who answered,
and when. Never the name.</p></div>
</div>

<p class="muted">For a serious flag, the page says: don't wait for an answer here, go find
the teacher now.</p>

---

## Meet the cast

<div class="cards">
<div class="card-panel">
<h3>Ms. Overdue</h3>
<p><span class="chip">Librarian</span></p>
<p>Runs the library and keeps watch on the Live view. Students can chat only while she's
watching.</p>
<p><code>librarian.overdue</code></p>
</div>
<div class="card-panel">
<h3>Mr. Pop-Quiz</h3>
<p><span class="chip">Teacher</span></p>
<p>Makes Period 3's cards on his own computer, and keeps the list of who has which.</p>
<p><code>teacher.popquiz</code></p>
</div>
<div class="card-panel">
<h3>Dr. Hugsworth</h3>
<p><span class="chip">Counselor</span></p>
<p>Gets every flag that's escalated, and owns it until it's closed.</p>
<p><code>counselor.hugsworth</code></p>
</div>
</div>

**Period 3:**

<div class="roster">
<span><b>1</b>Paige Turner</span><span><b>2</b>Justin Time</span><span><b>3</b>Dot
Matrix</span><span><b>4</b>Moe Mentum</span><span><b>5</b>Anita Nap</span><span><b>6</b>Rhoda
Book</span>
</div>

<p class="muted">Every name here is made up. In a school, students' names stay on the teacher's
computer.</p>

---

## What you're about to see

<div class="steps">
<div class="card-panel"><strong>Cards</strong><p>Mr. Pop-Quiz makes Period 3's cards. Two
volunteers scan in as Paige and Justin.</p></div>
<div class="card-panel"><strong>Questions</strong><p>They research an animal. Ms. Overdue
watches the questions and answers arrive live.</p></div>
<div class="card-panel"><strong>A flag</strong><p>Paige types something worrying. Her phone
gets a supportive reply; the screen rings.</p></div>
<div class="card-panel"><strong>Follow-up</strong><p>Ms. Overdue escalates. Dr. Hugsworth
asks Mr. Pop-Quiz who held card 1.</p></div>
</div>

<div class="box">

**Volunteers:** join the Wi-Fi we hand you, keep questions to school research, and remember
the whole room can see them.

</div>

---

<!-- _class: lead -->
<!-- _paginate: false -->
<!-- _footer: '' -->

# Let's see it.

<p class="lede">Ms. Overdue is about to start watch.</p>

<p class="muted">Afterwards: take the handout. It has the questions to ask about any AI tool
for students, including this one.</p>
