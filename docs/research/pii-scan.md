# Confidentiality and secret scanning in the gate

Research for bead `lib-ds3`, 25 Oct 2026. Binding context: `README.md` § "What must not be
committed here", `AGENTS.md` § Verify (one gate, `scripts/check.sh`), ADR-0002 (no
Card-to-Student link leaves the Teacher's machine), ADR-0006 (intranet only),
`.bead-loop.toml` (`merge = "auto"`: a green gate is squash-merged with no human review).

## Question

What should `scripts/check.sh` run so that the gate goes red on what the README forbids:
secrets, Rosters, transcripts and Flags, an Install's network topology, and real people's
names in the templates? Two parts:

1. **Secret scanning.** gitleaks, trufflehog or detect-secrets (or another tool). It must
   work offline, be fast enough for every gate run, come from flox, have an acceptable
   licence and few false positives on this repo, and we need to know whether it scans the
   working tree, the git history or both.
2. **Confidentiality denylist.** A small Python standard-library check for the rest. What
   can it reliably detect, and what can't it?

Plus: where waivers live, and how to waive a false positive without an agent being able
to waive things quietly.

## Decision

- **Secrets: gitleaks 8.30.1 from the flox catalog (nixpkgs, MIT), run twice:** once over
  committed history (`gitleaks git --log-opts=HEAD`) and once over the files git would
  commit (tracked files plus untracked files that aren't ignored, copied into a temporary
  tree and scanned as `gitleaks dir .`). Always run with `--ignore-gitleaks-allow`. CI's
  checkout needs `fetch-depth: 0`.
- **Confidentiality: `scripts/confidentiality.py`, standard library only**, over the same
  file set. It checks Roster files by extension and header, transcript and Flag exports by
  filename (and by a marker line once exports exist), private and link-local addresses
  with CIDR, VLAN, switch and firewall rule syntax, and in `docs/templates/` filled-in
  name, signature and approver fields, honorific + surname, and email addresses outside
  reserved example domains.
- **Waivers: exact and visible, with no inline pragmas.** Secret waivers are gitleaks
  fingerprints in `.gitleaksignore`. Each one needs a `# lib-xxx: reason` line above it.
  Confidentiality waivers go in `scripts/confidentiality-waivers.toml`, keyed by path, rule
  and the file's sha256, and also need a bead id and a reason. The gate prints every active
  waiver on every run. A `.gitleaks.toml` in the repo fails the gate. Waiver files are
  owned by a human through CODEOWNERS, so the auto-merge watcher can't merge an agent's
  waiver unreviewed (a human must enable this; see "Not confirmed").

Why gitleaks: it was the only candidate that caught both planted tokens, ran clean on this
repo, scans working tree and history, is MIT-licensed and makes no network calls. trufflehog
is built around online verification and has no generic-key detector, and it is AGPL.
detect-secrets has no history mode, and waiving in it means a baseline JSON of hashed
secrets that is hard to review. Details below.

## Sources

