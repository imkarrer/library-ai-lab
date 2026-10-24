# Hardware detection and default models

Research for bead `lib-06g`, 24 Oct 2026. Binding context: ADR-0004 (Oversight never costs
Students anything; hardware detection decides whether it can share the box), ADR-0006
(intranet only), ADR-0008 (one flox environment), ADR-0009 (prefer small-active MoE).

## Question

When a Librarian installs the assistant with flox on Linux x86_64 or Apple Silicon, how should
the Install pick default models for the Answer lane (required), the embedding model, and the
Oversight lane (optional), and decide whether Oversight can share the Answer lane's box with
both models resident and KV headroom? The Librarian's config always wins; these are defaults
only.

Options weighed: (a) depend on llmfit at install time, (b) vendor or port its detection
logic, (c) ship our own small curated table plus detection, (d) something better.

## Decision

**(c), with one addition from (d): a small curated model table and a stdlib-only detection
module of our own, plus a fit probe that confirms the prediction once the model servers are
running.** llmfit is not a dependency of the Install. It stays useful as a developer
cross-check when the table is written or changed.

Why, in one paragraph: the question we have to answer is "do these two specific GGUF files,
at this context and slot count, fit together in this machine's GPU-addressable pool",
and llmfit answers a different one ("which of 17,700 Hugging Face models scores best here,
one at a time"). It has no multi-model co-residence calculation, grades Apple Silicon
against total RAM rather than the GPU wiring cap, and turns a failed `nvidia-smi` into "CPU
only" without saying so. The parts we need (read memory, read VRAM, read the Metal cap, add
up a few numbers from a table) are about 200 lines of Python with no dependencies, and the
part llmfit is best at, its catalog, is the part we must not use: our defaults have to be
models we have evaluated (the golden question set), at the exact quant the server loads.

## Sources

Primary sources read for this note (llmfit clone at `b8124fb`, 24 Oct 2026):

