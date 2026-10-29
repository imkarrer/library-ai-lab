# Librarian handout

A four-page, US Letter take-home summary for school librarians at a talk or conference. It
assumes no GitHub and no technical background. The source is
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
flox activate -- make          # build/librarian-handout.pdf and .html
flox activate -- make serve    # live preview at http://localhost:8080, reloads on save
flox activate -- make check    # fails if any page's content runs off the bottom of the page
flox activate -- make clean
```

Run `make check` on the machine that prints: the fonts are local, so a page that fits on one
machine can spill on another.

The PDF is not committed: build it fresh before printing.

**Before printing:** fill in "Get in touch" on page 4, and check "Where things stand" is still
true. Everything the handout claims has to be true on the day it's handed out.
