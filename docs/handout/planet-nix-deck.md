---
marp: true
theme: deck
paginate: true
footer: 'Library Assistant · Planet Nix'
---

<!-- _class: lead -->
<!-- _paginate: false -->
<!-- _footer: '' -->

# An AI for kids that fits in one manifest

<p class="lede">A school library's research helper: two local LLMs, no names, no cloud, on one
Mac Studio that sits on the library shelf.</p>

<p class="muted">Isaac Karrer · I work at Flox · source available: github.com/imkarrer/library-ai-lab</p>

<!--
Say up front that I work at Flox. This is a personal project, not a product.
-->

---

## Why a library, and why Wisconsin

<div class="cards">
<div class="card-panel">
<h3>It started at home</h3>
<p>My wife is a middle school librarian in Wisconsin. This is built for her library
first, and for the way she already teaches research.</p>
</div>
<div class="card-panel">
<h3>Libraries teach checking</h3>
<p>A librarian, a catalog of real sources, and an adult whose job is teaching students to
check what they read. That's where an AI for kids belongs.</p>
</div>
<div class="card-panel">
<h3>Wisconsin has the money</h3>
<p>The Common School Fund, a land-grant endowment in the state constitution, made a record
$73.5M distribution to school libraries: books, software, and computers.</p>
</div>
</div>

<div class="box">

The catch: the computer must be **housed in the library** (Wis. Stat. 43.70(3)). So the
whole product is one Mac on a shelf, never a server in the district datacenter.

</div>

<!--
Wisconsin is unusual: about 35 states give school libraries no direct aid. Texas's Permanent
School Fund pays for technology and instructional materials; New York pays $6.25 a pupil for
library materials. Wisconsin is the only one I found where library money buys the computer.
Eligibility is each district's call with DPI's School Library Education Consultant; we
designed to the statute, we don't certify it.
-->

---

## The problem is not the model

- Students already use chatbots, **under accounts with their names on them**.
- **No adult in the building** sees a worrying question.
- Schools that want something better can't run a cluster, hire an ML engineer, or
  **send pupil records to a vendor**.

<div class="box">

**Purpose-built for one Mac Studio on a library shelf.** We write for Apple silicon only:
its unified memory runs a real model on a quiet box with no GPU card, no rack, and no IT.

</div>

The person who installs it is the **school librarian**. They will never type `nix` and
won't call IT, so whatever we ship has to keep running with nobody who built it in the
room.

---

## What it does

<div class="steps">
<div class="card-panel"><strong>A Card</strong><p>A Student scans a QR code with a number on
it. The assistant never learns a name.</p></div>
<div class="card-panel"><strong>An answer</strong><p>An overview from the answer model, then
real books from the school's own catalog.</p></div>
<div class="card-panel"><strong>Oversight</strong><p>A second, small model screens every
message and raises a Flag for an adult.</p></div>
<div class="card-panel"><strong>Purge</strong><p>Every conversation is deleted at the end of
the school day.</p></div>
</div>

<p class="muted">The privacy design is the product. Each promise is an ADR, and the ADRs bind
every PR.</p>

---

## Three constraints that are really packaging problems

| Promise | What it means for the build |
|---|---|
| Stays in the building | **Offline after one setup.** Fetched once, then never again, with two planned exceptions. |
| Gone every day | **No prompt logs anywhere**, including inside the model server. |
| One thing to keep running | **One environment** with its services, not a stack of installers. |

<div class="box">

**The two exceptions:** product updates and HTTPS certificate renewal (Let's Encrypt, its
own ADR). Both use one short outbound window the Mac's firewall opens roughly monthly, only
to named hosts, with Students paused. The app's internet self-check treats that window, and
only it, as expected.

</div>

<p class="muted">"Offline", "no logs" and "one thing" are properties of the closure, not of the
Python.</p>

---

## The whole Install

