# LIFE v2: round-2 local adversarial critique

Critic: local reviewer (Claude Code subagent with read access to the live checkout), 2026-10-11.
Scope read in full: BRIEF.md, README.md, LIFE.md sections 0-18, bin/life_common.py, bin/life-tick.py,
bin/life-ctl.py, bin/life-check.py, bin/life-status.py, bin/life-seed.sh, genome/*.sym (9), organs/*,
policies/*, checks/*, db/*.sql, spawn/PROTOCOL.md, spawn/example/division.json, units/*,
benchmarks/benchmarks.example.json, VALIDATE.sh, workshop/LOG.md, workshop/round-1/decisions.md.
Nothing was run except `life_common.contract_problems()` (returns `[]`) and a pure-Python call of
`life_common.genome_protected_problems` on genome text (finding 2). No model, agent, task or cluster job.

Tags: **[CODE]** = verified against the platform or kit source with rg/sed (file:function given).
**[U]** = an undefined or ambiguous detail (counted in UNDEFINED_DETAILS). Severity: high / medium / low.
Per the round-2 rule, every kit claim the code contradicts is marked high.

---

## High

### 1. Selfdev can never pass its own check: `genome-protected` compares the file with itself [CODE]
- **Where:** policies/selfdev.json line 6 (check `life-check.py genome-protected genome/{program}.sym`);
  bin/life-check.py lines 46-52 (`git show HEAD:<file>`); LIFE.md 7.6.
- **Defect:** autogen verifies a worker node attempt in a *detached staging worktree of the fetched agent ref*
  (`symblicos/autogen.py:_stage_remote`: `hub.work_action('commit')`, then
  `git worktree add --detach -f STAGING refs/agents-nodes/<node>/<branch>`; `_verdict` runs every check
  with `cwd = verify_in` = that staging tree). HEAD there **is the agent's commit**, so
  `git show HEAD:genome/P.sym` returns the agent's new text; `genome_protected_problems(new, new)`
  returns `['no ask instruction changed']`. Every LIFE agent run is remote (cell nodes are worker nodes), so
  statement 0 of every selfdev run fails its check and the selfdev organ can never produce a proposal.
- **Fix (adopt):** `sync_selfdev` also writes and commits `genome-base/<name>.sym` (byte copy of the active
  release). Check 0 becomes
  `python3 -B {kit}/bin/life-check.py genome-protected genome/{program}.sym genome-base/{program}.sym`
  and `life-check.py genome-protected NEW BASE` compares the two files (both must resolve inside cwd, no
  `..`, regular files). The statement adds: "keeping every file under genome-base unchanged". The tick's
  gate (gate_proposal) keeps comparing against `STATE/release/<n>/genome/` so an agent that edits
  genome-base still fails at home.

### 2. The protected-line rule misparses enum asks: it lets a proposal swap enum meanings and forbids real instruction edits [CODE]
- **Where:** bin/life_common.py line 593 `ASK_RX` and `genome_protected_problems`; LIFE.md 7.6 ("every ask's
  name, type and from/with clause stay byte-identical").
- **Defect:** `(.+?) "` is lazy, so for `ask side: one of {a: "the item fits the first focus better", b: ...} "Which focus ..." from ...`
  group 2 is `one of {a:` and the "instruction" is the first enum description. Verified by running the
  function on genome/assign-item.sym: replacing the real instruction gives
  `['line 7: only an ask instruction or a note may change']`; swapping the description of `a` to
  "the item fits the second focus better" gives `[]` (accepted). The same holds for
  propose-experiment.sym `ask op` and any future `one of {x: "..."}` ask. A reviewed and adopted proposal
  can therefore invert a closed choice's meaning (e.g. a/b sides, op semantics) while "only an instruction
  changed".
- **Fix (adopt):** the instruction is the LAST top-level quoted string before ` from `:
  `ASK_RX = re.compile(r'^ask (?P<name>[a-z_][a-z0-9_]*): (?P<type>.*) "(?P<instr>(?:[^"\\]|\\.)*)" (?P<tail>from .*)$')`
  (greedy `type`), and `type` + `tail` must be byte-identical. VALIDATE.sh gains negative cases:
  enum-description swap -> refused; real instruction edit of assign-item/propose-experiment -> accepted;
  removing a `{placeholder}` that names a given -> refused (code: the set of `{name}` tokens in the
  instruction must be unchanged).

### 3. Killing a program run with SIGKILL leaves the model running on the worker node [CODE]
- **Where:** bin/life-tick.py `Procs.kill_one` (lines 77-81, `os.killpg(pid, 9)`), `Procs.run` timeout path,
  `serve_nodes` STOP loop (line 1265-1266), bin/life_common.py `run_bounded`; README KILL SWITCH ("a running
  tick kills its model processes within 2 s"); LIFE.md 5 and 8.
- **Defect:** the model generation is the fleet runner run on the worker node. `bin/symblic run` cancels it only from its
  SIGTERM/SIGINT handler (`symblic_run.py` lines 5420-5426 set `stop`; `symblic_apply.Applicators._wait_run`
  then calls `ba.cancel`). SIGKILL skips the handler, so the worker node keeps generating (up to
  `timeout_seconds` 600 s per call) and keeps the node's only Ollama slot
  (`fleet_runner._check_capacity`: one model per node). `bin/local-research` has no signal handler at all
  and each step waits up to `local_research.STEP_TIMEOUT = 1800` s. Every CALL_TIMEOUT kill, every STOP
  and every thread-deadline kill therefore orphans a worker node run; the next tick's call on that node waits or
  fails `no capacity` -> `infra` -> node hold (finding 7 loop).
- **Fix (adopt):** one kill sequence everywhere: `killpg(SIGTERM)`; wait up to 30 s; then `killpg(SIGKILL)`.
  Research runs go through a wrapper that installs a SIGTERM handler which cancels its fleet-runner run (role
  label `life-<call_id>`), or LIFE cancels the fleet runner runs whose role starts with `life-` after a kill through
  the in-process `fleet_runner.cancel` (the call `symblic_apply` already uses). README: "STOP ends
  local processes within 2 s and asks the fleet runner to cancel their worker node runs within 35 s".

### 4. The kill switch depends on release integrity, and "within 2 s" holds only in one phase [CODE]
- **Where:** bin/life-ctl.py `stop` (lines 402-420: builds `mod.Tick(conn)`); bin/life-tick.py `Tick.__init__`
  (lines 92-104: `active_release`, `load_organs`, increments `tick_no`), `main` (line 1645 builds Tick
  before `run()` checks STOP); README KILL SWITCH; LIFE.md 5.
- **Defect:** a missing/corrupt active release or organs.json raises in `Tick.__init__`, so neither
  `life-ctl stop` nor any tick ever reaches `stop_everything`: runs are not cancelled, every tick faults.
  STOP is checked by the running tick only between phases and every 2 s inside `serve_nodes`; the
  watched test (600 s), devcheck gate (900 s), fetches (4 x 90 s), division clone (600 s), catalogue
  (60 s) and canaries (10 x 120 s) are never interrupted. `life-ctl stop` also increments `tick_no`
  (shifts the canary/storage schedule).
- **Fix (adopt):** `stop_everything(conn, procs)` becomes a module function needing only the registry;
  `main()` checks `STOP_FILE` immediately after the lock, before any release load. A daemon watcher thread
  started at tick begin polls STOP every 1 s and calls `procs.kill_all()` (finding 3 sequence) for the
  whole tick. All tick subprocesses (git, gate, fetch, catalogue, canaries) run through `Procs.run`.
  Define: "STOP: local LIFE processes end within 2 s + 30 s grace; worker node model runs are cancelled within
  35 s; each autogen cancel call is bounded by 60 s; benchmark cancel by 30 s".

### 5. Agent-written code runs unsandboxed on the host, and the codebase gate runs the patch's own judge [CODE]
- **Where:** policies/codebase.json check 0 (`python3 -s -m unittest {test_id}`), checks/devcheck-gate.sh
  (imports the test module, `./bin/devcheck`, unittest), LIFE.md 1 ("No worker can reach STATE"),
  LIFE.md 7.4.
- **Defect:** autogen policy checks run through `symblicos/autogen.py:_run` (nice 10, scrubbed env, own
  session, **no sandbox**; only designer scripts use `sandbox_prefix`/Landlock) on the host in the staging
  tree, i.e. the agent's code executes as user operator with read/write access to `~/.local/state/life`
  (control/STOP, ARMED, the registry), `~/.ssh`, `.env`. The tick's gate does the same and also runs
  `./bin/devcheck`, which imports `scripts/devcheck.py` **from the clone**: a `local_fix` patch may edit
  `bin/devcheck`, `scripts/devcheck.py`, `bin/devtest` or test helpers and so decide its own gate. Only
  `tests/` is protected, and only for non-test classes.
- **Fix (adopt):** (a) gate refuses any patch touching `bin/`, `scripts/`, `tests/__init__.py`,
  `tests/**/conftest.py`, `.agents/`, `docs/life/`, `.gitignore`, `security_gate.py`,
  `register.py`, `*.service`, `*.timer`, `sw.js` (list kept in `life_common.GATE_DENY_RX`); (b) the gate
  runs the live checkout's judge on the clone: `/usr/bin/python3 /home/operator/host-checkout/bin/devcheck`
  with cwd = clone only after confirming devcheck reads its rules from cwd (verify; else copy the live
  `scripts/devcheck.py` into a temp dir); (c) every execution of agent-written code (autogen check 0 and
  the gate) runs under the existing Landlock wrapper (`landlock_sandbox.py --require`, as
  `symblicos/autogen.py:sandbox_prefix` builds it) with HOME a temporary folder and STATE, `~/.ssh`,
  `~/.config`, the live checkout and `.env` invisible; until (c) exists the codebase organ accepts only
  `comment_or_doc` (no agent code is executed). LIFE.md 1 must not claim workers cannot reach STATE until (c) holds.

### 6. The governor cannot see LIFE's own load, and no worker node has a duty-cycle limit [CODE] [U]
- **Where:** bin/life-tick.py `metabolism` (lines 183-253); LIFE.md 10 ("percent busy over the probe
  interval"); BRIEF ("keep continuous all-worker node load under about an hour before resting").
- **Defect:** `vitals.cpu` is a 0.3 s `/proc/stat` difference (`cluster_engine.py` PROBE_SH lines 207-211)
  sampled once at tick start, after the previous tick's threads finished and after the >= 300 s timer gap,
  so LIFE's program runs are invisible. "Fleet loaded" needs 3 of 5 worker nodes at >= 50 %; one worker node
  (e.g. node-f with command + immune, or node-i with 1-hour agy runs back to back) can run LIFE work
  continuously for days. Only the 85 °C trip protects it.
- **Fix (adopt), per node and fleet:** `busy(node, t0, t1)` = seconds within [t0, t1] covered by the union of
  LIFE intervals on that node: `calls.started_at..ended_at`, `runs.submitted_at..ended_at` (live runs to
  now), benchmark `started..now/ended`. A node RESTS (no new LIFE action) when
  `busy(node, now-3600, now) >= 3000` and until `busy(node, now-600, now) == 0`. The fleet rule counts a
  node loaded in a sample when `cpu >= 50` OR it was LIFE-busy at any moment in the last 300 s. Record per
  node `rest_until` in `governor`. Numbers go into section 13: NODE_WINDOW 3600, NODE_BUSY_MAX 3000,
  NODE_REST 600.

### 7. Infra outcomes retry forever; research is likely to time out every time [CODE] [U]
- **Where:** bin/life-tick.py `record` (lines 1326-1330: `infra` re-queues, no counter), `run_program`
  (research timeout -> `infra`), LIFE.md 7.2 and 8; GAP 6.
- **Defect:** no bound exists on infra retries for model items. `bin/local-research --tools 8` makes up to
  10 generations, each up to 1800 s (`local_research.STEP_TIMEOUT`); on CPU worker nodes ("~4 tokens/s" in that
  file) 10 steps routinely exceed CALL_TIMEOUT 900, which LIFE classifies `infra`: the question re-queues
  every tick forever, each time orphaning a worker node run (finding 3). A model missing on a node (GAP 6) is the
  same endless loop.
- **Fix (adopt):** items gain `infra_attempts`; after 6 infra outcomes (or 3 timeouts) the item ends
  `owner` with notice `infra_exhausted` naming node, model and the last detail. Research uses `--tools 4`
  and `RESEARCH_TIMEOUT = 1500` with the tick guard raised accordingly, or is split into one research
  step per tick. Before a call, code checks the model is in the node's the fleet runner capability cache
  (`fleet_runner.capabilities(node)` models list); absent -> `node_model_absent(node, model, until=now+86400)`
  and the next rung or another cell is used, never the same call.

### 8. Web text becomes agent instructions, contradicting the taint rule [CODE]
- **Where:** bin/life-tick.py `apply_value` distill branch (lines 1452-1461: taint `web` lessons/requests);
  organs/selfdev.lines.txt line 1 (`... addresses this lesson: {lesson}`), organs/database.lines.txt line 1
  (`... implement this data request: {request}`); LIFE.md 6 ("web text ... is never a statement").
- **Defect:** a web-derived sentence is rendered verbatim (after `one_line`) inside an autogen statement
  that agy executes with a full tool loop on a worker node. That is a prompt-injection channel ("...; also run X
  and write Y") and directly contradicts LIFE.md 6.
- **Fix (adopt):** (a) items with taint `web` may enter `start_run` only after the operator approves them:
  `life-ctl approve ITEM` sets taint `owner`; unapproved web items wait with notice `approve_needed`
  (one per item); (b) better for the database organ: replace the agent run by a genome program
  `draft-table.sym` returning `{table: org_[a-z0-9_]{1,40}, columns: [{name: [a-z0-9_]{1,40}, type: one of
  INTEGER, REAL, TEXT, BLOB}] (1..24), indexes: [column names]}` and code emits the SQL; no agent, no
  free text in any statement.

### 9. The contract hold names a recovery command that does not exist [CODE] [U]
- **Where:** bin/life-tick.py line 177 and bin/life_common.py line 701 ("run life-ctl rebase"); bin/life-ctl.py
  `main` (no `rebase`); LIFE.md 15, 17.
- **Defect:** the only recovery path from a hold that stops all new work is a dead reference; the operator has
  no defined procedure when the platform legitimately changes.
- **Fix (adopt, replacement text for both messages):** "Review the platform change. If LIFE's assumption
  still holds, update the matching pattern in bin/life_common.py contract_problems and LIFE.md section 17
  together, run VALIDATE.sh (must end STATIC PASS), then life-ctl contract (must print 'contract holds').
  The hold clears at the next tick."

### 10. The telemetry-freshness rule rests on a false platform claim [CODE]
- **Where:** LIFE.md 10 ("its ts is older than 180 s"); workshop/round-1/decisions.md G48 ("serves a cached
  probe; 15 s would hold LIFE permanently"); bin/life-tick.py `metabolism` lines 188-190.
- **Defect:** `cluster_engine.py` route `status` returns `'ts': int(time.time())` at response time and
  `probe_all` re-probes when its cache is older than `STATUS_CACHE_SEC = 2.0`. The 180 s rule can never
  fire, and the G48 rationale is wrong.
- **Fix (adopt):** drop the `ts` rule. Hold when the request fails or takes > 60 s; per node, treat
  `online: false` or a missing `vitals.cpu`/`vitals.temp`/`vitals.memavail` as unavailable (already done);
  correct decisions.md G48.

### 11. Commands get no answer: the command loop has no output organ
- **Where:** LIFE.md 2, 7.1-7.3; bin/life-tick.py `apply_value` local-research branch (the `answer` field of
  `bin/local-research` is discarded); commands.state never reaches `done`; no CLI reads knowledge.
- **Defect:** the brief's "continuously takes commands" has no reply. A research command yields sources and
  private knowledge rows the operator cannot see except through raw SQLite; patches/experiments surface only
  as separate notices with no link to the command.
- **Fix (adopt):** a `report` step (code, the host): when every item whose `origin` chain leads to a command
  is terminal, write `STATE/operator/reports/<command_id>.md` (command text, route, research answers with
  their model and node, sources, quote-verified facts with URLs, patches/proposals/experiments with
  states), set `commands.state='done'`, open notice `command_done`. `life-ctl report CMD` prints it.
  Keep the research `answer` (<= 4000 characters, taint web) in a `answers` table.

### 12. Items re-queued on retired or quarantined cells are stranded forever [CODE]
- **Where:** bin/life-tick.py `dispatch` (only `cell_id IS NULL`), `start_agent_runs` and `plan_slot`
  (only `active`/`dividing` cells), `collect_run`, review `needs_work` (line 1486); spawn/PROTOCOL.md 2.3
  ("Items the parent is still running ... stay with the parent's id").
- **Defect:** an agent item that was running when its cell divided, was retired by the operator, or was
  quarantined is re-queued later (infra retry, STOP, reviewer `needs_work`) still pointing at that cell;
  nothing serves it and no notice is opened.
- **Fix (adopt):** first statement of `dispatch`:
  `UPDATE items SET cell_id=NULL WHERE state='queued' AND stage NOT IN ('gate','apply') AND cell_id IN (SELECT cell_id FROM cells WHERE state IN ('retired','quarantined'))`.
  Gate/apply stages keep their cell (their workspace holds the promoted change) and are served regardless
  of cell state (already true in `host_stages`).

---

## Medium

### 13. STOP re-queues items whose runs it could not cancel (double run, wrong workspace) [CODE]
- **Where:** bin/life-tick.py `stop_everything` lines 158-162.
- **Defect:** all `running` items become `queued`, including those whose cancel failed (`unresolved`). After
  `unstop` the item can be dispatched/divided to another cell and started again while the old run lives;
  when the old run completes, `collect_run` moves the item to `gate` under the new cell, whose workspace
  does not hold the promoted change.
- **Fix:** re-queue only items whose run row became `cancelled`; items of unresolved runs stay `running` and
  are reconciled by `poll_runs`.

### 14. "Refused" from bin/symblic-task does not prove the run does not exist [CODE]
- **Where:** bin/life-tick.py `start_run` lines 814-822; bin/symblic-task `request` line 151 (every HTTP
  error, 5xx included, exits REFUSED = 1).
- **Defect:** a 500/502 after the server wrote the run record is marked `not_submitted`; the next attempt
  uses a new request id, so the first run lives on unpolled and uncancelled.
- **Fix:** on rc 1 or 2, `GET /api/symblicos/autogen/get?id=<expected run_id>`: 404 -> `not_submitted`;
  200 -> `live` (policy sha check as usual); no answer -> `unknown`.

### 15. Blocked work triggers division and queues grow without bound [U]
- **Where:** bin/life-tick.py `lifecycle` (backlog = all queued items), LIFE.md 9, 13.
- **Defect:** selfdev items while SELFDEV_ARMED is off, compute items without benchmarks.json, and agent items
  on nodes where agy is not ready all count as backlog: cells divide to hold work nobody can do. No queue
  cap exists; every top-rung program failure adds a selfdev lesson (identity includes the error text).
- **Fix:** backlog counts only *workable* items (organ switch on, prerequisites present, node ready).
  QUEUE_CAP_PER_ORGAN = 200 queued items; beyond it new items of taint `web`/`code` end `abstained`
  (outcome `OVERFLOW`, one notice per organ per day); operator items are never dropped.

### 16. A permanently failing watched test regenerates a finding every 6 hours [U]
- **Where:** bin/life-tick.py `findings` (identity = test, base commit, first error line; "one open
  finding" only while queued/running); LIFE.md 7.4.
- **Defect:** after the finding ends `owner`/`failed`, each new commit on the branch yields a new identity:
  triage and agent runs repeat on an unfixable test indefinitely.
- **Fix:** `watch_state(test_id, last_finding, last_outcome, next_due)`; after an `owner` or `failed` ending
  the test is skipped until the operator acks the finding notice or the normalised first error line
  changes; consecutive failures back off 6 h -> 12 h -> 24 h -> 48 h (cap).

### 17. Autogen checks time out at 120 s; the watch list has no duration rule [CODE] [U]
- **Where:** policies/codebase.json check 0; `symblicos/autogen.py` `CHECK_TIMEOUT = 120` (`_run_checks`);
  LIFE.md 7.4 (watched test timeout 600 s).
- **Defect:** a watched test that runs 120-600 s passes the finding stage but fails check 0 on every
  attempt (CHECK_FAILURE), consuming agent runs.
- **Fix:** `findings` records the test's wall time; a test over 90 s gets notice `watch_too_slow` and is
  never patched. README: "watch.txt: unittest ids that finish in under 90 s".

### 18. Free text that trips lint warnings sends items to the operator [CODE]
- **Where:** bin/life_common.py `render_run` (zero findings, warnings included);
  `symblic_autogen.lint` line 250 (`the previous|the last|as before|like above|earlier`), 1500-character warning.
- **Defect:** test output, reviewer reasons ("Reviewer asked: ..."), lessons and requests often contain
  "the last"/"earlier"; the item then ends `owner` with a `render` notice.
- **Fix:** before render, code rewrites those phrases in placeholder values (`the last` -> `the final`,
  `earlier` -> `before`, `the previous` -> `the prior`, `as before` -> `as stated`, `like above` -> `as stated`)
  and caps each value so every statement stays under 1400 characters.

### 19. A child's focus has no effect after division [U]
- **Where:** bin/life-tick.py `dispatch` (fewest queued items, focus ignored); genome/reproduce.sym,
  assign-item.sym; LIFE.md 1, 9.
- **Defect:** after commit, new items go to whichever sibling has the shortest queue, so foci are labels and
  reproduction is plain load-balancing; the brief's "cells with different functions" is not met and the
  assign-item calls buy nothing beyond the first partition.
- **Fix (choose one, write it in LIFE.md 9):** (a) dispatch among >= 2 active siblings runs assign-item once
  per new item (counted in PROGRAM_RUNS_PER_DAY) and gives the item to that focus; or (b) state that foci
  are display labels and remove assign-item (parity split only).

### 20. The compute pass criterion is chosen by the model and measured once, in a biased order [U]
- **Where:** genome/propose-experiment.sym (`op`, `threshold_pct`), bin/life-tick.py `start_bench`
  (`items: [param, baseline]`), `poll_benches`; LIFE.md 7.7.
- **Defect:** a model can choose `le 10000` (always passes); the template does not say whether lower or
  higher is better; one candidate-then-baseline pair has warm-up and thermal order bias. "Experiment
  passed" is not evidence.
- **Fix:** template fields `better: "lower"|"higher"` and `min_gain_pct` (operator, 1..90). The model picks only
  benchmark id and parameter. Items `[baseline, param, baseline, param, baseline, param]` (the per-node
  output keeps order with `parallel 1`); pass iff every pair improves in the `better` direction and the
  median gain >= `min_gain_pct`. Drop `op`/`threshold_pct` from the genome and the `experiments` table.

### 21. high-power mode leases and their rest period are ignored [CODE]
- **Where:** bin/life-tick.py `metabolism` reads only `cool.phase`; `cluster_highpower.view` returns
  `enabled`, `phase`, `restUntil` (rest 5-60 min after a lease, `REST_MIN, REST_MAX = 300, 3600`).
- **Fix:** hold new worker node work while high-power mode `enabled` is true or `restUntil > now` (reason
  `highpower lease or rest`); never treat a lease as spare capacity for LIFE.

### 22. Storage grows without a retention rule, and part of it is not counted [U]
- **Where:** LIFE.md 3, 12, 13 (STATE_MAX_BYTES only for STATE); bin/life-tick.py `storage`.
- **Defect:** STATE/calls/<id>/ (up to 1200 run folders a day), STATE/runs, the `samples` table
  (5 rows a tick), `calls`, `cell_events`, `organism-before-*` backups, `local_research_data/` reports in the
  live checkout, and the codebase clones (the repository pack is 745 MiB, `--no-hardlinks` copies it per
  clone) all grow forever; only STATE counts. The "perpetual" organism eventually holds on storage and
  stays held until the operator deletes files.
- **Fix:** retention (code, daily at the backup tick): call folders of terminal items older than 14 days
  deleted; `samples` older than 7 days deleted; `organism-before-*` keep the newest 10; workspaces under
  PROJECTS/life-* counted in the storage total; codebase clones made with
  `git clone --single-branch --branch <branch> --filter=blob:none` from the live checkout. STATE_MAX_BYTES
  then covers STATE + workspaces.

### 23. An organ halts permanently when its last cell is quarantined or its node disappears [U]
- **Where:** LIFE.md 9 endings, bin/life-tick.py `lifecycle`; no `move` command in life-ctl.
- **Defect:** extract-source and propose-experiment have one-rung ladders; 8 failed items in a row quarantine
  the only digest cell and the whole learning pipeline stops until the operator acts. A worker node that is powered
  off (node power release) or removed leaves its cells unserved forever.
- **Fix:** agent workspaces live on the host, so re-homing is code-only: a cell whose node has been offline
  for >= 6 h moves to the node `child_node` picks (event `moved`, notice). `life-ctl move CELL NODE` for the
  operator. Last-cell quarantine: notice at once plus an automatic release after 24 h with its program rungs
  set to the top rung; a second quarantine within 7 days waits for the operator.

### 24. Agent organs are probably blocked from the start; the README has no readiness step [U]
- **Where:** README "Start it"; LIFE.md 7.9 placement, GAP 10; BRIEF ("CLI logins exist on the host").
- **Fix:** README step 3b: run `bin/symblic-task catalog --json` and confirm `ready.agy` is true for node-i,
  node-a and node-b (the agent seed nodes); if not, log agy in on those worker nodes (the worker node CLI login
  procedure) or edit organs.json seed nodes before seeding. LIFE.md 7.9: "Until then the codebase,
  selfdev and database organs do nothing; this is expected, not a fault."

### 25. The kit departs from binding operator words without stating the precedence [U]
- **Where:** BRIEF (10 Oct words: regenerate until complete or split; no time cap; spawn as many agents as
  needed; research may run for days) vs policies (`until_done false`, `self_split false`, 2 live and 12 daily
  agent runs, 900 s calls, 3 dry research runs); decisions.md does not cite these words.
- **Fix:** LIFE.md section 0 gains: "Precedence: heat and rest rules, budgets and the kill switch override
  until-done and no-time-cap. Within them, the caps live in control/limits.json (operator file, bounded by
  LIMITS in life_common: AGENT_RUNS_LIVE_MAX 1..6, AGENT_RUNS_PER_DAY 0..48, QUESTION_DRY_LIMIT 1..20,
  CALL_TIMEOUT 300..1800)." The operator signs off this deviation in the next workshop round.

### 26. The backup restore procedure corrupts a WAL database [U]
- **Where:** LIFE.md 12 ("stop the timer, copy a backup over the file, start the timer").
- **Fix (replacement text):** "Restore (operator): `systemctl --user stop life-tick.timer`; wait until
  `flock -n STATE/tick.lock true` succeeds; move `life.sqlite3`, `life.sqlite3-wal` and `life.sqlite3-shm`
  into `STATE/backups/replaced-<UTC time>/`; copy the backup to `life.sqlite3`; `chmod 600`; run
  `bin/life-check.py registry` (must print pass); `systemctl --user start life-tick.timer`. The same for
  organism.sqlite3."

### 27. The coordinator code itself is not pinned [U]
- **Where:** bin/*, checks/*, units/* executed from the live checkout; decisions.md G1/G25.
- **Defect:** any agent, Codex session or cloudsync pull that edits docs/life/bin changes the running
  coordinator at the next tick with no validation; a LIFE patch (local_fix) may itself target the kit.
- **Fix:** `life-ctl arm` writes ARMED as JSON `{boot_id, kit_sha256}` where kit_sha256 hashes bin/*,
  checks/*, db/*.sql, units/* in sorted order; the tick holds (`integrity: kit changed since arm`) when it
  differs, so unrelated repository commits never hold LIFE. The gate refuses patches touching
  `docs/life/`.

### 28. Division commit clones a 745 MiB repository inside the tick, and a failed clone is never retried [CODE]
- **Where:** bin/life-tick.py `division_commit` -> `make_workspace` (lines 1011-1025), called from
  `serve_nodes` before the model threads.
- **Defect:** a 600 s clone plus the 960 s slot phase exceeds `TimeoutStartSec=1500`; a failed clone leaves a
  committed child whose workspace never exists (start_agent_runs silently skips it forever).
- **Fix:** clone into `PROJECTS/.life-tmp-<hex8>` BEFORE the commit transaction (abort the division on
  failure), rename after commit; only when `time_left() >= 900 + 600`; a lifecycle sweep re-creates any
  missing workspace of an active agent cell (one per tick, notice on failure).

### 29. Inbox writes race the tick and can overwrite each other [CODE]
- **Where:** bin/life-ctl.py `command` (`write_atomic` creates `NAME.tmp-PID` inside `inbox/`); bin/life-tick.py
  `ingest_inbox`.
- **Defect:** a tick listing the inbox moves the temp file to `inbox-refused/` (name rule), then life-ctl's
  `os.replace` fails; two commands in the same second with the same slug share a name and the second
  overwrites the first.
- **Fix:** write the temp file in `STATE/inbox-tmp/` and rename into `inbox/`; name
  `<YYYYmmddTHHMMSSZ>-<slug>-<4 random hex>.txt` (name rule updated); `ingest_inbox` skips names
  containing `.tmp-`.

### 30. MemoryMax=1G also bounds the gate, the watched tests and the clones [U]
- **Where:** units/life-tick.service; all tick subprocesses share its cgroup (page cache counts toward
  memory.max in cgroup v2).
- **Fix:** run gate, watched tests and clones in their own transient scope
  (`systemd-run --user --scope -p MemoryMax=4G -p CPUQuota=200% -p Nice=19`), in the work slice if
  that user slice exists (CLAUDE.md: new local workloads get separate work.slice scopes; verify the
  slice name in the user manager first); state the measured peak in LIFE.md 13.

### 31. Numbers are not single-sourced as LIFE.md claims [U]
- **Where:** LIFE.md 0 and 13 ("Every number has one definition, in bin/life_common.py").
- **Defect:** bin/life-tick.py defines or hard-codes MAX_INFRA_ATTEMPTS 3, FETCHES_PER_TICK 4, the division
  timeout 3 x 3600, run_unknown notice 900 s, needs_work limit 2, inbox 50 per tick, 40 tail lines,
  watched-test timeout 600, gate timeout 900, fetch timeout 90, catalogue timeout 60, time guards 700 /
  960 / 200, jobs limit 200, sample text 1600, assign maximum 16; none is in section 13.
- **Fix:** move each into life_common with a comment and a section 13 row; VALIDATE.sh greps life-tick.py
  for integer literals >= 10 outside an allow-list.

### 32. Long holds are silent [U]
- **Where:** LIFE.md 14 (kind list includes "telemetry-driven holds", which no code opens); governor,
  storage-free holds and observe-only exits open no notice.
- **Fix:** notice `held` (subject = the first reason) after 12 consecutive non-working armed ticks, closed
  automatically when work resumes; remove the non-existent kind from the list.

### 33. `local_fix` scope is only a prompt [U]
- **Where:** bin/life-tick.py `gate_patch`; LIFE.md 7.4 ("the source files the failure names").
- **Fix:** code extracts repository-relative paths from the finding's traceback lines
  (`File "<clone>/<path>.py"`); a local_fix patch may touch only those files (at most 3) plus nothing under
  the finding 5 deny list; otherwise refused `out of scope`.

### 34. The organism database is created but never filled or read
- **Where:** LIFE.md 7.8, 12; db/organism.sql; brief ("creates databases ... new ways to store data").
- **Defect:** migrations add empty `org_` tables; no organ inserts rows or reads them, so the database has no
  producer and no consumer.
- **Fix:** define one producer and one consumer: knowledge facts and research answers that a request names
  are inserted by code into the new table (column mapping chosen by a typed program, values copied by
  code from registry rows only); the report step (finding 11) lists table row counts. Otherwise state
  plainly that LIFE creates schemas only.

### 35. Proposal and patch identities can drift from what was reviewed [CODE]
- **Where:** bin/life-tick.py `gate_proposal` (proposal_id = the lesson item's hex; bundle files overwritten,
  `INSERT OR IGNORE`); bin/life-ctl.py `adopt` (never compares the bundle with `proposals.new_sha256`);
  `gate_patch` (an identical diff re-bundled after a rejection gets no new review).
- **Fix:** `proposal_id = sha16(item_id, new_text)`; `adopt` refuses unless `sha(bundle text) ==
  new_sha256`; a re-bundled patch whose row is `rejected` ends the finding `owner` with a notice.

### 36. Retiring a dividing cell resurrects it [CODE]
- **Where:** bin/life-ctl.py `retire` (allows `dividing`); the open division later commits two children.
- **Fix:** `retire` aborts the cell's open division first (`stage='aborted'`, reason `owner retire`), then retires.

### 37. A persistent tick fault reruns every 5 minutes forever [U]
- **Where:** bin/life-tick.py `main` (exit 1, notice deduplicated by exception type); units (timer re-runs).
- **Fix:** meta `faults_in_a_row`; at 3 the tick runs observe-only (`fault hold`) until `life-ctl clear-fault`;
  notice `tick_fault` names the count.

### 38. "Optimizes the codebase" has no path
- **Where:** LIFE.md 2, 7.4 (findings only from failing watched tests or operator commands).
- **Fix:** either an operator-approved optimisation source (benchmark templates over repository functions,
  `better`/`min_gain_pct` per finding 20, a `perf_fix` change class gated by the benchmark) or an explicit
  "out of scope in v2" line in LIFE.md 0 for the operator to sign off.

### 39. Learning never asks its own questions
- **Where:** LIFE.md 7.2 (questions only from operator commands); LOG.md "open for round 2".
- **Fix:** code turns at most 2 lessons a day (target `none` excluded) into follow-up questions
  (`question` items, taint web, priority 0, identity = normalised text), deduplicated against all earlier
  questions; operator can switch it off with `control/NO_SELF_QUESTIONS`.

---

## Low

40. **[U] read_page length.** `local_research.read_page` returns up to 6000 characters plus `\n[…page continues…]`;
    LIFE.md 3/7.3 say "at most 6000". Strip the marker before storing; state "6000 + marker" otherwise.
41. **[U] ratio rounding.** LIFE.md 7.7 says `floor`, code uses `int()` (truncation); `RESULT_RX` admits negatives.
    Use `math.floor` and refuse values <= 0.
42. **[U] PROTOCOL 2.1 vs code.** "the first 12 queued items' labels"; code joins all snapshot labels and cuts at
    1600 characters. Make the code take 12.
43. **[U] review size unit.** `review_inputs` compares bytes (`getsize`) with "6000 characters". Say bytes, or read
    and count characters.
44. **[U] tick-counted durations.** APOPTOSIS_IDLE_TICKS 288 ("about a day"), DIVIDE_SUSTAIN 3, CANARY_EVERY_TICKS 12
    are 1-6x longer in time because ticks are 300 s plus tick duration. Define them in seconds.
45. **[U] step lists disagree.** life-tick.py docstring (12 steps) vs LIFE.md 4 (15 steps); the start-of-tick
    re-queue of `running` model items (run(), line 1595) and exit 5 for a schema mismatch are undocumented.
46. **Credential screen too broad.** `SECRET_RX` refuses any command containing "password" or "secret key"
    ("research password hashing"). Match assignment shapes (`password\s*[:=]\s*\S{6,}`) plus the token patterns.
47. **[U] cool phase.** Code treats a missing `cool.phase` as off; LIFE.md 10 says unreadable = hold. Require `== 'off'`.
48. **Module derivation in devcheck-gate.sh** (`${test_id%%.[A-Z]*}`) fails for lowercase class names; resolve the
    longest importable prefix instead.
49. **Unit details.** `After=network-online.target` has no effect in a user manager; before seeding,
    `WorkingDirectory` is missing and the unit fails with 200/CHDIR instead of exit 6.
50. **Committed history carries private data.** `.backups/[path removed for publication]`
    is tracked; every codebase clone and every agy checkout on a worker node receives it. Clone with a sparse
    checkout excluding `.backups/`, and add `.backups/` to the gate deny list.
51. **VALIDATE.sh canaries** always prints `PASS canaries` even after a `bad canary` line (the exit code is still right).
52. **[U] model_calls** is counted but never budgeted. Add MODEL_CALLS_PER_DAY or drop the column.
53. **[U] experiment re-measurement.** identity (benchmark, param) forbids re-running an experiment that failed for
    infrastructure reasons. Allow a re-run when the previous state is `failed` with a non-semantic outcome.
54. **[U] memory estimate.** MODEL_MIB counts weights only, while the fleet runner sizes `num_ctx` to the prompt up to
    `node_num_ctx` 32768 (fleet_runner settings); state the KV allowance (e.g. +1024 MiB for extract-source).
55. **[U] abstention masks broken cells.** `abstained` resets `failures_in_a_row`; a program that always abstains is
    never noticed. Notice `abstain_rate` when >= 90 % of a cell's last 20 items abstained.
56. **Tests and gates run on the host.** Watched tests, devcheck and clones load the host (operator: the host only
    orchestrates). Move watched tests and the gate's unittest to a worker node through the sandboxed path of
    finding 5, or bound them with the scope of finding 30 and the host load gate.

---

## Platform claims checked (rg/sed, 2026-10-11)

Held: `AutogenManager.submit` run id and `.git` rule; `normalize` sha256 excludes engines/nodes (so LIFE's
local sha matches the server's while `symblic_autogen.DEFAULTS` are unchanged; note that the flags do NOT
send perpetual/until_done/syntax/require_change/designer/final/hidden/interval_seconds/feedback_chars, so
LIFE.md 7.9 "every field explicit, none left to a server default" is inaccurate: a changed DEFAULT would
cancel every LIFE run as `policy_mismatch`; add `DEFAULTS` equality to `contract_problems`);
`apply_work` promotes uncommitted files into cwd (so `git diff --cached HEAD` in the gate is right);
`/api/cluster/map` substitutes `{{item}}` as `"$1"` (shell-safe); jobs carry `out[node].out`, status `done`;
`fleet_runner._check_capacity` one model per node; `REMOTE_ENGINES` excludes copilot; `TENANT_STACKS`
node-h; `sqlite3` CLI absent; `bin/symblic run` flags and report keys; `CAPACITY_WAIT` 1800; thermal 85/75.

Contradicted (high above): genome-protected base (1), STOP/SIGKILL vs the fleet runner cancel (3), worker isolation
(5), status `ts` freshness (10). Not verified (needs a cluster probe, which this workflow forbids): the
installed-model ladders on the five worker nodes (GAP 6) and agy readiness on node-a/b/i (finding 24).

---

FINDINGS_TOTAL=56
UNDEFINED_DETAILS=30
VERDICT=CHANGES NEEDED
