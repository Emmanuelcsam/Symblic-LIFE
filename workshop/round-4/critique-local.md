# Round 4 — local adversarial critique of LIFE v2.2

Reviewer: local Claude Code subagent with the live checkout, 2026-10-11 [clock reading removed for publication]. Read: BRIEF.md,
DECISIONS.md, README.md, LIFE.md sections 1-18 in full, and every program verbatim (bin/life-tick.py, life_common.py,
life-ctl.py, life-check.py, life-research.py, life-fetch.py, life-seed.sh), checks/, genome/, organs/, policies/,
db/organism.sql and the life.sql column list, spawn/PROTOCOL.md, units/, benchmarks/, round-3 decisions and LOG.

Nothing was run except static checks that call no model: `VALIDATE.sh` (ends **STATIC PASS**) and
`life_common.contract_problems()` (prints `contract holds`, 94 rows). Every platform statement below was read with
rg/sed in the live checkout; `[U]` marks a finding that is an undefined or two-way-readable detail.

The regex contract holds, so the round-4 defects are mostly places where the *behaviour* of a platform path differs
from what the kit says about it (findings 1-5), and quantitative bounds that were never derived (7, 8, 9, 16).

---

## HIGH

**1. high — the codebase gate can never pass a code or test patch: `bin/devcheck` runs `bin/devtest` in the sandbox, which needs `uv`, a HOME cache and the network**
Location: checks/devcheck-gate.sh line 42 (step 2); LIFE.md §7.4 "gate", §11 "Sandbox", README step 3 (`gate-selftest`).
Defect (verified in code): `./bin/devcheck --changed BASE` without `--no-tests` runs the affected tests
(`scripts/devcheck.py` main: `tests = 'skip' if args.hook or args.no_tests ... else 'run'`; `run_tests` →
`bin/devtest --changed BASE` because `bin/devtest` is tracked 100755). `scripts/devtest.py:environment()` builds
`~/.cache/dashboard-devtest/venv-<lock>` with `uv_command()`: `Path.home()/agent-upgrades/bin/agent-tool`, then
`shutil.which('uv')`, then `~/.local/bin/uv`. Inside the sandbox HOME is an empty temporary folder and PATH is
`/usr/local/bin:/usr/bin:/bin` (uv lives only in /home/operator/.local/bin), so devtest raises `uv is missing`; even
with uv, `uv pip sync --require-hashes requirements-devtest.lock` needs PyPI over TCP, which the sandbox blocks.
devcheck then reports `bin/devtest exit 1` and exits 1 → gate exit 4. Every `local_fix` (its file selects at least
the tests that import it) and every `test_only` patch fails the gate; `gate-selftest` phase A fails too. The kit's
claim that a correct patch passes step 2 is contradicted by the code; with 8 failures the codebase cell is
quarantined, auto-released after 24 h, and quarantined again forever.
Fix (replacement for line 42 and the step-2 comment):
```
out="$(/usr/bin/python3 -B "$KIT/bin/life-check.py" sandboxed --timeout 600 ./bin/devcheck --changed "$base" --no-tests 2>&1)"
#   2. ./bin/devcheck --changed BASE --no-tests (compile, ruff F, project rules, secrets, page checks; NO test run:
#      the focused test is step 3, under /usr/bin/python3, because bin/devtest needs uv, a HOME cache and PyPI)
```
Add a CONTRACT row on scripts/devcheck.py `ap.add_argument('--no-tests'` and a VALIDATE rule that the gate script
contains `--no-tests`. State in §7.4 that `node --check` page checks are skipped inside the sandbox (node lives under
~/.nvm, unreadable) and appear only as a devcheck note.

