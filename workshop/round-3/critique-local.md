# LIFE v2.1 — round 3 local adversarial critique

Reviewer: local critic (Claude, highest effort), 2026-10-11. Read: BRIEF.md, LIFE.md sections 1-18, every file in
bin/, checks/, db/, genome/, organs/, policies/, spawn/, units/, benchmarks/, README.md, VALIDATE.sh and
workshop/round-2/decisions.md. Platform claims were checked with rg/sed in the live checkout. Static checks only:
`life_common.contract_problems()` ("contract holds") and two in-memory SQLite experiments (no model, no agent, no
cluster job, no tick, no seed). Every file:function named below was found with rg.

Severity: high = the kit cannot do what it says, a claim the platform code contradicts, or unsafe/unbounded
behaviour; medium = a wrong or undefined rule a light model or fresh agent would act on two ways, or a missing
path the brief needs; low = wording, dead config or small inefficiency. "[U]" marks an undefined or ambiguous
detail (counted in UNDEFINED_DETAILS).

---------------------------------------------------------------------------------------------------------------
## HIGH
---------------------------------------------------------------------------------------------------------------

1. **high — agent organs can never reproduce** (bin/life-tick.py `Tick.division_commit` line 1754; spawn/PROTOCOL.md
   section 2 stage 3; LIFE.md section 9).
   `division_commit` returns early unless `self.can_start(2 * 3 * L.CLONE_TIMEOUT)`, i.e. `elapsed + 3600 + 30 + 60
   <= TICK_HARD (2700)`, which is false at every elapsed time. PROTOCOL.md says the same ("a tick with less than
   3600 s of hard budget left waits"), and TICK_HARD is 2700, so no tick ever has 3600 s. Effect: every codebase,
   selfdev and database division runs `reproduce` + up to 16 `assign-item` model calls, holds the parent in
   `dividing` for 10800 s, aborts, waits 21600 s, and repeats forever; because DIVISIONS_OPEN_MAX = 1 (unique index
   `divisions_one_open`), each such doomed division also blocks every model organ's division for 3 h.
   Fix (adopt): add a division stage `workspaces` between `assign` and `committed`:
   "**workspaces** (agent organs only) — at most ONE child workspace is created per armed tick, in step 12, admitted
   by `can_start(3 * CLONE_TIMEOUT)`; the stage records `ws_a_done`/`ws_b_done`; commit runs only when both
   workspaces exist; a failed clone aborts the division and removes any child workspace it created (see 11)."
   Add to VALIDATE check 11: `assert 3 * L.CLONE_TIMEOUT + L.KILL_GRACE + 60 <= L.TICK_HARD` and a rule that no
   `can_start(X)` literal in life-tick.py exceeds `TICK_HARD - KILL_GRACE - 60`.

2. **high — the database organ dies at its first index** (bin/life-tick.py `Tick.write_snapshot` line 1406;
   bin/life-ctl.py `seed_workspace` line 190; LIFE.md section 7.8 "ordered by type, then name").
   `ORDER BY type, name` sorts `index` before `table`, so schema-snapshot.sql lists `CREATE INDEX org_x_i ON
   org_x (...)` before `CREATE TABLE org_x`. Check 0 (`life-check.py migration`) runs `migration_problems(sql,
   snapshot)`, which executes the snapshot in order: verified in memory, an ALTER on an existing indexed table
   returns `['sqlite refused: no such table: main.org_papers']`. Once any migration creates an index, every later
   database run fails check 0 at every attempt, the cell's failure streak grows and it is quarantined.
   Fix: in both places use `SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'
   ORDER BY rowid` (creation order: a table always precedes its indexes) and change LIFE.md 7.8 to "in creation
   order (sqlite_master rowid)". Add a VALIDATE rule case: snapshot of {table, index on it} + an ADD COLUMN passes.

3. **high — one AUTOINCREMENT bricks the organism forever** (bin/life_common.py `MIGRATION_RX`,
   `migration_problems`, `snapshot_problems`; LIFE.md 7.8).
   `CREATE TABLE IF NOT EXISTS org_a (id INTEGER PRIMARY KEY AUTOINCREMENT, x TEXT)` passes `migration_problems`
   (verified: `[]`), is applied, and SQLite then adds `CREATE TABLE sqlite_sequence(name,seq)` to sqlite_master.
   Every later snapshot contains it and executing it fails (`object name reserved for internal use:
   sqlite_sequence`, verified), so check 0 and the apply stage refuse every future migration.
   Fix: add `AUTOINCREMENT` to the denied words (`FUNCTION_DENY_RX`/a new `WORD_DENY_RX = r'(?i)\bAUTOINCREMENT\b'`
   checked on every statement) AND exclude `name LIKE 'sqlite_%'` from every snapshot query (finding 2). LIFE.md 7.8
   add: "AUTOINCREMENT is refused (it creates the internal sqlite_sequence table)". VALIDATE: one negative case.

4. **high — "cancel confirmed" is not "run ended"; the kit's STOP text is contradicted by the platform**
   (bin/life_common.py `stop_everything` lines 1325-1347; bin/life-tick.py `poll_runs` policy-mismatch branch;
   LIFE.md section 5 step 4; README KILL SWITCH).
   `symblicos/autogen.py:AutogenManager.control('cancel')` only sets `cancel_requested` and returns success; it also
   returns success for a run that is already `completed`/`failed`/`cancelled` (the `if` is skipped, no error).
   `host_routes.Jobs.cancel` signals a running job; a job in `unknown` cannot be cancelled at all (404). LIFE treats
   rc 0 as "cancelled", sets the run row `cancelled`, re-queues the item with attempt+1 and stops polling. Results:
   (a) the old run keeps running and may still promote (hub commit -> apply) into the cell's workspace after
   `unstop`, while LIFE starts a new run in the same workspace -> a foreign diff reaches the next gate;
   (b) a run that had already `completed` (changes promoted) is thrown away by the next `refresh_clone`/reset and
   redone; (c) `busy_seconds` stops counting the node although it is still loaded.
   Fix (replace LIFE.md 5 step 4): "A run whose cancel request was accepted keeps state `live` with detail
   `cancel_requested`; its item stays `running`; the next polls collect it exactly like any other run (a
   `completed` run still goes to its gate; `cancelled`/`failed` follow the collection rules). A benchmark job
   whose cancel was accepted stays `running` until the jobs listing shows `cancelled`/`failed`/`done`; a job in
   `unknown` keeps its node held (see 36)." Same change for the policy-mismatch and 4500 s branches.

5. **high — candidate code escapes STOP and every timeout** (bin/life-check.py `sandboxed` line 64;
   checks/devcheck-gate.sh steps 2-3; LIFE.md sections 1, 5; README "STOP ... ends every LIFE process").
   `life-check.py sandboxed` runs the sandbox with `start_new_session=True` and on its own timeout calls only
   `kill()` on the direct child. When the tick ends the gate (GATE_TIMEOUT 900 s, STOP watcher, unit SIGTERM) it
   kills bash's process group: `life-check.py` dies without killing its child, and the sandboxed devcheck or unit
   test (a NEW session, outside that group) keeps running with no time limit inside the gate's scope. Grandchildren
   of the test (devtest workers, subprocesses) escape even on the normal 110/240/600 s path, and in autogen's check 0
   (`symblicos/autogen.py:_run` kills only life-check's group) they are left in the dashboard server's cgroup, which
   has no 4G MemoryMax. Agent-written code can therefore run unbounded on the host.
   Fix: in `sandboxed`, start the child with `subprocess.Popen(..., start_new_session=True)`, keep its pid, install
   `signal.signal(SIGTERM and SIGINT, handler)` where the handler runs `os.killpg(child.pid, SIGKILL)` then
   `os._exit(143)`, and on timeout run `os.killpg(child.pid, SIGKILL)` before returning 1; also prefix the
   sandboxed command with `timeout --kill-after=10 <N>` and `prlimit --as=4294967296` so a process that outlives
   its parent still ends and stays memory-bounded outside a scope.
   LIFE.md section 1 add: "life-check.py kills the sandbox's whole process group on timeout, SIGTERM and SIGINT."

6. **high — the worker node checkout contains `.backups/` as plain files; GAP 11 understates it** (LIFE.md section 18
   GAP 11; README step 4; bin/life-seed.sh header; LIFE.md 7.4/11 "LIFE's clones keep .backups/ out").
   `agent_hub.provision_remote` pushes the workspace branch to a bare mirror on the node and runs `git worktree
   add` there with no sparse patterns, so every codebase agent checkout on a worker node holds the 28 tracked `.backups/`
   files in HEAD (including [a private database]) in its working folder, not only "in the
   history". The operator's CODEBASE_HISTORY_OK decision is asked on the weaker description. The mirror is named by
   the workspace basename, so every codebase cell costs a full ~750 MiB push per worker node plus a ~750 MiB worktree per
   run, none of it counted by STATE_MAX_BYTES or removed when the cell retires.
   Fix (replace GAP 11's middle sentence): "an agent checkout on a worker node is a full `git worktree` of the branch: the
   tracked `.backups/` files, including a private database, are present as plain files in the agent's
   working folder, and the full history is in the worker node's bare mirror `~/agents-repos/life-codebase-<d>-<hex>.git`."
   Add notice text for `tracked_private_data` saying the same, and a GAP 14: "worker node-side mirrors and worktrees are
   not counted or removed by LIFE (operator cleanup: `git -C ~/agents-repos/<name>.git worktree prune` on each worker node)."

7. **high — no host memory gate before 4 GiB local work** (bin/life-tick.py `Tick.host_reasons`;
   life_common `scope_argv(memory='4G')`; LIFE.md section 10 Hold list).
   The host has 16 GB and 6 CPUs; LIFE starts scopes with MemoryMax 4G (watched test, confirm, gate with devcheck and
   its tests, two 750 MiB clones) after checking only load1 and io PSI. The operator's recorded history is three
   systemd-oomd kills on the host (including all terminals), with "RAM rule + PSI < 10" as the agreed wake gate.
   Fix: add to the Hold list and to every host-stage admission: "the host `MemAvailable` (from /proc/meminfo)
   >= HOST_MEM_FLOOR_MIB 6144 (4096 for the scope + 2048 reserve) and `/proc/pressure/memory` `some avg60` <
   HOST_MEM_SOME_AVG60 10.0; unreadable = hold". New constants in life_common.py, table rows in section 13,
   VALIDATE check 11 reads /proc/pressure/memory like io.

---------------------------------------------------------------------------------------------------------------
## MEDIUM
---------------------------------------------------------------------------------------------------------------

8. **medium — queued gate/apply items move to children at division commit** (bin/life-tick.py
   `division_commit`: `queued = ... cell_id=? AND state='queued'`; PROTOCOL.md section 2 stage 3).
   PROTOCOL only protects items the parent is *running*. A run collected in step 5 leaves its item `queued` at
   `gate`/`apply` on the parent; if the one-per-tick gate did not reach it (deadline, another gate first), the slot
   phase can commit the division and move it to a child whose workspace is a fresh clone: `staged_diff` sees no
   change -> `failed` ("the run left no diff"), and `remove_retired_workspace` then deletes the parent clone that
   held the promoted work. Masked today by finding 1, exposed once 1 is fixed.
   Fix: eligibility rule 13 "the cell has no live run and no item queued or running at gate, apply or confirm",
   re-checked at commit; and commit moves only items whose stage is not gate/apply.

9. **medium — command reports starve after 20 pending commands** (bin/life-tick.py `Tick.reports`, LIMIT
   REPORT_COMMANDS_PER_TICK ordered by `updated_at`). A dispatched command whose descendants wait (an
   approve_needed lesson, an operator-state item is fine, but a never-approved request is `queued` forever) is skipped
   without changing `updated_at`, so the same 20 oldest rows are read every tick and no newer command ever gets a
   report. Fix: add `commands.report_checked_at` (or reuse updated_at) set on every skip, ORDER BY it; and define
   "ended" for reports as state not in (queued, running) OR (taint web/model AND waiting for approval > 7 days).

10. **medium [U] — agenda floods while disarmed** (bin/life-tick.py `Tick.agenda`, run() step 6; LIFE.md section 6
    "Each entry becomes one command per period"). Agenda runs even when disarmed/frozen/held and operator items are
    never dropped, so 20 entries at 6 h make 80 commands a day that pile up for the first armed tick. Catch-up is
    undefined. Fix: "Agenda entries are read only when ARMED, not FROZEN and no hold; each entry yields at most the
    CURRENT period's command; missed periods are skipped (notice `agenda_skipped` with the count)."

11. **medium — operator commands lose to long ticks** (bin/life-ctl.py `LOCK_WAIT = 600` line 49). A tick holds the
    lock up to TICK_HARD 2700 s (any research slot is ~1500 s), so `approve`, `apply`, `adopt`, `ack`, `retire`,
    `canaries`, `clear-fault` fail with "a tick holds the lock" during most of an active hour. Fix: `LOCK_WAIT =
    L.TICK_HARD + L.KILL_GRACE + 60` (2790 s) with a progress line every 60 s, or document that operator writes go
    through an operator-ops inbox file the tick applies first.

12. **medium — the slot phase is a barrier, so throughput follows the slowest worker node** (bin/life-tick.py
    `serve_nodes` line 2047). Every node waits for the longest thread (a 1500 s research run) before the tick can end
    and the next 300 s timer starts: a 60 s classification node then idles ~30 min. "Learns efficiently" is not
    met. Fix: "a node whose run ended may plan its next action in the same slot phase while `can_start(t)` holds;
    research runs only on a node with no other planned work".

13. **medium [U] — HTTP status is ignored on fetch** (bin/life-fetch.py; `local_research.read_page` ->
    `deep_research.safe_fetch` returns any status). A 403/404/429/503 error page of >= 200 characters is stored as
    the immutable source snapshot and becomes "quote-verified knowledge". Fix: life-fetch calls
    `deep_research.safe_fetch` itself (then `local_research.page_text`/`pdf_text`) and classifies: 2xx -> text;
    404/410/451/401/403 -> refused (abstained `HTTP <code>`); 408/425/429/5xx -> error (infra); other -> refused.
    Add the rows to the 7.3 outcome table.

14. **medium [U] — environment errors become findings** (bin/life-tick.py `watch_outcome`). A sandbox or
    interpreter problem (`ModuleNotFoundError` under /usr/bin/python3, `PermissionError` from Landlock, a refused TCP
    connect) prints `FAILED (errors=1)` and is classified `fail` -> triage -> an agent run "fixing" the environment.
    Fix: "error when the tail matches `ModuleNotFoundError|ImportError|PermissionError|Errno 1[13]|Errno 111|
    ConnectionRefused|Landlock`", and README step 4: "each watch.txt test must pass `life-ctl gate-selftest TEST`".

15. **medium — gate-selftest is vacuous for devcheck** (bin/life-ctl.py `gate_selftest`). It runs the gate with
    BASE = HEAD and no patch, so `./bin/devcheck --changed BASE` sees no change and runs no compile, rule, ruff or
    test step inside the sandbox; the README treats PASS as proof the gate machinery works. Fix: the self-test
    writes one comment line to the resolved test module (`# life gate selftest`), runs steps 2-3 against HEAD, then
    resets the clone; PASS requires devcheck to report the file as checked.

16. **medium — test_only patches can rewrite the judge** (life_common `patch_problems`; LIFE.md 7.4/7.5).
    Assertion counting lets `assertEqual(x, 3)` become `assertEqual(x, 4)`, and any file under tests/ may change,
    so a 3B "the test is wrong" label plus a 3B accept turns a real regression into a green test with `patch_ready`.
    comment_or_doc may edit docs/agents/*.md, which other agents read as instructions. Fix: test_only may change
    only the resolved module file of TEST_ID; a test_only patch is never `ready` from a model accept (state `owner`,
    apply needs `--unreviewed`); add `docs/agents/`, `(^|/)AGENTS\.md$`, `(^|/)CLAUDE\.md$`, `docs/fleet-power\.md$`
    to GATE_DENY_RX.

17. **medium — selfdev CAN weaken an acceptance rule** (LIFE.md 7.6 "Acceptance rules ... are not in the genome,
    so selfdev cannot weaken them"; genome/distill-lesson.sym `program` enum; life-tick `on_classify_command`
    selfdev route). review-patch.sym is a genome program; its ask instruction may be rewritten by a proposal, and
    a patch becomes `ready` (apply without --unreviewed) only through its verdict. Fix: `SELFDEV_PROTECTED =
    ('review-patch',)`: no lesson, command or code lesson may target it, the gate refuses it, and LIFE.md 7.6 says so.

18. **medium [U] — which branch the codebase organ tracks is undefined** (bin/life-ctl.py `seed` line 230).
    `git rev-parse --abbrev-ref HEAD` records whatever is checked out at seed (today `[branch name removed]`, a feature
    branch; a detached HEAD gives `HEAD` and the clone fails). Watched tests then run on a stale branch while
    `apply` patches whatever branch the live tree is on. Fix: `seed --confirm START --branch NAME` (default `main`),
    stored as meta.codebase_branch; `apply` refuses (unless `--moved-base`) when the live checkout's branch differs,
    printing both names.

19. **medium [U] — selfdev and database runs start without a clean workspace** (bin/life-tick.py `start_run`,
    `sync_selfdev`, `write_snapshot`). Only codebase resets (refresh_clone). A stray file from a policy-mismatch,
    cancelled or late-promoting run survives into the next selfdev/database run, whose gate then refuses "must change
    exactly ...", growing the failure streak. Fix: "every agent start first runs `git reset -q --hard HEAD && git
    clean -fdq` in the workspace (reset_workspace), then the organ's sync".

20. **medium — a timed-out start can leave an untracked twin run** (bin/life-tick.py line 1364 `check_submitted`).
    When `bin/symblic-task start` times out (rc None at 180 s) the immediate 404 marks `not_submitted` and
    re-queues with attempt+1; if the original request is still being handled, its run appears later under the old
    request id, never polled, never cancelled by STOP (not in submitting/live/submit_unknown), absent from the load
    ledger, and promoting into the same workspace. (Round-2 G46 was about a settled 404; this is an in-flight one.)
    Fix: "rc None or no HTTP answer -> `submit_unknown`; only an HTTP 4xx refusal printed by the CLI followed by a
    404 is `not_submitted`; a `submit_unknown` row becomes `not_submitted` only after two 404 polls at least
    RUN_UNKNOWN_NOTICE seconds apart".

21. **medium [U] — research time bound is not derived** (life_common RESEARCH_TIMEOUT 1500, RESEARCH_TOOLS 4,
    RESEARCH_STEP_TIMEOUT 300; LIFE.md 7.2 "each generation at most 300 s"). `local_research.research` makes up to
    RESEARCH_TOOLS + 1 = 5 generations and `generate` polls each up to STEP_TIMEOUT + 120 = 420 s, plus 4 tool uses
    (SearXNG, `read_page` up to 5 hops x 35 s + robots). Worst case > 2400 s, so slow worker nodes end as "research timed
    out" = infra with a 1800 s node hold, and the question goes to the operator after 6. Fix: define the bound
    `RESEARCH_TIMEOUT >= (RESEARCH_TOOLS + 1) * (RESEARCH_STEP_TIMEOUT + 120) + RESEARCH_TOOLS * 180` and assert it
    in VALIDATE; with RESEARCH_TOOLS 3 and RESEARCH_STEP_TIMEOUT 240 it gives 4 x 360 + 540 = 1980, so
    RESEARCH_TIMEOUT 2000 (admitted by can_start only while elapsed <= 610 s, i.e. early in a tick).

22. **medium [U] — a job in `unknown` frees its node** (bin/life-tick.py `poll_benches` line 491). `unknown`
    (host_routes `_unknown`: "execution unknown; reservation held") is treated as running until timeout+300, then
    LIFE "cancels" (404) and fails the item; the node leaves the benchmarking set and gets new LIFE work while the
    remote command may still run. Fix: "status unknown -> the item goes to `owner` with notice `job_unknown`, and a
    `node_holds` row for that node with until = far future, cleared only when the jobs listing shows the job
    terminal or the operator releases the reservation".

23. **medium [U] — high-power mode phase is ignored** (bin/life-tick.py `metabolism`; LIFE.md 10). LIFE checks `enabled`
    and `restUntil` but not `phase`; `cluster_highpower` sets `enabled False, phase 'restoring'` at lease end, and
    `restore_pending` can outlast `restUntil`, i.e. worker nodes may still be at maximum performance. Fix: Hold when the
    high-power mode state's `phase` is not exactly `off` (the same rule as cool).

24. **medium — "no network" in the sandbox is false for UDP** (bin/life-check.py docstring "no network";
    checks/devcheck-gate.sh header; LIFE.md section 1 is accurate). `landlock_sandbox.py` docstring: "UDP (DNS) and
    Unix sockets are not network rules"; the seccomp filter permits SOCK_DGRAM. Agent-written code in the gate can
    send the clone (its .git holds the `.backups/` history) anywhere over UDP. Fix the two texts to "no TCP except
    port 1, no unix sockets; UDP is NOT blocked", and add GAP 15 (platform: a `--no-udp` seccomp rule).

25. **medium — a 1B label decides between research and a schema change** (bin/life-tick.py `on_classify_command`
    route database; genome/classify-command.sym). Operator text routed to `database` creates an operator-taint request
    (no approval) whose migration is applied automatically. A misroute of "research how databases index DOIs"
    spends an agent run and changes organism.sqlite3. Fix: "the database route creates a request only when the
    command text starts with `database:` (code check, case-insensitive); otherwise notice `command_database_confirm`
    asks the operator to resend with the prefix".

26. **medium [U] — reproducers never escalate or tune** (bin/life-tick.py `record_division`, `plan_division`).
    Division calls never set `rung_extra` or call `tune`, so `reproduce` and `assign-item` always use rung 0 (the
    second rungs in organs.json are dead except after auto_release); a 1B model that cannot name foci aborts every
    6 h forever. Fix: "a failed foci answer retries once at the next rung in the next slot before aborting; both
    division programs update the parent's `cell_programs` window like any program".

27. **medium [U] — benchmark pairs are order-biased** (bin/life-tick.py `start_bench` line 2435; LIFE.md 7.7
    "alternating, baseline first"). Baseline always runs before candidate, so cache warm-up and thermal drift
    favour the candidate; no warm-up run is discarded. Fix: `items = [B, C, C, B, B, C]` (ABBA), pair k = the
    baseline and candidate of block k, plus one discarded warm-up run of the baseline (7 runs, timeout 7T+60).

28. **medium [U] — two autogen fields are not fixed** (life_common `AGENT_POLICY_FIXED`, `DEFAULT_FIELDS`,
    CONTRACT; bin/symblic-task has no `--feedback-chars` flag). `interval_seconds` and `feedback_chars` come from
    the server's `symblic_autogen.DEFAULTS` (900, 2000) unpinned; a changed default makes every LIFE run a
    `policy_mismatch` (cancelled, operator) instead of a contract hold. Fix: add both to AGENT_POLICY_FIXED and
    DEFAULT_FIELDS (server compare) and a CONTRACT row for `'interval_seconds': 900,\s*'feedback_chars': 2000`.

29. **medium [U] — section 13 leaves ~25 numbers without a meaning** (LIFE.md section 13; life_common limits
    block): TAIL_LINES, LOCAL_FIX_FILES_MAX, GIT_TIMEOUT, GIT_FETCH_TIMEOUT, CLONE_TIMEOUT, SOURCE_KEY_MAX,
    FETCHES_PER_TICK, FETCH_TIMEOUT, JOB_CANCEL_TIMEOUT, JOBS_PAGE, BENCH_FSIZE_BYTES, BENCH_NOFILE, MIGRATION_*,
    SNAPSHOT_MAX_BYTES, DISK_FREE_MIN, SAMPLES_KEEP_DAYS, REPORT_COMMANDS_PER_TICK, HTTP_MAX_BYTES, HOUR/DAY,
    PAYLOAD_MAX, COMMAND_MAX_BYTES, INBOX_PER_TICK show only their group name. Fix: one trailing comment per
    constant (unit + what it bounds + who enforces it); the generator copies it.

30. **medium — platform code LIFE executes is pinned only by regex fragments** (life_common CONTRACT; LIFE.md 17).
    The live checkout "often has others' edits"; a change to landlock_sandbox.py, deep_research.safe_fetch or
    bin/symblic-task that keeps the pinned line changes LIFE's sandbox or fetch behaviour with no hold. Fix:
    `PLATFORM_PINS = ('landlock_sandbox.py', 'deep_research.py', 'local_research.py', 'bin/symblic-task',
    'symblic_autogen.py')`: their sha256 is recorded in ARMED at arm; a difference is an integrity hold
    ("platform changed since arm: read it, run VALIDATE.sh, arm again").

31. **medium — no path back for a dead organ or an operator-state item** (bin/life-ctl.py). `retire --force` can
    remove an organ's last cell and nothing re-creates one (LIFE.md 2 says "never below one cell per organ");
    items ending `owner` (infra_repeat, policy_mismatch, render) can only be re-sent as a new command. Fix: add
    `life-ctl.py revive ORGAN NODE` (a depth-0 cell `<organ>.0.<8 hex of sha256(organ, now)>` with the seed focus;
    CHECK `(parent_id IS NULL) = (depth = 0)` already allows it) and `life-ctl.py requeue ITEM --confirm REQUEUE`
    (state queued, infra_runs 0, faults 0, same stage).

---------------------------------------------------------------------------------------------------------------
## LOW
---------------------------------------------------------------------------------------------------------------

32. **low [U]** bin/life-tick.py module docstring numbers 14 steps and says status is written "after step 1";
    LIFE.md section 4 (declared authoritative) numbers 15 and says "after step 2"; hold notices run after the
    STOP/arm check, not in step 7. Fix: copy section 4's numbering into the docstring.
33. **low [U]** LIFE.md 6 "Beyond 200 queued items" vs code `>= QUEUE_CAP_PER_ORGAN`: write "at 200 or more".
34. **low [U]** PAYLOAD_MAX is unused; an oversize payload hits the SQL CHECK as an IntegrityError tick fault
    (failed after 3). Fix: `new_item`/`item_update` refuse `len(json) > PAYLOAD_MAX` with outcome `PAYLOAD_TOO_LARGE`.
35. **low [U]** "proposal_id" means two things: verify.txt and the selfdev template use the lesson item's 16 hex,
    the bundle uses sha16(lesson id, sha256(new)). Rename the verify field `lesson=<16hex>`.
36. **low [U]** auto_release "released once" (LIFE.md 9, PROTOCOL 4) but the code releases again after every 7-day
    window. Write "at most once per REQUARANTINE_WINDOW".
37. **low** `inbox_refused` notice subject is the file name, whose slug is made from the text (LIFE.md 6 "never
    quotes the text"). Use subject `sha16(name)`.
38. **low** PARAM_RX allows a leading `-`, so a model parameter can be an option to the operator's command. Use
    `[A-Za-z0-9._:+][A-Za-z0-9._:+-]{0,63}`.
39. **low [U]** `answers` keeps only the latest answer per question (INSERT OR REPLACE); 7.2 says "the answer is
    kept". Write "the latest answer per question".
40. **low [U]** research `sources` are SearXNG hits in hit order plus any URL the model asked to READ
    (`local_research._source`), not pages read or cited. Say so in 7.2.
41. **low [U]** FETCH_TIMEOUT 90 s is below `safe_fetch`'s worst case (5 hops x (10 + 25) s + robots), so a slow
    legitimate page is infra six times. Define 200 s, or document the cut.
42. **low [U]** STOP "instant" (LIFE.md 5 step 1) is up to START_TIMEOUT 180 s: `bin/symblic-task start` runs
    `tracked=False`, so the watcher never ends it. Correct the text.
43. **low [U]** units/life-tick.service: TasksMax=128 has no measured basis (five `bin/symblic run` processes plus
    threads), and `systemd-run --scope` children leave the unit's cgroup, so KillMode=control-group does not reach
    them after a SIGKILL. Define TasksMax from a count, and add `ExecStopPost=` that stops `run-*.scope` units LIFE
    started (record their names).
44. **low** `plan_slot` returns None when the first item's model does not fit memory, instead of trying another
    cell's smaller model. Use `continue`.
45. **low** `life-ctl arm` does not require `meta.seed_complete = 1` or a fresh VALIDATE pass. Require both.
46. **low [U]** while STOP exists, `run_bounded` refuses every subprocess, so `new-release`, `adopt`, `canaries`,
    `gate-selftest` and `apply` print misleading failures ("bin/symblic check failed"). Operator tools pass
    `tracked=False` or print "STOP is present".
47. **low** an agy run marks its worker node busy for its whole wall time though its model is in the cloud, so a 50-minute
    agent run rests that worker node for light-model work. Count agent runs at weight 0.25 in `busy_seconds`, or document.
48. **low [U]** the brief asks for "extremely light weight models"; three organs use agy (a cloud agent) with no
    quota accounting besides 12 runs x 4 agents a day. State the decision and the quota in LIFE.md 1.
49. **low** `benchmarks()` is called many times per tick and re-opens `benchmarks_invalid` each time (count noise).
    Validate once per tick and cache.
50. **low [U]** "a process starts only when elapsed + its timeout + ..." (LIFE.md 4) is applied to the first
    process of a stage only; the following git calls of refresh_clone/start_run are not admitted. Write "a stage
    starts only when elapsed + the sum of its processes' timeouts + KILL_GRACE + 60 <= TICK_HARD" and pass that sum.

---------------------------------------------------------------------------------------------------------------
## Platform claims checked (rg) — holds unless listed above

contract_problems(): "contract holds". Verified true: autogen run id, 404 for an unknown run (AutogenError 404),
promotion is the hub's commit -> apply into the project working copy, check timeout 120, catalogue `nodes[].ready`
survives `symblic_agent_teams.capability_catalog`, cluster map passes items as "$1" through xargs with duplicates
kept and `label` stored in `meta`, map timeout bound 3600, job statuses queued/running/done/failed/cancelled/unknown,
job cancel 404 when not running, status `vitals.cpu` = % busy and `memavail` bytes, high-power mode/cool state fields,
the fleet runner one model per node and 1800 s capacity wait, the fleet runner units carry MemoryMax/CPUQuota/RuntimeMaxSec, the fleet runner
sizes num_ctx to the prompt (no truncation risk from OLLAMA_LIMITS), `--ollama-limits` keys, a pinned `--by @node`
is never thermally re-routed, `symblic check` is a pure parser, sqlite3 CLI absent, devcheck reads
DEVCHECK_RUFF/DEVCHECK_AST_GREP (both native binaries). Contradicted: findings 4, 6, 24 (and 5 against the kit's
own STOP claim).

FINDINGS_TOTAL=50
UNDEFINED_DETAILS=25
VERDICT=CHANGES NEEDED
