# LIFE v1 review, round 1 (task life-review-r1-20261011)

Mode: review only. Nothing in `docs/life` was changed, executed, started or deployed.
The report below is the deliverable. The two integers and the verdict the task asks for are the
last three lines of this file.

## 1. What was reviewed and how

- A source-only snapshot branch and commit made for this task [branch name and commit id removed for publication].
- All 36 files listed in `.cloud-agent/task.json` were hashed; every SHA-256 matches task.json.
  The bundle-level SHA-256 (`c9e827e4…`) is not derivable from the files alone with any obvious
  scheme (sorted hash list, path+hash lines, JSON map, concatenated contents were tried); the
  per-file hashes are the verification relied on.
- Every file was read in full: `LIFE.md` (1363 lines), `BRIEF.md`, `README.md`, `VALIDATE.sh`,
  `checks/*.sh` (4), `genome/*.sym` (6), `organs/*.lines.txt` (10), `policies/*.json` (10),
  `spawn/PROTOCOL.md`, `workshop/round-1/sources/schema.sql.txt` (the `db/schema.sql` copy).
- `bin/life-spawn-tick.py`, `bin/life-status.py`, `bin/life-seed.sh` and `spawn/example/*` are not
  in the bundle as files; they were reviewed from their verbatim copies in LIFE.md Appendices F
  and G (line numbers below refer to LIFE.md for those).
- The appendix copies of every file that *is* in the bundle were compared byte-for-byte with the
  standalone files: all identical (see §3). So there is one text, not two drifting ones.
- No kit script was run. Four parsing expressions copied out of the scripts were exercised on
  synthetic input in a scratch folder to confirm their behaviour (§3). No model, agent, network
  call or cluster job was involved.

Finding classes used below (one per finding, counted at the end):
`[undefined]` a detail two agents could read two ways; `[contradiction]` conflicts with BRIEF.md or
with another part of the kit; `[unsafe]` unbounded or damaging behaviour; `[missing]` an organ or
path the brief requires that the kit does not provide.

## 2. Changes made

- Added `.cloud-agent/STATUS.json` and this `.cloud-agent/RESULT.md`. No other file changed.

## 3. Reproductions executed (scratch folder, no kit file executed)

Hash verification of the bundle (Python, stdlib only):

```
$ python3 -I - <<'EOF'   # loops over task.json "files", sha256 each path
OK docs/life/BRIEF.md
... (36 lines, all OK)
ALL FILE HASHES OK
EOF
```

Appendix-vs-file drift check (extracts every "### path" fenced block from LIFE.md and diffs it
against the file on disk):

```
SAME   VALIDATE.sh
APPENDIX-ONLY (not in bundle) bin/life-seed.sh  [60 lines]
APPENDIX-ONLY (not in bundle) bin/life-spawn-tick.py  [180 lines]
APPENDIX-ONLY (not in bundle) bin/life-status.py  [36 lines]
SAME   checks/devcheck-gate.sh ... SAME   policies/selfdev.json   (28 files SAME)
APPENDIX-ONLY (not in bundle) spawn/example/{lineage.json,policy.json,reason.txt,statements.txt}
appendix blocks found: 39
```

`checks/heat-gate.sh` line 8 (the io-pressure awk) on synthetic `/proc/pressure/io` text:

```
$ awk -F'=' '/full/{split($0,a," "); for(i in a) if(a[i] ~ /avg10/){split(a[i],b,"="); print b[2]}}' psi_full.txt
41.50                                  # parses correctly when a "full" line exists
$ io="$(awk ... psi_nofull.txt 2>/dev/null || echo 0)"; echo "'${io}' -> gate uses '${io:-0}'"
'' -> gate uses '0'                     # no "full" line: io silently becomes 0 (ALLOW side)
$ io="$(awk '/full/{print}' /nonexistent/pressure/io 2>/dev/null || echo 0)"
'0'                                     # file missing: io becomes 0 (ALLOW side)
```

`bin/life-spawn-tick.py` line 997 cell_id regex vs. the kit's own examples:

```
'learning.3.a1b2c3d4' True   'learning.2.00000000' True   'life-learning' False
'learning.3.A1B2C3D4' False  'learning-c1.3.a1b2c3d4' False
VALIDATE lineage rule (count(".")==2, 0<=depth<=64) accepts depth 63: True
```

Shell facts used by findings 68 and 82:

```
$ cp --version | head -1 ; cp -n a.txt b.txt; echo rc=$?
cp (GNU coreutils) 9.4
cp: warning: behavior of -n is non-portable and may change in future; use --update=none instead
rc=0
$ for f in /nonexistent/bin/*.sh; do echo "loop var='$f'"; done ; bash -n /nonexistent/bin/*.sh; echo rc=$?
loop var='/nonexistent/bin/*.sh'
bash: /nonexistent/bin/*.sh: No such file or directory
rc=127
```

Git modes in the bundle: `VALIDATE.sh` and `checks/*.sh` are 100755; everything else 100644.

## 4. Findings

Ordered by theme, not by severity. Every finding gives the location, the exact defect and the text
to adopt.

### A. Workspace, cwd and lane placement

### 1. [HIGH] [contradiction] All lanes share one cwd, so ten organs write one verify.txt
- Location: LIFE.md App. F `life-seed.sh` `start()` line 1110–1111 (`--root "$ROOT" --cwd "$ROOT"`);
  `life-spawn-tick.py` line 1006 (same for children); every `organs/*.lines.txt` ("to the file
  verify.txt", relative); LIFE.md §2 line 57–58 ("Each organ writes into its own organ-<name>/").
- Defect: with cwd = ROOT for every run, all ten lanes (and every child) write and overwrite
  `ROOT/verify.txt`; the check `test -s verify.txt` passes on another organ's file; `require_change`
  is satisfied by another organ's write; `bin/life-status.py` (line 1059) and the heartbeat look
  for `organ-<organ>/verify.txt`, which no lane writes. §2's statement is false as seeded.
- Adopt: in `life-seed.sh` `start()`: `--root "$ROOT" --cwd "$ROOT/organ-$organ"`; in the tick:
  `'--cwd', os.path.join(ROOT, f'organ-{organ}', 'cells', cell_id.split(".")[-1])`. Add to §2:
  "A lane's `verify.txt`, `AUTOGEN-CHECKPOINT.json`, `AUTOGEN-INDEX.jsonl`, `HANDOFF.md` and
  `AUTOGEN-SPLIT.txt` are always `<cwd>/<name>`; cwd is `ROOT/organ-<organ>` for a seed and
  `ROOT/organ-<organ>/cells/<8hex>` for a child." Seed must `mkdir -p` the cwd before `start`.

### 2. [HIGH] [undefined] Where the engine keeps checkpoint, index and handoff files is unstated
- Location: LIFE.md §2 lines 57–58; BRIEF.md line 29–31 (names the files, not their folder).
- Defect: if these live in the attempt cwd, finding 1 means ten lanes share one checkpoint
  (`{done,left,files,items}`) and one dedup index: the learning organ's DOI index and the digest's
  text index merge, and one lane's checkpoint overwrites another's. If they live in the run record
  on the host, §2's "keeps its own AUTOGEN-INDEX.jsonl" is true but `--cwd` is irrelevant to it.
- Adopt: one sentence in §2 citing the code: "The engine writes `AUTOGEN-*.json(l)` into the
  attempt cwd (symblicos/autogen.py:<line>); therefore cwd is per organ (finding 1)."

### 3. [HIGH] [undefined] What an "item" is for saturation is defined for no organ
- Location: LIFE.md §2 table column "Kind" ("sat 4", "sat 3", "sat 6"); policies codebase/learning/
  digest/selfdev/compute/immune (`"saturation"`); BRIEF.md line 30 (index keyed by DOI/URL/text).
- Defect: saturation stops a perpetual lane after N generations with zero new index keys. The kit
  never says which output file or key the engine indexes for each organ. For codebase, selfdev,
  compute and immune no DOI/URL/text item is produced at all, so those lanes can stop after 4–6
  generations (6–12 hours) and nothing restarts them.
- Adopt: a table in §2: "Item key per organ (what the engine indexes; declared via <policy field or
  statement phrase, cite autogen.py>): command `text:<sha256[:16] of command text>` per routed
  line; codebase `text:<finding_id>`; learning `doi:`/`url:` per source line; digest
  `text:<source_id>`; selfdev `text:<proposal_id>`; compute `text:<experiment_id>`; immune
  `text:<patch_id>`; metabolism, heartbeat: saturation disabled." Then set the mechanism that
  makes the engine read that key (file name or statement wording), or set `saturation` to the
  disabled value for every organ that cannot produce keys.

### 4. [HIGH] [undefined] `saturation: 0` meaning, and the seed omits it
- Location: policies/command.json line 10, metabolism.json line 10, heartbeat.json line 10
  (`"saturation": 0`); `life-seed.sh` lines 1115, 1121, 1123 (no `--saturation`).
