# Round 3 decisions: findings not applied as written

One line per finding that was rejected, or applied only in part or in another form, with the reason. Every other
finding in critique-local.md (Lo, 50), critique-cloud.md (C, 58) and critique-chatgpt.md (G, 145) was applied in
LIFE v2.2 (see LOG.md, Round 3). Platform facts cited here were read in the live checkout on 2026-10-11 (rg/sed, no
model, no run); the Landlock wrapper was exercised once with harmless local commands (`/bin/true`, `/bin/false`,
`sleep`, the sandbox probe) in a scratch folder, which calls no model, agent or cluster job.

## Wrong, or the platform contradicts it

- C6 (restUntil null holds LIFE forever): wrong: `cluster_highpower.rest_until` returns 0 when no rest is pending, never null; that line is now a contract row, and a non-integer restUntil is a hold.
- C4 (SYMBLIC_THERMAL may re-place a call on another node): wrong for LIFE's calls: `symblic_apply._runner` places only when `node in ('', 'auto', 'nodes')`, so a call named `@NODE` is never moved (thermal only refuses); applied as a contract row and the sentence "a call runs on NODE or not at all"; SYMBLIC_THERMAL stays on.
- G54 (a valid finding plus three scope paths exceeds 1400 characters): already handled: the finding text is cut 700/500/300/150 until both statements fit; VALIDATE now renders the largest legal values of every organ (worst codebase case 1343 characters).
- G52 (descriptor inheritance unspecified): already true: Python's subprocess closes every descriptor but 0-2 (now passed explicitly, close_fds=True) and stdin is /dev/null; written into section 1.
- G112 (whitespace-only inbox commands): already true: a text empty after strip was refused; the refusal now says "empty command".
- G114 (inbox crash ordering): already true: the command row and its classify item are one transaction before the archive move, and the same file always yields the same command id (INSERT OR IGNORE); the archive is now no-replace too (G115).
- G21 (a 404 is not proof of non-submission): applied in another form: autogen is idempotent per request id (`request_digest`, pinned), so a run the server does not know is RE-SENT with the identical request instead of preserved forever; a 4xx refusal is the only not_submitted.

## Needs a platform change (kept as a GAP or a contract row)

