# A Supportive reply is written for its Rubric category, and staff can preview it

Proposed 2026-10-25 (lib-irf). Found while drafting the escalation protocol (section 7) and the
AI literacy unit (Lesson 4).

ADR-0004 gives a high-severity Watchlist match one fixed Supportive reply, built around 988.
That fits self-harm. It fits a child disclosing abuse or a threat to others badly, it cannot say
where *this* school's counselor is, and staff can only see it by raising a real Flag, which
Lesson 4 tells teachers never to do. So:

- **One default text per Rubric category** (self-harm, abuse, bullying, threats of violence),
  shipped as data with the assistant and reviewed like the Watchlist.
- **Install overrides.** An Install can set `{counselor}`, the line that tells a Student who the
  counselor is and where to find them. The default is "a school counselor". For each category
  it can also add one extra line (for example a state tip line) or replace the text outright.
- **Guard rails, checked at startup.** An Install whose overrides break a rule refuses to
  start and names the rule, the same way a bad Watchlist does. The self-harm text must contain
  988. Every text must name at least one adult in the building, which `{counselor}` or "the
  librarian" satisfies. Every text must stay within 120 words. A text may use only known
  placeholders.
- **One reply per message.** When one message matches high-severity entries in several
  categories, the Student gets one reply, chosen in this order: self-harm, threats of violence,
  abuse, bullying. The order puts first the replies that point to 988 and 911, where a
  minute matters most. Every matching entry still raises its own Flag.
- **A staff preview page.** Any signed-in staff account can see each category's reply,
  rendered by the same template the Student sees, with this Install's overrides. It also has a
  print view for the Lesson 4 slide. Previewing raises no Flag, writes no transcript, and calls
  no model.
- Low-severity matches stay silent, and Oversight Flags still get no reply (ADR-0004).

## Default texts

Written for 11-to-13-year-olds: short sentences, no clinical words, nothing that blames the
Student, and an honest line that an adult may check in, because Lesson 4 promises Students
that. A rough Flesch-Kincaid estimate puts each at about grade 4 (80-96 words), so a weak
reader in grade 6 can manage them. They are drafts. The reference deployment's counselor
should review them before the pilot, as section 7 of the escalation protocol expects.

**Self-harm**

> It sounds like you are going through something really hard. You don't have to handle it alone.
>
> Please talk to an adult you trust today, like {counselor} or the librarian.
>
> You can call or text **988** any time, day or night. It is free, and a real person will
> listen. If you might hurt yourself right now, tell an adult near you or call **911**.
>
> I am a library computer, so a person can help with this better than I can. An adult here may
> check in with you, because they care how you are doing.

**Abuse**

> Thank you for saying something. If someone is hurting you or making you feel unsafe, it is not
> your fault. You deserve to be safe.
>
> Please tell an adult you trust at school, like {counselor}, a teacher, or the librarian.
>
> You can also call or text the Childhelp hotline at **1-800-422-4453**, any time, day or night.
> If you are in danger right now, call **911**.
>
> An adult here may check in with you, because they want you to be safe.

**Bullying**

> That sounds really hard. Nobody deserves to be treated that way, and it is not your fault.
>
> Please tell an adult you trust, like {counselor}, a teacher, or the librarian. They can help
> make it stop. If it is happening to a friend, telling an adult is a way to help them.
>
> If it is making you feel really down, you can call or text **988** any time.
>
> An adult here may check in with you, because they want to help.

**Threats of violence**

> It sounds like someone could get hurt. That is serious. Please tell an adult right away, like
> {counselor}, a teacher, or the librarian.
>
> If you are angry or upset, an adult can help you work it out. If you are worried about someone
> else, telling an adult is the right thing to do. It is not snitching.
>
> If anyone is in danger right now, call **911**.
>
> An adult here may check in with you, because they want everyone to be safe.

The threats text is written for both the Student who is afraid and the Student who is angry,
because the Watchlist cannot tell which one typed it. It accuses no one. The abuse text says
*tell an adult at school* rather than *tell a parent*, because the person hurting the child
may be a parent.

### Numbers, and where they were checked (2026-10-25)

- **988 Suicide & Crisis Lifeline.** Call or text 988, or chat at chat.988lifeline.org. Free,
  confidential, 24/7. You "do not have to be suicidal to call", and there is a section for
  helping someone else. Source: <https://988lifeline.org/get-help/>. The site states no minimum
  age.
- **Childhelp National Child Abuse Hotline.** 1-800-422-4453 (1-800-4-A-CHILD). Call, text
  ("GO" to the same number), or chat at childhelphotline.org. Its teen page invites teens to
  call or text: <https://childhelphotline.org/teens/>. Its FY2024 impact report describes 24/7
  support:
  <https://childhelp.org/wp-content/uploads/2024/10/Ch_Hotline_2024-Impact-Report_Spread_V1.pdf>.
  The hotline's own contact pages do not state hours. Childhelp counselors give support and
  referrals and do not file reports. A report goes to the county agency, which is the school's
  job under the protocol, not the Student's.
- **Wisconsin has no statewide child-abuse hotline.** Reports go to the county or tribal
  agency where the child lives (<https://dcf.wisconsin.gov/reportabuse>). That is why county
  numbers stay in the staff protocol and out of the Student text.
- **An example Wisconsin override for threats of violence.** Speak Up, Speak Out (Wisconsin
  DOJ Office of School Safety): call 1-800-697-8761, or text "SUSO" to 738477, per
  <https://speakup.wisdoj.gov/>. Its old address, speakup.widoj.gov, now redirects there. The
  page does not state hours, so the extra line should not say "any time". It is not a
  default, because the project ships to schools in any state.

## Considered options

- **One text for every category (ADR-0004 as written).** It points a child disclosing abuse to
  a suicide line and says nothing about danger to others.
- **Texts entirely per Install, with no defaults.** Every school would write its own crisis
  text from scratch. Some would leave out 988, and the demo would have nothing to show.
- **Pick the reply with the model.** Oversight runs after the answer (ADR-0004), and an inline
  model call is what ADR-0004 rejected.

## Consequences

- lib-f24.6 can ship its single reply. The per-category texts replace it without changing the
  Watchlist format, because entries already carry a Rubric category.
- The defaults are safety-critical content, like the Watchlist. A change to them needs the
  same review, and a test pins that each default meets the guard rails.
- The Lesson 4 slide and section 7 of the escalation protocol should show the preview page's
  print view, not a pasted copy that can drift.
