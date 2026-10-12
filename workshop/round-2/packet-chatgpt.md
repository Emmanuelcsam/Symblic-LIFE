# LIFE round-2 critique packet (ChatGPT web, highest effort)

## Critic brief
You critique LIFE, a Symblic script kit meant to turn a home cluster into a perpetually living self-improving system (cells = worker + reproducer agent pairs on lightweight local models; autogen lanes; reproduction admitted only by code). The kit is under /home/operator/host-checkout/docs/life (read LIFE.md fully, then the organs, policies, genome, checks, spawn protocol, db schema, README). All of their full text is in this packet. Highest effort. Your job: find EVERY detail that is not atomically defined (any threshold, file, schema, interval, model, engine, node, check, exit code, failure path, race, ordering, budget, unit or ownership that a lightweight model or a fresh agent could interpret in two ways), every contradiction with the platform facts in /home/operator/host-checkout/docs/life/BRIEF.md (included below), every unsafe or unbounded behaviour (runaway spawning, resource exhaustion, heat, secrets, writes outside the workspace, live-code damage, restart loops), and every missing organ or path the operator's brief requires. Output numbered findings: severity (high/medium/low), location (file and section or line number), the exact ambiguity or defect, and the atomic definition or fix to adopt (write the replacement text where possible). End with two integers on their own lines: FINDINGS_TOTAL=<n> and UNDEFINED_DETAILS=<n> (the count of findings that are undefined or ambiguous details), and a final line VERDICT=<CONVERGED|CHANGES NEEDED>.

Note: the kit has NOT been run; it was written but deliberately not executed. Critique the text only. This is round 2: v2 is the rewrite after round 1 (349 findings). LIFE.md sections 1-18 are included in full; its appendices repeat every file verbatim, so the files are included below as themselves instead. bin/life-tick.py (102 KB) and bin/life-ctl.py (20 KB) are omitted for length; their behaviour is specified in LIFE.md sections 4-15 and every number they use is in bin/life_common.py (included).


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


===== FILE: LIFE.md (sections 1-18; appendices omitted, files follow) =====
# LIFE v2 — the master Symblic script that brings the cluster to life

**Status: written, not run.** Nothing in this kit has been started, installed, armed or called. v2 is
the round-1 rewrite: three critics (ChatGPT web, Claude cloud, a local reviewer; 349 findings in
`workshop/round-1/`) found that v1's perpetual lanes stopped after three generations, its run ids
never matched the platform's, its organs overwrote one `verify.txt`, its reproducer never ran, its
spawn queue lived in the live repository, and its light models were unreachable from a worker node attempt.
v2 keeps the operator's design (cells with a worker and a reproducer, ten organs, code decides) and moves
every decision that a weak model or a remote agent cannot be trusted with into one code coordinator.
Every platform fact below was read in the live checkout on 2026-10-11 and is re-checked by code at
every tick (section 17). Every number has one definition, in `bin/life_common.py`; section 13
tabulates them. `VALIDATE.sh` (section 16) checks every file statically; the appendices hold every
file verbatim and `VALIDATE.sh` proves it.

Design stance, from the operator's brief (`BRIEF.md`): a living, breathing cluster that continuously
takes commands, optimises its codebase, fixes errors, learns from the internet, develops itself from
what it learns, creates databases, finds new ways to compute and store data, and reproduces and learns
efficiently, on extremely light models, each subline with two agents: one does one exact task, the
other reproduces. The Symblic program is the gcode; the agent is the printer. Models propose; code
decides. The host only orchestrates. Nothing restarts itself.

---

## 1. The cell: one subline, two agents

A **cell** is one row in the registry `cells` table: an organ, a focus (8..120 characters), a worker node, a
queue of **items** (units of work), and two agents.

- **WORKER** — performs one exact task on one item per turn and nothing else. For the five model
  organs it is a **genome program** (`genome/*.sym`, a typed Symblic program) run on a light model
  on the cell's own worker node: `bin/symblic run genome/P.sym --by ollama:MODEL@NODE` (or `bin/local-research`
  for research). The kernel checks every answer (type, range, enum, verbatim quote, record fields);
  code checks it again. For the three agent organs (codebase, selfdev, database) one stage needs a
  full read-edit-run tool loop: that stage is a **bounded autogen run** of a two-line statement script
  (`organs/<organ>.lines.txt`) on `agy`, in the cell's own git workspace, accepted only by code checks.
- **REPRODUCER** — never does the task and never decides *whether* to divide. Code decides that from
  the cell's own counters (section 9). When code says divide, the reproducer names two narrower foci
  (`genome/reproduce.sym`) and sorts queued items between them (`genome/assign-item.sym`, the tiniest
  rung: a two-way closed choice). Code commits the division only if both sides are nonempty.

A third role exists for changes: the **reviewer** (`genome/review-patch.sym`, run by an immune cell) reads
the actual diff of every patch and genome proposal. Worker, reproducer and reviewer are separate calls
with separate inputs; none can start, stop or admit anything.

Why code decides and models only propose: the operator's rule for Symblic is determinism from weak
models (kernel, spec and record do the deciding). A 1B model asked "should you divide?" is a coin;
"the cell had 12 or more queued items for 3 ticks, 0 failures, depth under 10, and a second worker node is
free" is a fact. The model's job is the part code cannot do: naming the split and sorting by meaning.

**Roles cannot be impersonated.** Workers are model calls with no tools, or agent runs on a worker node that
write only inside their own checkout. No worker can reach `~/.local/state/life` (STATE), the registry,
the control files or the loopback API that starts runs (no worker node tunnel to :8080; agents never get SSH
to the host from LIFE). Role identity is assigned by the coordinator when it builds the call.

## 2. The organism: ten organs

| # | organ | kind | seed cell (node) | worker program(s) | item | output |
|---|-------|------|------------------|-------------------|------|--------|
| 1 | command | model | command.0.00000000 (node-f) | classify-command | command | a route; a new item in the target organ, or an operator notice |
| 2 | learning | model | learning.0.00000000 (node-d) | bin/local-research | question | 0..3 new sources per run (global dedup), each a digest item |
| 3 | digest | model | digest.0.00000000 (node-b) | (fetch: code) extract-source, distill-lesson | source | a quote-verified knowledge row; at most one lesson item |
| 4 | codebase | agent | codebase.0.00000000 (node-i) | triage-error, then an agy run | finding | a gated patch bundle for review |
| 5 | immune | model | immune.0.00000000 (node-f) | review-patch | patch, proposal | accept / reject / needs_work; canaries (code) |
| 6 | selfdev | agent | selfdev.0.00000000 (node-a) | an agy run | lesson | a protected-line-checked genome proposal for review |
| 7 | compute | model | compute.0.00000000 (node-a) | propose-experiment, rank-experiment, then a benchmark job | experiment | a measured result vs a baseline |
| 8 | database | agent | database.0.00000000 (node-b) | an agy run | request | an additive migration applied to organism.sqlite3 |
| 9 | metabolism | code | — (in the tick) | none | — | the governor (section 10) |
| 10 | heartbeat | code | — (in the tick) | none | — | STATE/operator/status.json, metrics, notices (section 14) |

Metabolism and heartbeat are code steps of the tick on the host, not cells: they need no model, and an
agent on the host every 300 s would break "the host only orchestrates". At most 4 seed or child cells
share a worker node (`NODE_CELL_CAP`); the seed placement puts 2 on node-f, node-b and node-a and 1 on
node-d and node-i. LIFE never places work on the host, node-arm (the ARM node), node-c, node-e (not in the
brief's cluster list) or node-h (it hosts the protected service stack, `cluster_engine.TENANT_STACKS`).

## 3. Where everything lives, and who writes it

| path | what | written by |
|------|------|------------|
| `/home/operator/host-checkout/docs/life/` (KIT) | program material: this kit | the operator only; LIFE reads it |
| `/home/operator/.local/state/life/` (STATE, mode 0700) | all runtime state | the tick and life-ctl only |
| `STATE/life.sqlite3` | the registry: cells, items, runs, calls, lineage, knowledge, metrics, notices (`db/life.sql`) | the tick and life-ctl, one at a time (`STATE/tick.lock`) |
| `STATE/organism.sqlite3` | the database the organism grows (`db/organism.sql` + migrations) | the tick's database apply stage only |
| `STATE/control/{STOP,FREEZE,ARMED,SELFDEV_ARMED,watch.txt,benchmarks.json}` | operator switches and operator lists | the operator (life-ctl or by hand) |
| `STATE/inbox/`, `inbox-done/`, `inbox-refused/` | operator command files | the operator writes `inbox/`; the tick moves them |
| `STATE/release/<n>/{genome,organs,policies}/` | immutable releases; one is active | life-ctl seed, adopt, new-release |
| `STATE/calls/<call_id>/` | each program run's record (`bin/symblic run --dir`) | bin/symblic |
| `STATE/text/<16hex>.txt` | fetched source text snapshots (at most 6000 characters) | the tick |
| `STATE/runs/<request_id>/` | the exact statements and policy of each agent run | the tick |
| `STATE/bundles/{patches,proposals}/<id>/` | gated patches and proposals | the tick |
| `STATE/applied/<patch_id>/` | before-bytes and hashes of every operator apply | life-ctl apply |
| `STATE/backups/` | daily registry and organism copies (7 kept) and pre-migration copies | the tick |
| `STATE/operator/status.json`, `STATE/logs/tick.log` | status projection; log (rotated at 5 MiB, 3 kept) | the tick |
| `/home/operator/symblicos/projects/life-<organ>-<8hex>/` | one git workspace per agent cell | seed or division (clone), the tick (reset), autogen promotion |

`host-checkout` itself is never written by LIFE, except by `life-ctl.py apply`, which the operator
runs. `bin/local-research` keeps writing its own reports to `host-checkout/local_research_data/`
(its existing private behaviour). No STATE file is ever carried to a worker node: STATE is not a git
workspace, and the agent workspaces never contain STATE paths.

## 4. The coordinator tick (`bin/life-tick.py`)

Run by the user timer `units/life-tick.timer`: 10 min after boot, then 300 s after each tick **ends**
(`OnUnitInactiveSec=300`); the service (`units/life-tick.service`) has `TimeoutStartSec=1500`,
`SuccessExitStatus=3 5 6`, `Restart=no`, `MemoryMax=1G`, `Nice=10`. A tick stops starting new work
1200 s after it began (`TICK_DEADLINE`). One tick, in this exact order:

1. **lock** — `flock(STATE/tick.lock, LOCK_EX|LOCK_NB)`; held: print and exit 0.
2. **stop** — `control/STOP` exists: `stop_everything` (section 5) and exit 3.
3. **integrity** — every file of the active release matches its manifest sha256; the platform contract
   facts hold (section 17); the last canary round passed. Any failure: a notice and a hold.
4. **metabolism** — sample `/api/cluster/status` and `/api/cluster/highpower/state`; check the host's own
   load and io pressure; update the governor (section 10); compute the nodes available for new work.
5. **runs** — poll every LIFE autogen run through `GET /api/symblicos/autogen/get?id=RUN_ID`; confirm
   new runs' policy sha256; cancel runs older than 4500 s; collect ended runs. Poll benchmark jobs
   through `GET /api/cluster/jobs?kind=map&limit=200`; collect finished ones.
6. **inbox** — take at most 50 command files (section 6). Always, even disarmed.
7. **upkeep** — canaries every 12th tick; the daily backup at the first tick of each UTC day; the
   storage check (every 12th tick and the first).
8. If STOP appeared meanwhile: stop and exit 3. If not ARMED for this boot, or FROZEN, or any hold:
   write status and exit (0, or 5 for an integrity or contract hold). **Observe-only ends here.**
9. **findings** — run one due watched test in a codebase clone (section 7.4).
10. **dispatch** — give each unassigned queued item to the active cell of its organ with the fewest
    queued-or-running items (ties: lowest cell id).
11. **the host stages** — fetch up to 4 source texts; run at most one codebase gate, one selfdev gate
    and one database apply; then start agent runs (section 7).
12. **lifecycle** — update backlog and idle counters; quarantine, apoptosis; start a division (section 9).
13. **dispatch** again.
14. **node slots** — for each available LIFE worker node, plan at most ONE action (a division step, a
    benchmark start, or one program run), then run all program runs in parallel threads (one per
    worker node) and record the results (section 8). While they run the tick checks STOP every 2 s and kills
    every model process the moment STOP appears.
15. **status** — write `STATE/operator/status.json`.

Exit codes: 0 done (also observe-only, held, or the lock was busy), 1 a tick fault (logged, a
`tick_fault` notice; the next tick runs normally), 3 STOP handled, 5 integrity or contract hold, 6 not
seeded. One item's fault never stops a tick or poisons later ones: `Tick.guard` logs it, returns the
item to its queue, and fails the item after 3 such faults.

## 5. Control: ARMED, FREEZE, STOP, reboot, operator commands

| switch | meaning | set by |
|--------|---------|--------|
| ARMED | `control/ARMED` holds THIS boot's id (`/proc/sys/kernel/random/boot_id`); otherwise the tick only observes | `life-ctl.py arm` / `disarm` |
| FREEZE | nothing new starts; running work finishes | `freeze` / `thaw` |
| SELFDEV_ARMED | selfdev agent runs may start | `selfdev-arm` / `selfdev-disarm` |
| STOP | cancel every LIFE run and benchmark job, kill model processes, start nothing | `stop` / `unstop` |

**Reboot**: ARMED holds the old boot id, so the first tick after a reboot only observes. Runs that were
live are reconciled through the API before anything new starts (an unanswered run stays `unknown`
with a notice after 900 s; it is never resubmitted). Nothing restarts itself; the operator re-arms.

**STOP**: `life-ctl.py stop` writes `control/STOP` first (no new work can start from that instant: every
external effect re-checks it), then cancels every run in state `submitting`, `live` or `unknown`
(`bin/symblic-task autogen cancel RUN_ID`) and every running benchmark job
(`POST /api/cluster/job/cancel`), returns running items to the queue (agent items get a new attempt
number, so a later run uses a new request id), and opens a `stopped` notice listing anything
unresolved. If a tick holds the lock, that tick does all of this itself within 2 s. `unstop` removes
STOP; nothing that was cancelled restarts by itself.

**Operator commands** go only through `life-ctl.py` (section 15) or the inbox. Stop, freeze, cool and
power are never routed through a model: the command classifier cannot express them.

## 6. Work items

An item is one unit of work: `items` row `item_id = <organ>:<first 16 hex of sha256(kind + "\n" +
identity parts joined by "\n")>`. The same identity is never queued twice (`INSERT OR IGNORE`).

| kind | organ | identity | payload (closed JSON, at most 16384 characters) | taint |
|------|-------|----------|-----------------------------------------------|-------|
| command | command | command_id | `{command_id}` | operator |
| question | learning | normalised question text | `{question (<=600), command_id, found}` | operator |
| source | digest | source_key | `{source_key, url, text_path, text_sha256, fact_id, claim, quote}` (filled by stage) | web |
| finding | codebase | test_id, base commit or "owner", normalised first error line or command id | `{test_id, finding_text (<=600), base_commit, source: watch|operator, change_class}` | code / operator |
| patch | immune | patch_id | `{subject: patch, patch_id}` | code |
| proposal | immune | proposal_id | `{subject: proposal, proposal_id}` | code |
| lesson | selfdev | fact_id + "genome", or command id, or program + "failed" + error | `{program, lesson (10..300), proposal_id}` | web / operator / code |
| experiment | compute | command id or fact_id | `{seed_text (<=600), experiment_id, job_id, node, unit, started, timeout}` | operator / web |
| request | database | command id or fact_id | `{request (10..600), migration_id}` | operator / web |

States: `queued` → `running` → `done` | `abstained` | `failed` | `owner` (handed to the operator with a
notice). Queue order inside a cell: `priority` (2 high, 1 normal, 0 low) descending, then
`updated_at` ascending (a re-queued item goes to the back). Urgency only orders a queue; it never
bypasses a gate. **Taint**: `web` text may be quoted to a later worker only as data inside a template
field (`one_line`: NFC, control characters, backticks and braces removed, length-capped); it is never a
statement, check, policy, command or canary.

**The inbox** (`STATE/inbox/`): one command per file named `<YYYYmmddTHHMMSSZ>-<slug>.txt`, UTF-8,
1..4000 bytes, a regular file owned by the operator's uid (no symlink). `life-ctl.py command "TEXT"` writes
one atomically. A file failing any rule, or whose text matches the credential screen
(`life_common.SECRET_RX`), moves to `inbox-refused/` with a notice that never quotes the text.
`command_id = first 16 hex of sha256(file name + "\n" + text)`, so the same text sent twice is two
commands. Accepted files move to `inbox-done/`. The command's original text stays the only
authoritative instruction; the classifier's `restated` line is display text.

## 7. The organs, stage by stage

Each organ's items move through a fixed stage list (`life_common.STAGES`). A **slot** stage uses its
cell's worker node for one program run in step 14; an **the host** stage is code in step 11.

### 7.1 command — `classify` (slot)

`classify-command.sym` with `command_id`, `command_text` → `{organ, urgency, restated}`. Dispatch by code:

| route | effect |
|-------|--------|
| learning | a question item (text <= 600 characters; longer: notice `command_too_long`) |
| codebase | a finding item if the text names a test id `tests.<module>[...]`; else notice `command_needs_test` |
| database | a request item |
| compute | an experiment item |
| selfdev | a lesson item if the text names one genome program; else notice `command_needs_program` |
| immune, heartbeat, none | notice `command_<route>` for the operator (no lifecycle action follows from a model label) |

The item's priority is the urgency (low 0, normal 1, high 2). The command row becomes `dispatched` or `owner`.

### 7.2 learning — `research` (slot)

`bin/local-research --model M --node NODE --tools 8 --json "QUESTION"` (timeout 900 s; the model
searches through SearXNG at 127.0.0.1:18888 on the host and reads pages through code-run tools; it never
touches the network itself). From the result's `sources`, in order, code keeps URLs that start with
http(s), are at most 2000 characters, pass the credential screen, and whose
`source_key = symblic_autogen.items_key(url)` is not yet in `sources` (the ONE dedup authority for
every learning cell). At most 3 new sources per run; each becomes a `sources` row and a digest item.
The question then: 0 new sources → `dry_runs + 1`; at 3 dry runs in a row it is `done` (exhausted);
at 9 sources in total it is `done`; otherwise it returns to the back of the queue. A research error
matching an infrastructure pattern (no capacity, offline, SearXNG down, timeout) is `infra`.

### 7.3 digest — `fetch` (host) → `extract` (slot) → `distill` (slot)

- **fetch**: `local_research.read_page(url, 6000)` in a subprocess (`.venv` Python, timeout 90 s) — the
  existing `deep_research.safe_fetch` path: http(s) only, every resolved address global, every redirect
  re-validated, robots honoured. Fewer than 200 characters: `abstained` (EMPTY). A refusal: `abstained`.
  Otherwise the text is stored once at `STATE/text/<16hex>.txt` with its sha256; the snapshot never changes.
- **extract**: `extract-source.sym` → `supported false`: `abstained` (NO_SUPPORTED_CLAIM). Else code
  re-checks the snapshot hash, then that the whitespace-collapsed quote occurs in the
  whitespace-collapsed snapshot, 12..400 characters, claim 20..300; it inserts a `knowledge` row with
  `fact_id = first 16 hex of sha256(source_key + "\n" + quote)`, `quote_verified = 1` (the quote is in
  the text; the claim's truth is NOT established; `claim_status = unreviewed`).
- **distill**: `distill-lesson.sym` → target `genome` (with a program) → a selfdev lesson item; `compute`
  → an experiment item; `database` → a request item; `none` → nothing. All taint `web`.

### 7.4 codebase — `triage` (slot) → `patch` (agent run) → `gate` (host)

- **Findings** come from two sources only: the operator's `control/watch.txt` (at most 20 lines
  `tests.<module>[.<Class>[.<test>]]`) and operator commands naming a test id. Each tick at most one watched
  test runs, each test at most every 6 h: `nice -n 19 /usr/bin/python3 -s -B -m unittest TEST` in a
  codebase clone just reset to `origin/<branch recorded at seed>` (timeout 600 s). A nonzero exit makes a
  finding (one open finding per test) with the last 40 output lines as `finding_text` (withheld if they
  hold credential-like text). LIFE never reads the dashboard's logs or private stores.
- **triage**: `triage-error.sym` → `unknown`, `signature_change` or `confident false`: `owner` (notice
  `finding_owner`). Else the class is recorded.
- **patch**: the clone is reset to the finding's base commit (operator findings: the branch head now); the
  two-line `organs/codebase.lines.txt` is rendered with `scope` = "files under tests/" (test_only),
  "Markdown files under docs/" (comment_or_doc) or "the source files the failure names" (local_fix);
  checks: statement 0 `python3 -s -m unittest TEST`, statement 1 the verify line (section 7.9).
- **gate** (after a completed run): the promoted change is staged; the diff excludes `verify.txt`,
  `AUTOGEN-*`, `HANDOFF.md`. Refused when: no diff; test_only touches anything outside `tests/`; any
  other class touches `tests/` (the judging test stays fixed); comment_or_doc touches anything but
  `docs/*.md`; the diff holds credential-like text; or `checks/devcheck-gate.sh CLONE TEST` fails
  (module resolves inside the clone, `./bin/devcheck`, the focused test under system Python; timeout
  900 s). A pass writes `STATE/bundles/patches/<patch_id>/{patch.diff,meta.json}` with
  `patch_id = first 16 hex of sha256(diff)`, a `patches` row (`bundled`), and an immune review item.
  The clone is reset (`git reset --hard HEAD; git clean -fdq`) either way: only LIFE writes in it.
- `path_class` (code, from the paths alone): `tests`, `docs`, `restart_gated` (any `.py`, `bin/`,
  `.service`, `.timer`, `.sh`), `live_static` (anything else), or `mixed`. The operator sees it at apply.

### 7.5 immune — `review` (slot), canaries (code)

`review-patch.sym` with the bounded diff text (at most 6000 characters; a larger or missing diff goes
to the operator unreviewed), `change_class`, `path_class` and `checks_passed` computed by code. `accept`
→ patch `ready` + notice `patch_ready` (or proposal `ready` + `proposal_ready`); `reject` → `rejected`;
`needs_work` → `rejected`, and for a patch whose finding has fewer than 2 attempts, the finding is
re-queued at `patch` with the reviewer's reason appended. **Canaries** (`checks/canaries.txt`, shipped
in the kit, never empty): `bin/symblic check` on each active genome program and
`life-check.py registry` (`PRAGMA integrity_check`), every 12th tick, argv without a shell, timeout
120 s. Any failure holds all new work until a later round passes. Quarantine is section 9.

