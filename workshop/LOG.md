# LIFE workshop log

## Round 1 (2026-10-11)

**Critics.** ChatGPT web, highest effort (`round-1/critique-chatgpt.md`, chat <conversation-id-removed>, sent in five
parts): 206 findings, 107 undefined details. Claude cloud, highest effort (`round-1/critique-cloud.md`,
task life-review-r1-20261011): 89 findings, 50 undefined. Local reviewer (Claude Code subagent with
the live checkout, `round-1/critique-local.md`): 54 findings, 27 undefined. Total 349 findings, 184
undefined details; all three verdicts CHANGES NEEDED. Overlap was heavy: the same dozen defects were
found by two or three critics.

**Verified against the code before acting** (read only; no model, agent, task or cluster job):
`symblic_autogen.decide` (a perpetual lane without until_done stops at `generations`, default 3),
`symblicos/autogen.py:AutogenManager.submit` (run id = `autogen-` + sha256(request id)[:24]; cwd must
hold `.git`; the local engine takes spec sheets only and refuses perpetual lanes),
`bin/symblic-task` (`autogen list` prints run ids, never `life-*`), `symblic_run.Run._apps` (an
ask-level `by` beats `--by`), `fleet_runner._check_capacity` (one model per node),
`symblic_apply` (thermal 85/75 °C, CAPACITY_WAIT 1800 s), `agent_hub._check_remote`/`REMOTE_ENGINES`
(copilot is the host-only), `cluster_engine` routes (status, capacity, map, jobs), `cluster_highpower.view`,
`local_research.read_page` → `deep_research.safe_fetch`, `command -v sqlite3` (absent on the host).
The local critic's [CODE] findings were all confirmed.

**What changed (v1 → v2).** The kit was rebuilt around one code coordinator:
- `bin/life-tick.py` (new): the only control loop, every 300 s after the previous tick ends; lock,
  STOP, integrity and platform-contract checks, governor, run and benchmark polling, inbox, canaries,
  backups, storage holds, findings, dispatch, agent runs, lifecycle, one light-model action per worker node
  in parallel threads, status. Replaces `bin/life-spawn-tick.py` and the agy lanes for metabolism and
  heartbeat (no agent runs on the host any more).
- Cells are registry rows (organ, focus, worker node, queue) with a worker (a genome program on a light model,
  or a bounded agy run for codebase/selfdev/database) and a reproducer (`reproduce.sym` +
  `assign-item.sym`). Code decides whether a cell divides; the reproducer only names foci and sorts
  items; one registry transaction births both children. The file spawn queue in the live repository is
  gone.
- Ten organs: command, learning, digest, codebase, immune, selfdev, compute, database (cells) plus
  metabolism and heartbeat (code). Every organ input now has a producer and every output a consumer:
  inbox → command → question/finding/request/experiment/lesson; learning → sources (one global dedup)
  → digest (code fetch through safe_fetch, quote-verified knowledge) → lessons/experiments/requests;
  watch list → findings → triage → patch run → devcheck gate → review → operator apply; lessons → selfdev
  proposals (protected-line rule) → review → operator adopt (releases); requests → additive org_ migrations
  applied by code; experiments → operator-approved benchmark templates via `/api/cluster/map`.
- Genome: nine programs, none with an in-file `by`; one model per call chosen by code from per-program
  ladders; `if` branches so stay/abstain paths ask nothing extra; worst-case calls <= 12 each. New:
  distill-lesson, propose-experiment, assign-item.
- State moved out of git: `/home/operator/.local/state/life` (0700) holds the registry
  (`db/life.sql`, CHECK constraints for every enum and range), the organism database
  (`db/organism.sql`), control switches (STOP, FREEZE, ARMED per boot, SELFDEV_ARMED), inbox,
  releases, call records, bundles, backups.
- Agent runs: one fixed bounded policy (agents_max 3, attempt 900 s, wall 3600 s, strategies
  fresh,feedback, self_split false, depth 0), every flag explicit, server policy sha256 confirmed,
  durable submit state machine, at most 2 live and 12 a day, the cell's node only when agy is ready.
- Metabolism: a governor over `/api/cluster/status` (3000 s work window, 600 s rest, hot at 85 °C,
  stale or missing telemetry = hold, the host load/io gate, cool mode = hold); replaces the host-only
  heat gate.
- Operator tools: `bin/life-ctl.py` (seed, arm, freeze, stop, command, notices, apply/revert with hashes,
  adopt/new-release, release-cell, retire, contract); `bin/life-status.py` read-only; `bin/life-check.py`
  for autogen checks and canaries; `units/` exact systemd files; `benchmarks/` example catalogue.
- `VALIDATE.sh`: inventory, symblic check x9, organs schema, template render + lint (zero findings) +
  normalize + fixed policy, bash -n / ast.parse, schemas twice with negative inserts, canaries,
  benchmarks, LIFE.md embedding equality, platform contract. Result after this round: **STATIC PASS**.
