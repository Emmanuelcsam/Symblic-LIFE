# LIFE round-1 critique packet (ChatGPT web, highest effort)

## Critic brief
You critique LIFE, a Symblic script kit meant to turn a home cluster into a perpetually living self-improving system (cells = worker + reproducer agent pairs on lightweight local models; autogen lanes; reproduction admitted only by code). The kit is under docs/life (read LIFE.md fully, then the organs, policies, genome, checks, spawn protocol, db schema, README). All of their full text is in this packet. Highest effort. Your job: find EVERY detail that is not atomically defined (any threshold, file, schema, interval, model, engine, node, check, exit code, failure path, race, ordering, budget, unit or ownership that a lightweight model or a fresh agent could interpret in two ways), every contradiction with the platform facts in BRIEF.md (included below), every unsafe or unbounded behaviour (runaway spawning, resource exhaustion, heat, secrets, writes outside the workspace, live-code damage, restart loops), and every missing organ or path the operator's brief requires. Output numbered findings: severity (high/medium/low), location (file and section or line number), the exact ambiguity or defect, and the atomic definition or fix to adopt (write the replacement text where possible). End with two integers on their own lines: FINDINGS_TOTAL=<n> and UNDEFINED_DETAILS=<n> (the count of findings that are undefined or ambiguous details), and a final line VERDICT=<CONVERGED|CHANGES NEEDED>.

Note: the kit has NOT been run; it was written but deliberately not executed. Critique the text only.


===== FILE: BRIEF.md =====
# LIFE: the operator's brief (verbatim intent, 2026-10-11)

"I talked about making perpetual 'life' and I want you to write up an extremely exhaustively extensively
meticulously detailed symblic script built to make that perpetually living system turning my cluster into a
self improving system that continuously takes commands, optimizes the codebase, fixes errors, learns from the
internet, develops itself based on things it learns, creates databases, figures out new ways to compute and
store data and LIVES (reproduces and learns efficiently). Make this symblic script that will bring my cluster to
life but don't run it. Workshop this symblic script with ChatGPT (web) at its highest effort and Claude cloud at
its highest effort until every minor detail in this symblic script is atomically defined, since the subagents
running the intricate script are expected to be extremely lightweight models to keep processing power low, but
each subline has two focuses, maybe two agents per subtask: one to perform an extremely specific task and the
other to reproduce, just like how cells come with different functions but they need to subdivide to keep the
whole system going."

Earlier operator words that bind this design (10 Oct): one agent per line by default; agents regenerate until their
task is complete or they split off what they cannot do; no time cap while they try new things; the master
coordinator may spawn as many agents as needed; research lanes must avoid duplicate sources and may run for days;
"a living breathing cluster"; the Symblic program is the gcode and an agent is the 3D printer; model/agent work
runs on the worker nodes, the host only orchestrates; keep continuous all-worker node load under about an hour before resting;
models propose, code decides; no credentials in shared documents; guest internet off; nothing restarts itself.

# What exists that the script must use (facts, verify in the code before relying on a detail)

- Statement scripts: `bin/symblic-task` lines (one statement per line, 20-1500 chars, at most 64 per task,
  verbs from `symblic_autogen.VERBS`, absolute folder named, "keeping every existing part" on edits, a verify
  line writing verify.txt). Autogen policy fields: candidates, regenerate, depth, children, generations,
  agents_max, attempt_seconds, wall_seconds, interval_seconds, feedback_chars, strategies, perpetual, checks,
  final, hidden, syntax, require_change, until_done, novelty_limit, self_split, designer, saturation
  (`symblic_autogen.LIMITS/DEFAULTS`). Perpetual lanes: one generation per interval, checkpoint
  AUTOGEN-CHECKPOINT.json {version, done, left, files, items}, HANDOFF.md, dedup index AUTOGEN-INDEX.jsonl keyed
  by DOI/URL/text; saturation stop. Until-done: no caps; stall split; self-split (AUTOGEN-SPLIT.txt); designer
  (AUTOGEN-TESTS.sh, sandboxed); stuck + resume (+extend). Contracts: docs/symblic/AUTOGEN.md, RECURSION.md.
- Engines for autogen attempts: CLI agents only (agy, claude, codex, mistral, copilot), placed on a node by the
  Agents hub; verification at home in a staging checkout; promotion = commit -> apply. Local Ollama models are
  reached through the formal language (`bin/symblic run F.sym --by ollama:qwen3:4b-instruct`), English
  statements, delegate templates, spec sheets, `bin/local-research` (SearXNG web research with local models) and
  the `local` task engine (cli-agent over Ollama; refuses long inputs).
- Cluster: the host (serves the site, orchestrates only), node-arm (ARM board, manager), node-a/b/d/f (~15.5 GB),
  node-h (~28 GB), node-i (~31 GB); CLI logins exist on the host; worker nodes run agents through the hub's registered
  launch path (no SSH shortcuts, no worker node tunnel to :8080). Capacity/heat: docs/fleet-power.md; high-power mode leases
  are bounded; rest after long load.
- Safety invariants (CLAUDE.md): private stores never in prompts/docs; no new SSH bypass; service worker/CSP rules;
  Python/API changes are restart-gated and warned; never restart slices or the busy browser daemon; tests isolate
  every store; code decides acceptance; `bin/devcheck` before commits; preserve others' work.
===== END BRIEF.md =====

===== FILE: LIFE.md (sections 1-11; section 12 appendices are the files below in full) =====
# LIFE v1 — the master Symblic script that brings the cluster to life

Author's note. This is a complete, self-contained script. It is **written, not run**. It was
workshopped against the platform's own code (every fact below was checked in the live checkout on
2026-10-11 with no model, agent or cluster job). Where the platform cannot do something the brief
asks, §11 (GAPS) says so plainly, with the smallest platform change that would close it and the
interim rule this script follows meanwhile. Every statement line here passes
`symblic_autogen.lint` with zero errors and zero warnings; every policy passes
`symblic_autogen.normalize`; every `.sym` passes `bin/symblic check`; every shell check passes
`bash -n`. Run `VALIDATE.sh` to confirm (§10). It calls no model, agent or cluster job.

Design stance, from the operator's brief: a living, breathing cluster that continuously takes
commands, optimises its codebase, fixes errors, learns from the internet, develops itself from
what it learns, creates databases, finds new ways to compute and store data, and **reproduces and
learns efficiently**. The Symblic program is the gcode; an agent is the 3D printer. Lightweight
models do the work; CLI agents are used only where a full tool loop is unavoidable. Models
propose; code decides. Nothing restarts itself.

---

## 1. The cell: one subtask, two agents

A **cell** is one subtask. Like a living cell it has two functions that must stay separate:

- **WORKER** — performs one extremely specific task and nothing else. It is a **lightweight local
  model** wherever the task is a typed decision, an extraction, a classification or a bounded file
  edit (reached through the formal language `genome/*.sym`, English statements, delegate
  templates, spec sheets or `bin/local-research`). It is a **CLI agent** (agy first) only where
  the task genuinely needs a full read-edit-run tool loop — for example applying and testing a
  multi-file code patch. A cell is realised as one statement inside an organ's autogen lane; the
  lane's attempt is a CLI agent that, for every typed decision in its batch, calls the matching
  lightweight-model program rather than deciding itself.
- **REPRODUCER** — never does the task. It reads the cell's own metrics (generation, failures in a
  row, new items last generation, lineage depth) and decides whether and how the cell divides. It
  runs `genome/reproduce.sym` on a lightweight model and returns `stay`, `divide` (with two
  distinct child foci) or `apoptosis`. On `divide` it writes a **spawn record** — it does not
  start anything.

This mirrors cell biology: a differentiated cell keeps doing its one job, while division is a
separate, tightly controlled act that keeps the whole organism going. Reproduction is **admitted
only by code**: the orchestrator `bin/life-spawn-tick.py` on the host validates each spawn record
(lint + normalize + budget + lineage depth + content-hash dedup) and only then starts the child
run with `bin/symblic-task`. No model ever launches a run. See §4 and `spawn/PROTOCOL.md`.

Why two agents and not one process doing both: a worker that could also spawn would reproduce its
own mistakes without review. Splitting the functions means every division passes through the
code gate, and a failing cell (failures_in_a_row > 0) is refused division by the reproducer's own
`ensure` check **and** cannot pass the orchestrator budget. The content-hash dedup is the brake on
runaway self-replication: a reproducer that re-proposes identical work is a silent no-op.

## 2. The organism: ten organs

The organism lives in one git-backed workspace, `/home/operator/symblicos/projects/life` (created by
`bin/symblic-task workspace life`; `symblicos/workspaces.py` runs `git init` on `main`). Each organ
is its **own** autogen run with its own `--id`, because autogen runs statements strictly in order
and a perpetual lane never ends — so concurrent organs must be separate runs (RECURSION.md §3.1,
verified in `symblicos/autogen.py:_current`). Each organ writes into its own `organ-<name>/`
subfolder and keeps its own `AUTOGEN-INDEX.jsonl` dedup ledger.

| # | Organ | Lane file | Engine | Node (class) | Default model for its typed decisions | Interval | Kind | Acceptance check |
|---|-------|-----------|--------|--------------|----------------------------------------|----------|------|------------------|
| 1 | command inbox | organs/command.lines.txt | agy | node-f (mid, keepAwake) | qwen3:4b-instruct@node-a (classify-command.sym) | 120 s | perpetual | `test -s verify.txt` |
| 2 | codebase fixer | organs/codebase.lines.txt | agy | node-i (heavy) | qwen2.5-coder:3b (triage-error.sym) + agy tool loop | 1800 s | perpetual, sat 4 | `test -s verify.txt`, then devcheck-gate in checkout |
| 3 | learning | organs/learning.lines.txt | agy | node-d (mid) | qwen3:4b-instruct via bin/local-research | 1800 s | perpetual, sat 3 | `test -s verify.txt` |
| 4 | digest | organs/digest.lines.txt | agy | node-f (mid) | qwen3:4b-instruct@node-d (extract-source.sym) | 900 s | perpetual, sat 3 | `test -s verify.txt` |
| 5 | self-development | organs/selfdev.lines.txt | agy | node-i (heavy) | qwen3:4b-instruct (proposes edits to genome/policies) | 3600 s | perpetual, sat 4 | `test -s verify.txt` |
| 6 | compute/storage R&D | organs/compute.lines.txt | agy | node-i (heavy) | qwen3:4b-instruct@node-i (rank-experiment.sym) | 3600 s | perpetual, sat 4 | `test -s verify.txt` |
| 7 | metabolism (energy) | organs/metabolism.lines.txt | agy | the host (i/o only) | none — reads cluster APIs, no model | 300 s | perpetual | `test -s verify.txt` |
| 8 | immune | organs/immune.lines.txt | agy | node-i (heavy) | qwen2.5-coder:3b@node-f (review-patch.sym) | 1800 s | perpetual, sat 6 | `test -s verify.txt` |
| 9 | heartbeat | organs/heartbeat.lines.txt | agy | the host (i/o only) | none — reads ledgers, no model | 300 s | perpetual | `test -s verify.txt` |
| 10 | database | organs/database.lines.txt | agy | node-a (light) | none — writes SQL, runs sqlite3 | — | bounded build | `test -s verify.txt` + final check_schema.sh |

