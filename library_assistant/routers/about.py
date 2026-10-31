"""The Student's "What happens to what I type" page (lib-bns).

Plain language for a Student, drawn from Lesson 4 of the AI literacy unit
(docs/curriculum/ai-literacy-unit.md) and kept true to the design: the Card holds no name
(ADR-0002), questions are deleted at the end of the school day unless an adult is following
up or the school must keep them (ADR-0003), nothing leaves the school (ADR-0006), and a
worrying message gets a caring reply and tells an adult (ADR-0004, ADR-0011). No Session
is needed to read it, so a Student can read it before signing in.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from library_assistant.access import NO_STORE

ABOUT_PATH = "/about"

ABOUT_PAGE_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="/library.css">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<title>What happens to what I type</title>
</head>
<body>
  <h1>What happens to what I type</h1>

  <h2>Your Card</h2>
  <p>The QR code on your Card holds a secret code that lets you start a chat. The
  assistant keeps only a scrambled copy of that code, your Card number, your class (like
  "Period 3"), and when the Card stops working. A Card stops working by the end of the
  school day, or sooner if an adult turns it off.</p>

  <h2>Your name</h2>
  <p>The assistant never gets your name. Your teacher keeps a list of who had which Card
  number, and that list never goes to the assistant.</p>
  <p>If an adult needs to check in with you, they can ask your teacher who had your Card
  number. That happens between adults, not inside the assistant.</p>

  <h2>Who can see your questions</h2>
  <p>The librarian, and any staff member the librarian asks to help, can see your
  questions and the answers as you chat. They see your class and Card number, not your
  name. A school counselor sees a question only if the librarian asks them to help with
  it.</p>

  <h2>How long it is kept</h2>
  <p>Everything you type is deleted at the end of the school day. There are two
  exceptions: a message an adult is still following up on is kept until they have
  finished, and the school keeps messages longer if the law requires it.</p>
  <p>It all stays on a computer in this school. It does not go to a company or out to
  the internet.</p>

  <h2>If you type something worrying</h2>
  <p>The assistant checks every message for signs that someone could be in danger: that
  you want to hurt yourself, that someone is hurting you, that you are being bullied, or
  that someone might hurt another person. If it finds one, it does not answer the usual
  way. It shows a message asking you to talk to an adult you trust, and it lets the
  librarian know. The librarian may bring in a school counselor. Sometimes an adult
  checks in even when the assistant answered normally.</p>
  <p>That is not to get anyone in trouble. The adults here would rather know.</p>
  <p>The assistant can miss things. It is not a counselor. Asking about hard topics, like
  grief, worry, or a family change, is welcome; that is what libraries are for.</p>

  <div class="help">
    <p><strong>If you or a friend are not okay, talk to a person.</strong> A trusted adult
    at school, like a school counselor, a teacher, or the librarian, can help.</p>
    <p>You can call or text 988 any time, day or night. It is free, and a real person will
    listen. If someone might get hurt right now, tell an adult near you or call 911.</p>
  </div>
</body>
</html>
"""

router = APIRouter()


@router.get(ABOUT_PATH)
def about_page() -> HTMLResponse:
    """What the Card holds, who sees questions, the daily Purge, and what a caring reply
    means, for Students. No Session needed."""
    return HTMLResponse(ABOUT_PAGE_HTML, headers=NO_STORE)
