# Demo runbook: the M5 Pro conference demo

The step-by-step for showing the Library Assistant live at a librarian conference: the
presenter's M5 Pro MacBook runs everything, the room has no internet, and two volunteers chat
as Students on their own phones while the presenter screen-shares the Live view. Vocabulary is
[`CONTEXT.md`](../CONTEXT.md)'s. Binding: [ADR-0006](adr/0006-intranet-only.md) (nothing
reaches the internet at demo time; the model and the Catalog are fetched once, online,
beforehand) and [ADR-0010](adr/0010-student-sessions-run-only-on-watch.md) (Students chat only
while an adult is on Watch).

Two kinds of step. **Presenter** steps set up the machine: the install, the model, the
network, starting the assistant. They use Terminal, as whoever installs the assistant at a
school would. **Librarian** and **Teacher** steps are what school staff do, and they happen
only in a browser: no Terminal, no script. Show those on stage exactly as written.

**Shortcut:** `./stack up --lan` does the Presenter's part of Steps 2 and 5 in one command
(accounts, settings, Make Cards prefilled for the Teacher, both Ollamas, warming both models,
the assistant on the LAN address), and `./stack down` stops it; see `README.md`, "Running
it". The steps below are what it does, by hand, for when something needs doing differently.

**The cast.** `./stack up` seeds the people the deck
([`handout/demo-deck.md`](handout/demo-deck.md)) introduces, so the names on screen match the
slides. Sign in as `librarian.overdue` (Ms. Overdue) where the steps say `librarian`, use
`teacher.popquiz` (Mr. Pop-Quiz) for `demo-teacher`, and `counselor.hugsworth` (Dr.
Hugsworth) for the Counselor. His Make Cards (`./stack status` prints the address, ending
`/staff/mint/`) opens with Class Label `Period 3` and a made-up class: Paige Turner, Justin
Time, Dot Matrix, Moe Mentum, Anita Nap, Rhoda Book. So does his offline copy,
`teacher.popquiz-minting-page.html` in the stack folder. Volunteer 1 plays Paige (card 1),
volunteer 2 plays Justin (card 2).

Follow it in order. Steps 1 to 3 happen at home, online, days before. Steps 4 to 7 happen at
the venue, offline, before the audience arrives. Steps 8 to 14 are the demo itself. Commands
are for macOS's Terminal (zsh) and are run from the repo root unless a step says otherwise.

Lines marked **GAP** are things the demo needs that the code does not do yet, or does wrongly,
as of this runbook. Each says what to do instead. The full list is at the end. Re-check them
before the trip: some are being built now.

The examples use `192.0.2.10` for the laptop's LAN address. That is a documentation address;
yours is whatever the travel router hands out. Nothing about a real school's network, and no
key or password, belongs in this file or anywhere in this repo.

## Step 1. Online setup: environment, model, Catalog, disk

Do this at home, online, on the M5 Pro. Everything here downloads; nothing after Step 3 may.

1. Check free disk. The model is about 14 GB, the Catalog about 150 MB (its build needs about
   400 MB while running), and the flox environment a few GB. Want at least 30 GB free:

   ```bash
   df -h "$HOME"
   ```

2. Get the code you will demo, and make sure it is the version you will rehearse with. Do not
   `git pull` after Step 3: a change to `requirements.txt` makes the next activation try to
   install from PyPI, which fails offline.

   ```bash
   cd ~/src/library-ai-lab        # wherever your checkout is
   git switch main && git pull
   ```

   Run every later command from this same folder. The model is cached inside the checkout
   (`.flox/cache/models/`), so a second checkout or worktree does not see it.

3. Activate once, online. The first activation installs Python, uv, Ollama, llama.cpp,
   and the Python packages (from PyPI). It prints `Installing Python packages...` the first
   time.

   ```bash
   flox activate -- python3 -c "import fastapi, uvicorn, qrcode, httpx; print('env ok')"
   ```

4. Get the demo models. The M5 Pro runs both Lanes on the environment's own Ollama
   (`ollama` in the manifest, from the Flox catalog), on the GPU: about 59 tokens/s on
   `gpt-oss:20b`, the same as Ollama.app. Pull the models once, online (about 14 GB and
   3.4 GB) into `~/.ollama/models`, which every Ollama on this Mac shares. Pulling needs a
   server running, so this starts a temporary one on a spare port and stops it after:

   ```bash
   flox activate -- bash -c 'export OLLAMA_HOST=127.0.0.1:11499
     ollama serve >/dev/null 2>&1 & s=$!; sleep 3
     ollama pull gpt-oss:20b && ollama pull qwen3.5:4b; kill $s'
   ```

   `gpt-oss:20b` (Apache-2.0) answers in 3 to 8 seconds here and writes the `SEARCH:` line
   the Catalog search reads. Measured on this Mac and rejected: `qwen3.6:27b` (18 GB, does
   not fit in 24 GB beside everything else) and `qwen3.5:4b` (faster, but slips on the
   `SEARCH:` line; it screens for Oversight instead). Each Ollama listens on `127.0.0.1`
   only and keeps no log or copy of a question (`~/.ollama/cache` holds only its model
   list).

   The flox model server (llama.cpp) is the fallback: fetch its model with
   `flox activate -- bash scripts/fetch_demo_model.sh` (about 19 GB; it ends with
   `Verified: ...gguf`) and see Step 5, "Without Ollama".