### 7.6 selfdev — `draft` (agent run) → `gate` (host); needs SELFDEV_ARMED

Before a run the workspace's `genome/` is made equal to the active release (committed in the workspace).
`organs/selfdev.lines.txt` asks the agent to change only the quoted instruction text of the named
program's ask lines. Checks: `bin/symblic check genome/P.sym` and `life-check.py genome-protected`
(versus the workspace HEAD), and the verify line. **gate**: the same protected-line rule against the
active release (`life_common.genome_protected_problems`: only `ask` instruction strings and `note`
lines may differ; every `given`, `define`, `ensure`, `let`, `if`, `return` line and every ask's name,
type and `from`/`with` clause stay byte-identical; at least one ask changed), and `bin/symblic check`
again. A pass bundles `STATE/bundles/proposals/<id>/` and queues an immune review. A proposal never
takes effect until the operator runs `life-ctl.py adopt` (a new release). Acceptance rules, budgets, gates,
placement and STOP are not in the genome, so selfdev cannot weaken them.

### 7.7 compute — `propose` (slot) → `rank` (slot) → `bench` (slot; a cluster job)

Needs a valid operator `control/benchmarks.json` (else items wait with notice `benchmarks_missing`).
Each benchmark: `{id, description, cmd (contains {{item}}, <= 2000 characters), param_rx, baseline
(matches param_rx), unit, timeout (30..900)}`; the cmd must print exactly one line
`LIFE_RESULT <number> <unit>` per run. **The model never writes a command.**
- **propose**: `propose-experiment.sym` with the seed text and the catalogue → code requires an existing
  benchmark id, a parameter matching its `param_rx` and different from the baseline, a comparison
  (`lt le gt ge` → `< <= > >=`) and `threshold_pct` 1..10000; `experiment_id = first 16 hex of
  sha256(benchmark_id + "\n" + param)`; a repeated experiment is `abstained`.
- **rank**: `rank-experiment.sym` → measured only when `feasible` is true AND `risk` is `low` AND
  `score >= 60`; else the item is `done` as ineligible.
- **bench**: `POST /api/cluster/map` with `cmd = "timeout T nice -n 15 " + cmd`, `items = [param,
  baseline]` (run in that order), `targets = [the cell's node]`, `parallel = 1`, `timeout = 2T + 60`.
  The node takes no other LIFE work while the job runs. Exactly two `LIFE_RESULT` lines in the
  benchmark's unit, baseline > 0: `ratio_pct = floor(100 x candidate / baseline)`, passed when
  `ratio_pct <op> threshold_pct`. A passed experiment opens an `experiment_passed` notice: adopting a
  new way to compute or store is the operator's decision. A job past `timeout + 300` s is cancelled.
  LIFE never enables high-power mode; nothing here changes power settings.

### 7.8 database — `draft` (agent run) → `apply` (host)

Before a run the workspace's `schema-snapshot.sql` is made equal to organism.sqlite3's schema.
`migration_id = <4-digit next number>_<slug of the request, <= 30 characters>`. The agent writes
`migrations/<id>.sql`. **apply**: `life_common.migration_problems`: 1..24 statements, at most 16384
bytes, each exactly one of `CREATE TABLE IF NOT EXISTS org_x (...)`, `CREATE [UNIQUE] INDEX IF NOT
EXISTS org_x ON org_y (...)`, `ALTER TABLE org_x ADD COLUMN c TYPE ...`; none of DROP, DELETE, UPDATE,
INSERT, REPLACE, ATTACH, DETACH, PRAGMA, VACUUM, TRIGGER, VIEW, load_extension, readfile, writefile;
and the whole applies cleanly in memory on top of the snapshot. Then: a backup copy of
organism.sqlite3, one transaction applying every statement plus a `schema_migrations` row, a commit of
the migration file in the workspace, a `migrations` registry row and a `migration_applied` notice. The
control registry is a different file, so no migration can touch control state.

### 7.9 Agent runs (codebase patch, selfdev draft, database draft)

- **Policy** (every LIFE agent run, `policies/<organ>.json`, checked by `agent_policy_problems`):
  `perpetual false, until_done false, candidates 1, regenerate 2, depth 0, children 2, generations 1,
  agents_max 3, attempt_seconds 900, wall_seconds 3600, novelty_limit 2, saturation 0, strategies
  [fresh, feedback], syntax true, require_change true, self_split false, designer false, final [],
  hidden []` and checks on statements 0 and 1. So: no engine or node rotation, no internal splitting
  (`self_split false` and bounded-mode `depth 0` make `decide` never decompose), at most 3 agents.
  `generations 1` is the platform minimum; a remote handoff request is refused by the platform
  ("remote handoff unsupported") and counts as a failed attempt.
- **Statements**: rendered from the active release's template with exactly the organ's fields, each
  matching its exact form (`life_common.PLACEHOLDERS`) and passing the credential screen; the result
  must name the workspace in every statement and lint with ZERO findings (`symblic_autogen.lint` with
  the workspace as root). The templates write the workspace as the literal absolute prefix
  `/home/operator/symblicos/projects/life-<organ>-` followed by `{ws_id}`, which `render` derives from
  `ws` (its last 8 hex digits, refused when `ws` belongs to another organ), so even the raw template
  text names an absolute folder and lints with ZERO findings without a root.
- **Submit**: `request_id = life-<organ>-<cell hex8>-<item 16hex>-<attempt>`; expected
  `run_id = autogen-<first 24 hex of sha256(request_id)>`. A `runs` row (`submitting`) is committed
  BEFORE `bin/symblic-task start --lines SNAPSHOT --root WS --cwd WS --node NODE --engine agy --id
  REQUEST_ID --json` plus the full flag list (`policy_flags`: every field explicit, none left to a
  server default). The CLI reads the snapshot file at submit time (`read_lines_file`), so the snapshot
  is evidence, not a live input. rc 1 or 2: `not_submitted` (item re-queued; failed after 3).
  Anything else: `unknown` until the next poll finds the run (then its server policy sha256 must equal
  `symblic_autogen.normalize(policy)['sha256']`, else the run is cancelled) or the API answers 404
  (`not_submitted`).
- **Placement**: the cell's node only, and only when the task-engine catalogue
  (`bin/symblic-task catalog --json`) reports agy ready there; otherwise notice `agy_not_ready` and
  wait. Never another node, never the host. At most 2 LIFE runs live fleet-wide, 1 per cell, 12 a UTC day.
- **Collection**: `completed` → the next stage. `failed`/`stuck`/`cancelled`/`unknown`: when every
  attempt failure is non-semantic (INFRASTRUCTURE, REFUSAL, CANCELLED, CONFLICT, FETCH_FAILURE,
  TIMEOUT) the item is re-queued (failed after 3 such runs); otherwise the item fails and the cell's
  `failures_in_a_row` grows. The workspace is reset after every failed run.
- **verify.txt**: exactly one line — codebase `finding=<16hex> test=<test_id>`, selfdev
  `proposal=<16hex> program=<name>`, database `migration=<id>` — checked by `life-check.py verify-line`.

## 8. Light models: ladders, the program contract, escalation

**Ladders** (`organs/organs.json`, release-managed; models drawn from those installed on all five LIFE
worker nodes according to the authoring pass's `bin/local-research --list`; a model missing on a node fails
as `infra` there and never counts against the cell):

| program | rung 0 | rung 1 |
|---------|--------|--------|
| classify-command | llama3.2:1b | qwen3:4b-instruct |
| triage-error | qwen2.5-coder:3b | qwen3:4b-instruct |
| extract-source | qwen3:4b-instruct | — |
| distill-lesson | llama3.2:1b | qwen3:4b-instruct |
| propose-experiment | qwen3:4b-instruct | — |
| rank-experiment | llama3.2:1b | qwen3:4b-instruct |
| review-patch | qwen2.5-coder:3b | qwen3:4b-instruct |
| reproduce | llama3.2:1b | qwen3:4b-instruct |
| assign-item | qwen2.5:0.5b | llama3.2:1b |
| local-research | qwen3:4b-instruct | — |

**The program contract.** The tick runs, from cwd STATE with a fixed environment (PATH, HOME, LANG,
`SYMBLIC_THERMAL=1`, `SYMBLIC_CALL_WALL_S=900`, `DASH_URL`, nothing inherited):

```
bin/symblic run STATE/release/<n>/genome/P.sym --by ollama:MODEL@NODE --json --max-calls 12 \
  --ollama-limits '{"num_predict": 1024, "timeout_seconds": 600}' --dir STATE/calls/<call_id> \
  --input NAME=<JSON-encoded value> ...
```

in its own process group, killed at 900 s. Genome asks carry no `by`: an ask-level `by` would win over
`--by` (`symblic_run.Run._apps`), so the code chooses model and node. Values are JSON-encoded so text
stays text. Every call goes through the fleet runner (`symblic_apply` → `fleet_runner.launch`), which allows one
model process per node (`fleet_runner._check_capacity`) and waits up to 1800 s for a busy node;
LIFE adds one program run per node per tick and requires `memAvailMiB >= 2048 + the model's size`
(0.5b 400, 1b 1300/900, 3b 1900, 4b 2600 MiB) before a call. Each program's worst-case model calls
(votes x attempts) is written in its `note` and is at most 12.

**Outcome classification** (code): exit 0 with `status done` and exactly one returned record → `done`.
No JSON, a timeout, or an error whose kind is `unavailable`/`capacity`/`timeout` or whose message
matches the infrastructure pattern → `infra`: the item stays queued, the node is held 300 s, nothing
counts against the cell. Anything else → `failed`.

**Escalation and tuning** (per item, per cell): a `failed` item retries at the next rung (at most 2
extra rungs). Past the top it fails, the cell's `failures_in_a_row` grows, and a code lesson
(`taint code`) asks selfdev to improve that program. Each cell keeps, per program, a base rung and a
window of its last 10 outcomes (b = done at base, e = needed escalation, f = failed): 5 or more e/f in
the last 10 moves the base rung up; 10 b in a row moves it down one (the cheapest model that works).
This is how cells learn efficiently without a model deciding anything about itself.

## 9. Reproduction

The full protocol is `spawn/PROTOCOL.md`. Summary: code decides eligibility (active, 0 failures,
depth < 10, backlog >= the organ's `divide_backlog` for 3 ticks, organ < 3 live cells, organism <= 16,
<= 8 births a day, one open division, 6 h after an abort, organ efficiency >= 0.2, a second worker node
free); the reproducer names two foci; assign-item sorts up to 16 items (4 per tick; the rest by the
parity of sha256(item_id)); one transaction births both children (child a on the parent's worker node,
child b on another), moves the items and retires the parent (`divided`).
`cell_id = <organ>.<depth>.<first 8 hex of sha256(parent + "\n" + letter + "\n" + focus)>`. Seeds are
`<organ>.0.00000000`. A repeated lineage key aborts the division. Endings: apoptosis after 288 idle
ticks when a sibling remains; quarantine after 8 failed items in a row (operator releases); operator retire.
The organism therefore grows where work piles up, shrinks where it is idle, never below one cell per
organ, and never past the heat, budget and placement limits.

## 10. Metabolism (the governor)

Every tick reads `GET /api/cluster/status` (fields used: `ts`, and per node `online`, `vitals.cpu` =
percent busy over the probe interval, `vitals.temp` °C, `vitals.memavail` bytes) and
`GET /api/cluster/highpower/state` (`cool.phase`), with bin/symblic-task's request shape (loopback,
no proxy, no redirect, Host 127.0.0.1:8080).

- **Hold** (no new work at all) when: the status is unreadable or its `ts` is older than 180 s; cool
  mode is on or unreadable; the host `load1 >= 0.75 x nproc`; the host `/proc/pressure/io` full avg60 >=
  10.0 or unreadable. Telemetry is never replaced by zero.
- **Fleet loaded** in a sample: at least 3 online LIFE worker nodes with `cpu >= 50`. `dt` = seconds since the
  previous sample, at most 1500. Loaded: `continuous += dt`, `quiet = 0`. Not loaded: `quiet += dt`; when
  `quiet >= 600`, `continuous = 0`. **Rest** when `continuous >= 3000` and until `quiet >= 600`. A short
  gap never resets the window; the fleet's own non-LIFE load counts too. This implements "continuous
  all-worker node load under about an hour, then rest".
- **Per node**: hot at `temp >= 85` and cool again below 75 (hysteresis; the same numbers as
  `symblic_apply.THERMAL_HOT/THERMAL_COOL`); a missing temperature counts as hot. A hot, offline, held
  or benchmarking node takes no new LIFE action.
- The governor row (`governor` table) is the single truth both scheduling and status read.

## 11. Immunity and safety

- Review: section 7.5. Canaries: section 7.5. Quarantine: section 9.
- Integrity: release manifests every tick; the platform contract every tick (section 17).
- Secrets: the credential screen (`SECRET_RX`) on inbox text, finding text, rendered template values,
  URLs and patch diffs; matching text is refused or withheld, never stored or echoed. LIFE reads no
  `.env`, no `easy_config.json`, no private store, no log. Subprocesses get a fixed environment.
- Web text: section 6 (taint). Model processes have no network; research and fetches go through the
  existing safe-fetch path; guest internet is untouched.
- Rollback: `life-ctl.py revert` restores the recorded pre-apply bytes only when every touched file
  still has its post-apply hash; otherwise it names the changed files and does nothing. `git checkout --`
  is never used on the live tree.
- LIFE renders nothing in a web page in v2; any later dashboard view must escape every string and pass
  the CSP and service-worker rules.

## 12. Databases

- **Registry** `STATE/life.sqlite3` (`db/life.sql`): WAL, `synchronous=FULL`, `busy_timeout=5000`,
  `foreign_keys=ON`; one writer at a time under `STATE/tick.lock`; CHECK constraints encode every enum,
  range and identity rule (organs, nodes, depth 0..10, one active release, one open division per
  parent, quote_verified = 1, ...). Times are UTC Unix seconds from `int(time.time())`.
- **Organism** `STATE/organism.sqlite3` (`db/organism.sql`): starts with `schema_migrations` only;
  grows only by section 7.8 migrations.
- **Backups**: the first tick of each UTC day copies both through the SQLite backup API to
  `STATE/backups/{life,organism}-YYYY-MM-DD.sqlite3` (mode 0600, the newest 7 kept); every migration
  first copies the organism database to `organism-before-<id>.sqlite3`. Restore is an operator action:
  stop the timer, copy a backup over the file, start the timer.
- Python's `sqlite3` module is used everywhere (`sqlite3` CLI is not installed on the host).

## 13. Every number

| name | value | meaning |
|------|-------|---------|
| TICK_SECONDS | 300 | timer interval after the previous tick ends |
| TICK_DEADLINE | 1200 s | no new work starts later in a tick |
| CALL_TIMEOUT | 900 s | one program or research process |
| CALL_MAX_MODEL_CALLS | 12 | `--max-calls` per program run |
| OLLAMA_LIMITS | num_predict 1024, timeout 600 s | per model call |
| ASSIGN_PER_SLOT | 4 | assign-item runs per division tick |
| LIFE_MAX_CELLS / ORGAN_CELL_CAP / NODE_CELL_CAP | 16 / 3 / 4 | live cells |
| MAX_DEPTH | 10 | deepest child |
| DIVIDE_SUSTAIN / DIVISION_COOLDOWN / DIVISIONS_OPEN_MAX | 3 ticks / 21600 s / 1 | division |
| APOPTOSIS_IDLE_TICKS / QUARANTINE_FAILURES | 288 / 8 | endings |
| NODE_HOLD_SECONDS | 300 | after an infra answer |
| AGENT_RUNS_LIVE_MAX / AGENT_RUN_KILL_SECONDS | 2 / 4500 s | agent runs |
| PROGRAM_RUNS_PER_DAY / AGENT_RUNS_PER_DAY / BENCH_JOBS_PER_DAY / BIRTHS_PER_DAY | 1200 / 12 / 12 / 8 | UTC-day budgets |
| QUESTION_DRY_LIMIT / QUESTION_SOURCE_LIMIT / NEW_SOURCES_PER_RUN / RESEARCH_TOOLS | 3 / 9 / 3 / 8 | research |
| SOURCE_TEXT_CHARS / SOURCE_TEXT_MIN | 6000 / 200 | fetched text |
| DIFF_REVIEW_CHARS | 6000 | largest model-reviewed diff |
| EFFICIENCY_FLOOR / EFFICIENCY_MIN_RUNS | 0.2 / 20 | division gate |
| STATE_MAX_BYTES / DISK_FREE_MIN | 10 GiB / 5 GiB | storage hold |
| LOG_ROTATE_BYTES / BACKUP_KEEP | 5 MiB / 7 | upkeep |
| CANARY_EVERY_TICKS / FINDINGS_EVERY_SECONDS | 12 / 21600 s | immune, codebase |
| SAMPLE_MAX_AGE / LOADED_CPU / FLEET_LOADED_NODES | 180 s / 50 % / 3 | governor |
| WORK_WINDOW / REST_SECONDS | 3000 s / 600 s | governor |
| HOT_C / COOL_C / MEM_RESERVE_MIB | 85 / 75 °C / 2048 MiB | per node |
| HOST_LOAD_FRACTION / HOST_IO_FULL_AVG60 | 0.75 / 10.0 | the host |
| agent policy | see section 7.9 | every agent run |
| item payload / inbox file / command text | 16384 / 4000 / 4000 | sizes |