- llmfit repository: <https://github.com/AlexsJones/llmfit>; licence
  [`LICENSE`](https://github.com/AlexsJones/llmfit/blob/main/LICENSE) (MIT);
  releases: <https://github.com/AlexsJones/llmfit/releases>
- [`docs/how-it-works.md`](https://github.com/AlexsJones/llmfit/blob/main/docs/how-it-works.md),
  [`docs/platform-support.md`](https://github.com/AlexsJones/llmfit/blob/main/docs/platform-support.md),
  [`API.md`](https://github.com/AlexsJones/llmfit/blob/main/API.md) (REST, MCP, NATS)
- Source: [`llmfit-core/src/hardware.rs`](https://github.com/AlexsJones/llmfit/blob/main/llmfit-core/src/hardware.rs),
  [`concurrency.rs`](https://github.com/AlexsJones/llmfit/blob/main/llmfit-core/src/concurrency.rs),
  [`plan.rs`](https://github.com/AlexsJones/llmfit/blob/main/llmfit-core/src/plan.rs),
  [`update.rs`](https://github.com/AlexsJones/llmfit/blob/main/llmfit-core/src/update.rs),
  [`benchmarks.rs`](https://github.com/AlexsJones/llmfit/blob/main/llmfit-core/src/benchmarks.rs),
  [`llmfit-core/Cargo.toml`](https://github.com/AlexsJones/llmfit/blob/main/llmfit-core/Cargo.toml),
  [`llmfit-core/data/hf_models.json`](https://github.com/AlexsJones/llmfit/blob/main/llmfit-core/data/hf_models.json)
- docs.rs: <https://docs.rs/llmfit-core/latest/llmfit_core/> (1.1.17);
  crates.io API <https://crates.io/api/v1/crates/llmfit-core>
- nixpkgs package: [`pkgs/by-name/ll/llmfit/package.nix`](https://github.com/NixOS/nixpkgs/blob/master/pkgs/by-name/ll/llmfit/package.nix);
  flox catalog (`flox show llmfit`, run 24 Oct 2026)
- llama.cpp server flags: [`tools/server/README.md`](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md) (`--fit`, `--fit-target`, `--fit-ctx`)
- Apple: [`MTLDevice.recommendedMaxWorkingSetSize`](https://developer.apple.com/documentation/metal/mtldevice/recommendedmaxworkingsetsize)
- Linux: [`/proc/meminfo`](https://docs.kernel.org/filesystems/proc.html#meminfo) (`MemTotal`, `MemAvailable`);
  amdgpu sysfs [`mem_info_vram_total` / `mem_info_vram_used`](https://docs.kernel.org/gpu/amdgpu/driver-misc.html)
- NVIDIA: [`nvidia-smi` documentation](https://docs.nvidia.com/deploy/nvidia-smi/index.html) (`--query-gpu=name,memory.total,memory.free --format=csv,noheader,nounits`)
- Alternative estimator: gpustack [`gguf-parser-go`](https://github.com/gpustack/gguf-parser-go) (MIT)
- Homelab practice: `agent-hub/llama-swap.yaml` (not public; the four co-resident models on
  llm-box and the measured sizes in its comments)
- This repo: ADR-0004, ADR-0006, ADR-0008, ADR-0009, `CONTEXT.md`, beads `lib-06g`, `lib-f24`
  (story 31, implementation decisions), `lib-f24.9`, `lib-f24.14`, `lib-f24.16`; the old plan
  at commit `68abceb` (`docs/plan.md`, "Hardware and budget")

Runs on this workstation (WSL2, Ryzen 9800X3D, 30 GiB, RTX 4080 16 GiB) with
`nix shell github:NixOS/nixpkgs/nixos-unstable#llmfit` (1.1.16) are quoted below as
"measured here".

## Findings

### llmfit: what it is

- MIT licence, single author doing most of the work (665 of the commits; next human
  contributor 44), 38k stars, created Feb 2026. Releases roughly weekly: v0.9.19 (3 May 2026)
  to v1.1.17 (8 Oct 2026) is 40 tags. ([releases](https://github.com/AlexsJones/llmfit/releases))
- A Rust workspace: `llmfit-core` (library, published on crates.io and docs.rs), `llmfit`
  (CLI/TUI, `serve` for REST and MCP), a desktop app, and a Python wheel that only ships the
  binary (`llmfit-python/hatch_build.py`).
- Dependencies of the core: `sysinfo`, `ureq`, `serde`, `regex`, `which`, and `objc2-metal`
  on macOS ([`Cargo.toml`](https://github.com/AlexsJones/llmfit/blob/main/llmfit-core/Cargo.toml)).

### How llmfit detects hardware

From [`hardware.rs`](https://github.com/AlexsJones/llmfit/blob/main/llmfit-core/src/hardware.rs)
and [`platform-support.md`](https://github.com/AlexsJones/llmfit/blob/main/docs/platform-support.md):

- **RAM and CPU**: `sysinfo` total and available memory; CPU name from `/proc/cpuinfo`;
  `vm_stat` fallback on macOS when `sysinfo` reports zero available.
- **NVIDIA (Linux)**: shells out to `nvidia-smi --query-gpu=...`; falls back to
  `/sys/class/drm` and `lspci` for the name, and estimates VRAM from the GPU model name if
  reporting fails.
- **AMD (Linux)**: `rocm-smi --showmeminfo vram` if ROCm is installed, else amdgpu sysfs
  `mem_info_vram_total` / `mem_info_vram_used`; special handling for APU UMA carve-outs
  (Strix Halo, issue #964).
- **CPU only**: no GPU found means backend `CPU (x86)` or `CPU (ARM)`.
- **Apple Silicon**: `system_profiler SPDisplaysDataType` to recognise an Apple GPU, then
  VRAM := total RAM. Separately it calls Metal's `recommendedMaxWorkingSetSize` through
  `objc2-metal` and reports it as `gpu_available_gb`; the source comment says it tracks a
  manual `sysctl iogpu.wired_limit_mb` (verified by the author on an M3 16 GB).
- **But fit grading on unified memory uses the total pool, not the Metal cap**:
  `SystemSpecs::gpu_fit_pool_gb` returns `total` when `unified_memory` is true ("Unified
  memory keeps the total pool"). Measured here with the bundled `apple-m3-max-128gb`
  profile: `llmfit concurrency openai/gpt-oss-120b --context 32768` reports `pool_gb: 128.0`
  and "Perfect". On a real Mac the GPU can wire only the Metal cap, which is what llama.cpp
  allocates against, so llmfit over-states what fits on exactly the platform we target.
- **Silent fallback** (measured here): on this WSL2 box `nvidia-smi` exists but fails
  (`couldn't find libnvidia-ml.so`). `llmfit system --json` then reports `has_gpu: false,
  backend: "CPU (x86)"` with no warning. With `LD_LIBRARY_PATH=/usr/lib/wsl/lib` it reports
  the RTX 4080 at 15.99 GB. A default chosen from the first answer would be wrong and nobody
  would be told.

### llmfit's model database

- `llmfit-core/data/hf_models.json`, 15.9 MB, **17,700 entries** scraped from the Hugging Face
  API and baked in with `include_str!` ([how-it-works](https://github.com/AlexsJones/llmfit/blob/main/docs/how-it-works.md#model-database)).
  Refreshed weekly by bot PR (#1140 on 15 Oct, #1112 on 7 Oct, #1077 on 29 Sep ...); newest
  `release_date` in the file is 12 Oct 2026. Current, then.
- Memory is computed from parameter counts across a quant ladder, not read from the GGUF the
  server will actually load. Spot checks against the model cards and llm-box:
  - `openai/gpt-oss-120b`: `active_parameters` 9.3 B; OpenAI's card and llm-box both say
    5.1 B active. The weights estimate (66.7 GB resident at MXFP4) is close to the 63 GB file
    llm-box serves.
  - `meta-llama/Llama-Guard-4-12B`: marked `is_moe: true`, 1.3 B active. Meta's card
    describes it as a dense 12 B model pruned from Llama 4 Scout. Its 16k KV estimate
    (0.39 GB) is a fifteenth of the dense `gemma-4-12B-it` (6 GB), which suggests the
    architecture metadata is wrong.
  - Many entries are draft heads or adapters (`gpt-oss-120b-Eagle3`, `-DFlash`); the REST
    API filters these from `/api/v1/models` ("Catalog sanitization" in API.md).
- Ranking is a weighted composite of quality (parameter count, family reputation, a per-family
  leaderboard table), speed, fit, and context. Nothing in it reflects how a model does on a
  middle-school readers'-advisory question set, which is what should pick our Answer model.

### llmfit's interfaces

From [API.md](https://github.com/AlexsJones/llmfit/blob/main/API.md):

- `llmfit serve --port 8787`: `GET /api/v1/system`, `/api/v1/models`, `/api/v1/models/top`,
  `/api/v1/models/{name}`, `/api/v1/concurrency`, `/api/v1/storage`, `POST /api/v1/plan`;
  Unix socket option; optional NATS events.
- `llmfit serve --mcp` (stdio): `get_system_specs`, `recommend_models`, `search_models`,
  `plan_hardware`, `get_runtimes`, `get_installed_models`.
- `llmfit concurrency <model>` answers "how many sessions of **one** model fit":
  `sessions = floor((pool - weights_resident) / kv_cache(ctx))`, GQA- and hybrid-aware
  ([`concurrency.rs`](https://github.com/AlexsJones/llmfit/blob/main/llmfit-core/src/concurrency.rs)).
  There is no command, endpoint, or MCP tool that charges two models against one pool. To ask
  "can Oversight share" we would call it twice and do the subtraction ourselves, against a
  pool figure we have just seen is wrong on Macs.

### Network behaviour (ADR-0006)

- Detection, `fit`, `plan`, `concurrency`, `recommend` work offline: the catalog and a
  benchmark cache are embedded in the binary.
- Outbound calls exist and are opt-in by command: `llmfit update` (Hugging Face API, cached in
  `~/.llmfit/`), downloads, and the localmaxxing.com benchmark client, which "includes an
  embedded cache as fallback when the API is unreachable"
  ([`benchmarks.rs`](https://github.com/AlexsJones/llmfit/blob/main/llmfit-core/src/benchmarks.rs)).
  A tool on the Install that knows how to reach the internet, and falls back quietly when it
  can't, is the shape ADR-0006 asks us to avoid even if we never call those commands.

### Packaging (ADR-0008)

- **flox catalog**: `llmfit@1.1.16`, MIT, for `aarch64-darwin`, `aarch64-linux`,
  `x86_64-linux` (`flox show llmfit`, 24 Oct 2026). So (a) would be one line in
  `[install]`.
- **nixpkgs**: `pkgs/by-name/ll/llmfit/package.nix`, maintained (Matthias Beyer), bumped
  within a week of upstream (1.1.15 to 1.1.16 on 25 Sep); three Apple GPU tests skipped in the
  sandbox. The workstation's pinned nixpkgs registry still resolves `nixpkgs#llmfit` to
  0.9.25, so the version an Install gets depends on the catalog pin, and llmfit's output
  schema has changed across those versions (`gpu_available_gb` and `pcie_links` are recent).
- llmfit's own repo ships a `flake.nix`, so pinning a revision is possible.

### What our own detection needs (do-it-yourself)

All available with the Python standard library and tools already on the box:

| Platform | Pool the model server can use | Source |
|---|---|---|
| Linux, NVIDIA | Sum of `memory.total` across cards, minus a margin per card | `nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader,nounits` |
| Linux, AMD | `mem_info_vram_total` per `/sys/class/drm/card*/device` | amdgpu sysfs, no ROCm needed |
| Linux, CPU only | `MemTotal` minus an OS and app reserve | `/proc/meminfo` |
| Apple Silicon | `recommendedMaxWorkingSetSize` | Metal, via `ctypes` into `libobjc` and `Metal.framework` (no PyObjC) |
| Apple, fallback | `hw.memsize` with a conservative fraction, marked "estimated" | `sysctl -n hw.memsize`, `sysctl -n iogpu.wired_limit_mb` |

Detection must report three states, not two: found, absent, and **failed** (a tool exists and
errored). Failed is shown to the Librarian with the error, and the planner picks no GPU
defaults rather than CPU ones.

### The co-residence calculation

For each lane model in the table we keep, measured rather than derived: the GGUF file size
(weights), KV bytes per token at the server's KV type, and a fixed per-server overhead
(compute buffers). Then:

```
need(model, ctx, slots) = weights + kv_per_token * ctx * slots + overhead
shared_ok = need(answer) + need(embed) + need(oversight) <= pool - headroom
```

`headroom` is a fraction of the pool plus a floor (llama-server's own `--fit-target` default
margin is 1024 MiB per device). Worked from llmfit's estimates (illustration only; the table
must use file sizes):

| Box | Answer | Oversight | Sum, 16k ctx | Verdict |
|---|---|---|---|---|
| Apple 24 GB (demo M5 Pro) | ~9 B dense Q4, ~6 GB | gpt-oss-20b, ~13 GB | ~19 GB + embed | Off: over the wiring cap |
| Apple 64 GB | Qwen3.6-35B-A3B Q4_K_M, ~20 GB | gpt-oss-20b, ~13 GB | ~34 GB + KV | Shared |
| Apple 128 GB | Qwen3.6-35B-A3B Q8_0, ~38 GB | gpt-oss-120b MXFP4, ~67 GB | ~108 GB + KV | Shared only with the wiring cap raised (`iogpu.wired_limit_mb`, as `docs/plan.md` already planned) |
| NVIDIA 16 GB | ~9 B dense Q4 | none | | Off |

Oversight is a different model family from the Answer model where the table allows it,
for the same reason llm-box's reviewer is not the coder's twin.

### Alternatives considered

- **llama-server `--fit`** (default on): adjusts unset arguments (layers offloaded, context)
  to fit the device's free memory. It fits one server at a time against whatever is free when
  it starts, so a second server started later sees the first one's allocation and silently
  shrinks its context. Useful as a safety net; it does not answer the planning question.
  We should pass explicit `--ctx-size` and `--parallel` so the plan is what runs.
- **gguf-parser-go** (MIT, release 23 Oct 2026): reads a GGUF's metadata and estimates memory
  per device including KV. Accurate for the file it reads, but not in the flox catalog
  (`flox search gguf-parser`: no match), and we only need its numbers once per table entry,
  at authoring time.
- **(b) port llmfit's detection**: the useful parts for our two platforms are small (the
  `nvidia-smi` parse, the amdgpu sysfs read, the Metal query); the rest of `hardware.rs`
  (7,148 lines) is Windows, Intel Arc, Ascend, Android, APU carve-outs. Porting would import
  its unified-memory grading choice too. Writing the five reads above is less code than
  porting and keeping a port in sync.
- **(a) depend on llmfit**: offline-capable, MIT, in the flox catalog. Rejected for the
  reasons in the Decision: it answers single-model fit, over-states Apple pools, falls back
  silently, recommends from a catalog we don't support, and its JSON shape moves weekly.

## Implementation tickets

Each is one Sonnet session. Order: T1 and T2 can start now in parallel; T3 needs the
golden-set evidence for its model choices; T4 needs T1 and T3; T5 needs T4 and the config
loader; T6 needs T5 plus the local llama-server service and the shared-box lock.

### T1. Hardware report from standard-library reads

Build `library_assistant/hardware.py`: pure parsers (meminfo text, `nvidia-smi` CSV, amdgpu
sysfs files, macOS `sysctl` output) and a thin runner that calls them, returning a
`HardwareReport` (platform, total RAM, accelerators, model-server pool in bytes, pool source,
and a list of problems). No new dependencies.

- [ ] Each parser is tested from fixture text: NVIDIA one and two cards, AMD sysfs, CPU-only
  meminfo, macOS sysctl
- [ ] A detection tool that exists but errors yields a `failed` accelerator with the stderr,
  never "no GPU" (fixture: the WSL `libnvidia-ml.so` message)
- [ ] The runner makes no network call and spawns only `nvidia-smi` and `sysctl`
- [ ] `flox activate -- bash scripts/check.sh` passes

Blocked by: nothing.

### T2. Metal working-set probe on Apple Silicon

Add the Apple pool reading: `recommendedMaxWorkingSetSize` via `ctypes` (`libobjc`,
`Metal.framework`, `MTLCreateSystemDefaultDevice`), falling back to `hw.memsize` times a
conservative fraction with the pool source marked `estimated`.

- [ ] On macOS the report's pool equals Metal's value; elsewhere the probe is skipped
- [ ] Unit tests cover the fallback path and run on Linux CI
- [ ] Human-verified on the M5 Pro: the printed value, before and after a temporary
  `sudo sysctl iogpu.wired_limit_mb=...`, recorded on the bead
- [ ] `flox activate -- bash scripts/check.sh` passes

Blocked by: T1.

### T3. The curated model table

Add `library_assistant/data/models.toml` and a loader: one entry per model we support, with
id, lanes it may serve (answer, oversight, embed), family, GGUF repo, file name, SHA-256,
file size in bytes, KV bytes per token at the server's KV type, native context, licence, and a
source note for each number. Seed it with the demo model and the candidates in this note.

- [ ] A schema test fails on a missing field or a number without a source
- [ ] Sizes come from the GGUF files (or their Hugging Face listing), not parameter counts
- [ ] A dev-only script compares each entry to `llmfit concurrency` (run through
  `nix shell nixpkgs#llmfit`, never installed in the Install's environment) and prints drift
  above 15%; not part of the gate
- [ ] `flox activate -- bash scripts/check.sh` passes

Blocked by: the golden-set comparison that picks the Answer model (plan item
`readers-advisory-set`); the demo model from `lib-f24.9` can go in first.

### T4. Lane planner

A pure function `plan(report, table, request)`; the request carries Answer context and slot
count, and whether Oversight is configured on this box. It returns the Answer and embedding
defaults, an Oversight verdict (`shared`, `second-box`, `off`), and the arithmetic behind it.

- [ ] Table-driven tests: Apple 24, 64, 128 GB (cap default and raised), NVIDIA 16 GB,
  CPU-only 32 GB, and a `failed` detection
- [ ] `shared` only when the sum of all resident models plus headroom fits the pool; any
  unknown pool gives `off`
- [ ] Every verdict carries a one-sentence reason a Librarian can read
- [ ] `flox activate -- bash scripts/check.sh` passes

Blocked by: T1, T3.

### T5. `hardware` command and defaults precedence

A CLI subcommand that prints the report and plan in plain language, and `--write-defaults`,
which writes a defaults file the config loader reads beneath the Librarian's config.

- [ ] Precedence is the Librarian's config, then the defaults file, then built-ins; a test
  shows a configured model name survives `--write-defaults`
- [ ] When the configured Answer endpoint is not on this machine (not loopback), the command
  says to run it on the model server's machine and writes nothing
- [ ] Oversight is never switched on by defaults unless the plan says `shared` and the
  Librarian has configured an Oversight lane
- [ ] `flox activate -- bash scripts/check.sh` passes

Blocked by: T4; the `lib-f24` bead that introduces the lane config (story 31).

### T6. Fit probe after the servers start

Once the Answer and Oversight llama-servers are up on one box, confirm the plan: both
`/health` ok, both report the planned `n_ctx` (llama-server `/props`), and free GPU memory
(or Metal headroom) is above the planned margin. If not, record why and keep Oversight off
for the shared box.

- [ ] Tested with fake servers: a server reporting a smaller context than planned (the
  `--fit` shrink) turns Oversight off with that reason
- [ ] Servers are started with explicit `--ctx-size` and `--parallel` from the plan
- [ ] Human-verified once on Apple Silicon with both models resident
- [ ] `flox activate -- bash scripts/check.sh` passes

Blocked by: T5, `lib-f24.9` (local llama-server service), `lib-f24.14` (shared-box lock).

## Not confirmed

- macOS's default `recommendedMaxWorkingSetSize` as a fraction of RAM on M5 machines.
  Commonly quoted as about two thirds to three quarters; not checked on hardware. T2 measures it.
- Whether llama.cpp's Metal backend refuses to allocate past `recommendedMaxWorkingSetSize`
  or only slows down; the plan treats it as a hard limit.
- The model sizes in the co-residence table are llmfit 1.1.16 estimates, not GGUF file sizes.
- Meta's and OpenAI's model cards were cited from memory of their published figures (dense 12 B;
  5.1 B active), corroborated for gpt-oss-120b by llm-box's comments, not re-fetched here.
- llmfit on Apple Silicon and on AMD was read from source and docs, not run.