5. Build the demo Catalog from Library of Congress records (ADR-0006's one demo exception:
   about 3 GB of downloads, one part at a time, around 20 minutes on a fast line). It writes
   `catalog.db` at the repo root, which `.gitignore` keeps out of git.

   ```bash
   flox activate -- python3 scripts/build_demo_catalog.py --dest catalog.db
   ```

   It keeps only books with a call number a school librarian would recognize (a Dewey
   number, E, FIC, or B, then three letters of the author: `599.74 LEP`), and swaps the new
   `catalog.db` in only when it finishes. If loc.gov drops the connection mid-part, it stops
   with `EOFError: Compressed file ended before the end-of-stream marker was reached`.
   Re-run the same command: it skips the parts already loaded (`marc-dist-download/done.txt`)
   and resumes.

   **Already have a `catalog.db` from an older build** (call numbers like `QL737.C22 W45`)?
   Clean it and seed it again; the old one keeps working until the new one is done, then
   restart the stack (`./stack down && ./stack up --lan`):

   ```bash
   flox activate -- python3 scripts/build_demo_catalog.py --dest catalog.db --fresh
   ```

   When it finishes, check it answers a search:

   ```bash
   flox activate -- python3 -c "
   from library_assistant.catalog.sqlite_backend import SqliteCatalog
   c = SqliteCatalog.open('catalog.db')
   for r in c.search('wolves', 5): print(r.call_number, r.title)"
   ```

6. Check the disk again: `du -sh catalog.db ~/.ollama/models` and `df -h "$HOME"`.

## Step 2. Online setup: the Librarian, accounts, supervision mode

Set up the demo's database once, at home, and keep a clean copy of it to reset to between
runs (Recovery, "Reset between runs"). The database lives outside the repo, in a folder only
you can read, because it will hold the accounts' password hashes and, during a demo, the
volunteers' questions.

1. **Presenter.** Make the demo folder and its settings file. `$PWD` is expanded now, so run
   this from the repo root:

   ```bash
   mkdir -p ~/library-assistant-demo && chmod 700 ~/library-assistant-demo
   cat > ~/library-assistant-demo/demo.env <<EOF
   export DEMO_DIR="$HOME/library-assistant-demo"
   export LIBRARY_ASSISTANT_DB="$HOME/library-assistant-demo/demo.db"
   export LIBRARY_ASSISTANT_CATALOG_PATH="$PWD/catalog.db"
   export LIBRARY_ASSISTANT_DEMO=1
   export LIBRARY_ASSISTANT_OPENAI_ENDPOINT=http://127.0.0.1:11436/v1
   export LIBRARY_ASSISTANT_OPENAI_MODEL=gpt-oss:20b
   export LIBRARY_ASSISTANT_OPENAI_REASONING_EFFORT=low
   export LIBRARY_ASSISTANT_OVERSIGHT_ENDPOINT=http://127.0.0.1:11435/v1
   export LIBRARY_ASSISTANT_OVERSIGHT_MODEL=qwen3.5:4b
   export LIBRARY_ASSISTANT_OVERSIGHT_REASONING_EFFORT=none
   EOF
   ```

   The three `OPENAI` lines point the Answer lane at its Ollama's `gpt-oss:20b`, on port
   11436 (Step 5).
   `REASONING_EFFORT=low` matters: without it the model thinks silently for most of a minute
   before its first word. The three `OVERSIGHT` lines turn on the Oversight Lane: a second,
   small model that screens every message for what the Watchlist's phrases miss ("Billy says
   I stink and makes me cry" is a bullying Flag from Oversight, not from the Watchlist). It
   runs on a second Ollama (Step 5). Its `REASONING_EFFORT=none` matters more: without it
   `qwen3.5:4b` spends its whole reply thinking, returns no verdict, and Oversight reports
   itself down. Step 1 pulled it.

   `LIBRARY_ASSISTANT_DEMO=1` adds the demo Watchlist entry
   (`library_assistant/watchlist-demo.toml`): the phrase **library demo flag**, Rubric category
   self-harm, severity high. It is the only phrase ever used to raise a Flag on stage. Never
   ask a volunteer to type a real disclosure or anything from the real Watchlist.

2. **Presenter.** Start the assistant on this machine only, for setup. It runs in this
   Terminal tab until you press Ctrl-C, which stops it within two seconds even with staff
   pages open:

   ```bash
   source ~/library-assistant-demo/demo.env
   flox activate -- python3 -m library_assistant
   ```

   **GAP (lib-f9o):** start the assistant this way, not with `flox services start assistant`.
   A flox service does not see the variables `demo.env` exports, so it would write its
   database to `library_assistant.db` in the repo, without the demo Watchlist or the Catalog,
   and at the venue it would listen on `127.0.0.1` where no phone can reach it.

   In a second tab, check the assistant took the settings. This file must exist:

   ```bash
   ls -la ~/library-assistant-demo/demo.db
   ```

   If it is missing, stop the assistant and fix this before creating any account: an account
   made now would land in the wrong database.

