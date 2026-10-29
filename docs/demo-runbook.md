# Demo runbook: the M5 Pro conference demo

The step-by-step for showing the Library Assistant live at a librarian conference: the
presenter's M5 Pro MacBook runs everything, the room has no internet, and two volunteers chat
as Students on their own phones while the presenter screen-shares the Live view. Vocabulary is
[`CONTEXT.md`](../CONTEXT.md)'s. Binding: [ADR-0006](adr/0006-intranet-only.md) (nothing
reaches the internet at demo time; the model and the Catalog are fetched once, online,
beforehand) and [ADR-0010](adr/0010-student-sessions-run-only-on-watch.md) (Students chat only
while an adult is on Watch).

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

1. Check free disk. The model is about 19 GB, the Catalog about 150 MB (its build needs about
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

3. Activate once, online. The first activation installs Python, uv, llama.cpp, and the
   Python packages (from PyPI). It prints `Installing Python packages...` the first time.

   ```bash
   flox activate -- python3 -c "import fastapi, uvicorn, qrcode, httpx; print('env ok')"
   flox activate -- llama-server --version
   ```

4. Fetch the demo model (Qwen3-30B-A3B-Instruct-2507, Q4_K_M GGUF, Apache-2.0) into
   `.flox/cache/models/`. It checks the file's sha256 and resumes a partial download if
   re-run.

   ```bash
   flox activate -- bash scripts/fetch_demo_model.sh
   ```

   The script checks the download with `sha256sum`. This has not been confirmed on macOS: if it
   stops with `sha256sum: command not found`, check by hand with `shasum -a 256` against the
   `SHA256` line in `scripts/fetch_demo_model.sh`, and note it on lib-f24.9.

5. Build the demo Catalog from Library of Congress records (ADR-0006's one demo exception:
   about 3 GB of downloads, one part at a time, around 20 minutes on a fast line). It writes
   `catalog.db` at the repo root, which `.gitignore` keeps out of git.

   ```bash
   flox activate -- python3 scripts/build_demo_catalog.py --dest catalog.db
   ```

   Re-running with the same `--download-dir` (default `marc-dist-download/`) resumes. When it
   finishes, check it answers a search:

   ```bash
   flox activate -- python3 -c "
   from library_assistant.catalog.sqlite_backend import SqliteCatalog
   c = SqliteCatalog.open('catalog.db')
   for r in c.search('wolves', 5): print(r.id, r.title)"
   ```

6. Check the disk again: `du -sh .flox/cache/models catalog.db` and `df -h "$HOME"`.

## Step 2. Online setup: the Librarian, accounts, Registration key, supervision mode

Set up the demo's database once, at home, and keep a clean copy of it to reset to between
runs (Recovery, "Reset between runs"). The database lives outside the repo, in a folder only
you can read, because it will hold the accounts' password hashes and, during a demo, the
volunteers' questions.

1. Make the demo folder and its settings file. `$PWD` is expanded now, so run this from the
   repo root:

   ```bash
   mkdir -p ~/library-assistant-demo && chmod 700 ~/library-assistant-demo
   cat > ~/library-assistant-demo/demo.env <<EOF
   export DEMO_DIR="$HOME/library-assistant-demo"
   export LIBRARY_ASSISTANT_DB="$HOME/library-assistant-demo/demo.db"
   export LIBRARY_ASSISTANT_CATALOG_PATH="$PWD/catalog.db"
   export LIBRARY_ASSISTANT_DEMO=1
   EOF
   ```

   `LIBRARY_ASSISTANT_DEMO=1` adds the demo Watchlist entry
   (`library_assistant/watchlist-demo.toml`): the phrase **library demo flag**, Rubric category
   self-harm, severity high. It is the only phrase ever used to raise a Flag on stage. Never
   ask a volunteer to type a real disclosure or anything from the real Watchlist.

2. Start the assistant on this machine only, for setup:

   ```bash
   flox activate
   source ~/library-assistant-demo/demo.env
   LIBRARY_ASSISTANT_HOST=127.0.0.1 flox services start assistant
   ```

   Always pass `--no-access-log`: uvicorn's own access log would write request paths
   (ADR-0003 addendum). The assistant keeps its own log of route, status, and duration.

3. In a browser, open `http://127.0.0.1:8000/staff/login`. With no accounts yet it sends you
   to `/staff/setup`. Create the Librarian: username `librarian`, a password you will
   remember on stage. This signs you in.

4. Open `http://127.0.0.1:8000/staff/accounts` and add two accounts with **Add account**:
   - `demo-teacher`, role **Teacher** (the Teacher who mints and registers the demo Batch;
     its name shows as "Registered by" on the Flag).
   - `demo-counselor`, role **Counselor** (so the Flag page offers **Escalate**; optional).

   Do not use a real person's name for either.

5. Open `http://127.0.0.1:8000/staff/keys`. On the `demo-teacher` row press **Rotate key**.
   The new Registration key is shown once. Copy it, then save it outside the repo:

   ```bash
   pbpaste > ~/library-assistant-demo/teacher.key && chmod 600 ~/library-assistant-demo/teacher.key
   ```

6. Open `http://127.0.0.1:8000/staff/settings` and set:
   - **Supervision mode: Live.** It is the default and the one the demo shows: Students chat
     only while someone is on Watch, so End watch visibly pauses them (Step 13).
   - **Watch grace seconds: 300.** The default 90 is right for a library; on stage, 300 gives
     slack for a slow tab switch or a screen-share hiccup. End watch is still immediate.
   - **Oversight down: Carry on.** The demo runs without Oversight (Recovery, "Oversight
     down"), so this only matters if you configure one.
   - Leave **Session idle minutes** at 0, **Alarm chime** On, **Alarm repeat seconds** 30.

   Press **Save**. The page lists the change under "Recent changes".

7. Open `http://127.0.0.1:8000/staff/supportive-replies-preview` and read the four replies,
   so you know what the volunteer will see in Step 9.

8. Stop the assistant (Ctrl-C), then keep the clean copy:

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

Two terminal tabs, both at the repo root. Tab 1 runs the model and the assistant; tab 2 is for
checks and minting.

**GAP (lib-f24.9):** the shipped `assistant` flox service now binds to the intranet address
instead of `127.0.0.1` only. Start only the `model` service with flox, then start the
assistant with the intranet address set. Do not run `flox activate --start-services`, which would
start a second assistant on `127.0.0.1`.

Tab 1:

```bash
flox activate
flox services start model
flox services status
```

`model` should be `Running` and `assistant` not running (if it is, `flox services stop
assistant`). The model takes a minute or two to load; wait until this prints
`{"status":"ok"}`:

```bash
curl -s http://127.0.0.1:8080/health
```

Warm it up with one throwaway request straight to the model server (it records nothing; the
assistant is not involved):

```bash
curl -s http://127.0.0.1:8080/v1/chat/completions -H 'content-type: application/json' \
  -d '{"model":"demo","messages":[{"role":"user","content":"Say ready."}],"max_tokens":5}'
```

Then start the assistant, bound to the LAN address, with the demo Watchlist on:

```bash
source ~/library-assistant-demo/demo.env
source ~/library-assistant-demo/today.env
LIBRARY_ASSISTANT_HOST="$LAN_IP" flox services start assistant
```

Leave tab 1 running. Services started inside an activation stop when its last shell exits, so
do not close it.

Tab 2, check what is listening and what is connected:

```bash
source ~/library-assistant-demo/demo.env && source ~/library-assistant-demo/today.env
curl -s "http://$LAN_IP:8000/health"
lsof -nP -iTCP -sTCP:LISTEN | grep -E 'llama|python'
lsof -nP -a -p "$(pgrep -d, -f 'uvicorn library_assistant')" -iTCP
lsof -nP -a -p "$(pgrep -d, llama-server)" -iTCP
```

Expect `{"status":"ok"}`; `llama-server` listening on `127.0.0.1:8080` only; the assistant
(`python`) listening on `$LAN_IP:8000` only. Every connection the assistant has should be to
`127.0.0.1:8080` (the model) or from an address on the router's network (your browser, the
phones). Re-run the last two lines during the demo if anyone asks: that is the answer to "does
anything leave the building?". Nothing in the assistant can reach the internet anyway: its one
outbound client is scoped to the model endpoint (ADR-0006), and the room has no uplink.

If macOS asks whether `python3` may accept incoming network connections, press **Allow**.

## Step 6. Mint 3 Cards, register them, and get them to the volunteers

You are playing the Teacher here: Minting happens on the Teacher's machine, which today is
the same laptop. Three Cards: one per volunteer and a spare.

Tab 2:

```bash
flox activate -- python3 scripts/mint_batch.py \
  --count 3 \
  --class-label "Conference demo" \
  --until "$TALK_END" \
  --out-dir "$DEMO_DIR/cards" \
  --url "http://$LAN_IP:8000/batches" \
  --registration-key "$(cat "$DEMO_DIR/teacher.key")"
```

It prints four `wrote ...` lines and `registered 3 cards at http://.../batches`. `--until`
must not be later than `LIBRARY_ASSISTANT_SCHOOL_DAY_END`, or Registration is refused ("A
Batch must expire by the end of today's school day"), and must be later than now. In
`$DEMO_DIR/cards/`:

- `Conference_demo-cards.html`: the Cards, one QR code and Card number each. The QR codes
  carry `http://<LAN_IP>:8000/card#t=<Token>`.
- `Conference_demo-roster.csv` and `Conference_demo-roster-printable.html`: the Roster. In a
  school it would record which Student holds which Card number; for the demo leave it blank.
- `Conference_demo-registration.json`: what was sent to the assistant. It contains the raw
  Tokens (the assistant stores only their hashes), so treat it like the Cards.

Getting the Cards to the volunteers, best first:

- **Print** `Conference_demo-cards.html` (open it in the browser, Cmd-P) if the venue has a
  printer you can reach offline, and cut out Cards 1, 2, and 3.
- **Show them on your own phone**, not the projector: AirDrop `Conference_demo-cards.html`
  to your phone (AirDrop works without internet), open it, and let each volunteer scan their
  Card from it.

Never put the Cards on the shared screen: anyone in the room could scan one.

## Step 7. Sign in, open the Live view, Start watch, and screen-share

1. In the browser, open `http://$LAN_IP:8000/staff/login` (type the real address; the
   assistant is not on `127.0.0.1` today) and sign in as `librarian`. `/staff` shows only who
   you are and a Sign out button; go straight to the pages by address.
2. Open `http://$LAN_IP:8000/staff/live`. It shows "No active Sessions." and **Start watch**.
3. Press **Start watch**. The line reads "You are on Watch." and the button becomes **End
   watch**. Until you press it, a volunteer who scans a Card gets the paused message ("The
   Library Assistant is taking a break until the librarian is ready...").
4. Open a second tab at `http://$LAN_IP:8000/staff/flags` and leave it there for Step 10.
   Keep the Live view in its own tab all talk: the Live view and the Session detail answer
   the Watch heartbeat, but the Flag queue and Flag page do not yet (see Known gaps). Lose
   every Live view tab for longer than the Watch grace and the volunteers are paused.
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
wrong. Then the Records from our own Catalog, each with a Citation, found by the model's search
terms: that's the part to check the overview against. The books come from the Catalog, never
from the model."* On the phone, the second part follows "Books in our library:". If the
Catalog has nothing, the Student is told "The library's catalog has nothing on this yet. Ask
the librarian."

**GAP:** Citations on the Session detail page link to `/staff/catalog/record/<id>`, a route
that does not exist (404). Do not click them on stage.

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
   seconds** (30) until someone Acknowledges. The "Open Flags" count goes up by one.

Say: *"The screen is ringing, and it never shows the words, so it's safe on a projector. The
words are one click away, on the Flag."* (Card 1's tile shows "Flag: high" after a refresh.)

## Step 10. Acknowledge, then the Flag page: Export and Close

1. **Acknowledge.** Press **Acknowledge** on the Alarm banner. It records who and when, and
   silences the Alarm on every page at once: the banner goes, the tab title and favicon come
   back, the chime stops. It does not close the Flag. Say: *"That's me saying I'm on it. The
   Flag stays open until it's worked."* An Alarm nobody Acknowledges replays at the next
   Start watch.
2. In the Flag queue tab (refresh it), the Flag's row shows raised at, category, severity, source, entry,
   Class ("Conference demo"), Card ("1"), and Registered by (`demo-teacher`). Click **View**.
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
   queue.

Optional: before closing, with the Counselor account from Step 2, the Flag page also offers
**Escalate** (a reason is required). Say how Identification works: the Librarian asks the
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

Open `http://$LAN_IP:8000/staff/supportive-replies-preview`. It shows the reply for each Rubric
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
one was missed (ADR-0003). To show it ran, after the talk (tab 2):

```bash
sqlite3 "$LIBRARY_ASSISTANT_DB" "SELECT ran_at, deleted, kept_for_flags FROM purge_runs ORDER BY ran_at DESC LIMIT 3; SELECT count(*) FROM transcripts;"
```

**GAP:** the in-process Purge loop and the startup Purge read the built-in defaults, not the
environment: they run at **15:30 America/Chicago** whatever `LIBRARY_ASSISTANT_SCHOOL_DAY_END`
and `LIBRARY_ASSISTANT_SCHOOL_TIMEZONE` say (`library_assistant/app.py` builds `Settings()`
instead of reading the environment). Registration, Card expiry, and the Flag page's "Next
Purge" do read the environment, so "Next Purge" shows your `TALK_END` while the real Purge
fires at 15:30 Central. If your talk spans 15:30 Central, the transcripts vanish mid-demo
(an open Flag's exchange stays). Check the conversion before the talk; if it spans, keep the
Flag open until after 15:30 Central or move the Flag steps earlier.

## Recovery

### The model server is down

Symptom: answers never start, or the phone shows "Something went wrong. Ask the librarian."
The Watchlist, the Supportive reply, and Flags do not need the model, so Step 9 still works.

```bash
curl -s http://127.0.0.1:8080/health        # tab 2
flox services status                        # tab 1 (inside the activation)
flox services logs model -n 50
flox services restart model
```

"Demo model not found" in the log means Step 1.4 did not finish. The model takes a minute or
two to load after a restart; re-run the warm-up from Step 5.

### Oversight is down: carry on or pause

This runbook's demo runs without Oversight: `LIBRARY_ASSISTANT_OVERSIGHT_ENDPOINT` and
`LIBRARY_ASSISTANT_OVERSIGHT_MODEL` are unset, so every message is screened by the Watchlist
alone, and the Live view never shows a screening line. Do not point Oversight at the demo's
one model server: the Oversight Lane must never take capacity from the Answer lane.

If you do configure Oversight on its own Lane and it stops answering, the Live view shows
"Screening is unavailable since HH:MM." What happens next is the **Oversight down** setting
on `/staff/settings`:

- **Carry on** (the demo's choice): Students keep chatting, screened by the Watchlist alone;
  those messages are screened once Oversight is back. The Live view offers **Pause
  Sessions** if you would rather stop.
- **Pause**: Sessions pause at once (the paused message) until Oversight answers again. The
  Live view says "Sessions are paused." with **Resume Sessions** for an adult to override.

### A phone cannot reach the laptop

Work down the list:

1. On the laptop, `curl -s "http://$LAN_IP:8000/health"` must print `{"status":"ok"}`. If not,
   the assistant in tab 1 has stopped; restart it (Step 5).
2. `ipconfig getifaddr en0` must still equal `$LAN_IP`. If the address changed, the Cards'
   QR codes point at the old one: restart the assistant with the new address (rewrite
   `today.env`) and mint a new Batch (Step 6).
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

The fix for all of them is a new Batch: re-run Step 6 (the Class label can stay "Conference
demo"). If Registration says "Registration is closed: today's school day has ended",
`LIBRARY_ASSISTANT_SCHOOL_DAY_END` has passed: rewrite `today.env` with a later time, restart
the assistant, then mint.

"The Library Assistant is taking a break..." is not a refused Card: nobody is on Watch. Press
**Start watch** on the Live view.

### Reset between runs

Put the database back to the clean copy from Step 2. This keeps the accounts, the settings,
and the Teacher's Registration key, and drops every Card, Session, transcript, and Flag.

1. Stop the assistant in tab 1 (Ctrl-C). Never copy over the database while it runs.
2. Tab 2:

   ```bash
   cp -f "$DEMO_DIR/clean.db" "$LIBRARY_ASSISTANT_DB"
   rm -f "$LIBRARY_ASSISTANT_DB-journal"
   rm -rf "$DEMO_DIR/cards"
   ```

3. Start the assistant again (Step 5's `uvicorn` line, in tab 1) and mint a new Batch
   (Step 6). Old Cards will be refused, as they should be.

If `clean.db` is lost, delete `demo.db` and redo Step 2 from item 2 (the Teacher gets a new
Registration key).

## After the talk: Purge and cleanup

1. Stop the assistant (Ctrl-C in tab 1), then the model, and leave the activation:

   ```bash
   flox services stop
   exit
   ```

2. Delete what could carry a Token or an exchange. The Cards, the Roster, and the
   registration payload:

   ```bash
   rm -rf ~/library-assistant-demo/cards
   ```

   The Flag export the browser downloaded (`~/Downloads/flag-*-export.txt`), and the demo's
   transcripts, by resetting the database:

   ```bash
   rm -f ~/Downloads/flag-*-export.txt
   cp -f ~/library-assistant-demo/clean.db ~/library-assistant-demo/demo.db
   rm -f ~/library-assistant-demo/demo.db-journal
   ```

   Shred any printed Cards. The volunteers' phones hold only a cookie that expired with the
   Batch.

3. If the Registration key was ever on the shared screen, rotate it (`/staff/keys`, **Rotate
   key** on `demo-teacher`) and save the new one as in Step 2.5, then take a fresh
   `clean.db`.
4. Note on lib-f24.9 what worked and what broke, with the gaps below that you hit.

Nothing from the demo goes into this repo: not the database, the Cards, the Roster, an
export, or the travel router's details.

## Known gaps

As of this runbook; re-check before the trip.

- **No LAN binding for the shipped assistant service.** `[services.assistant]` in
  `.flox/env/manifest.toml` binds `127.0.0.1:8000`, so the demo runs the assistant by hand
  (Step 5), and lib-f24.9's "one flox command starts the assistant and the model server" does
  not hold for a demo with phones.
- **The Purge loop ignores the environment's school day** (`library_assistant/app.py`'s
  lifespan builds `Settings()` rather than `Settings.from_env()`): it runs at 15:30
  America/Chicago, while the Flag page's "Next Purge" shows the configured time (Step 14).
- **Citation links on the Session detail page 404**: `/staff/catalog/record/<id>` has no
  route (Step 8).
- **The Flag queue and Flag page do not hold a Watch**: they send no heartbeat and have no
  Start watch button, though ADR-0010 names the Flag queue as a watching page. Keep a Live
  view tab open (Step 7).
- **The Live view's Flag badge is not live**: "Flag: high" on a tile appears only on refresh.
- **`/staff` has no links** to the Live view, Flag queue, accounts, keys, or settings: type
  the addresses.
- **No staff page shows Purge runs**; the after-the-talk check uses `sqlite3` (Step 14).
- **`fetch_demo_model.sh` uses `sha256sum`**, not yet confirmed present on macOS (Step 1).