A spent daily budget holds that class of work until 00:00 UTC with one `budget` notice. Storage
over its limit holds all new work; nothing is deleted automatically (only backups beyond 7 and
rotated logs beyond 3).

## 14. Observability

`bin/life-status.py` (read-only; `--json`): control switches, release, governor, today's budget, every
live cell with its queue, live runs, open notices; it prints UNKNOWN and exits 1 when the registry
cannot be read. `STATE/operator/status.json` is the same projection written each tick. `notices` (kinds:
stopped, integrity, contract, canary_failed, storage, budget, telemetry-driven holds, inbox_refused,
command_*, finding_owner, patch_ready, proposal_ready, review_owner, migration_applied,
experiment_passed, benchmarks_missing, agy_not_ready, workspace, quarantine, render, run_unknown,
policy_mismatch, bench_refused, tick_fault) stay open until acknowledged; one per kind and subject.
`metrics` holds per organ per UTC day: items done, failed, abstained, program runs, agent runs.

## 15. Operator operations (`bin/life-ctl.py`)

seed, arm/disarm, freeze/thaw, selfdev-arm/selfdev-disarm, stop/unstop, command, notices/ack, apply,
revert, adopt, new-release, release-cell, retire, contract. Registry-changing commands take the tick's
lock (waiting up to 1500 s). `apply` refuses unless the patch is `ready` (or `owner`), its diff hash
matches its id, and `git apply --check` passes against the live checkout; it copies every touched
file's before-bytes, applies without staging or committing, records before/after sha256, and prints
the restart-gated or live-static warning. `adopt` refuses unless the proposal is `ready`, the active
release still has the proposal's base, and the new release passes the protected-line rule and
`bin/symblic check`; running calls keep the release they started with.

## 16. Validation

`VALIDATE.sh` runs only static checks (no model, agent, network or task): inventory and executable
bits; `bin/symblic check` on the nine programs; the organs.json closed schema; each raw agent template
linted with zero findings and no root; each agent template rendered with `organs/fixtures.json`, linted
with zero findings, its policy normalized and equal to the
fixed agent policy; `bash -n` and `ast.parse` on every script; both schemas applied twice in memory
with negative inserts; canary targets; the example benchmarks; this document's appendices against
the files; the platform contract. It ends **STATIC PASS**. It is not an admission test (GAP 8).

## 17. Platform facts LIFE relies on (verified 2026-10-11; re-checked every tick by `contract_problems`)

- `symblicos/autogen.py:AutogenManager.submit` — `run_id = 'autogen-' + sha256(client_request_id)[:24]`;
  cwd must be an existing folder with `.git`; a duplicate id of a terminal run is not rescheduled;
  `local` engine runs only spec sheets and refuses perpetual lanes; `ADMITTED_ENGINES` includes agy;
  run statuses `queued, active, completed, failed, cancelled, unknown, stuck`.
- `symblic_autogen.decide` — a perpetual lane without `until_done` stops at `generations` (default 3);
  bounded mode decomposes only while `depth < policy depth`; `normalize` refuses unknown keys and
  returns `sha256`; `agents_max` and `wall_seconds` cap the whole run; `items_key` normalises DOIs and
  URLs; `next_strategy` lives here (not in symblicos/autogen.py).
- `bin/symblic-task` — `start ... --json` prints `{id, duplicate, run}`; `autogen get|cancel`;
  `catalog --json` lists nodes with `ready` per engine; `--feedback-chars` has no flag (LIFE never sets it).
- `bin/symblic run` — `--by`, `--input name=value` (JSON parsed when valid), `--dir`, `--json`,
  `--max-calls`, `--ollama-limits`; exit 0 only for `status done`. `symblic_run.Run._apps`: an ask-level
  `by` wins over `--by`. Default `retries` 2 (`Run._retries`, at most 5). `len()` counts characters.
- `symblic_apply` — every ollama call goes through `fleet_runner.launch`; `CAPACITY_WAIT` 1800 s;
  `THERMAL_HOT/COOL` 85/75 °C with `SYMBLIC_THERMAL=1`; `cluster_temps` reads `/api/cluster/status`.
- `fleet_runner._check_capacity` — one model process per node and kind.
- `agent_hub._check_remote` — an engine runs on a node only when the node reports it ready;
  `REMOTE_ENGINES` excludes copilot; `provision_remote` sends only the run's branch to a worker node;
  `carry_over` skips ignored files and files over 25 MiB.
- `cluster_engine` — `GET /api/cluster/status` (`status`, `ts`), `GET /api/cluster/capacity`,
  `POST /api/cluster/map` (`cmd` with `{{item}}`, `items`, `targets`, `parallel`, `timeout`),
  `GET /api/cluster/jobs`, `POST /api/cluster/job/cancel`; operator-only, loopback.
  `cluster_highpower.view` — `cool.phase`; leases 5..120 min, rest after a lease.
- `local_research.read_page` → `deep_research.safe_fetch` (every hop re-validated, global addresses
  only); `bin/local-research --model --node --tools --json` prints `[{model, node, answer, sources, steps}]`.
- `sqlite3` CLI: absent on the host (`command -v sqlite3` rc 1).

## 18. GAPS — what is not done, and the rule meanwhile

1. **No platform hook for code-admitted runs inside autogen.** Reproduction is the tick's registry
   transaction instead; smallest platform change: none needed for v2.
2. **Autogen cannot run a light model as a statement worker** (the `local` engine takes spec sheets
   only). Model organs therefore run genome programs from the tick, not autogen lanes.
3. **Remote handoff is refused.** Agent runs use `generations 1` and short statements.
4. **No fleet duty-cycle field in autogen.** The tick's governor gates everything LIFE starts; a
   running agent run is bounded by `attempt_seconds 900` and `wall_seconds 3600`, and cancelled at 4500 s.
5. **high-power mode cannot be requested safely by code.** LIFE never touches power; passed experiments
   are notices.
6. **Installed-model inventory is not re-verified at runtime.** A missing model fails as `infra` on
   that node; the operator can check with `bin/local-research --list`.
7. **Benchmark commands run on the worker node host through the cluster control plane**, not a sandbox: only
   operator-written templates run, with model-chosen parameters that must match the template's `param_rx`.
8. **No admission tests yet.** `VALIDATE.sh` proves the static contract only. Before arming, the
   coordinator needs mocked tests (fake API, fake bin/symblic, temporary STATE) for every gate, STOP
   mid-tick, crash between submit and record, duplicate ticks, division abort and commit, quarantine,
   budget and storage holds. They were not written or run in round 1 because this workflow may run
   only lint, check, normalize and syntax checks.
9. **Genome programs have no recorded fixtures.** `bin/symblic replay` could test the code paths
   model-free once real call records exist.
10. **Engine readiness on the worker nodes is unknown until the catalogue says so.** Agent organs wait
    (notice `agy_not_ready`) rather than run elsewhere.


===== FILE: README.md =====
# LIFE v2 — how to bring the cluster to life, use it, and stop it

This folder is a **script kit, not a running system**. Nothing here has been started, installed or
armed. The operator starts it, once, when they choose. Read this file, then `LIFE.md` (the master script:
every rule, number, path and file, with every file embedded verbatim).

LIFE is a cell organism on the cluster. Each **cell** is one subline of work with two agents: a
**worker** that does one exact task on a light local model (or, for three organs, a bounded `agy` run),
and a **reproducer** that, when code says the cell may divide, splits its work into two child cells
on two worker nodes. One code program, `bin/life-tick.py`, runs every 300 s on the host: it admits, schedules,
checks and records everything. Models propose; code decides. The host only orchestrates.

## Start it (operator, on the host)

1. **Validate** (static: no model, no agent, no network):
   ```
   /home/operator/host-checkout/docs/life/VALIDATE.sh      # must end STATIC PASS
   ```
2. **Seed** (creates `/home/operator/.local/state/life`, release 1, three workspaces and the eight seed
   cells; starts nothing):
   ```
   /home/operator/host-checkout/docs/life/bin/life-seed.sh  # type START
   ```
3. **Give it work and limits** (all optional, all operator files under `~/.local/state/life/control/`):
   - `watch.txt`: one unittest id per line (`tests.test_x`), at most 20 — the codebase organ's error source.
   - `benchmarks.json`: copy `benchmarks/benchmarks.example.json`, read every command, keep only what you
     approve — the compute organ measures only these.
4. **Install the timer** (user units; the kit never installs them):
   ```
   cp /home/operator/host-checkout/docs/life/units/life-tick.{service,timer} ~/.config/systemd/user/
   systemctl --user daemon-reload
   systemctl --user enable --now life-tick.timer
   loginctl enable-linger operator          # once: user timers keep running after logout
   ```
   Disarmed, each tick only observes: it samples the cluster, takes inbox commands and writes status.
5. **Arm** (for this boot only; a reboot always comes back disarmed):
   ```
   /home/operator/host-checkout/docs/life/bin/life-ctl.py arm
   /home/operator/host-checkout/docs/life/bin/life-ctl.py selfdev-arm   # optional: genome proposals
   ```

## Use it

```
B=/home/operator/host-checkout/docs/life/bin
$B/life-ctl.py command "Research how ceramic foam porosity is measured by gas adsorption"
$B/life-status.py                 # control, governor, budgets, cells, runs, notices
$B/life-ctl.py notices            # what needs you; ack with: $B/life-ctl.py ack ID
$B/life-ctl.py apply PATCH --confirm APPLY      # a reviewed, gated patch into the live checkout (no commit)
$B/life-ctl.py revert PATCH --confirm REVERT    # only if nobody changed those files since
$B/life-ctl.py adopt PROPOSAL --confirm ADOPT   # a reviewed genome proposal becomes the next release
```

LIFE never applies a patch, adopts a genome change, restarts the dashboard, commits to
host-checkout, enables high-power mode or changes guest internet. Those stay with you.

## KILL SWITCH

| what | command | effect |
|------|---------|--------|
| stop everything now | `$B/life-ctl.py stop` | writes `control/STOP`; a running tick kills its model processes within 2 s; every LIFE autogen run and benchmark job is cancelled; nothing new starts. `unstop` removes STOP; cancelled runs are never restarted (their items wait in the queue) |
| pause new work | `$B/life-ctl.py freeze` / `thaw` | running work finishes; nothing new starts |
| disarm | `$B/life-ctl.py disarm` | same as a reboot: observe only until `arm` |
| stop the timer | `systemctl --user disable --now life-tick.timer` | no tick at all |
| one cell | `$B/life-ctl.py retire CELL` | the cell ends; its queue returns to its organ |

STOP lives outside every workspace (`~/.local/state/life/control/`), which no worker can reach.

## Safety summary

- Light models run only on node-a/b/d/f/i through the fleet runner (`bin/symblic run --by ollama:M@node-X`,
  `bin/local-research`); never on the host, the ARM node, node-c/e or node-h.
- Agent runs are `agy` only, strategies `fresh,feedback` (no engine or node rotation), 3 agents per run,
  at most 2 runs at once and 12 a day, no internal splitting (`self_split false`, `depth 0`).
- The heat governor rests the fleet after 3000 s of fleet load until 600 s are quiet; hot worker nodes
  (85 °C, cool again below 75 °C) get no new work.
- No credential, `.env` value or private-store value is written by LIFE; inbox text with
  credential-like strings is refused; web text is data (taint `web`), never a statement or command.


===== FILE: organs/codebase.lines.txt =====
Fix the failing test {test_id} in the folder /home/operator/symblicos/projects/life-codebase-{ws_id} keeping every existing part of every file that does not need to change, changing only {scope}, so that the command python3 -m unittest {test_id} passes; the failing output was: {finding_text}
Run the command python3 -m unittest {test_id} in the folder /home/operator/symblicos/projects/life-codebase-{ws_id} and verify the fix by writing exactly the line finding={finding_id} test={test_id} to the file verify.txt in the folder /home/operator/symblicos/projects/life-codebase-{ws_id}.


===== FILE: organs/database.lines.txt =====
Create the file /home/operator/symblicos/projects/life-database-{ws_id}/migrations/{migration_id}.sql containing only SQLite statements of the three forms CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS and ALTER TABLE with ADD COLUMN, where every table and index name starts with org_, that together implement this data request: {request}
Read the file /home/operator/symblicos/projects/life-database-{ws_id}/migrations/{migration_id}.sql and verify it by writing exactly the line migration={migration_id} to the file verify.txt in the folder /home/operator/symblicos/projects/life-database-{ws_id}.


===== FILE: organs/selfdev.lines.txt =====
Update the file /home/operator/symblicos/projects/life-selfdev-{ws_id}/genome/{program}.sym keeping every existing part, changing only the quoted instruction text inside its ask lines, so that the program addresses this lesson: {lesson}
Read the file /home/operator/symblicos/projects/life-selfdev-{ws_id}/genome/{program}.sym and verify the change by writing exactly the line proposal={proposal_id} program={program} to the file verify.txt in the folder /home/operator/symblicos/projects/life-selfdev-{ws_id}.


===== FILE: organs/organs.json =====
{
  "version": 2,
  "organs": {
    "command":  {"kind": "model", "seed_node": "node-f", "seed_focus": "route every operator command to exactly one organ", "divide_backlog": 12},
    "learning": {"kind": "model", "seed_node": "node-d", "seed_focus": "research the open questions and record new sources", "divide_backlog": 12},
    "digest":   {"kind": "model", "seed_node": "node-b", "seed_focus": "turn each new source into one quote-checked claim", "divide_backlog": 12},
    "codebase": {"kind": "agent", "seed_node": "node-i", "seed_focus": "fix one failing watched test per run", "divide_backlog": 6},
    "immune":   {"kind": "model", "seed_node": "node-f", "seed_focus": "review every bundled patch and proposal adversarially", "divide_backlog": 6},
    "selfdev":  {"kind": "agent", "seed_node": "node-a", "seed_focus": "turn one lesson into one checked genome proposal", "divide_backlog": 6},
    "compute":  {"kind": "model", "seed_node": "node-a", "seed_focus": "propose rank and measure one compute or storage experiment", "divide_backlog": 6},
    "database": {"kind": "agent", "seed_node": "node-b", "seed_focus": "turn one data request into one additive migration", "divide_backlog": 6}
  },
  "ladders": {
    "classify-command":   ["llama3.2:1b", "qwen3:4b-instruct"],
    "triage-error":       ["qwen2.5-coder:3b", "qwen3:4b-instruct"],
    "extract-source":     ["qwen3:4b-instruct"],
    "distill-lesson":     ["llama3.2:1b", "qwen3:4b-instruct"],
    "propose-experiment": ["qwen3:4b-instruct"],
    "rank-experiment":    ["llama3.2:1b", "qwen3:4b-instruct"],
    "review-patch":       ["qwen2.5-coder:3b", "qwen3:4b-instruct"],
    "reproduce":          ["llama3.2:1b", "qwen3:4b-instruct"],
    "assign-item":        ["qwen2.5:0.5b", "llama3.2:1b"],
    "local-research":     ["qwen3:4b-instruct"]
  }
}


===== FILE: organs/fixtures.json =====
{
  "codebase": {"ws": "/home/operator/symblicos/projects/life-codebase-00000000", "kit": "/home/operator/host-checkout/docs/life",
               "test_id": "tests.test_symblic_autogen", "finding_id": "0123456789abcdef",
               "finding_text": "AssertionError: 3 != 4 in test_normalize_limits (tests.test_symblic_autogen.PolicyTests)",
               "scope": "the source files the failure names"},
  "selfdev":  {"ws": "/home/operator/symblicos/projects/life-selfdev-00000000", "kit": "/home/operator/host-checkout/docs/life",
               "proposal_id": "fedcba9876543210", "program": "extract-source",
               "lesson": "Ask small models to copy the quote first and state the claim second, so the claim stays inside the quoted span."},
  "database": {"ws": "/home/operator/symblicos/projects/life-database-00000000", "kit": "/home/operator/host-checkout/docs/life",
               "migration_id": "0001_org_reading_list", "request": "Keep a reading list of papers with title, DOI, the question it answers and whether it was read."}
}


===== FILE: policies/codebase.json =====
{
  "version": 1, "perpetual": false, "until_done": false, "candidates": 1, "regenerate": 2, "depth": 0, "children": 2,
  "generations": 1, "agents_max": 3, "attempt_seconds": 900, "wall_seconds": 3600, "novelty_limit": 2, "saturation": 0,
  "strategies": ["fresh", "feedback"], "syntax": true, "require_change": true, "self_split": false, "designer": false,
  "checks": {
    "0": ["python3 -s -m unittest {test_id}"],
    "1": ["python3 -B {kit}/bin/life-check.py verify-line codebase verify.txt finding={finding_id} test={test_id}"]
  },
  "final": [], "hidden": []
}


===== FILE: policies/database.json =====
{
  "version": 1, "perpetual": false, "until_done": false, "candidates": 1, "regenerate": 2, "depth": 0, "children": 2,
  "generations": 1, "agents_max": 3, "attempt_seconds": 900, "wall_seconds": 3600, "novelty_limit": 2, "saturation": 0,
  "strategies": ["fresh", "feedback"], "syntax": true, "require_change": true, "self_split": false, "designer": false,
  "checks": {
    "0": ["python3 -B {kit}/bin/life-check.py migration migrations/{migration_id}.sql schema-snapshot.sql"],
    "1": ["python3 -B {kit}/bin/life-check.py verify-line database verify.txt migration={migration_id}"]
  },
  "final": [], "hidden": []
}


===== FILE: policies/selfdev.json =====
{
  "version": 1, "perpetual": false, "until_done": false, "candidates": 1, "regenerate": 2, "depth": 0, "children": 2,
  "generations": 1, "agents_max": 3, "attempt_seconds": 900, "wall_seconds": 3600, "novelty_limit": 2, "saturation": 0,
  "strategies": ["fresh", "feedback"], "syntax": true, "require_change": true, "self_split": false, "designer": false,
  "checks": {
    "0": ["/home/operator/host-checkout/bin/symblic check genome/{program}.sym", "python3 -B {kit}/bin/life-check.py genome-protected genome/{program}.sym"],
    "1": ["python3 -B {kit}/bin/life-check.py verify-line selfdev verify.txt proposal={proposal_id} program={program}"]
  },
  "final": [], "hidden": []
}


===== FILE: genome/assign-item.sym =====
program LIFE item assignment.
use profile=verified, context=none, determine=false, solve=false.
note Part of the reproducer. One queued item and the two child foci in, one side out. The tiniest rung suffices: a two-way closed choice. Code assigns at most four items per node slot this way (life_common.ASSIGN_PER_SLOT) and at most sixteen per division; the rest are split by the parity of sha256(item_id). Worst case 3 calls.
given focus_a: Text.
given focus_b: Text.
given item_text: Text.
ask side: one of {a: "the item fits the first focus better", b: "the item fits the second focus better"} "Which focus fits this item better? First: {focus_a}. Second: {focus_b}. Item: {item_text}" from item_text, focus_a, focus_b with effort=low, retries=2
let assignment = {side: side}.
return assignment.


===== FILE: genome/classify-command.sym =====
program LIFE command classifier.
use profile=verified, context=none, determine=false, solve=false.
note Worker of a command cell. One operator command in, one route out. Code reads the typed answer, keeps the original command text as the only authoritative instruction, and dispatches; the model only labels. Stop, freeze and cool are never routed here: the operator uses bin/life-ctl.py for them. Requests about digest or metabolism are routed to learning or heartbeat. The tick passes --by ollama:MODEL@NODE and --max-calls 12; worst case here is 6 + 2 + 3 = 11 calls.
given command_id: Text.
given command_text: Text.
define Organ as one of {
  learning: "research something from the internet, read sources, or learn about a topic",
  codebase: "fix a failing test or an error in the dashboard code; the command names a test id such as tests.test_x",
  database: "create a new table, column or index to store some kind of data",
  compute: "propose or measure a new way to compute or store data",
  selfdev: "improve how the organism's own genome programs ask their questions",
  immune: "review, audit, roll back or quarantine something",
  heartbeat: "report status, metrics or what the organism is doing",
  none: "the command fits no organ and must be shown to the operator"}.