3. **Librarian**, in a browser. Open `http://127.0.0.1:8000/staff/login`. With no accounts
   yet it sends you to `/staff/setup`. Create the Librarian: username `librarian`, a password
   you will remember on stage. This signs you in, and `/staff` links to every page below.

4. **Librarian.** Open **Accounts** and add two with **Add account**:
   - `demo-teacher`, role **Teacher** (the Teacher who makes the demo Cards; its name shows
     as "Registered by" on the Flag).
   - `demo-counselor`, role **Counselor** (so the Flag page offers **Escalate**; optional).

   Do not use a real person's name for either. The Librarian account cannot be removed (it is
   the Install's only way back in); to start over, see Recovery, "Start setup over".

5. **Librarian.** Open **Install settings** and set:
   - **Supervision mode: Live.** It is the default and the one the demo shows: Students chat
     only while someone is on Watch, so End watch visibly pauses them (Step 13).
   - **Watch grace seconds: 300.** The default 90 is right for a library; on stage, 300 gives
     slack for a slow tab switch or a screen-share hiccup. End watch is still immediate.
   - **Oversight down: Carry on.** If the Oversight Lane stops answering, Students keep
     chatting, screened by the Watchlist alone (Recovery, "Oversight is down").
   - Leave **Session idle minutes** at 0, **Alarm chime** On, **Alarm repeat seconds** 30.

   Press **Save**. The page lists the change under "Recent changes".

6. **Librarian.** Open **Supportive reply preview** and read the four replies, so you know
   what the volunteer will see in Step 9.

7. **Presenter.** Stop the assistant (Ctrl-C in its tab), then keep the clean copy:

   ```bash
   cp -f ~/library-assistant-demo/demo.db ~/library-assistant-demo/clean.db
   ```

## Step 3. Rehearse offline at home

Do the whole demo once at home under the venue's conditions, then reset. This is the only way
to catch a missing download before you are offline for real.

1. Set up the travel router with **no uplink** (no cable in its WAN port, no tethering). Turn
   off the router's client isolation (often called "AP isolation"), or phones cannot reach the
   laptop. If the router can reserve an address for the laptop, reserve one: the Cards' QR
   codes carry the laptop's address, so it must not change between minting and the demo.
2. Join the laptop to the router's Wi-Fi. Turn off any other network (Ethernet, phone
   tethering, VPN).
3. Run Steps 4 to 14 with two phones, start to finish. Pick three or four animals that return
   Records from your Catalog and note them for the volunteers (Step 8).
4. Reset (Recovery, "Reset between runs").

## Step 4. Day of: go offline, bind to the LAN address, and verify nothing leaves

"Offline" means no internet, not no network: the volunteers' phones must reach the laptop.

1. Plug in the travel router (still no uplink). Join the laptop to its Wi-Fi and turn off
   every other network. Set the Mac's time zone by hand if you crossed one (System Settings,
   General, Date & Time): offline, the Mac cannot update it, and the assistant's school day is
   computed from it below.
2. Keep the laptop awake for the whole talk, in its own terminal tab. A sleeping laptop stops
   answering heartbeats and its Watch lapses:

   ```bash
   caffeinate -dis
   ```

3. Write today's settings. `TALK_END` is when your slot ends, 24-hour, local time. It is both
   the Cards' expiry and the assistant's end of school day, so it must be later than now:

   ```bash
   cat > ~/library-assistant-demo/today.env <<EOF
   export LIBRARY_ASSISTANT_SCHOOL_TIMEZONE="$(readlink /etc/localtime | sed 's|.*/zoneinfo/||')"
   export TALK_END=15:00
   export LIBRARY_ASSISTANT_SCHOOL_DAY_END=15:00
   export LAN_IP="$(ipconfig getifaddr en0)"
   EOF
   cat ~/library-assistant-demo/today.env
   ```

   Edit both `15:00`s to your slot's end. Check `LAN_IP` is not empty (it is the Wi-Fi
   address, for example `192.0.2.10`) and `LIBRARY_ASSISTANT_SCHOOL_TIMEZONE` is an IANA name
   such as `America/Chicago`.

4. Verify there is no internet. This must print the second message:

   ```bash
   curl -sS -m 5 -o /dev/null https://example.com && echo "INTERNET REACHABLE: fix before going on" || echo "No internet: good"
   ```

The check that nothing the assistant runs talks to anything but the laptop and the phones is
in Step 5, once the services are up.

## Step 5. Start the services

**Presenter.** Each Lane gets an Ollama of its own, from the flox environment, so neither
Lane waits on the other (ADR-0004): the Answer lane's on `127.0.0.1:11436`, the Oversight
Lane's on `127.0.0.1:11435`. Not Ollama's default 11434, so an Ollama.app or LaunchAgent
left on 11434 cannot answer in their place. Four Terminal tabs, all at the repo root: tab 1
runs both Ollamas, tab 2 the assistant, tab 3 is for checks and warming, tab 4 spare.

Tab 1, enter the environment and set what both Ollamas share:

