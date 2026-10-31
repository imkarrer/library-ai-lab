# Librarian handout, decks, IT sheets, and lessons

Every document here shares one look:

- [`demo-deck.md`](demo-deck.md), nine 16:9 slides that lead into the live demo, styled by
  [`deck.css`](deck.css). Its "Meet the cast" slide introduces the people `./stack up` seeds
  (`DEMO_CAST` and `DEMO_STUDENTS` in [`scripts/stack.py`](../../scripts/stack.py)); a test
  fails if the two drift apart.
- The two sheets for district IT, kept with the other school templates and built here in
  the handout's look: [`it-network-request.md`](../templates/it-network-request.md) (let
  student devices reach the Mac when client isolation blocks them) and
  [`it-https-rollout.md`](../templates/it-https-rollout.md) (optional HTTPS, one
  certificate upload in Google Admin). The assistant's IT kit page fills in the HTTPS one
  for a given Mac.
- Each lesson of the AI literacy unit, kept with the teacher's guide in
  [`docs/curriculum/`](../curriculum/ai-literacy-unit.md): `lesson-N-deck.md`, slides to teach
  from with what to say in the speaker notes, and `lesson-N-handout.md`, a two-sided sheet
  each student keeps. Blanks on the front match the words in bold on the slides.
- The handout, below.

The handout is a four-page, US Letter take-home summary for school librarians at a talk or
conference. It assumes no GitHub and no technical background. The source is
[`librarian-handout.md`](librarian-handout.md), a [Marp](https://marp.app/) document styled by
[`handout.css`](handout.css) and configured by `.marprc.yml`.

Its colours and fonts come from the assistant's own palette,
[`library_assistant/static/palette.css`](../../library_assistant/static/palette.css), which
`.marprc.yml` registers as a Marp theme: change a colour there and the handout and the app's
pages change together.

The toolchain (Marp, a browser, make) is this directory's own Flox environment, apart from the
repo root's, which a librarian installs and which should not carry a browser. From this
directory:

```bash
flox activate -- make          # every document into build/, each .pdf and .html
flox activate -- make serve    # live preview at http://localhost:8080, reloads on save
flox activate -- make check    # fails if any page or slide runs off its bottom edge
flox activate -- make clean
```

Run `make check` on the machine that prints: the fonts are local, so a page that fits on one
machine can spill on another.

The PDFs here are not committed: build them fresh before printing. `./stack materials` from the
repo root builds and checks everything without starting the assistant.

The pipeline builds every document on each pull request, on a Mac so the fonts match, and keeps
the result as a downloadable artifact on the run. On `main`, it also commits changed lessons to
`library_assistant/static/materials/`, and staff download them at `/staff/lessons`.

**Before printing:** fill in "Get in touch" on page 4, and check "Where things stand" is still
true. Everything the handout claims has to be true on the day it's handed out.

**Before teaching a lesson:** a school counselor reviews Lesson 4's deck and handout, and the
AI Use Tier names in Lesson 5 match your district's. Change either source if not, and rebuild.