```toml
[install]
python.pkg-path = "python312"
uv.pkg-path = "uv"
llama-cpp = { pkg-path = "llama-cpp", systems = ["aarch64-darwin"] }
ollama = { pkg-path = "ollama", systems = ["aarch64-darwin"] }

[hook]
on-activate = '''
  # a venv in $FLOX_ENV_CACHE, rebuilt only when requirements change
'''

[services.assistant]
command = 'exec "$FLOX_ENV_CACHE/venv/bin/python" -m library_assistant'

[services.model]
command = 'exec llama-server --host 127.0.0.1 --no-slots ...'
```

<p class="muted">Abridged. <code>./stack up</code> starts the assistant and both Ollamas from
this environment.</p>

---

## Policy you can grep for

```toml
# No -v, --log-prompts-dir, or --slot-save-path, and --no-slots (ADR-0003):
# the model server keeps no log or cache of a question.
# 127.0.0.1 only (ADR-0006).
exec llama-server --host 127.0.0.1 --port 8080 --no-slots ...
```

- A **privacy reviewer** reads the manifest, not a wiki page.
- The **confidentiality scan** runs in the same gate as the tests
  (`flox activate -- bash scripts/check.sh`), locally and in CI.
- The demo, the dev box and CI **activate the same environment**.

<!--
If there's time: the same environment does three jobs. It is the Install (the assistant and
the model servers as flox services). It is the gate: ruff, the confidentiality scan, and
~750 tests, with a fake model and a fake catalog so UX work doesn't wait on a GPU. And a
second, small environment builds this deck and the librarian's handout (Marp and a pinned
Chrome), kept apart on purpose so a school's Install never pulls in a browser.
-->

---

## The models come from the manifest too

- Catalog **`ollama`**, built with Metal: both models on the GPU, ~59 tokens/s, the same
  as the Mac app.
- **Two instances**, one per model, so screening never waits on answering. Both on
  127.0.0.1.
- `ollama serve` **calls ollama.com at startup** unless told not to. One variable turns it
  off, and a test makes sure it stays off.

```toml
[install.ollama]
pkg-path = "ollama"
pkg-group = "models"        # flox upgrade models: the model servers move on their own
systems = ["aarch64-darwin"]
```

```python
"OLLAMA_HOST": f"127.0.0.1:{port}",  # loopback only
"OLLAMA_NO_CLOUD": "1",              # no call home
```

<!--
If asked about llama.cpp: it's still in the environment as a fallback server. If asked how we
found the startup call: by reading what the package does once it was in the manifest. A
package that phones home by default is the reason to want egress declared, next slide but one.
-->

---

## Offline is a supply-chain problem

- **One online moment**: activate the environment, fetch the models, build the catalog.
  After that, the Mac talks to the internet only in the update and renewal window.
- The **store paths are the bill of materials.** What ran in the demo is what runs in the
  school.
- Updates are a new generation, **not a person driving to the school**.

<p class="muted">At the venue there is no internet either: the demo runs on a travel router
and this laptop.</p>

<!--
The demo runs on an M5 Pro MacBook: the same Apple silicon and unified memory as the Studio
a school would buy, just less of it. The school's Studio gets the most memory the budget
allows; that's what decides which models it can run.
-->

---

## What I'd ask of the ecosystem

<div class="cards">
<div class="card-panel">
<h3>Declared egress</h3>
<p>Which hosts a package may reach, stated with the package, so "phones home at startup" is
found by a check, not by reading source.</p>
</div>
<div class="card-panel">
<h3>Models as inputs</h3>
<p>Weights are multi-GB, hashed, and fetched once. They want to be pinned like any other
input.</p>
</div>
<div class="card-panel">
<h3>Policy in the closure</h3>
<p>"No logs, loopback only" should be a property you can check, not a comment you trust.</p>
</div>
</div>

---

<!-- _class: lead -->
<!-- _paginate: false -->
<!-- _footer: '' -->

# Let's see it.

<p class="lede">Period 3 is about to scan in. Ms. Overdue is on watch.</p>

<p class="muted">github.com/imkarrer/library-ai-lab · the ADRs are in docs/adr</p>