```bash
flox activate
unset OLLAMA_DEBUG OLLAMA_DEBUG_LOG_REQUESTS
export OLLAMA_NO_CLOUD=1 OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1 \
  OLLAMA_KEEP_ALIVE=30m OLLAMA_FLASH_ATTENTION=1
```

`OLLAMA_NO_CLOUD=1` matters: without it `ollama serve` asks ollama.com for model
recommendations as it starts, which an Install must never do (ADR-0006). The debug variables
are unset because `OLLAMA_DEBUG_LOG_REQUESTS` writes request bodies, questions included, to
the log (ADR-0003 addendum). Then start the two, sharing the downloaded models:

```bash
OLLAMA_HOST=127.0.0.1:11436 OLLAMA_CONTEXT_LENGTH=16384 ollama serve &
OLLAMA_HOST=127.0.0.1:11435 OLLAMA_CONTEXT_LENGTH=4096 ollama serve
```

The first is the Answer lane's, in the background; the second is the Oversight Lane's. Leave
the tab running: Ctrl-C stops the Oversight Ollama, then `kill %1` stops the other.

Tab 3, warm both models so the first question is quick:

```bash
curl -s http://127.0.0.1:11436/v1/chat/completions -H 'content-type: application/json' \
  -d '{"model":"gpt-oss:20b","messages":[{"role":"user","content":"Say ready."}],"reasoning_effort":"low"}' \
  | grep -o '"content":"[^"]*"'
curl -s http://127.0.0.1:11435/v1/chat/completions -H 'content-type: application/json' \
  -d '{"model":"qwen3.5:4b","messages":[{"role":"user","content":"Say ready."}],"reasoning_effort":"none"}' \
  | grep -o '"content":"[^"]*"'
curl -s http://127.0.0.1:11436/api/ps; curl -s http://127.0.0.1:11435/api/ps
```

The first calls take 10 to 15 seconds while the models load; Ollama keeps them loaded for 30
minutes after the last question (`OLLAMA_KEEP_ALIVE`), so warm them again if the demo starts
later than that. Both fit on the GPU together (about 12.8 and 3.2 GB of the 24), measured
here: a screen takes about a second and the answer's first words still come in about 0.3
seconds. That leaves little memory free, so quit memory-hungry apps first.

