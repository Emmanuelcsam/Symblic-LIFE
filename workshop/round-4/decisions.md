# Round 4 decisions: findings not applied as written

One line per finding that was rejected, already true, or applied only in part or in another form, with the reason.
Every other finding in critique-local.md (Lo, 40), critique-cloud.md (C, 70) and critique-chatgpt.md (G, 106) was
applied in LIFE v2.3 (see LOG.md, Round 4). Platform facts cited here were read in the live checkout on 2026-10-11
(rg/sed, no model, no run); one scratch `git clone --no-local` + `sparse-checkout` of a two-file repository in the
session scratchpad showed which configuration keys LIFE's clones hold (GIT_CONFIG_ALLOWED); nothing else was run.

## Wrong, or already true

- G5 (local clones hardlink objects): already true: every LIFE clone is `git clone --no-local` (no hardlinks, no shared objects, no alternates); git_admin_problems now also refuses an alternates file.
- G22 (observe-only re-sends): already true for admission (resend required may_admit); applied the rest: a re-send now also needs a tick with no hold.
- G25 (an in-flight start can land after its cancel): already handled (round 3 G12): STOP re-requests the cancel of every LIFE run id at every tick while it exists, and a STOP tick now reconciles too; a server-side tombstone is a platform change.
- G35 (canaries need a maintenance admission): already true: `canaries()` is admitted by `can_start` (time and STOP only), never by ARMED or the canary hold, and a pass removes the hold before step 10; the text now says so.
- G40 (tuning accounting undefined): already true: one window entry per finished stage, escalation steps add none, nothing is judged before 10 entries; the text now spells it out.
- G42 (a finalization record per item and generation): already counted once (count_finding_done only when the patch leaves review; needs_work never counts; a run is collected once by its state); a separate finalization table is a redesign.
- G81 (autonomous descendants block report closure): already true: a derived question's origin is a fact id, which `descendants()` never follows; the text now says derived questions have no report (C46).
- Round 3's G50 decision ("a deny-all network flag is a platform change") was WRONG: `landlock_sandbox.parse_ports('')` documents "An empty string means no TCP connect at all"; LIFE now passes `--net-connect ''` (pinned), which closes the port-1 exfiltration path G12 found.

## Needs a platform change (kept as a GAP or a decision line)