Node classes (verified against `cluster_data/nodes.json` and the live capacity probe, 2026-10-11):
**light** = node-a, node-b (8 cpu, ~15.6 GB free, Ollama cap 12 GiB, models up to qwen3:4b-instruct);
**mid** = node-d, node-f (node-f keepAwake, has granite3.3:2b, phi4-mini, ministral); **heavy** =
node-i (16 cpu, ~31 GB, Ollama cap 26 GiB, high-power mode top rank, underused) and node-h (28 GB but
Ollama cap **3 GiB** → only models ≤2.5 GB, and it is overcommitted, so LIFE avoids it for model
work); **never for models** = the host (host; i/o-only lanes allowed because agy CLI is not a local
model) and node-arm/the ARM node (failover standby; the fleet runner runs nothing there).

Every perpetual organ drops `other_node` from its strategies (`fresh,feedback,other_engine`),
because `other_node` round-robins over every online node including the host and the ARM node
(`symblicos/autogen.py` `next_strategy`), which must never host a model lane. A node going to sleep
between generations therefore shows as INFRASTRUCTURE and the lane waits rather than migrating to
The host; LIFE places perpetual lanes on nodes that stay awake (node-f keepAwake; node-i/node-d/node-h
are protected infrastructure) to keep this rare.

## 3. Lightweight-first: the model ladder

Cells try the cheapest capable model first and only climb when a check fails. All of these are on
the installed list (`bin/local-research --list`, 2026-10-11). Cloud CLIs are last resort.

| Rung | Model | Installed on | Used by | Lane |
|------|-------|--------------|---------|------|
| 0 | qwen2.5:0.5b | node-a/b/d/f/i | tiniest yes/no and 2-way choice | formal `.sym` ask, effort=low |
| 1 | llama3.2:1b | all worker nodes | urgency/confidence/risk labels | `.sym` ask, effort=low |
| 1 | gemma3:1b | node-a/b/d/f/i | short enum choice | `.sym` ask |
| 2 | deepseek-r1:1.5b | node-a/b/f | small reasoned choice | `.sym` ask, effort=medium |
| 2 | granite3.3:2b | node-d/f/i | novelty label, 2-class | `.sym` ask |
| 3 | qwen2.5-coder:3b | node-a/b/d/f/i | error triage, patch review | triage-error.sym, review-patch.sym |
| 4 | qwen3:4b-instruct | all worker nodes incl node-h | **default** typed decision, fact extraction, routing, ranking, local-research | classify/extract/rank/reproduce.sym, bin/local-research |
| 4 | gemma3:4b | node-d/f/i | alt 4B for family diversity in votes | `.sym` ask, effort=ultra |
| 4 | phi4-mini | node-d/f/i | alt 4B reasoning | `.sym` ask |
| big | qwen2.5:14b, qwen3.8:27b, laguna-xs-2.1 | node-i only | reserved; not used by default cells (heat) | manual `--by ollama:...@node-i` |