- gitleaks: <https://github.com/gitleaks/gitleaks>, licence
  [MIT](https://github.com/gitleaks/gitleaks/blob/master/LICENSE); README sections on
  `.gitleaksignore`, `gitleaks:allow` and config precedence. Behaviour below was checked
  against `gitleaks help`, `gitleaks dir --help` and `gitleaks git --help` of 8.30.1, not
  just the README.
- trufflehog: <https://github.com/trufflesecurity/trufflehog>, licence
  [AGPL-3.0](https://github.com/trufflesecurity/trufflehog/blob/main/LICENSE).
- detect-secrets: <https://github.com/Yelp/detect-secrets>, licence
  [Apache-2.0](https://github.com/Yelp/detect-secrets/blob/master/LICENSE).
- flox catalog, `flox show <pkg>` on 25 Oct 2026: `gitleaks@8.30.1` (MIT, x86_64-linux,
  aarch64-linux, aarch64-darwin, x86_64-darwin); `trufflehog@3.99.3` (AGPL-3.0-only, no
  x86_64-darwin); `detect-secrets@1.5.0` (Apache-2.0). All come from nixpkgs.
- flox manifest reference (`pkg-path`, `version`):
  <https://flox.dev/docs/reference/command-reference/manifest.toml/>.
- `actions/checkout` defaults to `fetch-depth: 1`: <https://github.com/actions/checkout>.
- GitHub CODEOWNERS and "Require review from Code Owners":
  <https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners>.
- Address ranges: RFC 1918 (IPv4 private), RFC 4193 (IPv6 ULA `fc00::/7`), RFC 3927
  (link-local `169.254/16`), RFC 5737 and RFC 3849 (documentation ranges), RFC 2606 and
  RFC 6761 (reserved example domains: `example.com`, `example.org`, `example.net`,
  `.example`, `.test`, `.invalid`). Python's `ipaddress` module (`is_private`,
  `is_link_local`) covers these ranges with no dependencies.

## Findings

### Trial runs (all tools installed from the flox catalog into a scratch env)

`flox install gitleaks@8.30.1 detect-secrets trufflehog` worked in this sandbox. Once
installed, every scan below ran with no network. Repo at `7605f53` (17 commits on HEAD,
31 across all local refs).

| Run | gitleaks 8.30.1 | trufflehog 3.99.3 (`--no-verification`) | detect-secrets 1.5.0 |
|---|---|---|---|
| Clean worktree, files | 0 findings, 0.23 s | 0 findings, 0.42 s | 0 findings, 0.72 s |
| Clean repo, history | 0 findings, 0.18 s | 0 findings, 1.0 s | no history mode |
| Planted GitHub-PAT-shaped token | caught (`github-pat`) | caught (`Github`) | caught (`GitHub Token` and `Base64 High Entropy String`) |
| Planted AWS-shaped key pair in `.env` | caught (`generic-api-key`) | **missed** (no generic detector) | caught (`AWS Access Key`) |

The planted values were generated at runtime and never committed.

### Behaviour that shapes how the gate calls gitleaks

1. **`gitleaks dir` ignores `.gitignore`.** Run on the main checkout, it walked the
   untracked `.claude/worktrees/` and gitignored `.flox/log/`, took 4.1 s over 25 MB, and
   reported two false positives (`generic-api-key` in flox `upgrade-check.*.log`). The gate
   must scan only what git would commit: `git ls-files -co --exclude-standard`, which
   includes force-added files and untracked files that aren't ignored. Copying that list into
   a temporary tree and scanning it took the same 0.23 s as the clean worktree.
2. **Dir-mode fingerprints include the scanned path.** Scanning `$TMP` gives
   `/tmp/tmp.XXXX/leak.env:generic-api-key:2`, which changes on every run, so
   `.gitleaksignore` could never match. Running `cd "$TMP" && gitleaks dir .` gives the
   stable `leak.env:generic-api-key:2`.
3. **`gitleaks git` walks every local ref by default** (31 commits rather than HEAD's 17).
   In a bead-loop worktree, another bead's unmerged branch would turn every gate red.
   `--log-opts=HEAD` limits the scan to the branch being gated.
4. **CI's checkout is shallow.** `ci.yml` sets no `fetch-depth`, and `gitleaks git` on a
   depth-1 clone scanned 1 commit. CI needs `fetch-depth: 0` for the history scan to mean
   anything. Bead-loop worktrees already have full history.
5. **`--pre-commit` is not enough on its own.** It diffs against HEAD and missed untracked
   files. `--staged` caught them only after `git add`.
6. **Inline `gitleaks:allow` waives a finding with no review trail.** Appending
   `# gitleaks:allow` to the planted token's line silenced it. `--ignore-gitleaks-allow`
   brings it back. That is the waiver an agent could add quietly, so the gate disables it.
7. **Config precedence.** `--config`, then `GITLEAKS_CONFIG`, then `GITLEAKS_CONFIG_TOML`,
   then `<target>/.gitleaks.toml`, then the built-in rules. A committed `.gitleaks.toml`
   with an `[allowlist]` would silently replace or extend the rules. The repo needs no
   custom config, so the gate fails if one exists. The scan also runs with
   `GITLEAKS_CONFIG` and `GITLEAKS_CONFIG_TOML` unset (`env -u`).
8. **A secret in history stays red after the file is deleted.** That is correct: the
   secret is already public. The fix is to rotate it, then add the history fingerprint
   (`commit:file:rule:line`) to `.gitleaksignore` with a bead id. Because main
   squash-merges, a fingerprint taken on a bead branch won't match main's squash commit.
   Take it from main.

### Why not trufflehog or detect-secrets

- **trufflehog** is built to verify candidate secrets against live APIs. Offline
  (`--no-verification`) it is a detector-per-vendor scanner with no generic fallback, and it
  missed the `.env` key pair. AGPL-3.0 is acceptable for a dev-only tool but buys nothing
  here, and the catalog has no x86_64-darwin build.
- **detect-secrets** found everything planted and is Apache-2.0, but it only scans files,
  never history. Waivers live in `.secrets.baseline`, a JSON file of hashed secrets that
  `detect-secrets audit` maintains interactively. A reviewer can't tell from a diff what was
  waived, and regenerating the baseline (`detect-secrets scan > .secrets.baseline`) waives
  everything at once, which is exactly the quiet abuse we want to prevent.
- **Others not trialled:** ggshield (needs a GitGuardian API key, so it's online by
  design) and `git-secrets` (AWS-oriented patterns, little recent maintenance).

### What the confidentiality check can and can't detect

Measured against the tracked files at `7605f53`. "Hits today" is what each rule would
report on the current repo, which is its false-positive count.

| README item | Rule (stdlib) | Hits today | Reliable? |
|---|---|---|---|
| Roster | `*.csv`, `*.tsv` whose first row (case- and punctuation-folded) has a column in {`student`, `student name`, `name`, `first name`, `last name`, `surname`, `given name`, `full name`, `pupil`, `legal name`}, or a `card` / `card number` column next to any name-like column | 0 (no CSV/TSV tracked) | Yes, for CSV/TSV. |
| Roster (spreadsheets) | `*.xlsx`, `*.xls`, `*.ods`, `*.numbers` anywhere: denied by extension, since there's no reason to allow any | 0 | Yes. |
| Roster (in Markdown) | Same header rule applied to Markdown table headers | 0 | Partly. A Roster written as prose or a list is not detected. |
| Transcripts, Flags | Filename denylist: `*transcript*`, `*flag-export*`, `*flags*.{json,jsonl,csv}`, `*.jsonl` outside `.beads/`, `*.sqlite*`, `*.db` (already gitignored, but `git add -f` gets past that) | 0 | Partly. There is no export format yet (the app is a `/health` stub). When exports are built, they should start with a fixed marker line (e.g. `# library-assistant export: transcript v1`) that this check matches. That would make detection exact and is a design note for the export bead. Until then, a transcript pasted into a doc as prose is not detected. |
| Network topology | IP literals that `ipaddress` reports as private or link-local, except loopback (`127.0.0.1` appears in the flox manifest and lock) and the documentation ranges `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24` and `2001:db8::/32`, which templates may use as examples. Syntax: `vlan <n>` / `vlan id`, `switchport`, `iptables -A`/`-I`, `nft add rule`, `table inet`, `access-list <n>`, `ufw allow`/`deny`, MAC addresses, hostnames ending `.lan`, `.local`, `.internal`, `.corp`, `.home.arpa` | 0 (only `127.0.0.1`, which is exempt) | Yes for addresses and config syntax. Prose like "the library VLAN is the one behind the office switch" is not detected. The words "VLAN" and "firewall rule" stay allowed in prose (README, ADR-0006 and the PIA use them). |
| Real names in templates | Only under `docs/templates/`: (a) Markdown table cells under a `Name`, `Signature`, `Student`, `Staff` or `Contact` column must be empty or `` `[BLANK…]` ``; (b) the value after `Prepared by:`, `Legal review:`, `Approved by:`, `Signed:`, `Superintendent:` or `School Board:` must be `` `[BLANK…]` ``; (c) an honorific (`Mr`, `Mrs`, `Ms`, `Miss`, `Mx`, `Dr`) followed by a capitalised word; (d) repo-wide, email addresses whose domain isn't a reserved example domain | 0 (all such fields are `[BLANK]` today; no honorifics or emails tracked) | Partly. A bare name in prose ("ask Maria in the office") can't be told apart from "Library Assistant", "Crisis Lifeline" or "Speak Up" without an NER model. The repo's capitalised two-word phrases are almost all like these, so a rule for them would only produce noise. Not attempted. |
| Completed PIA | The same template rules, applied to `pia-template.md` and any copy under `docs/templates/` | 0 | Partly. A filled-in PIA moved outside `docs/templates/` is only caught by rule (d) and the network rules. |
| Phone numbers | Not checked. The escalation protocol rightly lists public tiplines (`1-800-…`), and a student's phone number can't be told apart from one. | n/a | No. |

`[BLANK]` and `[BLANK: …]` stay allowed everywhere. The template rules treat a value as
blank when, with backticks stripped, it is empty or matches `^\[BLANK(: [^\]]*)?\]$`.

The confidentiality check covers the files that would be committed, as gitleaks' `dir`
pass does. It doesn't scan history: a Roster that was already committed and then removed
is still in history, and that needs a history rewrite, which the gate can't do.

### Waivers that an agent can't add quietly

The threat is concrete. `.bead-loop.toml` auto-merges anything green, so an agent that
clears a red gate by waiving its own finding goes straight to main. These rules close the
quiet routes:

1. **No inline pragmas.** gitleaks runs with `--ignore-gitleaks-allow`, and the Python
   check has no in-file escape hatch. Any `gitleaks:allow` in a scanned file fails the
   gate, so the attempt shows up instead of silently doing nothing.
2. **No custom gitleaks config.** A `.gitleaks.toml` in the repo fails the gate, and the
   gate unsets `GITLEAKS_CONFIG` and `GITLEAKS_CONFIG_TOML`.
3. **Exact, content-pinned waivers.**
   - `.gitleaksignore` holds fingerprints only, with no globs. The gate fails on any
     fingerprint line that doesn't have a `# lib-<id>: <reason>` comment right above it.
   - `scripts/confidentiality-waivers.toml` holds `[[waiver]]` entries with `path`, `rule`,
     `sha256` (of the whole file), `bead` and `reason`. Every key is required. Globs and
     directories are rejected. If the file's content changes, the hash stops matching and
     the waiver expires.
4. **Visible.** Every run prints each active waiver (path, rule, bead), so it's in every CI
   log and bead-loop transcript.
5. **Owned by a human.** `.github/CODEOWNERS` lists `/.gitleaksignore`,
   `/scripts/confidentiality-waivers.toml`, `/scripts/confidentiality.py`,
   `/scripts/secrets.sh` and `/scripts/check.sh` with `@imkarrer` as owner. This only
   protects anything once branch protection on `main` has "Require review from Code Owners"
   turned on, which is a human step outside these tickets. Until then, rules 1 to 4 make
   abuse visible but not impossible.
6. **Agent rule.** `AGENTS.md` should say that adding or editing a waiver is a design change
   (stop and ask), like weakening ADR-0002/0003/0006. That is a soft control, but it's where
   agents look first.

## Proposed tickets

Each ticket is independent and sized for one Claude Sonnet session. Either can land first.
Both add a line to `scripts/check.sh`. If both are in flight, the second one rebases a
one-line conflict.

### Ticket A: Confidentiality check in the gate (stdlib Python)

**Goal.** `scripts/check.sh` fails when a file git would commit looks like a Roster, a
transcript or Flag export, an Install's network detail, or a filled-in name field in a
template, as specified in the "What the confidentiality check can and can't detect" table
of `docs/research/pii-scan.md`.

**Build.**
- `scripts/confidentiality.py`: Python 3.12, standard library only. Entry point
  `python scripts/confidentiality.py [--root PATH]` (default: the repo root). It:
  - lists files with `git -C ROOT ls-files -co --exclude-standard -z`;
  - reads text files as UTF-8 with `errors="replace"` and applies binary files' extension
    rules only;
  - prints one `path:line: rule-id: message` per finding, and exits 1 on any finding,
    0 otherwise.

  Rule ids: `roster-csv`, `roster-spreadsheet`, `roster-table`, `export-file`,
  `private-address`, `network-config`, `template-name-field`, `template-honorific`,
  `email-address`, `inline-allow` (any `gitleaks:allow`), `waiver-invalid`.
- `scripts/confidentiality-waivers.toml`: committed with no entries, only a header comment
  explaining the format. A `[[waiver]]` entry suppresses one `(path, rule)` only while the
  file's sha256 matches. An entry missing any of `path`, `rule`, `sha256`, `bead`, `reason`,
  or with `*` in its path, is itself a `waiver-invalid` finding. Each waiver that applies is
  printed as `waived: <path> <rule> <bead>`.
- `pyproject.toml`: `pythonpath = [".", "scripts"]`, so tests can import the module.
- `tests/test_confidentiality.py`. **Positive cases are built at test time in `tmp_path`
  (`git init` plus files), never committed**, so the repo stays green with nothing to
  waive. Negative fixtures may be committed under `tests/fixtures/confidentiality/`.
- `scripts/check.sh`: one line, before `pytest`: `python scripts/confidentiality.py`.
- `.github/CODEOWNERS`, with the paths from "Waivers" rule 5 that exist after this ticket.
  A sentence in `AGENTS.md` § Verify: "Adding or editing a waiver is a design change: stop
  and ask."

**Acceptance criteria** (all offline, no human step):
1. Positive tests: each is a temp git repo where the script exits 1 and names the expected
   rule:
   - `class.csv` with header `Student Name,Card number`;
   - `period3.tsv` with header `last name<TAB>first name`;
   - `roster.xlsx` (any bytes);
   - a Markdown table with `| Card | Student |` headers;
   - `transcript-2026-10-24.txt`;
   - `flags.jsonl`;
   - `notes.md` containing `10.20.30.40`, `192.168.1.0/24` and `fd12:3456::1`;
   - `switch.txt` containing `switchport access vlan 40`;
   - `fw.sh` containing `iptables -A INPUT -s`;
   - `docs/templates/x.md` with `Prepared by: Jane Doe`;
   - a template table whose `Name` column holds `Pat Smith`;
   - `Ms. Alvarez` in a template;
   - `jdoe@district.k12.wi.us` anywhere;
   - any file containing `gitleaks:allow`.
2. Negative tests: each exits 0:
   - every current file in `docs/templates/`, copied in unchanged (all `[BLANK]` and
     `[BLANK: …]` placeholders pass);
   - `127.0.0.1`, `192.0.2.10` and `2001:db8::1`;
   - the prose "a firewall rule" and "VLAN layout";
   - a CSV with header `title,author,isbn`;
   - `someone@example.org`;
   - `.beads/issues.jsonl`;
   - a gitignored `roster.csv` (not reported, because git won't commit it).

   A force-added (`git add -f`) gitignored `roster.csv` **is** reported.
3. Waiver tests:
   - a valid waiver with the matching sha256 suppresses its finding and prints `waived:`;
   - editing the waived file brings the finding back;
   - a waiver missing `bead`, or with `path = "docs/*"`, fails with `waiver-invalid`.
4. Planted Roster goes red: a test copies the repo's tracked files into `tmp_path`, runs
   `git init` and `git add -A` there, adds `roster.csv` with header `Student,Card`, runs
   `python scripts/confidentiality.py --root <tmp>` and asserts exit 1. It then deletes the
   file and asserts exit 0. Manually: `printf 'Student,Card\n' > roster.csv && flox
   activate -- bash scripts/check.sh` exits nonzero. Then `rm -f roster.csv`.
5. The script runs in under 2 s on this repo (a test with that bound).
6. `ruff check .` and `ruff format --check .` pass. `flox activate -- bash scripts/check.sh`
   passes on the clean repo.

### Ticket B: gitleaks secret scan in the gate

**Goal.** `scripts/check.sh` fails on a secret in the files git would commit or in HEAD's
history. It uses gitleaks from the flox environment, and the only waivers are annotated
`.gitleaksignore` fingerprints.

**Precondition.** This step needs the flox catalog. If the session has no network, do it
before dispatch: run `flox install gitleaks@8.30.1` in the repo root and commit
`.flox/env/manifest.toml` and `.flox/env/manifest.lock`. After that, activation is offline
on any machine whose Nix store already has the package. That was true on this workstation
on 25 Oct 2026. If the session has network, the ticket does this step itself.

**Build.**
- `scripts/secrets.sh` (bash, `set -euo pipefail`), called from `check.sh` as
  `bash scripts/secrets.sh`. In order, it:
  1. fails if `.gitleaks.toml` exists in the repo root;
  2. checks `.gitleaksignore`: every non-blank, non-comment line must have a comment line
     right above it matching `^# lib-[a-z0-9.]+: .+`, or the script fails;
  3. prints each active fingerprint as `waived: <fingerprint>`;
  4. runs `env -u GITLEAKS_CONFIG -u GITLEAKS_CONFIG_TOML gitleaks git --no-banner --redact
     --ignore-gitleaks-allow --log-opts=HEAD -i "$ROOT" "$ROOT"`;
  5. copies `git ls-files -co --exclude-standard -z` into a `mktemp -d` tree with
     `tar --null -T -`, `cd`s into it and runs `gitleaks dir . --no-banner --redact
     --ignore-gitleaks-allow -i "$ROOT"`, so fingerprints are repo-relative;
  6. removes the temp tree on exit (`trap`).
- `.gitleaksignore`: committed, containing only a header comment describing the format.
- `.github/workflows/ci.yml`: add `with: fetch-depth: 0` to the Checkout step.
- `tests/test_secrets.py`: builds temp git repos in `tmp_path` and runs
  `bash <repo>/scripts/secrets.sh` with `cwd` set to them. It skips with a clear reason if
  `gitleaks` isn't on `PATH`. Fake tokens are assembled at runtime (for example
  `"ghp_" + "A1b2" * 9`), so no secret-shaped literal is committed and the test file itself
  passes the scan.
- `scripts/check.sh`: one line, before `pytest`: `bash scripts/secrets.sh`.
- `.github/CODEOWNERS`: add `/.gitleaksignore` and `/scripts/secrets.sh`. Create the file
  if ticket A hasn't landed.

**Acceptance criteria** (offline once the precondition holds, no human step):
1. On the clean repo, `bash scripts/secrets.sh` exits 0 in under 2 s, and
   `flox activate -- bash scripts/check.sh` passes.
2. Each of these exits nonzero:
   - an untracked, non-ignored `leak.env` with a runtime-built GitHub-PAT-shaped token;
   - the same token committed and then deleted in a later commit (the history pass);
   - the same token followed by `# gitleaks:allow` (inline waiver ignored);
   - a `.gitleaks.toml` present, even an empty one.
3. A token in a gitignored path (e.g. `.flox/log/x.log`) is **not** reported. This is the
   regression test for the false positives found in triage.
4. A token committed only on another local branch, not reachable from HEAD, is **not**
   reported.
5. A `.gitleaksignore` with `# lib-abc: test fixture` above the finding's repo-relative
   fingerprint exits 0 and prints `waived:`. The same fingerprint without the comment line
   exits nonzero.
6. `ruff check .` and `ruff format --check .` pass. `flox activate -- bash scripts/check.sh`
   passes.

## Not confirmed

- **Bead-loop and CODEOWNERS.** Whether the bead-loop watcher (`merge = "auto"`) respects
  GitHub's required Code Owner review, or merges through it. Turning on "Require review
  from Code Owners" is a human repository-settings step. Until it's done, the waiver
  controls give visibility, not enforcement.
- **Offline `flox install`.** `flox install` contacts the catalog. Whether it can resolve
  from a warm Nix store with no network wasn't tested, since the catalog was reachable
  here. Hence ticket B's precondition.
- **CI.** gitleaks inside GitHub Actions via `flox/activate-action` wasn't run. The history
  pass under `fetch-depth: 0` is untested there. Locally, a depth-1 clone scanned 1 commit,
  as expected.
- **aarch64-darwin.** gitleaks was only run on x86_64-linux. The catalog lists an
  aarch64-darwin build.
- **False-positive rates beyond this repo.** These figures come from today's 50-odd
  tracked files. Filled-in examples in future templates may use documentation-range
  addresses, which are exempt, or honorifics in sample scripts, which would be flagged.
