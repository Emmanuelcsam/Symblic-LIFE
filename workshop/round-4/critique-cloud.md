# LIFE v2.2 critique — workshop round 4 (task life-review-r4-20261011)

Task id: life-review-r4-20261011. Bundle SHA-256 (as given): 9a9c500a07c8c22b2636c4dc9e8c5a92e23a916ce6547376620c35a7517f4532.
Operating mode: review. No application source was modified; this branch adds only `.cloud-agent/STATUS.json` and this file.

## What was read (every attached kit file, in full)

docs/life/BRIEF.md, README.md, checks/devcheck-gate.sh, genome/*.sym (9), organs/*.lines.txt (3), policies/*.json (3),
spawn/PROTOCOL.md, workshop/round-4/sources/LIFE.md (all 10554 lines: sections 1-18 and every appendix block, including
the embedded DECISIONS.md, VALIDATE.sh, bin/life_common.py, bin/life-tick.py, bin/life-ctl.py, bin/life-check.py,
bin/life-fetch.py, bin/life-research.py, bin/life-seed.sh, bin/life-status.py, organs/organs.json, organs/fixtures.json,
checks/canaries.txt, spawn/example/division.json, units/life-tick.service, units/life-tick.timer,
benchmarks/benchmarks.example.json), VALIDATE.sh.txt, db-life.sql.txt, db-organism.sql.txt.
Line numbers below are LIFE.md lines (kit paths cited as the task asks). For embedded programs the kit line is
LIFE.md line minus the block offset: bin/life-tick.py = L − 3709, bin/life_common.py = L − 7189, bin/life-ctl.py = L − 2339,
bin/life-check.py = L − 2174, VALIDATE.sh = L − 1745.

## Changes

None to the kit or any application source (review mode). Files written: `.cloud-agent/STATUS.json`, `.cloud-agent/RESULT.md`.

## Tests and checks executed (all on scratchpad COPIES extracted from LIFE.md, never on the kit)

```
# 1. integrity of the bundle: every file hash in .cloud-agent/task.json re-computed
python3 -I verify_hashes.py            -> OK for all 23 files ("ALL FILE HASHES OK")
#    the bundle_sha256 itself could not be re-derived from any obvious concatenation of the file hashes;
#    it is recorded as given.

# 2. appendix blocks of LIFE.md extracted (37 blocks) and hashed; the blocks for README.md, checks/devcheck-gate.sh,
#    genome/*, organs/*.lines.txt, policies/*, spawn/PROTOCOL.md, db/life.sql, db/organism.sql, VALIDATE.sh equal the
#    attached kit files byte for byte (same sha256 prefixes: ef9872a7, 6d71d527, 204663f9 ..., e99e0e7a, 14ce3a82,
#    41725215, 87eb0b83).
python3 -I scripts/extract.py LIFE.md extract   -> "37 blocks extracted", no duplicate

# 3. VALIDATE.sh check 6 replica (db/life.sql + db/organism.sql applied twice in memory, the 23 refusals)
python3 -I scripts/check_sql.py extract
  PASS sqlite: life.sql applied twice, organism.sql applied twice, 23 bad rows refused (VALIDATE expects 23)

# 4. VALIDATE.sh check 11 replica on the extracted bin/life_common.py (inert import), every case that needs no
#    platform module (symblic_autogen, /proc/pressure), plus check 13 (generated tables) and the kinds/keys rules
python3 -I scripts/check_common.py extract LIFE.md
  83 rule cases run; failed: none
  PASS section 13 numbers / PASS section 14 notice kinds / PASS section 17 contract
  organs_problems: none; the three policies equal AGENT_POLICY_FIXED + AGENT_CHECKS; 94 CONTRACT regexes compile;
  every ask line of the nine programs parses with ASK_RX; no placement option in any program

# 5. VALIDATE.sh check 12 replica (timing literals outside life_common.py; gate timeouts 600/240) -> would pass
# 6. count of check-11 cases in VALIDATE.sh: 70 top-level expect() + 11 (stage budgets) + 4 (bad cell ids)
#    + 2 (pressure files) = 87, as section 16 says

# 7. defect demonstrations (python3 -I scripts/demo_defects.py extract); the decisive lines:
  D1  git --raw line ":100644 120000 ce01362 3594e94 T  docs/x.md"; Tick.mode_problems(): NONE;
      patch_problems(comment_or_doc): NONE; path_class: docs            -> finding 1
  D2  devcheck_tools() with a regular-file tool in ~/.local/bin: --rx dirs ['/home/operator/.local', ...];
      STATE under an rx dir: True                                        -> finding 2
  D3  has_secret() is True for the code lines <kw> = request.headers.get('X-Token'), <kw> = getpass.getpass(),
      def check_<kw>(<kw>=None): and for the prose <kw>: ceramic foams absorb water, with <kw> any of the key words
      (token, password, api_key, secret)                                   -> finding 8
  D4  False == 0 -> True (restUntil)                                     -> finding 36
  D5  UNIQUE index on a snapshot table: check 0 PASS, apply with rows: "UNIQUE constraint failed"   -> finding 9
  D7  GATE_DENY_RX: config/.env denied=False, app/secrets_data/x denied=False, ruff.toml denied=False -> findings 39, 60
  D11 has_secret() is True for a lower-case akia prefix + 16 alphanumerics and for the lower-case words
      begin … private key                                                -> finding 40
  D12 'CREATE TABLE IF NOT EXISTS org_x (Title TEXT, Doi TEXT);' -> PASS (rule 3 says lower-case) -> finding 33
  D13 failure_fingerprint(realistic tail) == ('AssertionError', '# != #')   (ok)
  D14 limits rows: 204
# 8. sitecustomize.py in the clone root is NOT imported by `/usr/bin/python3 -s -B -m unittest` (no finding)
# 9. the benchmark wrapper of Tick.start_bench, passed through the map route's own quoting
#    (shlex.quote(cmd.replace('{{item}}', '"$1"') + ' 2>&1')) and run with sh: framing LIFE_RUN k / LIFE_RESULT /
#    LIFE_END k correct for items '2:7', '3:a:b', "4:x'y"  (no defect; see finding 59 for the missing static test)
```

## Limitations

The platform (host-checkout, symblic_autogen, bin/symblic, bin/symblic-task, landlock_sandbox.py, the fleet runner, the
dashboard API) is not in this bundle (intentional), so VALIDATE.sh checks 2, 3-4 (lint, normalize, CLI round trip),
7 (target presence), 10 (contract) and the `symblic_autogen`-dependent lines of check 11 were not executed; every
behaviour under autogen, the fleet runner, Landlock and systemd is judged from the text. Findings that depend on the operator's
install layout say so (finding 2). The task's upload substitution (password fixture) is irrelevant to the findings.

## Findings

Severity: HIGH / MEDIUM / LOW. Class: [U] = a detail that is undefined or ambiguous (two readings possible);
[D] = a defect, unsafe or unbounded behaviour, contradiction with BRIEF.md, or a missing path.

**1. HIGH [D] checks/devcheck gate mode rule — bin/life-tick.py `Tick.mode_problems` (LIFE.md L5162-5174) and section 7.4 L509-510.**
`git diff --cached --raw` reports a tracked file replaced by a symlink or a submodule as a TYPECHANGE row
`:100644 120000 <sha> <sha> T<TAB>path`; the regex `([AMD])` skips it, `patch_problems` (L8394-8427) has no mode or
"new file mode 120000" rule, and `path_class` classes the path by extension. Demonstrated: docs/x.md turned into a symlink
to /etc/passwd passes mode_problems, patch_problems('comment_or_doc') and gets path_class `docs`; the 3B reviewer sees only
`deleted file mode 100644 / new file mode 120000` text; `life-ctl apply` then runs `git apply` and creates the symlink in
the live checkout (a link into STATE, ~/.ssh or .env inside the served tree). Fix (replacement): in mode_problems
`m = re.match(r':(\d{6}) (\d{6}) \S+ \S+ ([AMDT])\t(.+)$', ln)` and `if kind == 'T': out.append(f'{path}: type change
{old} -> {new} is refused')`, keep the A/M/D rules; in patch_problems add `if re.search(r'^(?:new|old|deleted|new file)
mode (?!1006(?:44|55)\b)\d+$', diff, re.M): out.append('a mode other than 100644/100755')`; in apply_patch refuse when
`git apply --summary` prints `mode change`, `create mode 120000`, `create mode 160000` or `symbolic link`; VALIDATE
check 11: `expect(Tick.mode_problems(':100644 120000 a b T\tdocs/x.md'), 'a typechange is refused')`.

**2. HIGH [D] bin/life_common.py `devcheck_tools` (L9074-9087) + `sandbox_argv` rx (L9090-9107); bin/life-ctl.py `sandbox_probe` (L2479-2488, used by arm L2701 and gate-selftest L3249).**
The read-execute root handed to the Landlock launcher is `dirname(dirname(realpath(tool)))`. For a ruff or ast-grep that
is a regular file in `/home/operator/.local/bin` (the second ruff candidate, the first ast-grep candidate), that root is
`/home/operator/.local`, which holds STATE (`~/.local/state/life`: registry, control switches, bundles, raw call traces)
and `~/.local/share`. Candidate code in autogen check 0 and in gate steps 2 and 3 then reads all of it; the invariant
"STATE unreadable inside the sandbox" (section 1 L76-80, README L106-108) is false, and the arm/gate-selftest probe cannot
notice because it runs WITHOUT the rx list. Demonstrated with that layout: `dirs == ['/home/operator/.local',
'/home/operator/.local']`, STATE under an rx dir: True. Whether the operator's the host has that layout is not pinned by any
contract row, so the kit must fail closed. Fix: `TOOL_ROOT_RX = re.compile(r'^(/home/operator/agent-upgrades/envs/[^/]+|
/home/operator/\.local/share/uv/tools/[^/]+)/bin/[^/]+$')`; in devcheck_tools use a tool only when
`TOOL_ROOT_RX.fullmatch(real)` and append `real.rsplit('/bin/', 1)[0]`; otherwise `sandboxed` exits 125 with
`'tool root not allow-listed: ' + real`; add to `state_problems()` the rule "no rx dir is a prefix of STATE, REPO,
/home/operator/.ssh or /home/operator/.config"; run the probe with the gate's rx list
(`L.sandbox_argv(ws, home, [...], rx=L.devcheck_tools()[1])`) and extend SANDBOX_PROBE to list each rx dir and assert STATE
is unreadable; VALIDATE check 11: `expect(all(not L.STATE.startswith(d + '/') for d in L.devcheck_tools()[1]), 'no rx dir
covers STATE')`.

**3. HIGH [D] bin/life-ctl.py `arm` (L2701) and `gate_selftest` (L3233-3234) hard-code the seed clone `codebase.0.00000000`; bin/life-tick.py `remove_retired_workspace` (L5918-5935).**
The seed codebase cell retires at its first division (`end_reason='divided'`, section 9) or by `retire`, and
remove_retired_workspace then deletes `PROJECTS/life-codebase-0-00000000`. From that moment `arm` runs the sandbox probe
with cwd = a missing folder, Procs.run answers 127, and arm prints "refused: the sandbox probe did not hold" forever;
`workspace_sweep` re-creates workspaces of active/dividing cells only, so nothing restores the folder. Every reboot,
STOP, kit, platform-pin or DECISIONS change disarms, so the organism cannot be re-armed after its first codebase division;
gate-selftest breaks the same way. Fix: `def probe_dir(conn)`: the workspace of the lowest active codebase cell whose
`.git` exists, else a fresh `PROJECTS/.life-probe-<8hex>` (mode 0700, removed after the probe); arm uses it;
gate_selftest takes `cid` = the lowest active codebase cell with a not-busy workspace and refuses with "no idle codebase
clone" otherwise; GAP 8 list: add `test_arm_after_seed_division`.

**4. MEDIUM [D] bin/life-tick.py `start_agent_runs` (L5512-5516) vs `division_commit` (L6127-6130) and spawn/PROTOCOL.md rule 13 / stage 4.**
Items of cells in state `dividing` may start agent runs; the commit then aborts "the parent's workspace is busy", costing
the 21600 s cooldown and the reproducer calls, although section 9 says a dividing cell receives no new items. Fix: in
that query `c.state = 'active'` (a dividing cell starts no agent run; its queued agent items wait for the children), and
PROTOCOL stage 4: "the parent's workspace cannot be busy at commit because a dividing cell starts no run; a run that was
live at division start is awaited (the division stays open, counted in ticks) instead of aborting".

**5. MEDIUM [D] bin/life-tick.py `poll_runs` (L4245-4250); bin/life-ctl.py `requeue` (L3032), `retire` (L2990); `recover` (L3945-3959).**
A run whose `autogen get` never answers (row None) is polled forever with notice `run_unknown`; its item stays `running`
at patch/draft and its workspace stays busy (no watched test, no new run, no division, no apoptosis for that cell). No
operator command ends it: requeue needs state owner/failed, retire --force re-queues only `queued` items and leaves the
running item on the retired cell, recover handles non-agent stages only. Fix: add `life-ctl.py abandon-run RUN_ID
--confirm ABANDON` (lock): runs row → `unknown`, `ended_at=now`, `detail='abandoned by the operator'`, then `collected`;
the item → `owner` (outcome 'run abandoned'), workspace reset; `retire --force` does the same for the cell's live runs;
document in section 15 and the README kill-switch table.

**6. MEDIUM [D] bin/life-tick.py `on_classify_command` database route (L6694-6703); section 7.1 L372; genome/classify-command.sym.**
The `database:` prefix is checked only after the 1B classifier chose `database`. A command that starts with `database:`
but is labelled learning, compute, selfdev or none by the model silently becomes a research question, an experiment, a
lesson or an operator notice: the operator's explicit, prefixed instruction is not honoured, and "code decides" is not true for
this route. Fix: before reading the label: `if text.lower().startswith(L.DATABASE_PREFIX): route = 'database'` (the
model's organ is recorded in `restated` only); section 7.1: "a command starting with database: is routed to database by
code; the classifier is asked only for urgency and the restated line".

**7. MEDIUM [D] bin/life-tick.py `new_item` OVERFLOW (L3903-3916), `requeue` (L3032), `on_local_research` usable count (L6756-6758); section 6 L314-316.**
An item recorded `abstained` by OVERFLOW keeps its identity forever: every later new_item with that identity returns it
(created=False), so the work is never done once the queue drains ("deduplication stops duplicate CONCURRENT work, never
later work" is false here); requeue refuses abstained items; a digest source whose item overflowed keeps `fetch_state
pending` and counts as a usable link, so a question can reach 9 "usable" links that are never fetched. Fix: outcome
prefix `OVERFLOW:`; new_item treats an `OVERFLOW:` abstained row as ended (creates a new occurrence with reoccur, or
deletes the row first); requeue accepts `abstained` items whose outcome starts with `OVERFLOW:`; on_local_research sets
`fetch_state='failed'` for a source whose digest item overflowed; write the three rules in section 6.

**8. MEDIUM [U] bin/life_common.py `SECRET_RX`/`has_secret` (L7606-7618), applied to patch diffs (L8425, refused), inbox text (L4546, refused), fetched pages (L5123, abstained), template values (L8231, refused); section 11 L929-934.**
"Credential-shaped VALUE, not a word" is not atomic: any identifier or expression of 6+ non-space characters after
`token =`, `password =`, `secret:` matches. Demonstrated (with <kw> = token, password, api_key or secret): `<kw> = request.headers.get('X-Token')`, `<kw> =
getpass.getpass()`, `<kw> = os.environ['API_KEY']`, `def check_<kw>(<kw>=None):` and the prose `<kw>: ceramic foams absorb
water` all count as credentials. So every codebase patch touching auth code fails the gate (finding failed, cell streak
+1), operator commands with such prose are refused without quoting them, pages are abstained wholesale. Fix (definition):
a value is a quoted string of 8+ characters, or an unquoted run of 16+ characters of `[A-Za-z0-9+/=_-]` that holds at least
one digit and is not followed by `(`, `[` or `.`: first alternative `\b(?:KEYWORDS)\s*[:=]\s*(?:['"][^'"\n]{8,}['"]|
(?=[A-Za-z0-9+/=_-]{16,}(?![\w(\[.]))[A-Za-z0-9+/=_-]*\d[A-Za-z0-9+/=_-]*)`; VALIDATE: the five strings above pass,
`<kw>=` followed by 18 letters and digits is refused; for pages, redact instead of abstaining (finding 53).

**9. MEDIUM [D] MIGRATION_RULES rule 10 (L8566-8567); bin/life-check.py `migration` (L2299-2305: snapshot only) vs `apply_migration` (L5346: copy WITH rows); section 7.8 L646-648.**
The agent's check 0 validates against an empty snapshot while apply validates on a copy with rows, so a UNIQUE index over
an existing table with duplicate values passes the run, is promoted, and is refused at apply as `failed` — counted against
the cell for a fact the agent cannot see. Demonstrated: `CREATE UNIQUE INDEX ... org_papers (doi)`: check 0 PASS, apply
"UNIQUE constraint failed". Fix: rule 10 becomes "a UNIQUE index may be created only on a table created in this same file;
never on a table listed in schema-snapshot.sql (its rows are not visible to you)", enforced in migration_problems (UNIQUE
INDEX ON a snapshot table → refused) so both validations agree; an apply refusal caused only by existing rows ends the
item `abstained`, not `failed`.

**10. MEDIUM [D] GAP 4 (L1476-1478), section 10 L885-891 ("no one worker node runs LIFE work for more than about 50 minutes of any hour"), policies wall_seconds 3600, AGENT_RUN_KILL_SECONDS 4500 (L7377), `duty_allows` (L4213-4216).**
Agent starts are not admitted by the duty cycle while their intervals are counted in `busy_seconds`; one run keeps a worker node
busy up to 75 min, and a worker node with two agent cells can carry LIFE agents for hours with no 600 s rest. BRIEF "keep
continuous all-worker node load under about an hour before resting" is not met per node. Fix (atomic): admit an agent start only
when `busy_seconds(node, t1 - NODE_WINDOW, t1) == 0`, set `wall_seconds 2700` and `AGENT_RUN_KILL_SECONDS 3000` so one run
never exceeds NODE_BUSY_MAX, and let node_rest apply after it; or write in DECISIONS.md line 5 that agent runs are exempt
from the per-node rest and why.

**11. MEDIUM [D] bin/life-tick.py `collect_run` (L4349-4351) vs README kill-switch L100 ("cancelled work never restarts by itself") and section 5 step 5 L271-272.**
An item whose run STOP cancelled is queued again with a new attempt and `start_agent_runs` starts it at the next admitted
tick: the cancelled work restarts after `arm` without the operator's say. Fix: end such items `owner` with outcome
`cancelled by STOP; requeue to restart` and notice kind `stopped_item` (new), or change both sentences to "a STOP-cancelled
run is queued again and starts after the next arm".

**12. MEDIUM [D] bin/life-tick.py `auto_release` (L5854-5873), section 9 L838-839, vs BRIEF "nothing restarts itself" and DECISIONS.md line 8 (L1712-1713).**
An organ's only cell, quarantined after 8 consecutive failed items, is put back to work automatically after 24 h at the
top rung; DECISIONS line 8 lists the dashboard, re-arming and run resubmission only, so arming does not accept this
self-restart. Fix: add to DECISIONS line 8 "a quarantined last cell of an organ is released automatically after 86400 s,
at most once per 604800 s (auto_release)", or delete auto_release and leave release to `life-ctl.py release-cell`.

**13. MEDIUM [D] DECISIONS.md (L1683-1741) omits three safety decisions the kit makes elsewhere: GAP 15 (candidate code can send UDP, L1539-1541), GAP 16 (chmod of STATE paths, L1542-1544), and section 11 L924-926 (page fetching and parsing run outside the Landlock sandbox "by decision").**
bs4/pypdf parse attacker-controlled bytes as the host with HOME readable and the network open; UDP exfiltration from a
watched test or the gate is possible. Since arming = accepting DECISIONS.md, these are accepted without being written.
Fix: DECISIONS lines 21-23 with the exact risk text; split bin/life-fetch.py into `fetch` (network, writes raw bytes to the
scope's temporary folder, no parse) and `parse` (run through sandbox_argv with `--rx REPO/.venv`, no network) so only the
parser is sandboxed.

**14. MEDIUM [D] bin/life-tick.py `serve_nodes`/`refresh_available` (L4160-4178, L4488) and `launch_slot` refills (L4438-4481); section 10 L896-898.**
Temperature, high-power mode and the host inputs are read once before the slot phase; each node is refilled up to 4 times without
a re-read, and the phase lasts up to ~25 min (actions start until TICK_DEADLINE 1200 s and run up to 900 s). A worker node that
crosses HOT_C or a high-power mode lease that starts during the phase keeps receiving program runs; only the fleet runner's thermal
refusal backs this up. Fix: `self.refresh_available()` at the start of launch_slot (one status GET when the sample is older
than TELEMETRY_REFRESH), and section 10: "before EVERY slot action, when the last sample is older than 120 s".

**15. MEDIUM [D] watched-test dedup, bin/life-tick.py `findings` (L4965-4977); section 7.4 L471-476.**
A finding that ended `done` (patch bundled, state bundled/ready/operator, not yet applied) does not block the next finding;
LIFE never applies, so the test keeps failing and every later run (6 h, 12 h, 24 h, then 48 h) creates a new finding and a
new agy run producing the same diff → `patch_repeat` → operator. One cloud agent run per cycle is wasted per failing test.
Fix: add "and NOT (the previous finding ended done and a patch of it is in state bundled, ready or operator with the same
fingerprint)"; code: `patches WHERE item_id=prev AND state IN ('bundled','ready','owner')`.

**16. MEDIUM [D] bin/life-tick.py `workspace_sweep` clone source (L5886-5891) and `git_meta_broken` (L4871-4878); README L21 "seeding is never a recovery step".**
For selfdev/database the only clone sources are a sibling workspace or `PROJECTS/life-<organ>-0-00000000`. After
git_meta_broken deleted the seed workspace and no sibling has one, every re-creation fails, the last cell is quarantined,
and release-cell/revive loop through the same failure with no documented recovery. Fix: when no source exists,
make_workspace builds the workspace as seed_workspace does (symblic-task workspace; selfdev: genome/ and genome-base/ from
the active release; database: migrations/.keep, schema-snapshot.sql, MIGRATION-RULES.txt; commit); say so in section 7.9.

**17. MEDIUM [D] BRIEF.md L16-17 ("research lanes must avoid duplicate sources") and L30-31 (dedup "keyed by DOI/URL/text") vs bin/life-tick.py `source_key` (L6736-6746) and section 7.2 L404-406.**
Dedup is by `items_key(url)` only: the same paper via doi.org, the publisher URL, http/https or trailing-slash variants or
a mirror is a new source, a new fetch, a new digest and a duplicate knowledge row (fact_id includes source_key). Fix:
`source_key = 'doi:' + lower(DOI)` when the URL or the fetched text carries `10\.\d{4,9}/[^\s"<>]+`, else items_key of the
URL with scheme/host lower-cased, default port and trailing slash removed, fragment dropped; at fetch, an identical
`text_sha256` links the existing source (question_sources) instead of storing a second snapshot.

**18. MEDIUM [D] Missing path vs BRIEF "optimizes the codebase": section 2 L117-121, GAP 12 (L1531-1533), DECISIONS 12.**
No autonomous route exists from a passed experiment to a code change; the compute organ only times operator templates. The
brief states the requirement; DECISIONS accepts the gap but README's opening does not say so. Fix: README paragraph 1:
"'optimises the codebase' means: reports passed benchmark experiments; code changes come only from failing tests"; or the
smallest closure: change class `perf_fix` admitted only for a finding the operator creates from an `experiment_passed` notice
(`life-ctl.py command "perf: EXPERIMENT_ID tests.test_x"`), gated like local_fix.

**19. MEDIUM [D] Missing path vs BRIEF "fixes errors": section 7.4 L448 and L476 ("LIFE never reads the dashboard's logs"), DECISIONS 13.**
Error intake is only control/watch.txt and commands naming a test; a runtime error with no failing test is never seen.
Fix: README step 4: "LIFE fixes only failing tests you list or name"; or add the code-only intake `life-ctl.py error
"TRACEBACK TEXT" --test tests.test_x` that creates a confirm-stage finding with the text as finding_text.

**20. MEDIUM [D] Missing path vs BRIEF "creates databases ... new ways to store data": section 7.8 L673-678 (store adapter), GAP 13 (L1534-1535), DECISIONS 16.**
Rows reach organism.sqlite3 only for tables shaped (fact_id, source_url, claim, quote, created_at); any other table a
`database:` request creates stays empty unless the operator fills it, so the organ produces schema without data and the operator
is not told. Fix: `migration_applied` notice text adds "this table receives rows from LIFE: yes/no (store adapter shape)";
define the next adapter (operator-approved column mapping in `control/adapters.json`) as the closure.

**21. MEDIUM [D] bin/life-tick.py `child_node` (L5985-6000), `dispatch` (L5784-5800), `model_for`/`model_absent` (L6215-6219); PROTOCOL rule 11.**
Child b of a model organ may be born on a worker node that has none of the organ's ladder models installed (rule 11 checks
availability and cell counts only); dispatch keeps giving it items by focus words, every slot skips them with notice
`model_absent`, the cell never idles (so no apoptosis) and never divides; only `life-ctl.py move` ends it. Fix: for model
organs, rule 11 adds "and the top-rung model of every program the organ runs is installed there (meta.models)";
dispatch skips cells whose node lacks every rung of the item's program.

**22. LOW [U] spawn/PROTOCOL.md rule 4 ("12 for model organs, 6 for agent organs"), section 1 L66, vs organs/organs.json.**
immune and compute are model organs with divide_backlog 6. Fix text: "divide_backlog is organs.json's value: command,
learning, digest 12; codebase, immune, selfdev, compute, database 6".

**23. LOW [U] "a division step takes its parent node's slot at most every 2nd armed tick" (PROTOCOL stages 1-2, section 9 L829) vs `plan_slot` L6186 using `tick_no`, which observe-only ticks also increment.**
Fix: write "every 2nd tick (observe-only ticks count)" or keep `meta.working_tick_no` (incremented only on admitted working
ticks) and compare `last_step_tick` with it.

**24. LOW [U] section 7.2 L407 "every source is linked to the question" vs `on_local_research` L6761-6774.**
Once the run's quota of new usable links is reached, the remaining sources are neither recorded nor linked. Fix text:
"sources are taken in hit order until the quota of new usable links (min(3, 9 − found)) is reached; the rest are ignored
for this run".

**25. LOW [U] three lists for "items that stay with a cell's workspace": `workspace_busy` and `division_commit` use (gate, apply, confirm) (L3941, L6132-6133); `dispatch` and `retire` use (gate, apply) (L5789, L2990); `WORKSPACE_STAGES` (L7303), `HOST_STAGES` (L7301) and `MODEL_ORGANS` (L7281) are defined and never used.**
Fix: one constant `WORKSPACE_STAGES = ('gate', 'apply')` used in all four places (a confirm item needs any idle active
clone, section 7.4, so it moves like other items); delete the unused constants or use them.

**26. LOW [U] STATE/operator/status.json `disposition` (section 14 L1220) is always `'finished'` (L7177), also after a fault, STOP, hold or SIGTERM.**
Fix: `disposition` ∈ {done, observe_only, stop, hold, fault, killed}, derived from the exit path, and listed in section 14.

**27. LOW [U] section 4 L223-224 ("1 a tick fault ... a tick_fault notice") and README L103 vs `on_term` (L7137-7140): a systemd stop or TimeoutStartSec also exits 1 with no notice and no fault count.**
Fix: exit 4 for SIGTERM, add 4 to SuccessExitStatus, text "4 ended by SIGTERM (systemd stop or TimeoutStartSec); not a fault".

**28. LOW [U] agenda (`agenda` L4603-4610; README L48-51): an entry fires at the first armed working tick after it is added or edited (its current period has no record), not after every_hours.**
Fix README text: "an entry fires once in every period of every_hours counted from the Unix epoch, including the period in
which it is added or edited".

**29. LOW [U] minimum command length differs: inbox and `life-ctl command` accept 1 byte (L4543-4545, L3148); agenda needs 10 bytes (L4594).**
Fix: `COMMAND_MIN_BYTES = 10` in life_common, used by both.

**30. LOW [D] `on_classify_command` L6699-6701: a `database:` request shorter than 10 characters gets notice `command_too_long` ("at most 600 characters").**
Fix: notice `command_too_long` only when `len(req) > REQUEST_MAX_CHARS`; otherwise `command_database_confirm` with
"the request after database: is 10..600 characters".

**31. LOW [U] organs/codebase.lines.txt line 1 "changing only function bodies inside the file(s) ..." vs the gate rule `local_fix_problems` (L8453-8479).**
The agent is not told: no new import, no signature, default, decorator, class or module-level change, at most 3 functions,
each named in the traceback, no new file. Fix (scope text for local_fix): "only the bodies of the functions {functions}
inside the file(s) {files}, at most three functions, adding no import and no file, and changing no signature, default
value, decorator, class line or module-level line" (render `functions` from trace_functions; add it to PLACEHOLDERS).

**32. LOW [U] organs/selfdev.lines.txt line 1 "the quoted instruction text that ends its ask lines".**
The instruction is followed by `from ... with ...`, so it does not end the line. Fix text: "only the double-quoted
instruction that stands immediately before the word from on an ask line".

**33. LOW [U] MIGRATION_RULES rule 3 (L8555-8556: every column name lower-case) vs MIGRATION_RX (L8534-8537: only ADD COLUMN names checked).**
`CREATE TABLE IF NOT EXISTS org_x (Title TEXT, Doi TEXT);` passes (demonstrated); a later `ADD COLUMN title` is then a
new name. Fix: for CREATE TABLE split the definition on top-level commas and require each to match
`^[a-z0-9_]{1,40} [A-Z]+(?: [^,]*)?$|^(PRIMARY KEY|UNIQUE|CHECK|FOREIGN KEY) `, or relax rule 3 to ADD COLUMN only.

**34. LOW [D] genome/distill-lesson.sym line 17: `ask program: one of {..., review-patch, ...}` offers the protected program; code drops the answer (L6813) and the lesson is lost.**
Fix: remove `review-patch` from the enum; VALIDATE: no enum of a selfdev-targeting ask names a SELFDEV_PROTECTED program.

**35. LOW [D] STOP during the slot phase: the watcher kills `bin/symblic run` (rc −15) → `run_program` returns `infra` ("no JSON report") → `record` holds the node 1800 s and adds an infra outcome (L6585-6591); `stop_everything` then re-queues the item.**
Six STOPs end an item `owner` with notice `infra_repeat`. Fix: in record(): `if self.stopping(): self.item_update(...,
state='queued', outcome='stopped'); return` before any counting.

**36. LOW [D] `highpower_reasons` L4071-4075: `sm.get('restUntil') == 0` is True for the boolean False, and an integer-valued float passes, while section 10 says "integer Unix seconds".**
Fix: `rest = sm.get('restUntil'); if type(rest) is not int or rest < 0: out.append('high-power mode restUntil is not integer
Unix seconds') elif rest > self.now: ...`.

**37. LOW [D] bin/life-ctl.py `apply_patch` L2755-2766 compares `git show BASE:path` (decoded with errors='replace', cut at OUTPUT_KEEP_BYTES 1 MiB) with the live file (surrogateescape).**
A non-UTF-8 or > 1 MiB file is always "moved" and apply refuses without --moved-base. Fix: compare blob ids:
`git rev-parse BASE:path` vs `git hash-object -- path`.

**38. LOW [U] `apply_patch` L2735-2738 refuses while an apply record exists; after `revert` the record stays (state reverted), so a reverted patch can never be applied again and nothing says so.**
Fix: define "a reverted patch is final; requeue the finding for a new patch", or move the journal to
`STATE/applied/<id>/history-<utc>.json` on revert.

**39. LOW [D] `GATE_DENY_RX` L8338-8346: `\.env` and `secrets_data/` are anchored at the root only; `config/.env` and `app/secrets_data/x` are not denied (demonstrated).**
Fix: `(^|/)\.env[^/]*$` and `(^|/)secrets_data/`.

**40. LOW [D] `SECRET_RX` L7610-7614: the leading `(?i)` makes `AKIA…`, `ghp_`, `sk-`, `BEGIN … PRIVATE KEY` case-insensitive; a lower-case akia prefix with 16 alphanumerics, or the lower-case words begin … private key, in prose are
credentials (demonstrated).**
Fix: scope `(?i:...)` to the keyword and bearer alternatives only; keep the token prefixes case-sensitive.

**41. LOW [U] section 8 L788-793 and OLLAMA_LIMITS (L7331): 12 calls × timeout_seconds 240 = 2880 s cannot fit CALL_TIMEOUT 900 s; a slow but valid run ends as `timeout` (escalation, then infra at the top rung).**
Fix: `timeout_seconds = CALL_TIMEOUT // CALL_MAX_MODEL_CALLS` (75) or CALL_TIMEOUT 2880; write the derivation in the
limits comment and add a VALIDATE bound `CALL_MAX_MODEL_CALLS * OLLAMA_LIMITS['timeout_seconds'] <= CALL_TIMEOUT`.

**42. LOW [U] `owned_jobs` docstring L4366-4369 ("absence from these pages is never taken as proof that a job does not exist") vs `poll_benches` L4418-4423 (absence past timeout + 300 s is `job_lost`: operator, node held).**
Fix docstring: "absence within timeout + BENCH_GRACE is not proof; past it the job is treated as lost".

**43. LOW [D] `watch_stop` thread L7131-7135 runs `systemctl --user stop life-*.scope` (60 s timeout) every second while STOP exists.**
Fix: stop scopes once, then only while `procs.live` is non-empty.

**44. LOW [U] routing label of a finding: `label` L5776 takes the text before the first `.`, its docstring L5768 says "first line", section 9 L847-848 says "first sentence"; a traceback `File "x.py"` ends the "sentence" at `x`.**
Fix: define "the test id and the finding_text up to its first `: ` or 80 characters, whichever is shorter".

**45. LOW [U] a research answer is cut to 8000 characters in bin/life-research.py (L3569) and to ANSWER_CHARS 4000 in the tick (L6754).**
Fix: `[:L.ANSWER_CHARS]` in the wrapper; one number.

**46. LOW [U] derived questions (`self_questions` L5968-5969, origin = fact_id) and everything they produce descend from no command, so no report ever shows them; section 7.2 L413-416 does not say where their results are seen.**
Fix text: "derived questions have no report; their answers are in table answers, their claims in knowledge
(life-status.py shows the counts)".

**47. LOW [U] commands routed heartbeat, immune or none end in state `owner` (L6733) and never get `command_done` or a report; section 7.1 L375-377 says only "notice ... for the operator".**
Fix text in the route table: "the command ends in state owner; the notice is its only output; no report is written".

**48. LOW [D] `scope_argv` TasksMax = SCOPE_TASKS_MAX 64 (L9144) for the gate scope: `./bin/devcheck` runs ruff and ast-grep, each with one worker thread per CPU; with bash, python, timeout, prlimit, the launcher and git, a many-core the host exceeds 64 tasks and devcheck fails spuriously (gate exit 4, finding failed).**
Fix: `SCOPE_TASKS_MAX = 64 + 4 * os.cpu_count()`, or `RAYON_NUM_THREADS=4` in devcheck_tools' env.

**49. LOW [D] `duty_allows` L4216 mixes `self.now` (tick start) and `L.now()`: the window is [tick start − 3600, now], up to 1500 s longer than NODE_WINDOW late in a tick (over-counting busy time).**
Fix: `t1 = L.now(); return self.busy_seconds(node, t1 - L.NODE_WINDOW, t1) + budget <= L.NODE_BUSY_MAX`.

**50. LOW [U] `ENV_ERROR_RX` L3777-3778 is searched over the whole 40-line tail (L4912-4914): a genuine failure whose traceback mentions ImportError or PermissionError anywhere (an assertion about them) is never a finding.**
Fix: apply ENV_ERROR_RX to the LAST exception line only (the class failure_fingerprint found) and to rc 127/125.

**51. LOW [U] section 7.9 L687-688 "statement 0 can use 3 [agents], leaving statement 1 at least 1" assumes how autogen splits agents_max over statements; no CONTRACT row pins it.**
Fix: pin the split rule in CONTRACT (symblicos/autogen.py) or delete the sentence.

**52. LOW [U] section 7.7 L586-587 and benchmarks.example.json descriptions: LIFE_RESULT must appear within the first BENCH_OUT_BYTES 4096 bytes of a run's output (`head -c`, L6976) and exactly once; neither limit is stated where the operator writes templates.**
Fix text: "cmd prints at most 4096 bytes and exactly one LIFE_RESULT line within them; more output or a second LIFE_RESULT
line fails the experiment".

**53. LOW [U] `fetch_one` L5123-5126 abstains a whole page when `has_secret` matches; tutorial pages holding `<kw>: 12345678` (<kw> a key word such as password) lose every claim.**
Fix: store `L.redact(text)` (the quote check runs on the redacted snapshot) and record `redacted=1` in the source row.

**54. LOW [D] `inputs_for('rank-experiment')` L6369-6374: when the benchmark left control/benchmarks.json the model is asked about a benchmark with an empty description and timeout 0; `start_bench` then fails the item.**
Fix: in plan_slot, a rank or bench item whose benchmark id is not in benchmarks() ends `failed` ("benchmark left the
catalogue") without a model call.

**55. LOW [U] `#!/usr/bin/env python3` in bin/life-ctl.py, bin/life-status.py, bin/life-check.py (L2175, L2340, L3610) writes bin/__pycache__/*.pyc when run as README shows (`$B/life-ctl.py …`); `kit_sha256` (L7668-7673) hashes __pycache__ on purpose.**
A .pyc written or rewritten after arm (first `life-status.py` after a Python minor upgrade, a stale-mtime rewrite) is an
integrity hold. Fix: `import sys; sys.dont_write_bytecode = True` as the first statement of every entry point, before
`import life_common`; or exclude `__pycache__` from kit_sha256 and say so in section 11.

**56. LOW [D] `descendants` (L4772) and `write_report` (L4811-4837) build `IN (?,?,…)` lists of up to REPORT_TRAVERSE_MAX 5000 ids; SQLite's variable limit is 999 before 3.32 and `sqlite3.sqlite_version` is not pinned.**
Fix: chunk the lists at 500 ids per statement, or add the contract row `sqlite3.sqlite_version_info >= (3, 32)` to
contract_problems.

**57. LOW [U] PREMIGRATION_KEEP 10 × ORGANISM_MAX_BYTES 1 GiB = STATE_MAX_BYTES 10 GiB (L7462, L7472, L7478): ten pre-migration copies of a full organism alone trigger the storage hold.**
Fix: `PREMIGRATION_KEEP_BYTES = 2 GiB` (keep the newest copies within it) or ORGANISM_MAX_BYTES 512 MiB; write the
relation in the limits comments.

**58. LOW [U] BRIEF.md L24-26 requires statement verbs from `symblic_autogen.VERBS`; the templates start with Fix, Run, Create, Read, Update; no CONTRACT row pins VERBS, so only lint (VALIDATE check 4, itself unpinned) guards it.**
Fix: CONTRACT row `('symblic_autogen.py', r"^VERBS\b.*", 'statement verbs')` plus a check-11 case that each template's
first word is in `symblic_autogen.VERBS`.

**59. LOW [U] VALIDATE check 8 validates templates only through bench_problems; the three nested shell quotings of `start_bench` (L6973-6978) through the map route's `shlex.quote(cmd.replace('{{item}}', '"$1"'))` are never executed.**
(Run here locally: the LIFE_RUN/LIFE_RESULT/LIFE_END framing is correct for items `2:7`, `3:a:b`, `4:x'y`.) Fix: VALIDATE
check 8b runs the generated wrapper with `sh -c` on `printf` as the operator command and asserts the framing and the
`head -c` cut.

**60. LOW [U] checks/devcheck-gate.sh step 2 ("this judge is the base commit's own bytes, never the patch's") relies on bin/ and scripts/ being denied; the judge's configuration inputs at the clone root (ruff.toml, .ruff.toml, any file scripts/devcheck.py opens) are not all denied (`ruff.toml` denied=False, demonstrated).**
Fix: add `ruff\.toml$|\.ruff\.toml$` to GATE_DENY_RX and pin in CONTRACT the config files devcheck/ruff/ast-grep read.

**61. LOW [U] `apply_migration` L5374-5377: a migration refused at validation is reset away with the workspace and only 400 characters of the reason survive in migrations.detail; "refused ids are never reused", so the text is lost.**
Fix: write `STATE/bundles/migrations/<id>.sql` and `<id>.refused.txt` (full problem list) BEFORE validation; state it in
section 7.8.

**62. LOW [U] units/life-tick.service MemoryMax=1G and the TICK_TASKS_MAX comment: `refresh_clone`'s `git fetch`/`git reset` of the codebase clone and `bin/symblic-task` run inside the tick's own cgroup (L5015-5018, no scope).**
A fetch of host-checkout's history can exceed 1G and OOM-kill the tick (a signal exit, not in SuccessExitStatus).
Fix: run refresh_clone's fetch through scope_argv like clones (life-fetchgit-*.scope, MemoryMax 2G), or raise MemoryMax
and list which processes share it.

**63. LOW [U] README step 2 / bin/life-seed.sh: "a seed that stopped halfway is finished by running it again", but `seed` (L2612-2614) refuses after any kit change ("remove ~/.local/state/life by hand") and neither text says a half-seed also leaves three `life-*-0-00000000` folders under PROJECTS.**
Fix text: "to start over, remove ~/.local/state/life AND /home/operator/symblicos/projects/life-{codebase,selfdev,database}-0-00000000".

**64. LOW [U] organ efficiency (section 9, EFFICIENCY_FLOOR, `efficiency_ok` L5976-5983) counts abstained items as output: a digest cell that abstains on every source (abstain_rate notice) still divides.**
Fix: define efficiency as items_done / cost, or state in section 9 that abstentions count as useful work on purpose.

**65. LOW [U] `refresh_available` (L4166-4171) empties the available list on a new hold reason but `self.holds` and the governor row are not updated, so status.json and `held` counting say `governor work` for a tick whose slot phase refused everything.**
Fix: append the reasons to `self.holds` and rewrite the governor row's `reasons` in refresh_available.

**66. LOW [U] BRIEF.md L40-41 names docs/fleet-power.md as the capacity/heat source; the kit pins HOT_C/COOL_C to symblic_apply only (CONTRACT) and never reads fleet-power.md.**
Fix: a CONTRACT row on the thresholds stated in docs/fleet-power.md, or a sentence in section 10 that symblic_apply's
constants are authoritative and fleet-power.md is informative.

**67. LOW [U] README step 3 recommends `gate-selftest tests.test_symblic_autogen`: it runs under `/usr/bin/python3 -s -B` with no .venv; if that module needs a .venv dependency the self-test ends with exit 5 and the README offers no alternative.**
Fix text: "any test that passes with `/usr/bin/python3 -s -B -m unittest ID` inside the clone; `tests.test_symblic_autogen`
is the default suggestion".

**68. LOW [U] `findings` (L4924-4927): a control/watch.txt that exists but fails read_owner_file's rules (wrong operator, a symlink, over 16 KiB) is silently ignored (no notice), unlike agenda.json (`agenda_invalid`).**
Fix: notice kind `watch_invalid` (subject `watch.txt`) with the OSError text; add it to NOTICE_KINDS and section 14.

**69. LOW [U] `model_installed` (L6752-6754): a node absent from the daily inventory counts as having every model; a worker node offline at inventory time is then given every rung for up to 86400 s, each answer an infra outcome (node held 1800 s, operator at 6).**
Fix: re-read the inventory when a node answers an infra outcome whose text matches `not installed`, or treat an absent
node as "no model known" and open `model_absent` instead; write the chosen rule in section 8.

**70. LOW [U] BRIEF.md "extremely lightweight models" and "the host only orchestrates" are widened by DECISIONS 11 (agent organs run the operator's cloud agy login) and DECISIONS 9 (gates, watched tests, fetch parsing, migration validation and backups run on the host), but README.md's opening paragraph does not repeat either, so the operator meets them only inside DECISIONS.md.**
Fix: README paragraph 2 adds "the three agent organs use the operator's cloud agy login (12 runs a day); the host runs the
gates, watched tests and fetches in bounded scopes".

FINDINGS_TOTAL=70
UNDEFINED_DETAILS=38
VERDICT=CHANGES NEEDED

Review artifacts: [local results path and commit id removed for publication; kept privately by the operator]
