# RESULT — life-review-r3-20261011 (review mode, no source modified)

Task: critique the LIFE v2.1 kit (`docs/life`) for details that are not atomically defined,
contradictions with `BRIEF.md`, unsafe or unbounded behaviour, and missing organs or paths.
Bundle SHA-256 `9b577276c62142a084404f2f9341b57da5f126041a652970a1a289ef2592dcc6` (every per-file
sha256 in `.cloud-agent/task.json` verified against the snapshot; the bundle digest's construction is
not documented, so it was not recomputed).

## Changes

None to application source (review mode). Files written: `.cloud-agent/STATUS.json`,
`.cloud-agent/RESULT.md` only.

## What was read

Every kit file in the snapshot, in full: `LIFE.md` (workshop/round-3 copy, 7677 lines, sections
1–18 and all 36 appendix blocks), `BRIEF.md`, `README.md`, `spawn/PROTOCOL.md`, `VALIDATE.sh`,
`db/life.sql`, `db/organism.sql`, the nine `genome/*.sym`, the three `organs/*.lines.txt`, the three
`policies/*.json`, `checks/devcheck-gate.sh`. Line numbers below cite kit paths; `LIFE.md NNNN`
cites the master document (the appendix copies of `bin/*`, `units/*`, `organs/organs.json`,
`organs/fixtures.json`, `checks/canaries.txt`, `spawn/example/division.json`,
`benchmarks/benchmarks.example.json` exist only inside `LIFE.md` in this snapshot).

## Tests executed (static, no platform; commands and outcomes)

The 36 `### <path>` appendix blocks were extracted from `LIFE.md` into a scratch folder with the
exact regex `VALIDATE.sh` check 9 uses, then compared with the snapshot's files:

```
python3 -I extract.py   -> blocks: 36; every block with a snapshot counterpart is byte-identical
                           (README.md, VALIDATE.sh, genome/*, organs/*.lines.txt, policies/*,
                            checks/devcheck-gate.sh, db/life.sql, db/organism.sql, spawn/PROTOCOL.md)
bash -n bin/life-seed.sh checks/devcheck-gate.sh VALIDATE.sh      -> all ok
python3 -I -B -c 'ast.parse(...)' bin/*.py                         -> all 7 files parse
json.load organs/*.json policies/*.json spawn/example/*.json benchmarks/*.json -> all parse
grep -nE 'timeout=[0-9]|\b(3600|86400)\b|time_left\(\) < [0-9]' bin/life-tick.py -> no match (check 12 PASS)
db/life.sql and db/organism.sql executescript twice in :memory:    -> ok, 26 tables / 1 table
VALIDATE.sh check 6 block (13 negative inserts) re-run on the extracted schema -> PASS (13 refused)
VALIDATE.sh check 11 block re-run on extracted bin/life_common.py   -> 38 rule cases, all pass
   (the redacted has_secret fixture replaced by a dummy literal of the same shape, [PASSWORD-ASSIGNMENT-FIXTURE]; /proc/pressure/io is
    absent in this container, so that single expectation was skipped)
```

Probes written for this review (results quoted in the findings):

```
can_start(2*3*CLONE_TIMEOUT): 0 + 3600 + 30 + 60 <= 2700 -> False          (finding 1)
ASK_RX.fullmatch over every ask line of the nine programs -> 0 non-matching (no finding)
patch_problems(test_only, '-assertEqual(a, b)' / '+assertTrue(True)') -> ACCEPTED   (finding 18)
Tick.owned_jobs with a label-only job on page 2 and job_ids={A}   -> B not found (finding 13)
render() worst cases: codebase [1785, 675] at finding_text 700, [1235, 675] at 150; database
   [1127, 328]; selfdev [704, 300]; STATEMENT_MAX 1400 (the cut loop suffices; no finding)
benchmark cmd through sh -c CMD sh ITEM with ITEM='7; echo INJECTED' -> item passed as data (no finding)
migration_problems: uppercase org_ name, block comment, index WHERE, lowercase ADD COLUMN type,
   WITHOUT ROWID -> refused; REFERENCES org_y (table absent) with a snapshot -> ACCEPTED (finding 52)
```

## Limitations

- No platform: `VALIDATE.sh` checks 1–4, 7, 10 (bin/symblic, symblic_autogen, the contract files) and
  every runtime behaviour could not be executed; findings about platform facts are about what the
  kit pins versus what it relies on, not about the platform's actual behaviour.
- `LIFE.md` and `VALIDATE.sh` were read in their workshop copies (fixture string redacted, line
  numbers unchanged, as the task states).

## Findings

Severity: high / medium / low. Class tags: [undefined] an ambiguous or undefined detail, [defect] a
contradiction or logic error, [unsafe] unsafe or unbounded behaviour, [missing] an organ or path
the brief requires. UNDEFINED_DETAILS counts the [undefined] findings.

### High

**1. [defect] Agent-organ divisions can never commit.**
Location: `LIFE.md` 4301–4303 (`division_commit`: `if not self.can_start(2 * 3 * L.CLONE_TIMEOUT): return None`), 2655–2659 (`can_start`), 5290–5291 (`TICK_HARD = 2700`), 5368 (`CLONE_TIMEOUT = 600`), 3487–3502 (`make_workspace`: three git steps, each `CLONE_TIMEOUT`); `spawn/PROTOCOL.md` 46–48 ("a tick with less than 3600 s of hard budget left waits for the next tick instead").
Defect: `can_start(3600)` requires `elapsed + 3600 + 30 + 60 <= 2700`, which is false at every elapsed value, so a codebase, selfdev or database division returns "commit next tick" on every tick until `DIVISION_MAX_SECONDS` aborts it, then the 21600 s cooldown, forever. PROTOCOL's rule is self-contradictory (no tick ever has 3600 s of hard budget). Only model organs can reproduce.
Fix: add a `workspaces` stage between `assign` and commit that creates ONE child workspace per tick under `can_start(L.CLONE_TIMEOUT)` (the three git steps run under one shared `CLONE_TIMEOUT` deadline, not three), records `child_a_ws_ok`/`child_b_ws_ok` in `divisions`, and commits (no clone, no model) at the next tick. Replace PROTOCOL 46–48 with: "Agent organs: each child's workspace is created in its own tick (stage `workspaces`, one clone per tick, bounded by CLONE_TIMEOUT 600 s in total); commit happens at the first tick after both exist." Replace `LIFE.md` 4302 with `if not all(os.path.isdir(os.path.join(ws, '.git')) for _c, _f, _n, ws, _i in kids): return None`. Add a VALIDATE check-11 case: every `can_start(x)` literal argument in `bin/life-tick.py` satisfies `x + KILL_GRACE + 60 <= TICK_HARD`.

