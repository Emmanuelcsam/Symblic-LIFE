# Round 2 decisions: findings not applied as written

One line per finding that was rejected, or applied only in part, with the reason. Every other finding in
critique-cloud.md (C), critique-local.md (Lo) and critique-chatgpt.md (G) was applied in LIFE v2.1 (see LOG.md,
Round 2). Platform facts cited here were read in the live checkout on 2026-10-11 (rg/sed, no model, no run).

## Wrong, or the platform contradicts it

- C2 (run the gate under `bwrap --unshare-net ...`): rejected as written: Ubuntu sets kernel.apparmor_restrict_unprivileged_userns=1, so unprivileged bwrap fails (landlock_sandbox.py docstring); applied with the repository's Landlock launcher instead (`landlock_sandbox.py --require`, the path symblicos/autogen.py:sandbox_prefix uses), which refuses rather than degrading.
- C8 (the server may normalise with the run's engines/nodes, so LIFE's sha256 could differ): the sha part is wrong: symblic_autogen.normalize computes `sha256` over the policy without `engines` and `nodes` (now a contract row); the flagless-field part was right and is applied.
- C21 (one interpreter: `.venv/bin/python` when it exists): applied as one interpreter, but `/usr/bin/python3`: CLAUDE.md says tests use the system/isolated test Python and service Python is the venv; the gate, check 0 and watched tests all use `/usr/bin/python3 -s -B`.
- Lo5(b) (gate runs the LIVE checkout's bin/devcheck on the clone): rejected: the live checkout (with .env and secrets_data/) must not be readable inside the sandbox; instead bin/, scripts/, rules/, sgconfig.yml and the test package files are on the gate deny list, so the clone's `./bin/devcheck --changed BASE` is byte-for-byte the base commit's judge.
- Lo22 (`git clone --filter=blob:none`): rejected: a partial clone fetches missing blobs lazily from the live repository, which is invisible inside the sandbox; applied as `--no-local --single-branch --no-tags` plus a sparse checkout without `.backups/`, and removal of retired codebase clones.
- G46 (a 404 is not proof the run never existed): rejected: autogen's run store is the single server's own files (symblicos/autogen.py AutogenManager.get reads `self._read(run_id)`); a 404 is authoritative for that store. A live run that later answers 404 is now collected as a terminal unknown (infra).
- G49 (the server must verify the policy before enqueueing): rejected: no such platform hook exists and the kit cannot add one; the residual risk is closed statically (VALIDATE round-trips the flags through bin/symblic-task's own parser to the same sha256) and at runtime (contract pins the flagless defaults; each armed tick compares the running server's `/api/symblicos/autogen/catalog` defaults); a mismatch still cancels at the first poll.
- G87 (children inherit the parent's mutable working tree): wrong: `git clone` copies commits only; uncommitted files never travel (PROTOCOL.md section 3 says so now).
- G114 (knowledge insertion and the lesson item are not atomic): wrong: both happen inside the single `record()` transaction; a crash rolls both back.
- G183 (apply may validate against an older schema): wrong for v2 and v2.1: the apply stage builds its snapshot from organism.sqlite3 at apply time; the workspace snapshot only guides the agent (and is now sha-pinned).
- G184 (two drafts can pick the same migration number): rejected: the tick is the only writer (flock), and next_migration_id reads every migration row and every database item's payload in the same process.
- G221 (required inputs may not reach the worker node): rejected: LIFE commits every input it writes (genome, genome-base, schema snapshot) before submit, and agent_hub.provision_remote sends the branch; only ignored files and files over 25 MiB are skipped, and LIFE writes neither.

## Applied in part (the rest is out of the kit's reach or a later decision)

- G1 (arm refuses without an admission-test receipt): applied as `arm --confirm ARM-UNTESTED`: the tests do not exist yet (GAP 8) and this workflow may not write and run them; a receipt check would make arming impossible rather than explicit.
- G3 (recurring work only from an operator agenda; LIFE invents no objectives): agenda applied (control/agenda.json); "invents no objectives" rejected for derived questions, because the brief says it "learns from the internet" continuously; they are bounded (2 a day, 3 queued, NO_SELF_QUESTIONS switch).
- G4 / C32 / Lo38 (codebase optimisation path): decided, not built: optimisation = operator benchmark templates measured by the compute organ; an autonomous `perf_fix` class is GAP 12 for the operator.
- G5 / C29 / Lo34 (organism tables need a writer and reader): decided: v2.1 grows schema only (section 7.8, GAP 13); a typed per-table adapter is a later operator-approved design, because model-generated DML is exactly what the migration rules forbid.
- G6 (retrieve existing knowledge before new research): reports, answers and question_sources applied; a pre-research knowledge lookup is not built (the model searches; known sources still count for the question without a refetch).
- G7 (inject clock, runner and API adapter): `life_common.configure()` (paths, API URL, the three executables) and the `Procs` runner passed into Tick applied; a clock seam is left to the admission tests (they can set `Tick.now`).
- G9 (attested per-run sandbox on the worker nodes): out of the kit's reach: worker node-side confinement is the hub's; recorded as GAP 10.
- G10 (no real HOME for subprocesses): applied for every process that runs candidate code (Landlock, empty temporary HOME); trusted platform tools (bin/symblic, bin/symblic-task, git) keep the real HOME because their logins and configuration live there.
- G12 (an approved input manifest before provisioning): sparse checkout, gate deny list and the CODEBASE_HISTORY_OK switch applied (GAP 11); a provisioning manifest is the hub's (platform).
- G14 (a provenance set per item): applied as taint derivation (most external parent taint) plus `origin`; a full provenance set column was not added.
- G15 (screen every persistence boundary): applied to fetched text, quotes, claims, research answers, foci, inbox, agenda, findings, diffs; `STATE/calls/<id>` model records are not screened: they live in the 0700 STATE, are never quoted into a prompt or document, and are deleted after 14 days.
- G19 (enforced memory/process/disk limits for every execution): benchmark jobs now run under timeout, nice and prlimit; model calls are the fleet runner units (MemoryMax, CPUQuota, RuntimeMaxSec in fleet_runner.unit_argv) and agent runs the hub's: the kit cannot set those.
- G21 (an admission lock and control epoch): rejected as written: every admission re-reads STOP immediately before its effect and the watcher ends any process started in the remaining instant within 1 s + 30 s.
- G23 (keep the node reserved until the fleet runner confirms the cancel): partly: SIGTERM now lets bin/symblic and bin/life-research.py cancel their fleet-runner runs; LIFE does not hold the node, because fleet_runner._check_capacity already refuses a second model on a busy node and that outcome is infra (counted).
- G26 (STOP must work with an unusable registry): stop_everything needs only the registry; with no readable registry life-ctl stop prints how to cancel by hand; querying executors by an organism instance id needs a platform listing by label that does not exist for autogen runs.
- G29 (one reservation table for agents, models and jobs): rejected: agent runs do not use a node's Ollama slot; the per-node load ledger (calls + runs + jobs) and the benchmarking-node exclusion already keep work apart.
- G31 (a versioned telemetry adapter with fixtures): value validation applied (finite, ranges, booleans, duplicates); fixtures belong to GAP 8.
- G33 (monotonic governor accounting across boots): wall clock kept (the governor persists across ticks and boots, where monotonic time resets); a backwards clock step counts 0 s and a forward jump is capped at 3000 s.
- G34 (a dedicated 30-second load monitor): rejected: it would be a resident process on the host; LIFE's own load is now measured exactly from its call/run/job intervals, and a long gap is capped.
- G35 (stop attempts inside running runs at the cutoff): needs an autogen attempt lease (GAP 4); runs are bounded by 900 s attempts, 3600 s wall and LIFE's cancel at 4500 s.
- G36 (consult platform capacity before launching): the fleet runner's own capacity check and 1800 s wait stay authoritative; LIFE adds its memory rule and one run per node per tick, and infra outcomes are counted.
- G38 (a new governor starts in hold): rejected: the first sample with readable telemetry and no hold reason may work; unreadable telemetry is already a hold.
- G41 / G79 (an execution-intent journal for every stage): agent runs, benchmark jobs and migrations have durable intents and recovery; model stages simply re-run (their effects are written only by record() in one transaction), and fetch/gate/apply are idempotent.
- G47 (separate unknown states): LIFE's own uncertainty is now `submit_unknown`; the server's terminal `unknown` keeps its name and is collected.
- G57 (a server-instance id in every answer): run-id identity checked; there is one dashboard server, so no instance id exists to compare.
- G58 (a total-exchange deadline): oversize detection (limit + 1 bytes) and non-finite constants applied; urllib's per-operation timeout stays (60 s at most per read).
- G62 (an organism-instance UUID and submission journal across restores): rejected; the restore procedure (section 12) instead cancels any `life-` run the restored registry does not know.
- G63 / G67 / G203 (versioned closed schemas for every payload and artifact): payload keys per stage and every identity formula are written in sections 6 and 7; a versioned schema per artifact is not added (one writer builds every payload from typed values).
- G66 (short-hash collisions): rejected: 16 hex = 64 bits; with a million items the collision chance is about 3 in 10^8, and a collision dedups an item, it cannot grant access.
- G68 (an anti-starvation rule): tie-breaker (item_id) applied; starvation rule rejected: priority 2 comes only from the operator's own urgency and every operator question ends after at most 9 sources or 3 dry runs.
- G70 (only logical completion resets the failure streak): rejected: a cell that answers a stage correctly is healthy; quarantine is about consecutive item failures, and abstentions are correct answers (section 8).
- G72 / G97 (map rungs by model identity across releases): a rung beyond a shortened ladder is read as its top; mapping by model name is not added (ladders change only by operator releases).
- G73 (only structured error codes may mean infra): kept the infra pattern for messages, but every infra outcome now counts (operator at 6), so a misclassified failure can no longer loop forever.
- G78 (efficiency counts useful outputs only): rejected: an abstention (no supported claim, an empty page) is the correct output; C57 asked for the opposite and was applied.
- G90 (a UUID division id and monotonic expiry): the 3-hour abort now runs every armed tick; the id stays sha16(parent, start time), unique while one division is open fleet-wide.
- G98 (check memory profiles for child b at commit): child b's node must be available this tick (online, not hot, held, resting or benchmarking); its memory is checked when it first runs a program.
- G101 (claim inbox files into a processing directory): O_NOFOLLOW and fstat checks applied; a separate claim directory is unnecessary with one tick at a time under the lock.
- G103 (many-to-many command/item links): a second command for the same work gets notice `command_merged`; a link table was not added.
- G107 (cap research tokens per call): tool uses, generation time and process time are capped by the wrapper; local_research sets no num_predict and the kit does not edit platform code.
- G110 (snapshot refresh policy): transient fetch failures now retry as infra; refreshing a changed page is not done (a source is read once).
- G111 (full fetch resource contract): safe_fetch's hop limit, byte cap and redirect refusal are now contract rows; parser memory is the platform's.
- G112 (name snapshots by content digest): snapshots stay named by the source key with their sha256 recorded and re-checked before extract.
- G115 (who supersedes claims): documented as reserved; no LIFE path sets `superseded` in v2.1.
- G116 / G117 (result types, closed output envelopes): reports show counts and states; output binding (echoed ids) applied; beyond that the kernel's typed records are the envelope.
- G118 (pin model digests): rejected: model artifacts are the fleet runner's and Ollama's; LIFE pins model names and checks the installed inventory daily.
- G124 (an independent oracle for test-only repairs): the gate now refuses removed assertions and added skips; a second oracle per test does not exist in the repository.
- G125 (an AST boundary for local_fix): file scope applied (only the files the traceback or the command names); a function-level AST diff is not added.
- G134 (a tree hash for the gated artifact): the diff's sha256 is recorded and the gate refuses a tree that changed during the gate; a git tree object id was not added.
- G137 (an fsync'd application journal with per-file progress): an intent/done journal applied; a revert of an unfinished apply is refused with the before-bytes path.
- G138 (revalidate the patch in an isolated checkout before live apply): rejected: the gate already ran the exact diff on the exact base; apply refuses when a touched live file differs from that base unless the operator adds --moved-base.
- G150 (a bounded revision path for proposals): rejected for v2.1: a needs_work proposal is a rejection (documented); the operator can re-send the lesson.
- G151 / G156 / G157 (fixture-based improvement and conformance tests): recorded as GAP 8 and GAP 9; adoption stays the operator's judgement.
- G160 (argv-only benchmark execution): the map API takes a command string; LIFE passes the parameter as `"$1"`, restricts it to [A-Za-z0-9._:+-], and wraps the operator's command in `sh -c` under timeout.
- G164 (separately identified results per run): the map job returns one combined output per node; with parallel 1 the six results arrive in item order, and any count other than six fails.
- G169 (quality and durability invariants per benchmark): template descriptions now say what a timing does not measure; adoption is the operator's decision.
- G170 (at least five pairs): three alternating pairs: a job is 6 runs of at most 300 s, which keeps one benchmark under about 31 minutes of one worker node.
- G181 (a sandbox and limits for migration validation): rejected: validation runs at most 24 DDL statements of at most 16 KiB on an in-memory database.
- G187 (refused versus retryable migration failures): a failed backup raises and the item is retried by the guard (3 faults); policy and schema refusals are final.
- G189 (every invariant in the database): more CHECKs added (canonical ids, organ/kind pairs, one workspace per cell, non-negative counters); state-transition rules stay in code.
- G191 (ordered schema migrations): schema 3 is required and older registries are refused; nothing is seeded yet, so there is no older registry to migrate.
- G195 (verify ownership of every ancestor): STATE and control are checked (operator, 0700, not symlinks); ancestors above STATE are the operator's home.
- G199 (count every growth location): STATE and LIFE workspaces are counted; worker node-side branches and executor artifacts are the platform's.
- G200 (reserve disk before each write): rejected: writes per tick are bounded (one bundle, at most 4 snapshots of 6000 characters, one backup a day) and the 5 GiB free floor holds all work.
- G202 (disk-full behaviour): backups are written as .partial and renamed; a failed state write is a tick fault (three in a row hold); log writes never block STOP.
- G206 (untruncated condition keys): occurrence count and last time applied; subjects are ids or short names under 120 characters.
- G210 (one machine-readable operational contract): section 13 is generated from life_common.py, VALIDATE checks the unit timeout and timing literals; units and policies are not generated.
- G211 (run VALIDATE in a sandbox): rejected: it is the operator's static validator; its Python runs with -I -B and bin/symblic check is a parser.
- G215 (a negative fixture for every invariant): 13 negative inserts and 38 rule cases added; full coverage by invariant id is not tracked.
- G218 (an expiring admission lease for remote work): rejected: no platform lease exists; runs are bounded by their own wall times and LIFE's 4500 s cancel.
- C4 (generate the fake API from the contract anchors): contract rows added for the facts listed (52 rows); the fake API is part of GAP 8.
- C12 (raise MemoryMax or delete every retired workspace): retired codebase clones are deleted; heavy children run in their own scopes, so MemoryMax 1G stays for the tick itself; selfdev and database workspaces are kept (small, hold history).
- C15 (`prlimit --nproc=64`): applied without `--nproc`: RLIMIT_NPROC counts every process of the user on the worker node, so it could fail a benchmark for unrelated reasons.
- C20 (taint `model` for failure lessons): the lesson text is now built by code only (no error or model text), so taint `code` is accurate.
- C22 (seed runs the gate on a watched test): seed has no watch list yet; applied as the operator command `gate-selftest` (README step 3).
- C31 (`deep:` prefix for longer research): rejected for v2.1: one more command grammar for the classifier path; the operator can repeat a question or put it on the agenda.
- C33 (write the twelve tests): the seam and the named test list are written (GAP 8); the tests are not, because this workflow may not run them.
- C34 (`life-ctl fixture` and a VALIDATE replay check): division steps now write calls rows; the fixture command and replay check wait for GAP 9 (bin/symblic replay's behaviour is not verified here).
- C45 / C46 (commit a RULES.md into each workspace): the rules are in the statements themselves instead (one file fewer to keep in sync).
- C63 (pin how `ensure ... else retry` counts calls): rejected: no single source line pins it; `--max-calls 12` is the hard bound whatever the notes say.
- Lo7 (check the model through fleet_runner.capabilities in-process): applied through `bin/local-research --list` daily (the existing CLI), not by importing fleet_runner into the tick.
- Lo8(b) (replace the database agent with a typed draft-table program): rejected for v2.1: Lo8(a) (operator approval of web-derived requests) closes the injection channel; the typed redesign is a candidate for GAP 13.
- Lo19 (assign-item per new item after division): applied as a code rule (shared focus words) instead of one more model call per item.
- Lo25 (control/limits.json bounded by LIMITS): rejected: the caps stay code in life_common.py; changing them changes the kit hash, which disarms LIFE until VALIDATE and arm, so every change is an operator sign-off.
- Lo31 (VALIDATE rejects every integer >= 10 in life-tick.py): applied to timing literals (timeouts, hours, days); text-length caps stay inline.
- Lo50 (clone with a sparse checkout; `.backups/` on the deny list): applied; the history itself still carries the files, so codebase agent runs wait for the operator (GAP 11).
- Lo53 (re-run experiments that failed for infrastructure reasons): a refused submit is re-queued as infra; a job that ran and failed or timed out is a measurement outcome and is not repeated (a changed template is a new experiment).
- Lo56 (move watched tests and the gate to a worker node): rejected: no sandboxed worker node execution path exists for LIFE besides the hub's agent runs; on the host they run sandboxed, in a niced work.slice scope with MemoryMax 4G, under the host load and io gates.

## Correction to round 1

- round-1 G48 said `/api/cluster/status` serves a cached probe; it re-probes when its cache is older than 2 s (cluster_engine STATUS_CACHE_SEC) and `ts` is the answer time. v2.1 drops the age rule; a slow or failed answer is the hold (Lo10).
