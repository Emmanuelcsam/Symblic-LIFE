# LIFE v1 — round 1 local adversarial critique

Critic: local reviewer (Claude Code subagent). Written 2026-10-11 01:44. Nothing was run except
model-free checks: `bin/symblic check` on the six genome files (all `ok`), the pure functions
`symblic_autogen.lint / plan_checks / localize / normalize` on every organ line and policy,
`checks/heat-gate.sh` and `checks/kill-switch.sh` (read /proc and a path only), and
`command -v sqlite3`. No model, agent, task start, cluster job or network call was made.

Scope read: BRIEF.md, README.md, LIFE.md (all 1363 lines, appendices compared with the files),
organs/*, policies/*, genome/*, checks/*, db/schema.sql, bin/*, spawn/PROTOCOL.md, spawn/example/*,
VALIDATE.sh. Platform code checked: `symblic_autogen.py`, `symblicos/autogen.py`, `bin/symblic-task`,
`symblicos/workspaces.py`, `agent_hub.py` (`make_worktree`, `carry_over`, `provision_remote`,
`_check_remote`, `REMOTE_ENGINES`), `agent_integrations.py:apply_work`, `cluster_engine.py`
(`TENANT_STACKS`, `UNMEASURED_TENANTS`), `cluster_power.py`, `cluster_highpower.py`,
`docs/fleet-power.md`, `docs/symblic/RECURSION.md` §3.1, `cluster_data/nodes.json`.

Legend: **[CODE]** = a kit claim or behaviour the platform code contradicts (high by rule).
**[U]** = an undefined or ambiguous detail (counted in UNDEFINED_DETAILS).

---

## A. Claims and behaviour the code contradicts

### 1. HIGH [CODE] — The "perpetual" organs are bounded and die after 3 generations
- Location: LIFE.md §2 table ("perpetual"), Appendix B, every `policies/*.json` except database,
  `bin/life-seed.sh` lines 44-52, README "they are perpetual".
- Defect: none of the policies sets `until_done`. `symblic_autogen.decide()` (perpetual branch):
  `if not until and generation >= policy['generations']: accept … 'perpetual lane reached its
  generation cap'`. `generations` is absent, so `DEFAULTS['generations'] = 3` applies: every organ
  stops after its 3rd promoted generation (the command organ after about 6-10 minutes). Also
  `if not until and len(trailing) > policy['regenerate']: fail`: two or three failed generations in
  a row end the organ as `failed`. RECURSION.md §3.1 ("No generation cap", "failed generations never
  fail the lane") describes **until_done** lanes. The kit misread it as applying to all perpetual lanes.
  In addition, `wall_seconds` (6-24 h) sets a deadline after which `exhausted` stops the lane. So the
  organism can live for at most 24 h even with until_done, and the BRIEF's "research lanes may
  run for days" fails as well.
- Fix (replacement policy core for every perpetual organ):
  ```json
  {"version": 1, "perpetual": true, "until_done": true, "candidates": 1, "depth": 0,
   "agents_max": <organ cap from §C-13 table>, "wall_seconds": <organ cap>,
   "interval_seconds": <organ interval>, "attempt_seconds": <organ cap>, "saturation": <0 or N>,
   "strategies": ["fresh", "feedback"], "syntax": true, "require_change": true,
   "checks": {"0": ["bash checks/organ-<name>.sh"]}, "final": []}
  ```
  Write this rule into LIFE.md §2: "A lane is perpetual only with `until_done: true`. With
  until_done, exhausting `agents_max` or `wall_seconds` makes the run **stuck** (not failed). The
  renewal rule in finding 2 is the only way it continues."

### 2. HIGH [CODE][U] — Renewal and re-seeding cannot work as written, and perpetuity is undefined
- Location: README "re-seed or `autogen resume` the ones you want back", `bin/life-seed.sh`
  (`--id life-<organ>`), LIFE.md §9.
- Defect: `symblicos/autogen.py:submit` sets `run_id = 'autogen-' + sha256(client_request_id)[:24]`.
  If that record already exists with the same digest, the submit is a **duplicate** and a terminal
  run is not rescheduled (`if not duplicate or row['status'] not in TERMINAL`). If the digest
  differs, the submit gets 409. Re-running `life-seed.sh` therefore never brings a dead organ back.
  Nothing in the kit defines how a perpetual organism stays alive once a lane is stuck or completed.
  The operator's "nothing restarts itself" rule and "a living breathing cluster" conflict here, and
  the kit has to resolve that conflict explicitly.
- Fix (atomic):
  - The request id is `life-<organ>-s<YYYYmmddHHMMSS>` (UTC, from `date -u +%Y%m%d%H%M%S`).
  - The kit adds the operator-armed file `~/.local/state/life/ARMED`, created by the operator, never by
    code. While ARMED exists, the tick may **renew** a seed organ whose run is `stuck` with reason
    `budget or deadline exhausted…` by calling `bin/symblic-task autogen resume <run_id>
    --agents-max <cap> --wall-seconds <cap>`, at most once per organ per 6 h. It never renews one
    whose status is `failed`/`unknown`/`cancelled`, and it writes one `renewals.jsonl` row
    `{organ, run_id, at, reason}` for each renewal.
  - Removing ARMED stops all renewals. Document this as the operator's standing consent. It is not a
    service restart.

### 3. HIGH [CODE] — `life-*` ids never appear in `autogen list`: the budget gate, status and kill switch are all dead
- Location: `bin/life-spawn-tick.py:live_run_count` (line 94-99), README KILL SWITCH loop,
  `bin/life-status.py` lines 20-24, README "`autogen get life-learning`", "`autogen cancel life-<organ>`".
- Defect: `bin/symblic-task:cmd_autogen_list` prints `r["id"]` (= `autogen-<24hex>`), the date,
  the status, the counts and `lines[0][:50]`. None of the organ statements contains `life-` in
  its first 50 characters ("Read every file in the folder /home/operator/symbli…"). The
  consequences:
  - `live_run_count()` always returns 0, so the budget gate never holds and births are unbounded.
  - The README loop `awk '/life-/{print $1}'` cancels nothing.
  - `life-status.py` shows no runs.
  - `autogen get|cancel life-<organ>` returns 404 `Unknown autogen run id.` (`_path` requires
    `^autogen-[a-f0-9]{24}$`).
  - The CLI lists 20 rows by default and the server lists at most 100.
- Fix:
  - Keep a code ledger `~/.local/state/life/runs.jsonl` with rows `{request_id, run_id, organ,
    cell_id, parent_id, depth, node, engine, kind: seed|child|renewal, at}`. The ledger computes
    `run_id = "autogen-" + sha256(request_id).hexdigest()[:24]` and also records the id printed by
    `start --json`.
  - `live_run_count()` = the number of ledger run_ids whose
    `bin/symblic-task autogen get <run_id> --json` status is in {queued, active}.
  - The kill switch, status and cancel commands iterate over that ledger.
  - The README commands use `$(life-id <organ>)`, a helper that prints the run id.

### 4. HIGH [CODE] — All organs share one root `verify.txt`, one `AUTOGEN-INDEX.jsonl` and one checkout base
- Location: LIFE.md §2 "each organ … keeps its own `AUTOGEN-INDEX.jsonl` dedup ledger", every
  organ line "write … to the file verify.txt", `bin/life-status.py` (reads `organ-<o>/verify.txt`).
- Defect:
  - `localize()` and `plan_checks()` (run on every organ line) resolve `verify.txt` to the
    **workspace root** for all ten organs.
  - `_index_items` writes `AUTOGEN-INDEX.jsonl` at `row['base']['cwd']`, which is the shared
    `/home/operator/symblicos/projects/life` for every organ and every child. The kit's
    per-organ-index claim is false.
  - Ten runs promote into one folder through `apply_work`, and each one rewrites `verify.txt`.
    The 3-way merge raises "N file(s) clash" and the attempt fails with `CONFLICT`.
  - `life-status.py` reads `organ-<o>/verify.txt`, which is never written.
- Fix (choose and state one):
  - **Recommended:** one git workspace per organ: `symblic-task workspace life-<organ>`, with
    `--cwd /home/operator/symblicos/projects/life-<organ>`. Each organ then owns its own index,
    checkpoint, HANDOFF.md and verify.txt. Cross-organ data moves only through the code
    circulation step (finding 24).
  - Or keep one workspace, but every line names
    `/home/operator/symblicos/projects/life/organ-<name>/verify.txt` absolutely, the checks use
    `test -s organ-<name>/verify.txt`, and LIFE.md states that the dedup index is shared by all
    organs.

### 5. HIGH [CODE] — Every acceptance check is vacuous: only "some verify.txt exists" is checked
- Location: every organ line (all start with `Read`/`Research` = `READ_ONLY_RX`), policies `checks`.
- Defect: `plan_checks` on each perpetual line returns exactly `[exists verify.txt, command
  test -s verify.txt]`. The real products (`routed.jsonl`, `sources.jsonl`, `facts.jsonl`,
  `metabolism.jsonl`, `verdicts.jsonl`, `status.json`, `results/`) are not even extracted as
  files. `_locate` falls back to a basename search, and `carry_over` copies the previous
  `verify.txt` into each new checkout's baseline, so `exists` passes before the worker does
  anything. The only real gate is `require_change` (any file changed). "Code decides" therefore
  reduces to "the agent touched something".
- Fix: one model-free check script per organ, `checks/organ-<name>.sh`, run as the policy check
  for statement 0. Each script:
  (a) validates every new JSONL line of the organ's product against the schema in finding 25
      (with `python3 -c` and `json`, no network);
  (b) requires `new_lines >= 0` and requires `verify.txt` to match the regex in finding 27;
  (c) refuses any changed path outside `organ-<name>/` (finding 21b).
  Exit 0 pass, 1 fail. Start each organ statement with a writing verb ("Append …", "Write …")
  so that `plan_checks` also adds `exists`+`changed` for the product file.

### 6. HIGH [CODE] — An idle generation fails: `require_change` with an unchanged `verify.txt` is NO_OUTPUT
- Location: every organ policy (`require_change: true`), organ verify lines.
- Defect: with an empty inbox, no new source or no finding, the worker writes the same `verify.txt`
  ("0"). Control files are excluded from the change set (`CONTROL_FILES`), so the change count is 0,
  `classify()` returns `NO_OUTPUT`, and repeated idle generations fail or stick the lane. A healthy
  organism with nothing to do dies.
- Fix: every verify line writes one line in the format
  `organ=<name> generation_utc=<YYYY-MM-DDTHH:MM:SSZ> new=<int> status=<ok|idle>`. The timestamp
  guarantees a change, and `status=idle` with `new=0` is a pass by the organ check.

### 7. HIGH [CODE] — The reproducer never runs, and the spawn queue cannot be reached
- Location: LIFE.md §1, §4; spawn/PROTOCOL.md; README "Turn on reproduction"; `bin/life-seed.sh` line 28.
- Defect:
  - No organ line runs `genome/reproduce.sym` or writes a spawn record. The BRIEF's core
    requirement ("each subline … two agents … one to reproduce") is not implemented anywhere.
  - The queue is `KIT/spawn/queue` = `/home/operator/host-checkout/docs/life/spawn/queue`,
    inside the **live dashboard checkout**. It is outside every attempt checkout, which is the
    life workspace only (`make_worktree`/`provision_remote` push just that branch to a worker node).
  - `life-seed.sh` and the tick create and write files (`queue/approved/rejected/hashes.txt`) in
    the live repo, which contradicts the tick docstring "touches no files outside the organism
    workspace" and leaves untracked files in a checkout that others edit.
- Fix (atomic):
  - Move all spawn state to `~/.local/state/life/spawn/{queue,approved,rejected,hashes.txt,
    retired.txt,runs.jsonl}`.
  - Define the reproducer as a **code step of the tick**. After every `generation_done` event of
    a LIFE run (read via `autogen get <run_id> --json`), the tick:
    (1) computes the reproducer inputs itself (finding 31);
    (2) runs `bin/symblic run genome/reproduce.sym --by ollama:qwen3:4b-instruct@node-a --dir
        ~/.local/state/life/repro/<run_id>/g<generation> --input …` (through the fleet runner on a worker node; it
        is the second agent of the cell);
    (3) on `divide`, builds the record from the template in finding 8.
  - Workers never write spawn records.

### 8. HIGH [U] — No rule turns a reproducer verdict into a spawn record
- Location: PROTOCOL.md "statements.txt", reproduce.sym `return plan`, spawn/example.
- Defect: reproduce.sym returns two clauses of at most 14 words. The kit does not say who turns
  them into a lint-clean `statements.txt`, `policy.json` and `lineage.json`. It also leaves these
  undefined:
  - which 8 hex digits are used (and who chooses them);
  - what the `generation` in `cell_id` means;
  - the child folder name (the example invents `organ-learning-c1`);
  - the child node and engine;
  - how a child statement keeps the organ's verify format.
  A model-written record is unreviewable.
- Fix (code template, one per organ, in `spawn/templates/<organ>.json`):
  - `{"statement": "<Organ verb sentence with {focus} and {folder}>", "policy": <organ policy
    verbatim>, "node_pool": [...]}`.
  - `hex8 = sha256(parent_run_id + ":" + str(parent_generation) + ":" + child_letter).hexdigest()[:8]`.
  - `cell_id = f"{organ}.{parent_generation}.{hex8}"`.
  - `folder = f"/home/operator/symblicos/projects/life-{organ}/cells/{hex8}"`.
  - `node` = the first node in `node_pool` with no live LIFE lane (from the ledger).
  - `engine = "agy"` (or `local`, per finding 15).
  - `focus` = the reproducer clause, after `re.sub(r'[^A-Za-z0-9 ,.-]', '', focus)[:120]`.

### 9. HIGH [U] — What "divide" means for the parent is undefined
- Location: LIFE.md §1 ("exactly two child foci"), spawn/example/reason.txt ("Child A (this
  record) … child B keeps the remainder").
- Defect: the kit does not say whether a divide produces one record or two, or whether the parent
  keeps running with its old statement (in which case it duplicates child A's work), narrows, or
  retires. The example contradicts §1.
- Fix: "On `divide` the tick writes **two** records (A and B). After both are approved, the tick
  cancels the parent run (`autogen cancel <parent_run_id>`) and marks it `retired_at` in lineage
  with reason `divided`. If either record is rejected, neither child is born and the parent continues."

### 10. HIGH [CODE] — The tick trusts model- or worker-written lineage, node, engine and policy
- Location: `bin/life-spawn-tick.py` lines 144-163; PROTOCOL.md "lineage.json", "policy.json".
- Defect:
  - `depth` is self-reported, so a record that always says `depth: 0` defeats the depth limit.
  - `organ`, `parent_id`, `node` and `engine` are not validated. `node` defaults to `node-i`, and
    `host` or `node-arm` are accepted even though PROTOCOL says never. Any engine is accepted,
    including cloud `claude`/`codex`, and `copilot`, which `REMOTE_ENGINES` excludes.
  - The policy passes `normalize()`, which **allows** `until_done: true` with `agents_max`/
    `wall_seconds` 0 (unlimited). An omitted `strategies` defaults to the server default, which
    includes `other_node` (it can move to the host or the ARM node).
  - PROTOCOL's own rules ("never 0/unlimited for a child", "never other_node") are not enforced.
- Fix: the tick enforces
  - `depth = ledger[parent_id].depth + 1` (refuse if the parent is unknown);
  - `organ in ORGANS`;
  - `node in {"node-a","node-b","node-d","node-f","node-i"}`;
  - `engine in {"agy"}` (v1);
  - the policy, after normalize, must equal the organ template policy except for an allow-listed
    key set `{interval_seconds}` within ±50 %;
  - `0 < agents_max <= 24`, `0 < wall_seconds <= 86400`, `"other_node" not in strategies`,
    `strategies` given explicitly.

### 11. HIGH — The content-hash dedup (the "runaway brake") can be bypassed with one space
- Location: tick line 155-158, PROTOCOL gate 7, schema `lineage.content_hash` comment.
- Defect: the hash covers the raw bytes, so a changed space, newline or key order makes a new hash.
  The schema comment says `statements_file || policy_json` and the tick hashes
  `statements + "\n" + policy`, so the two definitions disagree.
- Fix: `chash = sha256(json.dumps({"organ": organ, "lines": A.statements(text), "policy":
  A.normalize(spec)["sha256"], "focus": focus.lower().split()}, sort_keys=True,
  separators=(",",":")).encode()).hexdigest()`. Use the same definition in schema.sql, PROTOCOL
  and the tick.

### 12. HIGH [CODE] — The heat gate measures the host, and its thresholds are not in fleet-power.md
- Location: `checks/heat-gate.sh`, LIFE.md §6, PROTOCOL gate 2.
- Defect:
  - The operator's heat rule is about **worker nodes** ("continuous all-worker node load under about an hour").
    The gate reads the host's `/proc/loadavg` and `/proc/pressure/io` only.
  - The script says "Thresholds from docs/fleet-power.md", but fleet-power.md contains no 4.0 or
    40.0 threshold.
  - The host has 6 CPUs (`nproc`), so load 4.0 is not a heat signal. avg10 is a 10-second spike
    value: the check during this review printed `ALLOW load=3.24 io_full_avg10=2.43` while
    avg300 was 32.69.
- Fix:
  - The gate HOLDs when any of these is true:
    (a) `~/.local/state/life/metabolism.json` (code-written, finding 28) has `fanout=false` or is
        older than 900 s;
    (b) the host `load5 >= 0.75*nproc`;
    (c) the host io `full avg60 >= 10.0`;
    (d) `GET /api/cluster/highpower/state` reports cool mode on.
  - Exit codes: 0 ALLOW, 4 HOLD, 5 cannot read (treated as HOLD).

### 13. HIGH [U] — No numeric duty cycle; node-i carries four overlapping heavy lanes plus the autonomous agent
- Location: LIFE.md §2 table (codebase, selfdev, compute and immune all on node-i), §6.
- Defect:
  - Each node-i lane may run 3600 s attempts, and the interval is measured from the attempt's
    finish (`decide`: `due = last.finished + interval`). Four independent lanes overlap freely, so
    node-i can stay busy for hours, which breaks the 1-hour rule.
  - `cluster_engine.UNMEASURED_TENANTS` lists node-i as hosting "the autonomous agent worker" and node-d
    as hosting "an uptime monitor plus other workers". The kit does not mention either.
  - "Each organ's wall_seconds and interval_seconds build the rest in" is not a defined rule.
- Fix: one table, enforced by the tick through the ledger:
  - At most **one** LIFE lane per worker node.
  - `attempt_seconds <= 900`.
  - `interval_seconds >= 2 * attempt_seconds`.
  - The tick holds births and renewals for a node whose `busy_minutes_last_60 >= 45`, computed
    from attempt start and finish times in `autogen get`.
  - Placement:

    | Organ | Node |
    |---|---|
    | command | node-f |
    | codebase | node-i |
    | learning | node-d |
    | digest | node-b |
    | compute | node-a |
    | immune | node-f, only after command is idle |

    selfdev is paused in v1 (finding 20).

### 14. HIGH [CODE] — Agent lanes on the host break "the host only orchestrates" and the code-only launch rule
- Location: LIFE.md §2 rows 7 and 9 (metabolism and heartbeat: `agy` on `host`), `life-seed.sh`
  lines 86 and 88.
- Defect: BRIEF: "model/agent work runs on the worker nodes, the host only orchestrates". These two lanes
  start an agy CLI agent on the host every 300 s, about 576 sessions a day. A CLI agent on the host
  is not Landlock-sandboxed (`sandbox_prefix` applies to model-written test scripts) and can run
  `bin/symblic-task start` itself, which breaks the "No model ever launches a run" invariant.
  Neither lane needs a model.
- Fix: delete both agent lanes. Write `bin/life-metabolism.py` and `bin/life-heartbeat.py` as pure
  code run by the same timer before the spawn tick. They read the loopback API and run records and
  write `~/.local/state/life/metabolism.json` and `status.json`. LIFE then has **no** lane on
  The host, and worker node agents cannot reach `:8080` (no tunnel), which enforces the launch rule by
  topology.

### 15. HIGH [CODE] — The lightweight-model lanes cannot be reached from a worker node attempt, and GAP 2 is wrong
- Location: LIFE.md §1 ("the lane's attempt … calls the matching lightweight-model program"), §3,
  §11 GAP 2, organ lines ("by running the command classifier", "source fact extractor").
- Defect:
  - `genome/*.sym`, `bin/symblic` and `bin/local-research` live in host-checkout. A worker node
    checkout holds only the life-workspace branch (`provision_remote`).
  - SearXNG is at `127.0.0.1:18888` on **the host**, so a worker node cannot reach it on its own loopback.
  - The statements never give the program path, and the injected `CHECKOUT_LOCK` tells the worker
    "do not explore other … folders".
  - The agy agent (a cloud model) therefore makes every decision itself, which contradicts the
    BRIEF's "extremely lightweight models".
  - GAP 2 says "Lightweight local models cannot *be* autogen workers". `symblicos/autogen.py`
    admits `LOCAL_ENGINE='local'` when the run's base engine is `local`
    (`admitted_engines('local')`). `submit` requires a `model` and refuses `host` for local runs.
- Fix:
  - (a) Correct GAP 2: "`--engine local --model qwen3:4b-instruct --node node-X` makes a cell a
    bare local model (cli-agent over Ollama, 8192 ctx). Its rotation may move to CLI engines through
    `other_engine`, so local cells use `strategies: ["fresh","feedback"]`."
  - (b) Typed decisions (classify, triage, extract, rank, review, reproduce) run as **code steps
    on the host** that call `bin/symblic run genome/<p>.sym --by …@node-X` through the fleet runner. Agent
    lanes only produce files.
  - (c) The learning lane runs `bin/local-research` from the host code step, never from a worker node
    agent.

### 16. HIGH [U] — No cloud quota or attempt budget, and the engine rotation includes engines that cannot run there
- Location: §3 "When a CLI agent is allowed", `strategies` containing `other_engine` in 7 policies.
- Defect:
  - Every generation is a cloud CLI session (agy). `other_engine` rotates through
    `ENGINES ∩ ADMITTED_ENGINES` in hub order (`triad, gpt, gemini, claude, codex, agy, copilot,
    mistral, …` filtered), **not** the claimed order "agy → codex → claude → copilot/mistral".
  - `copilot` is not in `agent_hub.REMOTE_ENGINES`, so it is refused on any worker node (REFUSAL). The
    rotation also spends Claude/Codex weekly limits.
  - There is no daily cap on attempts across LIFE.
- Fix:
  - `strategies: ["fresh","feedback"]` for every lane (no `other_engine`).
  - The tick keeps `~/.local/state/life/budget.json`
    `{date, attempts_started, cap: 200}`, computed from the summed `agents_started` deltas. It
    holds births and renewals when `attempts_started >= cap`.
  - The operator changes `cap` by editing the file.

### 17. HIGH [U] — The codebase organ is not wired
- Location: organs/codebase.lines.txt, triage-error.sym note, README "only for the change classes
  the master script permits", `checks/devcheck-gate.sh`.
- Defect:
  - (a) Nothing produces `organ-codebase/findings`. The seed creates an empty folder and no organ
    runs tests or reads logs.
  - (b) The "permitted change classes" appear **nowhere** in LIFE.md.
  - (c) Patches would be against host-checkout, which is not in the attempt's checkout.
    `devcheck-gate.sh` needs a dashboard checkout that the worker node worker does not have.
  - (d) No step moves an accepted patch into the live checkout. Autogen promotes into the life
    workspace only.
  - (e) The "request queued for you" for restart-gated changes has no file or schema.
- Fix (v1):
  - PERMITTED = {`test_only`, `comment_or_doc`}. Everything else is written to
    `~/.local/state/life/operator-requests.jsonl` as `{id, change_class, patch_path, reason, at}`
    and never applied.
  - Findings producer: a code step runs `bin/devcheck --json` (or the focused failing tests the
    operator lists in `organ-codebase/watch.txt`) on the host at most once per 6 h, niced, and writes
    one `findings/<sha8>.json` per failure.
  - A patch is a `git diff` file only. The operator applies it with the existing Work→Apply.
    Nothing in LIFE applies to host-checkout.

### 18. HIGH — The rollback recipe destroys others' uncommitted work
- Location: LIFE.md §7 ("a bad apply is reverted with `git checkout -- <file>` in the live tree").
- Defect: the live checkout routinely holds others' uncommitted edits (project CLAUDE.md).
  `git checkout -- <file>` discards every uncommitted change in that file, not just LIFE's apply.
  `agent_integrations` has no undo path.
- Fix: "LIFE never applies to the live checkout in v1 (finding 17). If a later version does, it
  records `{path, before_sha256, after_sha256, before_blob_path}` per file before the apply, and
  a rollback restores `before_blob` only when the current file's sha256 equals `after_sha256`;
  otherwise it reports the file to the operator."

### 19. HIGH — The kill switch does not stop the organism and can be deleted by a worker
- Location: README KILL SWITCH, `checks/kill-switch.sh`, tick gate 1, PROTOCOL gate 1 ("spawn/../STOP").
- Defect:
  - (a) STOP only blocks births. Perpetual lanes keep running new generations indefinitely.
    "Lanes finish their current generation and then rest" is false, because `decide` keeps
    issuing `perpetual_next`.
  - (b) STOP sits inside the git workspace. `carry_over` commits it into each attempt's baseline,
    so a worker that deletes it produces an `apply_work` plan `delete` (ours == base), which
    removes the operator's STOP.
  - (c) PROTOCOL's "spawn/../STOP" is `KIT/STOP`, not `ROOT/STOP`.
  - (d) The "stop everything" loop is broken (finding 3).
- Fix:
  - Two files outside every workspace: `~/.local/state/life/FREEZE` (no births or renewals) and
    `~/.local/state/life/STOP`.
  - On STOP the tick cancels every ledger run in {queued, active} via
    `bin/symblic-task autogen cancel <run_id>`, logs one line per run and exits 3.
  - Add `bin/life-stop.sh`, which does the same immediately without the timer.

### 20. HIGH — Untrusted internet text feeds self-modification and shell commands
- Location: learning → digest → (lessons) → selfdev ("improvement to a genome program or organ
  policy"), the command inbox, the compute experiments.
- Defect: web pages are untrusted. Facts, lessons and proposals derived from them flow into agent
  prompts that have a shell, and into proposals that change LIFE's own genome and policies.
  CLAUDE.md: "An agent reading untrusted mail/web must not receive personal Workspace tools in that
  run". `carry_over` also copies the whole workspace (including the operator's inbox commands) to worker nodes
  and into cloud agent context. No taint rule or adoption gate exists.
- Fix:
  - Every row derived from the web carries `"taint": "web"`.
  - A tainted row may be quoted as data in a prompt, but it is never a statement, check, policy,
    command or canary.
  - selfdev proposals are never adopted by code in v1. They go to `owner-requests.jsonl`.
  - The inbox accepts files only with operator uid and mode 0600, at most 4000 bytes, and lines
    matching the credential screen (`re.search(r'(?i)(api[_-]?key|token|password|secret|BEGIN [A-Z ]*PRIVATE KEY)', text)`)
    are refused into `inbox-refused/`.
  - selfdev is **paused** in v1 until the operator arms it with `~/.local/state/life/SELFDEV_ARMED`.

### 21. HIGH — The compute organ executes model-proposed shell on worker nodes
- Location: organs/compute.lines.txt ("run the highest-scoring experiment whose measurement command
  …"), schema `experiments.measurement` ("the exact shell command").
- Defect: an agent runs an arbitrary command from `experiments.jsonl`, a file that models write
  and that no code validates. This is unbounded CPU, disk and heat, and code execution.
  `rank-experiment.sym` is never invoked by any line, and nothing produces `experiments.jsonl`.
  BRIEF: use the existing admitted launch paths.
- Fix:
  - `measurement` must be one of the operator-approved templates in
    `organ-compute/benchmarks.json` (`{id, argv[], cpus, memoryMiB, timeout<=900}`), and
    parameters must match `^[A-Za-z0-9._=-]{1,64}$`.
  - Code runs it with `POST /api/cluster/map` (`targets` = the LIFE node, `parallel` 1,
    `timeout` <= 900), never inside an agent.
  - Proposals come from a code step that runs `rank-experiment.sym`. Only `score >= 60 and
    risk != "high"` is runnable.

**21b. HIGH — Workers may write anywhere in the workspace.** Part of 21 and 5: workers can write anywhere in the shared workspace (other organs'
ledgers, the queue if it were inside, STOP). The fix is the scope rule in finding 5(c), plus one
workspace per organ (finding 4).

### 22. HIGH [CODE] — The database organ cannot pass on this host and fights the seed
- Location: organs/database.lines.txt, policies/database.json `final`, LIFE.md §5.
- Defect:
  - (a) `command -v sqlite3` returns rc=1 on the host, where `final` checks run in the project
    folder, so `bash organ-database/check_schema.sh` always fails.
  - (b) `life.sqlite3` is a binary inside the git workspace. `carry_over` copies it and
    `apply_work` refuses binaries that both sides changed ("binary; both of you changed it").
  - (c) Line 1 "Create the file …/db/schema.sql" overwrites the copy the seed already placed
    (`cp -n`). An identical result is NO_OUTPUT, and a different one diverges from the kit.
  - (d) Line 1 says "exact columns and types named in the master script", but the worker cannot
    see LIFE.md.
  - (e) `plan_checks` on line 3 (check_schema.sh) requires `life.sqlite3` to be **changed**, which
    creating a checker never does. Line 0 requires `schema.sql` at the checkout root (bare name),
    not `db/schema.sql`.
- Fix: retire the database agent lane in v1.
  - `bin/life-db.py` (code, the host, python3 `sqlite3` module) creates
    `~/.local/state/life/life.sqlite3` outside git with `PRAGMA journal_mode=WAL;
    PRAGMA busy_timeout=5000;`, applies `db/schema.sql` idempotently and is the **only** writer.
  - New tables come only through numbered migrations `db/migrations/NNNN_*.sql` that the operator
    adds, each applied once and recorded in a `schema_migrations(version INTEGER PRIMARY KEY,
    applied_at INTEGER)` table.

### 23. HIGH [U] — No component writes the database
- Location: db/schema.sql comments ("Each spawn writes one row", "written by heartbeat"), LIFE.md §5.
- Defect: no line, script or tick step inserts into `knowledge`, `lineage`, `metrics`, `commands`
  or `experiments`. The heartbeat line writes `status.json` only, and the tick writes no lineage row.
- Fix: `bin/life-db.py ingest`, run by the timer after the tick, does the following:
  - inserts `lineage` on every approval or retirement from `runs.jsonl`;
  - inserts `metrics` from every new `generation_done` (organ, run_id, generation, items_new,
    trailing failures, node, finished);
  - inserts `knowledge` from new `facts.jsonl` rows with `verified=1` only;
  - inserts `commands` from `routed.jsonl`;
  - inserts `experiments` from `results/*.json`.
  - All inserts use `INSERT OR IGNORE`, and a byte offset per file in `ingest-offsets.json`
    makes the step idempotent.

### 24. HIGH [U] — The organs' inputs and outputs do not connect
- Location: organs/*.lines.txt, `life-seed.sh` lines 29-30.
- Defect:
  - learning writes `organ-learning/sources.jsonl`, but digest reads `organ-digest/sources.jsonl`,
    so digest never gets input.
  - `questions.txt` is seeded empty and nothing writes it.
  - `routed.jsonl` has no consumer, so commands go nowhere.
  - `lessons.jsonl` has no producer.
  - `experiments.jsonl` has no producer.
  - `canaries.txt` is empty and has no producer.
  - `findings/` has no producer.
- Fix: a circulation table that code in `bin/life-circulate.py` runs every tick. It copies only
  new rows (byte offsets):

  | From | To | Condition |
  |---|---|---|
  | `life-command/routed.jsonl` | `life-learning/questions.txt` | `organ=="learning"` |
  | `life-command/routed.jsonl` | `life-codebase/findings/cmd-<id>.json` | `organ=="codebase"` |
  | `life-command/routed.jsonl` | `owner-requests.jsonl` | `organ=="none"` |
  | `life-learning/sources.jsonl` | `life-digest/sources.jsonl` | none |
  | `life-digest/facts.jsonl` | life.sqlite3 `knowledge` | none |
  | `life-immune/verdicts.jsonl` (`rejected`) | `life-selfdev/lessons.jsonl` (tainted) | none |

  The seed writes `canaries.txt` with exactly the six `bin/symblic check …/genome/<p>.sym` lines
  plus `bash -n` on each checks/*.sh.

## B. Undefined or ambiguous details

### 25. HIGH [U] — No ledger has a defined record schema
- Location: routed.jsonl, sources.jsonl, facts.jsonl, metabolism.jsonl, verdicts.jsonl,
  status.json, results/, lessons.jsonl, experiments.jsonl, proposals/.
- Fix (exact, one JSON object per line, UTF-8, no trailing commas; times are integer Unix seconds):
  - `routed.jsonl`: `{"id": str(sha256(file_bytes)[:16]), "file": str, "organ": enum(8),
    "urgency": "low|normal|high", "restated": str(10..160), "at": int}`
  - `sources.jsonl`: `{"key": items_key(url_or_doi), "url": str, "doi": str|null, "title": str(<=200),
    "question": str, "taint": "web", "at": int}`
  - `facts.jsonl`: `{"id": sha256(key+quote)[:16], "source_key": str, "claim": str(20..300),
    "quote": str(>=12), "verified": 1, "model": "qwen3:4b-instruct@node-d", "taint": "web", "at": int}`
  - `verdicts.jsonl`: `{"item": str, "kind": "canary|patch|quarantine", "verdict":
    "pass|fail|accept|reject|needs_work|quarantine", "reason": str(<=240), "at": int}`
  - `experiments.jsonl`: `{"id": str, "benchmark_id": str, "params": {}, "hypothesis": str(<=300),
    "threshold": {"op": "<|<=|>|>=", "value": number, "unit": str}, "score": int, "risk": str, "at": int}`
  - `results/<id>.json`: `{"id","benchmark_id","node","measured": number,"unit","passed": bool,"ran_at"}`
  - `lessons.jsonl`: `{"id","source":"immune|metrics|owner","text": str(<=300),"taint","at"}`
  - `status.json`: `{"at": int, "organs": {"<organ>": {"run_id","status","generation","items_total",
    "trailing_failures","last_finished"}}}`

### 26. HIGH [U] — The command inbox protocol is undefined
- Location: organs/command.lines.txt, README.
- Defect: the kit does not say how the operator submits a command (file name, format, encoding,
  size), what "new" means, how a file is marked processed, or how the `commands.id` arrival time
  is measured. Every generation would re-route every file.
- Fix:
  - One command per file `inbox/<YYYYmmddTHHMMSSZ>-<slug>.txt`, UTF-8, 1..4000 bytes. The arrival
    time is the timestamp in the name.
  - `id = sha256(file bytes)[:16]`.
  - A file is new when its id is not in `routed.jsonl`.
  - The worker never moves or deletes inbox files. Code archives a routed file to `inbox-done/`
    after ingest.
  - Classification is the code step `classify-command.sym` (finding 15b), so the command lane
    needs **no** agent at all.

### 27. MEDIUM [U] — `verify.txt` "exact format" is undefined
- Location: every organ verify clause ("the count of routed commands", "the three new source keys").
- Fix: line 1 `organ=<name> generation_utc=<ISO> new=<int> status=<ok|idle|fail>`, then zero or
  more lines `key=<items_key>`. Regex for line 1:
  `^organ=[a-z]+ generation_utc=\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ new=\d+ status=(ok|idle|fail)$`.

### 28. HIGH [U] — The metabolism decision rule is undefined and nothing consumes it
- Location: organs/metabolism.lines.txt ("compute the current continuous all-worker node load minutes …
  whether fan-out is allowed"), LIFE.md §6.
- Defect: no formula, no thresholds, no reader. The tick ignores `metabolism.jsonl`.
- Fix (`bin/life-metabolism.py`, code): `busy(node,t)` is true when
  `capacity[node].cpu_used_pct >= 50` in that 60-s sample (the sample is appended to
  `~/.local/state/life/load-samples.jsonl` each tick). `all_node_busy_minutes` = the trailing run of
  consecutive samples in which every online LIFE worker node is busy.
  `fanout = all_node_busy_minutes < 45 and not cool_mode and highpower.phase != "applying"`.
  Write `metabolism.json {at, fanout, all_node_busy_minutes, per_node: {...}}`. The heat gate
  reads it (finding 12).

### 29. MEDIUM [U] — Saturation "items" are undefined for non-research organs
- Location: policies codebase (sat 4), selfdev (4), compute (4), immune (6).
- Defect: `_index_items` counts a generation that lists no `items` as stale. "Items" means nothing
  for codebase, selfdev, compute or immune, so these lanes stop after N generations of normal work.
- Fix: `saturation: 0` for command, codebase, compute and immune. Learning uses `saturation: 6`
  with items = source URLs/DOIs, and digest uses `saturation: 6` with items = `fact:<id>`.

### 30. MEDIUM [U] — "Climb the ladder when a check fails" has no mechanism
- Location: LIFE.md §3 first paragraph and table.
- Defect: every genome `ask` pins one model and node, and `stronger_model` is refused by
  `normalize`. Nothing escalates, so the rung table is decoration.
- Fix: either remove the sentence, or define the ladder in code. For each program the step runs
  `--by <rung0>`. On a kernel `ensure` failure after `retries`, it reruns once with `--by <rung+1>`
  from `ladders.json` `{"reproduce": ["ollama:qwen3:4b-instruct@node-a", "ollama:gemma3:4b@node-f"], …}`,
  with a maximum of 2 rungs. After that the decision is `none`/`stay` and is logged.

### 31. HIGH [U] — Reproduction is nondeterministic, its inputs have no source and its failure path is undefined
- Location: genome/reproduce.sym.
- Defect:
  - (a) No rule says when a cell should divide (backlog, items rate). It is a 4B-model judgement
    with `effort=low`.
  - (b) No source is defined for `failures_in_a_row`, `new_items_last_generation` or `summary`.
  - (c) The `ensure … else retry` checks re-ask the model about facts code already knows. When the
    retries are exhausted, the program errors and the kit does not say what the tick does then.
  - (d) `child_a`/`child_b` are asked even for `stay`/`apoptosis`, which wastes calls.
  - (e) `child_a != child_b` is an exact-string test, so "Research X" and "research x" pass.
- Fix:
  - The verdict is decided by code first:
    - `failures_in_a_row >= 8` → `apoptosis`;
    - `failures_in_a_row > 0` → `stay`;
    - `lineage_depth >= 10` → `stay`;
    - `items_new == 0` for the last 6 generations → `apoptosis`;
    - `items_new >= 6` in each of the last 3 generations **and** live LIFE runs <
      `LIFE_MAX_RUNS - 1` → `divide`;
    - else `stay`.
  - The model is asked **only** for the two foci when the verdict is `divide`, with
    `ensure lower(child_a) != lower(child_b)`.
  - Inputs come from `autogen get <run_id> --json`: `items_new` of the last generations,
    `_trailing_failures`, and `summary` = the last `verify.txt` line 1.
  - If the program fails, the result is `stay` and a logged `repro_error`.

### 32. MEDIUM [U] — review-patch.sym loops on an impossible accept, and `diff_summary` has no producer
- Location: genome/review-patch.sym line 15.
- Defect: when `checks_passed=false` and the model says `accept`, `ensure … else retry` asks
  again and then fails the program. Nothing defines who writes `diff_summary` or its length.
- Fix: the code step calls the program only when the organ check passed. `diff_summary` is
  `git diff --stat` plus the first 3000 characters of `git diff -U1`, produced by code.
  A program error counts as `reject`.

### 33. LOW [U] — rank-experiment.sym spends model retries on rules code can apply
- Location: genome/rank-experiment.sym, the two `ensure` lines on score.
- Fix: keep the asks. Then
  `let final = (if feasible then (if risk = "high" then min(score, 40) else score) else 0)`
  (or the same clamp in the code step). Drop the two retrying ensures.

### 34. MEDIUM [U] — extract-source.sym has no source text, length or fetch rule
- Location: genome/extract-source.sym `given source_text`, digest lane.
- Defect: the kit does not say who fetches the page, with what network path, how much text is
  kept, or whether HTML is stripped. A 4B model's context (and the CLI agent's 8192 limit) is exceeded by
  most pages. It also does not say what happens when `quotes()` fails after 3 retries.
- Fix: the code step fetches through the existing SearXNG / local-research READ path on the host
  (global-IP check on every redirect), strips HTML and keeps the first 6000 characters. On a
  failure the row is written with `verified=0` to `facts-rejected.jsonl` and never enters
  `knowledge`.

### 35. MEDIUM [U] — The model and node pins conflict with the fleet runner's one-model-per-node rule
- Location: genome pins; LIFE.md §2 table and §6.
- Defect:
  - node-a serves `qwen3:4b-instruct` (reproduce, classify) **and** `qwen2.5-coder:3b` (triage),
    so the weights swap.
  - rank-experiment uses three models on node-i.
  - node-b serves `llama3.2:1b` for every organ.
  - No concurrency limit is defined, and `fleet_runner.py` line 627 says that two models at once
    swap weights.
- Fix: one model per node.

  | Node | Model |
  |---|---|
  | node-a | qwen3:4b-instruct |
  | node-b | llama3.2:1b |
  | node-f | qwen2.5-coder:3b |
  | node-i | granite3.3:2b |

  - Each `ask` uses only the model pinned to its node.
  - The code step runs genome programs **serially** (one at a time across LIFE), at most
    30 program runs per hour.

### 36. MEDIUM — The node lists contradict each other and leave nodes out
- Location: PROTOCOL lineage `node` allows `node-h`, while §2 says "LIFE avoids it for model work".
  `cluster_data/nodes.json` also lists `node-c` and `node-e`, which the kit never mentions.
- Fix: "LIFE nodes = {node-a, node-b, node-d, node-f, node-i}. node-c, node-e and node-h are
  excluded: node-h hosts the protected service stack (`TENANT_STACKS`) with a 3 GiB Ollama cap, and node-c and
  node-e are not in the BRIEF's cluster list. The seed verifies each LIFE node is `online` before
  starting and aborts otherwise."

### 37. HIGH [CODE] — "The lane waits rather than migrating" is false
- Location: LIFE.md §2 last paragraph.
- Defect: on `INFRASTRUCTURE`/`TIMEOUT`, `next_strategy` restricts rotation to
  `other_node`/`other_engine`. Without `other_node` it tries `other_engine` on the **same** offline
  node, then `fresh`. The bounded `decide` then fails after `regenerate` trailing failures, and
  until_done becomes `stuck`. Nothing waits for a node.
- Fix: state the real behaviour. Renewal (finding 2) only resumes a stuck run after the
  metabolism step reports the node `online` for 2 consecutive samples.

### 38. MEDIUM [U] — Quarantine is undefined and has nobody to carry it out
- Location: LIFE.md §7 ("a lineage whose cells fail `novelty_limit` generations in a row … run
  cancelled by the operator").
- Defect: `novelty_limit` is unset (default 2), and perpetual lanes do not use it. Nobody computes
  the condition, and the cancel is manual, so quarantine is advisory only.
- Fix: the tick quarantines a run with `trailing_failures >= 4` or `apoptosis`. It cancels it,
  adds its hash and cell to `retired.txt`, and appends a `verdicts.jsonl` row `kind=quarantine`.

### 39. MEDIUM — Claims in §1 and §4 have no code behind them
- Location: LIFE.md §1 ("a failing cell … cannot pass the orchestrator budget"), §4 ("the
  operator/immune organ cancels the run", "A retired cell's content hash stays known").
- Defect: the tick has no failure gate. The immune agent cannot cancel runs (no API from a worker node).
  Retirement is only a file the tick never reads.
- Fix: the tick reads `retired.txt` and refuses those hashes and cell ids. The failure gate is
  finding 31's rule.

### 40. MEDIUM — §3 contradicts GAP 4 on `delegate`
- Location: LIFE.md §3 lists `delegate` templates as a lightweight lane. §11 GAP 4 says "no
  `delegate` inside LIFE v1".
- Fix: delete the `delegate` bullet from §3, or mark it "not used in v1".

### 41. LOW — A citation names the wrong file
- Location: LIFE.md §2 ("`symblicos/autogen.py` `next_strategy`").
- Defect: `next_strategy` is in `symblic_autogen.py`. `_current` is correctly in
  `symblicos/autogen.py`.

### 42. MEDIUM — Seed: duplicated flags, no preconditions, writes into the live repo
- Location: `bin/life-seed.sh`.
- Defect:
  - The flags are hand-copied from `policies/*.json` ("keep the two in sync"), so they will drift.
  - The seed starts 10 runs at once with no STOP, heat, budget or node-readiness check. agy
    readiness on each worker node is unverified: BRIEF says CLI logins exist on the host, and
    `_check_remote` refuses an engine whose node is not `ready`.
  - `mkdir "$KIT/spawn/…"` writes into host-checkout.
- Fix:
  - Generate the flags with `policy_flags(json.load(policy))` (one source).
  - Before any start, require FREEZE/STOP absent, heat ALLOW, and every target node `online`.
  - Stagger the starts by 120 s.
  - Write state only under `~/.local/state/life/`.

### 43. MEDIUM — The tick has no lock, timeouts, birth cap, atomic intake or exit-status mapping
- Location: `bin/life-spawn-tick.py`, LIFE.md §9 unit text.
- Defect:
  - Two concurrent ticks (timer plus manual) can double-birth.
  - `subprocess.run(start)` and the heat gate have no timeout.
  - One tick can birth up to the whole budget at once.
  - A record still being written is read as incomplete and rejected.
  - Exit 3/4 marks the systemd unit failed on every hold.
  - `OnBootSec` resumes births automatically after a reboot.
- Fix:
  - `fcntl.flock(~/.local/state/life/tick.lock, LOCK_EX|LOCK_NB)` (exit 0 if held).
  - `timeout=120` on every subprocess.
  - `LIFE_MAX_BIRTHS_PER_TICK=1`.
  - Intake only folders containing `READY` (written last).
  - The unit gets `SuccessExitStatus=3 4` and `TimeoutStartSec=600`, and the tick runs only when
    `ARMED` exists (finding 2).

### 44. MEDIUM [U] — Storage grows without bound and silent truncation is possible
- Location: whole design.
- Defect:
  - Every attempt creates a worktree and branch `agents/<name>-<stamp>` beside the workspace and
    under `~/agents-work` on worker nodes.
  - `carry_over` silently skips untracked files over `CARRY_MAX_BYTES` (25 MiB), so a large
    `sources.jsonl` simply disappears from workers' view.
  - Rejected folders, hashes and run records accumulate.
- Fix:
  - Rotate each JSONL at 5 MiB into `archive/<name>-<YYYYmmdd>.jsonl.gz` (code step).
  - Prune rejected folders older than 14 days.
  - The status step reports workspace size and refuses births above 2 GiB per workspace.
  - Worktree cleanup uses the hub's existing removal path only.

### 45. LOW — devcheck-gate.sh conflicts with the test rules
- Location: `checks/devcheck-gate.sh` line 13.
- Defect: CLAUDE.md says tests use the system or isolated test Python, not the service `.venv`.
  The `||` reruns a failing test with a second interpreter, which hides the first result. It also
  ignores the "at most three test workers" rule and the scratch-copy trap (`-m unittest` from a
  copy imports the live module).
- Fix: `cd "$checkout" && ./bin/devcheck && python3 -m unittest "$focused" -v`. Exit 0 only when
  both pass, and print `PWD` and `__file__` of the test module.

### 46. MEDIUM [U] — The high-power mode request row is undefined
- Location: LIFE.md §6, GAP 6 ("the compute organ may request it by writing a row the operator approves").
- Fix: `owner-requests.jsonl` row `{"id","kind":"highpower","minutes": 5..60,"reason": str(<=240),
  "batch": str,"at"}`. The operator acts on /cluster. LIFE never calls `/api/cluster/highpower/mode`.
  Also state the code fact: the rest after a lease is `REST_MIN..REST_MAX` = 300..3600 s
  (`cluster_highpower.py`). It is not "as long as the last ran" without a cap.

### 47. MEDIUM [U] — Seed cell ids and the meaning of `generation` are undefined
- Location: lineage.json spec, schema `lineage`, example `parent_id: "learning.2.00000000"`.
- Fix: seed cell = `"<organ>.0.00000000"`, `parent_id=null`, `depth=0`, `spawn_reason="seed"`.
  `generation` in a child id = the parent's `node.generation` at the moment of the divide, read
  from `autogen get`.

### 48. MEDIUM [U] — Budget semantics are undefined
- Location: `LIFE_MAX_RUNS=16`, BRIEF "the master coordinator may spawn as many agents as needed".
- Defect: the kit does not say whether the 16 includes the 10 seeds (which leaves 6 children)
  or what the per-organ cap is. The BRIEF's "as many as needed" is not reconciled.
- Fix: "LIFE_MAX_RUNS counts every ledger run in {queued, active}, seeds included. Per organ: at
  most 3 live runs. The cap is a heat and quota budget (findings 13 and 16), not a limit on ideas.
  A queued record waits; it is not rejected."

### 49. LOW — VALIDATE.sh is weaker than the tick and leaves artefacts
- Location: VALIDATE.sh lines 63, 77.
- Defect:
  - The lineage check uses `count('.')==2` instead of the tick regex.
  - It has no seed↔policy parity check.
  - `py_compile` leaves `bin/__pycache__/` in the kit (present now).
  - Lint passes a `root`, which suppresses the folder warning, so "zero warnings" is weaker than
    it reads.
- Fix: use `re.fullmatch(r'[a-z]+\.[0-9]+\.[0-9a-f]{8}', cell_id)`; run
  `python3 -B -c "import ast,sys; ast.parse(open(f).read())"` instead of py_compile; add a parity
  check comparing `policy_flags(policy)` with the seed's flags.

### 50. MEDIUM [U] — The knowledge table's key and concurrency are ambiguous
- Location: db/schema.sql `knowledge.id` ("items_key form"), `created_at` ("strftime('%s')").
- Defect: an items_key of the source as the PRIMARY KEY allows only one fact per source ever,
  which contradicts "one checked fact per row". `strftime('%s')` returns TEXT. There is no
  single-writer rule.
- Fix: `id = sha256(source_key + "\n" + quote)[:16]`, with `source_key TEXT NOT NULL` indexed.
  Write times with Python `int(time.time())`. The single writer is `bin/life-db.py` (finding 22).

### 51. LOW [U] — "Every 120 s" does not match the scheduling semantics
- Location: LIFE.md §2 Interval column.
- Fix: "interval = seconds from the previous attempt's finish to the next generation's start
  (`decide`: `due = finished + interval_seconds`); the actual period is interval + attempt time."

### 52. MEDIUM [U] — The learning lane's batch definition is ambiguous
- Location: organs/learning.lines.txt ("find three sources").
- Defect: the line does not say whether "three" is exact or a maximum, how many fetches or bytes
  a batch may use, which question is processed when there are many, or how a question is marked
  answered.
- Fix: "Process the first question in `questions.txt` whose sha8 is not in `answered.txt`; collect
  up to 3 new sources (0 is an idle pass); at most 10 page reads and 2 MB per generation; append
  the question's sha8 to `answered.txt` after 3 consecutive generations with 0 new sources for it."

### 53. MEDIUM — The organ roster misses parts of the BRIEF
- Location: §2 table versus the BRIEF.
- Defect:
  - "develops itself based on things it learns" has no closed loop (lessons are never produced and
    proposals are never adopted).
  - "learns efficiently" has no efficiency metric (items per attempt, per cloud minute).
  - "two agents per subtask" is missing (finding 7).
  - "creates databases" is a one-shot (finding 22).
  - No organ watches the organism's own failure rate across generations (metrics → lessons).
- Fix: add a **code** organ "learning-efficiency":
  `efficiency = items_new / attempts_started` per organ over 24 h, written to `metrics`. An organ
  whose efficiency < 0.2 for 2 days is put to rest automatically (no renewal) and listed in
  `owner-requests.jsonl`. Lessons = immune rejections + efficiency drops, tainted by origin.

---

## Summary
The kit is honest about its gaps and its genome programs pass `bin/symblic check`. However, the
code contradicts many of its central claims:
- The organs are not perpetual (generation cap 3; finding 1).
- The `life-*` ids are invisible, so the budget gate, kill switch and status are dead (finding 3).
- The organs collide on one root folder (finding 4).
- Acceptance is vacuous (finding 5).
- Reproduction is unreachable (finding 7).
- Light models cannot be reached from worker node workers (finding 15).
- sqlite3 is absent where the final check runs (finding 22).

The largest safety gaps:
- Unvalidated node, engine and policy in child records (finding 10).
- An the host-only heat gate (finding 12).
- Agent lanes on the host (finding 14).
- A kill switch that does not stop lanes and that workers can delete (finding 19).
- Model-proposed shell benchmarks (finding 21).
- Untrusted web text flowing into self-modification (finding 20).
- A rollback that discards others' work (finding 18).

The recommended restructure keeps agents for file-producing work on worker nodes and moves every typed
decision, admission, circulation, metabolism, heartbeat and database write into model-free code on
The host. That code calls light models only through `bin/symblic run … --by ollama:…@node-X`.

FINDINGS_TOTAL=54
UNDEFINED_DETAILS=27
VERDICT=CHANGES NEEDED