**2. [undefined] The `bin/symblic run` interface LIFE's every model call depends on is not pinned.**
Location: `LIFE.md` 4529–4551 (`run_program` reads `rep['status'] == 'done'`, `outputs[].kind == 'return'`, `.value`, `rep['calls']`, `error.kind/message`), 4531–4532 (`--input NAME=<JSON>`), 4530 (`--dir`), 6438–6440 (`SYMBLIC_CALL_WALL_S`, `SYMBLIC_THERMAL`), CONTRACT 6563–6564 (pins only `--max-calls` and `--ollama-limits`), section 8 lines 604–608.
Ambiguity: the JSON report's keys, the `--input` value encoding, `--dir`, `--json` and the two environment variables are relied on without a contract row. If the running `bin/symblic` names the status `ok`, nests `outputs` differently or ignores `--input`, every program run is classified `failed` (not `infra`), every item escalates to the top rung and fails, each cell reaches `QUARANTINE_FAILURES` after 8 items, and the organism stops with `quarantine` notices instead of a `contract` notice. Nothing distinguishes "the platform changed" from "the models are bad".
Fix: add CONTRACT rows for `bin/symblic` / `symblic_run.py`: `p.add_argument('--input'`, `p.add_argument('--dir'`, `p.add_argument('--json'`, the report writer line that emits `'status': 'done'`, the `'kind': 'return'` output record, the `'calls':` counter, the `error` object with `kind` and `message`, and the readers of `SYMBLIC_CALL_WALL_S` and `SYMBLIC_THERMAL`. In `run_program`, when the report is a JSON object but has neither `status` nor `error`, return a new outcome `contract` that opens a `contract` notice and holds (not `failed`).

**3. [undefined] Sandbox invisibility of STATE and the TCP rule are asserted, never pinned or self-tested; the kill-switch argument rests on them.**
Location: `LIFE.md` 70–77, 6464–6478 (`sandbox_argv`: `--require --no-unix --net-connect 1`), README 86–88 ("where STATE does not exist"), CONTRACT 6583–6585 (pins only that the launcher parses those flags).
Ambiguity: what `landlock_sandbox.py` grants by default (is `/home/operator` readable? STATE is the same uid), whether `--require` refuses when the kernel's Landlock lacks network rules (ABI 4, kernel 6.7+) or silently runs filesystem-only (then candidate code reaches 127.0.0.1:8080, the API that starts runs and cancels jobs), and whether `--net-connect 1` means "only port 1" are platform behaviours, not pinned text.
Fix: (a) CONTRACT rows pinning the launcher's default read-only roots and its ABI check (`landlock_create_ruleset` with the net flag, and the refusal when missing); (b) extend `life-ctl.py gate-selftest` and `arm` with a sandbox probe run through `sandbox_argv` inside the seed clone: `python3 -c "import os,socket; assert not os.path.exists('/home/operator/.local/state/life'); assert not os.path.exists('/home/operator/.ssh');` then a `socket.create_connection(('127.0.0.1', 8080), 2)` that must raise; `arm` refuses when the probe passes anything it must not. Document: "Landlock ABI 4 or newer is required; `--require` refuses older kernels (exit 125)".