Lanes a lightweight model reaches (all call no cloud, run on a worker node through the fleet runner's one-model-per-node cap):
- **formal `.sym` asks** with `ensure` checks — the six `genome/*.sym` programs. The kernel checks
  the answer (type, range, verbatim quote, enum, record fields). This is the main lane.
- **English statements** (`bin/symblic english`) — for the simplest closed questions a 0.5–1B model
  can answer; compiles to the verified profile, `context=none`.
- **delegate templates** (`bin/symblic delegate`) — `enum_classification` for routing/triage,
  `witnessed_line` for quote extraction, `typed_transform` for structured edits; local ladder
  1B→Granite 2B→Qwen 4B when no `--by` is given.
- **spec sheets** (`bin/symblic spec`) — when a cell must produce checked JS/HTML, each unit is a
  `Code js` ask tested in a sandbox before acceptance; suits 0.5B–1B workers (`signatures` view).
- **`bin/local-research`** — the learning organ's web lane: a local model drives SEARCH/READ/ANSWER
  over SearXNG at 127.0.0.1:18888; the model never touches the network directly; calls go through
  `fleet_runner.launch` (the only safe path — a direct the host Ollama call caused the 2026-09-30
  oomd kill).
- **the `local` task engine** (cli-agent over Ollama, 8192 ctx) — only in lines/agent tasks, never in
  autogen; LIFE uses it only for short discrete helper turns, because it refuses long inputs.

**When a CLI agent is allowed.** Only inside the codebase, selfdev and database organs, and only
for the apply-and-test tool loop. Order: **agy** first (cheapest, local-friendly), then **codex**,
then **claude**, then **copilot** (the host only) or **mistral** (node-a/b only). The `other_engine`
strategy rotates within `ENGINES ∩ ADMITTED_ENGINES`, so a stuck lane escalates engines
automatically without a model ladder (which `normalize` refuses).

## 4. Reproduction (admitted by code)

Full detail in `spawn/PROTOCOL.md`; the orchestrator is `bin/life-spawn-tick.py`. Summary:

1. A reproducer cell runs `genome/reproduce.sym`. On `divide` it writes `spawn/queue/<name>/` with
   `statements.txt`, `policy.json`, `lineage.json`, `reason.txt`.
2. `bin/life-spawn-tick.py` (operator's timer, the host, no model) checks, in order: **kill switch**
   (STOP absent), **heat gate** (`checks/heat-gate.sh`), **budget** (< `LIFE_MAX_RUNS`=16 live
   `life-*` runs), **lint** (0 errors, 0 warnings), **normalize**, **lineage depth** (< 10, ≤ 64,
   `cell_id` = `organ.generation.8hex`), **content-hash dedup** (`spawn/hashes.txt`).
3. On all-pass it starts the child with `bin/symblic-task start … --id life-<organ>-<8hex>` plus the
   flags `policy_flags()` derives from `policy.json`, records the hash, and files the record under
   `spawn/approved/`. Any failure files it under `spawn/rejected/` with a reason.

`apoptosis` writes no record; it appends the cell_id to `spawn/retired.txt` and the operator/immune
organ cancels the run. A retired cell's content hash stays known, so it is never re-spawned.

## 5. Databases

`db/schema.sql` defines five tables in one SQLite file
`/home/operator/symblicos/projects/life/db/life.sqlite3`, all `CREATE TABLE IF NOT EXISTS` so a
re-apply never drops rows: **knowledge** (one checked fact per row: id, claim, quote, source_id,
source_url, organ, created_at, verified), **lineage** (the cell family tree: cell_id, organ,
parent_id, depth, focus, spawn_reason, content_hash, run_id, created_at, retired_at; unique index
on content_hash), **metrics** (one row per organ generation: organ, run_id, generation, new_items,
failures, node, at), **commands** (operator commands with their route), **experiments** (compute R&D
proposals and measured results). Migrations are statements in the database organ's lane
(`organ-database/migrations/0001_init.sql`), each idempotent, each verified by `check_schema.sh`.
The exact columns and types are in Appendix E.

## 6. Metabolism (energy) and heat

The metabolism organ (the host, i/o only, every 300 s) reads `/api/cluster/status`, `/capacity` and
`/highpower/state` from the loopback dashboard and writes a `metabolism.jsonl` row deciding whether
fan-out is allowed. Rules, from the operator heat rule and `docs/fleet-power.md`:
- **Continuous all-worker node load stays under ~1 hour**, then rest. Each organ's `wall_seconds` and
  `interval_seconds` build the rest in; the orchestrator's `heat-gate.sh` refuses new spawns when
  The host 1-min load ≥ 4.0 or io full avg10 ≥ 40.0.
- **high-power mode only when a batch justifies it**: a 5–120 min lease, never chained (a new lease is
  refused for as long as the last ran). LIFE never enables high-power mode automatically in v1 — the
  compute organ may *request* it by writing a row the operator approves (§11 gap). The host never runs
  a model.
- the fleet runner enforces one model per node at a time; LIFE respects that by one perpetual model lane per
  worker node plus the shared formal-language calls.

## 7. Immune system

The immune organ (node-i, every 1800 s) runs three jobs each generation: **canary checks** (a list
in `organ-immune/canaries.txt` of cheap commands that must keep passing — e.g. `bin/symblic check`
on each genome file), **adversarial patch review** (`genome/review-patch.sym`: a second model must
`accept` a codebase patch, and only when its automated checks already passed — a model accept alone
never promotes), and **quarantine** (a lineage whose cells fail `novelty_limit` generations in a row
is written to `organ-immune/verdicts.jsonl` and its run cancelled by the operator). **Rollback** uses
git: every promotion is a Work→Apply 3-way merge into the live checkout with nothing committed, so a
bad apply is reverted with `git checkout -- <file>` in the live tree (the operator's existing recovery
path). LIFE never force-pushes and never restarts the dashboard.

## 8. Observability (heartbeat)

The heartbeat organ (the host, every 300 s) writes `organ-heartbeat/status.json` summarising each
organ's last generation, new items and failures, and `bin/life-status.py` prints the same from the
run records on demand. What the operator looks at: `bin/life-status.py`, `bin/symblic-task autogen
list`, `bin/symblic-task autogen get life-<organ> --tasks`, and the per-organ `verify.txt`.

## 9. Starting it, and the reproduction timer

Seeding: `bin/life-seed.sh` (Appendix F) — creates the workspace, folders and schema copy, and
starts the ten organ runs. Reproduction stays **off** until the operator installs a systemd *user*
timer for the orchestrator. Suggested unit text (the operator installs this; it is not installed here):

```ini
# ~/.config/systemd/user/life-spawn.service
[Unit]
Description=LIFE spawn orchestrator tick (validates and births queued cells)
[Service]
Type=oneshot
Environment=DASH_URL=http://127.0.0.1:8080
ExecStart=/usr/bin/python3 /home/operator/host-checkout/docs/life/bin/life-spawn-tick.py
Nice=10
```
```ini
# ~/.config/systemd/user/life-spawn.timer
[Unit]
Description=Run the LIFE spawn tick every 5 minutes
[Timer]
OnBootSec=5min
OnUnitActiveSec=5min
[Install]
WantedBy=timers.target
```
Enable with `systemctl --user enable --now life-spawn.timer`. The tick is niced, calls no model,
and births nothing while `STOP` exists or the heat gate holds.

## 10. Validation (no model, no agent, no network)

`VALIDATE.sh` runs exactly: `symblic_autogen.lint` on every organ lines file (must be 0 errors and
0 warnings), `symblic_autogen.normalize` on every policy, `bin/symblic check` on every genome
program, `bash -n` on every shell script, `python3 -m py_compile` on every python script, and an
in-memory idempotent apply of `db/schema.sql`. It prints PASS/FAIL per file and exits non-zero on
any failure. It starts no task and calls no model.

## 11. GAPS — what the platform cannot do, and the interim rule

1. **No autogen engine can launch a new autogen run from inside a run.** There is no
   recursion-to-new-run primitive in the statement layer; a worker calling the loopback API to
   spawn is out of policy. *Interim rule:* reproduction is a **separate code path** — the operator's
   timer runs `bin/life-spawn-tick.py`, which is the only launcher. *Smallest platform change:* an
   autogen `spawn` policy field / coordinator hook that, on a validated on-disk spawn record,
   submits a sibling run under the same global budget. Then reproduction would need no external
   timer.
2. **Autogen attempts are CLI agents only** (`ADMITTED_ENGINES` = agy, claude, codex, mistral,
   copilot). Lightweight local models cannot *be* autogen workers. *Interim rule:* the lane's CLI
   agent calls `bin/symblic run genome/*.sym --by ollama:MODEL@node-X` (and local-research/delegate)
   for every typed decision, so the heavy thinking is still a 0.5–4B model; the CLI agent is only
   the hands. *Smallest change:* admit `ollama`/`local` as an autogen engine for pure typed-decision
   statements (schema-checked), so a cell could be a bare local model with no CLI wrapper.
3. **Remote handoff is refused** ("remote handoff unsupported"; no `workspaceFrom`). The
   `generations` context-handoff mechanism works only for the host-local attempts. *Interim rule:*
   worker node lanes rely on **self-split** (`AUTOGEN-SPLIT.txt`) and decompose instead of handoff; the
   database organ (bounded, `--handoff 2`) runs on node-a where a handoff that does need carrying
   can be reconsidered, but its policy leans on self-split. *Smallest change:* a `workspaceFrom`
   in task submit so a successor attempt can inherit a predecessor's checkout on a worker node.
4. **The formal language's `delegate` targets the /agents hub, not Ollama directly** (`local` needs
   `model=`, `cwd` defaults to `~`). LIFE does not use `delegate` for cell work; it uses `.sym`
   asks `--by ollama:...`. *Interim rule:* no `delegate` inside LIFE v1. *Smallest change:* none
   needed; noted so an author does not reach for `delegate` expecting a light-model call.
5. **No fleet-wide heat governor inside autogen.** Only `interval_seconds` and `attempt_seconds`
   space and bound work. *Interim rule:* the metabolism organ + `heat-gate.sh` + conservative
   intervals + `wall_seconds` caps implement rest; the operator is asked before long worker node load.
   *Smallest change:* an autogen duty-cycle field that pauses all lanes when a cluster heat signal
   trips.
6. **high-power mode cannot be safely self-chained** (a new lease is refused for as long as the last
   ran). *Interim rule:* LIFE never enables high-power mode on its own; the compute organ writes a
   request row for the operator. *Smallest change:* an admitted, rate-limited high-power mode request API a
   metabolism cell could call with a justification and a bounded lease.
7. **`other_node` can place a lane on the host or the ARM node.** There is no node allow-list policy
   field. *Interim rule:* every model lane omits `other_node` and names a safe worker node. *Smallest
   change:* an autogen `nodes_allow` field so a lane can rotate nodes without risking the host/ARM node.
===== END LIFE.md (sections 1-11; section 12 appendices are the files below in full) =====

===== FILE: README.md =====
# LIFE v1 — how to bring the cluster to life (and the kill switch)

This folder is a **script kit**, not a running system. Nothing here has been started. The operator
starts it, once, when they choose. Read this file, then `LIFE.md` (the complete master script).

LIFE turns the cluster into a perpetually living, self-improving organism built entirely from the
existing Symblic autogen engine (`bin/symblic-task`), the formal language (`bin/symblic`) run on
lightweight local models, and `bin/local-research`. The host only orchestrates; models run on the
worker nodes. Models propose; code decides every acceptance and every reproduction.

## What it is made of

- **Ten organs**, each its own perpetual (or, for the database, bounded) autogen run:
  `organs/<organ>.lines.txt` (the statement) + `policies/<organ>.json` (the policy).
- **Six genome programs** the lightweight models run as typed decisions with kernel checks:
  `genome/*.sym`.
- **Reproduction by code**: `spawn/PROTOCOL.md` + `bin/life-spawn-tick.py` (the orchestrator).
- **Databases**: `db/schema.sql` (knowledge, lineage, metrics, commands, experiments).
- **Checks**: `checks/*.sh`. **Observability**: `bin/life-status.py`.

## Start it (operator, on the host)

1. **Validate the kit (safe, no model, no agent, no network):**
   ```
   docs/life/VALIDATE.sh      # prints PASS/FAIL per file; must end ALL PASS
   ```
2. **Warn before any restart** — LIFE starts no server changes, but confirm the dashboard is up
   and `DASH_URL=http://127.0.0.1:8080` resolves to this machine.
3. **Seed the organism:**
   ```
   docs/life/bin/life-seed.sh     # creates workspace life, starts the 10 organ runs
   ```
   It asks you to type `START`. It creates `/home/operator/symblicos/projects/life` (git-backed),
   the per-organ folders, copies `db/schema.sql`, and starts each organ as its own run on its
   node. It calls only `bin/symblic-task` — no model is called by a start.
4. **Watch it live:**
   ```
   docs/life/bin/life-status.py
   bin/symblic-task autogen list
   bin/symblic-task autogen get life-learning --tasks
   ```
5. **Turn on reproduction (optional, later):** install a systemd *user* timer that runs
   `bin/life-spawn-tick.py` every few minutes. The unit text is in `LIFE.md` §9. Until you install
   it, cells never divide — the ten seed organs simply run and rest. The tick is pure code: it
   validates queued spawn records (lint + normalize + budget + depth + dedup) and starts the valid
   ones. Nothing restarts itself; an older/stuck run needs `bin/symblic-task autogen resume`.

## KILL SWITCH

- **Freeze reproduction instantly:** create the stop file.
  ```
  touch /home/operator/symblicos/projects/life/STOP
  ```
  `bin/life-spawn-tick.py` exits 3 and births nothing while `STOP` exists. Running lanes finish
  their current generation and then rest (they are perpetual; they wait `interval_seconds`).
- **Stop a single organ:** `bin/symblic-task autogen cancel life-<organ>`.
- **Stop everything:**
  ```
  for r in $(bin/symblic-task autogen list | awk '/life-/{print $1}'); do bin/symblic-task autogen cancel "$r"; done
  ```
- **Cool the hardware:** `curl` is not used by LIFE; use the dashboard high-power mode **cool** control
  (operator-only) to pin every worker node to its cool thermal mode. LIFE's metabolism organ never turns cool off.
- Remove `STOP` to allow reproduction again. Cancelled runs do not restart themselves; re-seed or
  `autogen resume` the ones you want back.

## Safety summary

No credentials or private-store values are ever written by LIFE. Guest internet is untouched
(off). No SSH bypass, no worker node tunnel. Codebase patches reach the live checkout only through the
existing Work→Apply path and only for the change classes the master script permits; restart-gated
changes are queued as a request for you, never applied by a cell. The heat rule is enforced by the
metabolism organ and the orchestrator's heat gate.
===== END README.md =====

===== FILE: organs/codebase.lines.txt =====
Read the findings in the folder /home/operator/symblicos/projects/life/organ-codebase/findings, pick one small finding whose change class the master script permits, write a proposed patch and its focused test into the folder /home/operator/symblicos/projects/life/organ-codebase/patches, run the focused test, and verify this batch by writing the finding id and the test result to the file verify.txt.
===== END organs/codebase.lines.txt =====

===== FILE: organs/command.lines.txt =====
Read every file in the folder /home/operator/symblicos/projects/life/organ-command/inbox, classify each new operator command into one organ and urgency by running the command classifier, append one JSON line per command to the file /home/operator/symblicos/projects/life/organ-command/routed.jsonl, and verify this batch by writing the count of routed commands to the file verify.txt.
===== END organs/command.lines.txt =====

===== FILE: organs/compute.lines.txt =====
Read the ranked experiments in the file /home/operator/symblicos/projects/life/organ-compute/experiments.jsonl, run the highest-scoring experiment whose measurement command fits one node and fifteen minutes, write its hypothesis, command, measured number and threshold into the folder /home/operator/symblicos/projects/life/organ-compute/results, and verify this batch by writing the experiment id and whether the threshold passed to the file verify.txt.
===== END organs/compute.lines.txt =====

===== FILE: organs/database.lines.txt =====
Create the file /home/operator/symblicos/projects/life/organ-database/apply.sh that runs sqlite3 on the database file life.sqlite3 in the folder /home/operator/symblicos/projects/life/db and applies the schema file schema.sql, exiting nonzero on any sqlite error.
Create the file /home/operator/symblicos/projects/life/db/schema.sql defining the tables knowledge, lineage, metrics, commands and experiments with the exact columns and types named in the master script, using create table if not exists so a rerun is a no-op.
Create the file /home/operator/symblicos/projects/life/organ-database/migrations/0001_init.sql holding the same create table if not exists statements so the first migration is idempotent and leaves existing rows untouched.
Create the file /home/operator/symblicos/projects/life/organ-database/check_schema.sh that runs sqlite3 on the database file life.sqlite3 and confirms every expected table and column exists, printing one line per table and exiting nonzero when a table or column is missing.
Verify the database build by running check_schema.sh in the folder /home/operator/symblicos/projects/life/organ-database and writing its full output and the exit status to the file verify.txt.
===== END organs/database.lines.txt =====

===== FILE: organs/digest.lines.txt =====
Read the unprocessed sources in the file /home/operator/symblicos/projects/life/organ-digest/sources.jsonl, extract one checked fact per source by running the source fact extractor so every quote is copied verbatim, append one JSON line per fact to the file /home/operator/symblicos/projects/life/organ-digest/facts.jsonl, and verify this batch by writing the count of new facts to the file verify.txt.
===== END organs/digest.lines.txt =====

===== FILE: organs/heartbeat.lines.txt =====
Read the ledgers and verify files produced by every organ under the folder /home/operator/symblicos/projects/life, summarise each organ's last generation, new items and failures, write one status snapshot to the file /home/operator/symblicos/projects/life/organ-heartbeat/status.json, and verify this snapshot by writing the number of organs seen to the file verify.txt.
===== END organs/heartbeat.lines.txt =====

===== FILE: organs/immune.lines.txt =====
Read the open patches in the folder /home/operator/symblicos/projects/life/organ-codebase/patches and the canary list in the file /home/operator/symblicos/projects/life/organ-immune/canaries.txt, run each canary check and one adversarial patch review, record each verdict and any quarantine to the file /home/operator/symblicos/projects/life/organ-immune/verdicts.jsonl, and verify this batch by writing the count of rejected or quarantined items to the file verify.txt.
===== END organs/immune.lines.txt =====

===== FILE: organs/learning.lines.txt =====
Research the open questions listed in the file /home/operator/symblicos/projects/life/organ-learning/questions.txt, find three sources with a DOI or URL that are not already in the index, append one JSON line per source to the file /home/operator/symblicos/projects/life/organ-learning/sources.jsonl, and verify this batch by writing the three new source keys to the file verify.txt.
===== END organs/learning.lines.txt =====

===== FILE: organs/metabolism.lines.txt =====
Read the cluster status and capacity and highpower state from the dashboard loopback api, compute the current continuous all-worker node load minutes and free capacity, write one metabolism row with the readings and whether fan-out is allowed to the file /home/operator/symblicos/projects/life/organ-metabolism/metabolism.jsonl, and verify this batch by writing the fan-out decision to the file verify.txt.
===== END organs/metabolism.lines.txt =====

===== FILE: organs/selfdev.lines.txt =====
Read the lessons in the file /home/operator/symblicos/projects/life/organ-selfdev/lessons.jsonl, draft one improvement to a genome program or organ policy under the folder /home/operator/symblicos/projects/life/organ-selfdev/proposals keeping every existing part that still applies, add a check that proves the improvement, and verify this batch by writing the proposal id and its check result to the file verify.txt.
===== END organs/selfdev.lines.txt =====

===== FILE: policies/codebase.json =====
{
  "version": 1,
  "perpetual": true,
  "interval_seconds": 1800,
  "attempt_seconds": 3600,
  "wall_seconds": 43200,
  "candidates": 1,
  "regenerate": 3,
  "agents_max": 16,
  "saturation": 4,
  "strategies": ["fresh", "feedback", "other_engine"],
  "syntax": true,
  "require_change": true,
  "checks": {"0": ["test -s verify.txt"]},
  "final": []
}
===== END policies/codebase.json =====

===== FILE: policies/command.json =====
{
  "version": 1,
  "perpetual": true,
  "interval_seconds": 120,
  "attempt_seconds": 600,
  "wall_seconds": 21600,
  "candidates": 1,
  "regenerate": 2,
  "agents_max": 12,
  "saturation": 0,
  "strategies": ["fresh", "feedback", "other_engine"],
  "syntax": true,
  "require_change": true,
  "checks": {"0": ["test -s verify.txt"]},
  "final": []
}
===== END policies/command.json =====

===== FILE: policies/compute.json =====
{
  "version": 1,
  "perpetual": true,
  "interval_seconds": 3600,
  "attempt_seconds": 3600,
  "wall_seconds": 43200,
  "candidates": 1,
  "regenerate": 2,
  "agents_max": 12,
  "saturation": 4,
  "strategies": ["fresh", "feedback", "other_engine"],
  "syntax": true,
  "require_change": true,
  "checks": {"0": ["test -s verify.txt"]},
  "final": []
}
===== END policies/compute.json =====

===== FILE: policies/database.json =====
{
  "version": 1,
  "perpetual": false,
  "until_done": false,
  "candidates": 1,
  "regenerate": 2,
  "depth": 1,
  "children": 4,
  "generations": 2,
  "agents_max": 12,
  "attempt_seconds": 3600,
  "wall_seconds": 21600,
  "strategies": ["fresh", "feedback", "other_engine"],
  "syntax": true,
  "require_change": true,
  "checks": {"4": ["test -s verify.txt"]},
  "final": ["bash organ-database/check_schema.sh"]
}
===== END policies/database.json =====

===== FILE: policies/digest.json =====
{
  "version": 1,
  "perpetual": true,
  "interval_seconds": 900,
  "attempt_seconds": 3600,
  "wall_seconds": 86400,
  "candidates": 1,
  "regenerate": 2,
  "agents_max": 24,
  "saturation": 3,
  "strategies": ["fresh", "feedback", "other_engine"],
  "syntax": true,
  "require_change": true,
  "checks": {"0": ["test -s verify.txt"]},
  "final": []
}
===== END policies/digest.json =====

===== FILE: policies/heartbeat.json =====
{
  "version": 1,
  "perpetual": true,
  "interval_seconds": 300,
  "attempt_seconds": 600,
  "wall_seconds": 86400,
  "candidates": 1,
  "regenerate": 1,
  "agents_max": 8,
  "saturation": 0,
  "strategies": ["fresh", "feedback"],
  "syntax": true,
  "require_change": true,
  "checks": {"0": ["test -s verify.txt"]},
  "final": []
}
===== END policies/heartbeat.json =====

===== FILE: policies/immune.json =====
{
  "version": 1,
  "perpetual": true,
  "interval_seconds": 1800,
  "attempt_seconds": 3600,
  "wall_seconds": 86400,
  "candidates": 1,
  "regenerate": 2,
  "agents_max": 16,
  "saturation": 6,
  "strategies": ["fresh", "feedback", "other_engine"],
  "syntax": true,
  "require_change": true,
  "checks": {"0": ["test -s verify.txt"]},
  "final": []
}
===== END policies/immune.json =====

===== FILE: policies/learning.json =====
{
  "version": 1,
  "perpetual": true,
  "interval_seconds": 1800,
  "attempt_seconds": 3600,
  "wall_seconds": 86400,
  "candidates": 1,
  "regenerate": 2,
  "agents_max": 24,
  "saturation": 3,
  "strategies": ["fresh", "feedback", "other_engine"],
  "syntax": true,
  "require_change": true,
  "checks": {"0": ["test -s verify.txt"]},
  "final": []
}
===== END policies/learning.json =====

===== FILE: policies/metabolism.json =====
{
  "version": 1,
  "perpetual": true,
  "interval_seconds": 300,
  "attempt_seconds": 600,
  "wall_seconds": 86400,
  "candidates": 1,
  "regenerate": 1,
  "agents_max": 8,
  "saturation": 0,
  "strategies": ["fresh", "feedback"],
  "syntax": true,
  "require_change": true,
  "checks": {"0": ["test -s verify.txt"]},
  "final": []
}
===== END policies/metabolism.json =====

===== FILE: policies/selfdev.json =====
{
  "version": 1,
  "perpetual": true,
  "interval_seconds": 3600,
  "attempt_seconds": 3600,
  "wall_seconds": 86400,
  "candidates": 1,
  "regenerate": 2,
  "agents_max": 12,
  "saturation": 4,
  "strategies": ["fresh", "feedback", "other_engine"],
  "syntax": true,
  "require_change": true,
  "checks": {"0": ["test -s verify.txt"]},
  "final": []
}
===== END policies/selfdev.json =====

===== FILE: genome/classify-command.sym =====
program LIFE command classifier.
use profile=verified, context=none, determine=false, solve=false.
note The command inbox cell gives one operator command to a light model, which routes it to exactly one organ and sets an urgency. Code reads the typed answer; the model only labels.
given command_id: Text.
given command_text: Text.
define Organ as one of {
  codebase: "optimise the dashboard code or fix an error or failing test",
  learning: "research something from the internet and record sources",
  database: "create or migrate a database table or column",
  compute: "propose or benchmark a new way to compute or store data",
  selfdev: "improve the organism's own scripts, policies or checks",
  immune: "review, audit, roll back or quarantine something",
  heartbeat: "report status, metrics or what is happening",
  none: "the command fits no organ and must be shown to the operator"}.
ask organ: Organ "Route this operator command to exactly one organ. Command: {command_text}" from command_text by "ollama:qwen3:4b-instruct@node-a" with effort=medium, votes=3, retries=2
ask urgency: one of {low, normal, high} "How urgent is this command for the cluster? Command: {command_text}" from command_text by "ollama:llama3.2:1b@node-b" with effort=low
ask one_line: Text up to 18 words "Restate the command as one short imperative line naming what to do." from command_text by "ollama:qwen3:4b-instruct@node-a" with effort=low
ensure len(one_line) >= 10 and len(one_line) <= 160 else retry because "the restated line is between ten and one hundred sixty characters".
let route = {command: command_id, organ: organ, urgency: urgency, restated: one_line}.
return route.
===== END genome/classify-command.sym =====

===== FILE: genome/extract-source.sym =====
program LIFE source fact extractor.
use profile=verified, context=none, determine=false, solve=false.
note The digest cell turns one fetched source into one checked fact. The kernel checks that the quote is copied verbatim from the source text; the claim and its usefulness are model judgements, not checks.
given source_id: Text.
given source_url: Text.
given source_text: Text.
ask claim: Text up to 40 words "State one specific factual claim this source supports, in your own words." from source_text by "ollama:qwen3:4b-instruct@node-d" with effort=medium, retries=2
ensure len(claim) >= 20 and len(claim) <= 300 else retry because "a claim is between twenty and three hundred characters".
ask quote: Text "Copy, word for word, the shortest span of the source that states the claim." from source_text, claim by "ollama:qwen3:4b-instruct@node-d" with effort=low, retries=3
ensure quotes(source_text, quote) else retry because "the quote must be copied exactly from the source text".
ensure len(quote) >= 12 else retry because "the quote is at least twelve characters".
let fact = {source: source_id, url: source_url, claim: claim, quote: quote}.
return fact.
===== END genome/extract-source.sym =====

===== FILE: genome/rank-experiment.sym =====
program LIFE experiment ranking.
use profile=verified, context=none, determine=false, solve=false.
note The compute cell scores one proposed compute-or-storage experiment before any benchmark runs. A low score means the orchestrator does not spend cluster time on it. The number is a model judgement, never a measurement.
given experiment_id: Text.
given hypothesis: Text.
given measurement: Text.
given threshold: Text.
ask feasible: Bool "Can this be measured on a laptop-class worker node node in under fifteen minutes with the given command? Hypothesis: {hypothesis} Measurement: {measurement}" from hypothesis, measurement by "ollama:qwen3:4b-instruct@node-i" with effort=medium, retries=2
ask novelty: one of {none, small, large} "How different is this from the obvious default approach? Hypothesis: {hypothesis}" from hypothesis by "ollama:granite3.3:2b@node-i" with effort=low
ask risk: one of {low, medium, high} "How likely is this experiment to overheat or overload a node? Measurement: {measurement}" from measurement by "ollama:llama3.2:1b@node-i" with effort=low
ask score: Int in 0..100 "Give a single integer priority from zero to one hundred for running this experiment. Hypothesis: {hypothesis} Threshold: {threshold}" from hypothesis, threshold, feasible, novelty, risk by "ollama:qwen3:4b-instruct@node-i" with effort=medium, votes=3, vote=median
ensure score = 0 or feasible else retry because "an experiment that is not feasible scores zero".
ensure score <= 40 or risk != "high" else retry because "a high-risk experiment cannot score above forty".
let ranking = {experiment: experiment_id, feasible: feasible, novelty: novelty, risk: risk, score: score}.
return ranking.
===== END genome/rank-experiment.sym =====

===== FILE: genome/reproduce.sym =====
program LIFE reproducer decision.
use profile=verified, context=none, determine=false, solve=false.
note The reproducer never does the cell's task. It reads the cell's own metrics and decides whether the cell divides, keeps working, or ends. Code (the orchestrator) acts on this; the model only proposes.
given cell_id: Text.
given organ: Text.
given generation: Int in 0..100000 = 0.
given failures_in_a_row: Int in 0..100000 = 0.
given new_items_last_generation: Int in 0..1000000 = 0.
given lineage_depth: Int in 0..64 = 0.
given summary: Text.
define Verdict as one of {
  stay: "the cell keeps its current single task and does not divide this generation",
  divide: "the cell splits its remaining work into exactly two child foci that each do less",
  apoptosis: "the cell stops and is retired because it cannot make progress or is no longer needed"}.
ask verdict: Verdict "Decide the fate of cell {cell_id} in organ {organ}. Generation {generation}, {failures_in_a_row} failures in a row, {new_items_last_generation} new results last generation, lineage depth {lineage_depth}. Summary: {summary}" from summary by "ollama:qwen3:4b-instruct@node-a" with effort=low, retries=2
ensure verdict != "divide" or failures_in_a_row = 0 else retry because "a cell that is currently failing must not divide".
ensure verdict != "divide" or lineage_depth < 10 else retry because "a cell at lineage depth ten or more must not divide".
ensure verdict != "stay" or failures_in_a_row < 8 else retry because "a cell failing eight generations in a row cannot simply stay".
ask child_a: Text up to 14 words "If cell {cell_id} divides, name the first child's single specific focus in one short imperative clause." from summary, verdict by "ollama:llama3.2:1b@node-b" with effort=low
ensure len(child_a) >= 8 and len(child_a) <= 120 else retry because "a child focus is a short clause between eight and one hundred twenty characters".
ask child_b: Text up to 14 words "If cell {cell_id} divides, name the second child's single specific focus, different from the first, in one short imperative clause." from summary, verdict, child_a by "ollama:llama3.2:1b@node-b" with effort=low
ensure len(child_b) >= 8 and len(child_b) <= 120 else retry because "a child focus is a short clause between eight and one hundred twenty characters".
ensure child_a != child_b else retry because "the two children must have different foci".
let plan = {cell: cell_id, organ: organ, verdict: verdict, generation: generation, child_a: child_a, child_b: child_b}.
return plan.
===== END genome/reproduce.sym =====

===== FILE: genome/review-patch.sym =====
program LIFE patch review.
use profile=verified, context=none, determine=false, solve=false.
note The immune cell is the second agent of a codebase cell. It reviews a patch summary adversarially and returns a verdict. Code requires both this accept and the passing checks before Work to Apply; a model accept alone never promotes anything.
given patch_id: Text.
given change_class: Text.
given diff_summary: Text.
given checks_passed: Bool = false.
define Verdict as one of {
  accept: "the change is safe, in scope and matches its stated class",
  reject: "the change is unsafe, out of scope, or does not match its stated class",
  needs_work: "the change is close but a named fix is required before it is safe"}.
ask verdict: Verdict "Review this patch adversarially. Stated class: {change_class}. Summary of the diff: {diff_summary}" from change_class, diff_summary by "ollama:qwen2.5-coder:3b@node-f" with effort=medium, votes=3, retries=2
ask reason: Text up to 30 words "State the single most important reason for your verdict." from diff_summary, verdict by "ollama:qwen3:4b-instruct@node-f" with effort=low
ensure len(reason) >= 10 and len(reason) <= 240 else retry because "the reason is between ten and two hundred forty characters".
ensure verdict != "accept" or checks_passed else retry because "a patch whose automated checks did not pass cannot be accepted".
let review = {patch: patch_id, verdict: verdict, checks_passed: checks_passed, reason: reason}.
return review.
===== END genome/review-patch.sym =====

===== FILE: genome/triage-error.sym =====
program LIFE error triage.
use profile=verified, context=none, determine=false, solve=false.
note The codebase cell gives one failing check or traceback line to a light coder model, which classifies the change class. Promotion is allowed only for the classes the master script permits; code enforces that, not the model.
given finding_id: Text.
given finding_text: Text.
define ChangeClass as one of {
  test_only: "a change confined to files under a tests directory",
  comment_or_doc: "a change only to comments, docstrings or markdown",
  local_fix: "a bounded fix inside one function body with no signature change",
  signature_change: "a change to a function or class signature or public interface",
  restart_gated: "a change to server python or an api handler that needs a dashboard restart",
  unknown: "the finding cannot be classified from this text alone"}.
ask change_class: ChangeClass "Classify the smallest change that would resolve this finding. Finding: {finding_text}" from finding_text by "ollama:qwen2.5-coder:3b@node-a" with effort=medium, votes=3, retries=2
ask confident: Bool "Is this classification well supported by the finding text alone?" from finding_text, change_class by "ollama:llama3.2:1b@node-b" with effort=low
let triage = {finding: finding_id, change_class: change_class, confident: confident}.
return triage.
===== END genome/triage-error.sym =====

===== FILE: checks/devcheck-gate.sh =====
#!/usr/bin/env bash
# LIFE codebase gate: the codebase organ worker runs this inside its OWN checkout before it
# writes a patch as accepted. It runs the repo's own bin/devcheck plus one focused test file the
# worker names. It never restarts anything and never pushes. Exit 0 only when both pass.
# Calls no model and no agent (bin/devcheck itself runs linters/tests, not models).
set -eu
checkout="${1:?usage: devcheck-gate.sh CHECKOUT_DIR FOCUSED_TEST}"
focused="${2:?name one focused test, e.g. tests/test_security_gate.py}"
cd "$checkout"
./bin/devcheck
.venv/bin/python -m unittest "$focused" -v 2>/dev/null || python3 -m unittest "$focused" -v
echo "devcheck-gate: PASS for $focused"
===== END checks/devcheck-gate.sh =====

===== FILE: checks/heat-gate.sh =====
#!/usr/bin/env bash
# LIFE metabolism heat gate (code side). Reads the host load and IO pressure locally and prints
# ALLOW or HOLD for cluster fan-out. Thresholds from docs/fleet-power.md and the operator heat rule.
# ALLOW (exit 0): 1-minute load average < 4.0 AND io pressure full avg10 < 40.0.
# HOLD  (exit 4): otherwise. Calls no model, no agent, no network.
set -eu
load1="$(awk '{print $1}' /proc/loadavg)"
io="$(awk -F'=' '/full/{split($0,a," "); for(i in a) if(a[i] ~ /avg10/){split(a[i],b,"="); print b[2]}}' /proc/pressure/io 2>/dev/null || echo 0)"
awk -v l="$load1" -v p="${io:-0}" 'BEGIN{
  if (l+0 < 4.0 && p+0 < 40.0) { printf "ALLOW load=%s io_full_avg10=%s\n", l, p; exit 0 }
  printf "HOLD load=%s io_full_avg10=%s\n", l, p; exit 4
}'
===== END checks/heat-gate.sh =====