**Without Ollama** (fallback): run the flox model server (llama.cpp) instead. It uses the GPU
too, at about 24 to 32 tokens/s against Ollama's 59, but takes nearly all of the GPU's
working set (about 17.8 GiB), so it cannot run beside either Ollama: stop tab 1 (or
`./stack down`) first. With no Oversight Ollama, Oversight is down (Recovery, "Oversight is
down"). `demo.env`'s three `OPENAI` lines must be removed so the assistant uses it:

```bash
flox activate
flox services start model
until curl -s http://127.0.0.1:8080/health | grep -q ok; do sleep 5; done; echo model ready
```

Tab 2, the assistant, bound to the LAN address, with the demo Watchlist on (as in Step 2, not
as a flox service; GAP lib-f9o):

```bash
source ~/library-assistant-demo/demo.env && source ~/library-assistant-demo/today.env
echo "Assistant address: http://$LAN_IP:8000"
LIBRARY_ASSISTANT_HOST="$LAN_IP" flox activate -- python3 -m library_assistant
```

Write down the address it prints: the Teacher signs in there to open Make Cards (Step 6), and
so do you (Step 7). If macOS asks whether `python3` may accept incoming network
connections, press **Allow**.

Tab 3, check what is listening and what is connected:

```bash
source ~/library-assistant-demo/demo.env && source ~/library-assistant-demo/today.env
curl -s "http://$LAN_IP:8000/health"
lsof -nP -iTCP -sTCP:LISTEN | grep -E 'ollama|python'
lsof -nP -a -p "$(pgrep -d, -f 'python3 -m library_assistant')" -iTCP
```

Expect `{"status":"ok"}`; `ollama` listening on `127.0.0.1:11436` and `127.0.0.1:11435`
only; the assistant (`python`) listening on `$LAN_IP:8000` only. Every connection the
assistant has should be to `127.0.0.1:11436` or `11435` (the two models) or from an address on
the router's network (your browser, the phones). Re-run the last line during the demo if anyone asks: that is the answer to "does
anything leave the building?". Nothing in the assistant can reach the internet anyway: its one
outbound client is scoped to the model endpoint (ADR-0006), and the room has no uplink.

## Step 6. The Teacher opens Make Cards and makes 3 Cards

Making Cards (Minting) happens in the Teacher's own browser, in **Make Cards**, a page the
assistant serves at `/staff/mint/`. The Teacher signs in, so nobody types or copies a key:
Cards made there are registered as the signed-in Teacher. Today the Teacher's computer is
the same laptop. Three Cards: one per volunteer and a spare.

This step is worth showing on stage: it is the whole of a Teacher's setup.

1. **Teacher.** In the browser, open `http://<LAN_IP>:8000/staff/login` (the address from
   Step 5; the assistant is not on `127.0.0.1` today) and sign in as `teacher.popquiz`
   (password `popquiz`). On `/staff`, press **Open Make Cards**. Signed out, the sign-in
   page brings you back to Make Cards afterwards. Served over HTTPS or from `localhost`,
   Chrome and Edge show **Install** in the address bar, which puts Make Cards on a
   Chromebook's shelf, the Mac's Dock, or the Windows Start menu. Over `http://` at the LAN
   address there is no Install button; it works the same in a tab.
2. **Teacher.** Make Cards has no address or key fields. It says "Cards you make here are
   registered as teacher.popquiz." After `./stack up` it opens with Class Label `Period 3`
   and Mr. Pop-Quiz's made-up class filled in; replace them for this step.
3. **Teacher.** Fill it in:
   - **Class Label:** `Conference demo`
   - **Students:** paste one name per line, one Card each (for the demo: `Volunteer 1`,
     `Volunteer 2`, `Spare`), or leave it empty and set **Number of Cards** to `3`. Names stay
     on this page and in the Roster; they never reach the assistant.
   - **Cards stop working at (today):** filled in with the assistant's end of school day.
     For the demo, set it to the end of your slot (`TALK_END` in Step 4).
4. **Teacher.** Press **Make Cards**. The page registers the Cards with the assistant first,
   and shows them only once it has accepted them: "Registered 3 Cards for Conference demo.
   They stop working at ... today." If something is wrong it says what, and makes no Cards:
   - "You are signed out of the Library Assistant": the sign-in has lapsed, or the
     database was reset. Sign in (item 1) and press **Make Cards** again.
   - "Could not reach the Library Assistant at ...": check the assistant is running and
     listening on that address (Step 5).
   - "A Batch must expire by the end of today's school day": pick an earlier stop time, or
     see Recovery, "A Card is refused".
5. **Teacher.** Hand the Cards out, one of two ways:
   - **One at a time** (the page opens on it): one large QR code with its Card number and
     Student's name. Invite that Student up to scan it with their device's camera, press
     **Handed out, next Card**, and the next one appears. A name typed there joins the
     Roster. On stage, do this in a browser window you are **not** sharing.
   - **Print**: every Card laid out to cut, each name on a tear-off stub below the cut line
     so the Card itself does not say whose it is. **Print Cards**, or **Download Cards** to
     print later. The QR codes carry `http://<LAN_IP>:8000/card#t=<Token>`.

   The page keeps nothing once you leave it (it warns you first), so hand out or save the
   Cards before you close it.
6. **Teacher.** The Roster: **Download Roster CSV** or **Print Sealed Roster Sheet**, with the
   names. It records which Student holds which Card number and never reaches the assistant.
   Say: *"The assistant got a fingerprint of each Card and the class name. It never saw a
   Card itself, and it will never see this list."*

Never put the Cards on the shared screen: anyone in the room could scan one.

**Fallback: a downloaded Minting page.** If Make Cards will not open, the Teacher presses **Download my Minting page** under "Or download a
Minting page to use offline" on `/staff` (the Librarian can download one for any Teacher
from **Keys**). The file has the assistant's address and a new Registration key built in,
so an earlier copy stops working; `./stack up` also writes one as
`teacher.popquiz-minting-page.html` in the stack folder. Open it in the browser and carry
on from item 3. If it says it "did not accept that Registration key", it is from an
earlier download or from before a reset: download a new one.

## Step 7. Sign in, open the Live view, Start watch, and screen-share

1. **Librarian.** Sign out Mr. Pop-Quiz, then sign in at
   `http://<LAN_IP>:8000/staff/login` as `librarian`.
2. On `/staff`, open **Live view**. It shows "No active Sessions." and **Start watch**.
3. Press **Start watch**. The line reads "You are on Watch." and the button becomes **End
   watch**. Until you press it, a volunteer who scans a Card gets the paused message ("The
   Library Assistant is taking a break until the librarian is ready...").
4. Open **Flag queue** from `/staff` in a second tab and leave it there for Step 10. The
   Live view, the Session detail, and the Flag queue all keep your Watch alive; close every
   one of them for longer than the Watch grace and the volunteers are paused.
5. Screen-share the browser window, not the terminal.

Start watch plays the Alarm chime once: that is the sound check (ADR-0010), and the click is
what lets the browser play sound at all. Have the venue's audio on and listen for it; if it is
silent, check **Alarm chime** is On in `/staff/settings` and the laptop is not muted. If any
high-severity Flag is still unacknowledged from rehearsal, its Alarm banner appears now, before
anything else: Acknowledge it before you share the screen.

## Step 8. The volunteers chat; the Live view updates live and streams the answer

Say: *"These two are Students. Each has a Card: a QR code with a number. No name, no login.
The assistant never learns who they are; only the Teacher's Roster says who holds card 1, and
that never leaves the Teacher's laptop."*

1. Ask the volunteers to put their phones in airplane mode, turn Wi-Fi back on, and join the
   travel router's network. (Some Android phones ask whether to stay on a network with no
   internet: answer yes.)
2. Each scans their Card with the phone's own camera app. The browser opens the chat page,
   showing "Conference demo / card 1" (or 2). Refresh the Live view: a tile for each Card.
