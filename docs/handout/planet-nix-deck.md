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

<p class="muted">Isaac Karrer · I work at Flox · open source: github.com/imkarrer/library-ai-lab</p>

<!--
Say up front that I work at Flox. This is a personal project, not a product.
-->

---

## The problem is not the model

- Students already use chatbots, **under accounts with their names on them**.
- **No adult in the building** sees a worrying question.
- Schools that want something better can't run a cluster, hire an ML engineer, or
  **send pupil records to a vendor**.

<div class="box">

**Purpose-built for one Mac Studio on a library shelf.** We write for Apple silicon only:
its unified memory runs a real model on a quiet box with no GPU card. In Wisconsin, a school
library's Common School Fund aid can buy "school library computers and related software", if
the computer is housed in the library (Wis. Stat. 43.70(3)). A Mac on a shelf is built to
fit that; a server in the district datacenter never could.

</div>

The person who installs it is the **school librarian**. They will never type `nix` and
won't call IT, so whatever we ship has to keep running with nobody who built it in the
room.

<!--
The funding is the design constraint: the money is the library's, not IT's, and it comes
with the machine having to live in the library. That's why everything is one Mac, one
environment, and no infrastructure. Eligibility is the district's call with DPI's School
Library Education Consultant; we designed to the statute, we don't certify it.
-->

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

<p class="muted">Abridged from <code>.flox/env/manifest.toml</code>. A librarian runs
<code>flox activate --start-services</code> and that's it.</p>

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

## Where Nix fought back: the GPU

- Catalog `llama-cpp` 0.6.0 on an M5 Pro: **every request failed on Metal** with
  `kIOGPUCommandBufferCallbackErrorOutOfMemory`, at every offload setting.
- Fix #1: `--n-gpu-layers 0`. Correct answers, at **~12 tokens/s on the CPU**. Too slow for a
  room of kids.
- Fix #2: Ollama, **from a Homebrew cask**, outside the environment. Fast, two models side by
  side, and the one part of the stack Nix doesn't describe.

<div class="box">

That's the gap this talk is about closing: the models have to come from the same manifest
as everything else, or "one environment" isn't true.

</div>

---

## Closing the gap

- **What was wrong:** not the Nix build. llama.cpp 0.6.0 itself mapped the CPU's share of
  the weights into the GPU's memory. Catalog **0.7.0 runs all 49 layers on Metal**.
- **What we use:** catalog `ollama`, built with Metal: **~59 tokens/s, same as the app.** Two
  instances, one per model, both from the environment.
- **What we found on the way:** `ollama serve` calls ollama.com at startup. One variable
  turns it off, and a test makes sure it stays off.

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
Nothing needed fixing upstream: the nixpkgs recipe was the same for 0.6.0 and 0.7.0, Metal on,
embedded shader library. The catalog trails nixpkgs a few point releases; that's fine here.
The Homebrew app runs the same code, so it very likely called home too (inferred, not
observed): moving into the environment is what made us look. OLLAMA_DEBUG_LOG_REQUESTS would write prompts to disk; the stack strips it.
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
<h3>GPU on macOS</h3>
<p>Metal builds that work on the newest Apple GPUs on day one, tested on real hardware.</p>
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