ask organ: Organ "Route this operator command to exactly one organ. Command: {command_text}" from command_text with effort=medium, votes=3, retries=1
ask urgency: one of {low, normal, high} "How urgent is this command? Answer high only when the command says it is urgent or time-critical. Command: {command_text}" from command_text with effort=low, retries=1
ask restated: Text up to 18 words "Restate the command as one short imperative line naming what to do. This is display text only." from command_text with effort=low, retries=2
ensure len(restated) >= 10 and len(restated) <= 160 else retry because "the restated line is between ten and one hundred sixty characters".
let route = {command: command_id, organ: organ, urgency: urgency, restated: restated}.
return route.


===== FILE: genome/distill-lesson.sym =====
program LIFE lesson distiller.
use profile=verified, context=none, determine=false, solve=false.
note Worker of a digest cell, distill stage. One verified claim in, at most one lesson out. A lesson is web-derived data (taint web): code may quote it to a later worker as data, never as a statement, check, policy or command. Target none writes no lesson. Worst case 3 + 3 + 2 = 8 calls.
given claim: Text.
given quote: Text.
define Target as one of {
  genome: "the claim suggests a better way to ask a small language model a typed question, extract a quote, classify, or review",
  compute: "the claim suggests a faster or cheaper way to compute, compress, store or index data that could be measured",
  database: "the claim suggests a kind of data worth keeping in its own table",
  none: "the claim gives the organism nothing to change or measure"}.
ask target: Target "What could this claim change in a small self-improving computing system? Claim: {claim}" from claim, quote with effort=low, retries=2
ask lesson: Text up to 30 words "State the lesson as one plain sentence a maintainer could act on. If the target is none, write: no lesson." from claim, target with effort=low, retries=2
ensure len(lesson) >= 10 and len(lesson) <= 300 else retry because "a lesson is between ten and three hundred characters".
if target = "genome" then
  ask program: one of {classify-command, triage-error, extract-source, distill-lesson, propose-experiment, rank-experiment, review-patch, reproduce, assign-item} "Which one of these genome programs should change its instructions to apply the lesson? Lesson: {lesson}" from lesson with effort=low, retries=1
  let distilled = {target: target, lesson: lesson, program: program}.
else
  let distilled = {target: target, lesson: lesson, program: ""}.
end.
return distilled.


===== FILE: genome/extract-source.sym =====
program LIFE source fact extractor.
use profile=verified, context=none, determine=false, solve=false.
note Worker of a digest cell, extract stage. One fetched source text snapshot in, one quote-checked claim or an abstention out. The kernel checks that the quote occurs verbatim in the text (quotes(): whole words, NFC, runs of white space as one); code checks it again against the stored snapshot before a knowledge row is written. quote_verified means only that: the claim's truth is not established. Worst case 2 + 3 + 4 = 9 calls.
given source_id: Text.
given source_url: Text.
given source_text: Text.
ask supported: Bool "Does this text state at least one specific factual claim that can be quoted from it?" from source_text with effort=low, retries=1
if supported then
  ask claim: Text up to 40 words "State one specific factual claim this text supports, in your own words." from source_text with effort=medium, retries=2
  ensure len(claim) >= 20 and len(claim) <= 300 else retry because "a claim is between twenty and three hundred characters".
  ask quote: Text "Copy, word for word, the shortest span of the text that states the claim. Copy it exactly; never shorten, join or paraphrase." from source_text, claim with effort=low, retries=3
  ensure quotes(source_text, quote) else retry because "the quote must be copied exactly from the text".
  ensure len(quote) >= 12 and len(quote) <= 400 else retry because "the quote is between twelve and four hundred characters".
  let fact = {source: source_id, url: source_url, supported: true, claim: claim, quote: quote}.
else
  let fact = {source: source_id, url: source_url, supported: false, claim: "", quote: ""}.
end.
return fact.


===== FILE: genome/propose-experiment.sym =====
program LIFE experiment proposer.
use profile=verified, context=none, determine=false, solve=false.
note Worker of a compute cell, propose stage. One seed (a lesson or an operator command) and the operator's benchmark catalogue in, one typed experiment out. The model never writes a command: it picks a catalogue id and a parameter; code checks the id exists and the parameter matches that benchmark's param_rx, then measures candidate against the benchmark's baseline. Worst case 3 + 3 + 3 + 3 + 3 = 15 is cut to 12 by --max-calls, so retries are 1 here: 2 + 2 + 2 + 2 + 2 = 10.
given seed_text: Text.
given catalogue: Text.
ask benchmark_id: Text up to 6 words "Which benchmark id from this catalogue best tests the idea? Answer with the id only. Idea: {seed_text} Catalogue: {catalogue}" from seed_text, catalogue with effort=medium, retries=1
ensure len(benchmark_id) >= 2 and len(benchmark_id) <= 40 else retry because "a benchmark id is between two and forty characters".
ask param: Text up to 4 words "Which parameter value should the candidate run use for that benchmark? Answer with the value only. Idea: {seed_text} Catalogue: {catalogue}" from seed_text, catalogue, benchmark_id with effort=medium, retries=1
ensure len(param) >= 1 and len(param) <= 64 else retry because "a parameter is between one and sixty-four characters".
ask hypothesis: Text up to 40 words "State the hypothesis this measurement tests, comparing the candidate parameter with the benchmark's baseline." from seed_text, benchmark_id, param with effort=low, retries=1
ensure len(hypothesis) >= 20 and len(hypothesis) <= 300 else retry because "a hypothesis is between twenty and three hundred characters".
ask op: one of {lt: "the candidate's number must be below the threshold", le: "at or below", gt: "above", ge: "at or above"} "How must 100 times candidate divided by baseline compare with the threshold for the hypothesis to hold?" from hypothesis with effort=low, retries=1
ask threshold_pct: Int in 1..10000 "Give the threshold as a whole percentage of the baseline, for example 90 for ten percent lower." from hypothesis, op with effort=low, retries=1
let experiment = {benchmark_id: trim(benchmark_id), param: trim(param), hypothesis: hypothesis, op: op, threshold_pct: threshold_pct}.
return experiment.


===== FILE: genome/rank-experiment.sym =====
program LIFE experiment ranking.
use profile=verified, context=none, determine=false, solve=false.
note Worker of a compute cell, rank stage. Model labels only: code applies the rule. An experiment is measured only when feasible is true, risk is low and score is at least 60; nothing a model says waives the governor, the budget or the benchmark template's own timeout. Worst case 2 + 2 + 2 + 3 = 9 calls.
given hypothesis: Text.
given benchmark: Text.
ask feasible: Bool "Can this benchmark, as described, test this hypothesis in one run of at most fifteen minutes on one node? Hypothesis: {hypothesis} Benchmark: {benchmark}" from hypothesis, benchmark with effort=medium, retries=1
ask novelty: one of {none, small, large} "How different is this hypothesis from the benchmark's default baseline?" from hypothesis, benchmark with effort=low, retries=1
ask risk: one of {low, medium, high} "How likely is this run to overheat or overload a node or to fill its disk?" from benchmark with effort=low, retries=1
ask score: Int in 0..100 "Give one integer priority from 0 to 100 for spending cluster time on this experiment." from hypothesis, feasible, novelty, risk with effort=medium, retries=2
let ranking = {feasible: feasible, novelty: novelty, risk: risk, score: score}.
return ranking.


===== FILE: genome/reproduce.sym =====
program LIFE reproducer.
use profile=verified, context=none, determine=false, solve=false.
note The reproducer is the second agent of every cell. It never does the cell's task, and it does not decide whether the cell divides: code already decided that from the cell's own counters (LIFE.md section 9). It names how the parent's focus splits into two narrower foci; assign-item.sym then sorts the queued items between them and code commits the division only when both sides are nonempty. Worst case 3 + 3 = 6 calls.
given organ: Text.
given parent_focus: Text.
given sample_items: Text.
ask focus_a: Text up to 14 words "Cell of organ {organ} with focus: {parent_focus}. Its queued items include: {sample_items}. Name a first narrower focus covering part of these items, as one short imperative clause." from parent_focus, sample_items with effort=low, retries=2
ensure len(focus_a) >= 8 and len(focus_a) <= 120 else retry because "a focus is a clause between eight and one hundred twenty characters".
ask focus_b: Text up to 14 words "Name a second narrower focus, different from the first, covering the rest of these items, as one short imperative clause." from parent_focus, sample_items, focus_a with effort=low, retries=2
ensure len(focus_b) >= 8 and len(focus_b) <= 120 else retry because "a focus is a clause between eight and one hundred twenty characters".
ensure lower(trim(focus_a)) != lower(trim(focus_b)) else retry because "the two foci must differ".
ensure lower(trim(focus_a)) != lower(trim(parent_focus)) and lower(trim(focus_b)) != lower(trim(parent_focus)) else retry because "each child focus must be narrower than the parent's".
let plan = {focus_a: trim(focus_a), focus_b: trim(focus_b)}.
return plan.


===== FILE: genome/review-patch.sym =====
program LIFE adversarial review.
use profile=verified, context=none, determine=false, solve=false.
note Worker of an immune cell. A third role, distinct from the worker that wrote the change and from any reproducer. It reads the actual bounded diff (code supplies it; never a summary written by the author) and returns a verdict. Code calls this program only after its own checks passed for this exact diff, and a model accept alone never applies or adopts anything: the operator does, with bin/life-ctl.py. Worst case 3 + 3 = 6 calls.
given subject_id: Text.
given change_class: Text.
given path_class: Text.
given diff_text: Text.
given checks_passed: Bool.
define Verdict as one of {
  accept: "the change is safe, in scope, matches its stated class and touches nothing else",
  reject: "the change is unsafe, out of scope, or does not match its stated class",
  needs_work: "the change is close but one named fix is required before it is safe"}.
ensure checks_passed else fail because "a change whose code checks did not pass is never reviewed".
ask verdict: Verdict "Review this change adversarially. Stated class: {change_class}. Path class: {path_class}. Diff: {diff_text}" from change_class, path_class, diff_text with effort=medium, retries=2
ask reason: Text up to 30 words "State the single most important reason for your verdict." from diff_text, verdict with effort=low, retries=2
ensure len(reason) >= 10 and len(reason) <= 240 else retry because "the reason is between ten and two hundred forty characters".
let review = {subject: subject_id, verdict: verdict, reason: reason}.
return review.


===== FILE: genome/triage-error.sym =====
program LIFE error triage.
use profile=verified, context=none, determine=false, solve=false.
note Worker of a codebase cell, first stage. One failing test and its sanitized output in, one change class out. Code then decides by the patch's actual paths (life_common.path_class), and a protected path always wins over this label. unknown, or confident false, sends the finding to the operator and no patch is attempted. Worst case 3 + 3 = 6 calls.
given finding_id: Text.
given test_id: Text.
given finding_text: Text.
define ChangeClass as one of {
  test_only: "the test itself is wrong or outdated and only files under tests/ need to change",
  comment_or_doc: "only Markdown documentation under docs/ needs to change",
  local_fix: "a bounded fix inside one function body of the code under test, with no signature change",
  signature_change: "a change to a function or class signature or a public interface",
  unknown: "the class cannot be decided from this text alone"}.
ask change_class: ChangeClass "Classify the smallest change that would make the failing test {test_id} pass. Output of the failing test: {finding_text}" from test_id, finding_text with effort=medium, retries=2
ask confident: Bool "Is this classification well supported by the test output alone?" from finding_text, change_class with effort=low, retries=2
let triage = {finding: finding_id, change_class: change_class, confident: confident}.
return triage.


===== FILE: checks/canaries.txt =====
# LIFE required canaries. bin/life-tick.py runs every line every 12 ticks (argv split by shlex, no shell,
# cwd STATE, timeout 120 s). {release_dir} = the active release folder, {kit} = this kit. Any nonzero exit
# holds all new work and opens a canary_failed notice until a later round passes. Calls no model.
/home/operator/host-checkout/bin/symblic check {release_dir}/genome/classify-command.sym
/home/operator/host-checkout/bin/symblic check {release_dir}/genome/triage-error.sym
/home/operator/host-checkout/bin/symblic check {release_dir}/genome/extract-source.sym
/home/operator/host-checkout/bin/symblic check {release_dir}/genome/distill-lesson.sym
/home/operator/host-checkout/bin/symblic check {release_dir}/genome/propose-experiment.sym
/home/operator/host-checkout/bin/symblic check {release_dir}/genome/rank-experiment.sym
/home/operator/host-checkout/bin/symblic check {release_dir}/genome/review-patch.sym
/home/operator/host-checkout/bin/symblic check {release_dir}/genome/reproduce.sym
/home/operator/host-checkout/bin/symblic check {release_dir}/genome/assign-item.sym
/usr/bin/python3 -B {kit}/bin/life-check.py registry