- Removed: organs/*.lines.txt for the seven model and code organs, their policies, checks/heat-gate.sh,
  kill-switch.sh, verify-format.sh, db/schema.sql, bin/life-spawn-tick.py, spawn/example v1 files.

**Superseded rather than rejected.** About 40 findings addressed v1 mechanisms that no longer exist
(perpetual lane saturation, interval semantics, spawn-record files, slug, symlink and size rules for
queue folders, archive name collisions, `hashes.txt`, `retired.txt`, the awk kill loop). The defects
they named cannot occur in v2 because those mechanisms were removed.

**Rejected or applied in part: 36**, one line each with the reason in `round-1/decisions.md`. The main
ones: no automatic apply to the live checkout (operator applies); no model-written shell, even sandboxed
(operator templates only); C70 was factually wrong about `--by`; Lo15(a) is out of date (local engine =
spec sheets only); telemetry freshness 180 s instead of 15 s; tick budget 1200 s instead of 30 s;
admission tests deferred because this workflow may only lint and check (GAP 8).

**Open for round 2.** Admission tests with fake API and fake bin/symblic (GAP 8); recorded fixtures for
the genome programs (GAP 9); whether 50 % CPU on 3 worker nodes is the right "fleet loaded" signal; whether the
learning organ should generate its own questions from lessons; per-job resource limits on the worker nodes.

## Round 2 (2026-10-11)

**Critics.** ChatGPT web, highest effort (`round-2/critique-chatgpt.md`, sent in eight parts, `round-2/send-log.txt`;
it saw no life-tick.py or life-ctl.py source and reviewed their specified behaviour): 224 findings, 139
undefined details. Claude cloud, highest effort (`round-2/critique-cloud.md`, task life-review-r2-20261011,
source-only snapshot without the platform files): 70 findings, 42 undefined. Local reviewer (Claude Code subagent
with the live checkout, `round-2/critique-local.md`): 56 findings, 30 undefined. Total 350 findings, 211
undefined details; all three verdicts CHANGES NEEDED. The same defects recurred across critics: the governor
blind to LIFE's own load (C1, Lo6, G34), STOP depending on the release and SIGKILL orphaning worker node runs (C5, C6,
Lo3, Lo4, G22, G23), agent code unsandboxed on the host (C2, Lo5, G8, G20), web text in agent statements (C3, Lo8,
G13), the enum-blind protected-line regex (C17, Lo2, G141), unbounded infra retries (C23, Lo7, G80), focus-blind
dispatch (C30, Lo19, G92), flagless policy fields (C8, G50, G51), the dead `life-ctl rebase` (C27, Lo9, G158).

**Verified against the code before acting** (rg/sed only; no model, agent, task, tick or cluster job):
`symblicos/autogen.py` (`_stage_remote` stages a detached worktree of the fetched agent ref, so `HEAD` there is the
agent's commit: Lo1 confirmed; `_run` runs policy checks with the real HOME and no sandbox; `CHECK_TIMEOUT = 120`;
`sandbox_prefix` and `landlock_sandbox.py --require` exist; a run row carries `policy` with `sha256`;
`AutogenManager.get` reads the local run store), `symblic_autogen` (`DEFAULTS` for the flagless fields, `VERSION = 1`,
`normalize` excludes engines/nodes from the sha, `items_key` can return 204 characters), `bin/symblic-task`
(`parse`/`autogen_policy` flag mapping, HTTP errors exit REFUSED, the AUTOGEN_FOLDER note maps the host path
for remote agents), `cluster_engine` (status `ts` is the answer time and the probe cache is 2 s: round-1 G48 was
wrong; map passes `{{item}}` as `"$1"` through xargs; jobs list pages of up to 200 with offset;
`TENANT_STACKS`/`UNMEASURED_TENANTS`), `cluster_highpower.view` (`enabled`, `restUntil`, `cool`),
`symblic_run` (SIGTERM handler) and `symblic_apply._wait_run` (cancels the fleet runner run), `fleet_runner`
(`cancel`, `unit_argv` limits), `local_research` (`STEP_TIMEOUT` 1800 read at call time, `read_page`'s
continuation marker, `bin/local-research` always writes a report into the live checkout), `deep_research.safe_fetch`
(hop limit, byte cap, RuntimeError refusals), `scripts/devcheck.py` (root from cwd, `--changed BASE`), the user
slices (`work.slice` active), and `git ls-tree HEAD` (a private database under `.backups/` is tracked).

**What changed (v2 → v2.1).**
- Kill switch: one process runner (`life_common.Procs`: temporary-file output, SIGTERM then SIGKILL after 30 s, a
  16 MiB output kill); a STOP watcher thread for the whole tick; STOP handled before the release loads;
  `stop_everything` needs only the registry and re-queues only what was confirmed cancelled; `life-ctl stop`
  cancels runs and jobs itself without the lock; `bin/life-research.py` cancels its fleet-runner runs on SIGTERM; the
  unit gets TimeoutStopSec, KillMode and a SIGTERM handler.
- Governor: LIFE's own load ledger (calls, runs, jobs per node) counts toward fleet load; a per-node duty cycle
  (3000 of 3600 s → rest 600 s); high-power mode leases and rest hold; cool must be exactly off; telemetry values
  validated; the `ts` age rule dropped; telemetry re-read before the slot phase; notices for missing temperatures
  and long holds.
- Sandbox and gate: codebase check 0, the gate and watched tests run only in the Landlock launcher in
  work.slice scopes; the gate diffs against the recorded base, resolves the test module without importing,
  runs the base commit's own devcheck (bin/, scripts/, rules/ and the rest of `GATE_DENY_RX` are refused), refuses
  binaries, mode changes, oversize diffs, weakened tests, local_fix outside the traceback's files, and a tree the
  gate changed; one interpreter (`/usr/bin/python3`).
- Selfdev: `genome-base/` travels with the run (Lo1); the protected-line rule takes the LAST quoted string as the
  instruction, protects notes, blank lines, indentation and placeholders; base release pinned; proposal ids bind
  the text; `adopt` checks the reviewed bytes; `owner`/`stale` proposal states.
- Taint: web/model lessons and requests wait for `life-ctl approve`; statements mark quoted text as data;
  failure lessons are code-written; taint propagates to derived items.
- Commands: reports (`STATE/operator/reports/<id>.md`, `life-ctl report`), research answers kept, `done`/`failed`
  command states, heartbeat answers, merged-command notices, operator agenda (`control/agenda.json`), derived
  questions (2 a day), a random-suffixed inbox name written through `inbox-tmp/`.
- Codebase: watched-test outcome table (pass, timeout, sandbox, slow, error, fail), backoff 6/12/24/48 h, the
  operator-finding `confirm` stage, `CODEBASE_HISTORY_OK` (GAP 11), sparse single-branch clones, retired clones
  removed, `gate-selftest`.
- Compute: templates v2 (`better`, `min_gain_pct`, timeout 30..300); the model picks only id, parameter and
  hypothesis; 3 alternating baseline/candidate pairs scored with exact decimals; timeout over the whole process
  group plus prlimit; a job intent and label before submit; paged job lookup; a parameter character set.
- Database: sha-pinned schema snapshot; quote-aware SQL splitting; names must be new; non-org references refused;
  applied twice in memory; crash recovery by sha; migration texts kept in bundles; schema-only decision (GAP 13).
- Reproduction: workable backlog only; focus-word dispatch; one open division enforced by an index; commit
  re-checks the rules and creates workspaces first; 3-hour abort every tick; workspace sweep; one automatic release
  of an organ's last quarantined cell; offline-node moves; fair organ order; `+1` population rule; depth in
  workspace and request ids.
- Accounting: separate item counters (`attempts`, `infra_runs`, `faults`, `review_rounds`), infra capped at 6,
  budgets charged before work (model calls budgeted too), day captured once, idle and canary schedules in seconds,
  fault hold after 3 tick faults, retention (call folders 14 days, samples 7 days, pre-migration copies 10).
- Platform contract: 52 anchors (was 16), the running server's autogen defaults compared each armed tick,
  `life-ctl rebase` replaced by a written recovery procedure (section 17), ARMED binds the kit hash.
- Registry schema 3: canonical id CHECKs, organ/kind pairs, one workspace per cell, a fleet-wide open-division
  index, question_sources, answers, notice counts, node rests, non-negative counters.
- Operator tools: `life-ctl` gained `show`, `approve`, `report`, `move`, `canaries`, `gate-selftest`, `clear-fault`,
  `purge-refused`, `--unreviewed`, `--moved-base`; releases are built in a temporary folder; seed resumes.
- New files: `bin/life-fetch.py`, `bin/life-research.py`. `VALIDATE.sh` gained the CLI policy round trip,
  13 negative schema inserts, the exact canary list, bytewise embedding, 38 rule cases and the timing-literal check.
  LIFE.md section 13 and the section 17 table are generated from life_common.py.

**Rejected or applied in part: 111** (C 16, G 83, Lo 12), one line each with the reason in
`round-2/decisions.md`; 239 findings applied as written. The main reasons: bwrap cannot run unprivileged here
(Landlock used); the live checkout must stay invisible to the sandbox (the clone's own judge is protected by the
deny list instead); several ChatGPT items need platform hooks the kit cannot add (pre-execution policy checks,
attested worker node sandboxes, admission leases, server instance ids, executor-side reservations); some were already
true (git clones carry commits only; knowledge and lessons share one transaction; apply validates the current
schema; the tick is the single writer); and two requirement decisions were written down instead of built
(optimisation = operator benchmarks, GAP 12; databases = schema only, GAP 13).

**Validation.** `VALIDATE.sh` ends STATIC PASS (12 checks; nine `bin/symblic check` ok; three templates lint with
zero findings and round-trip through bin/symblic-task's parser to the same policy sha256; contract holds).
`ruff check --select F,E9,B,PLE` passes on bin/. Nothing was run: no tick, seed, model, agent or cluster job.

**Open for round 3.** The admission tests (GAP 8: the seam and the list exist, the tests do not), recorded genome
fixtures (GAP 9), whether CODEBASE_HISTORY_OK or a history rewrite is the operator's choice (GAP 11), a `perf_fix`
class (GAP 12), typed table adapters (GAP 13), the operator's sign-off of the precedence paragraph (LIFE.md header),
and whether 3 benchmark pairs and the 50 % / 3-node fleet signal hold up once LIFE's own ledger is live.

## Round 3 (2026-10-11)

**Critics.** ChatGPT web, highest effort (`round-3/critique-chatgpt.md`, sent in 14 parts, `round-3/send-log.txt`;
it saw no life-tick.py or life-ctl.py source and reviewed their specified behaviour): 145 findings, 89 undefined
details. Claude cloud, highest effort (`round-3/critique-cloud.md`, task life-review-r3-20261011, a source snapshot
without the platform files): 58 findings, 41 undefined. Local reviewer (Claude Code subagent with the live checkout,
`round-3/critique-local.md`): 50 findings, 25 undefined. Total 253 findings, 155 undefined details; all three
verdicts CHANGES NEEDED. The same defects recurred across critics: agent divisions could never commit (Lo1, C1, G1),
the schema snapshot listed an index before its table (Lo2, G95), one AUTOINCREMENT broke every later snapshot (Lo3,
G94), "cancel accepted" was read as "run ended" (Lo4, G8), sandboxed candidate code escaped STOP and timeouts through
its own session (Lo5, G3), the stop-the-timer row did not stop a running tick (C5, G14), test_only could rewrite its
own judge (Lo16, C18, G43), the gate deny list missed the platform files LIFE relies on (C23), the watched-test
dedup was vacuous for failed findings (C22) and blocked recurring work (G105).

**Verified against the code before acting** (rg/sed only; no model, agent, task, tick or cluster job):
`symblicos/autogen.py` (`control('cancel')` only sets `cancel_requested` and answers ok for an ended run; a repeated
submit with the same request id and `request_digest` returns the existing run, so an identical re-send is safe; the
run row's `base` = engine, node, cwd), `host_routes.Jobs.cancel` (sets a flag; 404 when not running; `unknown` is
"execution unknown; reservation held"), `agent_hub.provision_remote` (a full `git worktree add` of the branch on the
worker node: Lo6 confirmed), `landlock_sandbox.py` (UDP is not a network rule: Lo24 confirmed; a kernel without network
rules refuses with --require; the launcher execs without a PATH search), `cluster_highpower` (`rest_until` returns 0
when idle: C6 wrong; `phase` restoring/restore_pending while `enabled` is false: Lo23 confirmed), `symblic_apply._runner`
(a named node is never re-placed: C4 wrong), `symblic_run.report` keys, `bin/symblic` flags, `symblicos_engine`
catalog route (version, defaults, failure_classes), `symblic_autogen.FAILURE_CLASSES` and the interval/feedback
defaults (Lo28), `bin/symblic-task` cmd_catalog/cmd_workspace, `scripts/devcheck.py` (`git diff BASE --` covers
uncommitted work; it prints `N file(s)`), `local_research.research` (`range(max_tools + 2)` generations, each polled
STEP_TIMEOUT + 120: Lo21 confirmed), `deep_research.safe_fetch` (returns any status: Lo13 confirmed),
`cluster_engine` (map stores `meta.label`; listing gives `total`; `OUT_HEAD` 40000; `CMD_TIMEOUT_MAX` 3600; vitals
units), `bin/local-research --list` format, man systemd.scope (RuntimeMaxSec on scopes) and systemctl (glob stop).
The Landlock wrapper was exercised once with harmless local commands in a scratch folder (`/bin/true`, `/bin/false`,
`sleep`, the sandbox probe: "held"); that run caught a real defect (timeout/prlimit need absolute paths inside the
launcher) before it shipped.

**What changed (v2.1 → v2.2).**
- New operator file `DECISIONS.md`: every operator word the kit bounds and the bound; `arm` requires its sha256 prefix
  (`--decisions HEX16`), a finished seed, VALIDATE STATIC PASS and the sandbox probe; ARMED binds the kit, the pinned
  platform files (`PLATFORM_PINS`) and DECISIONS.md; STOP disarms.
- Kill switch: Procs SIGKILLs the whole group after the grace whether or not the leader exited, registers a process
  the instant it exists, checks the output cap after exit too (rc OUTPUT_LIMIT_RC); `life-check sandboxed` owns its
  child's group (timeout, SIGTERM, SIGINT) under `timeout --kill-after` and `prlimit`; every heavy local job runs in a
  named `life-*.scope` with RuntimeMaxSec and TasksMax, stopped by STOP and by the unit's ExecStopPost; STOP is
  handled before the schema check; cancels are REQUESTS (runs and jobs stay live until polls see them end); every
  cancel is asked independently of registry writes; `launch_allowed` re-checks admission immediately before every new
  process; http_json has one deadline and strict JSON.
- Sandbox and git: every trusted git command in a workspace runs with GIT_SAFE and no system/global config; the
  clone's git configuration is hashed around every sandboxed run (a change deletes the clone); `clean -ffdx`;
  the sandbox probe; texts corrected for UDP (GAP 15) and metadata changes (GAP 16).
- Reproduction: a `workspaces` stage (one child clone per tick), the commit moved to lifecycle, rule 13 (workspace
  not busy), gate/apply/confirm items stay with the parent, divisions counted in armed ticks (12) with a 24 h wall
  backstop checked even while held, a release pin, one foci retry at the next rung, reproducer tuning, a division
  step every 2nd tick, orphan child workspaces removed on abort, `backlog_ticks` reset by any observe-only tick.
- Codebase: test_only may change only its module and is never ready from a model accept (`patch_test_only`);
  local_fix may change only function bodies the traceback names (`local_fix_problems`); environment errors, empty
  test runs and all-skipped runs are never findings; failure fingerprints; `finding_failed` notices; occurrence
  numbers in finding identities; the gate requires devcheck to check at least one file and the test to run;
  explicit exit codes 2/3/4/5/125; the tracked branch is chosen at seed and checked at apply; the deny list covers
  every CONTRACT file, docs/agents/, AGENTS.md and CLAUDE.md; a finding is counted done once.
- Database: snapshots in creation order without sqlite_* objects; AUTOINCREMENT, WITHOUT ROWID, STRICT, block
  comments and quoted identifiers refused; REFERENCES must exist; validation on a copy WITH rows under a progress
  deadline; MIGRATION-RULES.txt in the workspace; `database:` prefix for operator requests; durable evidence (bundle +
  `applying` row) before the organism commit; ledger reconciliation and `forget-migration`; the store adapter.
- Compute: ABBA order with a discarded warm-up, run-indexed output blocks, exact fractions, `head -c 4096` per run,
  job timeout 7 x (T + 10) + 60, no parameter salvage (a bad answer escalates), unknown/lost jobs to the operator with
  the node held (`release-hold`), cancelled jobs as infra, safer param_rx rules, the catalogue with baselines.
- Learning and digest: research bounds derived from the platform loop (3 tools, 5 generations, 2100 s) and a
  launch cap in the wrapper; HTTP status classified by the fetcher; fetch in its own scope; usable-link counting;
  recurring operator questions re-occur.
- Scheduling and metabolism: per-node refill (4 actions per tick), the duty-cycle reservation, the host memory gate
  (MemAvailable 6144 MiB, memory pressure), high-power mode phase, unobserved intervals count as loaded, samples only from a
  readable status, the full governor refresh before slots, `no_capacity`, effective-rung escalation, two timeouts
  escalate, structured error kinds first, model-call reservation (12 per run, budget 14400), a 7-day rung-down hold,
  only terminal endings touch the failure streak.
- Registry schema 4: NOT NULL ids, integer types, organ/stage pairs, triggers (item organ = cell organ, lineage,
  birth facts, item identity and taint), new item counters (start_refusals, timeouts) and approval columns, division
  stage/ticks/release, migration `applying`, FKs to items; payload schemas per stage (`PAYLOAD_KEYS`); declared
  notice kinds (`NOTICE_KINDS`, generated table) and meta keys (`META_KEYS`).
- Operator tools: life-ctl gained `revive`, `requeue`, `release-hold`, `recover-apply`, `restore`,
  `forget-migration`, a journaled revert, `seed --branch`, a 3000 s lock wait with progress lines, STOP-aware
  refusals; life-status samples registry and control separately and survives unreadable control state.
- Every number now has a written meaning; LIFE.md sections 13, 14 and 17 are generated (`limits_table`,
  `notices_table`, `contract_table`) and VALIDATE check 13 compares them; check 12 covers every program; CONTRACT
  grew from 52 to 94 rows; VALIDATE grew to 87 rule cases and 23 refused bad rows.

**Rejected or applied in part: 74** (Lo 8, C 16, G 50), one line each with the reason in `round-3/decisions.md`;
179 findings applied as written. The main reasons: two cloud claims were wrong (C6 restUntil is 0 when idle, C4 a
named node is never re-placed); four ChatGPT items were already true (G52, G112, G114, G54); ten need platform
changes (tombstones, an idempotency key on the map route, a worker node-side job cgroup, a deny-all/UDP network flag, a
metadata seccomp rule, model digests, a repository writer lock, atomic static deploys); twelve were rejected with a
stated design reason (an external bootstrap, a second materialized tree per gate, monotonic time across processes,
re-gating against the live checkout, a perf_fix class that would run candidate code unsandboxed on a worker node, an
archive subsystem); the rest were applied in another form (identical re-send instead of 404 bookkeeping, a rules
file instead of a 1500-character statement, one clone per tick, a 24 h wall backstop beside the tick count).

**Validation.** `VALIDATE.sh` ends STATIC PASS (13 checks; nine `bin/symblic check` ok with no placement option;
three templates lint with zero findings at fixture and largest legal values and round-trip through bin/symblic-task's
parser to the same policy sha256; 23 bad rows refused; 87 rule cases; contract holds; LIFE.md tables equal the
generated ones). `ruff check --select F,E9,B,PLE` passes on bin/. Nothing was run: no tick, seed, model, agent,
research question or cluster job.

**Open for round 4.** The admission tests (GAP 8: now with per-test assertions), recorded genome fixtures (GAP 9),
the operator's choice on GAP 11 (CODEBASE_HISTORY_OK or a history rewrite), the platform changes of GAPS 7, 15 and 16, a
measured TasksMax for the tick unit, whether 4 slot actions per node per tick and the 2100 s research bound hold up
once telemetry is live, and the operator's reading of DECISIONS.md.

## Round 4 (2026-10-11)

**Critics.** ChatGPT web, highest effort (`round-4/critique-chatgpt.md`, sent in 21 parts, `round-4/send-log.txt`;
it ran small probes of the supplied functions in its own sandbox): 106 findings, 58 undefined details. Claude cloud,
highest effort (`round-4/critique-cloud.md`, task life-review-r4-20261011, a source bundle without the platform files;
it replayed VALIDATE checks 6, 11 and 13 on extracted copies and demonstrated D1-D14): 70 findings, 38 undefined.
Local reviewer (Claude Code subagent with the live checkout, `round-4/critique-local.md`): 40 findings, 28 undefined.
Total 216 findings, 124 undefined details; all three verdicts CHANGES NEEDED. The regex contract held, so round 4 was
mostly about behaviour that differed from what the kit said: the gate could never pass (Lo1: `bin/devcheck` ran
`bin/devtest`, which needs uv and PyPI, inside the sandbox), a ruff under ~/.local would have made STATE readable to
candidate code (C2, G1), check 0 ran candidate code in the dashboard's own cgroup (Lo2), every agent attempt left a
0.8 GB checkout (Lo3), git metadata protection had holes (Lo4, G2-G6), a symlink passed as a docs change (C1), arm
could never succeed after the seed codebase cell divided (C3), a STOP was counted as the work's own failure (Lo6,
C35, G41), and several bounds were looser than written (model-call walls Lo8/C41, ABBA scoring G88-G89, migration
validation G59-G63, the regex engine G87).

**Verified against the code before acting** (rg/sed only; no model, agent, task, tick or cluster job):
`scripts/devcheck.py` (`tests = 'skip' if args.hook or args.no_tests`; `select_tests` falls back to its heuristic),
`scripts/devtest.py:uv_command/environment` (uv, a HOME cache, `uv pip sync` from PyPI: Lo1 confirmed),
`symblicos/autogen.py:_run` (checks run in the dashboard process: Lo2 confirmed) and `attempt['agent_id']`,
`agent_hub.make_worktree` (`<workspace>.agents/<name>-<stamp>`), `work_action('discard')` and its
`work/discard` route (Lo3), `fleet_runner` ("worker node Ollama is not capped", `_kv_bytes`, `KV_BYTES_PER_TOKEN_B`,
`OLLAMA_OVERHEAD`, `NODE_CTX_BUCKETS`, the worker node context formula: Lo5 confirmed, KV_ALLOWANCE_MIB derived = 819),
`cluster_engine` probe (`p load`, `p cpus`, `sleep 0.3`, load parsed to three floats: Lo9), `bin/symblic-task`
(`FLAGS_WITH_VALUE` has `--model`/`--effort`, start copies them into the body: Lo10), `agent_engines.agy_models`
(the model list comes from `agy models`, so the model is the operator's file, not a kit constant),
`landlock_sandbox.py` (`parse_ports('')` = no TCP connect at all: round 3's G50 decision was wrong; SCOPE_SIGNAL at
ABI 6; SYSTEM_RW holds /dev/shm: Lo17), `symblic_autogen.lint` (the 1500-character warning; VERBS), the LIMITS of
wall_seconds (300..172800), `deep_research.safe_fetch` (binary returns `data`), `symblicos/workspaces.py` (writes no
configuration), SQLite 3.45.1, the repository's pack (762502 KiB) and HEAD tree (786316617 bytes, `.backups/` 18.3 MB)
by `git count-objects`/`ls-tree` (read-only), free disk (322 GB). One scratch `git clone --no-local` +
`sparse-checkout set --no-cone` + `git init` of a two-file repository in the session scratchpad listed the exact
configuration keys LIFE's workspaces hold (GIT_CONFIG_ALLOWED).

**What changed (v2.2 → v2.3).**
- Sandbox and gate: the gate runs `./bin/devcheck --changed BASE --no-tests` (the focused test is step 3; contract rows
  on --no-tests and uv); every TCP connect and bind denied (`--net-connect ''`, pinned); read-exec grants only for
  allowlisted tool roots (`TOOL_ROOT_RX`, refusal 125, `state_problems` checks no grant covers STATE or a private
  root); `life-check.py sandboxed` runs in its own scope with the host memory gate, prlimit --fsize and /dev/shm
  cleanup; watched tests get prlimit too; the sandbox probe proves its targets outside first, needs the policy's
  PermissionError for each denial (inconclusive otherwise), runs with the gate's grants, tests a signal to an outside
  process, and reports /dev/shm and UDP; `probe_dir` replaces the hard-coded seed clone (arm after a division works).
- Git: `git_admin_problems` before every trusted git command (a real .git, no commondir/gitdir/alternates, a whole
  configuration allowlist instead of neutralising keys); GIT_SAFE adds attributesFile, gitProxy, alternateRefsCommand,
  credential.helper, askPass; GIT_NO_REPLACE_OBJECTS; `git_meta_sha256` covers HEAD, refs (replace refs), packed-refs,
  worktrees, shallow, commondir and loose objects with bounded, non-following, FIFO-safe reads; `workspace_guard` rows
  committed before each sandboxed run (a crash leaves the evidence; recover deletes the workspace).
- Gate rules: typechanges and diff mode lines refused; deny list adds .env and secrets_data at any depth, the judge's
  configuration files and any conftest.py; local_fix compares every definition's header at every nesting level, keeps
  duplicate definitions distinct (identity = qualified name + #N) and authorizes identities resolved from traceback
  line numbers (or `path.py:Class.function` named by the operator); the credential screen has a STRICT tier and a CODE
  tier for diffs, token prefixes case-sensitive; environment errors are decided by the last exception line only.
- STOP and processes: STOP and FREEZE fail closed when control/ cannot be inspected; Procs returns STOPPED_RC and
  NOT_ADMITTED_RC (no counters, no holds, no findings); deadlines checked with the remaining time; exceptional exits
  end the group; scopes stopped concurrently with the process groups; STOP ticks reconcile runs and jobs; label-only
  benchmark jobs are looked up and cancelled; `call_intents` cover division steps too; arm and stop serialized by a
  control lock and STOP_GENERATION; SIGTERM exits 4 (listed); status.json has a real disposition; in-process
  migration and store transactions check STOP before COMMIT; HTTP exchanges are closed at the deadline and capped.
- Runs: `--model` from control/agy-model.txt and `--effort low` (compared at confirmation); a versioned run manifest is
  the only source of a re-send; re-sends only on admitted ticks with no hold; exhausted re-sends stay submit_unknown
  until the operator's new `abandon-run`; structured `runs.cancel_cause` and a stated collection precedence; dividing
  cells start no run; the daily budget re-read before each start; agent starts need an idle hour on their node
  (wall 2700, cancel at 3000); hub checkouts discarded after collection; agy quota refusals are infra with a notice.
- Scheduling and metabolism: node holds keyed (node, cause, subject), never shortened, job holds without expiry,
  timeouts hold only their program; two top-rung timeouts end TIMEOUT_LIMIT; the per-call wall is derived (75 s);
  slot programs run in scopes; refresh before every slot action and after agent starts (holds recorded); fleet load
  from the 5-minute load per processor; observed samples need every node; quiet credit needs two observed samples;
  a wall-clock step is unobserved; the fleet window gates admission; node rest 1800 s and a 6 h daily cap; +4096 MiB
  beside a live agent run; odd working ticks run the slot phase first (no starvation); division steps and tick
  counts use working ticks and the parent node's availability (DIVISION_MAX_TICKS derived = 27).
- Commands and learning: COMMAND_PREFIXES routed by code (research:, fix:, database:, measure:, genome:, status);
  COMMAND_MIN_BYTES 6 everywhere; OVERFLOW rows revive; source identity by DOI, canonical URL and identical text;
  fetch once as bytes; pages redacted instead of abstained; questions at the link limit wait for their fetches
  (settle_questions); the research wrapper validates the platform's result types, drops long URLs, keeps the
  question's braces, cancels its runs on every exit and reports its launches.
- Codebase: watched-test dedup waits for a bundled patch; watch.txt errors are notices; review notes are their own
  never-cut template field; patch and proposal reviews are model-tainted; the codebase gate waits for a passing
  gate-selftest for this kit (gate_unproven); scope text names the exact functions and the body-only rule; triage
  descriptions match the gate.
- Compute: param_rx restricted to linear-time shapes; the catalogue shows whole entries with the pattern and timeout;
  two warm-ups, 8 runs; the wrapper records each run's exit status and truncation (LIFE_RC, LIFE_TRUNC) and only a
  `done` job is scored; incomplete listings never prove absence; label ambiguity goes to the operator; rank/bench with a
  missing benchmark fail without a model call.
- Database: an explicit column grammar (types, constraints, lower-case names, no sqlite_ names, no CHECK/GENERATED/ON
  CONFLICT), terminating semicolons, UNIQUE indexes only on new tables, references to real keys, foreign keys enforced
  during validation, the result must be a valid snapshot, one deadline over a paged copy, logical vs physical size,
  ORGANISM_MAX_BYTES 512 MiB, pre-migration bytes cap; texts saved before any decision (refused.txt); a full
  reconciliation matrix; a migration-number journal outside both databases; the store adapter qualifies tables by
  their full inventory, round-robins one attempt budget, disables a failing table, and replays after a restore.
- Operator tools: abandon-run; revive is a birth; requeue accepts OVERFLOW/EMPTY/refused sources; move refuses busy
  cells; release-hold clears every hold; apply compares blob ids, checks parents, links and `git apply --summary`,
  records modes and unverified bases; revert and recover-apply restore the pre-apply state and move the record to
  history (re-apply possible); restore clears store marks; arm checks the loaded units; check_release is the one
  release validator (raw lint, verbs, worst values, the CLI round trip); entry points never write bytecode;
  life-status refuses unknown arguments, decodes JSON columns and reports UNKNOWN for bad ARMED, schema or seed.
- Schema 5: runs.model/effort/cancel_cause, sources.duplicate_of/redacted/'duplicate', governor.observed, node_holds
  re-keyed, call_intents, workspace_guard, typed metrics and notices. DECISIONS.md: lines 1-20 updated (2700/3000,
  27 ticks, births, duty, accepted restarts, agy model, gate proof) and lines 21-27 name the accepted exposures (UDP,
  metadata, page parsing, benchmark cgroups, the gate as a regression check, /dev/shm, transitive imports). GAPS 17-20
  are new; GAP 8 lists 36 more admission tests and the measurements nothing here could make.

**Rejected or applied in part: 57** (Lo 9, C 9, G 39), one line each with the reason in `round-4/decisions.md`; 159
findings applied as written. The main reasons: seven were already true (G5, G22 in part, G25, G35, G40, G42, G81); a
round-3 decision was wrong and is corrected (an empty --net-connect list denies all TCP); nine need platform changes
(autogen staging receipts, an out-of-process test judge, UDP and metadata syscall rules, project quotas, job-wide
cgroups, remote mirror lifecycle, a sandboxed parser that needs the repository); the rest were applied in another
form or in part for a stated reason (a guard row instead of a persisted hash that the hub's own writes would break,
the hub's discard route instead of LIFE removing hub checkouts, alternating phase order instead of a reservation
ledger, a gate_unproven hold instead of refusing arm, derived per-call walls until latencies can be measured).

**Validation.** `VALIDATE.sh` ends STATIC PASS (13 checks; nine `bin/symblic check` ok; three templates lint with zero
findings at fixture and largest legal values, each field at its maximum, and round-trip through bin/symblic-task's
parser; `check_release` accepts the kit; 28 bad rows refused; the benchmark wrapper framed correctly under sh; 161 rule
cases; contract holds with 115 rows; LIFE.md tables and appendices equal the files). `ruff check --select F,E9,B,PLE`
passes on bin/; `bash -n` on every shell file. Nothing was run: no tick, seed, arm, model, agent, research question or
cluster job.

**Open for round 5.** The admission tests and measurements of GAP 8 (p95 call walls, slot and coordinator RSS, the
tick's tasks, clone time, the systemctl display formats `unit_problems` compares), recorded genome fixtures (GAP 9),
the operator's choices on GAP 11 (CODEBASE_HISTORY_OK) and on the agy model, the platform changes of GAPS 7, 15-19, and
whether the 6 h daily node cap and the idle-hour rule for agent starts leave enough throughput once telemetry is live.

## 10:14 closed by the operator's instruction

Round 4 folded (LIFE v2.3, STATIC PASS, validate:r4 passed). The judge asked for a round 5; its three critics were
stopped before they produced anything, and the workflow was ended here. The open items the judge listed stay open in
DECISIONS.md and at the end of LIFE.md; WORKSHOP-RECORD.md holds the whole record. Nothing in the kit was ever run.