===== FILE: checks/kill-switch.sh =====
#!/usr/bin/env bash
# LIFE kill switch probe. Prints STOP and exits 3 when the stop file exists, else prints GO
# and exits 0. The orchestrator (bin/life-spawn-tick) runs this before every spawn; the operator
# creates the stop file to freeze reproduction. Lanes already running finish their generation.
# Calls no model, no agent, no network.
set -eu
root="${1:-/home/operator/symblicos/projects/life}"
if [ -e "$root/STOP" ]; then
  echo "STOP ($root/STOP present): no new spawns, lanes finish and rest"
  exit 3
fi
echo "GO ($root/STOP absent)"
exit 0
===== END checks/kill-switch.sh =====

===== FILE: checks/verify-format.sh =====
#!/usr/bin/env bash
# LIFE check: a verify.txt exists in the current working folder and is non-empty.
# Used as the autogen check for perpetual organ lanes (policy checks index "0").
# Exit 0 pass, 1 fail. Calls no model, no agent, no network.
set -eu
f="${1:-verify.txt}"
if [ -s "$f" ]; then
  echo "verify-format: $f present, $(wc -c <"$f") bytes"
  exit 0
fi
echo "verify-format: $f missing or empty" >&2
exit 1
===== END checks/verify-format.sh =====