- Defect: 0 can mean "disabled" or "stop after zero stale generations" (immediate stop). The seed
  passes no `--saturation` for these three lanes, so the server default applies, which may differ
  from 0 (policy and seed already disagree).
- Adopt: verify `symblic_autogen.DEFAULTS['saturation']` and `normalize`'s treatment of 0; write
  in §2: "`saturation: 0` = never stop on saturation (autogen.py:<line>)". Add `--saturation 0` to
  the three seed lines, or generate every seed flag from the policy file (finding 79).

### 5. [HIGH] [undefined] `wall_seconds` on a perpetual lane: per generation or per run?
- Location: every perpetual policy (`"wall_seconds"` 21600/43200/86400); LIFE.md §6 line 164–165
  ("Each organ's wall_seconds and interval_seconds build the rest in"); BRIEF.md line 17
  ("research lanes ... may run for days"); README line 46 ("Nothing restarts itself").
- Defect: if `wall_seconds` caps the run, the command inbox dies after 6 h, codebase and compute
  after 12 h, the rest after 24 h, and the organism is mortal within a day with manual re-seeding as
  the only revival. That contradicts "perpetually living" and "may run for days". If it caps one
  generation, 86400 s for one generation is meaningless next to `attempt_seconds` 3600.
- Adopt: verify in `symblicos/autogen.py` and write one sentence in §2: either "`wall_seconds` caps
  one generation's agent time; the lane has no end" (then set it to `attempt_seconds × regenerate`
  per lane), or "`wall_seconds` caps the run; a perpetual lane ends when it is reached" (then set
  the platform's unlimited value for the ten seeds, keep caps for children only, and add to README
  the exact revival command per organ).

### 6. [HIGH] [undefined] `agents_max` per generation or per run
- Location: policies (`agents_max` 8–24); LIFE.md §2 table (not mentioned).
- Defect: if per run, learning (24) ends after 24 agents, i.e. 12 h at one agent per generation,
  metabolism after 8 generations = 40 min. Same consequence as finding 5.
- Adopt: same verification; one sentence: "`agents_max` bounds agents per generation (autogen.py:
  <line>)"; if per run, set unlimited for seeds.

### 7. [MEDIUM] [undefined] `interval_seconds` is measured from an undefined point
- Location: policies codebase (3600/1800), immune (3600/1800), learning (3600/1800), command
  (600/120), digest (3600/900) where `attempt_seconds` > `interval_seconds`; LIFE.md §6 line 164.
- Defect: if the interval runs from generation start, the next generation is due while the previous
  attempt may still be running; whether the engine skips, queues or overlaps (two agy agents and two
  model calls on one node) is unstated.
- Adopt: "The interval is counted from the end of the previous generation (autogen.py:<line>); a
  generation never overlaps its predecessor." If the code counts from the start, set
  `interval_seconds >= attempt_seconds` on every lane.