===== FILE: checks/devcheck-gate.sh =====
#!/usr/bin/env bash
# LIFE codebase gate. bin/life-tick.py runs this on the host (timeout 900 s, its own process group) after a
# codebase run promoted its change into the cell's clone and before the patch is bundled for review.
#   devcheck-gate.sh CHECKOUT TEST_ID
# CHECKOUT must be a LIFE codebase clone (/home/operator/symblicos/projects/life-codebase-<8hex>), never the
# live checkout. TEST_ID is tests.<module>[.<Class>[.<test>]]. Steps, all in CHECKOUT:
#   1. the test module resolves to a file inside CHECKOUT (the scratch-copy trap: never the live tests/)
#   2. ./bin/devcheck            (uncommitted work vs HEAD: exactly the patch)
#   3. /usr/bin/python3 -s -B -m unittest TEST_ID -v    (system Python; no interpreter fallback)
# Exit 0 only when all three pass; otherwise the first failing step's exit code (2 = bad arguments).
# Calls no model and no agent. Never restarts, commits or pushes.
set -euo pipefail
checkout="${1:-}"
test_id="${2:-}"
[[ "$checkout" =~ ^/home/operator/symblicos/projects/life-codebase-[0-9a-f]{8}$ ]] || { echo "devcheck-gate: not a LIFE codebase clone: $checkout" >&2; exit 2; }
[[ "$test_id" =~ ^tests\.[A-Za-z0-9_]+(\.[A-Za-z0-9_]+){0,4}$ ]] || { echo "devcheck-gate: bad test id: $test_id" >&2; exit 2; }
[ -d "$checkout/.git" ] && [ ! -L "$checkout" ] || { echo "devcheck-gate: $checkout is not a git checkout" >&2; exit 2; }
cd "$checkout"
module="${test_id%%.[A-Z]*}"
where="$(/usr/bin/python3 -s -B -c 'import importlib, sys; sys.path.insert(0, "."); print(importlib.import_module(sys.argv[1]).__file__)' "$module")"
case "$where" in
  "$checkout"/*) echo "devcheck-gate: $module -> $where" ;;
  *) echo "devcheck-gate: $module resolved outside the clone: $where" >&2; exit 3 ;;
esac
./bin/devcheck
/usr/bin/python3 -s -B -m unittest "$test_id" -v
echo "devcheck-gate: PASS $test_id in $checkout"


===== FILE: spawn/PROTOCOL.md =====
# LIFE division protocol (reproduction, admitted and executed by code)

A cell divides only through a **division transaction** in the registry (`divisions` table of
`/home/operator/.local/state/life/life.sqlite3`). There is no spawn-record file queue: no model,
agent or worker can write a birth request, and nothing a worker writes is ever read as one. The
coordinator `bin/life-tick.py` is the only writer of the registry; the reproducer (the cell's second
agent) only names foci and sorts items, through two genome programs with kernel checks.

## 1. Eligibility (code; checked by `Tick.division_start` every armed tick)

A cell may start a division only when ALL hold:

| # | rule | value |
|---|------|-------|
| 1 | cell state | `active` |
| 2 | failures_in_a_row | `0` |
| 3 | depth | `< 10` (life_common.MAX_DEPTH); a child is born at parent depth + 1, so at most 10 |
| 4 | backlog_ticks | `>= 3` consecutive ticks with `queued >= divide_backlog` (organs.json: 12 for model organs, 6 for agent organs) |
| 5 | live cells of the organ (active, dividing, quarantined) | `+1 <= 3` (a division adds one net cell) |
| 6 | live cells of the organism | `+2 <= 16` |
| 7 | births today (UTC) | `+2 <= 8` |
| 8 | open divisions fleet-wide | `0` (at most one at a time) |
| 9 | last `divide_aborted` event of this cell | at least 21600 s ago |
| 10 | organ efficiency over the last two complete UTC days | `items_done / (program_runs + 3 x agent_runs) >= 0.2`, or fewer than 20 runs |
| 11 | a second node exists | a LIFE node other than the parent's, online, not hot, not held, with `< 4` live cells, and (agent organs) agy ready |
| 12 | the tick may start work | governor `work`, no hold reason, ARMED for this boot, not FROZEN, STOP absent |

Cells are scanned in `cell_id` order; the first eligible one starts. The parent's state becomes
`dividing`; new items for its organ stop going to it (dispatch gives items only to `active` cells).

## 2. Stages (each uses the parent node's one model slot for that tick)

1. **foci** — `genome/reproduce.sym` with `organ`, `parent_focus` and `sample_items` (the first 12
   queued items' labels, each cut to 120 characters, joined by ` | `, at most 1600 characters). Code
   re-checks both foci: 8..120 characters, different after lower-casing. `failed` aborts the
   division; `infra` retries at the next tick; a division older than 3 hours aborts.
2. **assign** — `genome/assign-item.sym` for at most the first 16 snapshot items still queued, at
   most 4 per tick (life_common.ASSIGN_PER_SLOT), each bounded to 225 s. A `failed` assignment
   falls back to parity (below); an `infra` one is retried next tick.
3. **commit** (no model) — every item still queued under the parent goes to child **a** or **b**:
   its assign-item answer if it has one, else `a` when `int(sha256(item_id), 16)` is even and `b`
   when odd. If either side is empty the division aborts. Otherwise, in ONE registry transaction:
   both children are inserted, the items move, the parent becomes `retired` with
   `end_reason='divided'`, the day's `births` grows by 2, and `cell_events` records `born` twice and
   `divided` once. Items the parent is still running (a live agent run, a benchmark job) stay with
   the parent's id and are collected normally.

## 3. Child identity

- `hex8 = sha256(parent_cell_id + "\n" + letter + "\n" + focus)[:8]`, `letter` = `a` or `b`.
- `cell_id = <organ>.<depth>.<hex8>` with `depth = parent depth + 1` (life_common.CELL_RX).
- Child **a** stays on the parent's node; child **b** goes to the node rule 11 picks (fewest cells
  of this organ, then fewest cells, then the order node-a, node-b, node-d, node-f, node-i).
- A `cell_id` that already exists aborts the division (`lineage key ... already exists`): the same
  parent with the same focus is never born twice, however the text around it varies.
- Each child copies the parent's ladder rungs (`cell_programs`) with an empty outcome window.
- Agent children get their own workspace `/home/operator/symblicos/projects/life-<organ>-<hex8>`
  (codebase: `git clone` of host-checkout's committed history; selfdev and database: `git clone`
  of the parent's workspace). A failed clone opens a `workspace` notice; that child's agent stages
  wait until the workspace exists.

## 4. Endings

| ending | trigger (code) | effect |
|--------|----------------|--------|
| apoptosis | `idle_ticks >= 288` (empty queue, nothing running) AND another active cell of the organ exists AND the cell has no live run | `retired`, `end_reason='idle'`; never the organ's last active cell |
| quarantine | `failures_in_a_row >= 8` | `quarantined`; its queued items return to the organ (active siblings take them); a notice; only `life-ctl.py release-cell` returns it |
| operator | `life-ctl.py retire CELL` | `retired`, `end_reason='owner'`; refused for the organ's last active cell without `--force` |

Retired and quarantined cells never divide. Cell and event rows are never deleted.

## 5. Worked example

`example/division.json` walks one division of the seed learning cell through the three stages with
the registry rows it produces.


===== FILE: spawn/example/division.json =====
{
  "note": "One division of the seed learning cell as the registry records it. Values are illustrative; ids follow spawn/PROTOCOL.md section 3.",
  "parent": {"cell_id": "learning.0.00000000", "organ": "learning", "depth": 0, "node": "node-d",
             "focus": "research the open questions and record new sources", "state": "dividing",
             "failures_in_a_row": 0, "backlog_ticks": 3, "queued": 14},
  "division": {"division_id": "3f1c0b6a9d2e4475", "stage": "foci",
               "snapshot": ["learning:<16hex of question 1>", "learning:<16hex of question 2>", "... 14 ids, highest priority then oldest first"]},
  "foci_call": {"program": "reproduce", "applicator": "ollama:llama3.2:1b@node-d",
                "inputs": {"organ": "learning", "parent_focus": "research the open questions and record new sources",
                           "sample_items": "ceramic foam porosity measurement methods | polymer fibre tensile tests | ..."},
                "returned": {"focus_a": "research porous ceramic structure questions",
                             "focus_b": "research polymer fibre mechanics questions"}},
  "assign_calls": {"program": "assign-item", "applicator": "ollama:qwen2.5:0.5b@node-d", "per_tick": 4, "max_items": 16,
                   "returned": {"learning:<16hex of question 1>": "a", "learning:<16hex of question 2>": "b"}},
  "commit": {"rule": "assign-item answer, else the parity of sha256(item_id)",
             "child_a": {"cell_id": "learning.1.<first 8 hex of sha256('learning.0.00000000\\na\\nresearch porous ceramic structure questions')>",
                         "node": "node-d", "items": 8},
             "child_b": {"cell_id": "learning.1.<first 8 hex of sha256('learning.0.00000000\\nb\\nresearch polymer fibre mechanics questions')>",
                         "node": "node-i", "items": 6},
             "parent_after": {"state": "retired", "end_reason": "divided"},
             "budget_births": 2,
             "events": ["born", "born", "divided"]}
}


===== FILE: db/life.sql =====
-- LIFE v2 registry: /home/operator/.local/state/life/life.sqlite3
-- The ONE authoritative store for control, identity, lineage, work items, runs, knowledge and metrics.
-- Exactly one writer: bin/life-tick.py (and bin/life-ctl.py for operator operations, under the same lock).
-- Lanes, models and agents never open this file. Applying this file twice is a no-op.
-- Times are integer UTC Unix seconds written by Python int(time.time()). Ids are text.
-- No credential, .env value or private-store value is ever written here.

CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- releases: immutable copies of genome/, organs/, policies/ under STATE/release/<n>/. One is active.
CREATE TABLE IF NOT EXISTS releases (
  release   INTEGER PRIMARY KEY CHECK (release >= 1),
  at        INTEGER NOT NULL,
  source    TEXT NOT NULL CHECK (source IN ('kit', 'adopt')),
  manifest  TEXT NOT NULL,                       -- JSON {relative path: sha256}
  active    INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0, 1)),
  note      TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS releases_one_active ON releases (active) WHERE active = 1;

-- cells: one row per cell ever born. Birth facts never change; state columns do (guarded by the tick).
CREATE TABLE IF NOT EXISTS cells (
  cell_id           TEXT PRIMARY KEY CHECK (length(cell_id) BETWEEN 12 AND 40),
  organ             TEXT NOT NULL CHECK (organ IN ('command', 'learning', 'digest', 'codebase', 'immune',
                                                   'selfdev', 'compute', 'database')),
  kind              TEXT NOT NULL CHECK (kind IN ('model', 'agent')),
  parent_id         TEXT REFERENCES cells (cell_id),
  depth             INTEGER NOT NULL CHECK (depth BETWEEN 0 AND 10),
  focus             TEXT NOT NULL CHECK (length(focus) BETWEEN 8 AND 120),
  node              TEXT NOT NULL CHECK (node IN ('node-a', 'node-b', 'node-d', 'node-f', 'node-i')),
  workspace         TEXT,                        -- agent cells only: /home/operator/symblicos/projects/life-<organ>-<8hex>
  state             TEXT NOT NULL CHECK (state IN ('active', 'dividing', 'quarantined', 'retired')),
  failures_in_a_row INTEGER NOT NULL DEFAULT 0 CHECK (failures_in_a_row >= 0),
  items_done        INTEGER NOT NULL DEFAULT 0 CHECK (items_done >= 0),
  idle_ticks        INTEGER NOT NULL DEFAULT 0 CHECK (idle_ticks >= 0),
  backlog_ticks     INTEGER NOT NULL DEFAULT 0 CHECK (backlog_ticks >= 0),
  last_served_at    INTEGER NOT NULL DEFAULT 0,
  born_at           INTEGER NOT NULL,
  ended_at          INTEGER,
  end_reason        TEXT CHECK (end_reason IS NULL OR end_reason IN ('divided', 'idle', 'owner')),
  release           INTEGER NOT NULL REFERENCES releases (release),
  CHECK ((parent_id IS NULL) = (depth = 0)),
  CHECK ((state = 'retired') = (ended_at IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS cells_organ_state ON cells (organ, state);
CREATE INDEX IF NOT EXISTS cells_node_state ON cells (node, state);

-- cell_events: append-only lifecycle log (birth, division, quarantine, release, retirement, rung moves).
CREATE TABLE IF NOT EXISTS cell_events (
  seq      INTEGER PRIMARY KEY AUTOINCREMENT,
  cell_id  TEXT NOT NULL REFERENCES cells (cell_id),
  at       INTEGER NOT NULL,
  event    TEXT NOT NULL CHECK (event IN ('born', 'divide_started', 'divided', 'divide_aborted', 'quarantined',
                                          'released', 'retired', 'rung_up', 'rung_down')),
  detail   TEXT NOT NULL DEFAULT '' CHECK (length(detail) <= 400)
);

-- cell_programs: the ladder rung a cell uses for each program, and its last ten outcomes.
CREATE TABLE IF NOT EXISTS cell_programs (
  cell_id  TEXT NOT NULL REFERENCES cells (cell_id),
  program  TEXT NOT NULL,
  rung     INTEGER NOT NULL DEFAULT 0 CHECK (rung BETWEEN 0 AND 4),
  window   TEXT NOT NULL DEFAULT '',             -- up to 10 letters, newest last: b(base) e(escalated) f(failed)
  PRIMARY KEY (cell_id, program)
);

-- items: one unit of work. An item belongs to one organ and, while queued or running, to one cell.
CREATE TABLE IF NOT EXISTS items (
  item_id     TEXT PRIMARY KEY CHECK (length(item_id) BETWEEN 18 AND 40),   -- <organ>:<16hex>
  organ       TEXT NOT NULL,
  kind        TEXT NOT NULL CHECK (kind IN ('command', 'question', 'source', 'finding', 'patch', 'proposal',
                                            'lesson', 'experiment', 'request')),
  cell_id     TEXT REFERENCES cells (cell_id),
  stage       TEXT NOT NULL,                     -- the organ's next stage (LIFE.md section 7)
  state       TEXT NOT NULL CHECK (state IN ('queued', 'running', 'done', 'abstained', 'failed', 'owner')),
  priority    INTEGER NOT NULL DEFAULT 1 CHECK (priority IN (0, 1, 2)),
  rung_extra  INTEGER NOT NULL DEFAULT 0 CHECK (rung_extra BETWEEN 0 AND 2),
  attempts    INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  dry_runs    INTEGER NOT NULL DEFAULT 0 CHECK (dry_runs >= 0),
  taint       TEXT NOT NULL CHECK (taint IN ('owner', 'web', 'code', 'model')),
  origin      TEXT NOT NULL DEFAULT '',          -- the item id or command id that produced it
  payload     TEXT NOT NULL CHECK (length(payload) <= 16384),   -- closed JSON per kind (LIFE.md section 6)
  outcome     TEXT NOT NULL DEFAULT '' CHECK (length(outcome) <= 400),
  created_at  INTEGER NOT NULL,
  updated_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS items_cell_queue ON items (cell_id, state, priority, created_at);
CREATE INDEX IF NOT EXISTS items_organ_state ON items (organ, state);

-- calls: every genome program run and research run (light model on a worker node through the fleet runner).
CREATE TABLE IF NOT EXISTS calls (
  call_id     TEXT PRIMARY KEY,
  cell_id     TEXT NOT NULL REFERENCES cells (cell_id),
  item_id     TEXT,
  program     TEXT NOT NULL,
  release     INTEGER NOT NULL,
  applicator  TEXT NOT NULL,                     -- ollama:<model>@<node>
  outcome     TEXT NOT NULL CHECK (outcome IN ('done', 'failed', 'infra')),
  model_calls INTEGER NOT NULL DEFAULT 0,
  started_at  INTEGER NOT NULL,
  ended_at    INTEGER NOT NULL,
  dir         TEXT NOT NULL,
  detail      TEXT NOT NULL DEFAULT '' CHECK (length(detail) <= 400)
);
CREATE INDEX IF NOT EXISTS calls_started ON calls (started_at);

-- runs: every autogen run LIFE submits (agent cells). request_id -> run_id is autogen-<sha256(request_id)[:24]>.
CREATE TABLE IF NOT EXISTS runs (
  request_id    TEXT PRIMARY KEY CHECK (length(request_id) <= 120),
  run_id        TEXT NOT NULL UNIQUE CHECK (length(run_id) = 32),
  cell_id       TEXT NOT NULL REFERENCES cells (cell_id),
  item_id       TEXT NOT NULL REFERENCES items (item_id),
  organ         TEXT NOT NULL,
  workspace     TEXT NOT NULL,
  node          TEXT NOT NULL,
  engine        TEXT NOT NULL CHECK (engine = 'agy'),
  policy_sha256 TEXT NOT NULL,
  state         TEXT NOT NULL CHECK (state IN ('submitting', 'live', 'completed', 'failed', 'stuck', 'cancelled',
                                               'unknown', 'not_submitted', 'collected')),
  submitted_at  INTEGER NOT NULL,
  ended_at      INTEGER,
  detail        TEXT NOT NULL DEFAULT '' CHECK (length(detail) <= 400)
);
CREATE INDEX IF NOT EXISTS runs_state ON runs (state);

-- divisions: one row per division transaction (LIFE.md section 9). At most one is open at a time.
CREATE TABLE IF NOT EXISTS divisions (
  division_id TEXT PRIMARY KEY,
  parent_id   TEXT NOT NULL REFERENCES cells (cell_id),
  stage       TEXT NOT NULL CHECK (stage IN ('foci', 'assign', 'committed', 'aborted')),
  focus_a     TEXT,
  focus_b     TEXT,
  snapshot    TEXT NOT NULL,                     -- JSON list of the queued item ids at division start
  assigned    TEXT NOT NULL DEFAULT '{}',        -- JSON {item_id: "a"|"b"} from assign-item.sym
  child_a     TEXT,
  child_b     TEXT,
  started_at  INTEGER NOT NULL,
  ended_at    INTEGER,
  reason      TEXT NOT NULL DEFAULT '' CHECK (length(reason) <= 400)
);
CREATE UNIQUE INDEX IF NOT EXISTS divisions_one_open ON divisions (parent_id) WHERE stage IN ('foci', 'assign');

-- commands: operator commands taken from STATE/inbox. The text stays here (STATE is private, mode 0700).
CREATE TABLE IF NOT EXISTS commands (
  command_id  TEXT PRIMARY KEY CHECK (length(command_id) = 16),  -- sha256(file name + "\n" + file bytes)[:16]
  file        TEXT NOT NULL,
  text        TEXT NOT NULL CHECK (length(text) BETWEEN 1 AND 4000),
  organ       TEXT CHECK (organ IS NULL OR organ IN ('learning', 'codebase', 'database', 'compute', 'selfdev',
                                                     'immune', 'heartbeat', 'none')),
  urgency     TEXT CHECK (urgency IS NULL OR urgency IN ('low', 'normal', 'high')),
  restated    TEXT,
  state       TEXT NOT NULL CHECK (state IN ('received', 'routed', 'dispatched', 'owner', 'done', 'failed')),
  created_at  INTEGER NOT NULL,
  updated_at  INTEGER NOT NULL
);

-- sources: the ONE source-dedup authority for every learning cell. key = symblic_autogen.items_key(url).
CREATE TABLE IF NOT EXISTS sources (
  source_key   TEXT PRIMARY KEY CHECK (length(source_key) <= 200),
  url          TEXT NOT NULL CHECK (url LIKE 'http://%' OR url LIKE 'https://%'),
  title        TEXT NOT NULL DEFAULT '' CHECK (length(title) <= 200),
  question_id  TEXT NOT NULL,
  found_at     INTEGER NOT NULL,
  text_path    TEXT,
  text_sha256  TEXT,
  fetch_state  TEXT NOT NULL DEFAULT 'pending' CHECK (fetch_state IN ('pending', 'fetched', 'empty', 'failed'))
);

-- knowledge: one quote-verified claim per row. quote_verified means only that the quote occurs in the
-- stored text snapshot; the claim's truth is NOT established (claim_status says so).
CREATE TABLE IF NOT EXISTS knowledge (
  fact_id        TEXT PRIMARY KEY CHECK (length(fact_id) = 16),    -- sha256(source_key + "\n" + quote)[:16]
  source_key     TEXT NOT NULL REFERENCES sources (source_key),
  text_sha256    TEXT NOT NULL,
  claim          TEXT NOT NULL CHECK (length(claim) BETWEEN 20 AND 300),
  quote          TEXT NOT NULL CHECK (length(quote) BETWEEN 12 AND 400),
  quote_verified INTEGER NOT NULL CHECK (quote_verified = 1),
  claim_status   TEXT NOT NULL DEFAULT 'unreviewed' CHECK (claim_status IN ('unreviewed', 'superseded')),
  applicator     TEXT NOT NULL,
  created_at     INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS knowledge_source ON knowledge (source_key);

-- patches: codebase bundles (STATE/bundles/patches/<patch_id>/). Never applied by LIFE; the operator runs life-ctl apply.
CREATE TABLE IF NOT EXISTS patches (
  patch_id      TEXT PRIMARY KEY CHECK (length(patch_id) = 16),  -- sha256(diff bytes)[:16]
  item_id       TEXT NOT NULL,                   -- the finding item
  base_commit   TEXT NOT NULL CHECK (length(base_commit) = 40),
  files         TEXT NOT NULL,                   -- JSON list of changed paths
  change_class  TEXT NOT NULL CHECK (change_class IN ('test_only', 'comment_or_doc', 'local_fix', 'signature_change')),
  path_class    TEXT NOT NULL CHECK (path_class IN ('tests', 'docs', 'restart_gated', 'live_static', 'mixed')),
  gate_rc       INTEGER NOT NULL,
  review        TEXT NOT NULL DEFAULT '' CHECK (review IN ('', 'accept', 'reject', 'needs_work')),
  review_reason TEXT NOT NULL DEFAULT '',
  state         TEXT NOT NULL CHECK (state IN ('bundled', 'ready', 'rejected', 'owner', 'applied', 'reverted')),
  created_at    INTEGER NOT NULL,
  updated_at    INTEGER NOT NULL
);

-- proposals: selfdev genome proposals (STATE/bundles/proposals/<proposal_id>/). Adopted only by life-ctl adopt.
CREATE TABLE IF NOT EXISTS proposals (
  proposal_id  TEXT PRIMARY KEY CHECK (length(proposal_id) = 16),
  item_id      TEXT NOT NULL,                    -- the lesson item
  program      TEXT NOT NULL,
  base_sha256  TEXT NOT NULL,
  new_sha256   TEXT NOT NULL,
  review       TEXT NOT NULL DEFAULT '' CHECK (review IN ('', 'accept', 'reject', 'needs_work')),
  review_reason TEXT NOT NULL DEFAULT '',
  state        TEXT NOT NULL CHECK (state IN ('bundled', 'ready', 'rejected', 'adopted')),
  created_at   INTEGER NOT NULL,
  updated_at   INTEGER NOT NULL
);

-- experiments and results: compute organ. Measurements run only operator-approved benchmark templates.
CREATE TABLE IF NOT EXISTS experiments (
  experiment_id TEXT PRIMARY KEY CHECK (length(experiment_id) = 16),  -- sha256(benchmark_id + "\n" + param)[:16]
  item_id       TEXT NOT NULL,
  benchmark_id  TEXT NOT NULL,
  param         TEXT NOT NULL CHECK (length(param) BETWEEN 1 AND 64),
  hypothesis    TEXT NOT NULL CHECK (length(hypothesis) BETWEEN 20 AND 300),
  op            TEXT NOT NULL CHECK (op IN ('<', '<=', '>', '>=')),
  threshold_pct INTEGER NOT NULL CHECK (threshold_pct BETWEEN 1 AND 10000),
  feasible      INTEGER CHECK (feasible IS NULL OR feasible IN (0, 1)),
  novelty       TEXT CHECK (novelty IS NULL OR novelty IN ('none', 'small', 'large')),
  risk          TEXT CHECK (risk IS NULL OR risk IN ('low', 'medium', 'high')),
  score         INTEGER CHECK (score IS NULL OR score BETWEEN 0 AND 100),
  state         TEXT NOT NULL CHECK (state IN ('proposed', 'ranked', 'ineligible', 'measured', 'failed')),
  created_at    INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS results (
  experiment_id  TEXT PRIMARY KEY REFERENCES experiments (experiment_id),
  node           TEXT NOT NULL,
  job_id         TEXT NOT NULL,
  candidate      TEXT NOT NULL,                  -- decimal text of the candidate measurement
  baseline       TEXT NOT NULL,                  -- decimal text of the baseline measurement
  unit           TEXT NOT NULL,
  ratio_pct      INTEGER NOT NULL,               -- floor(100 * candidate / baseline)
  passed         INTEGER NOT NULL CHECK (passed IN (0, 1)),
  ran_at         INTEGER NOT NULL
);

-- migrations LIFE applied to the organism database (organism.sqlite3), for the database organ.
CREATE TABLE IF NOT EXISTS migrations (
  migration_id TEXT PRIMARY KEY CHECK (length(migration_id) BETWEEN 6 AND 45),
  item_id      TEXT NOT NULL,
  sha256       TEXT NOT NULL,
  state        TEXT NOT NULL CHECK (state IN ('applied', 'refused')),
  detail       TEXT NOT NULL DEFAULT '' CHECK (length(detail) <= 400),
  at           INTEGER NOT NULL
);

-- samples and governor: metabolism (LIFE.md section 10).
CREATE TABLE IF NOT EXISTS samples (
  at      INTEGER NOT NULL,
  node    TEXT NOT NULL,
  online  INTEGER NOT NULL CHECK (online IN (0, 1)),
  cpu     REAL,                                   -- vitals.cpu: percent busy over the probe interval
  temp    REAL,                                   -- vitals.temp: degrees C
  mem_avail_mib INTEGER,
  PRIMARY KEY (at, node)
);
CREATE TABLE IF NOT EXISTS governor (
  id                 INTEGER PRIMARY KEY CHECK (id = 1),
  at                 INTEGER NOT NULL,
  state              TEXT NOT NULL CHECK (state IN ('work', 'rest', 'hold')),
  continuous_seconds INTEGER NOT NULL CHECK (continuous_seconds >= 0),
  quiet_seconds      INTEGER NOT NULL CHECK (quiet_seconds >= 0),
  hot                TEXT NOT NULL DEFAULT '[]',  -- JSON list of LIFE nodes currently hot
  reasons            TEXT NOT NULL DEFAULT '[]'   -- JSON list of hold reasons
);

-- node_holds: a node that answered infra failures is skipped until `until`.
CREATE TABLE IF NOT EXISTS node_holds (
  node    TEXT PRIMARY KEY,
  until   INTEGER NOT NULL,
  reason  TEXT NOT NULL DEFAULT ''
);

-- budget: per UTC day counters.
CREATE TABLE IF NOT EXISTS budget (
  day         TEXT PRIMARY KEY CHECK (length(day) = 10),   -- YYYY-MM-DD (UTC)
  program_runs INTEGER NOT NULL DEFAULT 0,
  model_calls  INTEGER NOT NULL DEFAULT 0,
  agent_runs   INTEGER NOT NULL DEFAULT 0,
  bench_jobs   INTEGER NOT NULL DEFAULT 0,
  births       INTEGER NOT NULL DEFAULT 0
);

-- metrics: per organ per UTC day.
CREATE TABLE IF NOT EXISTS metrics (
  organ          TEXT NOT NULL,
  day            TEXT NOT NULL,
  items_done     INTEGER NOT NULL DEFAULT 0,
  items_failed   INTEGER NOT NULL DEFAULT 0,
  items_abstained INTEGER NOT NULL DEFAULT 0,
  program_runs   INTEGER NOT NULL DEFAULT 0,
  agent_runs     INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (organ, day)
);

-- notices: what the operator must see. Deduplicated by (kind, subject) while open.
CREATE TABLE IF NOT EXISTS notices (
  notice_id TEXT PRIMARY KEY,                    -- sha256(kind + "\n" + subject + "\n" + at)[:12]
  kind      TEXT NOT NULL,
  subject   TEXT NOT NULL CHECK (length(subject) <= 120),
  text      TEXT NOT NULL CHECK (length(text) <= 600),
  state     TEXT NOT NULL CHECK (state IN ('open', 'acked')),
  at        INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS notices_open ON notices (kind, subject) WHERE state = 'open';


===== FILE: db/organism.sql =====
-- LIFE v2 organism database: /home/operator/.local/state/life/organism.sqlite3
-- The database the organism grows itself. It starts with only the migration ledger below. Every later
-- table arrives as an additive migration drafted by a database cell and applied by bin/life-tick.py after
-- code validation (LIFE.md section 12): only CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS and
-- ALTER TABLE ... ADD COLUMN, and every table name starts with org_. Nothing is ever dropped or deleted.
-- The control registry (life.sqlite3) is a separate file, so a migration can never touch control state.

CREATE TABLE IF NOT EXISTS schema_migrations (
  migration_id TEXT PRIMARY KEY CHECK (length(migration_id) BETWEEN 6 AND 45),
  sha256       TEXT NOT NULL CHECK (length(sha256) = 64),
  applied_at   INTEGER NOT NULL
);


===== FILE: units/life-tick.service =====
# LIFE coordinator tick. The operator installs this file and life-tick.timer into ~/.config/systemd/user/ (README
# step 4); nothing in the kit installs it. Code only: it calls light models on the worker nodes through the fleet runner
# (bin/symblic run --by ollama:MODEL@node-X) and starts bounded agy runs through bin/symblic-task.
[Unit]
Description=LIFE coordinator tick (code only; light models run on the worker nodes)
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/home/operator/.local/state/life
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/usr/bin/python3 -B /home/operator/host-checkout/docs/life/bin/life-tick.py
Nice=10
TimeoutStartSec=1500
SuccessExitStatus=3 5 6
Restart=no
MemoryMax=1G
TasksMax=128


===== FILE: units/life-tick.timer =====
# Runs the LIFE tick 10 minutes after boot, then 300 s after each tick ENDS (a long tick delays the next one;
# missed ticks never pile up). A reboot always comes back disarmed: ARMED holds the previous boot's id.
[Unit]
Description=LIFE coordinator tick every 300 s after the previous one ends

[Timer]
OnBootSec=10min
OnUnitInactiveSec=300
AccuracySec=30s
Persistent=false

[Install]
WantedBy=timers.target


===== FILE: benchmarks/benchmarks.example.json =====
{
  "version": 1,
  "benchmarks": [
    {
      "id": "zlib-level",
      "description": "Seconds for Python zlib to compress 64 MiB of generated mixed text at level N, median of five runs; no file is written.",
      "cmd": "python3 -c 'import zlib,time,statistics,sys; n=int(sys.argv[1]); data=(b\"life organism \"*400+bytes(range(256)))*17000; data=data[:67108864]; ts=[]\nfor _ in range(5):\n s=time.time(); zlib.compress(data,n); ts.append(time.time()-s)\nprint(\"LIFE_RESULT %.4f s\" % statistics.median(ts))' {{item}}",
      "param_rx": "^[1-9]$",
      "baseline": "6",
      "unit": "s",
      "timeout": 600
    },
    {
      "id": "sqlite-journal",
      "description": "Seconds to insert 200000 rows into a fresh SQLite file with journal mode N (DELETE, WAL, MEMORY, TRUNCATE), median of five runs, in a private temporary folder deleted afterwards.",
      "cmd": "python3 -c 'import sqlite3,tempfile,time,os,statistics,sys; m=sys.argv[1]; ts=[]\nfor _ in range(5):\n d=tempfile.mkdtemp(); c=sqlite3.connect(os.path.join(d,\"t.db\")); c.execute(\"PRAGMA journal_mode=\"+m); c.execute(\"CREATE TABLE t(a,b)\"); s=time.time(); c.executemany(\"INSERT INTO t VALUES(?,?)\",((i,str(i)) for i in range(200000))); c.commit(); ts.append(time.time()-s); c.close(); [os.remove(os.path.join(d,f)) for f in os.listdir(d)]; os.rmdir(d)\nprint(\"LIFE_RESULT %.4f s\" % statistics.median(ts))' {{item}}",
      "param_rx": "^(DELETE|WAL|MEMORY|TRUNCATE)$",
      "baseline": "DELETE",
      "unit": "s",
      "timeout": 600
    }
  ]
}


===== FILE: VALIDATE.sh =====
#!/usr/bin/env bash
# LIFE kit validator: STATIC checks only. No model, no agent, no network, no task start, no file written
# outside a private temporary folder (Python runs with -B, so no bytecode cache is written either).
#   1 inventory   every required file exists; entry points are executable
#   2 genome      bin/symblic check on each of the nine programs (exit 0 and "ok")
#   3 organs      organs/organs.json passes life_common.organs_problems (closed schema)
#   4 templates   each raw agent template (organs/<organ>.lines.txt, placeholders unfilled) lints with ZERO
#                 findings and no root; each renders with organs/fixtures.json, lints with ZERO findings
#                 (symblic_autogen.lint), and its policy passes symblic_autogen.normalize and equals the
#                 fixed LIFE agent policy (life_common.agent_policy_problems); policy_flags() emits it whole
#   5 syntax      bash -n on every shell file; ast.parse on every Python file
#   6 databases   db/life.sql and db/organism.sql applied twice in memory; required tables; CHECK
#                 constraints refuse a depth-11 cell, an unknown organ and a second active release
#   7 canaries    every canary line names an existing program or script
#   8 benchmarks  benchmarks/benchmarks.example.json passes the tick's benchmark rules
#   9 embedding   every "### <path>" block in LIFE.md equals that file byte for byte
#  10 contract    life_common.contract_problems() is empty (the platform facts LIFE relies on hold)
# It prints PASS/FAIL per check and ends with STATIC PASS or SOME FAILED. Exit 0 only on STATIC PASS.
# STATIC PASS is not an admission test: the coordinator's behaviour under concurrency, crashes and STOP is
# not exercised here (LIFE.md section 16, GAP 8).
set -u
shopt -s nullglob
KIT="/home/operator/host-checkout/docs/life"
REPO="/home/operator/host-checkout"
PY="/usr/bin/python3 -B -I"
fail=0
pass() { printf 'PASS  %-10s %s\n' "$1" "$2"; }
bad()  { printf 'FAIL  %-10s %s\n' "$1" "$2"; fail=1; }

echo "== 1 inventory =="
required=(BRIEF.md README.md LIFE.md VALIDATE.sh
  bin/life_common.py bin/life-tick.py bin/life-ctl.py bin/life-status.py bin/life-check.py bin/life-seed.sh
  checks/devcheck-gate.sh checks/canaries.txt db/life.sql db/organism.sql
  organs/organs.json organs/fixtures.json organs/codebase.lines.txt organs/selfdev.lines.txt organs/database.lines.txt
  policies/codebase.json policies/selfdev.json policies/database.json
  spawn/PROTOCOL.md spawn/example/division.json units/life-tick.service units/life-tick.timer
  benchmarks/benchmarks.example.json)
for p in classify-command triage-error extract-source distill-lesson propose-experiment rank-experiment review-patch reproduce assign-item; do
  required+=("genome/$p.sym"); done
for f in "${required[@]}"; do
  if [ -f "$KIT/$f" ] && [ ! -L "$KIT/$f" ]; then :; else bad inventory "$f missing"; fi; done
for f in VALIDATE.sh bin/life-tick.py bin/life-ctl.py bin/life-status.py bin/life-check.py bin/life-seed.sh checks/devcheck-gate.sh; do
  [ -x "$KIT/$f" ] || bad inventory "$f is not executable"; done
[ "$fail" = 0 ] && pass inventory "${#required[@]} files"

echo "== 2 genome (bin/symblic check, no model) =="
for f in "$KIT"/genome/*.sym; do
  out="$("$REPO/bin/symblic" check "$f" 2>&1)"; rc=$?
  if [ "$rc" = 0 ] && printf '%s' "$out" | tail -1 | grep -q ': ok'; then pass check "$(basename "$f")"; else bad check "$(basename "$f")"; fi
done

echo "== 3-4 organs and templates (lint zero findings, normalize, fixed policy) =="
if $PY - <<'PYEOF'
import json, sys
sys.path.insert(0, '/home/operator/host-checkout'); sys.path.insert(0, '/home/operator/host-checkout/docs/life/bin')
import life_common as L
ok = True
problems = L.organs_problems(json.load(open(L.KIT + '/organs/organs.json', encoding='utf-8'), object_pairs_hook=L._no_dup_keys))
print(('PASS  organs     ' if not problems else 'FAIL  organs     ') + ('organs.json' if not problems else '; '.join(problems)))
ok &= not problems
fixtures = json.load(open(L.KIT + '/organs/fixtures.json', encoding='utf-8'))
import symblic_autogen as A
for organ in L.AGENT_ORGANS:
    raw = A.statements(open(f'{L.KIT}/organs/{organ}.lines.txt', encoding='utf-8').read())
    raw_findings = A.lint(raw)                  # the raw template, no root: it must name its absolute folder itself
    print(('PASS  raw lint   ' if not raw_findings else 'FAIL  raw lint   ') + f'{organ}: ' +
          ('0 lint findings without a root' if not raw_findings else '; '.join(f'{lv} line {n}: {m}' for lv, n, m in raw_findings)))
    ok &= not raw_findings
    try:
        lines, policy, sha = L.render_run(L.KIT, organ, fixtures[organ])
        flags = L.policy_flags(policy)
        print(f'PASS  template   {organ}: {len(lines)} statements, 0 lint findings, policy sha256 {sha[:12]}, {len(flags)} flags')
    except Exception as exc:
        print(f'FAIL  template   {organ}: {exc}'); ok = False
sys.exit(0 if ok else 1)
PYEOF
then :; else fail=1; fi

echo "== 5 syntax =="
for f in "$KIT"/bin/*.sh "$KIT"/checks/*.sh "$KIT/VALIDATE.sh"; do
  if bash -n "$f" 2>/dev/null; then pass "bash -n" "${f#$KIT/}"; else bad "bash -n" "${f#$KIT/}"; fi; done
for f in "$KIT"/bin/*.py; do
  if $PY -c 'import ast,sys; ast.parse(open(sys.argv[1],encoding="utf-8").read(), sys.argv[1])' "$f" 2>/dev/null; then
    pass ast "${f#$KIT/}"; else bad ast "${f#$KIT/}"; fi; done
for f in "$KIT"/organs/*.json "$KIT"/policies/*.json "$KIT"/spawn/example/*.json "$KIT"/benchmarks/*.json; do
  if $PY -c 'import json,sys; json.load(open(sys.argv[1],encoding="utf-8"))' "$f" 2>/dev/null; then :; else bad json "${f#$KIT/}"; fi; done

echo "== 6 databases (in memory, applied twice) =="
if $PY - "$KIT" <<'PYEOF'
import sqlite3, sys
kit = sys.argv[1]
c = sqlite3.connect(':memory:'); c.execute('PRAGMA foreign_keys=ON')
for _ in (1, 2):
    c.executescript(open(kit + '/db/life.sql', encoding='utf-8').read())
need = {'meta','releases','cells','cell_events','cell_programs','items','calls','runs','divisions','commands','sources',
        'knowledge','patches','proposals','experiments','results','migrations','samples','governor','node_holds','budget',
        'metrics','notices'}
have = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
assert need <= have, need - have
c.execute("INSERT INTO releases (release, at, source, manifest, active) VALUES (1, 0, 'kit', '{}', 1)")
def refused(sql):
    try:
        c.execute(sql); return False
    except sqlite3.IntegrityError:
        return True
assert refused("INSERT INTO releases (release, at, source, manifest, active) VALUES (2, 0, 'kit', '{}', 1)")
assert refused("INSERT INTO cells (cell_id, organ, kind, parent_id, depth, focus, node, state, born_at, release) VALUES ('learning.11.00000000', 'learning', 'model', NULL, 11, 'research something', 'node-d', 'active', 0, 1)")
assert refused("INSERT INTO cells (cell_id, organ, kind, parent_id, depth, focus, node, state, born_at, release) VALUES ('brain.0.00000000xx', 'brain', 'model', NULL, 0, 'think about things', 'node-d', 'active', 0, 1)")
c.execute("INSERT INTO cells (cell_id, organ, kind, parent_id, depth, focus, node, state, born_at, release) VALUES ('learning.0.00000000', 'learning', 'model', NULL, 0, 'research the open questions', 'node-d', 'active', 0, 1)")
o = sqlite3.connect(':memory:')
for _ in (1, 2):
    o.executescript(open(kit + '/db/organism.sql', encoding='utf-8').read())
assert {r[0] for r in o.execute("SELECT name FROM sqlite_master WHERE type='table'")} == {'schema_migrations'}
PYEOF
then pass sqlite "life.sql, organism.sql"; else bad sqlite "life.sql or organism.sql"; fi

echo "== 7 canaries =="
while IFS= read -r line; do
  case "$line" in ''|'#'*) continue ;; esac
  target="$(printf '%s' "$line" | awk '{print $NF}' | sed "s#{release_dir}#$KIT#; s#{kit}#$KIT#")"
  case "$line" in *"life-check.py registry"*) target="$KIT/bin/life-check.py" ;; esac
  [ -f "$target" ] || bad canary "$line"
done < "$KIT/checks/canaries.txt"
pass canaries "checks/canaries.txt"

echo "== 8 benchmarks example =="
if $PY - "$KIT/benchmarks/benchmarks.example.json" <<'PYEOF'
import json, re, sys
d = json.load(open(sys.argv[1], encoding='utf-8'))
assert d['version'] == 1 and d['benchmarks']
for b in d['benchmarks']:
    assert set(b) == {'id', 'description', 'cmd', 'param_rx', 'baseline', 'unit', 'timeout'}, b.get('id')
    assert re.fullmatch(r'[a-z0-9-]{2,40}', b['id']) and '{{item}}' in b['cmd'] and len(b['cmd']) <= 2000
    assert re.fullmatch(b['param_rx'], b['baseline']) and re.fullmatch(r'[A-Za-z/%]{1,12}', b['unit'])
    assert type(b['timeout']) is int and 30 <= b['timeout'] <= 900
PYEOF
then pass bench "benchmarks.example.json"; else bad bench "benchmarks.example.json"; fi

echo "== 9 LIFE.md embeds every file verbatim =="
if $PY - "$KIT" <<'PYEOF'
import os, re, sys
kit = sys.argv[1]
text = open(kit + '/LIFE.md', encoding='utf-8').read()
blocks = re.findall(r'^### (\S+)\n\n(`{3,4})[a-z]*\n(.*?)\n\2$', text, re.M | re.S)
seen, bad = set(), []
for path, _fence, body in blocks:
    seen.add(path)
    try:
        if open(os.path.join(kit, path), encoding='utf-8').read() != body + '\n':
            bad.append(path + ' differs')
    except OSError:
        bad.append(path + ' missing')
want = set()
for root, _d, files in os.walk(kit):
    if '/workshop' in root or '__pycache__' in root:
        continue
    for f in files:
        rel = os.path.relpath(os.path.join(root, f), kit)
        if rel not in ('LIFE.md', 'BRIEF.md'):
            want.add(rel)
bad += [p + ' not embedded' for p in sorted(want - seen)]
print('\n'.join(bad))
sys.exit(1 if bad else 0)
PYEOF
then pass embed "LIFE.md appendices"; else bad embed "LIFE.md appendices"; fi

echo "== 10 platform contract =="
if out="$($PY -c 'import sys; sys.path.insert(0, "/home/operator/host-checkout/docs/life/bin"); import life_common as L; p = L.contract_problems(); print("; ".join(p)); sys.exit(1 if p else 0)')"; then
  pass contract "platform facts hold"; else bad contract "$out"; fi

echo
if [ "$fail" = 0 ]; then echo "STATIC PASS"; else echo "SOME FAILED"; fi
exit "$fail"


===== FILE: bin/life-seed.sh =====
#!/usr/bin/env bash
# LIFE seed (the operator runs this ONCE, on the host). It asks for START, then runs life-ctl.py seed, which:
# runs VALIDATE.sh, creates /home/operator/.local/state/life (mode 0700) with the registry, the organism
# database and release 1, creates the three agent workspaces under /home/operator/symblicos/projects
# (life-codebase-00000000 = a clone of host-checkout's committed history; life-selfdev-00000000 and
# life-database-00000000 = symblic-task workspaces), and registers the 8 seed cells. It starts NO run and
# calls NO model: nothing happens until the operator installs the timer and runs life-ctl.py arm.
# Seeding an already seeded organism changes nothing and is never a recovery step.
set -euo pipefail
KIT="/home/operator/host-checkout/docs/life"
echo "LIFE seed: creates /home/operator/.local/state/life and three workspaces; starts nothing."
read -r -p "Type START to continue: " answer
[ "$answer" = "START" ] || { echo "aborted"; exit 1; }
exec /usr/bin/python3 -B "$KIT/bin/life-ctl.py" seed --confirm START


===== FILE: bin/life-check.py =====
#!/usr/bin/env python3
"""LIFE acceptance checks that autogen runs as policy checks (and the canaries run), all code, no model.

    life-check.py verify-line ORGAN FILE EXPECTED_WORDS...   verify.txt holds exactly the expected line
    life-check.py migration FILE SNAPSHOT                    an additive org_ migration (life_common rules)
    life-check.py genome-protected FILE                      only ask instructions/notes differ from HEAD:FILE
    life-check.py registry                                   PRAGMA integrity_check and quick_check of the registry

Exit 0 pass, 1 fail (the reason on stderr), 2 usage. Autogen runs these in its staging checkout on the host
(cwd = the checkout), with CHECK_TIMEOUT 120 s (symblicos/autogen.py). Nothing here writes a file.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import life_common as L  # noqa: E402


def fail(msg):
    print(f'life-check: {msg}', file=sys.stderr)
    return 1


def read(path, limit=65536):
    if os.path.islink(path) or not os.path.isfile(path):
        raise OSError(f'{path} is missing or not a regular file')
    with open(path, encoding='utf-8') as handle:
        text = handle.read(limit + 1)
    if len(text) > limit:
        raise OSError(f'{path} is larger than {limit} characters')
    return text


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    cmd, args = argv[0], argv[1:]
    try:
        if cmd == 'verify-line' and len(args) >= 3 and args[0] in L.VERIFY_LINES:
            problems = L.verify_line_problems(args[0], read(args[1], 400), ' '.join(args[2:]))
        elif cmd == 'migration' and len(args) == 2:
            snapshot = read(args[1], 262144) if os.path.exists(args[1]) else ''
            problems = L.migration_problems(read(args[0], 16384), snapshot)
        elif cmd == 'genome-protected' and len(args) == 1:
            if not args[0].startswith('genome/') or '..' in args[0]:
                return fail('the file must be genome/<program>.sym')
            old = subprocess.run(['git', 'show', f'HEAD:{args[0]}'], capture_output=True, text=True, timeout=30)
            if old.returncode != 0:
                return fail(f'git show HEAD:{args[0]} failed')
            problems = L.genome_protected_problems(old.stdout, read(args[0]))
        elif cmd == 'registry' and not args:
            conn = L.connect(readonly=True)
            rows = [r[0] for r in conn.execute('PRAGMA integrity_check')]
            problems = [] if rows == ['ok'] else ['integrity_check: ' + '; '.join(rows)[:300]]
        else:
            print(__doc__)
            return 2
    except (OSError, ValueError, UnicodeDecodeError, subprocess.SubprocessError) as exc:
        return fail(str(exc)[:300])
    except Exception as exc:  # noqa: BLE001 - any other fault is a failed check, never a pass
        return fail(f'{type(exc).__name__}: {str(exc)[:300]}')
    if problems:
        return fail('; '.join(problems)[:600])
    print('life-check: pass')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))


===== FILE: bin/life-status.py =====
#!/usr/bin/env python3
"""LIFE status for the operator. Read-only: opens the registry with mode=ro, writes nothing, calls nothing.

    life-status.py           control, governor, budgets, live cells, live runs, open notices
    life-status.py --json    the same as one JSON object

Exit 0 when the registry was read; 1 UNKNOWN (not seeded or unreadable: the state cannot be established).
Every string from the registry is printed through life_common.one_line (control characters removed).
"""
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import life_common as L  # noqa: E402


def age(t):
    if not t:
        return 'never'
    s = max(0, L.now() - int(t))
    return f'{s}s ago' if s < 120 else f'{s // 60}m ago' if s < 7200 else f'{s // 3600}h ago'


def main(argv):
    try:
        conn = L.connect(readonly=True)
        gov = conn.execute('SELECT * FROM governor WHERE id=1').fetchone()
        rel = conn.execute('SELECT release FROM releases WHERE active=1').fetchone()
        budget = conn.execute('SELECT * FROM budget WHERE day=?', (L.utc_day(),)).fetchone()
        cells = conn.execute("SELECT * FROM cells WHERE state != 'retired' ORDER BY organ, cell_id").fetchall()
        queued = {r[0]: r[1] for r in conn.execute("SELECT cell_id, COUNT(*) FROM items WHERE state='queued' GROUP BY cell_id")}
        runs = conn.execute("SELECT * FROM runs WHERE state IN ('submitting','live','unknown') ORDER BY submitted_at").fetchall()
        notes = conn.execute("SELECT * FROM notices WHERE state='open' ORDER BY at").fetchall()
        unassigned = conn.execute("SELECT COUNT(*) FROM items WHERE state='queued' AND cell_id IS NULL").fetchone()[0]
        last_tick = conn.execute("SELECT value FROM meta WHERE key='tick_no'").fetchone()
    except (sqlite3.Error, OSError) as exc:
        print(f'LIFE status UNKNOWN: {L.one_line(str(exc), 200)}')
        return 1
    ctl = L.control_state()
    data = {'at': L.now(), 'control': ctl, 'release': rel[0] if rel else None, 'tick_no': last_tick[0] if last_tick else None,
            'governor': dict(gov) if gov else None, 'budget': dict(budget) if budget else None,
            'cells': [dict(c, queued=queued.get(c['cell_id'], 0)) for c in cells], 'unassigned': unassigned,
            'runs': [dict(r) for r in runs], 'notices': [dict(n) for n in notices_safe(notes)]}
    if '--json' in argv:
        print(json.dumps(data, indent=1, sort_keys=True, default=str))
        return 0
    stopped = 'STOP' if ctl['stop'] else 'frozen' if ctl['freeze'] else 'armed' if ctl['armed'] else 'disarmed (observe only)'
    print(f'LIFE {time.strftime("%Y-%m-%d %H:%M:%S")}  release {data["release"]}  tick {data["tick_no"]}  {stopped}'
          f'  selfdev {"armed" if ctl["selfdev"] else "off"}')
    if gov:
        print(f'  governor {gov["state"]} (sampled {age(gov["at"])}): {gov["continuous_seconds"]}s loaded, '
              f'{gov["quiet_seconds"]}s quiet, hot {L.one_line(gov["hot"], 80)}, reasons {L.one_line(gov["reasons"], 200)}')
    if budget:
        print(f'  today: program runs {budget["program_runs"]}/{L.PROGRAM_RUNS_PER_DAY}, model calls {budget["model_calls"]}, '
              f'agent runs {budget["agent_runs"]}/{L.AGENT_RUNS_PER_DAY}, bench jobs {budget["bench_jobs"]}/{L.BENCH_JOBS_PER_DAY}, '
              f'births {budget["births"]}/{L.BIRTHS_PER_DAY}')
    print(f'  cells ({len(cells)} live, {unassigned} unassigned item(s)):')
    for c in data['cells']:
        print(f'    {c["cell_id"]:24} {c["state"]:11} {c["node"]:7} queued {c["queued"]:4} done {c["items_done"]:5} '
              f'fail-run {c["failures_in_a_row"]}  {L.one_line(c["focus"], 60)}')
    for r in data['runs']:
        print(f'  run {r["run_id"]} {r["state"]} {r["organ"]} on {r["node"]} submitted {age(r["submitted_at"])}')
    for n in data['notices']:
        print(f'  notice {n["notice_id"]} {n["kind"]}: {n["subject"]}: {n["text"]}')
    return 0


def notices_safe(rows):
    for r in rows:
        yield {'notice_id': r['notice_id'], 'kind': L.one_line(r['kind'], 40), 'subject': L.one_line(r['subject'], 120),
               'text': L.one_line(r['text'], 300), 'at': r['at']}


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))


===== FILE: bin/life_common.py =====
"""LIFE v2 shared contract: paths, limits, identities, validators and the loopback adapter.

Imported by bin/life-tick.py, bin/life-ctl.py, bin/life-status.py and bin/life-check.py. Inert on import:
importing this module reads nothing, writes nothing and starts nothing. Every number here is the single
definition LIFE.md section 13 tabulates; change it here and in LIFE.md together (VALIDATE.sh compares
the embedded copy). Paths are fixed: LIFE v1/v2 supports only these canonical locations, and no environment
variable can move them (a relocated kit would split control between two roots).
"""
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import time
import unicodedata
import urllib.error
import urllib.request

# ------------------------------------------------------------------------------------------- paths
REPO = '/home/operator/host-checkout'
KIT = REPO + '/docs/life'
STATE = '/home/operator/.local/state/life'
PROJECTS = '/home/operator/symblicos/projects'
TASK = REPO + '/bin/symblic-task'
SYMBLIC = REPO + '/bin/symblic'
RESEARCH = REPO + '/bin/local-research'
REPO_PY = REPO + '/.venv/bin/python'          # has bs4/pypdf for local_research.read_page
SYS_PY = '/usr/bin/python3'
DASH = 'http://127.0.0.1:8080'                  # loopback only; never a worker node tunnel

REGISTRY = STATE + '/life.sqlite3'
ORGANISM = STATE + '/organism.sqlite3'
CONTROL = STATE + '/control'
STOP_FILE = CONTROL + '/STOP'
FREEZE_FILE = CONTROL + '/FREEZE'
ARMED_FILE = CONTROL + '/ARMED'
SELFDEV_FILE = CONTROL + '/SELFDEV_ARMED'
WATCH_FILE = CONTROL + '/watch.txt'
BENCH_FILE = CONTROL + '/benchmarks.json'
INBOX = STATE + '/inbox'
INBOX_DONE = STATE + '/inbox-done'
INBOX_REFUSED = STATE + '/inbox-refused'
RELEASES = STATE + '/release'
CALLS = STATE + '/calls'
BUNDLES = STATE + '/bundles'
TEXTS = STATE + '/text'
RUNS_DIR = STATE + '/runs'
LOGS = STATE + '/logs'
BACKUPS = STATE + '/backups'
APPLIED = STATE + '/applied'
OWNER = STATE + '/operator'
LOCK_FILE = STATE + '/tick.lock'
STATE_DIRS = (STATE, CONTROL, INBOX, INBOX_DONE, INBOX_REFUSED, RELEASES, CALLS, BUNDLES, BUNDLES + '/patches',
              BUNDLES + '/proposals', BUNDLES + '/migrations', TEXTS, RUNS_DIR, LOGS, BACKUPS, APPLIED, OWNER)

# ------------------------------------------------------------------------------------------- organism
ORGANS = ('command', 'learning', 'digest', 'codebase', 'immune', 'selfdev', 'compute', 'database')
AGENT_ORGANS = ('codebase', 'selfdev', 'database')
MODEL_ORGANS = tuple(o for o in ORGANS if o not in AGENT_ORGANS)
NODES = ('node-a', 'node-b', 'node-d', 'node-f', 'node-i')   # node-c/e unlisted in BRIEF; node-h = protected service stack
PROGRAMS = ('classify-command', 'triage-error', 'extract-source', 'distill-lesson', 'propose-experiment',
            'rank-experiment', 'review-patch', 'reproduce', 'assign-item')
ROUTES = ('learning', 'codebase', 'database', 'compute', 'selfdev', 'immune', 'heartbeat', 'none')
STAGES = {                                       # each organ's item stage machine (LIFE.md section 7)
    'command': ('classify',),
    'learning': ('research',),
    'digest': ('fetch', 'extract', 'distill'),
    'codebase': ('triage', 'patch', 'gate'),
    'immune': ('review',),
    'selfdev': ('draft', 'gate'),
    'compute': ('propose', 'rank', 'bench'),
    'database': ('draft', 'apply'),
}
MODEL_MIB = {'qwen2.5:0.5b': 400, 'llama3.2:1b': 1300, 'gemma3:1b': 900, 'qwen2.5-coder:3b': 1900,
             'qwen3:4b-instruct': 2600}
ENGINE = 'agy'                                   # the only CLI engine LIFE v2 starts (strategies fresh,feedback)

# ------------------------------------------------------------------------------------------- limits
TICK_SECONDS = 300            # timer: OnUnitInactiveSec=300 (from the end of the previous tick)
TICK_DEADLINE = 1200          # a tick stops starting work after this many seconds; systemd kills at 1500
CALL_TIMEOUT = 900            # one bin/symblic run or bin/local-research process, seconds (process group killed)
CALL_MAX_MODEL_CALLS = 12     # --max-calls for every genome program run
OLLAMA_LIMITS = {'num_predict': 1024, 'timeout_seconds': 600}
ASSIGN_PER_SLOT = 4           # assign-item.sym runs one division may make in one node slot
LIFE_MAX_CELLS = 16           # cells in state active, dividing or quarantined, all organs
ORGAN_CELL_CAP = 3            # such cells per organ
NODE_CELL_CAP = 4             # such cells per node
MAX_DEPTH = 10                # a child's depth is at most 10; a parent may divide only at depth < 10
DIVIDE_SUSTAIN = 3            # consecutive ticks with backlog >= the organ's divide_backlog
DIVISION_COOLDOWN = 21600     # seconds after an aborted division before that parent may try again
DIVISIONS_OPEN_MAX = 1        # division transactions open at once, fleet-wide
APOPTOSIS_IDLE_TICKS = 288    # consecutive ticks with an empty queue (about a day at 300 s)
QUARANTINE_FAILURES = 8       # consecutive failed items
NODE_HOLD_SECONDS = 300       # a node that answered an infra failure is skipped this long
AGENT_RUNS_LIVE_MAX = 2       # LIFE autogen runs queued or active at once, fleet-wide (1 per cell)
AGENT_RUN_KILL_SECONDS = 4500 # the tick cancels a LIFE run still live this long after submission
PROGRAM_RUNS_PER_DAY = 1200   # UTC day budgets; a spent budget holds that class of work until 00:00 UTC
AGENT_RUNS_PER_DAY = 12
BENCH_JOBS_PER_DAY = 12
BIRTHS_PER_DAY = 8
QUESTION_DRY_LIMIT = 3        # research runs in a row with zero new sources before a question is exhausted
QUESTION_SOURCE_LIMIT = 9     # new sources per question before it is done
NEW_SOURCES_PER_RUN = 3       # at most this many new sources are recorded from one research run
RESEARCH_TOOLS = 8            # bin/local-research --tools (searches plus page reads per run)
SOURCE_TEXT_CHARS = 6000      # text kept per source (local_research.read_page chars)
SOURCE_TEXT_MIN = 200         # shorter text is EMPTY (abstained)
DIFF_REVIEW_CHARS = 6000      # a patch diff longer than this is not model-reviewed: it goes to the operator
EFFICIENCY_FLOOR = 0.2        # an organ below this over two complete UTC days may not divide
EFFICIENCY_MIN_RUNS = 20
STATE_MAX_BYTES = 10 * 1024 ** 3
DISK_FREE_MIN = 5 * 1024 ** 3
LOG_ROTATE_BYTES = 5 * 1024 ** 2
CANARY_EVERY_TICKS = 12
FINDINGS_EVERY_SECONDS = 6 * 3600
BACKUP_KEEP = 7
# metabolism (LIFE.md section 10)
SAMPLE_MAX_AGE = 180          # /api/cluster/status `ts` older than this is stale telemetry -> hold
LOADED_CPU = 50.0             # vitals.cpu (% busy) at or above: the node is loaded in this sample
FLEET_LOADED_NODES = 3        # at least this many online LIFE nodes loaded: the fleet is loaded
WORK_WINDOW = 3000            # loaded seconds before the fleet must rest
REST_SECONDS = 600            # consecutive quiet seconds that end a rest and reset the window
HOT_C, COOL_C = 85.0, 75.0    # same thresholds as symblic_apply.THERMAL_HOT/THERMAL_COOL
MEM_RESERVE_MIB = 2048        # a node needs memAvailMiB >= reserve + the model's size for a new call
HOST_LOAD_FRACTION = 0.75  # the host load1 must stay below this x nproc
HOST_IO_FULL_AVG60 = 10.0  # the host /proc/pressure/io full avg60 must stay below this

# ------------------------------------------------------------------------------------------- small helpers


def now():
    return int(time.time())


def utc_day(t=None):
    return time.strftime('%Y-%m-%d', time.gmtime(now() if t is None else t))


def sha(*parts):
    return hashlib.sha256('\n'.join(str(p) for p in parts).encode('utf-8')).hexdigest()


def sha16(*parts):
    return sha(*parts)[:16]


def file_sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 16), b''):
            h.update(block)
    return h.hexdigest()


def item_id(organ, *identity):
    return f'{organ}:{sha16(*identity)}'


def cell_id(organ, depth, hex8):
    return f'{organ}.{depth}.{hex8}'


CELL_RX = re.compile(r'^(command|learning|digest|codebase|immune|selfdev|compute|database)\.(\d{1,2})\.([0-9a-f]{8})$')


def parse_cell(cid):
    m = CELL_RX.match(cid or '')
    if not m or int(m.group(2)) > MAX_DEPTH:
        raise ValueError(f'not a cell id: {cid!r}')
    return m.group(1), int(m.group(2)), m.group(3)


SECRET_RX = re.compile(r'(?i)(api[_-]?key|access[_-]?token|secret[_-]?key|password|passwd|bearer\s+[a-z0-9._-]{16,}|'
                       r'BEGIN [A-Z ]*PRIVATE KEY|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|xox[abp]-[A-Za-z0-9-]{10,}|'
                       r'AKIA[0-9A-Z]{16})')


def has_secret(text):
    return bool(SECRET_RX.search(text or ''))


def one_line(text, limit):
    """NFC, every control character and newline as one space, whitespace collapsed, backticks and
    braces removed (they would break a statement or a template), cut to `limit` characters."""
    text = unicodedata.normalize('NFC', str(text or ''))
    text = ''.join(' ' if unicodedata.category(c).startswith('C') else c for c in text)
    text = re.sub(r'[`{}]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:limit].rstrip()


def norm_text(text):
    """The identity form of free text: NFC, lower case, whitespace collapsed."""
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', str(text or '')).lower()).strip()


def boot_id():
    with open('/proc/sys/kernel/random/boot_id', encoding='ascii') as handle:
        return handle.read().strip()


def ensure_dirs():
    for path in STATE_DIRS:
        os.makedirs(path, mode=0o700, exist_ok=True)


def write_atomic(path, data, mode=0o600):
    tmp = f'{path}.tmp-{os.getpid()}'
    with open(tmp, 'w', encoding='utf-8', opener=lambda p, f: os.open(p, f, mode)) as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def log(message):
    os.makedirs(LOGS, mode=0o700, exist_ok=True)
    path = LOGS + '/tick.log'
    try:
        if os.path.getsize(path) > LOG_ROTATE_BYTES:
            for n in (2, 1):
                if os.path.exists(f'{path}.{n}'):
                    os.replace(f'{path}.{n}', f'{path}.{n + 1}')
            os.replace(path, path + '.1')
    except OSError:
        pass
    line = f'{time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())} {one_line(message, 600)}'
    with open(path, 'a', encoding='utf-8', opener=lambda p, f: os.open(p, f, 0o600)) as handle:
        handle.write(line + '\n')
    print(line, flush=True)


# ------------------------------------------------------------------------------------------- control


def control_state():
    """The operator's switches. ARMED counts only when its content equals this boot's id, so a reboot
    always comes back disarmed (the operator re-arms with life-ctl arm)."""
    armed = False
    try:
        with open(ARMED_FILE, encoding='ascii') as handle:
            armed = handle.read().strip() == boot_id()
    except OSError:
        armed = False
    return {'stop': os.path.lexists(STOP_FILE), 'freeze': os.path.lexists(FREEZE_FILE), 'armed': armed,
            'selfdev': os.path.lexists(SELFDEV_FILE)}


# ------------------------------------------------------------------------------------------- registry


def connect(path=REGISTRY, readonly=False):
    if readonly:
        conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=5)
    else:
        conn = sqlite3.connect(path, timeout=5, isolation_level=None)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=FULL')
    conn.execute('PRAGMA busy_timeout=5000')
    conn.execute('PRAGMA foreign_keys=ON')
    conn.row_factory = sqlite3.Row
    return conn


def apply_schema(conn, sql_path):
    with open(sql_path, encoding='utf-8') as handle:
        conn.executescript(handle.read())


class Tx:
    """BEGIN IMMEDIATE ... COMMIT, or ROLLBACK on any exception."""

    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        self.conn.execute('BEGIN IMMEDIATE')
        return self.conn

    def __exit__(self, kind, value, tb):
        self.conn.execute('COMMIT' if kind is None else 'ROLLBACK')
        return False


def notice(conn, kind, subject, text):
    """Open an operator notice unless one with this kind and subject is already open."""
    subject, text = one_line(subject, 120), one_line(text, 600)
    if conn.execute("SELECT 1 FROM notices WHERE kind=? AND subject=? AND state='open'", (kind, subject)).fetchone():
        return
    conn.execute("INSERT INTO notices (notice_id, kind, subject, text, state, at) VALUES (?, ?, ?, ?, 'open', ?)",
                 (sha(kind, subject, now(), os.getpid())[:12], kind, subject, text, now()))


def budget_row(conn, day=None):
    day = day or utc_day()
    conn.execute('INSERT OR IGNORE INTO budget (day) VALUES (?)', (day,))
    return conn.execute('SELECT * FROM budget WHERE day=?', (day,)).fetchone()


def budget_add(conn, column, n=1):
    assert column in ('program_runs', 'model_calls', 'agent_runs', 'bench_jobs', 'births')
    budget_row(conn)
    conn.execute(f'UPDATE budget SET {column}={column}+? WHERE day=?', (n, utc_day()))


def metric_add(conn, organ, column, n=1):
    assert column in ('items_done', 'items_failed', 'items_abstained', 'program_runs', 'agent_runs')
    conn.execute('INSERT OR IGNORE INTO metrics (organ, day) VALUES (?, ?)', (organ, utc_day()))
    conn.execute(f'UPDATE metrics SET {column}={column}+? WHERE organ=? AND day=?', (n, organ, utc_day()))


def live_cells(conn, organ=None, node=None):
    sql = "SELECT * FROM cells WHERE state IN ('active','dividing','quarantined')"
    args = []
    if organ:
        sql += ' AND organ=?'
        args.append(organ)
    if node:
        sql += ' AND node=?'
        args.append(node)
    return conn.execute(sql + ' ORDER BY cell_id', args).fetchall()


def active_release(conn):
    row = conn.execute('SELECT * FROM releases WHERE active=1').fetchone()
    if not row:
        raise RuntimeError('no active release')
    return row['release'], f'{RELEASES}/{row["release"]}', json.loads(row['manifest'])


def release_problems(directory, manifest):
    out = []
    for rel, digest in sorted(manifest.items()):
        path = os.path.join(directory, rel)
        if os.path.islink(path) or not os.path.isfile(path):
            out.append(f'{rel}: missing or not a regular file')
        elif file_sha(path) != digest:
            out.append(f'{rel}: sha256 differs from the release manifest')
    return out


def release_manifest(directory):
    manifest = {}
    for sub in ('genome', 'organs', 'policies'):
        for name in sorted(os.listdir(os.path.join(directory, sub))):
            path = os.path.join(directory, sub, name)
            if os.path.isfile(path) and not os.path.islink(path):
                manifest[f'{sub}/{name}'] = file_sha(path)
    return manifest


# ------------------------------------------------------------------------------------------- organ config


def load_organs(directory):
    with open(os.path.join(directory, 'organs', 'organs.json'), encoding='utf-8') as handle:
        data = json.load(handle, object_pairs_hook=_no_dup_keys)
    problems = organs_problems(data)
    if problems:
        raise ValueError('organs.json: ' + '; '.join(problems))
    return data


def _no_dup_keys(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f'duplicate JSON key {key!r}')
        out[key] = value
    return out


def organs_problems(data):
    """The closed schema of organs/organs.json. Returns a list of problems (empty = valid)."""
    out = []
    if not isinstance(data, dict) or set(data) != {'version', 'organs', 'ladders'}:
        return ['top level must be exactly {version, organs, ladders}']
    if data['version'] != 2:
        out.append('version must be 2')
    organs = data['organs']
    if not isinstance(organs, dict) or set(organs) != set(ORGANS):
        return out + ['organs must name exactly ' + ', '.join(ORGANS)]
    for name, spec in organs.items():
        keys = {'kind', 'seed_node', 'seed_focus', 'divide_backlog'}
        if not isinstance(spec, dict) or set(spec) != keys:
            out.append(f'{name}: keys must be exactly ' + ', '.join(sorted(keys)))
            continue
        if spec['kind'] != ('agent' if name in AGENT_ORGANS else 'model'):
            out.append(f'{name}: kind must be {"agent" if name in AGENT_ORGANS else "model"}')
        if spec['seed_node'] not in NODES:
            out.append(f'{name}: seed_node must be one of ' + ', '.join(NODES))
        if not isinstance(spec['seed_focus'], str) or not 8 <= len(spec['seed_focus']) <= 120:
            out.append(f'{name}: seed_focus is 8..120 characters')
        if type(spec['divide_backlog']) is not int or not 4 <= spec['divide_backlog'] <= 64:
            out.append(f'{name}: divide_backlog is an integer 4..64')
    ladders = data['ladders']
    if not isinstance(ladders, dict) or set(ladders) != set(PROGRAMS) | {'local-research'}:
        out.append('ladders must name exactly every program plus local-research')
    else:
        for program, ladder in ladders.items():
            if not isinstance(ladder, list) or not 1 <= len(ladder) <= 3 or any(m not in MODEL_MIB for m in ladder):
                out.append(f'ladder {program}: 1..3 models drawn from ' + ', '.join(MODEL_MIB))
            elif len(set(ladder)) != len(ladder):
                out.append(f'ladder {program}: a model appears twice')
    per_node = {}
    for spec in organs.values():
        if isinstance(spec, dict) and spec.get('seed_node') in NODES:
            per_node[spec['seed_node']] = per_node.get(spec['seed_node'], 0) + 1
    if any(n > NODE_CELL_CAP for n in per_node.values()):
        out.append(f'seed placement puts more than {NODE_CELL_CAP} cells on one node')
    return out


# ------------------------------------------------------------------------------------------- templates

PLACEHOLDERS = {                                  # every value a template may receive, and its exact form
    'ws': re.compile(r'^/home/operator/symblicos/projects/life-(codebase|selfdev|database)-[0-9a-f]{8}$'),
    'kit': re.compile(r'^' + re.escape(KIT) + r'$'),
    'test_id': re.compile(r'^tests\.[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+){0,4}$'),
    'finding_id': re.compile(r'^[0-9a-f]{16}$'),
    'finding_text': re.compile(r'^[^`{}\n]{1,600}$'),
    'scope': re.compile(r'^(files under tests/|Markdown files under docs/|the source files the failure names)$'),
    'proposal_id': re.compile(r'^[0-9a-f]{16}$'),
    'program': re.compile(r'^(' + '|'.join(re.escape(p) for p in PROGRAMS) + r')$'),
    'lesson': re.compile(r'^[^`{}\n]{10,300}$'),
    'migration_id': re.compile(r'^[0-9]{4}_[a-z0-9_]{1,40}$'),
    'request': re.compile(r'^[^`{}\n]{10,600}$'),
}
TEMPLATE_FIELDS = {
    'codebase': ('ws', 'kit', 'test_id', 'finding_id', 'finding_text', 'scope'),
    'selfdev': ('ws', 'kit', 'proposal_id', 'program', 'lesson'),
    'database': ('ws', 'kit', 'migration_id', 'request'),
}
FIELD_RX = re.compile(r'\{([a-z_]+)\}')
# Derived by render() from ws, never passed in. The statement templates write the workspace as the literal
# absolute prefix PROJECTS/life-<organ>- followed by {ws_id}, so the raw template text already names an absolute
# folder (symblic_autogen.lint finds no warning without a root) and the rendered text is exactly ws.
DERIVED_FIELDS = ('ws_id',)


def render(text, organ, values):
    """Fill a statement or policy template. Exactly the organ's fields, each matching its exact form, plus the
    derived ws_id (the 8 hex digits that end ws); ws must belong to this organ."""
    fields = TEMPLATE_FIELDS[organ]
    if set(values) != set(fields):
        raise ValueError(f'{organ} template needs exactly ' + ', '.join(fields))
    for key, value in values.items():
        if not isinstance(value, str) or not PLACEHOLDERS[key].match(value) or has_secret(value):
            raise ValueError(f'{organ} template value {key} has the wrong form')
    prefix = f'{PROJECTS}/life-{organ}-'
    if not values['ws'].startswith(prefix):
        raise ValueError(f'{organ} template value ws is not a {organ} workspace')
    filled = dict(values, ws_id=values['ws'][len(prefix):])
    used = set(FIELD_RX.findall(text))
    if not used <= set(fields) | set(DERIVED_FIELDS):
        raise ValueError(f'{organ} template names unknown fields: ' + ', '.join(sorted(used - set(fields) - set(DERIVED_FIELDS))))
    return FIELD_RX.sub(lambda m: filled[m.group(1)], text)


def render_run(release_dir, organ, values):
    """(lines, policy dict) for one agent run, both rendered from the active release; the statements must
    lint with zero findings and the policy must pass symblic_autogen.normalize."""
    import sys
    if REPO not in sys.path:
        sys.path.insert(0, REPO)
    import symblic_autogen as A
    with open(os.path.join(release_dir, 'organs', f'{organ}.lines.txt'), encoding='utf-8') as handle:
        lines = A.statements(render(handle.read(), organ, values))
    if not lines or any(values['ws'] not in line for line in lines):
        raise ValueError('every statement must name the workspace ' + values['ws'])
    findings = A.lint(lines, values['ws'])
    if findings:
        raise ValueError('lint: ' + '; '.join(f'{lv} line {n}: {m}' for lv, n, m in findings)[:300])
    with open(os.path.join(release_dir, 'policies', f'{organ}.json'), encoding='utf-8') as handle:
        policy = json.loads(render(handle.read(), organ, values), object_pairs_hook=_no_dup_keys)
    normalized = A.normalize(policy)
    problems = agent_policy_problems(policy)
    if problems:
        raise ValueError('policy: ' + '; '.join(problems))
    return lines, policy, normalized['sha256']


AGENT_POLICY_FIXED = {'version': 1, 'perpetual': False, 'until_done': False, 'candidates': 1, 'regenerate': 2,
                      'depth': 0, 'children': 2, 'generations': 1, 'agents_max': 3, 'attempt_seconds': 900,
                      'wall_seconds': 3600, 'novelty_limit': 2, 'saturation': 0, 'strategies': ['fresh', 'feedback'],
                      'syntax': True, 'require_change': True, 'self_split': False, 'designer': False,
                      'final': [], 'hidden': []}


def agent_policy_problems(policy):
    """Every LIFE agent run uses exactly the fixed bounded policy; only its checks differ by organ."""
    out = []
    if set(policy) != set(AGENT_POLICY_FIXED) | {'checks'}:
        out.append('keys must be exactly the fixed agent policy keys plus checks')
    for key, value in AGENT_POLICY_FIXED.items():
        if policy.get(key) != value or type(policy.get(key)) is not type(value):
            out.append(f'{key} must be {value!r}')
    checks = policy.get('checks')
    if not isinstance(checks, dict) or set(checks) != {'0', '1'}:
        out.append('checks must have exactly statement indexes "0" and "1"')
    return out


def policy_flags(policy):
    """The complete, exact bin/symblic-task start flags for a LIFE agent policy. Every field of
    AGENT_POLICY_FIXED is emitted (none is left to a server default); the tick then compares the run's
    server-side policy sha256 with symblic_autogen.normalize(policy)['sha256']."""
    problems = agent_policy_problems(policy)
    if problems:
        raise ValueError('; '.join(problems))
    flags = ['--candidates', '1', '--regenerate', '2', '--decompose', '0', '--children', '2', '--handoff', '1',
             '--agents-max', '3', '--attempt-seconds', '900', '--wall-seconds', '3600', '--novelty-limit', '2',
             '--saturation', '0', '--strategies', 'fresh,feedback', '--no-self-split']
    for index in ('0', '1'):
        for command in policy['checks'][index]:
            flags += ['--check', f'{index}:{command}']
    return flags


def autogen_run_id(request_id):
    """symblicos/autogen.py submit: run_id = 'autogen-' + sha256(client_request_id)[:24]."""
    return 'autogen-' + hashlib.sha256(request_id.encode()).hexdigest()[:24]


# ------------------------------------------------------------------------------------------- code-owned classifiers

RESTART_GATED_RX = re.compile(r'\.py$|(^|/)bin/|\.(service|timer|sh)$')
LIVE_STATIC_RX = re.compile(r'\.(html|js|mjs|css|json|svg)$')


def path_class(files):
    """Code decides how a patch reaches the operator, from the paths alone (the model's class never overrides)."""
    classes = set()
    for f in files:
        if f.startswith('tests/'):
            classes.add('tests')
        elif f.startswith('docs/') and f.endswith('.md') or (f.endswith('.md') and '/' not in f):
            classes.add('docs')
        elif RESTART_GATED_RX.search(f):
            classes.add('restart_gated')
        else:
            classes.add('live_static')
    if len(classes) == 1:
        return classes.pop()
    return 'mixed'


MIGRATION_RX = re.compile(
    r'^(CREATE TABLE IF NOT EXISTS org_[a-z0-9_]{1,40} \(.+\)|'
    r'CREATE (UNIQUE )?INDEX IF NOT EXISTS org_[a-z0-9_]{1,40} ON org_[a-z0-9_]{1,40} \([a-z0-9_, ]+\)|'
    r'ALTER TABLE org_[a-z0-9_]{1,40} ADD COLUMN [a-z0-9_]{1,40} [A-Z]+( [^;]*)?)$', re.S)
MIGRATION_DENY_RX = re.compile(r'(?i)\b(DROP|DELETE|UPDATE|INSERT|REPLACE|ATTACH|DETACH|PRAGMA|VACUUM|TRIGGER|VIEW|'
                               r'load_extension|readfile|writefile)\b')


def migration_statements(sql_text):
    text = re.sub(r'--[^\n]*', '', sql_text or '')
    return [re.sub(r'\s+', ' ', s).strip() for s in text.split(';') if s.strip()]


def migration_problems(sql_text, snapshot_sql=''):
    """An organism migration is valid only when every statement is one of the three additive forms, names
    only org_ tables, uses no denied word, and applies cleanly twice in memory on top of the snapshot."""
    out = []
    if len((sql_text or '').encode('utf-8')) > 16384:
        return ['migration is larger than 16384 bytes']
    statements = migration_statements(sql_text)
    if not 1 <= len(statements) <= 24:
        out.append('a migration has 1..24 statements')
    for s in statements:
        if MIGRATION_DENY_RX.search(s):
            out.append(f'denied word in: {s[:80]}')
        elif not MIGRATION_RX.match(s):
            out.append(f'not an allowed additive form: {s[:80]}')
    if out:
        return out
    db = sqlite3.connect(':memory:')
    try:
        if snapshot_sql:
            db.executescript(snapshot_sql)
        for s in statements:
            try:
                db.execute(s)
            except sqlite3.OperationalError as exc:
                if s.startswith('ALTER TABLE') and 'duplicate column' in str(exc):
                    continue
                out.append(f'sqlite refused: {exc}')
    finally:
        db.close()
    return out


ASK_RX = re.compile(r'^ask ([a-z_][a-z0-9_]*): (.+?) "((?:[^"\\]|\\.)*)"(.*)$')


def genome_protected_problems(old_text, new_text):
    """A selfdev proposal may change only the quoted instruction of ask lines (and note lines). Every other
    line, and every ask's name, type and trailing from/with clause, must stay byte-identical and in order."""
    old = [ln for ln in (old_text or '').splitlines() if ln.strip()]
    new = [ln for ln in (new_text or '').splitlines() if ln.strip()]
    if len(old) != len(new):
        return ['the number of nonblank lines changed']
    out, changed = [], 0
    for n, (a, b) in enumerate(zip(old, new), 1):
        if a == b:
            continue
        if a.startswith('note ') and b.startswith('note '):
            continue
        ma, mb = ASK_RX.match(a), ASK_RX.match(b)
        if not (ma and mb) or (ma.group(1), ma.group(2), ma.group(4)) != (mb.group(1), mb.group(2), mb.group(4)):
            out.append(f'line {n}: only an ask instruction or a note may change')
        else:
            changed += 1
    if not out and changed == 0:
        out.append('no ask instruction changed')
    return out


VERIFY_LINES = {
    'codebase': re.compile(r'^finding=[0-9a-f]{16} test=tests\.[A-Za-z0-9_.]+$'),
    'selfdev': re.compile(r'^proposal=[0-9a-f]{16} program=[a-z-]+$'),
    'database': re.compile(r'^migration=[0-9]{4}_[a-z0-9_]{1,40}$'),
}


def verify_line_problems(organ, text, expected):
    lines = [ln for ln in (text or '').splitlines() if ln.strip()]
    if len(lines) != 1:
        return ['verify.txt must hold exactly one nonblank line']
    if not VERIFY_LINES[organ].match(lines[0].strip()):
        return ['verify.txt line has the wrong form']
    if lines[0].strip() != expected:
        return ['verify.txt names a different item']
    return []


# ------------------------------------------------------------------------------------------- loopback adapter


class Telemetry(Exception):
    pass


def http_json(path, body=None, timeout=30):
    """GET (body None) or POST JSON to the loopback dashboard with bin/symblic-task's header shape: no proxy,
    no redirect, Host 127.0.0.1:8080. Any HTTP error, non-JSON answer or timeout raises Telemetry."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    data = None if body is None else json.dumps(body).encode('utf-8')
    req = urllib.request.Request(DASH + path, data=data, method='GET' if body is None else 'POST')
    req.add_header('Host', '127.0.0.1:8080')
    req.add_header('Accept', 'application/json')
    req.add_header('User-Agent', 'life-tick')
    if data is not None:
        req.add_header('Content-Type', 'application/json')
    try:
        with opener.open(req, timeout=timeout) as res:
            raw = res.read(8 * 1024 * 1024)
        value = json.loads(raw.decode('utf-8'))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
        raise Telemetry(f'{path}: {type(exc).__name__}: {str(exc)[:200]}') from None
    if not isinstance(value, dict):
        raise Telemetry(f'{path}: answer is not a JSON object')
    return value


def run_bounded(argv, *, timeout, cwd=None, env=None, limit=1 << 20):
    """Run argv in its own process group; kill the group at `timeout`. Returns (rc, stdout, stderr) with each
    output cut to `limit` bytes; rc None means the timeout fired."""
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            start_new_session=True)
    try:
        out, err = proc.communicate(timeout=timeout)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, 9)
        except OSError:
            pass
        out, err = proc.communicate()
        rc = None
    return rc, out[:limit].decode('utf-8', 'replace'), err[:limit].decode('utf-8', 'replace')


def child_env(extra=None):
    """The environment every LIFE subprocess gets: no inherited secrets, fixed PATH, thermal placement on."""
    env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/home/operator', 'LANG': 'C.UTF-8',
           'PYTHONDONTWRITEBYTECODE': '1', 'DASH_URL': DASH, 'SYMBLIC_THERMAL': '1',
           'SYMBLIC_CALL_WALL_S': str(CALL_TIMEOUT)}
    env.update(extra or {})
    return env


# ------------------------------------------------------------------------------------------- platform contract


def contract_problems():
    """The platform facts LIFE relies on, checked from the source text (no import with side effects). Any
    problem holds all new work and opens a notice; the operator reviews, then runs life-ctl rebase."""
    checks = [
        (REPO + '/symblicos/autogen.py', r"run_id = 'autogen-' \+ hashlib\.sha256\(request_id\.encode\(\)\)\.hexdigest\(\)\[:24\]",
         'run id derivation'),
        (REPO + '/symblicos/autogen.py', r"ADMITTED_ENGINES = \([^)]*'agy'", 'agy admitted for autogen'),
        (REPO + '/symblicos/autogen.py', r"TERMINAL = \{'completed', 'failed', 'cancelled', 'unknown', 'stuck'\}",
         'terminal run states'),
        (REPO + '/symblicos/autogen.py', r"os\.path\.isdir\(os\.path\.join\(cwd, '\.git'\)\)", 'cwd must be a git workspace'),
        (REPO + '/symblic_autogen.py', r"'agents_max': \(1, 96\)", 'agents_max limits'),
        (REPO + '/symblic_autogen.py', r"def normalize\(spec, \*, engines=\(\), nodes=\(\)\)", 'normalize signature'),
        (REPO + '/bin/symblic-task', r"'--novelty-limit', '--saturation'\}", 'start flags'),
        (REPO + '/bin/symblic-task', r"def cmd_autogen_get", 'autogen get'),
        (REPO + '/bin/symblic', r"p\.add_argument\('--max-calls'", 'symblic run --max-calls'),
        (REPO + '/bin/symblic', r"p\.add_argument\('--ollama-limits'", 'symblic run --ollama-limits'),
        (REPO + '/symblic_run.py', r"by = self\._opt\(s, 'by', env\)\n\s+if by is None:\n\s+by = self\.defaults\.get\('applicator'\) or self\.opts\.get\('by'\)",
         'ask-level by wins over --by'),
        (REPO + '/symblic_apply.py', r"THERMAL_HOT, THERMAL_COOL, THERMAL_TTL = 85\.0, 75\.0", 'thermal thresholds'),
        (REPO + '/local_research.py', r'def read_page\(url: str, chars: int = PAGE_CHARS\) -> str:', 'read_page'),
        (REPO + '/bin/local-research', r"p\.add_argument\('--json'", 'local-research --json'),
        (REPO + '/cluster_engine.py', r"if route == 'map':", 'cluster map route'),
        (REPO + '/cluster_highpower.py', r"route=='state'", 'highpower state route'),
    ]
    out = []
    for path, pattern, what in checks:
        try:
            with open(path, encoding='utf-8') as handle:
                text = handle.read()
        except OSError as exc:
            out.append(f'{what}: cannot read {path}: {exc}')
            continue
        if not re.search(pattern, text):
            out.append(f'{what}: pattern not found in {os.path.relpath(path, REPO)}')
    return out