**4. [undefined] `SYMBLIC_THERMAL=1` may re-place a call on a node other than the cell's node.**
Location: `LIFE.md` 6438–6440 (`child_env`), section 8 lines 600–602 and 605 (`--by ollama:MODEL@NODE`), README 92–93 ("never on the host, the ARM node, node-c/e or node-h"), `BRIEF.md` 35 (the brief's example `--by ollama:qwen3:4b-instruct` carries no `@node`); no CONTRACT row names the `@node` suffix or the thermal placement rule.
Ambiguity: if thermal placement moves a hot node's call to a cooler Ollama host, the call may run on node-h (protected service stack), node-c/e or a node LIFE holds, the `calls.node` ledger, `node_holds` and the per-node rest are charged to the wrong worker node, and "one program run per node per tick" is false. If the `@node` suffix is not parsed, the call runs on the platform default node.
Fix: pin in CONTRACT the `symblic_apply.py` lines that parse `ollama:<model>@<node>` and that `SYMBLIC_THERMAL` only refuses (never relocates) when the named node is hot; otherwise set `SYMBLIC_THERMAL` to `0` in `child_env` and let the fleet runner's own thermal refusal be an `infra` outcome. Add to section 8: "A call runs on NODE or not at all."

### Medium

**5. [defect] The README kill switch misdescribes "stop the timer".**
Location: `README.md` 83 (`LIFE.md` 1161): "`systemctl --user disable --now life-tick.timer` | no tick at all (a running tick gets SIGTERM and ends its processes)".
Defect: stopping or disabling a timer unit does not stop an already running instance of the service it activates; a tick in its slot phase keeps its model and research processes (up to RESEARCH_TIMEOUT 1500 s) and its agent-run polling until it ends by itself. The operator is told otherwise.
Fix: replace the command cell with `systemctl --user disable --now life-tick.timer && systemctl --user stop life-tick.service` and the effect with "no further tick; the running tick (if any) gets SIGTERM from the stop and ends its process groups (SIGKILL 30 s later), exit 1".

**6. [undefined] high-power mode `restUntil` of no rest: `null` holds LIFE forever.**
Location: `LIFE.md` 2803–2807 (`rest_until = finite(sm.get('restUntil'), 0)`; `elif rest_until is None: reasons.append('high-power mode rest is unreadable')`), CONTRACT 6595 (pins only `'restUntil':rest_until(s),'cool':cool`).
Ambiguity: the type of `restUntil` when no rest is pending (0, null, absent) is not pinned; `null` or absent reads as "unreadable" and holds every tick.
Fix: pin `def rest_until(` and its idle return value in `cluster_highpower.py` in CONTRACT; in `metabolism` treat `restUntil` absent or null as 0 and only a non-number as unreadable: `rest_until = 0 if sm.get('restUntil') in (None, 0) else finite(sm.get('restUntil'), 0)`.

**7. [undefined] `/api/cluster/status` keys and units are relied on but not pinned.**
Location: `LIFE.md` 2786–2826 (`status['status']` list, `row['id']`, `row['online'] is True`, `vitals.cpu` 0..100, `vitals.temp`, `vitals.memavail` bytes // 1048576), section 10 lines 663–665, CONTRACT 6591 (pins only the `ts` field).
Ambiguity: if `memavail` is in MiB or KiB, every node computes `mem < 2048 + model + 1024` and `node_ok` is false forever with no notice (plan_slot returns None silently); if `cpu` is 0..1 the fleet never counts as loaded; if `online` is 1 instead of `true`, every node is offline.
Fix: CONTRACT rows on `cluster_engine.py` for the lines that build `'online':`, `'vitals': {'cpu':`, `'temp':`, `'memavail':` and the unit of each; add notice `no_capacity` when no available node has passed `node_ok` for 12 ticks while queued slot items exist.

**8. [undefined] The autogen run row shape and the failure vocabulary are not pinned; a platform rename turns every infrastructure failure into a cell failure.**
Location: `LIFE.md` 2606 (`NON_SEMANTIC = ('INFRASTRUCTURE', 'REFUSAL', 'CANCELLED', 'CONFLICT', 'FETCH_FAILURE', 'TIMEOUT')`), 2990–2992 (`row['nodes'][].attempts[].failure`), 2960 (`row['policy']['sha256']`), 2972 and 2977 (status words), CONTRACT 6542 (terminal set) and 6545 (`'base': base, 'policy': policy, 'lines': lines,`).
Ambiguity: the `nodes`/`attempts`/`failure` nesting and the exact failure labels are the only thing separating `infra` (re-queue) from `failed` (failure streak, quarantine at 8); none is pinned.
Fix: CONTRACT rows for the `symblicos/autogen.py` lines that write `'attempts'`, `'failure':` and the constants that define each of the six labels; VALIDATE check 11 case: every label in `NON_SEMANTIC` appears as a string literal in `symblicos/autogen.py`.

**9. [undefined] The autogen catalogue route's `defaults` and `version` keys are not pinned; a shape change holds LIFE permanently while armed.**
Location: `LIFE.md` 2743–2755 (`server_defaults_problems`: `cat.get('defaults')`, `cat.get('version')`), section 7.9 lines 541–543.
Ambiguity: a catalogue without `defaults` makes every DEFAULT_FIELD "mismatch" and opens a `contract` hold at every armed tick (exit 5), with a recovery note that points at CONTRACT rows which do not cover it.
Fix: CONTRACT row for the `symblicos` route handler that returns `{'version': symblic_autogen.VERSION, 'defaults': ...}`; in `server_defaults_problems`, report "catalogue has no defaults object" as one problem instead of seven field mismatches.

**10. [undefined] `bin/symblic-task catalog --json` output shape (`nodes[].id`, `online`, `ready.agy`) is not pinned; agent organs would wait forever with a misleading notice.**
Location: `LIFE.md` 3768–3778 (`catalogue_ready`), README 28, CONTRACT 6596 (pins a dict literal inside `agent_hub.py`, not the CLI's top-level `nodes` key).
Fix: CONTRACT rows for `bin/symblic-task`'s `cmd_catalog` printing `{'nodes': ...}` and for `agent_hub.py`'s `'online':` key; when the catalogue parses but names no LIFE node, open notice `catalogue_shape` (not `agy_not_ready`).

**11. [undefined] `bin/symblic-task workspace NAME` is relied on by the seed and never pinned.**
Location: `LIFE.md` 1784 (`[L.TASK, 'workspace', os.path.basename(ws)]`), section 15 seed row; CONTRACT has no `cmd_workspace` row.
Ambiguity: whether the subcommand exists, creates a git repository, and places it at `PROJECTS/<name>` (the code only checks `.git` afterwards) is unverified; a seed that fails here is "resumed" every time with the same failure.
Fix: CONTRACT rows `def cmd_workspace` and the `PROJECTS` root literal in `bin/symblic-task`; or create selfdev/database workspaces with `git init -q` + first commit under LIFE's own control (the hub only needs "cwd must be a git workspace", pinned at 6543).

**12. [undefined] The map/jobs API shape is relied on in two different ways at once.**
Location: `LIFE.md` 3014 and 3031 (`j.get('label') or (j.get('meta') or {}).get('label')`), 3017 (`page.get('total')`), 3039 and 3059 (statuses `queued`, `running`, `unknown`, `done`), 3057 (`job['out'][node]['out']`), 4983–4984 (body keys `cmd, items, targets, parallel, timeout, label`), 4990 (`.get('job').get('id')`), CONTRACT 6587–6590.
Ambiguity: the code itself does not know whether the job carries `label` at the top level or under `meta`; the status vocabulary, the per-node output nesting, `parallel` and `total` are unpinned. A missing `done` status fails every experiment ("benchmark job <status>").
Fix: pin in CONTRACT the `cluster_engine.py` lines that store the submitted `label`, the status constants (`'done'`, `'running'`, `'queued'`, `'unknown'`), the `out[node]['out']` writer and the `'total':` field of the listing; keep ONE label location in the code.

**13. [defect] `owned_jobs` stops paging before every label is found.**
Location: `LIFE.md` 3017: `if not jobs or offset >= (page.get('total') or 0) or len(found) >= len(job_ids): break`.
Defect: `found` counts jobs matched by id or label; with one job id known and one job known only by its label (a submit whose answer was lost, 4996), the first page that contains the id satisfies `len(found) >= len(job_ids)` and the label-only job on a later page is never seen; after `timeout + BENCH_GRACE` the item fails and the experiment is marked failed although it ran. Reproduced with a fake listing (probe above).
Fix: `len(found) >= len(job_ids) + len(labels_without_id)` where `labels_without_id` is the set of labels of running items whose `job_id` is empty; or always page until `offset >= total`.

**14. [defect] The 3-hour division deadline cannot hold a 16-item model-organ division under worst-case tick length.**
Location: `LIFE.md` 5320 (`DIVISION_MAX_SECONDS = 10800`), 5302 (`ASSIGN_PER_SLOT = 4`), 4387 (one foci tick, then ceil(n/4) assign ticks, then a commit tick), 4593–4596 (a tick's slot phase waits for its longest run: `CALL_TIMEOUT` 900 or `RESEARCH_TIMEOUT` 1500, plus KILL_GRACE + 30), `units/life-tick.timer` `OnUnitInactiveSec=300`.
Defect: a 16-item division needs 1 + 4 + 1 = 6 armed ticks; a tick can last ~1590 s in its slot phase alone, so six ticks span up to 6 × (300 + 1590 + the host stages) > 10800 s; any `infra` retry or a held parent node adds ticks. The deadline is in wall seconds while progress is in ticks, so a busy organism aborts divisions it is entitled to, then waits the 21600 s cooldown.
Fix: define the deadline in armed ticks: `DIVISION_MAX_TICKS = 12` (counted in `divisions.ticks`, incremented by `lifecycle` while open); abort when `ticks > DIVISION_MAX_TICKS`. Update PROTOCOL §2 last paragraph and section 9 ("a division open 3 h aborts") accordingly.

**15. [undefined] Where and when a division commits is defined three ways.**
Location: `spawn/PROTOCOL.md` 43 ("commit (no model)"); `LIFE.md` 143 ("no ... division commit begins after TICK_DEADLINE 1200 s"); 4334–4337, 4386–4389, 4569–4571 (the commit only happens when the PARENT'S node gets a slot in `serve_nodes`), 4560–4562 (a spent program-run or model-call budget returns before any node is planned), 4274–4323 (`division_commit` never checks `time_left()`).
Ambiguity: the commit needs no model yet requires the parent's node to be online, cool, not held, not resting, not benchmarking and the daily program budget unspent; a hot parent node for 3 h aborts a fully assigned division; and the commit can run after TICK_DEADLINE, contradicting section 4.
Fix: move the commit into `lifecycle`: "a division in stage `assign` with nothing left to assign commits in `lifecycle`, before `division_start`, when `time_left() > 0`, independent of any node's slot". Delete the `'commit'` plan from `plan_division`.

**16. [undefined] The database statement does not tell the agent the grammar the gate enforces, so runs are spent on refusals.**
Location: `organs/database.lines.txt` 1; `LIFE.md` 6111–6118 (`MIGRATION_RX`, `MIGRATION_HEAD_DENY_RX`, `FUNCTION_DENY_RX`, `REFERENCES_RX`), 6121–6155 (`split_sql`: no `/* */` comments), section 7.8 lines 511–519.
Ambiguity: the code requires lower-case `org_[a-z0-9_]{1,40}` table/index/column names, an upper-case type word after ADD COLUMN, plain column lists in indexes (no WHERE, no expressions), no `WITHOUT ROWID`/`STRICT`, REFERENCES only to `org_` tables, `;`-terminated statements, no block comments; the statement says only "three forms", "starts with org_", "does not exist in schema-snapshot.sql". A light agent has 3 attempts (candidates 1, regenerate 2) and 12 agent runs a day.
Fix: replace the first statement's middle with: "... containing only `;`-terminated SQLite statements of exactly the forms `CREATE TABLE IF NOT EXISTS org_<name> (...)`, `CREATE [UNIQUE] INDEX IF NOT EXISTS org_<name> ON org_<table> (<column list>)` and `ALTER TABLE org_<table> ADD COLUMN <column> <TYPE> ...`, where every table, index and column name is lower-case letters, digits and underscores, every type word is upper-case, every REFERENCES names an org_ table, no statement uses WHERE, WITHOUT ROWID, STRICT, DROP, DELETE, UPDATE, INSERT, REPLACE, ATTACH, DETACH, PRAGMA, VACUUM, TRIGGER, VIEW, REINDEX, ANALYZE, block comments or the functions load_extension, readfile, writefile, fts, zipfile, edit, sqlar_, at most 24 statements and 16384 bytes, ...". Keep `STATEMENT_MAX` satisfied (the rendered worst case is 1127 characters now; re-check after the edit).

**17. [undefined] `rank-experiment.sym` asks about "one run of at most fifteen minutes"; a run is 30..300 s.**
Location: `genome/rank-experiment.sym` 7; `LIFE.md` 5371 (`BENCH_TIMEOUT_MIN, BENCH_TIMEOUT_MAX = 30, 300`), 4502–4504 (the `benchmark` input already states "`N` pairs of runs of at most `T` s each").
Fix: replace the instruction with "Can this benchmark, as described, test this hypothesis within its stated per-run timeout on one node? Hypothesis: {hypothesis} Benchmark: {benchmark}".

**18. [unsafe] The test_only rule accepts a test rewritten to prove nothing.**
Location: `LIFE.md` 6073–6081 (`patch_problems`: added asserts >= removed asserts, no skip), section 7.4 lines 417–418; `genome/triage-error.sym` 9 (`test_only: the test itself is wrong or outdated`).
Defect: `-    self.assertEqual(a, b)` / `+    self.assertTrue(True)` and `-    x = compute()` / `+    return` both pass (probe above): the judging test is made vacuous by the patch it judges, the gate passes, a 3B reviewer may accept, and the operator is shown `patch_ready`. "Code decides acceptance" does not hold for this class.
Fix: either (a) test_only patches never reach `ready`: after the gate they end `owner` with notice `patch_owner_test_only` (the operator applies with `--unreviewed`), or (b) tighten the rule atomically: every removed line that matches `ASSERT_RX` must reappear byte-identical (after whitespace collapse) among the added lines, and the patch may not remove a line that calls the function under test.

**19. [undefined] `bin/devcheck --changed BASE` semantics are not pinned; the gate's judge may be vacuous.**
Location: `checks/devcheck-gate.sh` 5–6 and 40; CONTRACT 6586 (pins the literal `bin/devcheck --changed BASE` in a comment or usage line only).
Ambiguity: whether `--changed BASE` lints the working tree and index against BASE (what the gate needs: the promotion may not have committed) or only commits BASE..HEAD (then an uncommitted promotion is never linted).
Fix: CONTRACT row on `scripts/devcheck.py` pinning the `git diff --name-only BASE` (not `BASE..HEAD`) call; gate-selftest asserts that a deliberately bad uncommitted file makes step 2 fail.

**20. [undefined] Two different things are called `proposal_id`.**
Location: `LIFE.md` 3855–3857 (`pid = item['item_id'].split(':')[1]`, rendered as `{proposal_id}` and into the verify line), 3684 (`pid = L.sha16(item['item_id'], L.sha(new))`, the `proposals` row), section 7.6 line 464, `organs/selfdev.lines.txt` 2, `db/life.sql` 242.
Fix: rename the template field and verify word: `lesson_id` / `lesson=<16hex> program=<name>` (`PLACEHOLDERS`, `TEMPLATE_FIELDS`, `VERIFY_LINES`, `AGENT_CHECKS`, policies/selfdev.json, organs/selfdev.lines.txt, fixtures.json); `proposal_id` stays the bundle id.

**21. [undefined] "Every number has one definition" is false outside `bin/life-tick.py`.**
Location: `LIFE.md` 11 and 757 (claim), `VALIDATE.sh` 291–293 (check 12 greps only life-tick.py); literals: `bin/life-ctl.py` `LOCK_WAIT = 600` (1654), `lock(60)` (1826), `timeout=900` for VALIDATE.sh (1819), `timeout=60` for git show/apply (1894, 1903, 1918); `bin/life-check.py` `SANDBOX_TIMEOUT = 110` (1513), `1 <= int(cmd[1]) <= 900` (1542), `read_bytes(..., 65536)` (1578), `read_bytes(..., 400)` (1567); `checks/devcheck-gate.sh` `--timeout 600`, `--timeout 240` (40–41); `bin/life-tick.py` `(700, 500, 300, 150)` (3870), `+ 30` (4594), `+ 60` (2659), `[:3000]` (4498), `LIMIT 50` (4184), `entries[:20]` (3161), `[-4:]` (3004), `65537` (3666), `len(text) <= 600` (4732), `>= 10` (4748, 4756).
Fix: move each into `life_common.py` with a name and a section-13 row (`CTL_LOCK_WAIT`, `SEED_LOCK_WAIT`, `VALIDATE_TIMEOUT`, `GIT_SHOW_TIMEOUT`, `SANDBOX_CHECK_TIMEOUT`, `SANDBOX_TIMEOUT_MAX`, `GENOME_MAX_BYTES`, `VERIFY_MAX_BYTES`, `GATE_DEVCHECK_TIMEOUT`, `GATE_TEST_TIMEOUT`, `FINDING_CUTS`, `SLOT_WAIT_EXTRA`, `START_MARGIN`, `CATALOGUE_CHARS`, `SELF_QUESTION_CANDIDATES`, `AGENDA_MAX`, `FAILURES_SHOWN`, `QUESTION_CHARS`, `REQUEST_MIN_CHARS`); extend check 12 to every file under bin/ and checks/.

**22. [undefined] The watched-test dedup rule is vacuous for findings that ended `failed`.**
Location: `LIFE.md` 3422–3428 (`unacked` = an open notice whose subject is the previous finding's item id), section 7.4 lines 389–391; notices with an item-id subject exist only for `owner` endings (`finding_owner`, `infra_repeat`, `render`, `review_owner`, `already_passing`, `approve_needed`).
Defect: a finding that ended `failed` (gate refusal, run failure, three faults) leaves no notice, so the same test with the same first error line creates a new finding at every backoff step (6 h, 12 h, 24 h, then every 48 h), each spending a triage run and an agent run (one of 12 a day), forever.
Fix: `finish_item` opens notice `finding_failed` with subject = the finding's item id whenever a `codebase/finding` ends `failed`; or define the rule as "no new finding for (test, normalised line) while any earlier finding with that line exists in state `owner` or `failed` and the operator has not acknowledged its notice, where a failed finding's notice is `finding_failed`".

**23. [unsafe] The gate deny list omits the platform files LIFE itself depends on.**
Location: `LIFE.md` 6023–6028 (`GATE_DENY_RX`), 6538–6599 (CONTRACT names `symblicos/autogen.py`, `symblic_autogen.py`, `symblic_run.py`, `symblic_apply.py`, `fleet_runner.py`, `local_research.py`, `deep_research.py`, `cluster_engine.py`, `cluster_highpower.py`, `agent_hub.py`, `bin/devcheck`), 6095–6106 (`traceback_files` admits any `.py` not denied as a local_fix target).
Defect: a watched test whose traceback names `symblicos/autogen.py` or `symblic_autogen.py` makes those files legal local_fix targets; a bundled patch to the autogen policy checker, the lint LIFE renders against, the research path or the cluster map route is "reviewed and gated" and offered to the operator as `patch_ready`; after apply, LIFE either holds (contract) or runs on altered acceptance machinery. Also `CLAUDE.md`, `docs/symblic/AUTOGEN.md` and `docs/symblic/RECURSION.md` (the contracts the brief names) are editable as `comment_or_doc`.
Fix: append to `GATE_DENY_RX`: `symblicos/|symblic_autogen\.py$|symblic_run\.py$|symblic_apply\.py$|fleet_runner\.py$|local_research\.py$|deep_research\.py$|cluster_engine\.py$|cluster_highpower\.py$|agent_hub\.py$|CLAUDE\.md$|docs/symblic/AUTOGEN\.md$|docs/symblic/RECURSION\.md$`, and a VALIDATE case: every file named in `CONTRACT` matches `GATE_DENY_RX`.

**24. [undefined] "Fleet loaded" needs three online worker nodes; with one or two online the fleet rest never triggers.**
Location: `LIFE.md` 5406 (`FLEET_LOADED_NODES = 3`), 2850, section 10 line 679.
Ambiguity: with two worker nodes online and both at 100 % for hours, `continuous_seconds` never grows; only the per-node LIFE ledger (which ignores non-LIFE load) rests them. The brief's "continuous all-worker node load under about an hour" then depends on how many worker nodes happen to be online.
Fix: define `fleet loaded = loaded nodes >= max(1, ceil(online LIFE nodes / 2))` (document in section 10 and section 13 as `FLEET_LOADED_FRACTION = 0.5`).

**25. [undefined] `codebase_branch` is whatever branch the live checkout had at seed.**
Location: `LIFE.md` 1835 (`git rev-parse --abbrev-ref HEAD`), 3465–3468 (`refresh_clone` fetches that name forever).
Ambiguity: a detached HEAD at seed records the string `HEAD` (every later fetch and clone fails); a feature branch at seed is tracked for the organism's lifetime and never shown to the operator.
Fix: seed refuses unless HEAD is a named branch (`git symbolic-ref --short HEAD` succeeds); print the branch in the seed message and in `life-status.py`; document in section 15 and README step 2 ("LIFE tracks the branch the live checkout is on at seed").

**26. [undefined] The installed-model inventory's text format is not pinned and fails open silently.**
Location: `LIFE.md` 3255–3273 (`parts[0] in L.NODES and parts[1]` is a model), CONTRACT 6579 (pins only the `--list` flag), section 8 line 583 ("an unreadable inventory never blocks").
Ambiguity: any other line format (`node-a: model, model`) leaves `meta.models` empty and `model_installed` true for every model, so `model_absent` never fires and missing models surface only as 6 infra outcomes per item plus a 1800 s hold of the node each time.
Fix: CONTRACT row on `bin/local-research` pinning the `--list` print format (`f"{node} {model} ..."`); when `--list` succeeds but yields no LIFE node, open notice `inventory_shape` once a day.

**27. [undefined] Benchmark job endings are never `infra`; a lost or cancelled job is the compute cell's failure.**
Location: `LIFE.md` 3059–3062 and 3078–3081 (`job status != done` → `failed`, `experiments.state='failed'`, `finish_item(..., 'failed')`), 3040–3046 (lost job → failed after `timeout + BENCH_GRACE`), section 7.7 line 498.
Ambiguity: a job the platform marks `unknown`, a node that went offline mid-job, or a cancel by STOP ends the item `failed` and grows `failures_in_a_row` (quarantine at 8), while the same conditions for program runs are `infra`.
Fix: define: job status `unknown`, `cancelled`, a job never found in the listing, and a job with no `LIFE_RESULT` line at all are `infra` (`count_infra`, experiment back to `ranked`); only a `done` job with wrong or non-positive measurements, or one past `timeout + BENCH_GRACE` with output, is `failed`.

**28. [missing] "optimises the codebase" has no path that changes code.**
Location: `BRIEF.md` 5 ("optimizes the codebase"); `LIFE.md` 102–106 (decision: measurement only), 1066–1067 (GAP 12).
Gap: the brief asks for optimisation; v2.1 measures operator templates and opens a notice. The kit defers the decision rather than defining it.
Fix (bounded, code-decided): add change class `perf_fix` to `triage-error.sym`'s alternatives only for findings created by the compute organ: a passed experiment whose benchmark template has `"repo_function": "<module>.<function>"` creates a codebase finding (taint code, test id = the template's `"test_id"`); the patch may touch only the file that defines that function (`trace_files = [its path]`), must pass the gate AND re-run the same benchmark job with the clone's code (`cmd` executed with `PYTHONPATH=<clone>`), and is bundled only when the gain still holds; everything else as local_fix. Record it as a section-7.4 class with its own `patches.change_class` value.

**29. [missing] "creates databases ... store data" has no path that stores a row.**
Location: `BRIEF.md` 6–7; `LIFE.md` 526–528, 1068–1069 (GAP 13).
Gap: the organism grows empty tables; nothing LIFE learns is ever stored in them, so "creates databases" is schema only, and the knowledge the digest organ verifies lives only in the registry.
Fix (typed, code-only, no model-written DML): a `store` stage in the database organ that inserts registry facts into `org_` tables through a fixed adapter: when a migration creates a table whose columns are a subset of `{fact_id, source_url, claim, quote, created_at}`, the tick inserts every `knowledge` row (parameters bound, never text-built SQL) and records the count in the migration's notice. Any other table stays operator-filled. Document as section 7.8 "store".

**30. [unsafe] Untrusted web content is parsed on the host outside the sandbox and inside the tick's 1 GiB cgroup.**
Location: `LIFE.md` 3538–3539 (`procs.run([py, '-I', '-B', L.FETCHER, url], FETCH_TIMEOUT, env=child_env())`), 2315–2324 (bs4/pypdf parsing in `life-fetch.py`), `units/life-tick.service` `MemoryMax=1G` (7625), 6486–6490 (`scope_argv` exists for heavy work but is not used here).
Defect: a hostile page (a decompression-heavy PDF up to safe_fetch's byte cap) can exhaust the tick's cgroup memory; the cgroup OOM killer may end the tick itself (a `tick_fault`, three in a row a fault hold), and the parser runs with the full the host filesystem readable.
Fix: run the fetch under `scope_argv([...], memory='1G')` (its own scope, `MemoryMax`, `CPUQuota`) and `prlimit --as` as benchmarks do; state in section 11 that fetch parsing is the platform's own `deep_research.safe_fetch` path and runs unsandboxed by decision.

**31. [undefined] Slot fairness: command cells always first, and a dividing cell takes its node's only slot for the whole division.**
Location: `LIFE.md` 4326–4339 (`plan_slot`: open division first, then `CASE organ WHEN 'command' THEN 0`), 4334–4337.
Ambiguity: on node-f (command + immune) a steady agenda keeps immune reviews unserved; on any node a 3-hour division starves every other cell there (node-a: selfdev + compute; node-b: digest + database).
Fix: "a division step takes the node's slot at most every second armed tick (`divisions.last_step_tick`), and a command cell goes first only when its oldest queued item is older than one tick (`created_at < now - TICK_SECONDS`), else by `last_served_at`."

### Low

**32. [undefined] Quarantine: who frees the queued items is defined two ways.**
Location: `spawn/PROTOCOL.md` §4 quarantine row ("its queued items return to the organ when an active sibling exists"); `LIFE.md` 4064–4065 (lifecycle nulls `cell_id` only when siblings exist) vs 4024–4025 (`dispatch` nulls queued items of EVERY quarantined or retired cell, siblings or not).
Fix: one sentence in both places: "queued items of a quarantined or retired cell (not at `gate`/`apply`) lose their cell at the next dispatch and wait unassigned while the organ has no active cell."

**33. [undefined] The `moved` rule omits the sample-span condition.**
Location: `spawn/PROTOCOL.md` §4 moved row and `LIFE.md` 652 ("reported offline in every sample of the last 21600 s"); code 4163–4166 also requires the node's oldest sample to be older than 21600 s.
Fix: add "and the registry holds samples for that node spanning the whole 21600 s" to both texts.

**34. [defect] The service file cites the wrong README step.**
Location: `units/life-tick.service` 1–2 (`LIFE.md` 7601–7602: "README step 4"); the timer install is README step 5 (README 45).
Fix: "README step 5".

**35. [undefined] `items.faults` never resets.**
Location: `LIFE.md` 4612–4617; section 6 lines 259–263 (every other counter states its reset; `faults` states none). A question item researched for weeks fails after three unrelated tick faults.
Fix: reset `faults=0` at every stage advance (where `infra_runs=0` is set) and say so in section 6.

**36. [defect] A run the server never stored is retried without the start cap.**
Location: `LIFE.md` 2949–2957 (`poll_runs`: `not_submitted` → re-queued with `attempts + 1`, no limit) vs 3918–3923 (`start_run`: `failed` at `START_ATTEMPTS_MAX`).
Fix: apply the same rule in `poll_runs`: `attempts >= START_ATTEMPTS_MAX → finish_item(failed, 'start refused three times')`.

**37. [defect] `life-ctl move` ignores rule 11.**
Location: `LIFE.md` 2071–2086 (checks only `NODE_CELL_CAP` and "not the same node"); `spawn/PROTOCOL.md` §4 ("`life-ctl.py move CELL NODE` does it by hand", under the rule-11 row).
Fix: refuse when the node is not available this tick's sample or, for agent cells, when the catalogue reports agy not ready; or state in section 15 that `move` bypasses rule 11 and the cell waits there.

**38. [defect] Pre-migration backups are not created with mode 0600.**
Location: `LIFE.md` 3734–3738 (`sqlite3.connect(path)` creates the file with the umask default) vs 3211 (`os.chmod(tmp, 0o600)`) and section 12 line 741 ("mode 0600" for backups).
Fix: `os.chmod(path, 0o600)` after `org.backup(backup)`.

**39. [defect] An unrefreshable clone retries `confirm` every tick without a counter.**
Location: `LIFE.md` 3440–3443 (notice `workspace`, then `return`; the item stays queued at `confirm` and each tick spends up to `GIT_FETCH_TIMEOUT` 300 s on it).
Fix: `self.count_infra(item, cell, 'confirm: the codebase clone could not be refreshed')`.

**40. [undefined] Agenda periods and the 20-entry cap.**
Location: `LIFE.md` 3161 (`entries[:20]`, entries beyond 20 silently ignored), 3170 (`period = now // (every_hours * 3600)`: periods counted from the Unix epoch), section 6 lines 290–293.
Fix: notice `agenda_invalid` "more than 20 entries: entries after the 20th are ignored"; document "periods are counted from the Unix epoch, so a new entry enters at the next tick and then once per period boundary".

**41. [undefined] The selfdev statement permits adding placeholders; the rule forbids it.**
Location: `organs/selfdev.lines.txt` 1 ("keeping every placeholder name inside those instructions"); `LIFE.md` 6272–6273 (exactly the same multiset).
Fix: "keeping exactly the same {placeholder} names inside those instructions, adding none,".

**42. [undefined] The verify-line byte rule is not in the statements.**
Location: `organs/*.lines.txt` line 2 ("writing exactly the line ... to the file verify.txt"); `LIFE.md` 6288–6297 (no BOM, CR, spaces or second line; one optional LF).
Fix: "... to the file verify.txt as its only line, ending with a single newline and nothing else".

**43. [undefined] `num_predict 320` with a thinking-capable ladder model.**
Location: `LIFE.md` 5298 (`OLLAMA_LIMITS`), `organs/organs.json` ladders (`qwen3:4b-instruct` tops seven ladders); no `think` setting anywhere.
Fix: section 8: "ladder models are non-thinking tags, or `OLLAMA_LIMITS` carries `\"think\": false`"; VALIDATE case: every ladder model is in `MODEL_MIB` AND in a `NON_THINKING` allow-list.

**44. [undefined] `rc None` means both "timed out" and "wrote more than 16 MiB"; a slow model never escalates.**
Location: `LIFE.md` 6378–6381 (`Procs.run`), 3366–3368 (`watch_timeout`), 4534–4535 (`'infra', 'program timed out'`), 4660–4663 (node held 1800 s for it).
Fix: return rc `-1` for the output kill and treat it as `failed`; keep `None` for timeouts; add "a program that times out twice on the same item at the same rung escalates one rung" to section 8.

**45. [undefined] Operator commands refuse when a tick holds the lock longer than 600 s.**
Location: `LIFE.md` 1654, 1661–1672 (`LOCK_WAIT = 600`, then "try again after it ends"), section 15 line 940; a tick can hold the lock for up to 2700 s.
Fix: `LOCK_WAIT = UNIT_TIMEOUT` (3000) with a progress line every 60 s, or a documented `--wait SECONDS` flag; list in section 15 which commands never need the lock.

**46. [unsafe] Rows and folders that are never pruned.**
Location: `LIFE.md` 3223–3232 (retention: call folders and samples only), section 13 lines 890–892 ("Deleted automatically: ... Nothing else"); `calls` rows (up to 1200 a day), `STATE/runs/<request_id>/`, `inbox-done/`, `inbox-refused/`, acked `notices`, abstained OVERFLOW `items` rows grow for the organism's lifetime until the 10 GiB storage hold stops all work.
Fix: define retention for each in section 13: `calls` rows older than 90 days of ended items; `STATE/runs/` folders of `collected` runs after 14 days; `inbox-done/` files after 30 days; acked notices after 90 days; abstained OVERFLOW items after 7 days.

**47. [undefined] Watched tests must run under the system Python with no `.venv`.**
Location: `LIFE.md` 3346 and `checks/devcheck-gate.sh` 41 (`/usr/bin/python3 -s -B -m unittest`); README 41–42 says only "each finishing in under 90 s".
Fix: README: "each runnable as `/usr/bin/python3 -s -B -m unittest ID` (system Python, no .venv, no network, an empty HOME) in under 90 s; a test that needs the .venv ends as `watch_error`, never a finding".

**48. [undefined] `retire --force` asks for the cancel but leaves the `runs` rows live.**
Location: `LIFE.md` 2058–2059 (cancel CLI called, rows untouched), section 15 retire row.
Fix: state "the registry rows are settled by the next tick's poll (the run shows as live until then)" or update the rows as `stop_everything` does.

**49. [defect] A `needs_work` round counts the same finding `done` twice.**
Location: `LIFE.md` 3645 (`finish_item(..., 'done')` at the gate), 4874–4876 (the finding is re-queued at `patch`), 3991–3992 (`items_done + 1`, metric `items_done`); efficiency (rule 10) and the abstain window see the same item twice.
Fix: count a finding `done` once, when its patch leaves review (`accept`/`reject`), or subtract on re-queue.

**50. [defect] The service runs the tick without `-I`.**
Location: `units/life-tick.service` (`LIFE.md` 7617: `/usr/bin/python3 -B`); every other Python the kit starts uses `-I -B`, so `PYTHON*` variables and the user site can alter the coordinator's imports.
Fix: `ExecStart=/usr/bin/python3 -I -B /home/operator/host-checkout/docs/life/bin/life-tick.py` (life-tick inserts its own directory and REPO explicitly).

**51. [undefined] A migration may reference an `org_` table that does not exist.**
Location: `LIFE.md` 6198–6200 (prefix check only); probe: `CREATE TABLE IF NOT EXISTS org_x (a INTEGER REFERENCES org_y (id));` against a snapshot without `org_y` → accepted (SQLite defers the check to insert time).
Fix: "every REFERENCES names an org_ table that exists in the snapshot or is created earlier in the same migration" (check against `existing` in statement order).

**52. [undefined] `local_research.research`'s result keys and side effects are not pinned.**
Location: `LIFE.md` 2419–2425 (`answer`, `sources[].url/title`, `steps`, `error`), 2371–2372 ("writes no report"), CONTRACT 6577 (signature only).
Fix: CONTRACT rows for the `return {...}` line of `research()` and for the report write that only `bin/local-research` makes; set the wrapper's `HOME` to a scratch directory if `research()` may write caches.

**53. [undefined] Gate and check exit codes carry two meanings.**
Location: `checks/devcheck-gate.sh` 14–15 ("the first failing step's exit code; 2 = bad arguments, 3 = the module does not resolve, 125 = sandbox unavailable") and 40–41 (`life-check.py sandboxed` returns the candidate command's OWN exit code, which may be 2, 3 or 125); `bin/life-check.py` docstring (`LIFE.md` 1499) "Exit 0 pass, 1 fail, 2 usage, 125 sandbox" while `sandboxed` passes any code through.
Fix: the gate maps step 2 to exit 4 and step 3 to exit 5 whatever the inner code (`|| exit 4`, `|| exit 5`); `life-check.py sandboxed` returns 1 for every nonzero inner code except 125, which it keeps.

**54. [undefined] Routing labels are undefined for command, immune and finding items.**
Location: `LIFE.md` 4014–4017 (`label()` falls back to `subject` — the word "patch"/"proposal" — or the hex item id), 4033–4034, section 9 lines 654–657.
Fix: define per kind: command → the command text; finding → `test_id` plus the first error line; patch/proposal → the originating finding text or lesson (through `origin`).

**55. [undefined] The precedence decision over the operator's 10 Oct words lives outside the kit.**
Location: `LIFE.md` 21–32 (refers to `workshop/round-2/decisions.md`, not in VALIDATE's inventory), `BRIEF.md` 15–17 ("no time cap", "spawn as many agents as needed", "may run for days").
Fix: a `DECISIONS.md` in the kit with one line per overridden operator word and the bound that replaces it, signed by the operator, listed in VALIDATE check 1 and embedded in LIFE.md; until then the kit's authority on those points is undefined.

**56. [undefined] `SECRET_RX` misses shapes section 11 says it catches.**
Location: `LIFE.md` 5491–5496, section 11 lines 711–713 ("a key word followed by : or = and a 6+ character value"); probes: `token=abcdefghijk` → not matched; `PASSWORD: "two words here"` → not matched.
Fix: add `token|secret|credential|private[_-]?key` to the key-word group and a quoted-value alternative `['"][^'"]{6,}['"]`; keep the section-11 list equal to the regex's alternatives.

**57. [undefined] A merged command never gets a report.**
Location: `LIFE.md` 4766–4768 (`made and not created` → notice `command_merged`, state `owner`), 3301 (reports are written only for `dispatched` commands), section 7.1 line 319.
Fix: define: a merged command ends `done` at once with notice `command_merged` naming the original command id whose report covers it.

**58. [undefined] "Slow" is judged only for failing tests and includes sandbox start-up.**
Location: `LIFE.md` 3373–3376 (`wall > WATCH_SLOW` checked after `rc != 0` only), section 7.4 line 385; a passing 100 s test is accepted while the same test failing is "never patched".
Fix: measure and report `watch_too_slow` for passing runs too, and say in README that the 90 s is wall time of the sandboxed run including scope and sandbox start-up.

## Tallies

Class counts: undefined 41, defect 11, unsafe 4, missing 2.

FINDINGS_TOTAL=58
UNDEFINED_DETAILS=41
VERDICT=CHANGES NEEDED

Review artifacts: [local results path and commit id removed for publication; kept privately by the operator]