- G12 (cancellation tombstones for in-flight submissions): no such hook in autogen; instead STOP re-requests the cancel of every LIFE run at every tick while it exists and LIFE never resubmits under a new id, so a run created after a cancel is cancelled at the next tick.
- G25 (an idempotency key on the map route): the route has none; LIFE's label travels in `label` -> `meta.label` (pinned) and LIFE never starts a second job while one is uncertain (the item stays running under its label until the listing shows it or it goes to the operator with the node held).
- G29 (a job-wide cgroup for benchmarks): it would need `systemd-run --user` on each worker node's user manager over the map route's SSH, which is unverified; GAP 7 names it as a map-route change; per-process prlimit, timeout over the group and the per-run output cap stay.
- G30 (platform-retained job artifacts): retention of the map job's on-disk output (OUT_FILE_CAP) is the platform's; applied in part: each run's output is cut to 4096 bytes so 7 runs fit the job's kept 40000 bytes (both pinned).
- G49 (Landlock does not cover chmod/chown/utime): true; GAP 16; LIFE's STATE check holds on a changed mode (a denial of service, not a read); a destructive probe is not run.
- G50 (port 1 is not "no network"): the text is corrected (TCP only to port 1, UDP open); a deny-all network flag in landlock_sandbox.py is a platform change (GAP 15 for UDP).
- G51 (probe UDP and signal scoping too): applied in part: the probe checks TCP 8080, a unix socket and unreadable paths; UDP is known open (GAP 15, pinned from the launcher's own docstring); signal scoping is Landlock ABI 6 (the host has ABI 8) but probing it needs a victim process.
- G83 (pin model digests and context sizes): the inventory prints names and sizes only; a digest pin is an inventory change (GAP 6); memory admission uses the measured MODEL_MIB table plus 1024 MiB, and the fleet runner sizes num_ctx to the prompt.
- G121 (a repository-wide writer reservation for apply): no platform lock exists; apply stays an operator command run when the operator chooses, with the moved-file check, the branch check, the journal, recover-apply and revert.
- G125 (atomic deployment of live-static files): the dashboard serves the checkout directly; an atomic asset switch is a platform design; apply warns that static files go live one by one.

## Rejected as written, for a stated reason

- Lo47 (count an agent run at weight 0.25 in busy_seconds): the agent's tool loop (tests, builds, git) runs on the worker node, so its load is real; it stays at full weight.
- C28 (a perf_fix change class): it would benchmark the clone's candidate code on a worker node through the map route, outside any sandbox (GAP 7); GAP 12 keeps the design for the operator, and section 2 now says plainly that v2.2 cannot turn a passed experiment into a patch.
- G18 (a separately installed trusted bootstrap): a bootstrap is itself unverified code; instead the kit's code is hashed with types, modes, symlinks and stray .pyc files at arm and every tick, STOP is handled before the release or the schema matters, and only the operator writes the kit (docs/life/ is gate-protected).
- G45 (judge an immutable materialization of the tree): it would need a second copy of the clone per gate; the post-gate re-stage (`git add -A` and diff equality) catches every tracked or untracked write, `git clean -ffdx` removes ignored files before every run, and the git configuration hash catches .git writes.
- G46 (no candidate-controlled import may reach the judge): the judge's own code (bin/, scripts/, rules/, pyproject.toml, sgconfig.yml) is protected; devcheck's purpose is to import and run candidate code (the tests), so it runs sandboxed rather than import-free.
- G76 (monotonic time with boot ids for every duration): each tick is a new process, so monotonic time cannot carry durations between ticks; UTC seconds with the dt clamp, the unobserved-interval rule and the offline sample-density rule cover clock steps and reboots.
- G92 (store full identities to detect truncated-id collisions): ids are 64 bits; at the organism's scale (well under a million items) the collision chance is below 1e-7; the canonical-form CHECKs stay.
- G109 (a typed many-to-many provenance graph): a redesign; with re-occurrence keys a merge happens only for concurrent work, a merged command records `merged_into`, and the covering report lists it.
- G122 (re-run the full gate on a snapshot of the live tree before apply): that would run candidate code against a copy of the live checkout (with .env and secrets_data/), which the sandbox design forbids; the operator runs bin/devcheck in the live checkout before committing.
- G128 (a recovery manifest of every artifact a backup needs): releases and bundles are immutable and never deleted, so every file a restored registry names exists.
- G133 (an operator archive/export operation): a new subsystem; the retention rules (C46) bound growth and STATE_MAX_BYTES holds new work.
- G139 (import only an audited pure-contract module in VALIDATE): VALIDATE imports only modules that are inert on import (the repository's own invariant), and the policy round trip needs bin/symblic-task's real parser.

## Applied in part, or in another form

- Lo12 (slot phase is a barrier): applied as per-node refill (up to 4 actions per node per tick); the extra "research only on an otherwise idle node" rule is unnecessary because a node runs one action at a time.
- Lo15 (gate-selftest is vacuous): applied, plus a second phase in which a line that does not parse must fail at devcheck (exit 4), and the sandbox probe first.
- Lo20 (a timed-out start leaves an untracked twin): applied as the identical re-send (G21 above) instead of two 404 polls.
- Lo21 (research bound not derived): applied with the platform's real loop count (`range(max_tools + 2)`, pinned): RESEARCH_TOOLS 3, RESEARCH_STEP_TIMEOUT 180, RESEARCH_TIMEOUT 2100; the wrapper also refuses a 6th model launch (G82).
- Lo31 (revive and requeue): applied; a requeued gate or apply item returns to its agent stage (its workspace was reset, so the same stage would only find no diff).
- Lo43 (TasksMax basis, scope names): TasksMax 192 is derived in life_common.TICK_TASKS_MAX (no live measurement exists); scopes are named life-<purpose>-<8hex> and ExecStopPost stops `life-*.scope` by glob, so no list of names is kept.
- Lo46 (operator tools under STOP): commands that start processes refuse with "STOP is present" instead of running untracked.
- C3 (pin and probe the sandbox): applied (contract rows for the ABI refusal and the UDP fact; the probe at arm and gate-selftest); the launcher's default read-only roots are its SYSTEM_RX/SYSTEM_RO tuples, covered by the probe's unreadable-path checks rather than another regex.
- C14 (division deadline in ticks): applied (12 armed working ticks), and the wall deadline is kept as a 24 h backstop checked even while held (G61).
- C16 (tell the agent the migration grammar): applied as MIGRATION-RULES.txt written into every database workspace (the full grammar would push the statement past 1400 characters); the statement names the file and the two key rules.
- C21 (every number in life_common.py): applied for every timing, size bound and rule threshold in every program and the gate script (VALIDATE check 12 covers all of bin/); one_line display widths of log and notice text stay literal: they bound no behaviour.
- C25 (refuse a detached HEAD at seed): applied as an explicit `--branch NAME` (default main) that must exist in the live checkout; the tracked branch is printed by seed and life-status.
- C29 (store rows): applied as the store adapter for tables whose columns are fact_id plus source_url, claim, quote, created_at; GAP 13 keeps typed adapters for other tables.
- C30 (fetch outside the sandbox): applied as its own scope (MemoryMax 1G) and prlimit --as 1 GiB; Landlock is not used (the fetch needs the network and the .venv), stated in section 11.
- C31 (slot fairness): command cells go first only when their oldest queued item has waited a tick; a division step takes its node's slot at most every 2nd armed tick; otherwise last_served_at order is unchanged.
- C37 (move ignores rule 11): move refuses a node not online in the latest sample; agy readiness is not checked (the cell waits there), stated in section 15.
- C46 (rows and folders never pruned): applied for calls rows, run folders, inbox-done, acknowledged notices and abandoned temporary artifacts; abstained OVERFLOW items are kept (deleting item rows would let the same identity be queued again and loses lineage).
- C48 (retire --force leaves rows live): applied as stated semantics: the cancel is a request and the row stays live until a tick sees the run end (Lo4).
- C52 (pin research results; scratch HOME): the result keys and the loop are pinned; a scratch HOME is rejected: fleet_runner.launch on the host needs the operator's HOME to reach the worker nodes.
- C55 (an operator-signed DECISIONS.md): applied; "signed" = the operator passes its sha256 prefix at arm, which ARMED records (G141).
- G1 (agent division unreachable): applied as one child workspace per tick under CLONE_TIMEOUT (not a 1320 s reservation per pair).
- G11 (schema validation precedes STOP): STOP now comes first; a separate ownership journal is rejected (the runs and items rows are the ownership record, read with per-query fallbacks).
- G17 (persist model-call intents): the fleet runner run ids are created inside bin/symblic run, out of LIFE's reach; the node of every orphaned model item is held ORPHAN_HOLD_SECONDS (the fleet runner's RuntimeMaxSec ends the orphan).
- G20 (closed schemas and golden fixtures for every API): every shape LIFE reads is a contract row and a wrong-shaped report is a `contract` outcome; golden fixtures belong to the admission tests (GAP 8).
- G23 (completion bound to an immutable promotion artifact): collection is one transaction with the status copy and is recovered after a crash; the gate records the diff's sha256 in the bundle; no separate promoted-tree id.
- G33 (backtracking regexes): param_rx is at most 200 characters with no quantified group (no nested repetition); no subprocess regex evaluation for an operator-authored file (the unit's TimeoutStartSec bounds the tick).
- G37 (integrity manifest omits types and modes): applied (symlinks, modes, directories, stray .pyc); executing from a verified snapshot is rejected as in G18.
- G43 (assertion counting is weak): a test_only patch is never ready from a model accept and may touch only its own module; a trusted mutation check is rejected (no such tool exists; the operator reads the change).
- G48 (private history inside the clone): text applied (GAP 11 now says the objects are in the clone's .git and that sandboxed candidate code runs only after an agent run the same decision admits); a history-sanitized repository is the operator's choice; partial clones stay rejected (round 2: provision_remote pushes every object).
- G58 (send the previous diff on needs_work): the previous patch id is recorded (payload and bundle meta); the diff is not sent: statements are at most 1400 characters and a worker node checkout receives only committed files.
- G71 (reserve worst-case runtime against the duty cycle): applied for program, research, division and benchmark actions; not for agent runs, which would forbid every agent run (wall 3600 > 3000; GAP 4).
- G74 (telemetry scalar domains): memavail an integer not above memtotal, restUntil integer seconds, temperature -50..150, booleans refused; a missing CPU count falls back to 1.
- G78 (demote only after budgeted probes): a 7-day hold after a rung_up stops oscillation; probes are rejected (they would spend model calls on answers known to be worse).
- G86 (integer types everywhere): typeof checks on depths, counters, priorities and budgets; not on every time column.
- G89 (closed payload schemas with types): closed key sets per (kind, stage) and PAYLOAD_MAX are enforced before every write; value types are set by the code that builds them.
- G90 (schemas for meta values): meta keys are declared and enforced; their JSON values are read with explicit defaults.
- G91 (relationships and immutability): foreign keys from runs, calls, patches, proposals, experiments and migrations to items; birth facts, item identity and taint immutable by trigger; other evidence tables stay update-in-place.
- G100 (migration execution and growth bounds): a 120 s progress deadline on validation and on the transaction, and an organism size cap; no per-index storage reservation.
- G107 (failed sources count as evidence): failed or empty sources never count; the retry path is `life-ctl requeue` on the digest item.
- G119 (escaping): every report field passes one_line and `life-ctl report` strips control characters; no Markdown link validation (reports are local text, never rendered in a page by LIFE).
- G120 (secret screening channels): redaction added for source titles, review reasons, hypotheses, the restated line, notice text and log lines; raw call folders are operator-private evidence by rule.
- G136 (seed intent): an explicit branch, and a resumed seed refuses another kit or branch; not a full intent record.
- G137 (force-retire waits for termination): the run row stays live and owned until a tick sees it end; the operator's command does not block on the platform.
- G143 (notice identities): every kind with its subject is a generated, enforced table; recovery conditions are stated in each kind's section rather than in the table.
- G145 (a complete platform adapter for tests): configure() now also moves the inventory, fetcher, sandbox launcher and gate script; a full adapter object is test-harness design for GAP 8.