===== FILE: spawn/PROTOCOL.md =====
# LIFE spawn protocol (reproduction, admitted by code)

A cell divides only by writing a **spawn record** into `spawn/queue/<name>/`. A reproducer cell
(the second agent of a subtask, running `genome/reproduce.sym` on a lightweight model) proposes
the division; the **orchestrator** `bin/life-spawn-tick.py` (code on the host, run by the operator's
timer, calling no model) is the only thing that admits it and starts the new autogen run. Models
propose; code decides.

## Record layout (exact)

```
spawn/queue/<name>/
  statements.txt   one or more statement lines for the child lane (the child's genome)
  policy.json      the child's autogen policy (a superset of a normalize()-valid object)
  lineage.json     who the child is and where it runs
  reason.txt       prose: why this division (not read by the orchestrator; for the operator/immune)
```

`<name>` is any `^[a-z0-9][a-z0-9_-]{0,63}$` slug (the orchestrator timestamps it on admission).

### statements.txt
- Each nonblank line is one statement. Must pass `symblic_autogen.lint(lines, ROOT)` with
  **zero errors and zero warnings**: 20-1500 chars, first word in `VERBS`, an absolute
  `/home/operator/symblicos/projects/life/...` folder named on every line, no pronoun start,
  `keeping every existing part` on any edit verb, no reference to earlier lines, and the file
  as a whole has a verify line (a line containing both `verif` and a `.txt` name).