**2. high — codebase check 0 (agent-written code) runs inside host-checkout.service's cgroup, not in a bounded scope**
Location: policies/codebase.json check "0"; bin/life-check.py `sandboxed`; LIFE.md §4 ("Heavy local work ... runs in
its own life-<purpose>-<8hex>.scope"), DECISIONS.md line 9 ("each in its own bounded scope").
Defect (verified): autogen evaluates policy checks with `symblicos/autogen.py:_run` (`subprocess.Popen(['bash','-c',
cmd])`, nice 10) from a worker thread of the dashboard server; `systemctl --user show host-checkout.service`
gives `MemoryMax=infinity`, `TasksMax=16725`, cgroup `app.slice/host-checkout.service`. `life-check.py sandboxed`
adds Landlock and a per-PROCESS `prlimit --as 4 GiB`, but no cgroup: candidate code may fork N processes of 4 GiB each,
all charged to the dashboard's cgroup. The host has three oomd kills on record; oomd would pick the dashboard. The
process is also outside STOP's `systemctl --user stop life-*.scope` and outside LIFE's the host memory gate.
Fix: in `life-check.py sandboxed`, wrap the launcher with `L.scope_argv(argv, memory='4G', runtime=timeout + 15,
name='check')` and `env=L.scope_env()` (systemd-run --user works from inside the dashboard unit once
XDG_RUNTIME_DIR=/run/user/<uid> is set); exit 125 when systemd-run fails (never run unscoped); before starting, refuse
with exit 125 when `/proc/meminfo` MemAvailable < HOST_MEM_FLOOR_MIB or memory `some avg60` >=
HOST_MEM_SOME_AVG60 (same rule as the tick). Then §4's sentence becomes true for every candidate-code process.

**3. high — every agent attempt leaves a full own-checkout on the host and on the worker node; nothing removes them, so the organism halts on its storage hold within about a day**
Location: LIFE.md §3 (paths table), §12, GAP 14; bin/life-tick.py `storage`, `retention`, `remove_retired_workspace`.
Defect (verified): autogen starts each attempt "in their own checkouts" (symblicos/autogen.py docstring line 6);
`agent_hub.make_worktree` creates `<dirname(top)>/<basename(top)>.agents/<name>-<stamp>` on branch
`agents/<name>-<stamp>` — for LIFE that is `/home/operator/symblicos/projects/life-codebase-0-00000000.agents/...` — and
`provision_remote` adds `~/agents-work/<same>` on the worker node. Promotion calls only `work_action('commit')` and
`('apply')`; `agent_integrations.apply_work` keeps the worktree; the only remover is `discard`, which neither autogen
(`grep discard symblicos/` finds none) nor LIFE calls, and the hub has no janitor. Sizes measured today: HEAD tree
786.3 MB, pack 744.6 MiB, so each codebase attempt leaves about 0.77 GB on the host and on the worker node (up to 4 attempts per
run: agents_max 4). `storage()` counts `PROJECTS/life-*` (the `.agents` siblings start with `life-`), so after about
8 attempts plus the 1.5 GB clone, STATE_MAX_BYTES 10 GiB is passed and the storage hold stops ALL work and the inbox;
the storage notice tells the operator to prune STATE/calls and STATE/runs, which does not help. On the worker nodes the growth
is unbounded (GAP 14 mentions mirrors, not per-attempt checkouts). `remove_retired_workspace` deletes a clone while
its `.agents` worktrees still point into its `.git/worktrees/`.
Fix: a new upkeep step "agent checkouts" (after collection, same tick): for each collected run, for every attempt
agent id in the server row (`nodes[].attempts[].agent_id`), call the hub's discard through an existing loopback
route (or, if none is admitted for scripts, LIFE runs `git -C <ws> worktree remove --force <wt>` and
`git -C <ws> branch -D agents/<...>` with GIT_SAFE for worktrees under `<ws>.agents/` whose branch matches
`agents/` and whose run is collected, and records the worker node path `~/agents-work/<name>` in `STATE/operator/node-cleanup.txt`
with notice `node_cleanup`). Add the `.agents` sibling and the autogen staging folder to the §3 table, define
`CODEBASE_CLONE_BYTES = 1.6e9` (measured) and derive `STATE_MAX_BYTES >= ORGAN_CELL_CAP x CODEBASE_CLONE_BYTES +
AGENT_RUNS_LIVE_MAX x agents_max x 0.8e9 + 2 GiB`, and make `remove_retired_workspace` remove the `.agents` sibling
first. GAP 14 must name the per-attempt worker node checkouts and give a size per day (12 runs x up to 4 x 0.77 GB).

**4. high — "hooks, fsmonitor, external diff, textconv and filters can never execute" is false; the guard is a per-tick hash that is not persisted, and the platform's own git runs in LIFE clones without GIT_SAFE**
Location: bin/life_common.py lines 1854-1858 (GIT_SAFE comment), `git_meta_sha256`, `GIT_META`; LIFE.md §1 last
two bullets; bin/life-tick.py `watch_run`, `gate_patch`.
Defect (verified): GIT_SAFE sets hooksPath, fsmonitor, sshCommand, diff.external, protocol.ext.allow and pager only.
`filter.<driver>.clean/smudge/process` (run by `git add -A`, `reset --hard`, `checkout`, `diff`),
`diff.<driver>.command` on commands without `--no-ext-diff`, `core.gitProxy`, `core.alternateRefsCommand` and
`include.path` targets are not neutralised; protection rests on `git_meta_sha256` taken just before and compared just
after each sandboxed run in the SAME tick. (a) If the tick dies between the two (oomd, TimeoutStopSec SIGKILL, power
loss) the next tick takes the tampered config as its new "before" hash. (b) The hub and autogen run their own git in
the LIFE clone with no GIT_SAFE and with the operator's SSH environment: `agent_hub.make_worktree` (`worktree add` →
post-checkout hook), `provision_remote` (`git push` → pre-push hook, `_git_ssh_env`), autogen `_stage_remote`
(`worktree add`). (c) GIT_META omits `HEAD`, `refs/`, `packed-refs`, `worktrees/`, `shallow`, `commondir` and the
loose-object files, all writable by sandboxed code (`--rw cwd` covers `.git`); a rewritten HEAD/ref or loose object
changes what the next `reset --hard HEAD`, `git show BASE:f` or `git diff --cached BASE` reads.
Fix: (1) correct the comment to "hooks, fsmonitor, external diff and pagers are disabled; filters and other
config-driven commands are prevented only by the git-metadata hash". (2) Persist the hash: new column
`cells.git_meta_sha256`, written after every trusted LIFE git write (clone, reset, commit, sync); verified at tick
start for every agent workspace, before every trusted git command (`Tick.git`), before every agent start (the hub's
git) and by `life-ctl gate-selftest/apply`; a mismatch deletes the workspace (notice `workspace`) and never runs git
there. (3) Extend GIT_META with `HEAD`, `packed-refs`, `refs`, `worktrees`, `shallow`, `commondir` and the sorted
list of `objects/??/*` names with sizes (packs are immutable). (4) Add `-c core.attributesFile=/dev/null -c
core.gitProxy= -c core.alternateRefsCommand=` to GIT_SAFE.