- G7 (autogen staging integrity and a promotion receipt): staging and promotion are autogen's; LIFE checks the workspace after promotion (git_admin_problems before any trusted git, the gate's checks); GAP 18, DECISIONS 27.
- G9 (a supervisor records test completion outside the candidate's process): needs a new judge in the platform; GAP 19, DECISIONS 25.
- G12 (UDP exfiltration; refuse candidate execution until it is blocked): TCP is now fully denied; refusing all candidate execution until the launcher gains a UDP rule would switch "fixes errors" off entirely, so the exposure is an explicit operator decision (DECISIONS 21, GAP 15).
- G14 (metadata changes could disable the kill switch): applied in part: STOP and FREEZE are fail-closed (an uninspectable control/ reads as STOP); a complete metadata syscall filter is the launcher's (GAP 16, DECISIONS 22).
- G50 (enforced byte and inode quotas on every writable hierarchy): needs filesystem project quotas; applied in part: prlimit --fsize on every sandboxed run, DISK_FREE_MIN re-checked before every heavy local process, scopes bound memory.
- G51 (disable benchmarks until a job-wide cgroup exists): only operator-written templates run; GAP 7 stays and DECISIONS 24 records the exposure.
- G52 (a remote artifact ledger with quotas): applied in part: every attempt checkout is discarded through the hub's own route after collection, refusals listed in STATE/operator/node-cleanup.txt; the per-workspace worker node mirrors are the hub's (GAP 14).
- C13 (split life-fetch into a network fetcher and a sandboxed parser): the parser is local_research.page_text/pdf_text, which imports the repository; a sandbox that can read REPO can read .env. Recorded as DECISIONS 23 instead.
- C9 (an apply refused only by existing rows ends abstained): applied in another form: rule 7 (no UNIQUE index on a snapshot table) removes the case, and both validations now agree.

## Rejected as written, for a stated reason

- G8 (run the candidate tree read-only so judges cannot be rewritten mid-run): the candidate runs inside the test process, so it can forge results in memory whatever the file permissions; Landlock rules are additive, so `.git` and the tests cannot be made read-only under a writable checkout. The limit is now explicit (GAP 19, DECISIONS 25).
- G17 (descriptor-relative opens for every STATE file): STATE is 0700, operator-only and unreadable from candidate code; applied in part: every STATE directory, database, -wal and lock file is checked each tick (exact mode, operator, regular, one link).
- G18 (a byte manifest of the whole import closure): it would disarm LIFE on every unrelated platform edit; applied in part: bin/symblic, symblic_run.py, symblic_apply.py, fleet_runner.py and bin/local-research added to PLATFORM_PINS; GAP 18.
- G28 (a killable helper process per HTTP exchange): applied in another form: at the deadline the caller closes the response and an outstanding-exchange cap (4) refuses new ones.
- G36 (persisted continuation cursors for every maintenance phase): every other phase is already bounded (reports 20 per tick with a 5000-item traversal, retention by SQL, the backup once a day); applied to the one unbounded walk (STORAGE_WALK_SECONDS).
- G37 (reserve a start for the oldest long action): applied in another form: odd working ticks run the slot phase before the host stages, which gives each side the tick's start every other tick without a reservation ledger.
- G55 (monotonic time with boot identities for every duration): round 3's reason (G76) stands: each tick is a new process; in-tick deadlines are monotonic; a wall-clock jump is now detected (notice clock) and counted as an unobserved, loaded interval.
- G56 (record the effective unit configuration in ARMED and re-check it every tick): applied at arm (`unit_problems` compares the LOADED units); a per-tick systemctl query was not added.
- G63 (validate migrations in a killable worker process): applied in part: one deadline over the paged copy, both passes and the checks, STOP-aware; the copy is bounded by 64 MiB logical size, so a separate worker adds little.
- G75 (persist research launch intents outside the wrapper): applied in part: every exit path cancels what it started; a SIGKILLed wrapper is covered by the tick's call_intents row and the orphan hold.
- G79 (versioned source snapshots with freshness checks): a later decision; GAP 20 states the limit.
- G80 (typed dependency edges): round 3's reason (G109) stands; merges record merged_into and reports list them.
- G82 (versioned reports regenerated on late approval): applied in part: approval age already uses created_at; reports are snapshots by definition (section 7.1 says so).
- G93 (a repository-wide writer lock for apply): round 3's reason (G121) stands: no platform lock exists; apply stays an operator command with the moved-file check (now by blob id), the branch check, the journal and recover-apply.
- G97 (re-gate a moved-base apply against the current tree): round 3's reason (G122) stands (it would run candidate code against a copy of the live checkout); applied in part: the apply records unverified_base and prints UNVERIFIED.
- G101 (full identities beside truncated ids): round 3's reason (G92) stands.
- G102 (generate SQL and regexes from the constants): the schema text is what the registry is created from; applied in part: the protocol limits are named in LIFE.md and VALIDATE refuses a kit where code, SQL and regexes disagree.
- C11 (end STOP-cancelled items at the operator): applied as the other option the finding offered: the texts now say STOP-cancelled work returns to its queue and starts only after the operator arms again (DECISIONS 8), which keeps arming as the one restart act.
- C18 (a perf_fix change class): round 3's reason (C28) stands; applied in part: README says what "optimises" means and experiment_passed notices carry a ready-to-send `fix:` command.
- C19 (a `life-ctl.py error TRACEBACK --test` intake): the `fix: tests.x path.py:function` prefix gives the same route through the inbox with one fewer path; README says what "fixes errors" means.
- C20 (an operator-approved column-mapping adapter): a later decision (GAP 13); applied in part: migration_applied names the tables the store adapter fills.
- Lo3 (LIFE runs `git worktree remove` on hub checkouts): applied in another form: the hub's own route (POST /api/agents/work/discard, pinned) removes the host and the worker node checkout; LIFE never edits the hub's records.
- Lo4 (persist the metadata hash and verify it before every git command): applied in another form: the hub legitimately writes refs and worktrees in the clone during runs, so a persisted hash would delete healthy workspaces; instead a workspace_guard row is committed around each sandboxed run (a crash leaves it: the workspace is deleted) and a configuration allowlist runs before every trusted git command.
- Lo8 (WORST_CALLS x CALL_P95_SECONDS timeouts): no latency has been measured and nothing may run; applied in part: the per-call wall is derived (75 s = CALL_TIMEOUT / 12), a timeout holds only that program, two top-rung timeouts end at the operator; the p95 measurement is in GAP 8.
- Lo11 (c: agent seeds only on node-i or model-free nodes): the memory rule (+4096 MiB beside a live run) and the duty rule (an agent start needs an idle hour) cover co-residence; DECISIONS 5 says an agent run consumes its node's window.
- Lo16 (measure p95 RSS for TICK_MEMORY_MAX): applied in the other form offered: every slot process runs in its own scope (SLOT_MEMORY 1G, unmeasured: GAP 8).
- Lo19 (arm refuses without a passing gate-selftest): applied in the other form offered: the codebase organ holds (notice gate_unproven) until gate-selftest passed for this kit and these platform files.
- Lo36 (a relaxed screen only for diffs): applied with C8's exact definition for the code tier; the strict tier stays for operator and web text.
- Lo39 (a measured clone time): only the sizes were measurable without running a clone (pack 762502 KiB, tree 786316617 bytes); the clone time is in GAP 8.
- Lo40 (ready-to-send commands in already_passing too): an already passing test needs no fix; applied to experiment_passed and finding_owner.
- C48 (SCOPE_TASKS_MAX = 64 + 4 x cpus): applied in the other form offered: RAYON_NUM_THREADS=4 for ruff and ast-grep; SCOPE_TASKS_MAX stays 64.
- C56 (chunk IN lists at 500): applied in the other form offered: contract_problems requires SQLite >= 3.32 (the host has 3.45.1).
- C64 (efficiency = done / cost): applied as the other option: section 9 states that abstentions count as useful work on purpose (and abstain_rate catches a broken cell).
- G47 (quiet credit needs two observations at most TELEMETRY_REFRESH apart): ticks are 300 s apart, so that rule could never grant quiet; applied as two consecutive OBSERVED samples (every LIFE node present, every online one with a load reading).
- G2 (separate or read-only git administrative storage): Landlock cannot exclude `.git` under a writable checkout; applied in another form: .git must be a real directory with no commondir, gitdir or alternates, its configuration allowlisted, its administrative files hashed around every sandboxed run.
- G3 (a supervisor-owned baseline tree): applied in part: GIT_NO_REPLACE_OBJECTS for every trusted git, refs (replace refs included) and loose objects in the hash; the base stays the clone's own objects.
- G10 (a verified-empty dedicated cgroup per candidate run): applied in part: check 0 now runs in its own life-check scope (watched tests and gates already did), stopped when the run ends; emptiness is systemd's scope stop.
- G11 (require ABI 6): the launcher decides its mechanisms; applied in part: the text states which feature needs which ABI, and the probe proves a signal to an outside process is denied.
- G24 (STOP status per target: requested, confirmed, unresolved): applied in part: STOP ticks reconcile and status.json counts runs with a cancel requested; the stopped notice lists unconfirmed targets.
- G32 (a stop generation compared before every COMMIT): applied in part: the STOP file is checked in the progress handler and immediately before COMMIT; a STOP that comes after COMMIT finds the effect recorded.
- G94 (private before/after blobs, empty-directory cleanup): applied in part: before-bytes, modes and existence recorded, parents and links checked, absence restored as absence; after-bytes are recomputed from the patch, as before.