- At most 64 lines (`MAX_LINES`), 60000 chars total (`MAX_CHARS`).

### policy.json
- Must pass `symblic_autogen.normalize`. Perpetual lanes: `perpetual true`, `candidates 1`,
  `depth 0`, an `interval_seconds` and a `wall_seconds` cap (the heat rule; never 0/unlimited for
  a child), `strategies` drawn from `fresh,feedback,other_engine` (never `other_node`: that can
  place a child on the host or the ARM node).

### lineage.json (exact keys)
```json
{
  "cell_id": "<organ>.<generation>.<8hex>",   // e.g. learning.3.a1b2c3d4
  "organ": "<one of the ten organ names>",
  "parent_id": "<parent cell_id or null for a seed>",
  "depth": <int 0..64>,                         // parent depth + 1
  "focus": "<8..120 char clause from reproduce.sym>",
  "spawn_reason": "divide|seed|replan",
  "node": "node-a|node-b|node-d|node-f|node-h|node-i",  // never the host/node-arm for a model lane
  "engine": "agy"                               // CLI engine for the lane's attempts
}
```

## Admission gates (bin/life-spawn-tick.py, in order)

1. **kill switch** - `spawn/../STOP` (that is `/home/operator/symblicos/projects/life/STOP`) absent,
   else the tick exits 3 and nothing is born.
2. **heat gate** - `checks/heat-gate.sh` returns ALLOW (the host load < 4.0 and io full avg10 < 40.0),
   else exit 4.
3. **budget** - fewer than `LIFE_MAX_RUNS` (default 16) live `life-*` autogen runs; else the
   record stays queued.
4. **lint** - `statements.txt` has zero lint errors and zero warnings.
5. **normalize** - `policy.json` passes `symblic_autogen.normalize`.
6. **lineage depth** - `depth < LIFE_MAX_DEPTH` (default 10) and `<= 64`; `cell_id` matches
   `organ.generation.8hex`.
7. **content dedup** - `sha256(statements || "\n" || policy)` is not already in `spawn/hashes.txt`.
   (A reproducer that re-proposes identical work is a no-op; this is the self-replication brake.)

A record that fails any gate is moved to `spawn/rejected/<name>-<epoch>/` with a `REJECT.txt`
reason. A record that passes is submitted with `bin/symblic-task start --lines statements.txt
--root ROOT --cwd ROOT --node <node> --engine <engine> --id life-<organ>-<8hex>` plus the flags
`policy_flags()` derives from `policy.json`, its hash is appended to `spawn/hashes.txt`, and the
record moves to `spawn/approved/<name>-<epoch>/` with a `RUN.txt` naming the run.

## Apoptosis

A reproducer verdict of `apoptosis` writes **no** queue record; instead it appends the cell_id to
`spawn/retired.txt`. The operator (or the immune organ) cancels the run with
`bin/symblic-task autogen cancel <run_id>` and sets `retired_at` in the `lineage` table. A lane
that a reproducer retires is never re-spawned (its content hash stays in `hashes.txt`).
===== END spawn/PROTOCOL.md =====

===== FILE: spawn/example/lineage.json =====
{
  "cell_id": "learning.3.a1b2c3d4",
  "organ": "learning",
  "parent_id": "learning.2.00000000",
  "depth": 3,
  "focus": "research porous ceramic porosity sources",
  "spawn_reason": "divide",
  "node": "node-d",
  "engine": "agy"
}
===== END spawn/example/lineage.json =====

===== FILE: spawn/example/policy.json =====
{
  "version": 1,
  "perpetual": true,
  "interval_seconds": 1800,
  "attempt_seconds": 3600,
  "wall_seconds": 86400,
  "candidates": 1,
  "regenerate": 2,
  "agents_max": 24,
  "saturation": 3,
  "strategies": ["fresh", "feedback", "other_engine"],
  "syntax": true,
  "require_change": true,
  "checks": {"0": ["test -s verify.txt"]},
  "final": []
}
===== END spawn/example/policy.json =====

===== FILE: spawn/example/reason.txt =====
Parent learning.2.00000000 reached saturation on its broad question set but its reproducer
(genome/reproduce.sym on qwen3:4b-instruct@node-a) returned verdict=divide because new sources
kept arriving for the porosity sub-topic while the rest of the queue went stale. Child A (this
record) takes the porosity sub-topic on its own node and index; child B keeps the remainder.
This record was written by the reproducer cell; the orchestrator (bin/life-spawn-tick.py) admits
it only after lint + normalize + budget + depth + content-hash dedup all pass.
===== END spawn/example/reason.txt =====

===== FILE: spawn/example/statements.txt =====
Research the question in the file /home/operator/symblicos/projects/life/organ-learning/questions.txt about porous ceramic porosity, find three sources with a DOI or URL not already in the index, append one JSON line per source to the file /home/operator/symblicos/projects/life/organ-learning-c1/sources.jsonl, and verify this batch by writing the three new source keys to the file verify.txt.
===== END spawn/example/statements.txt =====

===== FILE: db/schema.sql =====
-- LIFE v1 organism database schema.
-- One SQLite file: /home/operator/symblicos/projects/life/db/life.sqlite3
-- Every table uses CREATE TABLE IF NOT EXISTS so re-applying is a no-op and never drops rows.
-- Times are integer Unix seconds (strftime('%s')). Ids are text. No credentials or private
-- store values are ever written here; only organism metadata, provenance and public sources.

-- knowledge: one checked fact per row, produced by the digest organ from a fetched source.
CREATE TABLE IF NOT EXISTS knowledge (
  id           TEXT PRIMARY KEY,        -- items_key form: doi:/url:/text: (<=200 chars)
  claim        TEXT NOT NULL,           -- model wording of the fact, 20..300 chars
  quote        TEXT NOT NULL,           -- span copied verbatim from the source (kernel-checked)
  source_id    TEXT NOT NULL,           -- id of the source row in sources.jsonl
  source_url   TEXT NOT NULL,           -- http(s) url or DOI the quote came from
  organ        TEXT NOT NULL DEFAULT 'digest',
  created_at   INTEGER NOT NULL,
  verified     INTEGER NOT NULL DEFAULT 0  -- 1 only when quotes() passed at extraction time
);
CREATE INDEX IF NOT EXISTS knowledge_source ON knowledge (source_id);

-- lineage: the family tree of cells. Each spawn writes one row. Append-only.
CREATE TABLE IF NOT EXISTS lineage (
  cell_id      TEXT PRIMARY KEY,        -- organ '.' generation '.' 8hex  e.g. learning.3.a1b2c3d4
  organ        TEXT NOT NULL,
  parent_id    TEXT,                    -- NULL for a seed cell
  depth        INTEGER NOT NULL DEFAULT 0,  -- 0..64, parent depth + 1
  focus        TEXT NOT NULL,           -- the child's single specific focus (8..120 chars)
  spawn_reason TEXT NOT NULL,           -- divide | seed | replan
  content_hash TEXT NOT NULL,           -- sha256 of (statements_file || policy_json) for dedup
  run_id       TEXT,                    -- the autogen run id once the orchestrator submits it
  created_at   INTEGER NOT NULL,
  retired_at   INTEGER                  -- set on apoptosis / quarantine
);
CREATE INDEX IF NOT EXISTS lineage_parent ON lineage (parent_id);
CREATE UNIQUE INDEX IF NOT EXISTS lineage_hash ON lineage (content_hash);