3. Tell them their questions will be on the big screen, so nothing personal. Ask them to
   research a favourite animal, from the list you tested in Step 3, for example *"What do
   wolves eat, and are there books about wolves?"*
4. As each question lands, its tile moves to the top with the question, the time, and the
   message count, without a refresh.
5. Click a tile. The Session detail page (`/staff/live/sessions/<n>`) shows the exchange so
   far, and the next answer streams in as it is written.

Say, while it streams: *"Two parts. First an overview from what the model knows, which can be
wrong. Then the Records from our own Catalog, each with a Citation: that's the part to check
the overview against. The search finds up to 12 books, and the model chooses the ones that
really fit and says why, a few seconds after the overview. It can only choose from what the
search found. The books come from the Catalog, never from the model; only the reason is the
model's. And under each one, where to walk in the library."* On the phone, the second part
follows "Books in our library:". If the search finds nothing, or the model says none of it
fits, the Student is told "The library's catalog has nothing on this yet. Ask
the librarian."



## Step 9. Trigger the Flag: "library demo flag", the Supportive reply, and the Alarm

Say: *"Every message is checked against a Watchlist before the model sees it. It's a curated
list of phrases in four categories: self-harm, abuse, bullying, threats of violence. For the
demo we've added one harmless phrase that counts as a self-harm disclosure."*

1. Volunteer 1 types exactly: **library demo flag**
2. Their phone shows the Supportive reply instead of an answer: it names an adult in the
   building and, for self-harm, the 988 line. Nothing went to the model or the Catalog. Read
   the first line aloud, or have the volunteer hold the phone up.
3. A Flag is raised: high severity, category self-harm, source watchlist, entry `demo-flag`.

4. The Alarm sounds at once on every open staff page (the Live view, the Session detail, and
   the Flag queue tab), with no refresh: a banner that stays ("Alarm: high self-harm
   (watchlist), Conference demo · card 1, registered by demo-teacher, raised ..."), the tab
   title "(1) Alarm - ...", a red favicon, and the chime, repeating every **Alarm repeat
   seconds** (30) until someone Acknowledges. The "Open Flags" count goes up by one, the
   **Open Flags** panel at the top of the Live view gets a red "High" row for Conference demo
   · card 1, and card 1's tile shows "Flag: high", all without a refresh.

Say: *"The screen is ringing, and it never shows the words, so it's safe on a projector. The
words are one click away, on the Flag."*

Optional, to show the quiet kind: have volunteer 2 type **everyone picks on me** (a
low-severity Watchlist phrase) or, with Oversight on, something the phrase list would miss,
such as *"Billy says I stink and makes me cry"*. No sound: a "Low" row appears in the panel
within a second or two. Say: *"Not everything rings. The small worries still land here, in
front of whoever is watching."*

## Step 10. Acknowledge, then the Flag page: Export and Close

1. **Acknowledge.** Press **Acknowledge** on the Alarm banner. The panel's row changes from
   "New" to "Acknowledged" on every open staff page. It records who and when, and
   silences the Alarm on every page at once: the banner goes, the tab title and favicon come
   back, the chime stops. It does not close the Flag. Say: *"That's me saying I'm on it. The
   Flag stays open until it's worked."* An Alarm nobody Acknowledges replays at the next
   Start watch.
2. In the Live view's **Open Flags** panel, click the High row (or use the Flag queue tab,
   whose row also shows the category, entry, and Registered by `demo-teacher`).
3. The Flag page (`/staff/flags/<id>`) shows the same fields, who Acknowledged it and when,
   the question and the reply, and its History (each view is recorded). Point at "Not yet exported. Next Purge: ..." and the
   checkbox "The school does not need this exchange": a high-severity Flag cannot be closed
   unexported without that explicit confirmation, because closing it is what lets the Purge
   delete the exchange.
4. Click **Export**. The browser downloads `flag-<id>-export.txt`: Class label, Card number,
   category, severity, the timed exchange, and the history. No Token, no name. Say: *"This is
   the copy the school files in its own records. The assistant keeps no copy."*
5. Refresh the Flag page. Now that it is exported, the confirmation is gone. Choose an
   **Outcome** (`handled`), type a **Reason** ("demo"), press **Close**. The Flag leaves the
   queue, and its row leaves the Live view's Open Flags panel at the same moment. Say:
   *"Every Flag goes New, Acknowledged, Closed, whatever its severity. Close is the last
   step: if nobody had Acknowledged it, closing records that I did."* A low-severity Flag
   has no banner; its Flag page has its own **Acknowledge** button.

Optional: instead of closing it yourself, press **Escalate** (a reason is required). The
Counselor now owns the Flag: your Flag page says so in place of Close, and the panel row reads
"Escalated". Sign in as `demo-counselor` in a private window to close it from the
Counselor's Flag page. Say how Identification works: the Librarian asks the
Teacher who holds card 1, offline, between adults.

## Step 11. Revoke card 2

1. Go back to the Live view tab and click card 2's tile.
2. At the bottom of the Session detail page, tick "Yes, revoke card 2" and press **Revoke
   this Card**. You are sent back to the Live view, and card 2's tile is gone on refresh.