### 8. [HIGH] [contradiction] node-i carries four perpetual lanes; the heat rule cannot hold
- Location: LIFE.md §2 table rows 2, 5, 6, 8 (node-i), rows 1, 4 (node-f); §6 line 171–172 ("one
  perpetual model lane per worker node"); BRIEF.md line 19 (continuous all-worker node load under about an hour).
- Defect: worst-case duty per lane = attempt/(attempt+interval): node-i codebase 0.67 + selfdev
  0.50 + compute 0.50 + immune 0.67 = 2.33 lanes busy on average, plus compute benchmarks and three
  model pins; node-f command 600/720 = 0.83 + digest 3600/4500 = 0.80 = 1.63. Load on node-i and
  node-f is continuous, not "under an hour then rest". §6's own one-lane-per-worker node rule is broken.
- Adopt: a placement rule in §2: "Per worker node, Σ attempt_seconds/(attempt_seconds+interval_seconds)
  ≤ 0.5 and at most one perpetual model lane." One legal assignment, with heartbeat, metabolism
  and command moved to pure code (finding 13, 45): codebase node-i (3600/5400), compute node-h
  (benchmarks only; its three `.sym` asks pinned `@node-h`, models ≤ 2.5 GB), learning node-d
  (1800/3600), digest node-f (1800/2700), selfdev node-a (1800/7200, after the database build),
  immune node-b (1800/3600). Record the arithmetic in the table.

### 9. [MEDIUM] [contradiction] Typed decisions are pinned to light nodes that sleep
- Location: genome/classify-command.sym lines 15–17 (`@node-a`, `@node-b`); reproduce.sym lines 15,
  19, 21; triage-error.sym lines 13–14; LIFE.md §2 lines 83–86 (non-keepAwake nodes sleep between
  generations; node-f keepAwake, node-i/node-d/node-h protected).
- Defect: node-a and node-b are neither keepAwake nor protected, yet every command classification,
  error triage and reproduction verdict is pinned to them, and node-a also hosts the database lane.
  While they sleep, every pinned ask fails; whether a pinned call wakes the node is unstated.
- Adopt: pin each genome ask to the node of the lane that calls it (`@node-f` for the command
  organ's classifier, `@node-i` for triage, the orchestrator-chosen node for reproduce via `--by`),
  and state: "A `--by ollama:MODEL@node` call never wakes a node; it fails with exit <code> and the
  caller retries at the next generation."

### 10. [MEDIUM] [undefined] One-model-per-node contention is unresolved
- Location: LIFE.md §3 line 106 and §6 line 171 (the fleet runner one model per node); rank-experiment.sym
  lines 8–11 (three models on node-i); review-patch.sym lines 12–13 (two models on node-f);
  classify + triage + reproduce all `@node-a`; digest `@node-d` while the learning lane's
  local-research model also runs on node-d.
- Defect: a second model requested on a busy node is either queued (how long?), refused (counts as
  a failed ask, `retries=2` then exhausted) or swapped in (eviction cost each ask). Unstated.
- Adopt: "A model request on a node holding another model waits up to 120 s then fails (the fleet runner
  <file:line>); each genome program uses one model per node, and a lane's own node hosts its
  program's models." Rewrite rank-experiment.sym and review-patch.sym to one model each, or split
  their asks across nodes.

### B. Reachability from a worker node attempt (BRIEF: no SSH shortcuts, no worker node tunnel to :8080)

### 11. [HIGH] [contradiction] worker node lanes are told to use tools that are not reachable from a worker node
- Location: LIFE.md §3 lines 106–121 and §11.2 lines 239–244 (`bin/symblic run genome/*.sym --by
  ollama:MODEL@node-X`, `bin/local-research` over SearXNG at 127.0.0.1:18888); organs/command,
  digest, codebase, immune lines ("by running the command classifier", "the source fact extractor",
  "run each canary check", "one adversarial patch review"); BRIEF.md line 39–40.
- Defect: the attempt's working copy is a staging checkout of the `life` workspace, which contains
  none of `bin/symblic`, `bin/local-research`, `genome/`, `checks/`; `127.0.0.1:18888` is the host's
  loopback; a cross-node `@node-X` model call from node-i has no stated transport; the immune organ
  cannot run `bin/symblic-task autogen cancel` from a worker node. A fresh agent on a worker node cannot find
  "the command classifier" at all because no line names a path.
- Adopt: (a) `life-seed.sh` copies `genome/` and `checks/` into `ROOT/genome` and `ROOT/checks`
  (promoted with the workspace); every organ line names the program:
  `... by running bin/symblic run /home/operator/symblicos/projects/life/genome/classify-command.sym
  with the given values ...`; (b) one sentence in §3: "A worker node attempt reaches a model on node X
  only through <mechanism, file:line>; LIFE pins every ask to the lane's own node" (finding 9);
  (c) "bin/local-research runs on <host> where SearXNG is reachable; the learning lane calls it as
  <exact command>"; (d) cancel requests are files (finding 15).

### 12. [HIGH] [contradiction] The spawn queue lives inside the git checkout on the host
- Location: LIFE.md App. F lines 878, 887–890 (`KIT = REPO/docs/life`; `QUEUE/APPROVED/
  REJECTED/HASHES` under `KIT/spawn`); `life-seed.sh` line 1099 (`mkdir -p "$KIT/spawn/queue"`);
  tick docstring line 865 ("touches files outside the organism workspace" never).
- Defect: a reproducer running on a worker node cannot write into `/home/operator/host-checkout/docs/
  symblic/life/spawn/queue/` without SSH; the tick writes queue moves, `hashes.txt`, `REJECT.txt`
  and `RUN.txt` into the live repository working tree (untracked files in the operator's checkout),
  contradicting its own docstring and BRIEF "preserve others' work".
- Adopt: `SPAWN = os.path.join(ROOT, 'spawn')` with `QUEUE/APPROVED/REJECTED/HASHES/RETIRED` under
  it; seed creates `ROOT/spawn/{queue,approved,rejected}`; a reproducer writes
  `ROOT/spawn/queue/<name>/` as workspace files that reach ROOT by the normal commit→apply
  promotion; PROTOCOL.md "Record layout" path becomes `/home/operator/symblicos/projects/life/spawn/
  queue/<name>/`.

### 13. [HIGH] [contradiction] Two agent lanes run on the host
- Location: LIFE.md §2 table rows 7 and 9 (metabolism, heartbeat: engine agy, node the host);
  `life-seed.sh` lines 1121, 1123; BRIEF.md line 19 ("the host only orchestrates"), line 40.
- Defect: an agy attempt every 300 s is agent work on the host (288 agent sessions per lane per
  day). Which model backs agy, and whether it can load a local model on the host (the 2026-09-30
  oomd kill, LIFE.md line 118–119), is unstated. Both jobs are pure file/API reads that
  `bin/life-status.py` already does in code.
- Adopt: delete the two lanes; add `bin/life-metabolism.py` (code, reads the three endpoints,
  appends the row, computes the fan-out decision) and run it and `life-status.py --write-snapshot`
  from the same user timer as the tick. §2 table drops rows 7 and 9. If a lane is kept anyway,
  write: "agy on the host uses <model/provider> and never loads an Ollama model on the host
  (verified <file:line>)."

### 14. [MEDIUM] [undefined] Which CLI engines are logged in on which worker node is unstated
- Location: LIFE.md §3 lines 123–127 (agy→codex→claude→copilot/mistral order; `other_engine`
  rotation); BRIEF.md line 39 ("CLI logins exist on the host").
- Defect: BRIEF only establishes logins on the host. If node-i has no codex/claude login, every
  `other_engine` rotation produces an authentication failure counted as a failed generation; if it
  has, a stuck lane calls cloud CLIs every generation forever with no spend bound. The stated
  order is also not something `strategies` can express (finding 85).
- Adopt: an engine×node table verified against the hub registry (`<file:line>`), and until then
  `"strategies": ["fresh", "feedback"]` on every policy, plus a budget (finding 86).

### C. Reproduction (LIFE §1, §4, spawn/PROTOCOL.md, reproduce.sym, life-spawn-tick.py)

### 15. [HIGH] [missing] Nothing ever runs the reproducer
- Location: LIFE.md §1 lines 33–37, §4 line 133 ("A reproducer cell runs genome/reproduce.sym");
  organs/*.lines.txt (no line calls it); PROTOCOL.md line 3–7.
- Defect: no lane, statement, timer or script invokes `reproduce.sym`; its inputs (generation,
  failures_in_a_row, new_items_last_generation, lineage_depth, summary) have no named source; no
  writer of the four record files is defined; `spawn/retired.txt` has no writer; the cell's
  "second agent" does not exist in the kit. The brief's central ask is not wired.
- Adopt: a code reproducer tick on the host, `bin/life-reproduce-tick.py`, run by the same timer
  just before the spawn tick: for every live `life-*` run read `bin/symblic-task autogen get <id>
  --json` → `generation`, `failures_in_a_row` (trailing failed generations), `new_items`
  (index keys added last generation), `depth` (from `ROOT/spawn/lineage.jsonl`), `summary` (the
  last 600 chars of `<cwd>/HANDOFF.md`); run `bin/symblic run ROOT/genome/reproduce.sym --by
  ollama:qwen3:4b-instruct@<lane node> --given ...` through the hub; on `divide` write two records
  (finding 16); on `apoptosis` append `cell_id run_id epoch` to `ROOT/spawn/retired.txt` and run
  `bin/symblic-task autogen cancel <run_id>`. Cadence: once per lane generation, at most once per
  30 min per lane.

### 16. [HIGH] [undefined] A 14-word focus cannot become a lint-clean child genome
- Location: reproduce.sym lines 19–23 (child_a/child_b: "Text up to 14 words", 8..120 chars);
  PROTOCOL.md lines 21–27 (statements.txt rules); App. G example line 1214 (`organ-learning-c1`).
- Defect: the only output of a division is two short clauses, but a child `statements.txt` must be
  a 20–1500 char statement with a VERBS verb, an absolute ROOT folder, a verify line and, for
  edits, "keeping every existing part". Who writes that line, from what template, is undefined;
  the example's `organ-learning-c1` folder scheme appears nowhere else.
- Adopt: per-organ child template in PROTOCOL.md, filled by the reproducer tick (code), e.g.
  learning: `Research the question "<focus>" listed in the file ROOT/organ-learning/cells/<8hex>/
  questions.txt, find three sources with a DOI or URL that are not already in the index, append one
  JSON line per source to the file ROOT/organ-learning/sources.jsonl, and verify this batch by
  writing the three new source keys to the file verify.txt.` (ROOT spelled out). Child cwd and
  folder = `ROOT/organ-<organ>/cells/<8hex>`; the tick writes `questions.txt` there with the focus.

### 17. [MEDIUM] [undefined] cell_id "generation" vs lineage "depth"; seeds have no cell_id
- Location: PROTOCOL.md lines 38–41 (`<organ>.<generation>.<8hex>`, `depth` = parent depth + 1);
  App. G example (cell_id `learning.3.a1b2c3d4`, depth 3, parent `learning.2.00000000`);
  schema.sql.txt line 22; tick line 997.
- Defect: the example makes "generation" equal depth, but a lane's autogen generation is a
  different number; seeds started as `life-<organ>` have no cell_id or lineage row, so
  `parent_id` for a first child is undefined; how `8hex` is chosen is undefined.
- Adopt: "`cell_id = <organ>.<depth>.<8hex>`; `8hex = sha256(parent_cell_id + '|' + focus)[:8]`;
  seed cells are `<organ>.0.00000000` and are written to `ROOT/spawn/lineage.jsonl` by
  life-seed.sh." Rename the middle field to depth everywhere (schema comment line 22 too).

### 18. [HIGH] [unsafe] The budget gate depends on unverified words in `autogen list` output
- Location: tick `live_run_count()` lines 939–944; README line 59 (`awk '/life-/{print $1}'`).
- Defect: the count is the number of lines containing `life-` and `active` or `queued`. The
  listing format and state vocabulary are never stated; a nonzero exit with empty stdout, or a
  state word such as `running`/`resting`, yields 0 → gate always open → unbounded birth across
  ticks. The count is not incremented after a successful start within one tick, so one tick can
  submit every queued record while the listing lags.
- Adopt: use the machine-readable listing and fail closed:
  ```python
  def live_run_count():
      try:
          out = subprocess.run([TASK, 'autogen', 'list', '--json'], capture_output=True, text=True, timeout=60)
          if out.returncode != 0: return LIFE_MAX_RUNS
          runs = json.loads(out.stdout)
          live = [r for r in runs if r['id'].startswith('life-') and r['state'] in LIVE_STATES]
          if not live: return LIFE_MAX_RUNS   # seeds must exist; an empty count means the listing is wrong
          return len(live)
      except (OSError, ValueError, subprocess.SubprocessError, KeyError): return LIFE_MAX_RUNS
  ```
  with `LIVE_STATES = {<exact states from autogen.py:<line>>}`, and `live += 1` after each
  successful `start`. README line 59 uses the same `--json` listing.

### 19. [HIGH] [unsafe] `node` and `engine` from the record are passed through unvalidated
- Location: tick lines 1007 (`lin.get('node', 'node-i')`, `lin.get('engine', 'agy')`);
  PROTOCOL.md line 44–45 (allow-list stated in prose only).
- Defect: a record saying `"node": "host"` or `"node-arm"`, or `"engine": "claude"`, is submitted
  as written, placing a model lane on the host or the ARM node or on a cloud CLI; `organ` is not checked
  against the ten names nor against the cell_id prefix; `interval_seconds`, `wall_seconds`,
  `depth 0`, `candidates 1` required by PROTOCOL.md lines 30–33 are not enforced; a missing
  `interval_seconds` silently becomes 900 (line 909).
- Adopt: gate 5b in the tick:
  ```python
  NODES = {'node-a','node-b','node-d','node-f','node-i'}; ENGINES = {'agy'}
  ORGANS = {'command','codebase','learning','digest','selfdev','compute','immune','database'}
  if lin.get('node') not in NODES: reject(folder, f'node {lin.get("node")!r} not allowed'); continue
  if lin.get('engine') not in ENGINES: reject(...); continue
  if organ not in ORGANS or not cell_id.startswith(organ + '.'): reject(...); continue
  if spec.get('perpetual') and not (spec.get('candidates') == 1 and spec.get('depth', 0) == 0
      and 60 <= spec.get('interval_seconds', 0) and 0 < spec.get('wall_seconds', 0)
      and 'other_node' not in spec.get('strategies', [])): reject(folder, 'child policy violates PROTOCOL'); continue
  ```

### 20. [MEDIUM] [unsafe] Parent health and existence are never checked
- Location: LIFE.md §1 lines 46–48 ("a failing cell ... cannot pass the orchestrator budget");
  tick gates lines 975–1003.
- Defect: the budget gate counts runs only; nothing checks that the parent run exists, is live,
  passed its last generation, or that `depth == parent.depth + 1`. The §1 claim is false; after a
  reboot (lanes not restarted, by design) the timer keeps birthing children of dead parents.
- Adopt: gate 6b: "parent cell_id is in `ROOT/spawn/lineage.jsonl`, its run is in the live listing
  with `failures_in_a_row == 0` on the latest generation, and `depth == parent.depth + 1`; else
  reject with `parent not live/healthy`."

### 21. [MEDIUM] [undefined] Duplicate run ids, crash window and moved `--lines` path
- Location: tick lines 1005–1019.
- Defect: two records with the same `8hex` produce the same `--id`; what `symblic-task start` does
  with an existing id (error, resume, overwrite) is unstated. The hash is appended after `start`
  succeeds and the folder is moved last, so a crash between the two re-submits the same record on
  the next tick. `--lines sfile` points into `queue/<name>/`, which is moved to `approved/` right
  after submit; whether the hub re-reads that path later (regenerate, resume) is unstated.
- Adopt: order the birth as: check `run_id` not in the live listing → move the folder to
  `approved/<name>-<epoch>/` → append the hash → `start --lines <approved path>` → on failure move
  to `rejected/` and remove the hash line. State: "`symblic-task start` copies the lines file at
  submit time (`<file:line>`)" or keep the record in place.

### 22. [MEDIUM] [unsafe] The dedup brake is one character wide; no per-parent or per-node cap
- Location: tick lines 1000–1003; PROTOCOL.md line 61–62; LIFE.md §1 line 48–49.
- Defect: the hash covers statements+policy text; a reproducer that changes one character (the
  child folder name changes every time by construction) is never deduplicated. With finding 18
  broken, nothing bounds runaway division. All children default to node-i (line 1007).
- Adopt: a second key, `lineage_key = sha256(organ + '|' + parent_id + '|' + normalised focus)`,
  also recorded in `hashes.txt`; caps in the tick: `≤ 2 live children per parent`, `≤ 4 live
  cells per organ`, `≤ 1 live model lane per worker node` (finding 8), default node = reject, not node-i.

### 23. [MEDIUM] [undefined] The systemd unit has no timeout, no lingering, no success codes
- Location: LIFE.md §9 lines 199–219; README line 42–46 ("every few minutes").
- Defect: `subprocess.run(cmd)` for `start` (line 1010) has no timeout and the unit no
  `TimeoutStartSec`, so one hung submit freezes reproduction silently (the timer does not re-fire
  while the service is active). Exit 3/4 are "failed" to systemd. Without `loginctl
  enable-linger operator` user timers stop at logout. A manual run concurrent with the timer
  processes the same queue twice (no lock).
- Adopt: in the service `TimeoutStartSec=600`, `SuccessExitStatus=3 4`; in README "run
  `loginctl enable-linger operator` once"; in the tick `timeout=300` on every `subprocess.run` and
  an `fcntl.flock` on `ROOT/spawn/.tick.lock` (exit 0 with log `another tick running`). README
  says "every 5 minutes", matching the unit.

### 24. [LOW] [undefined] The `<name>` slug rule is not enforced
- Location: PROTOCOL.md line 19; tick line 966–969.
- Adopt: `if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', name): reject(folder, 'bad name')`.

### 25. [LOW] [contradiction] node-h allowed for children but avoided by LIFE
- Location: PROTOCOL.md line 44 (node list includes node-h); LIFE.md §2 lines 76–78.
- Adopt: remove node-h from the PROTOCOL list (or add it to LIFE's allowed set with the ≤2.5 GB
  model rule); finding 19's `NODES` is the single source.

### 26. [LOW] [contradiction] `kill-switch.sh` is never used, and STOP does not stop lanes
- Location: checks/kill-switch.sh lines 3–4 ("The orchestrator runs this before every spawn");
  tick line 957 (re-implements the test); README lines 54–55 ("Running lanes finish their current
  generation and then rest").
- Defect: two implementations of one gate; and perpetual lanes keep generating every interval
  while STOP exists; only `autogen cancel` stops them.
- Adopt: tick calls `checks/kill-switch.sh` (exit 3 → return 3) or delete the script; README:
  "STOP freezes births only. Lanes keep running their generations; to pause the organism cancel
  the ten runs (loop below) and revive with `autogen resume`."

### 27. [MEDIUM] [contradiction] Engine-internal splitting bypasses the spawn gates
- Location: BRIEF.md lines 31–32 (self-split, stall split, designer); policies (no `self_split`
  key; database.json `depth 1, children 4`); LIFE.md §11.3 line 247 ("worker node lanes rely on
  self-split"); §1 line 40–43 ("Reproduction is admitted only by code").
- Defect: self-split writes `AUTOGEN-SPLIT.txt` and runs more agents inside the lane with no
  lint/budget/depth/dedup gate, bounded only by `agents_max`; its default is unstated. Either
  "admitted only by code" is false or self-split must be off.
- Adopt: `"self_split": false` in all ten policies and `--no-self-split` on every seed line, with
  §1 text "the only division path is the spawn record"; or state "self-split is the sanctioned
  intra-lane division, bounded by `agents_max` = N per generation on one node" and keep
  `agents_max` ≤ 4 for every worker node lane.

### 28. [MEDIUM] [undefined] reproduce.sym asks for children even when the verdict is stay
- Location: reproduce.sym lines 19–23.
- Defect: `child_a`/`child_b` are asked unconditionally (two extra model loads per decision) and
  `ensure child_a != child_b` can force retries and fail a `stay` or `apoptosis` decision. `len()`
  on "Text up to 14 words" is compared with character bounds; which unit `len` counts is a kernel
  fact not stated. What the program returns when retries are exhausted (exit code, partial JSON)
  is not stated anywhere in the kit.
- Adopt: split into `reproduce-verdict.sym` (lines 1–18, return `{verdict}`) and
  `reproduce-children.sym` (given verdict = "divide", lines 19–25), run the second only on divide;
  add to §3: "`bin/symblic run` prints the returned record as one JSON object on stdout and exits
  0; exit 2 = an ensure failed after all retries; exit 3 = model unreachable; `len()` counts
  characters (<file:line>)."

### 29. [LOW] [undefined] Thresholds 8 and 10 are duplicated and one is env-overridable
- Location: reproduce.sym lines 17–18; tick line 881 (`LIFE_MAX_DEPTH` env default 10).
- Adopt: fix `LIFE_MAX_DEPTH = 10` as a constant (no env), and a comment in both files
  "must equal reproduce.sym line 17".

### 30. [LOW] [undefined] Lint root differs between tick and validator
- Location: tick line 980 (`A.lint(lines, ROOT)` where ROOT honours `LIFE_ROOT`); VALIDATE.sh
  lines 27, 55 (hard-coded path).
- Adopt: VALIDATE.sh uses `${LIFE_ROOT:-/home/operator/symblicos/projects/life}`.

### D. Acceptance: "code decides" (policies, checks, organ lines)

### 31. [HIGH] [contradiction] The only code decision for nine organs is "verify.txt is non-empty"
- Location: every perpetual policy `"checks": {"0": ["test -s verify.txt"]}`; LIFE.md §2 table
  column "Acceptance check"; organs/*.lines.txt verify clauses (free text: "the count", "the
  finding id and the test result", "whether the threshold passed", "the fan-out decision");
  BRIEF.md line 20 ("models propose, code decides").
- Defect: one byte passes. The content formats have no grammar, so no downstream reader (heartbeat,
  status, reproducer) can parse them, and an agent may write "PASS" without doing the work.
  `checks/verify-format.sh` exists but no policy uses it (it only checks non-emptiness anyway).
- Adopt: per-organ verify grammar and a code check. `checks/verify-format.sh <organ>` validates
  `<cwd>/verify.txt` against:
  - command: `^routed=[0-9]+ generation=[0-9]+ at=[0-9]{10}$`
  - codebase: `^finding=[a-z0-9_-]+ class=(test_only|comment_or_doc|local_fix) devcheck=(0|[1-9][0-9]*) test=(0|[1-9][0-9]*) at=[0-9]{10}$`
  - learning: `^sources=3 keys=(doi|url):[^ ]+,(doi|url):[^ ]+,(doi|url):[^ ]+ at=[0-9]{10}$`
  - digest: `^facts=[0-9]+ at=[0-9]{10}$`; selfdev: `^proposal=[a-z0-9_-]+ check=(0|[1-9][0-9]*) at=[0-9]{10}$`
  - compute: `^experiment=[a-z0-9_-]+ measured=-?[0-9.]+ threshold=(<|<=|>|>=)-?[0-9.]+ passed=(0|1) at=[0-9]{10}$`
  - immune: `^canaries=[0-9]+ failed=[0-9]+ reviews=[0-9]+ rejected=[0-9]+ quarantined=[0-9]+ at=[0-9]{10}$`
  - idle (any organ): `^idle generation=[0-9]+ at=[0-9]{10}$` (finding 33)
  and every policy uses `"checks": {"0": ["bash /home/operator/symblicos/projects/life/checks/verify-format.sh <organ>"]}`.

### 32. [MEDIUM] [contradiction] Dead check script
- Location: checks/verify-format.sh; LIFE.md App. D line 697 ("Used as the autogen check for
  perpetual organ lanes").
- Adopt: finding 31 makes it the check; otherwise delete it and the App. D claim.

### 33. [HIGH] [undefined] Idle generations are undefined and become failures
- Location: organs/command, codebase, learning, digest, selfdev, compute lines (each presumes
  input exists); `life-seed.sh` lines 1100–1101 (questions.txt and canaries.txt created empty;
  findings/, inbox/ empty; sources.jsonl, lessons.jsonl, experiments.jsonl not created); every
  policy `"require_change": true`; reproduce.sym line 18 (8 failures → cannot stay).
- Defect: with an empty inbox the command organ either invents commands or cannot "verify this
  batch"; writing the same `0` twice violates `require_change`; a failed generation increments
  failures; after eight the reproducer must divide or kill an organ that was merely idle.
  `organ-digest/sources.jsonl` does not exist at all, so the digest's first read fails.
- Adopt: in §2 and each lines file: "When the input set is empty, write `idle generation=<n>
  at=<epoch>` to verify.txt and stop; an idle generation counts as a pass, not a failure, and the
  epoch makes the file differ." Seed creates every input file the lines name:
  `organ-digest/sources.jsonl`, `organ-selfdev/lessons.jsonl`, `organ-compute/experiments.jsonl`
  (empty), and seeds `questions.txt` and `canaries.txt` with the first entries (finding 42).

### 34. [HIGH] [undefined] The permitted change classes are never listed
- Location: organs/codebase.lines.txt ("whose change class the master script permits");
  triage-error.sym line 3 ("the classes the master script permits"); LIFE.md §7 line 179–180,
  README line 70–71 ("the change classes the master script permits"); LIFE.md has no such list.
- Adopt: add to §7: "PERMITTED_CLASSES = {test_only, comment_or_doc, local_fix}. A finding
  triaged `signature_change`, `restart_gated`, `unknown`, or any class with `confident=false`, is
  written to `ROOT/organ-codebase/requests/<finding_id>.md` for the operator and never patched."

### 35. [HIGH] [undefined] The codebase organ has no defined checkout to patch or test in
- Location: organs/codebase.lines.txt ("write a proposed patch and its focused test ... run the
  focused test"); checks/devcheck-gate.sh lines 2–3, 7 ("inside its OWN checkout",
  `CHECKOUT_DIR`); BRIEF.md line 44 (preserve others' work), 42 (Python/API restart-gated).
- Defect: the worker's working copy is the `life` workspace, which contains no dashboard code; the
  only dashboard checkout a worker node could reach is unstated; on the host the obvious candidate is the
  live tree `/home/operator/host-checkout`, which must never be edited by a cell.
- Adopt: seed creates `ROOT/organ-codebase/checkout` with `git clone --depth 50 <repo origin>
  <that path>` (text only, no secrets) and the codebase line names it: `... apply the patch and run
  the focused test only inside the folder /home/operator/symblicos/projects/life/organ-codebase/
  checkout ...`; devcheck-gate.sh refuses any `CHECKOUT_DIR` equal to `/home/operator/
  host-checkout`.

### 36. [HIGH] [missing] No one performs Work→Apply, so the fixer never fixes anything
- Location: README lines 69–71; LIFE.md §7 lines 181–184 (promotion described, no operator);
  organs/codebase.lines.txt (writes patches only); organs/immune.lines.txt (records verdicts only).
- Defect: accepted patches stay in `organ-codebase/patches` forever; no organ, script or timer
  applies them to the live checkout, so "optimizes the codebase, fixes errors" has no effector.
- Adopt: `bin/life-apply-tick.py` (code, the host, operator timer, one patch per tick): for each
  `patches/<id>/` with `review.json verdict=accept` and `result.json devcheck_rc=0 test_rc=0`
  and class in PERMITTED_CLASSES, re-run `checks/devcheck-gate.sh <the host staging checkout>
  <test>` itself, then apply through the existing Work→Apply path (`<command, file:line>`),
  append `applied.jsonl` `{id, files, pre_blobs, at}`, never for `restart_gated`, never restart.

### 37. [MEDIUM] [undefined] devcheck-gate.sh hides test output and switches interpreter on failure
- Location: checks/devcheck-gate.sh line 11
  (`.venv/bin/python -m unittest "$focused" -v 2>/dev/null || python3 -m unittest "$focused" -v`).
- Defect: unittest writes its report to stderr, which the first run discards; a real test failure
  in the venv silently re-runs under system python3 (different dependencies), which may pass or
  fail for unrelated reasons.
- Adopt:
  ```bash
  if [ -x .venv/bin/python ]; then PY=.venv/bin/python; else PY=python3; fi
  "$PY" -m unittest "$focused" -v
  ```

### 38. [MEDIUM] [undefined] review-patch.sym's inputs are supplied by the party under review
- Location: review-patch.sym lines 5–7 (`change_class`, `diff_summary`, `checks_passed` are
  givens), 15; LIFE.md §7 line 178–180 ("a model accept alone never promotes").
- Defect: whoever runs the program chooses `checks_passed` and writes the prose `diff_summary`;
  the "second agent" can be told `true` and a flattering summary. Code that independently computes
  `checks_passed` is not defined (finding 36 defines it).
- Adopt: "`checks_passed` is read by the immune lane's code from `patches/<id>/result.json`
  (devcheck_rc == 0 and test_rc == 0); `diff_summary` is the first 2000 characters of
  `patches/<id>/patch.diff`, never prose."

### 39. [MEDIUM] [undefined] The patch record layout is undefined
- Location: organs/codebase.lines.txt ("write a proposed patch and its focused test into the
  folder ... patches"); organs/immune.lines.txt ("the open patches").
- Adopt: `ROOT/organ-codebase/patches/<finding_id>/` containing `finding.txt` (the finding),
  `triage.json` (triage-error.sym output), `patch.diff` (unified diff, paths relative to the
  checkout), `test.txt` (one test path), `result.json` `{devcheck_rc, test_rc, at}`, and, written by
  immune, `review.json` (review-patch.sym output). "Open" = no `review.json`.

### 40. [MEDIUM] [undefined] `confident=false` has no consequence
- Location: triage-error.sym line 14; organs/codebase.lines.txt.
- Adopt: "A triage with `confident=false` is treated as class `unknown`" (then finding 34 routes
  it to the operator).

### 41. [MEDIUM] [undefined] Canary list format, cwd, timeout and pass rule are undefined
- Location: organs/immune.lines.txt ("run each canary check"); LIFE.md §7 lines 176–178; seed line
  1101 (empty file).
- Adopt: "`canaries.txt`: one shell command per non-blank line, run from `ROOT` with
  `timeout 120`; pass = exit 0; the immune lane records `{canary, rc, at}` per line." Seed content:
  `bash /home/operator/symblicos/projects/life/checks/verify-format.sh heartbeat` and
  `python3 -c "import json;json.load(open('/home/operator/symblicos/projects/life/organ-heartbeat/status.json'))"`
  (both reachable inside ROOT; `bin/symblic check` lines only after finding 11 is settled).

### 42. [MEDIUM] [undefined] `novelty_limit` drives quarantine but is never set
- Location: LIFE.md §7 line 180 ("fail novelty_limit generations in a row"); no policy sets it;
  BRIEF.md line 28 lists the field.
- Adopt: verify its meaning in `symblic_autogen.LIMITS/DEFAULTS`; set `"novelty_limit": <n>`
  explicitly in every perpetual policy and write the quarantine rule with that number: "a cell
  whose last 4 generations each added zero index keys and ended in failure is quarantined".

### 43. [LOW] [undefined] Rollback by `git checkout -- <file>` loses operator edits and leaves new files
- Location: LIFE.md §7 lines 181–184.
- Adopt: `applied.jsonl` records pre-apply blob ids; rollback restores those blobs and deletes
  paths the patch added; never a bare `git checkout --` on the live tree.

### E. Data flow between organs (paths the brief requires)

### 44. [HIGH] [missing] Command routing dead-ends
- Location: organs/command.lines.txt (reads `inbox`, writes `routed.jsonl`); classify-command.sym
  line 13 (`none` "must be shown to the operator"); no organ reads `routed.jsonl`; no operator channel.
- Defect: "continuously takes commands" ends at a file nobody reads. "Each new operator command" has
  no processed marker (every generation re-routes every file, every 120 s). The inbox file format
  and the command id derivation ("sha256[:16] of the command text + arrival time", schema line 51)
  are undefined.
- Adopt: inbox file = `inbox/<epoch>-<slug>.txt`, one command per file, UTF-8, ≤ 2000 chars;
  `command_id = sha256(text + '\n' + <epoch from the file name>)[:16]`; processed = moved to
  `organ-command/done/`. Dispatch table (performed by the command lane after classification):
  learning → append the restated line to `organ-learning/questions.txt`; codebase → write
  `organ-codebase/findings/<command_id>.txt`; compute → append `{id, hypothesis: text,
  measurement: "", threshold: "", score: 0}` to `experiments.jsonl` (the proposer, finding 48,
  fills the rest); selfdev → append to `lessons.jsonl`; database → write
  `organ-database/requests/<id>.sql.txt`; immune → append the command to `canaries.txt` only if it
  is one shell line, else operator; heartbeat and none → append to `organ-command/operator.jsonl`, which
  `life-status.py` prints.

### 45. [HIGH] [missing] Learning writes one sources file, digest reads another
- Location: organs/learning.lines.txt (`organ-learning/sources.jsonl`); organs/digest.lines.txt
  (`organ-digest/sources.jsonl`); LIFE.md §2 table rows 3–4.
- Adopt: digest reads `/home/operator/symblicos/projects/life/organ-learning/sources.jsonl`;
  "unprocessed" = `source_id` not present in `organ-digest/facts.jsonl`.

### 46. [HIGH] [missing] No defined fetch of source text for the digest
- Location: extract-source.sym line 6 (`given source_text`); organs/digest.lines.txt; BRIEF.md
  line 36–37.
- Defect: who fetches the page or paper text, where it is stored, its size cap for a 4B model, and
  how a worker node lane reaches the network are all unstated; a CLI agent fetching arbitrary URLs is an
  injection surface (finding 80).
- Adopt: the learning lane stores `organ-learning/text/<source_id>.txt` (first 20000 characters of
  the extracted text, written by `bin/local-research` at discovery); digest never fetches; the
  `.sym` call passes `source_text=@that file`.

### 47. [HIGH] [missing] Facts never become lessons; selfdev's input has no writer
- Location: organs/digest.lines.txt (writes `facts.jsonl`); organs/selfdev.lines.txt (reads
  `lessons.jsonl`); BRIEF.md line 5–6 ("develops itself based on things it learns").
- Adopt: selfdev reads `organ-digest/facts.jsonl` directly ("a lesson is a fact whose `claim`
  names a Symblic, autogen, Ollama, sqlite or shell behaviour"), or add `genome/reflect.sym`
  (given claim, quote → `lesson: Text`, `target: one of {genome, policy, check, none}`) run by the
  digest lane after each fact, appending to `organ-selfdev/lessons.jsonl`.

### 48. [MEDIUM] [missing] Nothing proposes experiments and nothing calls rank-experiment.sym
- Location: organs/compute.lines.txt ("Read the ranked experiments"); rank-experiment.sym; LIFE.md
  §2 row 6.
- Adopt: compute organ gets two statements: (1) `Read the facts ... propose one compute or storage
  experiment with a hypothesis, a measurement script and a threshold by running ROOT/genome/
  propose-experiment.sym, score it by running ROOT/genome/rank-experiment.sym, append one JSON
  line to .../experiments.jsonl ...` (new `propose-experiment.sym` with typed fields and ensures),
  (2) the existing run line, restricted to `score >= 60`.

### 49. [MEDIUM] [missing] The five tables have no writer
- Location: schema.sql.txt (lineage "Each spawn writes one row", metrics "written by heartbeat");
  tick (never opens sqlite); heartbeat/command/digest/compute lines (write jsonl only).
- Adopt: the code ticks on the host own the database: spawn tick inserts `lineage`; the status/
  metabolism script inserts `metrics` per generation and mirrors `commands`, `knowledge`,
  `experiments` from the jsonl files (idempotent `INSERT OR IGNORE`). Lanes never open the DB.

### 50. [MEDIUM] [missing] "Creates databases" is a one-shot build with no live consumer
- Location: policies/database.json (`perpetual false`); classify-command.sym line 9 (routes
  database commands to an organ that has ended).
- Adopt: after the bounded build, a perpetual `database` lane (interval 3600, idle rule) that
  applies `organ-database/requests/*.sql.txt` as numbered migrations after `sqlite3 -bail` dry-run
  on a copy, and records them in `migrations/`.

### 51. [MEDIUM] [undefined] No JSONL record schemas
- Location: organs/* ("one JSON line per command/source/fact/verdict", "one metabolism row",
  "one status snapshot"); schema.sql.txt (tables only).
- Adopt (fields, all required): `routed.jsonl` `{command_id, organ, urgency, restated, file, at}`;
  `sources.jsonl` `{source_id, key, url, doi, title, question, text_file, at}`; `facts.jsonl`
  `{fact_id, source_id, url, claim, quote, at}`; `verdicts.jsonl` `{kind: canary|review|quarantine,
  id, verdict, rc, reason, at}`; `metabolism.jsonl` `{at, nodes: {node: {load1, cpus, busy}},
  continuous_minutes, free_gb, highpower, fanout_allowed}`; `status.json` `{at, organs: {name:
  {run_id, generation, new_items, failures, last_verify, node}}}`; `lessons.jsonl` `{lesson_id,
  fact_id, lesson, target, at}`; `experiments.jsonl` `{id, hypothesis, measurement, threshold,
  score, feasible, novelty, risk, at}`; `results/<id>.json` `{id, node, measured, passed, started,
  ended}`. Ids are `sha256(...)[:16]` of the stated input.

### 52. [MEDIUM] [undefined] Source key normalisation is undefined
- Location: organs/learning.lines.txt ("not already in the index", "three new source keys");
  schema.sql.txt line 9 (`doi:/url:/text:`).
- Adopt: `doi:<DOI lower-cased, resolver prefix removed>`; `url:<scheme://host/path, host
  lower-cased, no query, fragment or trailing slash>`; `text:<sha256[:16] of NFC lower-cased
  whitespace-collapsed text>`; the same function in the engine and in LIFE's scripts.

### 53. [LOW] [undefined] `urgency` is produced and never used
- Location: classify-command.sym line 16; schema line 54.
- Adopt: "`high` commands are dispatched first within a generation; otherwise urgency is
  informational", or drop the ask (one model load fewer per command).

### 54. [HIGH] [missing] No producer of codebase findings
- Location: organs/codebase.lines.txt (`organ-codebase/findings`); seed line 1097 (empty folder).
- Defect: "fixes errors" has no error source; the organ idles forever or invents findings.
- Adopt: a code producer on the host in the same timer: run `bin/devcheck` on the host staging
  checkout once per hour and tail the dashboard error log (`<path>`), writing each distinct
  failure as `findings/<sha256[:16] of the normalised message>.txt` (first 4000 chars).

### F. Metabolism and heat

### 55. [HIGH] [contradiction] The heat gate measures the host, the heat rule is about the worker nodes
- Location: checks/heat-gate.sh lines 7–8 (`/proc/loadavg`, `/proc/pressure/io` of the machine
  running the tick); LIFE.md §6 lines 165–166; BRIEF.md line 19.
- Adopt: heat-gate reads the last `metabolism.jsonl` row (finding 13): HOLD when the row is older
  than 10 min, when `continuous_minutes >= 60`, or when any worker node has `load1/cpus >= 0.75`; keep
  the host checks as an additional HOLD condition only.

### 56. [MEDIUM] [unsafe] The io half of the gate fails open
- Location: checks/heat-gate.sh line 8 (`... 2>/dev/null || echo 0`, `${io:-0}`). Reproduced in §3.
- Defect: a missing or unreadable `/proc/pressure/io`, or one without a `full` line, yields 0,
  which is the ALLOW side.
- Adopt: `io="$(awk ... /proc/pressure/io 2>/dev/null)" || io=""; [ -n "$io" ] || { echo "HOLD io
  pressure unreadable"; exit 4; }`.

### 57. [HIGH] [undefined] "Continuous all-worker node load minutes" and "rest" are not defined; the decision has no reader
- Location: organs/metabolism.lines.txt ("compute the current continuous all-worker node load minutes
  and free capacity ... whether fan-out is allowed"); LIFE.md §6 lines 163–166; tick (reads
  heat-gate.sh only).
- Adopt: "A worker node is loaded in a 5-minute sample when `/api/cluster/status` reports `cpu_busy >=
  50` or an agent attempt active on it. `continuous_minutes` = 5 × length of the trailing run of
  samples in metabolism.jsonl with ≥ 4 of 6 worker nodes loaded. `fanout_allowed` = `continuous_minutes
  < 60`. Rest = 6 consecutive samples with ≤ 1 worker node loaded; it resets the run. The spawn tick
  reads `fanout_allowed` (finding 55); no new generation is required to pause because interval
  arithmetic (finding 8) keeps steady load under 50%."

### 58. [MEDIUM] [undefined] Endpoint paths and authentication for the loopback API
- Location: LIFE.md §6 line 160–161 (`/api/cluster/status`, `/capacity`, `/highpower/state`);
  README line 28 (`DASH_URL`).
- Adopt: the three exact paths as served (`/api/cluster/status`, `/api/capacity`,
  `/api/highpower/state`, verified at `<route file:line>`) and "loopback GETs need no token
  (verified <file:line>)"; if a token is needed, it comes from an environment file the operator
  creates (`~/.config/life/env`, mode 600), never from the kit.

### 59. [MEDIUM] [undefined] Where operator requests go (high-power mode, restart-gated, `none` commands)
- Location: LIFE.md §6 lines 168–169 ("writing a row the operator approves"); README line 70–71
  ("queued as a request for you"); classify-command.sym line 13.
- Adopt: `ROOT/requests/<epoch>-<organ>-<kind>.md` with `kind ∈ {highpower, restart_gated,
  command_none}` and fields `why`, `what`, `lease_minutes` (highpower); `life-status.py` lists
  open requests; the operator deletes the file to close it.

### 60. [LOW] [undefined] Load threshold 4.0 ignores core count
- Location: checks/heat-gate.sh line 4, 10.
- Adopt: `l < 0.5 * nproc` with `nproc="$(nproc)"`.

### G. Compute organ safety

### 61. [HIGH] [unsafe] Model-authored measurement commands run unsandboxed
- Location: organs/compute.lines.txt ("run the highest-scoring experiment whose measurement
  command fits one node and fifteen minutes"); schema line 64 ("the exact shell command");
  rank-experiment.sym line 10 (risk is a 1B model's label).
- Defect: arbitrary shell from `experiments.jsonl` executes on a worker node with no allow-list,
  timeout, memory, disk or network bound; "fifteen minutes" is a model's guess.
- Adopt: "`measurement` is the path `ROOT/organ-compute/bench/<id>.sh`; the lane runs it only as
  `timeout 900 nice -n 15 unshare -n bash -c 'ulimit -v 4000000 -f 1000000; bash <path>'` from
  `ROOT/organ-compute/scratch/<id>/` (deleted after); the script must have passed
  review-patch.sym with class `test_only` and contain none of: `rm -rf`, `dd `, `mkfs`, `curl`,
  `wget`, `ssh`, `sudo`, `systemctl`, `/dev/`, `:(){`, `kill`."

### 62. [MEDIUM] [undefined] Threshold grammar and measured-number parsing
- Location: schema line 65 (`e.g. '< 1.0'`); organs/compute.lines.txt ("whether the threshold
  passed").
- Adopt: `threshold` matches `^(<|<=|>|>=) -?[0-9]+(\.[0-9]+)?$`; `measured` = the last stdout
  line matching `^-?[0-9]+(\.[0-9]+)?$`; no such line = failed experiment.

### 63. [LOW] [undefined] rank-experiment.sym mechanics
- Location: rank-experiment.sym lines 8–11 (three models on one node), line 11 (`votes=3,
  vote=median`, no `retries`), lines 9–10 (enum votes with no tie rule).
- Adopt: one model (`qwen3:4b-instruct@<lane node>`) for all four asks; `retries=2` on `score`;
  state the default retry count and the enum vote rule ("plurality; tie → retry") in §3.

### H. Database organ

### 64. [HIGH] [contradiction] The database lane uses handoff on a worker node, which LIFE says is refused
- Location: policies/database.json line 9 (`"generations": 2`); seed line 1126 (`--handoff 2`);
  LIFE.md §11.3 lines 245–250 ("Remote handoff is refused").
- Adopt: delete `"generations"` from database.json and `--handoff 2` from the seed; §11.3 text
  "the database organ uses decomposition only".

### 65. [MEDIUM] [contradiction] Line 2 recreates a file the seed already copied
- Location: organs/database.lines.txt line 2 ("Create the file .../db/schema.sql ... named in
  the master script"); seed line 1104 (`cp -n "$KIT/db/schema.sql" "$ROOT/db/schema.sql"`);
  `"require_change": true`.
- Defect: the agent is asked to reproduce a schema it cannot read (LIFE.md is not in ROOT) over a
  file that already holds it; an identical rewrite violates `require_change`.
- Adopt: delete line 2; lines 1, 3, 4 refer to `/home/operator/symblicos/projects/life/db/
  schema.sql` as the source of truth; line 3 becomes `Create ... 0001_init.sql as a copy of the
  file /home/operator/symblicos/projects/life/db/schema.sql ...`.

### 66. [MEDIUM] [undefined] Database path, `-bail`, sqlite3 availability, expected columns
- Location: organs/database.lines.txt lines 1, 4 ("the database file life.sqlite3" with and
  without a folder); policy `final` (`bash organ-database/check_schema.sh`, relative).
- Adopt: both scripts use `DB=/home/operator/symblicos/projects/life/db/life.sqlite3` and
  `sqlite3 -bail "$DB"`; expected tables and columns are read from `ROOT/db/schema.sql` by
  `check_schema.sh` (parse `CREATE TABLE` blocks), not retyped; add "sqlite3 CLI is installed on
  node-a and the host (verified `which sqlite3`)" to §5.

### 67. [MEDIUM] [unsafe] A binary SQLite file inside the git-promoted workspace
- Location: LIFE.md §5 line 148–149 (`ROOT/db/life.sqlite3`); BRIEF.md line 34 ("promotion =
  commit -> apply").
- Defect: the database would be committed to the workspace git on every change and synced through
  staging checkouts to other nodes, with concurrent writers on different hosts.
- Adopt: `.gitignore` `db/*.sqlite3*` in ROOT; the file exists only on the host and is written only
  by the code ticks (finding 49); lanes write jsonl.

### 68. [LOW] [undefined] `cp -n` exit status is not portable under `set -e`
- Location: seed line 1104; `set -euo pipefail` line 1077. Reproduced in §3 (coreutils 9.4 warns
  that `-n` behaviour may change; 9.2 returned 1 on skip).
- Adopt: `[ -e "$ROOT/db/schema.sql" ] || cp "$KIT/db/schema.sql" "$ROOT/db/schema.sql"`.

### 69. [LOW] [undefined] Check index "4" under decomposition
- Location: policies/database.json line 16 (`"checks": {"4": [...]}`), line 7 (`"depth": 1`).
- Adopt: verify whether check indices follow the original statement numbering after `--decompose`;
  if not, move the check into `final`.

### I. Genome programs and the formal-language contract

### 70. [MEDIUM] [undefined] How givens are passed, how `--by` interacts with in-file `by`, what is returned
- Location: BRIEF.md line 35 (`bin/symblic run F.sym --by ollama:...`); every `.sym` (in-file `by
  "ollama:...@node"`); LIFE.md §11.2 line 241.
- Adopt: in §3: "Invocation: `bin/symblic run <file>.sym --given name=value --given
  name=@file --json [--by ollama:MODEL@node]`; `--by` overrides every in-file `by`
  (`<file:line>`); output and exit codes as in finding 28."

### 71. [LOW] [undefined] The Organ enum omits three organs
- Location: classify-command.sym lines 6–14 (no `command`, `digest`, `metabolism`).
- Adopt: state "commands are never routed to command, digest or metabolism; a digest request is
  routed to learning" in the `note`.

### 72. [LOW] [undefined] No upper bound on the extracted quote
- Location: extract-source.sym lines 9–11.
- Adopt: `ensure len(quote) >= 12 and len(quote) <= 400 else retry because "the quote is between
  twelve and four hundred characters".`

### 73. [MEDIUM] [missing] Selfdev has no program, no proposal format, no check definition, no apply path
- Location: organs/selfdev.lines.txt; LIFE.md §2 row 5 ("qwen3:4b-instruct (proposes edits)",
  no `.sym`); §3 line 120–121; README line 69–72.
- Defect: the CLI agent itself drafts edits to the genome and policies from web-derived lessons
  (finding 80); "add a check that proves the improvement" is undefined; nothing applies proposals
  and nothing says who may.
- Adopt: `proposals/<id>/{target, patch.diff, check.sh, reason.txt}` where `target` is one path
  under `ROOT/genome` or `ROOT/policies`; `check.sh` must run `bin/symblic check` /
  `normalize` / lint on a patched copy in `proposals/<id>/tmp/` and exit 0; proposals are applied
  only by the operator with `life-apply --genome <id>` after an immune `accept`; never by a cell.

### 74. [LOW] [contradiction] §3 lists `delegate` as a LIFE lane; §11.4 bans it
- Location: LIFE.md §3 lines 111–113; §11.4 lines 251–254.
- Adopt: delete the §3 bullet.

### 75. [LOW] [contradiction] The `local` task engine is described as used but nothing uses it
- Location: LIFE.md §3 lines 120–121.
- Adopt: delete the bullet or name the exact helper turn that uses it.

### 76. [LOW] [undefined] Model names must match `ollama list` exactly
- Location: LIFE.md §3 line 104 (`qwen3.8:27b`, `laguna-xs-2.1`).
- Adopt: replace with the tags as installed (`ollama list` output pasted), or drop the row.

### 77. [MEDIUM] [undefined] Enum vote semantics and default retries
- Location: classify-command.sym line 15 (`votes=3` over 8 classes), review-patch.sym line 12,
  triage-error.sym line 13; asks without `retries`.
- Adopt: in §3: "`votes=n` on an enum = plurality, tie → one more vote round, then `retry`;
  default `retries` = <value from the kernel, file:line>."

### J. Scripts: tick, seed, status, validator

### 78. [MEDIUM] [contradiction] Seed flags are hand-copied from the policies and already differ
- Location: seed lines 1114–1128 ("keep the two in sync"); finding 4 (missing `--saturation 0`);
  `--candidates 1` never passed.
- Adopt: the seed derives flags with the tick's `policy_flags()`:
  `python3 -c 'import sys,json; sys.path.insert(0,"<kit>/bin"); from life_spawn_tick import
  policy_flags; print("\0".join(policy_flags(json.load(open(sys.argv[1])))))' policies/$organ.json`
  (or a tiny shared module), so one file is the truth.

### 79. [LOW] [undefined] The tick does not catch a missing or non-executable heat-gate.sh
- Location: tick line 960.
- Adopt: wrap in `try/except OSError` → log and `return 4` (HOLD).

### 80. [MEDIUM] [unsafe] Web-derived text reaches CLI agents as instructions
- Location: organs/learning, digest, selfdev lines (agents read `sources.jsonl`, `facts.jsonl`,
  `lessons.jsonl`); extract-source.sym (`context=none` protects the typed ask only).
- Adopt: in §1: "A worker agent never reads the body of a fetched source, fact or lesson; it passes
  file paths to the genome program (`--given source_text=@file`) and reads only the program's JSON
  output. Only `.sym` programs with `context=none` see page text."

### 81. [MEDIUM] [undefined] Promotion concurrency and repository growth
- Location: LIFE.md §2 line 53–54 (one git-backed workspace), §7 line 182 (3-way merge on
  promotion); policies (command every 120 s → up to 720 promotions a day).
- Adopt: "Promotions take `flock ROOT/.promote.lock`; the workspace is squashed to one commit per
  day by the status tick when it exceeds 2000 commits; `approved/` and `rejected/` records older
  than 30 days and `metabolism.jsonl` rows older than 90 days are pruned by the same tick."

### 82. [LOW] [contradiction] VALIDATE.sh: comment vs code, weak lineage rule, unmatched globs
- Location: VALIDATE.sh line 9 ("skipped if no sqlite") vs lines 81–90 (FAIL); line 63 (`0<=depth
  <=64`, `count('.')==2`) vs tick (`depth < 10`, regex); lines 21, 39, 67, 72, 77 (globs without
  `nullglob`; reproduced: a missing `bin/` yields `bash -n '…/bin/*.sh'` → FAIL 127 with a
  misleading message).
- Adopt: `shopt -s nullglob` plus an explicit "no files" FAIL per section; the lineage check
  imports the tick's validator (`from life_spawn_tick import lineage_ok`); fix the comment.

### 83. [MEDIUM] [missing] Files the kit depends on exist only as appendix text in this bundle
- Location: README lines 23–25 ("must end ALL PASS"), 17–19; VALIDATE.sh lines 50, 57, 63, 72,
  77, 82 (`spawn/example/*`, `bin/*.sh`, `bin/*.py`, `db/schema.sql`).
- Defect: `bin/life-spawn-tick.py`, `bin/life-status.py`, `bin/life-seed.sh`, `spawn/example/*`
  and `db/schema.sql` are not present as files in the reviewed bundle; if they are also absent on
  The host, VALIDATE.sh can never print ALL PASS and the timer unit's `ExecStart` path does not
  exist.
- Adopt: ship them as files; add to VALIDATE.sh the appendix-equality check run in §3 of this
  report (every `### path` block in LIFE.md must equal the file), so the "complete text" claim is
  enforced.

### 84. [MEDIUM] [undefined] INFRASTRUCTURE wait and post-reboot behaviour
- Location: LIFE.md §2 lines 83–86 ("the lane waits rather than migrating"); §9 `OnBootSec=5min`.
- Adopt: "A generation whose node is asleep is skipped, not failed; the lane retries at the next
  interval (autogen.py:<line>)." And: "After a reboot the ten seeds are down until the operator
  re-seeds; the spawn tick births nothing while their runs are absent (finding 20)."

### 85. [LOW] [undefined] The engine escalation order is not expressible by `strategies`
- Location: LIFE.md §3 lines 124–127.
- Adopt: cite `next_strategy`'s actual order (`<file:line>`) or remove the ordered list.

### 86. [MEDIUM] [unsafe] No bound on agent sessions or cloud spend
- Location: policies (metabolism, heartbeat 288 attempts/day each; command 720/day); `other_engine`
  in seven policies.
- Adopt: `LIFE_MAX_ATTEMPTS_PER_DAY = 400` across all `life-*` runs, enforced by the status tick
  (cancels nothing, writes a request file and sets a HOLD flag the spawn tick honours); cloud CLIs
  only when the operator sets `LIFE_ALLOW_CLOUD=1` in the unit environment.

### 87. [LOW] [undefined] Exit codes of the tick are indistinguishable for systemd and the operator
- Location: tick `main()` returns 0 even when every record failed to start (line 1012 → continue).
- Adopt: return 5 when any `start` failed; `SuccessExitStatus=3 4` in the unit (finding 23).

### K. Schema

### 88. [LOW] [undefined] Id derivations and limits in schema comments
- Location: schema.sql.txt line 9 (`knowledge.id` = source key; many facts per source collide on a
  PRIMARY KEY), line 51 (`commands.id` "text + arrival time", no separator or time format), line
  25 (`depth 0..64` vs cap 10), lines 54, 56, 27 (enum columns without CHECK), line 4
  (`strftime('%s')` returns text).
- Adopt: `knowledge.id = sha256(source_id + '|' + quote)[:16]`; `commands.id` per finding 44;
  `depth INTEGER NOT NULL CHECK (depth BETWEEN 0 AND 10)`; `CHECK (urgency IN ('low','normal',
  'high'))`, `CHECK (status IN (...))`, `CHECK (spawn_reason IN ('divide','seed','replan'))`;
  "times are `CAST(strftime('%s','now') AS INTEGER)`".

### 89. [LOW] [undefined] `knowledge.verified` can never be 0
- Location: schema line 16; extract-source.sym line 10 (quotes() is enforced by retry).
- Adopt: drop the column or define "0 = inserted from a source whose text file was truncated".

## 5. Cross-cutting summary (what the next round must settle first)

1. Decide the cwd/placement model (findings 1, 2, 8): per-organ cwd, one lane per worker node, duty ≤ 0.5.
2. Pin the four engine semantics with code citations (findings 3–7): item key, saturation 0,
   wall_seconds, agents_max, interval origin. Until then the organism's lifetime is unknown.
3. Make the reproducer, the apply step, the findings producer and the dispatch table exist as code
   ticks on the host (findings 15, 36, 44, 54) and move metabolism/heartbeat to code (13).
4. Fix the four open gates in the tick (18, 19, 20, 22) before any timer is installed.
5. Replace `test -s verify.txt` with the per-organ grammar check (31, 33).
6. Sandbox the compute organ (61) and bound spend (86).

## 6. Limitations

- Platform facts asserted by LIFE.md about `symblicos/autogen.py`, `symblic_autogen`, the fleet runner,
  the Agents hub, node capacities and installed models could not be verified from this bundle;
  findings that depend on them are written as "verify at file:line and state the result" rather
  than as assertions about the platform.
- `bin/*` scripts and `spawn/example/*` were reviewed from LIFE.md appendices, not as files.
- Lint (`symblic_autogen.lint`), `normalize` and `bin/symblic check` were not run (not in the
  bundle); LIFE.md's claim that every line and policy passes them is taken as unverified.
- No kit script was executed and no model, agent or network call was made.

FINDINGS_TOTAL=89
UNDEFINED_DETAILS=50
VERDICT=CHANGES NEEDED

Review artifacts: [local results path and commit id removed for publication; kept privately by the operator]