-- metrics: one row per organ generation, written by heartbeat from the run records.
CREATE TABLE IF NOT EXISTS metrics (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  organ        TEXT NOT NULL,
  run_id       TEXT NOT NULL,
  generation   INTEGER NOT NULL DEFAULT 0,
  new_items    INTEGER NOT NULL DEFAULT 0,  -- new index keys this generation
  failures     INTEGER NOT NULL DEFAULT 0,  -- trailing failed generations
  node         TEXT,                        -- node the generation ran on
  at           INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS metrics_organ ON metrics (organ, at);

-- commands: operator commands taken by the command inbox, with their route.
CREATE TABLE IF NOT EXISTS commands (
  id           TEXT PRIMARY KEY,        -- sha256[:16] of the command text + arrival time
  text         TEXT NOT NULL,
  organ        TEXT NOT NULL,           -- routed organ, or 'none'
  urgency      TEXT NOT NULL DEFAULT 'normal',  -- low | normal | high
  restated     TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT 'routed',  -- routed | accepted | done | rejected
  created_at   INTEGER NOT NULL
);

-- experiments: compute/storage R&D proposals and their measured results.
CREATE TABLE IF NOT EXISTS experiments (
  id           TEXT PRIMARY KEY,
  hypothesis   TEXT NOT NULL,
  measurement  TEXT NOT NULL,           -- the exact shell command that produces a number
  threshold    TEXT NOT NULL,           -- the comparison that counts as success, e.g. '< 1.0'
  score        INTEGER NOT NULL DEFAULT 0,   -- 0..100 ranking from rank-experiment.sym
  node         TEXT,                    -- node the benchmark ran on
  measured     TEXT,                    -- the number produced, as text; NULL until run
  passed       INTEGER,                 -- 1 pass, 0 fail, NULL not run
  created_at   INTEGER NOT NULL,
  ran_at       INTEGER
);
CREATE INDEX IF NOT EXISTS experiments_score ON experiments (score DESC);
===== END db/schema.sql =====

===== FILE: bin/life-spawn-tick.py =====
#!/usr/bin/env python3
"""LIFE orchestrator tick: the only place a new cell (autogen run) is born.

Reproduction is admitted by CODE, never by a model. A reproducer cell proposes a division by
writing a SPAWN record folder under spawn/queue/ (see spawn/PROTOCOL.md). This tick, run by the
operator's systemd user timer on the host, validates each queued record and submits the valid ones.
It calls no model and starts no agent itself: it runs `bin/symblic-task lint`, `normalize` and
`bin/symblic-task start` (which submits an autogen run) only after every gate passes.

Gates, in order, per record:
  1. kill switch     -- spawn/../STOP absent (else the whole tick exits 3, nothing is born)
  2. heat gate       -- the host load/io under the fan-out thresholds (else exit 4)
  3. budget          -- fewer than LIFE_MAX_RUNS live LIFE autogen runs
  4. lint            -- statements.txt: zero errors AND zero warnings
  5. normalize       -- policy.json passes symblic_autogen.normalize
  6. lineage depth   -- depth < LIFE_MAX_DEPTH (10) and <= 64
  7. content dedup   -- sha256(statements||policy) not already in spawn/hashes.txt
A record that fails any gate is moved to spawn/rejected/ with a reason; a record that passes is
moved to spawn/approved/, its hash recorded, and submitted with `bin/symblic-task start`.
Nothing here restarts the dashboard, pushes, or touches files outside the organism workspace.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

ROOT = os.environ.get('LIFE_ROOT', '/home/operator/symblicos/projects/life')
REPO = os.environ.get('LIFE_REPO', '/home/operator/host-checkout')
KIT = os.path.join(REPO, 'docs/life')
TASK = os.path.join(REPO, 'bin/symblic-task')
LIFE_MAX_RUNS = int(os.environ.get('LIFE_MAX_RUNS', '16'))
LIFE_MAX_DEPTH = int(os.environ.get('LIFE_MAX_DEPTH', '10'))
DASH_URL = os.environ.get('DASH_URL', 'http://127.0.0.1:8080')

sys.path.insert(0, REPO)
import symblic_autogen as A  # noqa: E402

QUEUE = os.path.join(KIT, 'spawn', 'queue')
APPROVED = os.path.join(KIT, 'spawn', 'approved')
REJECTED = os.path.join(KIT, 'spawn', 'rejected')
HASHES = os.path.join(KIT, 'spawn', 'hashes.txt')


def log(msg):
    print(f'{time.strftime("%Y-%m-%d %H:%M:%S")} life-spawn-tick: {msg}')


def policy_flags(spec):
    """Translate a normalized-passing policy dict into exact bin/symblic-task start flags.
    Only keys present in the record are emitted, so server defaults fill the rest."""
    intmap = {'candidates': '--candidates', 'regenerate': '--regenerate', 'depth': '--decompose',
              'children': '--children', 'generations': '--handoff', 'agents_max': '--agents-max',
              'attempt_seconds': '--attempt-seconds', 'wall_seconds': '--wall-seconds',
              'novelty_limit': '--novelty-limit', 'saturation': '--saturation'}
    flags = []
    for key, flag in intmap.items():
        if key in spec and isinstance(spec[key], int) and not isinstance(spec[key], bool):
            flags += [flag, str(spec[key])]
    if spec.get('perpetual'):
        flags += ['--perpetual', str(int(spec.get('interval_seconds', 900)))]
    if spec.get('strategies'):
        flags += ['--strategies', ','.join(spec['strategies'])]
    if spec.get('syntax') is False:
        flags += ['--no-syntax']
    if spec.get('require_change') is False:
        flags += ['--allow-no-change']
    if spec.get('until_done'):
        flags += ['--until-done']
    if spec.get('designer'):
        flags += ['--designer']
    if spec.get('self_split') is False:
        flags += ['--no-self-split']
    for idx, cmds in (spec.get('checks') or {}).items():
        for c in cmds:
            flags += ['--check', f'{idx}:{c}']
    for c in spec.get('final') or []:
        flags += ['--final', c]
    for c in spec.get('hidden') or []:
        flags += ['--hidden', c]
    return flags


def known_hashes():
    try:
        return set(open(HASHES, encoding='utf-8').read().split())
    except OSError:
        return set()


def live_run_count():
    try:
        out = subprocess.run([TASK, 'autogen', 'list'], capture_output=True, text=True, timeout=60)
        return sum(1 for ln in out.stdout.splitlines() if 'life-' in ln and ('active' in ln or 'queued' in ln))
    except (OSError, subprocess.SubprocessError):
        return LIFE_MAX_RUNS  # fail closed: do not spawn when we cannot read the count


def reject(folder, reason):
    os.makedirs(REJECTED, exist_ok=True)
    with open(os.path.join(folder, 'REJECT.txt'), 'w', encoding='utf-8') as fh:
        fh.write(reason + '\n')
    shutil.move(folder, os.path.join(REJECTED, os.path.basename(folder) + f'-{int(time.time())}'))
    log(f'rejected {os.path.basename(folder)}: {reason}')


def main():
    # gate 1: kill switch
    if os.path.exists(os.path.join(ROOT, 'STOP')):
        log('STOP present: no spawns'); return 3
    # gate 2: heat
    heat = subprocess.run([os.path.join(KIT, 'checks', 'heat-gate.sh')], capture_output=True, text=True)
    if heat.returncode != 0:
        log(f'heat HOLD: {heat.stdout.strip()}'); return 4
    if not os.path.isdir(QUEUE):
        log('no queue folder, nothing to do'); return 0
    hashes = known_hashes()
    for name in sorted(os.listdir(QUEUE)):
        folder = os.path.join(QUEUE, name)
        if not os.path.isdir(folder):
            continue
        sfile = os.path.join(folder, 'statements.txt')
        pfile = os.path.join(folder, 'policy.json')
        lfile = os.path.join(folder, 'lineage.json')
        if not (os.path.isfile(sfile) and os.path.isfile(pfile) and os.path.isfile(lfile)):
            reject(folder, 'incomplete record: need statements.txt, policy.json, lineage.json'); continue
        # gate 3: budget
        if live_run_count() >= LIFE_MAX_RUNS:
            log(f'budget reached ({LIFE_MAX_RUNS} live runs): leaving {name} queued'); continue
        # gate 4: lint (errors AND warnings must be zero)
        lines = A.statements(open(sfile, encoding='utf-8').read())
        findings = A.lint(lines, ROOT)
        if findings:
            reject(folder, 'lint: ' + '; '.join(f'{lv} line {n}: {m}' for lv, n, m in findings)[:400]); continue
        # gate 5: normalize
        try:
            spec = json.load(open(pfile, encoding='utf-8'))
            A.normalize(spec)
        except (ValueError, OSError) as exc:
            reject(folder, f'policy refused: {exc}'); continue
        # gate 6: lineage depth
        try:
            lin = json.load(open(lfile, encoding='utf-8'))
            depth = int(lin['depth']); cell_id = str(lin['cell_id']); organ = str(lin['organ'])
        except (ValueError, OSError, KeyError) as exc:
            reject(folder, f'lineage invalid: {exc}'); continue
        if depth >= LIFE_MAX_DEPTH or depth > 64:
            reject(folder, f'lineage depth {depth} at or above limit {LIFE_MAX_DEPTH}'); continue
        if not re.fullmatch(r'[a-z]+\.[0-9]+\.[0-9a-f]{8}', cell_id):
            reject(folder, f'cell_id {cell_id!r} not organ.generation.8hex'); continue
        # gate 7: content-hash dedup
        content = open(sfile, encoding='utf-8').read() + '\n' + open(pfile, encoding='utf-8').read()
        chash = hashlib.sha256(content.encode()).hexdigest()
        if chash in hashes:
            reject(folder, f'duplicate content hash {chash[:16]}'); continue
        # all gates passed: birth the cell
        run_id = f'life-{organ}-{cell_id.split(".")[-1]}'
        cmd = [TASK, 'start', '--lines', sfile, '--root', ROOT, '--cwd', ROOT,
               '--node', str(lin.get('node', 'node-i')), '--engine', str(lin.get('engine', 'agy')),
               '--id', run_id[:120]] + policy_flags(spec)
        log(f'SUBMIT {run_id} node={lin.get("node", "node-i")} depth={depth}')
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            reject(folder, f'start failed rc={res.returncode}: {res.stderr.strip()[:300]}'); continue
        with open(HASHES, 'a', encoding='utf-8') as fh:
            fh.write(chash + '\n')
        hashes.add(chash)
        os.makedirs(APPROVED, exist_ok=True)
        with open(os.path.join(folder, 'RUN.txt'), 'w', encoding='utf-8') as fh:
            fh.write(f'{run_id}\n{res.stdout.strip()}\n')
        shutil.move(folder, os.path.join(APPROVED, name + f'-{int(time.time())}'))
        log(f'born {run_id}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
===== END bin/life-spawn-tick.py =====

===== FILE: bin/life-status.py =====
#!/usr/bin/env python3
"""LIFE heartbeat (code side): print one status line per LIFE autogen run. No model, no agent.
Reads `bin/symblic-task autogen list` and the per-organ verify.txt / ledger files. Read-only."""
import os
import subprocess
import sys
import time

ROOT = os.environ.get('LIFE_ROOT', '/home/operator/symblicos/projects/life')
REPO = os.environ.get('LIFE_REPO', '/home/operator/host-checkout')
TASK = os.path.join(REPO, 'bin/symblic-task')
ORGANS = ('command', 'codebase', 'learning', 'digest', 'selfdev', 'compute',
          'metabolism', 'immune', 'heartbeat', 'database')


def main():
    print(f'LIFE status {time.strftime("%Y-%m-%d %H:%M:%S")}  root={ROOT}')
    stop = os.path.join(ROOT, 'STOP')
    print(f'  kill switch: {"STOP present (frozen)" if os.path.exists(stop) else "GO"}')
    try:
        out = subprocess.run([TASK, 'autogen', 'list'], capture_output=True, text=True, timeout=60)
        for ln in out.stdout.splitlines():
            if 'life-' in ln:
                print('  run:', ln.strip())
    except (OSError, subprocess.SubprocessError) as exc:
        print('  (could not list runs:', exc, ')')
    for organ in ORGANS:
        d = os.path.join(ROOT, f'organ-{organ}')
        v = os.path.join(d, 'verify.txt')
        mark = 'verify.txt: ' + (open(v, encoding="utf-8").read().strip()[:80] if os.path.isfile(v) else 'none')
        print(f'  organ {organ:11s} {"dir" if os.path.isdir(d) else "no-dir":6s} {mark}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
===== END bin/life-status.py =====

===== FILE: bin/life-seed.sh =====
#!/usr/bin/env bash
# LIFE seed launcher. The operator runs this ONCE to create the organism workspace and start the ten
# seed organ runs. It is NOT run during authoring. Every command is bin/symblic-task (no model is
# called by a start; the organism's own lanes call CLI agents and, through them, light models).
# Read README.md first. This script warns and waits before it starts anything.
set -euo pipefail

REPO="${LIFE_REPO:-/home/operator/host-checkout}"
KIT="$REPO/docs/life"
ROOT="${LIFE_ROOT:-/home/operator/symblicos/projects/life}"
TASK="$REPO/bin/symblic-task"
export DASH_URL="${DASH_URL:-http://127.0.0.1:8080}"

echo "This will create workspace $ROOT and start 10 autogen runs on the worker node cluster."
echo "the host only orchestrates; models run on the worker nodes. Ctrl-C now to abort."
read -r -p "Type START to continue: " ans
[ "$ans" = "START" ] || { echo "aborted"; exit 1; }

# 1. the organism workspace (git-backed; idempotent)
"$TASK" workspace life

# 2. per-organ working folders (empty; lanes fill them)
for o in command codebase learning digest selfdev compute metabolism immune heartbeat database; do
  mkdir -p "$ROOT/organ-$o"
done
mkdir -p "$ROOT/organ-command/inbox" "$ROOT/organ-codebase/findings" \
         "$ROOT/organ-codebase/patches" "$ROOT/organ-immune" \
         "$KIT/spawn/queue" "$KIT/spawn/approved" "$KIT/spawn/rejected"
: > "$ROOT/organ-learning/questions.txt"
: > "$ROOT/organ-immune/canaries.txt"

# 3. copy the schema into the workspace so the database organ can apply it
mkdir -p "$ROOT/db"; cp -n "$KIT/db/schema.sql" "$ROOT/db/schema.sql"

# 4. start each organ as its OWN perpetual run, node and policy per the kit.
#    node classes: light=node-a/node-b, mid=node-d/node-f, heavy=node-i; the host for i/o lanes.
start() { # organ node extra-flags...
  local organ="$1" node="$2"; shift 2
  "$TASK" start --lines "$KIT/organs/$organ.lines.txt" --root "$ROOT" --cwd "$ROOT" \
    --node "$node" --engine agy --id "life-$organ" "$@"
}

# perpetual organs (flags mirror policies/<organ>.json; keep the two in sync)
start command    node-f --perpetual 120  --attempt-seconds 600  --wall-seconds 21600 --regenerate 2 --agents-max 12 --strategies fresh,feedback,other_engine --check '0:test -s verify.txt'
start codebase   node-i --perpetual 1800 --attempt-seconds 3600 --wall-seconds 43200 --regenerate 3 --agents-max 16 --saturation 4 --strategies fresh,feedback,other_engine --check '0:test -s verify.txt'
start learning   node-d --perpetual 1800 --attempt-seconds 3600 --wall-seconds 86400 --regenerate 2 --agents-max 24 --saturation 3 --strategies fresh,feedback,other_engine --check '0:test -s verify.txt'
start digest     node-f --perpetual 900  --attempt-seconds 3600 --wall-seconds 86400 --regenerate 2 --agents-max 24 --saturation 3 --strategies fresh,feedback,other_engine --check '0:test -s verify.txt'
start selfdev    node-i --perpetual 3600 --attempt-seconds 3600 --wall-seconds 86400 --regenerate 2 --agents-max 12 --saturation 4 --strategies fresh,feedback,other_engine --check '0:test -s verify.txt'
start compute    node-i --perpetual 3600 --attempt-seconds 3600 --wall-seconds 43200 --regenerate 2 --agents-max 12 --saturation 4 --strategies fresh,feedback,other_engine --check '0:test -s verify.txt'
start metabolism the host --perpetual 300 --attempt-seconds 600  --wall-seconds 86400 --regenerate 1 --agents-max 8  --strategies fresh,feedback --check '0:test -s verify.txt'
start immune     node-i --perpetual 1800 --attempt-seconds 3600 --wall-seconds 86400 --regenerate 2 --agents-max 16 --saturation 6 --strategies fresh,feedback,other_engine --check '0:test -s verify.txt'
start heartbeat  the host --perpetual 300 --attempt-seconds 600  --wall-seconds 86400 --regenerate 1 --agents-max 8  --strategies fresh,feedback --check '0:test -s verify.txt'

# bounded database build (not perpetual): runs once to create life.sqlite3 and migrations
start database   node-a --decompose 1 --children 4 --handoff 2 --regenerate 2 --agents-max 12 \
  --attempt-seconds 3600 --wall-seconds 21600 --strategies fresh,feedback,other_engine \
  --check '4:test -s verify.txt' --final 'bash organ-database/check_schema.sh'

echo "Seeded. Watch with: $REPO/docs/life/bin/life-status.py"
echo "Reproduction stays off until you install the spawn timer (see README)."
===== END bin/life-seed.sh =====

===== FILE: VALIDATE.sh =====
#!/usr/bin/env bash
# LIFE kit validator. Runs ONLY no-model, no-agent, no-network checks and prints PASS/FAIL per
# file. It never starts a task, never calls a model, never touches anything outside this kit.
#   - organ lines files : symblic_autogen.lint, zero errors AND zero warnings
#   - policy JSON        : symblic_autogen.normalize
#   - genome .sym        : bin/symblic check (no model)
#   - shell scripts      : bash -n
#   - python scripts     : python3 -m py_compile
#   - db/schema.sql      : applied twice in an in-memory sqlite (idempotent); skipped if no sqlite
# Exit 0 only when every file passes.
set -u
KIT="$(cd "$(dirname "$0")" && pwd)"
REPO="${LIFE_REPO:-/home/operator/host-checkout}"
SYMBLIC="$REPO/bin/symblic"
PY="python3"
fail=0
pass() { printf 'PASS  %-10s %s\n' "$1" "$2"; }
bad()  { printf 'FAIL  %-10s %s\n' "$1" "$2"; fail=1; }

echo "== organ lines (lint: zero errors, zero warnings) =="
for f in "$KIT"/organs/*.lines.txt; do
  out="$("$PY" - "$f" <<'PYEOF'
import sys
sys.path.insert(0, __import__('os').environ.get('LIFE_REPO','/home/operator/host-checkout'))
import symblic_autogen as A
lines = A.statements(open(sys.argv[1], encoding='utf-8').read())
f = A.lint(lines, '/home/operator/symblicos/projects/life')
n = len(f)
print(n)
for lv, ln, m in f:
    print(f'{lv} line {ln}: {m}')
PYEOF
)"
  n="$(printf '%s\n' "$out" | head -1)"
  if [ "$n" = "0" ]; then pass lint "$(basename "$f")"; else bad lint "$(basename "$f"): $(printf '%s' "$out" | tail -n +2 | tr '\n' ';')"; fi
done

echo "== policy JSON (normalize) =="
for f in "$KIT"/policies/*.json; do
  if "$PY" - "$f" <<'PYEOF'
import sys
sys.path.insert(0, __import__('os').environ.get('LIFE_REPO','/home/operator/host-checkout'))
import json, symblic_autogen as A
A.normalize(json.load(open(sys.argv[1], encoding='utf-8')))
PYEOF
  then pass normalize "$(basename "$f")"; else bad normalize "$(basename "$f")"; fi
done

echo "== spawn example (lint + normalize + lineage) =="
"$PY" - "$KIT/spawn/example/statements.txt" <<'PYEOF' && pass lint "spawn/example/statements.txt" || bad lint "spawn/example/statements.txt"
import sys
sys.path.insert(0, __import__('os').environ.get('LIFE_REPO','/home/operator/host-checkout'))
import symblic_autogen as A
lines=A.statements(open(sys.argv[1],encoding='utf-8').read())
sys.exit(1 if A.lint(lines,'/home/operator/symblicos/projects/life') else 0)
PYEOF
"$PY" - "$KIT/spawn/example/policy.json" <<'PYEOF' && pass normalize "spawn/example/policy.json" || bad normalize "spawn/example/policy.json"
import sys
sys.path.insert(0, __import__('os').environ.get('LIFE_REPO','/home/operator/host-checkout'))
import json, symblic_autogen as A
A.normalize(json.load(open(sys.argv[1],encoding='utf-8'))); sys.exit(0)
PYEOF
"$PY" -c "import json,sys; d=json.load(open('$KIT/spawn/example/lineage.json')); sys.exit(0 if 0<=d['depth']<=64 and d['cell_id'].count('.')==2 else 1)" \
  && pass lineage "spawn/example/lineage.json" || bad lineage "spawn/example/lineage.json"

echo "== genome .sym (bin/symblic check, no model) =="
for f in "$KIT"/genome/*.sym; do
  if "$SYMBLIC" check "$f" >/dev/null 2>&1; then pass check "$(basename "$f")"; else bad check "$(basename "$f")"; fi
done

echo "== shell scripts (bash -n) =="
for f in "$KIT"/checks/*.sh "$KIT"/bin/*.sh "$KIT/VALIDATE.sh"; do
  if bash -n "$f" 2>/dev/null; then pass "bash -n" "$(basename "$f")"; else bad "bash -n" "$(basename "$f")"; fi
done

echo "== python scripts (py_compile) =="
for f in "$KIT"/bin/*.py; do
  if "$PY" -m py_compile "$f" 2>/dev/null; then pass py "$(basename "$f")"; else bad py "$(basename "$f")"; fi
done

echo "== db/schema.sql (idempotent apply) =="
if "$PY" - "$KIT/db/schema.sql" <<'PYEOF'
import sys, sqlite3
sql=open(sys.argv[1],encoding='utf-8').read()
c=sqlite3.connect(':memory:'); c.executescript(sql); c.executescript(sql)
need={'knowledge','lineage','metrics','commands','experiments'}
have={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
sys.exit(0 if need<=have else 1)
PYEOF
then pass sqlite "schema.sql"; else bad sqlite "schema.sql"; fi

echo
if [ "$fail" = "0" ]; then echo "ALL PASS"; else echo "SOME FAILED"; fi
exit "$fail"
===== END VALIDATE.sh =====