3. Volunteer 2 asks anything. Their phone shows: "This card has stopped working. Ask your
   teacher for a new one."

Say: *"Every request re-reads the Card, so a Revoke ends that Session immediately. There's
also Revoke this Batch, for the whole class at once."* Do not press that one: card 1 is still
needed for Step 13.

## Step 12. The Supportive reply preview

From `/staff`, open **Supportive reply preview**. It shows the reply for each Rubric
category (self-harm, abuse, bullying, threats of violence), the text a Student sees instead of
an answer. Say: *"A school may adjust these within fixed guard rails: the self-harm reply must
always carry 988."* There is a Print button for the staff binder.

## Step 13. End watch refuses new Sessions

1. On the Live view, press **End watch**. It reads "You are not on Watch."
2. Hand the spare Card (card 3) to a volunteer to scan, and ask volunteer 1 to ask another
   question. Both phones show the paused message: "The Library Assistant is taking a break
   until the librarian is ready. Please ask the librarian or your teacher."

Say: *"In Live supervision mode, Students can only chat while an adult is watching. If I walk
away, or my laptop sleeps, the class pauses on its own. The Watchlist and the Supportive reply
still run even when paused."*

Press **Start watch** again if you will take audience questions with the volunteers.

## Step 14. The Purge

Tell it as a story; there is no button to show.

Say: *"At the end of the school day, here the end of this talk, the assistant deletes every
transcript, except one attached to an open Flag, which waits until an adult closes the Flag,
or one under a Hold for a records request. It also deletes the expired Cards' Token hashes.
The Flag we just closed keeps its history, without the exchange, for 90 days. Nothing to
remember to do; the default is a single day."*

The Purge runs inside the assistant at each school-day end, and once at startup if the last
one was missed (ADR-0003). To show it ran, after the talk (tab 3):

```bash
sqlite3 "$LIBRARY_ASSISTANT_DB" "SELECT ran_at, deleted, kept_for_flags FROM purge_runs ORDER BY ran_at DESC LIMIT 3; SELECT count(*) FROM transcripts;"
```

## Recovery

### The model server is down

Symptom: answers never start, or the phone shows "Something went wrong. Ask the librarian."
The Watchlist, the Supportive reply, and Flags do not need the model, so Step 9 still works.

```bash
./stack status                              # tab 3: is answer-ollama up?
curl -s http://127.0.0.1:11436/api/version  # or by hand: is the Answer lane's Ollama up?
curl -s http://127.0.0.1:11436/api/ps       # is gpt-oss:20b loaded?
```

Under `./stack`, its log is `answer-ollama.log` in the stack folder
(`~/library-assistant-demo`); restart it with `./stack down && ./stack up --lan`. On the
manual path, look at tab 1 and re-run its commands. Then warm it again (Step 5, tab 3). If
`api/ps` lists another model, something else is using that Ollama and has pushed the demo
model out (`OLLAMA_MAX_LOADED_MODELS=1`): stop it and warm again.

On the flox fallback instead: `flox services status`, `flox services logs model -n 50`, and
`flox services restart model`. `Compute error` or `kIOGPUCommandBufferCallbackErrorOutOfMemory`
in its log means something else holds GPU memory, most likely the Ollamas: stop them
(`./stack down`, or tab 1), then restart the model server.
"Demo model not found" means `scripts/fetch_demo_model.sh` did not finish, or ran in another
checkout.

### Oversight is down: carry on or pause

The Oversight Lane is the second Ollama in Step 5, tab 1 (`oversight-ollama` under
`./stack`). Never point `LIBRARY_ASSISTANT_OVERSIGHT_ENDPOINT` at the Answer lane's Ollama
(`11436`): it holds one
model at a time, so the two would swap models on every message, and the Oversight Lane must
never take capacity from the Answer lane (ADR-0004).

If it stops answering, check `curl -s http://127.0.0.1:11435/api/version` (or
`./stack status`, and `oversight-ollama.log` in the stack folder) and restart it: tab 1's
second command, or `./stack down && ./stack up --lan`. Meanwhile the Live view shows "Screening is unavailable since HH:MM." What happens next is the **Oversight down** setting
on `/staff/settings`:

- **Carry on** (the demo's choice): Students keep chatting, screened by the Watchlist alone;
  those messages are screened once Oversight is back. The Live view offers **Pause
  Sessions** if you would rather stop.
- **Pause**: Sessions pause at once (the paused message) until Oversight answers again. The
  Live view says "Sessions are paused." with **Resume Sessions** for an adult to override.

### A phone cannot reach the laptop

Work down the list:

1. On the laptop, `curl -s "http://$LAN_IP:8000/health"` must print `{"status":"ok"}`. If not,
   the assistant in tab 2 has stopped; restart it (Step 5).
2. `ipconfig getifaddr en0` must still equal `$LAN_IP`. If the address changed, the Cards'
   QR codes point at the old one: rewrite `today.env`, restart the assistant with the new
   address, and make new Cards with the new address (Step 6).
3. The phone must be on the travel router's Wi-Fi, with mobile data off (airplane mode, then
   Wi-Fi on).