**5. high — §10 says model calls are memory- and CPU-bounded by the fleet runner units; on the worker nodes the model runs in an uncapped Ollama service**
Location: LIFE.md §10 "Resource limits per job" (line 903), §8 program contract; life_common MEM_RESERVE_MIB/MODEL_MIB.
Defect (verified): `fleet_runner.unit_argv` puts MemoryMax/CPUQuota/RuntimeMaxSec on the fleet runner run unit (the
client process, 'node': memory 1536M, cpu 150 %); the model's weights and KV cache live in the node's `ollama`
service, which `fleet_runner` documents as uncapped ("worker node Ollama is not capped ... the nodes' drop-in
zz-local-models.conf lifts MemoryMax to 12G/26G and removes the CPU quota"). So the kit's statement that fleet runner bounds
a model call's memory and CPU is contradicted; LIFE's own admission (`memAvailMiB >= 2048 + MODEL_MIB + 1024`) and the
duty cycle are the only bounds, and CPU (heat) is unbounded per call.
Fix (replacement text for §10): "Model calls: the fleet runner unit bounds only the client's wall time (RuntimeMaxSec);
the model's memory and CPU are in the node's uncapped Ollama service. LIFE bounds them by its own memory admission
(MEM_RESERVE_MIB + MODEL_MIB[model] + KV_ALLOWANCE_MIB, checked against the latest sample), one model call per node
(fleet_runner._check_capacity) and the per-node duty cycle." Pin `'node_num_ctx'`/`ollama_need` in CONTRACT and
derive KV_ALLOWANCE_MIB from `fleet_runner._kv_bytes(model, 4096)` (the bucket LIFE's prompts reach) instead of 1024.

## MEDIUM

**6. medium — a STOP is recorded as the work's own failure**
Location: bin/life-tick.py `gate_patch`, `make_workspace`, `run_program`/`record`, `watch_run`; LIFE.md §5 step 4.
Defect: the watcher SIGTERMs process groups, but the main thread then records the killed process's return code as
an ordinary outcome: the gate gets rc -15 → `finish_item(... 'failed')` → failure streak + 1 and a `finding_failed`
notice that also blocks the next finding of that test (same fingerprint, notice open); a killed clone counts as
`workspace_failed` (3 → the cell is retired); a killed slot program becomes 'infra' (node hold 1800 s, infra_runs + 1)
before `stop_everything` runs. §5 promises STOP-cancelled work "not counted as a failure or as infra".
Fix: `Procs.kill_all(reason='stop')` sets `self.stopped = True`; `Procs.run` returns rc `STOPPED_RC = 1001` for any
process ended by it; every caller maps 1001 to "stopped": the item stays/returns queued at its stage with no counter
change, no node hold beyond ORPHAN_HOLD_SECONDS, no notice except `stopped`; `make_workspace` returns '' and records
nothing; the gate item stays queued at gate. Add test_stop_during_gate to GAP 8.

**7. medium [U] — a division cannot reliably finish inside DIVISION_MAX_TICKS 12**
Location: life_common DIVISION_MAX_TICKS, DIVISION_STEP_EVERY, ASSIGN_MAX/ASSIGN_PER_SLOT; life-tick `plan_slot`,
`division_progress`; spawn/PROTOCOL.md §2.
Defect: minimum path = foci at tick T, assign at T+2, T+4, T+6, T+8 (16 items / 4 per slot), model commit at T+9;
agent organs add the workspaces stage (T+9, T+10) and commit at T+11. Any single node hold (1800 s ≈ 6 ticks), node
rest (600 s ≈ 2 ticks), the one allowed foci retry (+2) or a tick whose the host stages pass TICK_DEADLINE aborts the
division, followed by a 6 h cooldown. Also `plan_slot` compares `tick_no - last_step_tick` where tick_no counts
observe-only ticks too, while the text says "every 2nd armed tick".
Fix: count `divisions.ticks` only on ticks where the parent's node was in `available` and the tick reached the slot
phase; set `DIVISION_MAX_TICKS = DIVISION_STEP_EVERY x (1 + FOCI_RETRIES + ceil(ASSIGN_MAX / ASSIGN_PER_SLOT)) + 3 +
12` (= 27, computed in life_common, VALIDATE asserts the formula); keep the 24 h wall backstop; use a separate
`armed_tick_no` meta counter for DIVISION_STEP_EVERY.

**8. medium [U] — CALL_TIMEOUT 900 s is not derived from the programs' worst case; a timeout punishes the whole node**
Location: life_common CALL_TIMEOUT, CALL_MAX_MODEL_CALLS, OLLAMA_LIMITS; genome notes; life-tick `record`.
Defect: worst cases are 6-11 calls per program (notes), each allowed `timeout_seconds 240`, i.e. up to 2640 s against
a 900 s process limit; extract-source sends a 6000-character source in each of up to 9 calls to qwen3:4b on CPU worker nodes.
No per-call latency was measured. A timeout holds the node 1800 s for all its cells, and single-rung ladders
(extract-source, propose-experiment, local-research) can never escalate, so long sources end at the operator after 6
timeouts.
Fix: life_common `WORST_CALLS = {program: n}` (from the notes, VALIDATE parses them), `CALL_P95_SECONDS = {model: s}`
measured by the admission tests (until then the operator fills it), program timeout = `min(CALL_TIMEOUT_MAX,
WORST_CALLS[p] x CALL_P95_SECONDS[m] + 60)` and `timeout_seconds = CALL_P95_SECONDS[m] x 2`; a `timeout` holds only
that program on that node (`node_holds` keyed by node and program) for NODE_HOLD_SECONDS.

**9. medium [U] — "fleet loaded" is judged from a 0.3-second CPU sample**
Location: life-tick `metabolism` (line ~411), LIFE.md §10 "Fleet loaded".
Defect (verified): `vitals.cpu` is `(1 - idle/total) x 100` over `sleep 0.3` of /proc/stat (cluster_engine probe,
lines 207-211). One 0.3 s sample per 300 s interval decides whether the whole interval counts toward the 3000 s work
window; a brief spike or a lull flips it.
Fix: loaded when `load5 / cpus >= FLEET_LOAD5_PER_CPU` (0.5) using `vitals.load` ("l1,l5,l15") and `vitals.cpus`
(both in the same probe; add two CONTRACT rows: `p load "$(cut -d' ' -f1-3 /proc/loadavg` and `p cpus`), OR LIFE's
own busy ledger; drop LOADED_CPU.

**10. medium [U] — the agy model and effort are not defined**
Location: life-tick `start_run` argv (line ~1934), `resend`; DECISIONS.md line 11; LIFE.md §1 and §7.9.
Defect (verified): bin/symblic-task accepts `--model` and `--effort` (FLAGS_WITH_VALUE), LIFE passes neither, so the
run's `base.model` is '' and the hub's default agy model is used — which model, at which effort and against which
per-model quota (`fleet_runner.cooldown_key` pauses agy per model) is undefined; the brief asks for lightweight
models and the operator's memory notes a weekly-limit incident.
Fix: life_common `AGY_MODEL = '<exact id the operator chooses>'`, `AGY_EFFORT = 'low'`; `start_run` and `resend` pass
`--model AGY_MODEL --effort AGY_EFFORT`; `run_identity_problems` also compares `base.model` and `base.effort`;
DECISIONS line 11 names the model; a cooldown refusal is infra with notice `agy_quota`.

**11. medium [U] — a worker node can run an agent run and a model run at once with no memory accounting, and one agent run rests the node for its other cells**
Location: life-tick `plan_slot` (only `bench` checks `node_has_agent_run`), `node_ok`, `refresh_available`; LIFE.md
§10, GAP 4.
Defect: `start_agent_runs` (step 14) and the slot phase (step 17) can start an agy run (up to 4 agents whose tool
loops run the repository's tests) and a 4B model on the same 15.5 GB worker node in the same tick; memory admission uses the
sample from step 5, taken before the agent run started, and `refresh_available` re-reads only if 120 s passed. Since
`busy_seconds` counts the whole agent run, one 3000+ s agent run rests the node, starving the up to 3 other cells
there for over an hour.
Fix: (a) after any agent start, force `refresh_available()` before the slot phase; (b) a program or division action
on a node with a live LIFE run needs `memAvailMiB >= MEM_RESERVE_MIB + MODEL_MIB + KV_ALLOWANCE_MIB + AGENT_RUN_MIB`
(define 4096); (c) seed placement keeps agent cells on node-i (31 GB) or on nodes that host no model cell, and
DECISIONS states that an agent run consumes its node's duty window.

**12. medium [U] — environment-error detection hides real regressions**
Location: life-tick `ENV_ERROR_RX` (line 68), `watch_outcome`.
Defect: the regex is searched in the whole 40-line tail: any failing test whose name or message contains `sandbox`
or `Landlock` (tests.test_landlock_sandbox, autogen sandbox tests) and every genuine `ImportError` caused by the code
(a removed or renamed function, the commonest regression) is classified `watch_error`, never a finding.
Fix: environment error only when (a) rc 125, or (b) the LAST exception line (`failure_fingerprint` class) is
`ModuleNotFoundError: No module named 'X'` and the top-level part of X is neither a `.py` file nor a package directory
at the clone root, or (c) the last exception is PermissionError/ConnectionRefusedError/OSError with errno 13, 11 or
111 naming a path outside the clone or a socket. Everything else with a `FAILED (` line is a finding.

**13. medium [U] — the operator's route is decided by a 1B model; the `database:` prefix is checked only after the model chose `database`**
Location: genome/classify-command.sym, life-tick `on_classify_command`, LIFE.md §7.1.
Defect: "models propose, code decides", yet a `database: ...` command labelled `learning` by llama3.2:1b becomes a
research question, and the operator has no deterministic way to force any route.
Fix: code parses a leading prefix before any model call (case-insensitive, followed by a space): `research:` →
learning, `fix:` → codebase (test id required), `database:` → database, `measure:` → compute, `genome:` → selfdev,
`status` (alone) → heartbeat. A prefixed command never runs classify-command (its item is created directly, priority
1, `restated` = ''). Unprefixed commands go to the model as now; the database route still requires the prefix.

**14. medium [U] — the host memory and pressure are sampled once, up to 20 minutes before heavy the host work starts**
Location: life-tick `host_reasons` (called in `metabolism` and `refresh_available` only), `launch_allowed`.
Defect: the watch test (4G scope), the gate (devcheck + test, 900 s), clones (1.5 GB, IO heavy), fetches (1G) and
in-process migration validation begin up to TICK_DEADLINE after step 5; `launch_allowed` checks only control files.
Fix: `launch_allowed(heavy=False)`; heavy=True also requires `host_reasons() == []`; every host-stage process
(watch, confirm, gate, clone, fetch) and `apply_migration` call it with heavy=True.

**15. medium [U] — propose-experiment never sees the parameter grammar it must match**
Location: life-tick `inputs_for` ('propose-experiment' catalogue), genome/propose-experiment.sym.
Defect: the catalogue lists id, description, baseline, unit, direction and minimum gain, but not `param_rx`; code
then requires a FULL match, so a 4B model guesses the legal values (the example's `^(DELETE|WAL|MEMORY|TRUNCATE)$` is
not shown).
Fix: catalogue entry text adds `allowed parameter pattern: <param_rx>`; the param ask becomes "Which parameter value
should the candidate run use? Answer with one value that fully matches the allowed parameter pattern of that
benchmark, and nothing else."

**16. medium [U] — the tick unit's MemoryMax=1G is unmeasured while up to five model clients run inside it**
Location: units/life-tick.service, life_common TICK_TASKS_MAX comment, life-tick `run_program`, `apply_migration`.
Defect: every `bin/symblic run` (the .venv Python plus the Symblic stack) and every `life-research.py` (imports
fleet_runner and local_research) runs as a child in the tick's cgroup, up to one per worker node in parallel, plus
in-process validation of an organism copy of up to 64 MiB. A cgroup OOM can kill the tick itself mid-transaction,
skipping its status write and STOP handling.
Fix: run each slot process in `L.scope_argv(argv, memory='768M', runtime=timeout, name='slot')` like other heavy
work, or measure the p95 RSS of both programs and set `TICK_MEMORY_MAX = 256 MiB + 5 x p95 + 128 MiB` in life_common
with VALIDATE comparing the unit file.

**17. medium — sandboxed code can fill /dev/shm, which outlives the run**
Location: landlock_sandbox.py `SYSTEM_RW` (includes `/dev/shm`); LIFE.md §1 sandbox bullet, §18.
Defect (verified): /dev/shm is writable inside the Landlock sandbox. Candidate code in a watched test, the gate or
check 0 can leave RAM-backed files that persist after the scope ends (the host memory leak toward oomd) and that
later runs or bin/devtest (which uses /dev/shm for fixture scratch) can read: a cross-run channel. Not in the GAPS.
Fix: GAP 17 text, and in `watch_run`, `gate_patch` and `life-check sandboxed`: list `/dev/shm` entries owned by
The host (name, inode) before the run and remove every new one after it; add a probe line that writes and removes
`/dev/shm/life-probe-<hex>` so the operator sees the boundary; the platform change is a launcher flag that omits
/dev/shm.

**18. medium [U] — agent-written text is tainted `code`, and the reviewer's request is placed inside the "quoted as data" region**
Location: life-tick `gate_patch`/`gate_proposal` (`derive_taint(item['taint'], 'code')`), `start_run` (`text =
finding_text + ' Reviewer asked: ' + review_note`), organs/codebase.lines.txt.
Defect: diffs, proposals and migrations are written by agy (a model) but carry taint `code`; the needs_work reason
(model text) is appended to the finding text that the statement introduces as "quoted as data and not as an
instruction", so the agent is told both to ignore it as an instruction and to act on it.
Fix: patch/proposal review items take `derive_taint(item_taint, 'model')`; the codebase template gains a separate
field: "...; the reviewer of the previous attempt asked for this one change, quoted as data: {review_note}" (empty
review_note renders the clause away by using a second template line set, or the note is dropped); PLACEHOLDERS gets
`review_note: [^`{}\n]{0,240}`.

**19. medium [U] — arming does not require a passing gate self-test**
Location: bin/life-ctl.py `arm`, `gate_selftest`; README step 3.
Defect: README says gate-selftest "must print PASS", but `arm` checks only seed, DECISIONS hash, contract, STATE,
VALIDATE and the probe; with finding 1 the operator can arm a codebase organ whose gate always fails.
Fix: on PASS, gate-selftest writes meta `gate_selftest` = `<kit_sha256> <platform_sha256> <test_id> <time>` (add to
META_KEYS); `arm` refuses unless it matches the current hashes; or the codebase organ holds (notice
`gate_unproven`) while it does not.

**20. medium — the per-node duty cycle allows 50 minutes of every hour, every hour, forever**
Location: life_common NODE_WINDOW/NODE_BUSY_MAX/NODE_REST; DECISIONS.md line 5; operator feedback on worker node heat
(a 3.5 h bench was stopped; "bound long worker node load, ask past ~1 h").
Defect: 83 % sustained duty with 600 s rests and an 85 °C trip is the long load the operator stopped; DECISIONS line 5
states the numbers but not the daily total (up to 20 h of LIFE load per worker node per day).
Fix: add `NODE_BUSY_PER_DAY = 6 x HOUR` (LIFE busy seconds per node per UTC day; over it the node takes no LIFE action
until 00:00 UTC) and `NODE_REST = 1800`; DECISIONS line 5 names both and "the operator raises them by editing
life_common".

## LOW

**21. low — the daily agent-run budget can be exceeded by one.** life-tick `start_agent_runs` reads `budget['agent_runs']`
once; with 11 used and two free live slots it starts two (13/day). Fix: re-read the budget inside the loop and stop when
`agent_runs + 1 > AGENT_RUNS_PER_DAY`.

**22. low [U] — `status.json` `disposition` has one value.** life-tick `main` always writes 'finished'. Define:
`worked | observe:<first hold> | stop | fault | integrity` from the exit path.

**23. low [U] — automatic quarantine release is not among the operator-accepted restarts.** DECISIONS line 8 ("nothing
restarts itself") does not mention `auto_release` (the organ's only cell returns to work after 24 h). Add: "except
the automatic release of an organ's only quarantined cell, once per 7 days, at the top rung".

**24. low [U] — DECISIONS does not say that "split off what they cannot do" is switched off.** Every LIFE run has
`self_split false, depth 0`. Add a line: "regenerate or split": agent runs never split; an item that cannot be done
goes to the operator (bounds of line 1).

**25. low [U] — triage class descriptions disagree with the gate.** genome/triage-error.sym: test_only "only files
under tests/" vs the gate's "only the ONE module file the test id resolves to"; local_fix "inside one function body"
vs up to 3 bodies in up to 3 traceback files. Replace with: `test_only: "only the test module file named by the
test id needs to change"`, `local_fix: "up to three function bodies in files the traceback names need to change, with
no signature, import or module-level change"`.

**26. low [U] — MIGRATION-RULES text and MIGRATION_RX disagree.** Rule 4 lists TEXT, INTEGER, REAL, BLOB, NUMERIC but
the regex accepts any `[A-Z]+`; rule 3 (lower-case column names) is not checked inside CREATE TABLE bodies; the body
`(.+)` admits CHECK, GENERATED and DEFAULT expressions with any undenied function. Fix: enforce
`(TEXT|INTEGER|REAL|BLOB|NUMERIC)` and a column grammar `[a-z0-9_]{1,40} TYPE( NOT NULL| UNIQUE| DEFAULT
<literal>| PRIMARY KEY| REFERENCES org_x \(col\))*` plus table-level `PRIMARY KEY (cols)`/`UNIQUE (cols)`; refuse
CHECK and GENERATED; state the same in MIGRATION_RULES.

**27. low [U] — one bad row stops the store adapter forever.** life-tick `store`: any constraint error rolls the batch
back and only logs; the mark never advances and the same 500 rows are retried every tick. Fix: `INSERT OR IGNORE`,
count ignored rows, notice `store_failed` after 3 ticks with no progress for a table.

**28. low [U] — `.py` files named in an operator command can never be fixed.** life-tick `confirm_finding` adds them to
`trace_files` with `trace_functions = []`, so every local_fix touching them fails `local_fix_problems`. Fix: accept
`path.py:function` in the command (functions become allowed) or drop bare file names.

**29. low — `revive` can exceed LIFE_MAX_CELLS.** life-ctl `revive` checks only NODE_CELL_CAP; add
`len(live_cells) + 1 <= LIFE_MAX_CELLS`.

**30. low [U] — one hold row per node.** `node_holds.node` is the primary key and every writer uses INSERT OR REPLACE,
so a later short hold can replace a `job:<id>` hold (365 days), after which `busy_seconds` no longer counts the lost
job. Fix: `ON CONFLICT(node) DO UPDATE SET until=max(until, excluded.until), reason=CASE WHEN reason LIKE 'job:%'
THEN reason ELSE excluded.reason END`.

**31. low [U] — STOP_POLL's meaning names FREEZE and ARMED; the watcher reads only STOP.** life_common line 134. Fix
the comment (and LIFE.md §13 row): "re-reads control/STOP this often".

**32. low [U] — several new processes start without the final admission check.** §4 step 14 and §5 say every process
is admitted by `launch_allowed` immediately before creation; `make_workspace` clones, `refresh_clone` fetches, the
catalogue and inventory reads and canary lines use `proc()` without `admit=True`. Either pass admit=True to the clones
and fetches or narrow the sentence to "every slot action, fetch, gate, watched test and agent start".

**33. low [U] — the "master Symblic script" is a Python coordinator.** LIFE.md title and §1: the top-level control
loop is bin/life-tick.py; the Symblic parts are nine genome programs and three two-line statement templates. Say so in
the first paragraph ("the Symblic program is the gcode" applies to the genome and statements; the tick is the printer's
firmware), so a fresh agent does not look for a runnable LIFE statement script.

**34. low [U] — confirm items: stay with the parent or not?** WORKSPACE_STAGES and spawn/PROTOCOL.md say confirm items
stay with their cell's workspace, but `dispatch` unassigns queued confirm items of retired or quarantined cells (it
excludes only gate and apply). Define: confirm items are re-dispatched (they need any idle clone) and remove confirm
from the "stay" wording.

**35. low — gate_proposal and apply_migration open workspace files following symlinks.** Check 0 (O_NOFOLLOW) refuses
symlinks first, but the host stage should not depend on it: read with life-check's `read_inside` logic and refuse a
mode other than 100644 (the codebase gate's `mode_problems`).

**36. low [U] — the credential screen refuses ordinary code and commands.** SECRET_RX matches `token = tokens[0]`,
`password = get_password()` or "research token = bucket algorithms" (6+ non-space characters after `=`), so such diffs
are refused and such commands bounced. Define for diffs: only quoted literals of 8+ characters or unquoted runs of
20+ characters with at least three character classes count; keep the strict rule for inbox text.

**37. low [U] — a clone that cannot be refreshed stops watched tests silently.** life-tick `findings` returns without a
notice when `refresh_clone` fails. Open notice `workspace` as `confirm_finding` does.

**38. low [U] — the bench duty reservation uses BENCH_TIMEOUT_MAX, not the template's timeout.** `plan_slot` reserves
`BENCH_RUNS x (300 + 10) + 60` = 2230 s for every job; §10 says "a benchmark job, its full 7-run timeout". Use the
template's `timeout`.

**39. low [U] — clone sizes and times are unmeasured.** CLONE_TIMEOUT 600 s covers a `--no-local` clone of a 744.6 MiB
pack plus a 786 MB checkout under the host IO pressure; nothing in §13 records the measured size. Add
`CODEBASE_CLONE_BYTES` (finding 3) and a measured clone time with 2x margin.

**40. low — two brief paths stay open-ended.** "optimizes the codebase": a passed experiment only opens a notice
(GAP 12); "fixes errors": only operator-listed tests (DECISIONS 13). Minimal closed loop inside the current safety rules:
`experiment_passed` and `already_passing`/`finding_owner` notices print a ready-to-send operator command
(`fix: tests.<id> ...` or `measure: ...`), so the operator closes the loop with one command.

---

## Platform claims checked (rg/sed, 2026-10-11) — hold unless named above

- symblicos/autogen.py: run id `autogen-` + sha256(request id)[:24]; `request_digest` over lines, base (engine, model,
  effort, node, cwd, context_note, headless) and policy without engines/nodes, 409 on a different digest; cwd must
  hold `.git`; checks run through `_run(shell=True)` with CHECK_TIMEOUT 120 in the dashboard process (finding 2);
  remote attempts are staged as a detached worktree of `main_root` under the autogen state folder; promotion =
  `work_action('commit')` + `('apply')` (finding 3).
- agent_hub.py: `make_worktree` path `<repo>.agents/<name>-<stamp>`, `provision_remote` pushes the branch to
  `~/agents-repos/<repo>.git` and adds `~/agents-work/<wt>`; catalog `ready` is a dict per engine; only `discard`
  removes worktrees.
- fleet_runner.py: `_check_capacity` one model run per node and kind (refuses at once); `symblic_apply` waits up to
  CAPACITY_WAIT 1800 s and never re-places a named node; unit RuntimeMaxSec = timeout + 60, MemoryMax/CPUQuota on the
  client unit only (finding 5); worker node num_ctx = smallest bucket (4096, 8192, ...) >= chars/3 + 256 + num_predict.
- cluster_engine.py: vitals memavail/memtotal in bytes, cpu over a 0.3 s sample (finding 9), coretemp package
  temperature; TENANT_STACKS node-h, UNMEASURED_TENANTS node-d/node-i.
- scripts/devcheck.py / scripts/devtest.py: `--changed BASE` runs tests unless `--no-tests`; devtest needs uv, a HOME
  cache and PyPI (finding 1).
- landlock_sandbox.py: Landlock scope SIGNAL at ABI >= 6; SYSTEM_RW includes /dev/shm (finding 17).
- symblicos/workspaces.py: the workspace marker is listed in `.git/info/exclude`, so LIFE's `git clean -ffdx` deletes
  it (harmless: nothing else reads it; a second `workspace NAME` would then refuse).
- host-checkout.service: MemoryMax=infinity, TasksMax 16725, app.slice (finding 2).
- local_research.research writes nothing; deep_research.safe_fetch checks robots, every hop and the byte cap; its
  read timeout is per read (LIFE's process timeout bounds a trickle).

FINDINGS_TOTAL=40
UNDEFINED_DETAILS=28
VERDICT=CHANGES NEEDED