4. The router's client isolation must be off.
5. macOS firewall: System Settings, Network, Firewall. Either allow incoming connections for
   `python3`, or turn the firewall off for the demo.
6. On the phone, type `http://<LAN_IP>:8000/health` into the browser by hand. If that works
   but the Card does not, see the next section.

### A Card is refused

"This card has stopped working" means the assistant does not know that Token, or its Batch
has expired. In order of likelihood:

- The Card was scanned with an in-app QR reader that dropped the `#t=...` part of the address.
  Use the phone's own camera app.
- The Card was Revoked (Step 11), or `TALK_END` has passed.
- The database was reset after the Batch was registered (Recovery, "Reset between runs").
  Cards belong to the database they were registered in.

The fix for all of them is new Cards: redo Step 6 (the Class label can stay "Conference
demo"). If Make Cards says "Registration is closed: today's school day has ended" or "A
Batch must expire by the end of today's school day", `LIBRARY_ASSISTANT_SCHOOL_DAY_END` is
earlier than the stop time: rewrite `today.env` with a later time, restart the assistant, then
make the Cards again.

"The Library Assistant is taking a break..." is not a refused Card: nobody is on Watch. Press
**Start watch** on the Live view. A phone that scanned while nobody was watching keeps that
message up and signs in by itself within a few seconds of Start watch, with no rescan. A Watch
lapses when no open Live view, Session detail, or Flag queue has answered the server for the
**Watch grace seconds** (300), for example while the assistant was stopped for a while or the
laptop slept: press Start watch again.

### Reset between runs

Put the database back to the clean copy from Step 2. This keeps the accounts and the settings,
and drops every Card, Session, transcript, and Flag. It also puts back the Teacher's key from
before Step 6, so a downloaded Minting page stops working: download a new one if you use one.
Make Cards needs nothing: sign in again.

1. Stop the assistant (Ctrl-C in tab 2). Never copy over the database while it runs.
2. Tab 3:

   ```bash
   cp -f "$DEMO_DIR/clean.db" "$LIBRARY_ASSISTANT_DB"
   rm -f "$LIBRARY_ASSISTANT_DB-journal"
   rm -f ~/Downloads/Conference_demo-cards*.html ~/Downloads/Conference_demo-roster*.csv
   rm -f ~/Downloads/*-minting-page*.html   # if you downloaded one
   ```

3. Start the assistant again (Step 5, tab 2) and have the Teacher sign in and make new Cards
   in Make Cards (Step 6).
   Old Cards will be refused, as they should be.

If `clean.db` is lost, delete `demo.db` and redo Step 2 from item 2.

### Start setup over

The Librarian account cannot be deleted or deactivated. To start Step 2 again (a wrong
username, or accounts made in the wrong database), stop the assistant and delete the database
it used, then redo Step 2 from item 2:

```bash
rm -f ~/library-assistant-demo/demo.db ~/library-assistant-demo/demo.db-journal
rm -f library_assistant.db    # only if an assistant ran without demo.env (GAP lib-f9o)
```

## After the talk: Purge and cleanup

1. Stop the assistant (Ctrl-C in tab 2), then the model, and leave the activation (tab 1):

   ```bash
   flox services stop
   exit
   ```

2. Delete what could carry a Token or an exchange. The Cards and the Roster Make Cards
   downloaded, a downloaded Minting page if you used one, and the Flag export:

   ```bash
   rm -f ~/Downloads/Conference_demo-cards*.html ~/Downloads/Conference_demo-roster*.csv
   rm -f ~/Downloads/*-minting-page*.html ~/Downloads/flag-*-export.txt
   ```

   Delete the Cards from your phone too, if you AirDropped them. The demo's transcripts go
   by resetting the database:

   ```bash
   cp -f ~/library-assistant-demo/clean.db ~/library-assistant-demo/demo.db
   rm -f ~/library-assistant-demo/demo.db-journal
   ```

   Shred any printed Cards. The volunteers' phones hold only a cookie that expired with the
   Batch.

3. Note on lib-f24.9 what worked and what broke, with the gaps below that you hit.

Nothing from the demo goes into this repo: not the database, the Cards, the Roster, an
export, or the travel router's details.

## Known gaps

As of this runbook; re-check before the trip.

- **The assistant cannot run as a flox service for the demo** (lib-f9o).
  `flox services start assistant` does not see the variables `demo.env` and `today.env`
  export, so Steps 2 and 5 start it with `uvicorn` in its own tab instead.
- **The Ollamas stop when their parent does** (lib-ktv). Under `./stack` both run in the
  background until `./stack down`; on the manual path both run in Step 5's tab 1. Neither
  survives a restart of the Mac: run `./stack up --lan` (or tab 1) again.
- **The flox model server cannot run beside the Ollamas** (lib-30v). llama.cpp 0.7.0 fixed
  0.6.0's Metal out-of-memory failure and runs on the GPU, but it takes nearly all of the
  GPU's working set, so it is a fallback only. The demo no longer needs Ollama.app or its
  LaunchAgent; they can be retired in the workstation repo.
- **No staff page shows Purge runs**; the after-the-talk check uses `sqlite3` (Step 14).
