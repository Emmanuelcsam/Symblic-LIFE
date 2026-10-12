"""LIFE v2.3 shared contract: paths, limits, identities, validators, the process runner and the loopback adapter.

Imported by bin/life-tick.py, bin/life-ctl.py, bin/life-status.py, bin/life-check.py, bin/life-research.py and
bin/life-fetch.py. Inert on import: importing this module reads nothing, writes nothing and starts nothing.
Every number here is the single definition LIFE.md section 13 tabulates: the table is generated from the limits block
below by limits_rows(), and VALIDATE.sh check 13 compares it with LIFE.md. Every limits line carries a trailing
comment (its unit, what it bounds and who enforces it). REPO and KIT are fixed. STATE, PROJECTS, DASH and the platform
executables can be moved ONLY by configure(), an in-process call made by the admission tests (LIFE.md GAP 8): no
environment variable, flag or file can move them, so a running organism never splits control between roots.
"""
import ast
import hashlib
import json
import math
import os
import re
import secrets
import shutil
import signal
import sqlite3
import stat
import subprocess
import tempfile
import threading
import time
import unicodedata
import urllib.error
import urllib.request

# ------------------------------------------------------------------------------------------- paths
REPO = '/home/operator/host-checkout'
KIT = REPO + '/docs/life'
SYS_PY = '/usr/bin/python3'                     # the ONE interpreter for everything LIFE runs on the host
REPO_PY = REPO + '/.venv/bin/python'            # only bin/life-fetch.py and bin/life-research.py (bs4/pypdf)
SANDBOX_LAUNCHER = REPO + '/landlock_sandbox.py'  # the repository's Landlock launcher (symblicos/autogen.py uses it)
STATE = '/home/operator/.local/state/life'
PROJECTS = '/home/operator/symblicos/projects'
DASH = 'http://127.0.0.1:8080'                  # loopback only; never a worker node tunnel
TASK = REPO + '/bin/symblic-task'
SYMBLIC = REPO + '/bin/symblic'
RESEARCH = REPO + '/bin/local-research'         # used only for --list (the model inventory); research runs
RESEARCH_WRAPPER = KIT + '/bin/life-research.py'  # go through this wrapper (SIGTERM cancels its fleet-runner runs)
FETCHER = KIT + '/bin/life-fetch.py'
GATE_SCRIPT = KIT + '/checks/devcheck-gate.sh'
DECISIONS_FILE = KIT + '/DECISIONS.md'          # the operator's requirements decisions; arm binds its sha256


def _derive():
    """Recompute every path derived from STATE. Called at import and by configure()."""
    g = globals()
    s = g['STATE']
    g.update(
        REGISTRY=s + '/life.sqlite3', ORGANISM=s + '/organism.sqlite3', CONTROL=s + '/control',
        INBOX=s + '/inbox', INBOX_TMP=s + '/inbox-tmp', INBOX_DONE=s + '/inbox-done', INBOX_REFUSED=s + '/inbox-refused',
        RELEASES=s + '/release', CALLS=s + '/calls', BUNDLES=s + '/bundles', TEXTS=s + '/text', RUNS_DIR=s + '/runs',
        LOGS=s + '/logs', BACKUPS=s + '/backups', APPLIED=s + '/applied', OWNER=s + '/operator',
        REPORTS=s + '/operator/reports', RETIRED=s + '/retired', LOCK_FILE=s + '/tick.lock',
        CONTROL_LOCK=s + '/control.lock', MIGRATION_JOURNAL=s + '/migration-numbers.txt',
        AGENT_CLEANUP=s + '/operator/node-cleanup.txt')
    c = g['CONTROL']
    g.update(STOP_FILE=c + '/STOP', FREEZE_FILE=c + '/FREEZE', ARMED_FILE=c + '/ARMED', SELFDEV_FILE=c + '/SELFDEV_ARMED',
             NO_SELF_QUESTIONS_FILE=c + '/NO_SELF_QUESTIONS', HISTORY_OK_FILE=c + '/CODEBASE_HISTORY_OK',
             WATCH_FILE=c + '/watch.txt', BENCH_FILE=c + '/benchmarks.json', AGENDA_FILE=c + '/agenda.json',
             AGY_MODEL_FILE=c + '/agy-model.txt', STOP_GENERATION_FILE=c + '/STOP_GENERATION')
    g['STATE_DIRS'] = (s, c, g['INBOX'], g['INBOX_TMP'], g['INBOX_DONE'], g['INBOX_REFUSED'], g['RELEASES'], g['CALLS'],
                       g['BUNDLES'], g['BUNDLES'] + '/patches', g['BUNDLES'] + '/proposals', g['BUNDLES'] + '/migrations',
                       g['TEXTS'], g['RUNS_DIR'], g['LOGS'], g['BACKUPS'], g['APPLIED'], g['OWNER'], g['REPORTS'],
                       g['RETIRED'])


# every name _derive() sets, declared here so readers and linters see them; _derive() fills them from STATE
REGISTRY = ORGANISM = CONTROL = INBOX = INBOX_TMP = INBOX_DONE = INBOX_REFUSED = RELEASES = CALLS = BUNDLES = None
TEXTS = RUNS_DIR = LOGS = BACKUPS = APPLIED = OWNER = REPORTS = RETIRED = LOCK_FILE = STATE_DIRS = None
CONTROL_LOCK = MIGRATION_JOURNAL = AGENT_CLEANUP = None
STOP_FILE = FREEZE_FILE = ARMED_FILE = SELFDEV_FILE = NO_SELF_QUESTIONS_FILE = HISTORY_OK_FILE = None
WATCH_FILE = BENCH_FILE = AGENDA_FILE = AGY_MODEL_FILE = STOP_GENERATION_FILE = None
_derive()


def configure(*, state=None, projects=None, dash=None, task=None, symblic=None, research=None, inventory=None,
              fetcher=None, sandbox=None, gate=None):
    """Admission tests only: move STATE/PROJECTS/DASH and the platform executables (task CLI, symblic, the research
    wrapper, the model inventory, the fetcher, the Landlock launcher, the gate script) to fakes, in-process. The
    production entry points never call it."""
    g = globals()
    for name, value in (('STATE', state), ('PROJECTS', projects), ('DASH', dash), ('TASK', task), ('SYMBLIC', symblic),
                        ('RESEARCH_WRAPPER', research), ('RESEARCH', inventory), ('FETCHER', fetcher),
                        ('SANDBOX_LAUNCHER', sandbox), ('GATE_SCRIPT', gate)):
        if value is not None:
            g[name] = value
    _derive()


# ------------------------------------------------------------------------------------------- organism
ORGANS = ('command', 'learning', 'digest', 'codebase', 'immune', 'selfdev', 'compute', 'database')
AGENT_ORGANS = ('codebase', 'selfdev', 'database')
NODES = ('node-a', 'node-b', 'node-d', 'node-f', 'node-i')   # node-c/e unlisted in BRIEF; node-h = protected service stack
PROGRAMS = ('classify-command', 'triage-error', 'extract-source', 'distill-lesson', 'propose-experiment',
            'rank-experiment', 'review-patch', 'reproduce', 'assign-item')
SELFDEV_PROTECTED = ('review-patch',)            # its verdict makes a patch `ready`: no lesson or proposal may change it
ROUTES = ('learning', 'codebase', 'database', 'compute', 'selfdev', 'immune', 'heartbeat', 'none')
STAGES = {                                       # each organ's item stage machine (LIFE.md section 7)
    'command': ('classify',),
    'learning': ('research',),
    'digest': ('fetch', 'extract', 'distill'),
    'codebase': ('confirm', 'triage', 'patch', 'gate'),
    'immune': ('review',),
    'selfdev': ('draft', 'gate'),
    'compute': ('propose', 'rank', 'bench'),
    'database': ('draft', 'apply'),
}
SLOT_STAGES = (('command', 'classify'), ('learning', 'research'), ('digest', 'extract'), ('digest', 'distill'),
               ('codebase', 'triage'), ('immune', 'review'), ('compute', 'propose'), ('compute', 'rank'),
               ('compute', 'bench'))
AGENT_STAGES = (('codebase', 'patch'), ('selfdev', 'draft'), ('database', 'draft'))
# The ONE list of stages whose items are bound to the workspace of the cell that produced them: they are never
# re-dispatched, a division leaves them with the parent, and they make the workspace busy (Tick.workspace_busy). A
# confirm item is NOT bound: it needs any idle active codebase clone and is dispatched like any other item.
WORKSPACE_STAGES = ('gate', 'apply')
MODEL_MIB = {'qwen2.5:0.5b': 400, 'llama3.2:1b': 1300, 'gemma3:1b': 900, 'qwen2.5-coder:3b': 1900,
             'qwen3:4b-instruct': 2600}
NON_THINKING_MODELS = ('qwen2.5:0.5b', 'llama3.2:1b', 'gemma3:1b', 'qwen2.5-coder:3b', 'qwen3:4b-instruct')
ENGINE = 'agy'                                   # the only CLI engine LIFE starts (strategies fresh,feedback)
AGY_EFFORT = 'low'                               # --effort of every LIFE agy run (bin/symblic-task FLAGS_WITH_VALUE)
AGY_MODEL_RX = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}')   # control/agy-model.txt: the operator's exact agy model id
DATABASE_PREFIX = 'database:'   # an operator command routed to database must start with this (case-insensitive)
# Operator command prefixes routed by CODE before any model is asked (case-insensitive; the text after the prefix,
# stripped, is the command). A command that is exactly `status` (any case) is a heartbeat. Unprefixed commands go to
# the classifier; the database route always needs its prefix.
COMMAND_PREFIXES = (('research:', 'learning'), ('fix:', 'codebase'), ('database:', 'database'),
                    ('measure:', 'compute'), ('genome:', 'selfdev'))
STORE_COLUMNS = ('fact_id', 'source_url', 'claim', 'quote', 'created_at')   # an org_ table with fact_id and only
#   these columns receives every quote-verified knowledge row (the store adapter: code-written, parameters bound)
GATE_EXITS = {2: 'bad arguments', 3: 'the test module does not resolve inside the clone', 4: 'devcheck failed or '
              'checked no file', 5: 'the focused test failed, ran no test or skipped every test', 125: 'the sandbox is unavailable'}

# ------------------------------------------------------------------------------------------- limits
# Every line: NAME = value  # unit; what it bounds; who enforces it. limits_rows() turns this block into LIFE.md section 13.
# tick timing
TICK_SECONDS = 300            # s; units/life-tick.timer OnUnitInactiveSec: the next tick starts this long after the previous one ENDS
TICK_DEADLINE = 1200          # s from tick start; no new the host stage, agent start, division step or slot action begins after it (Tick.can_start)
TICK_HARD = 2700              # s from tick start; every admitted stage or process must be able to end (its budget + KILL_GRACE + START_MARGIN) by it
UNIT_TIMEOUT = 3000           # s; units/life-tick.service TimeoutStartSec (= TICK_HARD + 300; VALIDATE compares)
KILL_GRACE = 30               # s; SIGTERM to a process group, then SIGKILL to the whole group this long later (Procs.end)
START_MARGIN = 60             # s; slack every admission keeps before TICK_HARD (Tick.can_start)
STOP_POLL = 1                 # s; the tick's watcher thread re-reads control/STOP (stop_present) this often
SLOT_WAIT_EXTRA = 30          # s; the slot phase ends a thread still alive this long after its timeout + KILL_GRACE
SLOT_ACTIONS_MAX = 4          # actions; one node takes at most this many slot actions per tick, each after the previous ended
TICK_TASKS_MAX = 192          # tasks; units/life-tick.service TasksMax = 8 (tick threads) + 5 nodes x 32 (a slot's systemd-run client and helpers before its process moves into its scope) + 24 helpers
SCOPE_TASKS_MAX = 64          # tasks; TasksMax of every transient scope LIFE starts (scope_argv); ruff and ast-grep get RAYON_NUM_THREADS=4 so devcheck stays far below it
SLOT_MEMORY = '1G'            # bytes (systemd); MemoryMax of the life-slot-*.scope each bin/symblic run and research run executes in (Tick.run_program)
# program and research runs
CALL_TIMEOUT = 900            # s; one bin/symblic run process (its process group gets SIGTERM, then SIGKILL)
CALL_MAX_MODEL_CALLS = 12     # model calls; --max-calls of every genome program run, reserved from the day's budget before launch
OLLAMA_LIMITS = {'num_predict': 320, 'timeout_seconds': CALL_TIMEOUT // CALL_MAX_MODEL_CALLS}   # per model call; generation cap (a cut answer fails its type check) and wall (75 s, so 12 calls fit CALL_TIMEOUT; VALIDATE compares)
RESEARCH_TOOLS = 3            # tool uses; per research run (searches plus page reads), passed to local_research.research
RESEARCH_GENERATIONS = RESEARCH_TOOLS + 2   # model calls; local_research.research loops max_tools + 2 times (pinned); the wrapper enforces it
RESEARCH_STEP_TIMEOUT = 180   # s; one research generation (overrides local_research.STEP_TIMEOUT in the wrapper)
RESEARCH_STEP_POLL_EXTRA = 120   # s; local_research.generate polls a generation up to STEP_TIMEOUT + 120 (pinned)
RESEARCH_TOOL_SECONDS = 180   # s; one tool use at most: a SearXNG search (30 s) or a page read (safe_fetch: 5 hops x (10 + 25) s)
RESEARCH_TIMEOUT = RESEARCH_GENERATIONS * (RESEARCH_STEP_TIMEOUT + RESEARCH_STEP_POLL_EXTRA) + RESEARCH_TOOLS * RESEARCH_TOOL_SECONDS + 60   # s; one bin/life-research.py process (the derived worst case + 60)
ASSIGN_PER_SLOT = 4           # runs; assign-item.sym runs one division makes in one node slot
ASSIGN_TIMEOUT = CALL_TIMEOUT // ASSIGN_PER_SLOT   # s; one assign-item.sym run
ASSIGN_MAX = 16               # items; snapshot items a division sends to assign-item at most (the rest go by parity)
SAMPLE_LABELS = 12            # labels; queued item labels shown to reproduce.sym
SAMPLE_CHARS = 1600           # characters; the joined labels are cut to this
INFRA_RUNS_MAX = 6            # outcomes; infrastructure outcomes of one item stage before it goes to the operator (notice infra_repeat)
FAULTS_MAX = 3                # faults; tick faults (Tick.guard) on one item stage before it fails
START_ATTEMPTS_MAX = 3        # refusals; HTTP 4xx refusals of bin/symblic-task start for one item before it fails (items.start_refusals)
RUN_RESENDS_MAX = 3           # re-sends; identical start re-sends of one submit_unknown run before notice run_unknown hands it to the operator
TIMEOUTS_ESCALATE = 2         # timeouts; program timeouts of one item at one rung before it escalates one rung; with no higher rung the item goes to the operator (outcome TIMEOUT_LIMIT, notice timeout_limit)
NODE_HOLD_SECONDS = 1800      # s; a node that answered infra is skipped this long; a timeout holds only that node for that program (node_holds cause timeout)
ORPHAN_HOLD_SECONDS = CALL_TIMEOUT + 300   # s; after a crashed tick or STOP, the node of every call intent left open is held this long
MODELS_REFRESH_SECONDS = 86400   # s; the installed-model inventory (bin/local-research --list) is re-read this often
MODELS_RETRY_SECONDS = 3600   # s; after a model_absent on a node missing from a readable inventory, the inventory is re-read this soon
# population and reproduction
LIFE_MAX_CELLS = 16           # cells; cells in state active, dividing or quarantined, all organs
ORGAN_CELL_CAP = 3            # cells; such cells per organ
NODE_CELL_CAP = 4             # cells; such cells per node
MAX_DEPTH = 10                # depth; a child's depth is at most this; a parent divides only below it
DIVIDE_SUSTAIN = 3            # ticks; consecutive armed working ticks with workable backlog >= the organ's divide_backlog
DIVISION_COOLDOWN = 21600     # s; after an aborted division before that parent may try again
DIVISIONS_OPEN_MAX = 1        # divisions; open at once, fleet-wide (also the unique index divisions_one_open)
DIVISION_STEP_EVERY = 2       # working ticks (meta working_tick_no); a division takes its parent node's slot at most every this many working ticks
FOCI_RETRIES = 1              # retries; a failed reproduce.sym answer retries this often at the next rung before the division aborts
DIVISION_MAX_TICKS = DIVISION_STEP_EVERY * (1 + FOCI_RETRIES + math.ceil(ASSIGN_MAX / ASSIGN_PER_SLOT)) + 3 + 12   # counted ticks (a working tick whose slot phase found the parent's node available); the slowest legal path (foci, one retry, every assign step, two workspace ticks, the commit) + 12 of slack; past it the division aborts
DIVISION_MAX_SECONDS = 86400  # s; wall-clock backstop: an open division older than this aborts, checked even while held
APOPTOSIS_IDLE_SECONDS = 86400   # s; an empty, idle cell with an active sibling retires after this long
QUARANTINE_FAILURES = 8       # items; consecutive terminal failed items before a cell is quarantined
EFFICIENCY_FLOOR = 0.2        # ratio; (done + abstained) / (program runs + 3 x agent runs) an organ needs to divide (an abstention is a checked answer, so it counts as useful work on purpose)
EFFICIENCY_MIN_RUNS = 20      # cost units; below this over the two prior UTC days, efficiency is not judged
LAST_CELL_AUTO_RELEASE = 86400   # s; an organ's only live cell, quarantined this long, is released automatically
AUTO_RELEASE_WINDOW = 7 * 86400  # s; at most one automatic release per cell in any rolling window of this length
NODE_OFFLINE_MOVE = 21600     # s; a cell whose node was reported offline in every sample this long moves to another node
OFFLINE_MIN_SAMPLES = 6       # samples; explicit offline samples needed inside NODE_OFFLINE_MOVE before a move
WORKSPACE_FAILURES_MAX = 3    # failures; workspace re-creations before the cell retires (or, as its organ's last cell, is quarantined)
ABSTAIN_WINDOW, ABSTAIN_RATE = 20, 0.9   # items / ratio; notice abstain_rate when >= 90 % of a cell's last 20 endings abstained
QUEUE_CAP_PER_ORGAN = 200     # items; at 200 or more queued items in an organ, a new non-owner item ends abstained (OVERFLOW)
RUNG_DOWN_HOLD = 7 * 86400    # s; after a rung_up of a program in a cell, no rung_down of it for this long
# agent runs
AGENT_RUNS_LIVE_MAX = 2       # runs; LIFE autogen runs submitting/live/submit_unknown at once, fleet-wide (1 per cell)
AGENTS_PER_RUN = 4            # agents; agents_max of every LIFE agent run (policies/*.json)
AGENT_WALL_SECONDS = 2700     # s; wall_seconds of every LIFE agent run (policies/*.json)
AGENT_RUN_KILL_SECONDS = 3000   # s; the tick asks to cancel a LIFE run still live this long after submission (a failure); = NODE_BUSY_MAX, and an agent start needs its node idle of LIFE work for the last NODE_WINDOW
AGENT_RUN_MIB = 4096          # MiB; extra memAvailMiB a node needs for a model action while a LIFE agent run is live on it
RUN_UNKNOWN_NOTICE = 900      # s; a run LIFE cannot confirm this long opens notice run_unknown
START_TIMEOUT = 180           # s; bin/symblic-task start (untracked: STOP's watcher never ends it; STOP re-requests the cancel of its run id at every tick while STOP exists)
CANCEL_TIMEOUT = 60           # s; bin/symblic-task autogen cancel
CATALOG_TIMEOUT = 60          # s; bin/symblic-task catalog --json and bin/local-research --list
NEEDS_WORK_MAX = 2            # rounds; reviewer needs_work rounds per finding before it goes to the operator
FINDING_CUTS = (700, 500, 300, 150, 80)   # characters; finding_text lengths tried in turn until both statements fit STATEMENT_MAX (the review note is never cut: render fails instead)
# UTC-day budgets; charged (reserved) before the work starts, never refunded; a spent budget holds that class until 00:00 UTC
PROGRAM_RUNS_PER_DAY = 1200   # runs; genome program runs, research runs and division steps
MODEL_CALLS_PER_DAY = 14400   # model calls; reserved: 12 per program run, RESEARCH_GENERATIONS per research run
AGENT_RUNS_PER_DAY = 12       # runs; agy autogen runs (each up to 4 agents)
BENCH_JOBS_PER_DAY = 12       # jobs; benchmark cluster jobs
BIRTHS_PER_DAY = 8            # cells; children born (2 per division)
SELF_QUESTIONS_PER_DAY = 2    # questions; derived questions learning asks itself
# learning and digest
QUESTION_DRY_LIMIT = 3        # runs; research runs in a row that add no new question-source link before a question is exhausted
QUESTION_SOURCE_LIMIT = 9     # links; usable question-source links per question before it is done
NEW_SOURCES_PER_RUN = 3       # links; at most min(3, 9 - found) links are recorded from one research run
SELF_QUESTION_QUEUE_MAX = 3   # questions; derived questions are made only while learning has fewer queued questions
SELF_QUESTION_CANDIDATES = 50   # rows; the newest knowledge rows scanned for one derived question
QUESTION_CHARS = 600          # characters; a research question (longer operator text: notice command_too_long)
SOURCE_TEXT_CHARS = 6000      # characters; text kept per source snapshot
SOURCE_TEXT_MIN = 200         # characters; shorter fetched text is EMPTY (abstained)
SOURCE_KEY_MAX = 200          # characters; a source key (longer items_key results become sha256: keys)
URL_MAX = 2000                # characters; a research URL LIFE records
ANSWER_CHARS = 4000           # characters; a research answer kept in table answers
FETCHES_PER_TICK = 4          # fetches; source fetches per tick
FETCH_TIMEOUT = 240           # s; one bin/life-fetch.py process (safe_fetch: robots + 5 hops x (10 + 25) s + parsing)
FETCH_MEMORY = '1G'           # bytes (systemd); MemoryMax of the scope each fetch runs in (also prlimit --as)
FETCH_AS_BYTES = 1024 ** 3    # bytes; prlimit --as of the fetch process
# codebase
WATCH_MAX = 20                # tests; watch.txt lines read
WATCH_TIMEOUT = 120           # s; one watched-test run (= symblicos/autogen.py CHECK_TIMEOUT)
WATCH_SLOW = 90               # s; wall time of a sandboxed run (scope and sandbox start-up included) above which a test is never patched
WATCH_BACKOFF = (21600, 43200, 86400, 172800)   # s; 6 h, 12 h, 24 h, then 48 h between runs of a failing test
TAIL_LINES = 40               # lines; output tail kept from a failing test
FINDING_CHARS = 600           # characters; a finding_text
TEST_ID_MAX = 160             # characters; a test id (at most 5 components after tests, each 1..64)
GATE_TIMEOUT = 900            # s; checks/devcheck-gate.sh as a whole
GATE_DEVCHECK_TIMEOUT = 600   # s; the gate's sandboxed ./bin/devcheck --changed BASE (checks/devcheck-gate.sh; VALIDATE compares)
GATE_TEST_TIMEOUT = 240       # s; the gate's sandboxed focused unittest (checks/devcheck-gate.sh; VALIDATE compares)
SANDBOX_CHECK_TIMEOUT = 110   # s; life-check.py sandboxed default (inside autogen's 120 s check timeout)
SANDBOX_TIMEOUT_MAX = 900     # s; the largest --timeout life-check.py sandboxed accepts
DIFF_MAX_BYTES = 262144       # bytes; larger diffs are refused at the gate
DIFF_REVIEW_BYTES = 6000      # bytes; a diff larger than this is not model-reviewed: it goes to the operator
LOCAL_FIX_FILES_MAX = 3       # files; a local_fix may change at most these traceback files
LOCAL_FIX_FUNCTIONS_MAX = 3   # functions; a local_fix may change at most these function bodies, each named in the traceback
GIT_TIMEOUT = 120             # s; one local git command
GIT_FETCH_TIMEOUT = 300       # s; git fetch of a codebase clone
CLONE_TIMEOUT = 600           # s; one whole workspace creation (its git steps share this one deadline)
GENOME_MAX_BYTES = 65536      # bytes; a genome program file read by the gates and life-check
VERIFY_MAX_BYTES = 400        # bytes; verify.txt read by life-check
# stage budgets: a stage starts only when elapsed + budget + KILL_GRACE + START_MARGIN <= TICK_HARD; its processes share the budget
WATCH_STAGE_SECONDS = 600     # s; one watched test: refresh the clone, run the test, reset
CONFIRM_STAGE_SECONDS = 600   # s; one operator-finding confirmation
GATE_STAGE_SECONDS = GATE_TIMEOUT + 300   # s; one codebase gate: stage, diff, the gate script, re-stage, bundle, reset
SELFDEV_GATE_STAGE_SECONDS = 300   # s; one selfdev gate
START_STAGE_SECONDS = START_TIMEOUT + GIT_FETCH_TIMEOUT + 120   # s; one agent start: reset, sync, render, submit
# compute
BENCH_PAIRS = 3               # pairs; baseline/candidate pairs per experiment, in ABBA order
BENCH_WARMUP_ORDER = ('baseline', 'candidate')   # runs; discarded warm-ups, one per variant, before the scored runs
BENCH_WARMUP_RUNS = len(BENCH_WARMUP_ORDER)   # runs; discarded runs per job
BENCH_ORDER = ('baseline', 'candidate', 'candidate', 'baseline', 'baseline', 'candidate')   # runs; the scored order after the warm-up (pair k = the k-th baseline and the k-th candidate)
BENCH_RUNS = BENCH_WARMUP_RUNS + 2 * BENCH_PAIRS   # runs; per job
BENCH_TIMEOUT_MIN, BENCH_TIMEOUT_MAX = 30, 300   # s; per run, operator template field
BENCH_RUN_SLACK = 10          # s; timeout --kill-after per run
BENCH_JOB_EXTRA = 60          # s; job timeout = BENCH_RUNS x (T + BENCH_RUN_SLACK) + this
BENCH_GRACE = 300             # s; a job past its timeout + this, still not terminal, goes to the operator (node held)
BENCH_OUT_BYTES = 4096        # bytes; output kept per run (head -c): 8 runs x (4096 + markers) stay under cluster_engine.OUT_HEAD 40000; a longer output is truncation (LIFE_TRUNC) and fails the experiment
JOB_CANCEL_TIMEOUT = 30       # s; POST /api/cluster/job/cancel
JOBS_PAGE, JOBS_PAGES_MAX = 200, 5   # jobs / pages; the jobs listing is read in pages of 200, at most 5 per tick (a capped or changing listing never proves absence)
BENCH_AS_BYTES = 4 * 1024 ** 3   # bytes; prlimit --as for every benchmark run
BENCH_FSIZE_BYTES = 2 * 1024 ** 3   # bytes; prlimit --fsize for every benchmark run
BENCH_NOFILE = 256            # files; prlimit --nofile for every benchmark run
PARAM_RX = re.compile(r'[A-Za-z0-9._:+][A-Za-z0-9._:+-]{0,63}')   # every benchmark parameter and baseline (fullmatch; never a leading -)
PARAM_RX_MAX = 200            # characters; an operator param_rx, which must also match PARAM_GRAMMAR_RX (a linear-time subset)
BENCH_FILE_MAX_BYTES = 65536  # bytes; control/benchmarks.json
BENCH_MAX = 20                # entries; benchmarks in control/benchmarks.json
CATALOGUE_CHARS = 3000        # characters; the catalogue shown to propose-experiment.sym: whole entries in id order while they fit, never a cut entry
# database
MIGRATION_MAX_BYTES = 16384   # bytes; one migration file
MIGRATION_STATEMENTS_MAX = 24   # statements; per migration
SNAPSHOT_MAX_BYTES = 262144   # bytes; schema-snapshot.sql
MIGRATION_NUMBER_MAX = 9999   # number; after it the database organ holds (notice migration_numbers)
MIGRATION_SECONDS = 120       # s; SQLite progress deadline of a migration's validation, and of its apply transaction
ORGANISM_MAX_BYTES = 512 * 1024 ** 2   # bytes; physical footprint (file + -wal + -shm) of organism.sqlite3 above which the database organ holds (notice storage)
ORGANISM_VALIDATE_MAX_BYTES = 64 * 1024 ** 2   # bytes; logical size (page_count x page_size) up to which a migration is validated on an in-memory copy WITH its rows
STORE_ROWS_PER_TICK = 500     # attempts; (table, knowledge row) insert attempts across every store table per tick, tables served round-robin (meta store_next)
APPLY_STAGE_SECONDS = 2 * MIGRATION_SECONDS + GIT_TIMEOUT   # s; one migration apply (validation and transaction, MIGRATION_SECONDS each, plus git)
REQUEST_MIN_CHARS, REQUEST_MAX_CHARS = 10, 600   # characters; a data request
LESSON_MIN_CHARS, LESSON_MAX_CHARS = 10, 300   # characters; a lesson
# upkeep, storage, observability
CANARY_EVERY_SECONDS = 3600   # s; canary round period (a never-passed or failed round runs at every tick)
CANARY_TIMEOUT = 60           # s; one canary line
CANARY_ROUND_SECONDS = 600    # s; the whole round
BACKUP_KEEP = 7               # files; daily backup files kept per database
PREMIGRATION_KEEP = 10        # files; organism-before-<id> copies kept (newest first, also within PREMIGRATION_KEEP_BYTES)
PREMIGRATION_KEEP_BYTES = 2 * 1024 ** 3   # bytes; organism-before-<id> copies kept in total, newest first
CODEBASE_CLONE_BYTES = 1_600_000_000   # bytes; one codebase clone, measured 2026-10-11 (pack 762502 KiB + a 768 MB sparse checkout)
AGENT_CHECKOUT_BYTES = 800_000_000   # bytes; one hub worktree of the branch on the host (<workspace>.agents/<name>: the 786 MB tree, objects shared) until LIFE discards it
STATE_BASE_BYTES = 2 * 1024 ** 3   # bytes; the registry, texts, calls, runs, bundles, reports and logs
STATE_MAX_BYTES = ORGAN_CELL_CAP * CODEBASE_CLONE_BYTES + AGENT_RUNS_LIVE_MAX * AGENTS_PER_RUN * AGENT_CHECKOUT_BYTES + STATE_BASE_BYTES + (1 + BACKUP_KEEP) * ORGANISM_MAX_BYTES + PREMIGRATION_KEEP_BYTES   # bytes (allocated); STATE plus every PROJECTS/life-* path (workspaces and their .agents siblings): the sum of the parts named here
STORAGE_EVERY_TICKS = 12      # ticks; the storage walk runs on ticks 1, 13, 25, ... (the free-space check every tick)
STORAGE_WALK_SECONDS = 120    # s; wall budget of one storage walk; a walk that passes it keeps the previous total and says so in the log
DISK_FREE_MIN = 5 * 1024 ** 3   # bytes; free space on the STATE and PROJECTS filesystems below which new work holds (also checked before every heavy the host stage)
BACKUP_MARGIN_BYTES = 64 * 1024 ** 2   # bytes; a backup starts only with its source size + this free
LOG_ROTATE_BYTES = 5 * 1024 ** 2   # bytes; tick.log rotates past this (three archives tick.log.1..3)
CALLS_KEEP_DAYS = 14          # days; STATE/calls/<id>/ folders whose call ended this long ago are deleted at the daily backup
CALL_ROWS_KEEP_DAYS = 90      # days; calls rows that ended this long ago are deleted at the daily backup
RUNS_DIR_KEEP_DAYS = 14       # days; STATE/runs/<request_id>/ of collected runs that ended this long ago are deleted
INBOX_DONE_KEEP_DAYS = 30     # days; inbox-done files older than this are deleted
NOTICES_KEEP_DAYS = 90        # days; acknowledged notices older than this are deleted
SAMPLES_KEEP_DAYS = 7         # days; samples older than this are deleted
TMP_KEEP_SECONDS = 86400      # s; abandoned .life-tmp-*, release .tmp-* and inbox-tmp files older than this are removed
HOLD_NOTICE_TICKS = 12        # ticks; the same hold this many ticks in a row opens notice held
TEMP_MISSING_SAMPLES = 12     # samples; a node without a temperature this many samples in a row opens notice telemetry
NO_CAPACITY_TICKS = 12        # ticks; armed working ticks in a row with queued slot items and no node passing node_ok open notice no_capacity
FAULTS_IN_A_ROW_MAX = 3       # ticks; tick faults in a row before the fault hold (life-ctl clear-fault)
REPORT_COMMANDS_PER_TICK = 20   # commands; dispatched commands examined for a report per tick (least recently examined first)
REPORT_ITEMS_MAX = 500        # items; listed in one report (the report says when it is cut)
REPORT_TRAVERSE_MAX = 5000    # items; a command's descendants are followed this far; past it the report waits (notice report_truncated)
APPROVAL_STALE_DAYS = 7       # days; a lesson or request waiting for approval this long counts as ended for its command's report
OUTPUT_KEEP_BYTES = 1 << 20   # bytes; stdout kept per process
ERR_KEEP_BYTES = 1 << 16      # bytes; stderr kept per process
OUTPUT_KILL_BYTES = 16 << 20  # bytes; a process writing more than this (stdout + stderr) is ended and returns OUTPUT_LIMIT_RC
OUTPUT_LIMIT_RC = 1000        # rc; the return code Procs.run gives an output-limit kill (never a real exit code)
STOPPED_RC = 1001             # rc; the return code Procs.run gives a process STOP ended (never counted as a failure, infra or fault)
NOT_ADMITTED_RC = 1002        # rc; the return code Procs.run gives when admission refused before any process existed (nothing counts)
HTTP_MAX_BYTES = 8 << 20      # bytes; a loopback HTTP answer
HTTP_OUTSTANDING_MAX = 4      # exchanges; loopback exchanges still open past their deadline; at this many a new one is refused (Telemetry)
GIT_META_MAX_ENTRIES = 50000  # entries; .git administrative entries git_meta_sha256 visits; more is a workspace problem
GIT_META_MAX_BYTES = 16 << 20   # bytes; content git_meta_sha256 hashes; more is a workspace problem
JSON_MAX_DEPTH = 32           # levels; a loopback JSON answer nested deeper is refused
# metabolism (LIFE.md section 10)
FLEET_LOAD5_PER_CPU = 0.5     # ratio; vitals.load[1] (5-minute load average) / vitals.cpus at or above: the node is loaded in this sample
LOADED_OWN_FRACTION = 0.5     # ratio; or LIFE kept the node busy this fraction of the interval
FLEET_LOADED_FRACTION = 0.5   # ratio; at least max(1, ceil(this x online LIFE nodes)) loaded nodes: the fleet is loaded
WORK_WINDOW = 3000            # s; loaded (or unobserved) seconds before the fleet must rest
REST_SECONDS = 600            # s; consecutive observed quiet seconds that end a rest and reset the window
NODE_WINDOW, NODE_BUSY_MAX, NODE_REST = 3600, 3000, 1800   # s; per node: an action is admitted only if busy + its budget <= 3000 of the last 3600; busy >= 3000 rests it 1800 idle s
NODE_BUSY_PER_DAY = 6 * 3600  # s; LIFE busy seconds per node per UTC day; over it the node takes no LIFE action until 00:00 UTC
TELEMETRY_REFRESH = 120       # s; the slot phase re-reads every governor input when the sample is older than this
HOT_C, COOL_C = 85.0, 75.0    # deg C; same thresholds as symblic_apply.THERMAL_HOT/THERMAL_COOL (hysteresis)
TEMP_MIN_C, TEMP_MAX_C = -50.0, 150.0   # deg C; a temperature outside is unavailable (treated as hot)
MEM_RESERVE_MIB = 2048        # MiB; a node needs memAvailMiB >= reserve + the model's size + KV_ALLOWANCE_MIB (+ AGENT_RUN_MIB with a live agent run)
KV_CTX_TOKENS = 4096          # tokens; the worker node context bucket every LIFE prompt reaches (fleet_runner: num_ctx = smallest bucket >= chars // 3 + 256 + num_predict)
PROMPT_CHARS_MAX = 9000       # characters; the largest LIFE program prompt (a 6000-character source or diff plus the instruction and fields); VALIDATE: it fits KV_CTX_TOKENS
KV_ALLOWANCE_MIB = -(-(KV_CTX_TOKENS * 4 * 36000) // 2 ** 20) + 256   # MiB; fleet_runner._kv_bytes for a 4B model at KV_CTX_TOKENS (KV_BYTES_PER_TOKEN_B 36000, pinned) + OLLAMA_OVERHEAD 256 MiB
MODEL_MIB_UNKNOWN = 4096      # MiB; memory assumed for a model missing from MODEL_MIB
HOST_LOAD_FRACTION = 0.75  # ratio; the host load1 must stay below this x os.cpu_count()
HOST_IO_FULL_AVG60 = 10.0  # %; the host /proc/pressure/io full avg60 must stay below this
HOST_MEM_FLOOR_MIB = 6144  # MiB; the host MemAvailable must be at least this (a 4 GiB scope + 2 GiB reserve)
HOST_MEM_SOME_AVG60 = 10.0   # %; the host /proc/pressure/memory some avg60 must stay below this
# units and adapter timeouts
HOUR, DAY = 3600, 86400       # s; units
HTTP_TIMEOUT = 30             # s; one loopback GET or POST that should answer at once (one deadline for the whole exchange)
HTTP_SLOW_TIMEOUT = 60        # s; /api/cluster/status (it may probe), autogen get, the jobs listing, map submit
SQLITE_TIMEOUT = 5            # s; a connection waits this long for another writer (busy_timeout 5000 ms)
CTL_LOCK_WAIT = UNIT_TIMEOUT  # s; life-ctl waits this long for the tick's lock (a progress line every CTL_LOCK_PROGRESS s)
CTL_LOCK_PROGRESS = 60        # s; life-ctl prints that it is waiting this often
SEED_LOCK_WAIT = 60           # s; seed waits this long for the lock
VALIDATE_TIMEOUT = 900        # s; seed and arm run VALIDATE.sh with this timeout
# sizes
PAYLOAD_MAX = 16384           # characters; an item payload (JSON); a larger one is refused before the write
COMMAND_MIN_BYTES = 6         # bytes; one operator command after stripping (status is the shortest), inbox, life-ctl command and agenda alike
COMMAND_MAX_BYTES = 4000      # bytes; one operator command (inbox file or agenda text)
INBOX_PER_TICK = 50           # files; inbox files taken per tick
AGENDA_MAX = 20               # entries; agenda entries read (more: notice agenda_invalid)
AGENDA_FILE_MAX_BYTES = 131072   # bytes; control/agenda.json
WATCH_FILE_MAX_BYTES = 16384  # bytes; control/watch.txt
AGENDA_HOURS_MIN, AGENDA_HOURS_MAX = 6, 720   # hours; an agenda entry's period

# ------------------------------------------------------------------------------------------- small helpers


def now():
    return int(time.time())


def utc_day(t=None):
    return time.strftime('%Y-%m-%d', time.gmtime(now() if t is None else t))


def sha(*parts):
    """sha256 hex of the parts joined by newlines (identity parts never contain a newline: see item_id)."""
    return hashlib.sha256('\n'.join(str(p) for p in parts).encode('utf-8')).hexdigest()


def sha16(*parts):
    return sha(*parts)[:16]


def file_sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 16), b''):
            h.update(block)
    return h.hexdigest()


def item_id(organ, kind, *parts):
    """<organ>:<first 16 hex of sha256(kind + "\\n" + parts joined by "\\n")>. A part holding a newline is refused,
    so two different identities can never serialize to the same text."""
    if any('\n' in str(p) for p in (kind, *parts)):
        raise ValueError('an identity part contains a newline')
    return f'{organ}:{sha16(kind, *parts)}'


CELL_RX = re.compile(r'(command|learning|digest|codebase|immune|selfdev|compute|database)\.(0|[1-9]|10)\.([0-9a-f]{8})')


def cell_id(organ, depth, hex8):
    return f'{organ}.{depth}.{hex8}'


def parse_cell(cid):
    """(organ, depth, hex8) of a canonical cell id (depth spelled 0..10 without leading zeros)."""
    m = CELL_RX.fullmatch(cid or '')
    if not m:
        raise ValueError(f'not a cell id: {cid!r}')
    return m.group(1), int(m.group(2)), m.group(3)


def workspace_for(cid):
    """The one git workspace of an agent cell: PROJECTS/life-<organ>-<depth>-<hex8> (None for model cells)."""
    organ, depth, hex8 = parse_cell(cid)
    return f'{PROJECTS}/life-{organ}-{depth}-{hex8}' if organ in AGENT_ORGANS else None


def request_id_for(cid, iid, attempt):
    """life-<organ>-<depth>-<hex8>-<item 16 hex>-<attempt>: the full cell identity, so no two cells share ids."""
    organ, depth, hex8 = parse_cell(cid)
    return f'life-{organ}-{depth}-{hex8}-{iid.split(":")[1]}-{attempt}'


TEST_ID_RX = re.compile(r'tests\.[A-Za-z0-9_]{1,64}(?:\.[A-Za-z0-9_]{1,64}){0,4}')


def valid_test_id(text):
    """tests.<module>[.<Class>[.<test>]]: at most TEST_ID_MAX characters, at most 5 components after tests, each 1..64."""
    return isinstance(text, str) and len(text) <= TEST_ID_MAX and bool(TEST_ID_RX.fullmatch(text))


# Credential-shaped VALUES, not words, in two tiers (LIFE.md section 11). Every key word below is listed there.
# The key words match in any case; the token prefixes (sk-, ghp_, github_pat_, xox?-, AKIA) and the private-key header
# match only as written (upper case BEGIN ... PRIVATE KEY), so prose like "akia" or "begin the private key" passes.
#  STRICT (SECRET_RX: operator text, web text, template values, research URLs, notice and log text): a key word, then : or
#    =, then a quoted value of 6+ characters or an unquoted run of 6+ non-space characters. "password = hunter22x" and
#    'PASSWORD: "two words here"' are credentials; "research password hashing" is not.
#  CODE (SECRET_CODE_RX: patch diffs only): a key word, then : or =, then a quoted value of 8+ characters, or an
#    unquoted run of 16+ characters of [A-Za-z0-9+/=_-] holding at least one digit and not followed by a word
#    character, ( [ or . (so token = request.headers.get('X-Token'), password = getpass.getpass() and
#    def check_token(token=None) are code, not credentials). Both tiers share every fixed-prefix rule.
SECRET_KEYWORDS = (r'api[_-]?key|access[_-]?token|auth[_-]?token|secret[_-]?key|client[_-]?secret|passw(?:or)?d|'
                   r'token|secret|credentials?|private[_-]?key')
_SECRET_FIXED = (r'\b(?i:bearer)\s+[A-Za-z0-9._~+/-]{16,}=*|BEGIN [A-Z ]*PRIVATE KEY|'
                 r'sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[abp]-[A-Za-z0-9-]{10,}|'
                 r'AKIA[0-9A-Z]{16}|(?i:https?)://[^/\s:@]+:[^/\s@]+@')
SECRET_RX = re.compile(r'\b(?i:' + SECRET_KEYWORDS + r')\s*[:=]\s*(?:[\'"][^\'"\n]{6,}[\'"]|[^\s\'"]{6,})|'
                       + _SECRET_FIXED)
SECRET_CODE_RX = re.compile(r'\b(?i:' + SECRET_KEYWORDS + r')\s*[:=]\s*(?:[\'"][^\'"\n]{8,}[\'"]|'
                            r'(?=[A-Za-z0-9+/=_-]{16,}(?![\w(\[.]))[A-Za-z0-9+/=_-]*\d[A-Za-z0-9+/=_-]*(?![\w(\[.]))|'
                            + _SECRET_FIXED)


def has_secret(text):
    """The STRICT tier (operator and web text, template values, URLs)."""
    return bool(SECRET_RX.search(text or ''))


def has_secret_code(text):
    """The CODE tier (patch diffs): a credential-shaped literal, never an identifier or an expression."""
    return bool(SECRET_CODE_RX.search(text or ''))


def redact(text):
    """The text with every STRICT credential-shaped span replaced by [redacted] (findings, pages and notices keep the
    rest)."""
    return SECRET_RX.sub('[redacted]', text or '')


def plain_line(text, limit):
    """NFC, every control character and newline as one space, whitespace collapsed, cut to `limit`: for operative text
    passed as an argument (a research question), where braces and backticks keep their meaning."""
    text = unicodedata.normalize('NFC', str(text or ''))
    text = ''.join(' ' if unicodedata.category(c).startswith('C') else c for c in text)
    return re.sub(r'\s+', ' ', text).strip()[:limit].rstrip()


def one_line(text, limit):
    """NFC, every control character and newline as one space, whitespace collapsed, backticks and
    braces removed (they would break a statement or a template), cut to `limit` characters."""
    text = unicodedata.normalize('NFC', str(text or ''))
    text = ''.join(' ' if unicodedata.category(c).startswith('C') else c for c in text)
    text = re.sub(r'[`{}]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:limit].rstrip()


# symblic_autogen.lint warns on these back-references; a rendered statement must lint with ZERO findings
LINT_REWRITES = ((r'\bthe previous\b', 'the prior'), (r'\bthe last\b', 'the final'), (r'\bas before\b', 'as stated'),
                 (r'\blike above\b', 'as stated'), (r'\bearlier\b', 'before'))


def lint_safe(text, limit):
    """one_line plus the LINT_REWRITES (case-insensitive), so free text inside a template never trips lint."""
    text = one_line(text, limit)
    for rx, repl in LINT_REWRITES:
        text = re.sub(rx, repl, text, flags=re.I)
    return text[:limit].rstrip()


def norm_text(text):
    """The identity form of free text: NFC, lower case, whitespace collapsed."""
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', str(text or '')).lower()).strip()


def words(text):
    """The routing words of a text: norm_text, then every run of 4 or more letters."""
    return set(re.findall(r'[^\W\d_]{4,}', norm_text(text)))


def boot_id():
    with open('/proc/sys/kernel/random/boot_id', encoding='ascii') as handle:
        return handle.read().strip()


KIT_CODE_DIRS = ('bin', 'checks', 'db', 'units')
KIT_CODE_FILES = ('VALIDATE.sh',)


def kit_sha256():
    """sha256 over every entry under KIT/bin, checks, db and units (directories, __pycache__ included, and every
    file of any type) plus VALIDATE.sh, in sorted relative-path order: a regular file as path, NUL, f, its mode bits,
    its content sha256; a symlink as path, NUL, l, its target; a directory as path, NUL, d; anything else as path,
    NUL, x. So a new symlink, a changed mode bit or a stray .pyc changes the hash. life-ctl arm records it; a tick
    whose kit differs holds (integrity)."""
    h = hashlib.sha256()

    def add(path):
        rel = os.path.relpath(path, KIT).encode()
        st = os.lstat(path)
        if stat.S_ISLNK(st.st_mode):
            h.update(rel + b'\0l\0' + os.readlink(path).encode() + b'\n')
        elif stat.S_ISREG(st.st_mode):
            h.update(rel + b'\0f\0' + oct(st.st_mode & 0o7777).encode() + b'\0' + file_sha(path).encode() + b'\n')
        elif stat.S_ISDIR(st.st_mode):
            h.update(rel + b'\0d\n')
        else:
            h.update(rel + b'\0x\n')
    for sub in KIT_CODE_DIRS:
        base = os.path.join(KIT, sub)
        add(base)
        for root, dirs, files in os.walk(base):
            dirs.sort()
            for name in sorted(dirs + files):
                add(os.path.join(root, name))
    for name in KIT_CODE_FILES:
        add(os.path.join(KIT, name))
    return h.hexdigest()


def decisions_sha256():
    """sha256 of DECISIONS.md (the operator's requirements decisions); arm records it with the operator's confirmation."""
    return file_sha(DECISIONS_FILE)


# Platform files LIFE executes or imports outside the server process: their bytes are recorded at arm, and a
# different byte anywhere is an integrity hold until the operator reads the change, runs VALIDATE.sh and arms again.
PLATFORM_PINS = ('landlock_sandbox.py', 'deep_research.py', 'local_research.py', 'bin/symblic-task', 'symblic_autogen.py',
                 'bin/symblic', 'symblic_run.py', 'symblic_apply.py', 'fleet_runner.py', 'bin/local-research')
# Pinned by bytes: the files LIFE's own processes execute or import on the host (the sandbox launcher, the fetch and
# research path, the task CLI, the program runner and its fleet-runner client). The server-side files LIFE only talks to are
# pinned by CONTRACT regexes instead (a platform edit there does not disarm LIFE unless a pinned fact changes). The
# transitive imports of these files are not byte-pinned (GAP 18).


def platform_sha256():
    h = hashlib.sha256()
    for rel in PLATFORM_PINS:
        h.update(rel.encode() + b'\0' + file_sha(os.path.join(REPO, rel)).encode() + b'\n')
    return h.hexdigest()


PRIVATE_ROOTS = ('/home/operator/.ssh', '/home/operator/.config', REPO)   # never under a sandbox read-exec grant


def state_problems():
    """Every STATE directory must be a real directory (lstat, no symlink) owned by this uid with mode EXACTLY 0700
    (stat.S_IMODE == 0o700: 0500 or 0000 fail too); the registry, the organism database, their -wal files and the two
    lock files, when they exist, must be regular files owned by this uid with no group or other permission and one
    link; and no read-exec directory the sandbox is given (devcheck_tools) may contain STATE or a PRIVATE_ROOTS path."""
    out, uid = [], os.getuid()
    for path in STATE_DIRS:
        try:
            st = os.lstat(path)
        except OSError as exc:
            out.append(f'{path}: {exc.strerror}')
            continue
        if not stat.S_ISDIR(st.st_mode):
            out.append(f'{path} is not a real directory')
        elif st.st_uid != uid or stat.S_IMODE(st.st_mode) != 0o700:
            out.append(f'{path} must be owned by uid {uid} with mode exactly 0700 (it is {oct(stat.S_IMODE(st.st_mode))})')
    for path in (REGISTRY, REGISTRY + '-wal', ORGANISM, ORGANISM + '-wal', LOCK_FILE, CONTROL_LOCK):
        try:
            st = os.lstat(path)
        except FileNotFoundError:
            continue
        except OSError as exc:
            out.append(f'{path}: {exc.strerror}')
            continue
        if not stat.S_ISREG(st.st_mode) or st.st_uid != uid or st.st_mode & 0o077 or st.st_nlink != 1:
            out.append(f'{path} must be a regular file owned by uid {uid}, without group or other permission, with one link')
    for d in devcheck_tools()[1]:
        for p in (STATE,) + PRIVATE_ROOTS:
            if p == d or p.startswith(d.rstrip('/') + '/'):
                out.append(f'the sandbox read-exec grant {d} contains {p}')
    return out


def ensure_dirs():
    for path in STATE_DIRS:
        os.makedirs(path, mode=0o700, exist_ok=True)


def read_owner_file(path, limit):
    """The bytes of an operator file (control/*, an inbox file): opened with O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC (a FIFO
    never blocks, a symlink is refused), checked ON THE OPEN DESCRIPTOR to be a regular file owned by this uid, read
    up to `limit` bytes. Raises OSError (FileNotFoundError when absent) on any rule failure or a larger file."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid():
            raise OSError(f'{os.path.basename(path)} is not a regular file owned by the operator')
        data = b''
        while len(data) <= limit:
            chunk = os.read(fd, limit + 1 - len(data))
            if not chunk:
                break
            data += chunk
    finally:
        os.close(fd)
    if len(data) > limit:
        raise OSError(f'{os.path.basename(path)} is larger than {limit} bytes')
    return data


def read_in(root, rel, limit):
    """The bytes of a regular file `rel` inside the folder `root`, opened relative to root's descriptor one component
    at a time with O_NOFOLLOW (a symlink anywhere, an absolute path, an empty, . or .. component is refused), checked on
    the open descriptor (a regular file), read up to `limit` bytes; OSError on any rule failure or a larger file.
    Nothing is checked and then reopened by name. life-check, the gates, the migration apply and traceback resolution
    read candidate-written files only through this."""
    parts = rel.split('/')
    if os.path.isabs(rel) or any(p in ('', '.', '..') for p in parts):
        raise OSError(f'{rel} must be a relative path inside the folder')
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts[:-1]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        ffd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    finally:
        os.close(fd)
    try:
        if not stat.S_ISREG(os.fstat(ffd).st_mode):
            raise OSError(f'{rel} is not a regular file')
        data = b''
        while len(data) <= limit:
            chunk = os.read(ffd, limit + 1 - len(data))
            if not chunk:
                break
            data += chunk
    finally:
        os.close(ffd)
    if len(data) > limit:
        raise OSError(f'{rel} is larger than {limit} bytes')
    return data


def write_atomic(path, data, mode=0o600):
    """Write a new random temporary file in the same directory (O_EXCL, mode), fsync it, rename it over
    `path`, then fsync the directory. Never follows or reuses an existing temporary path."""
    directory = os.path.dirname(path) or '.'
    tmp = os.path.join(directory, f'.{os.path.basename(path)}.tmp-{secrets.token_hex(8)}')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    fsync_dir(directory)


def fsync_dir(directory):
    dfd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def publish_noreplace(src, dest):
    """Move src to dest only if dest does not exist (os.link fails with EEXIST: never overwrites), then remove src.
    Returns False when dest exists."""
    try:
        os.link(src, dest, follow_symlinks=False)
    except FileExistsError:
        return False
    os.remove(src)
    fsync_dir(os.path.dirname(dest))
    return True


def open_lock(path):
    """The lock file opened for flock, created mode 0600 (never through a symlink)."""
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    return os.fdopen(fd, 'r+', encoding='utf-8')


def log(message):
    os.makedirs(LOGS, mode=0o700, exist_ok=True)
    path = LOGS + '/tick.log'
    try:
        if os.path.getsize(path) > LOG_ROTATE_BYTES:
            for n in (2, 1):
                if os.path.exists(f'{path}.{n}'):
                    os.replace(f'{path}.{n}', f'{path}.{n + 1}')
            os.replace(path, path + '.1')
    except OSError:
        pass
    line = f'{time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())} {one_line(redact(str(message)), 600)}'
    try:
        with open(path, 'a', encoding='utf-8', opener=lambda p, f: os.open(p, f, 0o600)) as handle:
            handle.write(line + '\n')
    except OSError:
        pass                                   # a full disk never blocks STOP or a tick's own handling
    print(line, flush=True)


# ------------------------------------------------------------------------------------------- control
ARMED_KEYS = ('boot_id', 'kit_sha256', 'platform_sha256', 'decisions_sha256')
HEX64_RX = re.compile(r'[0-9a-f]{64}')
BOOT_ID_RX = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')


def armed_read():
    """(state, data): 'absent' (no ARMED), 'valid' (exactly {"boot_id": a canonical boot id, "kit_sha256",
    "platform_sha256", "decisions_sha256": 64 lowercase hex each}, strict JSON: unique keys, at most 1024 bytes, a
    regular operator file read without following a link), 'malformed' or 'unreadable'. Only 'valid' can arm."""
    try:
        raw = read_owner_file(ARMED_FILE, 1024)
    except FileNotFoundError:
        return 'absent', None
    except OSError:
        return 'unreadable', None
    try:
        data = strict_json(raw.decode('ascii'))
    except (ValueError, UnicodeDecodeError):
        return 'malformed', None
    if not (isinstance(data, dict) and set(data) == set(ARMED_KEYS) and all(isinstance(v, str) for v in data.values())
            and BOOT_ID_RX.fullmatch(data['boot_id'])
            and all(HEX64_RX.fullmatch(data[k]) for k in ARMED_KEYS if k != 'boot_id')):
        return 'malformed', None
    return 'valid', data


def read_armed():
    """The ARMED object when it is valid, else None (absent, malformed and unreadable all read as disarmed)."""
    return armed_read()[1]


def _present_fail_closed(path):
    """An inhibiting switch (STOP, FREEZE): present when the path exists as anything at all, AND when control/ or the
    switch cannot be inspected (a permission or metadata change, GAP 16: fail closed). Before the seed (no control/
    folder) nothing is present."""
    try:
        os.lstat(path)
        return True
    except FileNotFoundError:
        pass
    except OSError:
        return True
    try:
        st = os.lstat(CONTROL)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return not stat.S_ISDIR(st.st_mode) or not os.access(CONTROL, os.R_OK | os.X_OK)


def stop_present():
    """STOP, fail-closed (_present_fail_closed). Every admission, the watcher and Procs.run read this."""
    return _present_fail_closed(STOP_FILE)


def grant_present(path):
    """A permission-granting switch (SELFDEV_ARMED, CODEBASE_HISTORY_OK; NO_SELF_QUESTIONS withdraws one): an EMPTY
    regular file owned by this uid, not writable by group or others, opened with O_NOFOLLOW | O_NONBLOCK and checked
    on the open descriptor. A dangling symlink, a directory, a FIFO, a non-empty or unreadable file grants nothing."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except OSError:
        return False
    try:
        st = os.fstat(fd)
        return stat.S_ISREG(st.st_mode) and st.st_uid == os.getuid() and not st.st_mode & 0o022 and st.st_size == 0
    finally:
        os.close(fd)


def agy_model():
    """The operator's agy model id from control/agy-model.txt (one line matching AGY_MODEL_RX, a regular operator file of
    at most 128 bytes), or '' when it is absent or invalid: agent organs then wait (notice agy_model)."""
    try:
        text = read_owner_file(AGY_MODEL_FILE, 128).decode('ascii').strip()
    except (OSError, UnicodeDecodeError):
        return ''
    return text if AGY_MODEL_RX.fullmatch(text) else ''


def control_state(hashes=True):
    """The operator's switches. ARMED counts only when it is valid and names THIS boot, so a reboot always comes back
    disarmed; kit_ok, platform_ok and decisions_ok say whether the kit code, the pinned platform files and DECISIONS.md
    still have the hashes recorded at arm (hashes=False skips them: they then read False); STOP and FREEZE are
    fail-closed; SELFDEV_ARMED and CODEBASE_HISTORY_OK are grants (grant_present); admit is the one admission answer:
    STOP absent, ARMED for this boot with all three hashes unchanged, FREEZE absent."""
    armed = read_armed()
    try:
        this_boot = boot_id()
    except OSError:
        this_boot = ''
    is_armed = bool(armed) and bool(this_boot) and armed['boot_id'] == this_boot

    def same(key, fn):
        if not (is_armed and hashes):
            return False
        try:
            return armed[key] == fn()
        except OSError:
            return False
    out = {'stop': stop_present(), 'freeze': _present_fail_closed(FREEZE_FILE), 'armed': is_armed,
           'kit_ok': same('kit_sha256', kit_sha256), 'platform_ok': same('platform_sha256', platform_sha256),
           'decisions_ok': same('decisions_sha256', decisions_sha256), 'selfdev': grant_present(SELFDEV_FILE),
           'self_questions': not os.path.lexists(NO_SELF_QUESTIONS_FILE),
           'history_ok': grant_present(HISTORY_OK_FILE)}
    out['admit'] = (not out['stop'] and out['armed'] and out['kit_ok'] and out['platform_ok'] and out['decisions_ok']
                    and not out['freeze'])
    return out


def host_problems():
    """Why the host cannot take heavy local work NOW ([] = it can): load1 >= HOST_LOAD_FRACTION x cpus, io full
    avg60 >= HOST_IO_FULL_AVG60, memory some avg60 >= HOST_MEM_SOME_AVG60, MemAvailable < HOST_MEM_FLOOR_MIB,
    or any of them unreadable. The governor reads it every tick; launch_allowed(heavy=True) reads it again immediately
    before every heavy the host process (watched test, confirmation, gate, clone, git fetch, page fetch) and
    life-check.py sandboxed before candidate code."""
    out = []
    try:
        with open('/proc/loadavg', encoding='ascii') as handle:
            load1 = float(handle.read().split()[0])
        if load1 >= HOST_LOAD_FRACTION * (os.cpu_count() or 1):
            out.append(f'the host load1 {load1:.2f}')
        for name, kind, limit in (('io', 'full', HOST_IO_FULL_AVG60), ('memory', 'some', HOST_MEM_SOME_AVG60)):
            with open(f'/proc/pressure/{name}', encoding='ascii') as handle:
                lines = [ln for ln in handle.read().splitlines() if ln.startswith(kind + ' ')]
            m = re.search(r'\bavg60=([0-9]+(?:\.[0-9]+)?)\b', lines[0]) if len(lines) == 1 else None
            if not m:
                out.append(f'the host {name} pressure unreadable')
            elif float(m.group(1)) >= limit:
                out.append(f'the host {name} {kind} avg60 {m.group(1)}')
        with open('/proc/meminfo', encoding='ascii') as handle:
            avail = [int(ln.split()[1]) for ln in handle if ln.startswith('MemAvailable:')]
        if len(avail) != 1:
            out.append('the host MemAvailable unreadable')
        elif avail[0] // 1024 < HOST_MEM_FLOOR_MIB:
            out.append(f'the host MemAvailable {avail[0] // 1024} MiB < {HOST_MEM_FLOOR_MIB}')
    except (OSError, ValueError, IndexError):
        out.append('the host load, pressure or memory unreadable')
    return out


def launch_allowed(heavy=False):
    """The final admission check made immediately before a slot action, a fetch, a gate, a watched test, a clone or
    an agent start creates its process: control_state()['admit'], and for heavy the host work also host_problems()
    empty and DISK_FREE_MIN free on the STATE and PROJECTS filesystems."""
    if not control_state()['admit']:
        return False
    if heavy:
        if host_problems():
            return False
        try:
            if min(shutil.disk_usage(p).free for p in (STATE, PROJECTS) if os.path.isdir(p)) < DISK_FREE_MIN:
                return False
        except (OSError, ValueError):
            return False
    return True


def heavy_allowed():
    return launch_allowed(heavy=True)


# ------------------------------------------------------------------------------------------- registry
SCHEMA_VERSION = '5'
# Every meta key LIFE writes, with its meaning; any other key is refused (Tick.set_meta).
META_KEYS = {
    'schema': 'registry schema version', 'seeded_at': 'seed time', 'seed_complete': '1 once the seed finished',
    'seed_kit_sha256': 'kit hash the seed started with (a resumed seed refuses a different kit)',
    'codebase_branch': 'the branch the codebase organ tracks (seed --branch)', 'platform_commit': 'HEAD at seed',
    'tick_no': 'ticks run', 'canary_at': 'last canary round', 'canary_failed': 'the failed canary lines, or empty',
    'canary_ok_ever': '1 once a round passed', 'fault_hold': 'set after FAULTS_IN_A_ROW_MAX tick faults',
    'faults_in_a_row': 'tick faults in a row', 'backup_day': 'UTC day of the last backup',
    'state_bytes': 'allocated bytes of STATE and the workspaces at the last walk', 'models_at': 'inventory time',
    'models': 'JSON {node: [models]}', 'watch_state': 'JSON {test: {next, ran, fails, finding, line, occurrence}}',
    'hold_reason': 'the first hold of the last tick', 'hold_ticks': 'ticks the same hold lasted',
    'agenda_state': 'JSON {entry revision: last period}', 'no_capacity_ticks': 'working ticks with no node fit',
    'migration_high': 'highest migration number ever allocated', 'store_marks': 'JSON {org table: last knowledge rowid}',
    'store_next': 'the org table the store adapter serves first next tick (round-robin)',
    'store_disabled': 'JSON {org table: schema sha256} of tables whose insert failed (until their schema changes)',
    'working_tick_no': 'admitted working ticks run (division steps count these)',
    'gate_selftest': 'kit_sha256 platform_sha256 test_id time of the last passing life-ctl gate-selftest',
    'models_retry': '1 when a node missing from a readable inventory needed a model (re-read after MODELS_RETRY_SECONDS)',
}


def connect(path=None, readonly=False):
    path = path or REGISTRY
    if readonly:
        conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=SQLITE_TIMEOUT, isolation_level=None)
    else:
        conn = sqlite3.connect(path, timeout=SQLITE_TIMEOUT, isolation_level=None)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=FULL')
    conn.execute('PRAGMA busy_timeout=5000')
    conn.execute('PRAGMA foreign_keys=ON')
    conn.row_factory = sqlite3.Row
    return conn


def apply_schema(conn, sql_path):
    with open(sql_path, encoding='utf-8') as handle:
        conn.executescript(handle.read())


class Tx:
    """BEGIN IMMEDIATE ... COMMIT, or ROLLBACK on any exception. A failed COMMIT is rolled back and re-raised,
    so no later step reuses a connection in an unknown transaction state."""

    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        self.conn.execute('BEGIN IMMEDIATE')
        return self.conn

    def __exit__(self, kind, value, tb):
        if kind is not None:
            if self.conn.in_transaction:
                self.conn.execute('ROLLBACK')
            return False
        try:
            self.conn.execute('COMMIT')
        except sqlite3.Error:
            if self.conn.in_transaction:
                self.conn.execute('ROLLBACK')
            raise
        return False


# Every notice kind, with its subject. The operator acknowledges a notice; acknowledging never clears the condition.
NOTICE_KINDS = {
    'stopped': 'STOP', 'integrity': 'state | release N | kit | platform | decisions', 'contract': 'platform',
    'canary_failed': 'canaries', 'storage': 'state | organism | backup', 'budget': '<budget column> <UTC day>',
    'held': 'the hold reason', 'telemetry': 'node', 'overflow': '<organ> <UTC day>', 'no_capacity': 'slots',
    'inbox_refused': 'first 16 hex of sha256(file name)', 'agenda_invalid': 'entry id or agenda.json',
    'agenda_skipped': 'entry id', 'command_too_long': 'command id', 'command_needs_test': 'command id',
    'command_needs_program': 'command id', 'command_database_confirm': 'command id', 'command_heartbeat': 'command id',
    'command_immune': 'command id', 'command_none': 'command id', 'command_merged': 'command id',
    'command_failed': 'command id', 'command_done': 'command id', 'report_truncated': 'command id',
    'approve_needed': 'item id', 'tracked_private_data': 'codebase', 'already_passing': 'item id',
    'watch_timeout': 'test id', 'watch_too_slow': 'test id', 'watch_error': 'test id', 'sandbox': 'landlock',
    'finding_owner': 'item id', 'finding_failed': 'item id', 'patch_ready': 'patch id', 'patch_test_only': 'patch id',
    'patch_repeat': 'patch id', 'proposal_ready': 'proposal id', 'review_owner': 'item id',
    'migration_applied': 'migration id', 'migration_numbers': 'database', 'migration_recovery_required': 'migration id',
    'migration_imported': 'migration id', 'store_table': 'org table', 'experiment_passed': 'experiment id',
    'benchmarks_missing': 'compute', 'benchmarks_invalid': 'benchmark id or benchmarks.json', 'bench_refused': 'experiment id',
    'job_unknown': 'job id or label', 'job_lost': 'job label', 'agy_not_ready': 'node', 'catalogue_shape': 'catalog',
    'inventory_shape': 'inventory', 'model_absent': '<node> <program>', 'workspace': 'workspace path',
    'quarantine': 'cell id', 'auto_released': 'cell id', 'moved': 'cell id', 'abstain_rate': 'cell id',
    'render': 'item id', 'run_unknown': 'run id', 'policy_mismatch': 'run id', 'infra_repeat': 'item id',
    'tick_fault': 'exception type', 'timeout_limit': 'item id', 'watch_invalid': 'watch.txt',
    'agy_model': 'agy-model.txt', 'agy_quota': 'node', 'gate_unproven': 'codebase', 'store_failed': 'org table',
    'node_cleanup': 'node', 'source_duplicate': 'source key', 'job_ambiguous': 'job label',
    'question_waiting': 'item id', 'clock': 'governor',
}


def notice_subject(subject):
    """The condition key of a notice subject: the full one_line subject when it has at most 120 characters, else its
    first 103 characters, '~' and 16 hex of sha256(full subject). Display shortening never merges two subjects."""
    s = one_line(subject, 4000)
    return s if len(s) <= 120 else s[:103] + '~' + sha(s)[:16]


def notice(conn, kind, subject, text):
    """Open an operator notice, or, when one with this kind and subject is already open, count the repeat
    (count + 1, last_at, text = the newest text). notice_id = first 12 hex of sha256(kind, subject, at, 8 random
    hex): unique per occurrence; (kind, subject) is the condition key. An unknown kind is a programming error."""
    if kind not in NOTICE_KINDS:
        raise ValueError(f'unknown notice kind {kind!r}')
    subject, text = notice_subject(subject), one_line(redact(text), 600)
    t = now()
    if conn.execute("UPDATE notices SET count=count+1, last_at=?, text=? WHERE kind=? AND subject=? AND state='open'",
                    (t, text, kind, subject)).rowcount:
        return
    conn.execute("INSERT INTO notices (notice_id, kind, subject, text, state, at, last_at, count) VALUES (?, ?, ?, ?, 'open', ?, ?, 1)",
                 (sha(kind, subject, t, secrets.token_hex(4))[:12], kind, subject, text, t, t))


BUDGET_COLUMNS = ('program_runs', 'model_calls', 'agent_runs', 'bench_jobs', 'births', 'self_questions')
METRIC_COLUMNS = ('items_done', 'items_failed', 'items_abstained', 'program_runs', 'agent_runs')


def budget_row(conn, day=None):
    day = day or utc_day()
    conn.execute('INSERT OR IGNORE INTO budget (day) VALUES (?)', (day,))
    return conn.execute('SELECT * FROM budget WHERE day=?', (day,)).fetchone()


def budget_add(conn, column, n=1, day=None):
    """Add n (an int >= 0) to one budget counter of `day` (the UTC day captured once by the caller)."""
    if column not in BUDGET_COLUMNS or type(n) is not int or n < 0:
        raise ValueError(f'budget_add {column} {n!r}')
    day = day or utc_day()
    budget_row(conn, day)
    conn.execute(f'UPDATE budget SET {column}={column}+? WHERE day=?', (n, day))


def metric_add(conn, organ, column, n=1, day=None):
    if column not in METRIC_COLUMNS or organ not in ORGANS or type(n) is not int or n < 0:
        raise ValueError(f'metric_add {organ} {column} {n!r}')
    day = day or utc_day()
    conn.execute('INSERT OR IGNORE INTO metrics (organ, day) VALUES (?, ?)', (organ, day))
    conn.execute(f'UPDATE metrics SET {column}={column}+? WHERE organ=? AND day=?', (n, organ, day))


def live_cells(conn, organ=None, node=None):
    sql = "SELECT * FROM cells WHERE state IN ('active','dividing','quarantined')"
    args = []
    if organ:
        sql += ' AND organ=?'
        args.append(organ)
    if node:
        sql += ' AND node=?'
        args.append(node)
    return conn.execute(sql + ' ORDER BY cell_id', args).fetchall()


def active_release(conn):
    rows = conn.execute('SELECT * FROM releases WHERE active=1').fetchall()
    if len(rows) != 1:
        raise RuntimeError(f'{len(rows)} active releases (exactly one is required)')
    row = rows[0]
    return row['release'], f'{RELEASES}/{row["release"]}', json.loads(row['manifest'])


RELEASE_DIRS = ('genome', 'organs', 'policies')
RELEASE_KEY_RX = re.compile(r'(genome|organs|policies)/[A-Za-z0-9][A-Za-z0-9._-]{0,80}')


def release_manifest(directory):
    """{relative path: sha256} of every regular file directly inside genome/, organs/ and policies/."""
    manifest = {}
    for sub in RELEASE_DIRS:
        for name in sorted(os.listdir(os.path.join(directory, sub))):
            path = os.path.join(directory, sub, name)
            if os.path.isfile(path) and not os.path.islink(path):
                manifest[f'{sub}/{name}'] = file_sha(path)
    return manifest


def release_problems(directory, manifest):
    """The release folder must hold EXACTLY genome/, organs/ and policies/ (real directories, nothing else at its
    root), each holding only regular files (no symlink, subdirectory, FIFO or other entry), and those files must be
    exactly the manifest's with the recorded hashes. Keys are canonical relative paths; an empty manifest is invalid."""
    out = []
    if not isinstance(manifest, dict) or not manifest:
        return ['the release manifest is empty or malformed']
    for rel in manifest:
        if not RELEASE_KEY_RX.fullmatch(rel):
            out.append(f'{rel}: not a canonical release path')
    try:
        if not stat.S_ISDIR(os.lstat(directory).st_mode):
            return out + ['the release folder is not a real directory']
        root = sorted(os.listdir(directory))
        if root != sorted(RELEASE_DIRS):
            return out + ['the release folder must hold exactly genome, organs and policies, it holds: ' + ', '.join(root)]
        for sub in RELEASE_DIRS:
            if not stat.S_ISDIR(os.lstat(os.path.join(directory, sub)).st_mode):
                return out + [f'{sub} is not a real directory']
            for name in os.listdir(os.path.join(directory, sub)):
                if not stat.S_ISREG(os.lstat(os.path.join(directory, sub, name)).st_mode):
                    out.append(f'{sub}/{name}: not a regular file')
        actual = release_manifest(directory)
    except OSError as exc:
        return out + [f'cannot list the release: {exc}']
    for rel in sorted(set(manifest) - set(actual)):
        out.append(f'{rel}: missing or not a regular file')
    for rel in sorted(set(actual) - set(manifest)):
        out.append(f'{rel}: not in the release manifest')
    for rel in sorted(set(actual) & set(manifest)):
        if actual[rel] != manifest[rel]:
            out.append(f'{rel}: sha256 differs from the release manifest')
    return out


# ------------------------------------------------------------------------------------------- organ config


def load_organs(directory):
    with open(os.path.join(directory, 'organs', 'organs.json'), encoding='utf-8') as handle:
        data = json.load(handle, object_pairs_hook=_no_dup_keys)
    problems = organs_problems(data)
    if problems:
        raise ValueError('organs.json: ' + '; '.join(problems))
    return data


def _no_dup_keys(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f'duplicate JSON key {key!r}')
        out[key] = value
    return out


def organs_problems(data):
    """The closed schema of organs/organs.json. Returns a list of problems (empty = valid). Every scalar's exact
    type is checked before it is compared."""
    out = []
    if not isinstance(data, dict) or set(data) != {'version', 'organs', 'ladders'}:
        return ['top level must be exactly {version, organs, ladders}']
    if type(data['version']) is not int or data['version'] != 2:
        out.append('version must be the integer 2')
    organs = data['organs']
    if not isinstance(organs, dict) or set(organs) != set(ORGANS):
        return out + ['organs must name exactly ' + ', '.join(ORGANS)]
    for name, spec in organs.items():
        keys = {'kind', 'seed_node', 'seed_focus', 'divide_backlog'}
        if not isinstance(spec, dict) or set(spec) != keys:
            out.append(f'{name}: keys must be exactly ' + ', '.join(sorted(keys)))
            continue
        if spec['kind'] != ('agent' if name in AGENT_ORGANS else 'model'):
            out.append(f'{name}: kind must be {"agent" if name in AGENT_ORGANS else "model"}')
        if not isinstance(spec['seed_node'], str) or spec['seed_node'] not in NODES:
            out.append(f'{name}: seed_node must be one of ' + ', '.join(NODES))
        focus = spec['seed_focus']
        if not isinstance(focus, str) or not 8 <= len(focus) <= 120 or one_line(focus, 120) != focus or has_secret(focus):
            out.append(f'{name}: seed_focus is one clean line of 8..120 characters')
        if type(spec['divide_backlog']) is not int or not 4 <= spec['divide_backlog'] <= 64:
            out.append(f'{name}: divide_backlog is an integer 4..64')
    ladders = data['ladders']
    if not isinstance(ladders, dict) or set(ladders) != set(PROGRAMS) | {'local-research'}:
        out.append('ladders must name exactly every program plus local-research')
    else:
        for program, ladder in ladders.items():
            if (not isinstance(ladder, list) or not 1 <= len(ladder) <= 3
                    or any(not isinstance(m, str) or m not in MODEL_MIB or m not in NON_THINKING_MODELS for m in ladder)):
                out.append(f'ladder {program}: 1..3 non-thinking models drawn from ' + ', '.join(MODEL_MIB))
            elif len(set(ladder)) != len(ladder):
                out.append(f'ladder {program}: a model appears twice')
    per_node = {}
    for spec in organs.values():
        if isinstance(spec, dict) and isinstance(spec.get('seed_node'), str) and spec['seed_node'] in NODES:
            per_node[spec['seed_node']] = per_node.get(spec['seed_node'], 0) + 1
    if any(n > NODE_CELL_CAP for n in per_node.values()):
        out.append(f'seed placement puts more than {NODE_CELL_CAP} cells on one node')
    return out


# ------------------------------------------------------------------------------------------- item payloads
# (kind, stage) -> (required keys, optional keys): the closed payload schema of every item at every stage (LIFE.md
# section 6). Tick.new_item and Tick.item_update refuse any payload outside it, and any payload over PAYLOAD_MAX.
_FINDING = {'test_id', 'finding_text', 'base_commit', 'source', 'wall_s', 'trace_files', 'trace_functions'}
_SOURCE = {'source_key', 'url'}
PAYLOAD_KEYS = {
    ('command', 'classify'): ({'command_id'}, set()),
    ('question', 'research'): ({'question', 'command_id', 'found'}, set()),
    ('source', 'fetch'): (_SOURCE, set()),
    ('source', 'extract'): (_SOURCE | {'text_path', 'text_sha256'}, set()),
    ('source', 'distill'): (_SOURCE | {'text_path', 'text_sha256', 'fact_id', 'claim', 'quote'}, set()),
    ('finding', 'confirm'): ({'test_id', 'finding_text', 'base_commit', 'source', 'command_text'}, set()),
    ('finding', 'triage'): (_FINDING, set()),
    ('finding', 'patch'): (_FINDING | {'change_class'}, {'review_note', 'previous_patch'}),
    ('finding', 'gate'): (_FINDING | {'change_class'}, {'review_note', 'previous_patch'}),
    ('patch', 'review'): ({'subject', 'patch_id'}, set()),
    ('proposal', 'review'): ({'subject', 'proposal_id'}, set()),
    ('lesson', 'draft'): ({'program', 'lesson'}, {'lesson_id', 'base_release', 'base_commit'}),
    ('lesson', 'gate'): ({'program', 'lesson', 'lesson_id', 'base_release', 'base_commit'}, set()),
    ('experiment', 'propose'): ({'seed_text'}, set()),
    ('experiment', 'rank'): ({'seed_text', 'experiment_id'}, set()),
    ('experiment', 'bench'): ({'seed_text', 'experiment_id'}, {'job_id', 'node', 'unit', 'started', 'timeout', 'label'}),
    ('request', 'draft'): ({'request'}, {'migration_id', 'snapshot_sha', 'base_commit'}),
    ('request', 'apply'): ({'request', 'migration_id', 'snapshot_sha', 'base_commit'}, set()),
}


def operative_sha(kind, payload):
    """sha256 of the fields an operator approval covers: a lesson's program and text, a request's text. Any change to them
    after approval makes the approval void (the item waits again)."""
    return sha(kind, payload.get('program', ''), payload.get('lesson', ''), payload.get('request', ''))


QUALNAME_MAX = 48                                # characters; a function identity LIFE can name (longer: never authorized)
QUALNAME_RX = re.compile(r'(?=[^\n]{1,51}$)[A-Za-z_][A-Za-z0-9_]{0,47}(?:\.[A-Za-z_][A-Za-z0-9_]{0,47}){0,3}(?:#[2-9])?')
PATH_TOKEN = r'(?!(?:[^,]*/)?\.{1,2}(?:/|,|$))[A-Za-z0-9_][A-Za-z0-9_./-]{0,79}'   # no . or .. component; <= 80


def _str(lo, hi):
    return lambda v: isinstance(v, str) and lo <= len(v) <= hi


def _hexs(n, empty=False):
    return lambda v: isinstance(v, str) and ((empty and v == '') or re.fullmatch(f'[0-9a-f]{{{n}}}', v) is not None)


def _int(lo, hi):
    return lambda v: type(v) is int and lo <= v <= hi


# The value rule of every payload field (exact type; booleans are never integers; ranges; identifier forms; list
# lengths). payload_problems applies them after the key schema.
FIELD_RULES = {
    'command_id': _hexs(16, empty=True), 'question': _str(1, QUESTION_CHARS), 'found': _int(0, QUESTION_SOURCE_LIMIT),
    'source_key': _str(1, SOURCE_KEY_MAX),
    'url': lambda v: isinstance(v, str) and len(v) <= URL_MAX and re.match(r'https?://', v) is not None,
    'text_path': _str(1, 400), 'text_sha256': _hexs(64), 'fact_id': _hexs(16), 'claim': _str(20, 300),
    'quote': _str(12, 400), 'test_id': lambda v: valid_test_id(v), 'finding_text': _str(1, FINDING_CHARS),
    'base_commit': _hexs(40, empty=True), 'source': lambda v: v in ('watch', 'owner'),
    'command_text': _str(1, COMMAND_MAX_BYTES), 'wall_s': _int(0, 86400),
    'trace_files': lambda v: isinstance(v, list) and len(v) <= LOCAL_FIX_FILES_MAX and all(
        isinstance(x, str) and re.fullmatch(PATH_TOKEN, x) for x in v),
    'trace_functions': lambda v: isinstance(v, dict) and len(v) <= LOCAL_FIX_FILES_MAX and all(
        isinstance(k, str) and isinstance(x, list) and len(x) <= 20 and all(isinstance(f, str) and QUALNAME_RX.fullmatch(f)
                                                                            for f in x) for k, x in v.items()),
    'change_class': lambda v: v in ('test_only', 'comment_or_doc', 'local_fix'), 'review_note': _str(0, 240),
    'previous_patch': _hexs(16, empty=True), 'subject': lambda v: v in ('patch', 'proposal'), 'patch_id': _hexs(16),
    'proposal_id': _hexs(16), 'program': lambda v: v in PROGRAMS, 'lesson': _str(LESSON_MIN_CHARS, LESSON_MAX_CHARS),
    'lesson_id': _hexs(16), 'base_release': _int(1, 10 ** 9), 'seed_text': _str(1, REQUEST_MAX_CHARS),
    'experiment_id': _hexs(16), 'job_id': _str(0, 80), 'node': lambda v: v in NODES,
    'unit': lambda v: isinstance(v, str) and re.fullmatch(r'[A-Za-z/%]{1,12}', v) is not None,
    'started': _int(0, 2 ** 40), 'timeout': _int(0, 7200), 'label': _str(1, 80),
    'request': _str(REQUEST_MIN_CHARS, REQUEST_MAX_CHARS),
    'migration_id': lambda v: isinstance(v, str) and re.fullmatch(r'[0-9]{4}_[a-z0-9_]{1,40}', v) is not None,
    'snapshot_sha': _hexs(64),
}


def payload_problems(kind, stage, payload):
    """Empty when `payload` (a dict) is exactly the closed schema of (kind, stage), every value passes its FIELD_RULES
    rule, and its JSON (no NaN or infinity) fits PAYLOAD_MAX."""
    spec = PAYLOAD_KEYS.get((kind, stage))
    if spec is None:
        return [f'no payload schema for {kind} at {stage}']
    if not isinstance(payload, dict):
        return ['the payload is not an object']
    required, optional = spec
    out = []
    if required - set(payload):
        out.append(f'{kind}/{stage} payload lacks ' + ', '.join(sorted(required - set(payload))))
    if set(payload) - required - optional:
        out.append(f'{kind}/{stage} payload has unknown keys ' + ', '.join(sorted(set(payload) - required - optional)))
    bad = sorted(k for k in set(payload) & (required | optional) if not FIELD_RULES[k](payload[k]))
    if bad:
        out.append(f'{kind}/{stage} payload has invalid values for ' + ', '.join(bad))
    try:
        if len(json.dumps(payload, sort_keys=True, allow_nan=False)) > PAYLOAD_MAX:
            out.append(f'PAYLOAD_TOO_LARGE: over {PAYLOAD_MAX} characters')
    except (TypeError, ValueError) as exc:
        out.append(f'the payload is not plain JSON: {exc}')
    return out


# ------------------------------------------------------------------------------------------- templates

SCOPES = {'comment_or_doc': 'Markdown files under docs/'}   # test_only: 'the file <module>'; local_fix: local_fix_scope()
LOCAL_FIX_RULE = (', adding no import or file and changing no signature, default, decorator, class line or module-level '
                  'line')
_QN = r'[A-Za-z_][A-Za-z0-9_]{0,47}(?:\.[A-Za-z_][A-Za-z0-9_]{0,47}){0,3}'


def local_fix_scope(functions, files):
    """The scope text of a local_fix run: exactly the functions (qualified names, #N dropped) the gate will accept,
    inside exactly its trace files, with the body-only rule spelled out."""
    names = list(dict.fromkeys(f.split('#')[0] for f in functions))[:LOCAL_FIX_FUNCTIONS_MAX]
    return ('the bodies of the functions ' + ', '.join(names) + ' inside ' + ('the file ' if len(files) == 1 else 'the files ')
            + ', '.join(files) + LOCAL_FIX_RULE)


PLACEHOLDERS = {                                  # every value a template may receive, and its exact (full) form
    'kit': re.compile(re.escape(KIT)),
    'test_id': TEST_ID_RX,
    'finding_id': re.compile(r'[0-9a-f]{16}'),
    'finding_text': re.compile(r'[^`{}\n]{1,700}'),
    'review_note': re.compile(r'[^`{}\n]{1,240}'),
    'scope': re.compile(r'Markdown files under docs/|the file ' + PATH_TOKEN + r'|the bodies of the functions ' + _QN
                        + r'(?:, ' + _QN + r'){0,2} inside the files? ' + PATH_TOKEN + r'(?:, ' + PATH_TOKEN + r'){0,2}'
                        + re.escape(LOCAL_FIX_RULE)),
    'lesson_id': re.compile(r'[0-9a-f]{16}'),
    'program': re.compile('|'.join(re.escape(p) for p in PROGRAMS if p not in SELFDEV_PROTECTED)),
    'lesson': re.compile(r'[^`{}\n]{10,300}'),
    'migration_id': re.compile(r'[0-9]{4}_[a-z0-9_]{1,40}'),
    'request': re.compile(r'[^`{}\n]{10,600}'),
    'snapshot_sha': re.compile(r'[0-9a-f]{64}'),
}
TEMPLATE_FIELDS = {
    'codebase': ('ws', 'kit', 'test_id', 'finding_id', 'finding_text', 'scope', 'review_note'),
    'selfdev': ('ws', 'kit', 'lesson_id', 'program', 'lesson'),
    'database': ('ws', 'kit', 'migration_id', 'request', 'snapshot_sha'),
}
FIELD_RX = re.compile(r'\{([a-z_]+)\}')
# Derived by render() from ws, never passed in. The statement templates write the workspace as the literal
# absolute prefix /home/operator/symblicos/projects/life-<organ>- followed by {ws_id} (= <depth>-<hex8>), so the raw
# template text already names an absolute folder (symblic_autogen.lint finds no warning without a root) and the
# rendered text is exactly ws.
DERIVED_FIELDS = ('ws_id',)
STATEMENT_MAX = 1480                              # every rendered statement stays below lint's 1500 warning (VALIDATE renders the largest legal values)


def ws_rx(organ):
    return re.compile(re.escape(f'{PROJECTS}/life-{organ}-') + r'(0|[1-9]|10)-[0-9a-f]{8}')


def render(text, organ, values):
    """Fill a statement or policy template. Exactly the organ's fields, each FULLY matching its exact form and
    free of credential-shaped text, plus the derived ws_id; ws must be a workspace of this organ."""
    fields = TEMPLATE_FIELDS[organ]
    if set(values) != set(fields):
        raise ValueError(f'{organ} template needs exactly ' + ', '.join(fields))
    for key, value in values.items():
        rx = ws_rx(organ) if key == 'ws' else PLACEHOLDERS[key]
        if not isinstance(value, str) or not rx.fullmatch(value) or has_secret(value) or (
                key == 'test_id' and not valid_test_id(value)):
            raise ValueError(f'{organ} template value {key} has the wrong form')
    filled = dict(values, ws_id=values['ws'][len(f'{PROJECTS}/life-{organ}-'):])
    used = set(FIELD_RX.findall(text))
    if not used <= set(fields) | set(DERIVED_FIELDS):
        raise ValueError(f'{organ} template names unknown fields: ' + ', '.join(sorted(used - set(fields) - set(DERIVED_FIELDS))))
    return FIELD_RX.sub(lambda m: filled[m.group(1)], text)


AGENT_POLICY_FIXED = {'version': 1, 'perpetual': False, 'until_done': False, 'candidates': 1, 'regenerate': 2,
                      'depth': 0, 'children': 2, 'generations': 1, 'agents_max': AGENTS_PER_RUN, 'attempt_seconds': 900,
                      'wall_seconds': AGENT_WALL_SECONDS, 'interval_seconds': 900, 'feedback_chars': 2000, 'novelty_limit': 2,
                      'saturation': 0, 'strategies': ['fresh', 'feedback'], 'syntax': True, 'require_change': True,
                      'self_split': False, 'designer': False, 'final': [], 'hidden': []}
# Fields bin/symblic-task has no flag for: the server fills them from symblic_autogen.DEFAULTS, so LIFE's value must
# equal that default (contract_problems pins each one; each armed tick compares the RUNNING server's catalogue).
DEFAULT_FIELDS = ('perpetual', 'until_done', 'syntax', 'require_change', 'designer', 'final', 'hidden',
                  'interval_seconds', 'feedback_chars')
LC = '/usr/bin/python3 -B {kit}/bin/life-check.py'
AGENT_CHECKS = {                                  # the exact check commands per organ (raw, before render)
    'codebase': {'0': [LC + ' sandboxed /usr/bin/python3 -s -B -m unittest {test_id}'],
                 '1': [LC + ' verify-line codebase verify.txt finding={finding_id} test={test_id}']},
    'selfdev': {'0': [REPO + '/bin/symblic check genome/{program}.sym',
                      LC + ' genome-protected genome/{program}.sym genome-base/{program}.sym'],
                '1': [LC + ' verify-line selfdev verify.txt lesson={lesson_id} program={program}']},
    'database': {'0': [LC + ' migration migrations/{migration_id}.sql schema-snapshot.sql {snapshot_sha}'],
                 '1': [LC + ' verify-line database verify.txt migration={migration_id}']},
}


def agent_policy_problems(policy, organ=None, raw_checks=None):
    """Every LIFE agent run uses exactly the fixed bounded policy; its checks are exactly the organ's
    AGENT_CHECKS (compared on the raw template when raw_checks is given)."""
    out = []
    if not isinstance(policy, dict) or set(policy) != set(AGENT_POLICY_FIXED) | {'checks'}:
        return ['keys must be exactly the fixed agent policy keys plus checks']
    for key, value in AGENT_POLICY_FIXED.items():
        if policy.get(key) != value or type(policy.get(key)) is not type(value):
            out.append(f'{key} must be {value!r}')
    checks = policy.get('checks')
    if not isinstance(checks, dict) or set(checks) != {'0', '1'} or not all(
            isinstance(v, list) and v and all(isinstance(c, str) and c for c in v) for v in checks.values()):
        out.append('checks must have exactly statement indexes "0" and "1", each a nonempty list of commands')
    if organ is not None and raw_checks is not None and raw_checks != AGENT_CHECKS[organ]:
        out.append(f'checks must be exactly life_common.AGENT_CHECKS[{organ!r}]')
    return out


def render_run(release_dir, organ, values):
    """(lines, policy, sha256) for one agent run, rendered from the release: exactly two statements, each naming
    the workspace, at most STATEMENT_MAX characters and linting with ZERO findings; the policy equal to the fixed
    policy with the organ's exact checks, accepted by symblic_autogen.normalize."""
    import sys
    if REPO not in sys.path:
        sys.path.insert(0, REPO)
    from symblic.autogen import policy as A
    with open(os.path.join(release_dir, 'organs', f'{organ}.lines.txt'), encoding='utf-8') as handle:
        lines = A.statements(render(handle.read(), organ, values))
    if len(lines) != 2 or any(values['ws'] not in line for line in lines):
        raise ValueError('a LIFE agent run has exactly two statements, each naming the workspace ' + values['ws'])
    if any(len(line) > STATEMENT_MAX for line in lines):
        raise ValueError(f'a rendered statement is longer than {STATEMENT_MAX} characters')
    findings = A.lint(lines, values['ws'])
    if findings:
        raise ValueError('lint: ' + '; '.join(f'{lv} line {n}: {m}' for lv, n, m in findings)[:300])
    with open(os.path.join(release_dir, 'policies', f'{organ}.json'), encoding='utf-8') as handle:
        raw = handle.read()
    raw_policy = json.loads(raw, object_pairs_hook=_no_dup_keys)
    policy = json.loads(render(raw, organ, values), object_pairs_hook=_no_dup_keys)
    problems = agent_policy_problems(policy, organ, raw_policy.get('checks') if isinstance(raw_policy, dict) else None)
    if problems:
        raise ValueError('policy: ' + '; '.join(problems))
    normalized = A.normalize(policy)
    return lines, policy, normalized['sha256']


def policy_flags(policy):
    """The bin/symblic-task start flags for a LIFE agent policy. Fields with a flag are emitted explicitly; the
    DEFAULT_FIELDS have no flag and equal the server defaults (pinned by contract_problems). The tick then compares
    the run's server-side policy sha256 with symblic_autogen.normalize(policy)['sha256'] (VALIDATE proves the round
    trip through bin/symblic-task's own parser statically)."""
    problems = agent_policy_problems(policy)
    if problems:
        raise ValueError('; '.join(problems))
    f = AGENT_POLICY_FIXED
    flags = ['--candidates', str(f['candidates']), '--regenerate', str(f['regenerate']), '--decompose', str(f['depth']),
             '--children', str(f['children']), '--handoff', str(f['generations']), '--agents-max', str(f['agents_max']),
             '--attempt-seconds', str(f['attempt_seconds']), '--wall-seconds', str(f['wall_seconds']),
             '--novelty-limit', str(f['novelty_limit']), '--saturation', str(f['saturation']),
             '--strategies', ','.join(f['strategies']), '--no-self-split']
    for index in ('0', '1'):
        for command in policy['checks'][index]:
            flags += ['--check', f'{index}:{command}']
    return flags


def autogen_run_id(request_id):
    """symblicos/autogen.py submit: run_id = 'autogen-' + sha256(client_request_id)[:24]."""
    return 'autogen-' + hashlib.sha256(request_id.encode()).hexdigest()[:24]


# ------------------------------------------------------------------------------------------- code-owned classifiers

# Paths no LIFE patch may touch: acceptance machinery (the gate must never run a judge the patch changed), every
# platform file LIFE relies on (each CONTRACT file; VALIDATE checks), agent instructions other agents read, private
# data, service and nav registration, the kit itself. Checked at the gate AND again by life-ctl apply.
GATE_DENY_RX = re.compile(
    r'^(bin/|scripts/|rules/|symblicos/|\.agents/|\.claude/|\.githooks/|\.github/|\.backups/|(.*/)?secrets_data/|'
    r'docs/life/|docs/agents/|docs/fleet-power\.md$|docs/symblic/AUTOGEN\.md$|docs/symblic/RECURSION\.md$|'
    r'(.*/)?AGENTS\.md$|(.*/)?CLAUDE\.md$|tests/__init__\.py$|(.*/)?conftest\.py$|tests/(.*/)?__init__\.py$|'
    r'sgconfig\.yml$|pyproject\.toml$|ruff\.toml$|\.ruff\.toml$|setup\.cfg$|tox\.ini$|pytest\.ini$|'
    r'requirements-devtest\.(in|lock)$|\.pre-commit-config\.yaml$|(.*/)?\.gitignore$|(.*/)?\.gitattributes$|'
    r'(.*/)?\.env[^/]*$|easy_config\.json$|security_gate\.py$|register\.py$|server\.py$|'
    r'host_routes\.py$|host_bridge\.py$|sw\.js$|index2\.html$|restart-dashboard\.sh$|landlock_sandbox\.py$|'
    r'symblic_autogen\.py$|symblic_run\.py$|symblic_apply\.py$|fleet_runner\.py$|local_research\.py$|deep_research\.py$|'
    r'cluster_engine\.py$|cluster_highpower\.py$|agent_hub\.py$|symblicos_engine\.py$|'
    r'.*\.(service|timer|slice|socket)$|.*(^|/)\.[^/]*rc$)')
DOC_RX = re.compile(r'^docs/(?:[^/]+/)*[^/]+\.md$')
RESTART_GATED_RX = re.compile(r'\.py$|(^|/)bin/|\.(service|timer|sh)$')
LIVE_STATIC_RX = re.compile(r'\.(html|js|mjs|css|json|svg|png|webp|ico|txt|webmanifest)$')
TEST_RX = re.compile(r'^tests/')
CONTROL_NAMES = ('verify.txt', 'HANDOFF.md', 'AUTOGEN-CHECKPOINT.json', 'AUTOGEN-SPLIT.txt', 'AUTOGEN-TESTS.sh',
                 'AUTOGEN-INDEX.jsonl')       # verify.txt plus symblic_autogen.CONTROL_FILES, root level only


def path_class(files):
    """Code decides how a patch reaches the operator, from the paths alone (the model's class never overrides):
    tests (tests/...), docs (docs/**/*.md), restart_gated (.py, bin/, .service/.timer/.sh), live_static
    (LIVE_STATIC_RX), other (anything else), or mixed when more than one class appears."""
    classes = set()
    for f in files:
        if TEST_RX.match(f):
            classes.add('tests')
        elif DOC_RX.match(f):
            classes.add('docs')
        elif RESTART_GATED_RX.search(f):
            classes.add('restart_gated')
        elif LIVE_STATIC_RX.search(f):
            classes.add('live_static')
        else:
            classes.add('other')
    return classes.pop() if len(classes) == 1 else 'mixed'


def resolve_test_module(root, test_id):
    """The repository-relative file a test id names, WITHOUT importing anything: the longest dotted prefix that is
    <path>.py or <path>/__init__.py, a regular file inside root with no symlink on the way; '' when none. The same
    rule checks/devcheck-gate.sh step 1 applies."""
    root = os.path.realpath(root)
    parts = test_id.split('.')
    for n in range(len(parts), 0, -1):
        for rel in ('/'.join(parts[:n]) + '.py', '/'.join(parts[:n]) + '/__init__.py'):
            path = os.path.join(root, rel)
            walk = [os.path.join(root, *rel.split('/')[:k]) for k in range(1, len(rel.split('/')) + 1)]
            if os.path.isfile(path) and not any(os.path.islink(p) for p in walk) and \
                    os.path.realpath(path).startswith(root + os.sep):
                return rel
    return ''


WEAKEN_RX = re.compile(r'skip(?:If|Unless)?\s*\(|skipTest\s*\(|expectedFailure|@unittest\.skip|pytest\.mark\.skip')
ASSERT_RX = re.compile(r'\bassert\w*\b')


def patch_problems(files, change_class, diff, allowed_files=()):
    """The gate's path and content rules for one codebase diff (LIFE.md section 7.4). files are repository-relative
    paths from `git diff --name-only --no-renames`. allowed_files: local_fix = the traceback's files; test_only = the
    ONE module file the test id resolves to."""
    out = []
    if not files or not diff.strip():
        return ['the run left no diff']
    if len(diff.encode('utf-8')) > DIFF_MAX_BYTES:
        out.append(f'the diff is larger than {DIFF_MAX_BYTES} bytes')
    if re.search(r'^(GIT binary patch|Binary files )', diff, re.M):
        out.append('the diff contains a binary file')
    if re.search(r'^(?:old mode|new mode) ', diff, re.M):
        out.append('the diff changes a file mode')
    if re.search(r'^(?:new file mode|deleted file mode) (?!100644$|100755$)', diff, re.M):
        out.append('the diff adds or deletes something other than a regular file (a symlink or submodule)')
    denied = [f for f in files if GATE_DENY_RX.match(f)]
    if denied:
        out.append('protected paths: ' + ', '.join(denied[:5]))
    if change_class == 'test_only':
        if not allowed_files or any(f not in allowed_files for f in files):
            out.append('a test_only patch may change only the module file its test id names: ' + (', '.join(allowed_files) or 'none'))
        removed = sum(len(ASSERT_RX.findall(ln)) for ln in diff.splitlines() if ln.startswith('-') and not ln.startswith('---'))
        added = sum(len(ASSERT_RX.findall(ln)) for ln in diff.splitlines() if ln.startswith('+') and not ln.startswith('+++'))
        if added < removed:
            out.append('a test_only patch removed assertions')
        if any(WEAKEN_RX.search(ln) for ln in diff.splitlines() if ln.startswith('+') and not ln.startswith('+++')):
            out.append('a test_only patch added a skip or an expected failure')
    elif any(TEST_RX.match(f) for f in files):
        out.append('a non-test patch changed files under tests/ (the judging test must stay fixed)')
    if change_class == 'comment_or_doc' and any(not DOC_RX.match(f) for f in files):
        out.append('a comment_or_doc patch changed files other than docs/**/*.md')
    if change_class == 'local_fix':
        outside = [f for f in files if f not in allowed_files]
        if not allowed_files or outside:
            out.append('a local_fix patch may change only the files the failure names: ' + (', '.join(outside[:5]) or 'none named'))
    if has_secret_code(diff):
        out.append('the diff contains a credential-shaped literal')
    return out


def _def_nodes(tree):
    """[(identity, node)] of every function definition in source (pre-)order, at every nesting level: identity =
    the qualified name (classes and enclosing functions joined by .), plus #N when it is the N-th definition of that
    name in the module (N >= 2: a property setter, a redefinition). Inner definitions follow their outer one."""
    out, seen = [], {}

    def visit(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = prefix + child.name
                seen[name] = seen.get(name, 0) + 1
                out.append((name + (f'#{seen[name]}' if seen[name] > 1 else ''), child))
                visit(child, name + '.')
            elif isinstance(child, ast.ClassDef):
                visit(child, prefix + child.name + '.')
            else:
                visit(child, prefix)
    visit(tree, '')
    return out


def _def_dumps(tree):
    """{identity: (header dump, own dump)}: the header is the definition with its body replaced by pass (name,
    arguments and defaults, decorators, return annotation, type parameters); own is the definition with every NESTED
    function's body blanked. Headers are compared at every level independently, so a nested signature change is seen
    even when only the outer body may change."""
    import copy
    out = {}
    for ident, node in _def_nodes(tree):
        head = copy.deepcopy(node)
        head.body = [ast.Pass()]
        own = copy.deepcopy(node)
        for sub in ast.walk(own):
            if sub is not own and isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sub.body = [ast.Pass()]
        out[ident] = (ast.dump(head), ast.dump(own))
    return out


def local_fix_problems(old_text, new_text, allowed_functions):
    """A local_fix changes only function BODIES: with every function body blanked, the old and new module are the same
    syntax tree (no import, class or module-level change); every definition keeps its identity (qualified name and
    occurrence) and its header (signature, defaults, decorators, annotations) at every nesting level; at most
    LOCAL_FIX_FUNCTIONS_MAX bodies change, and each changed identity is one the traceback named, resolved against the
    base file by line number (allowed_functions; traceback_functions)."""
    try:
        old_tree, new_tree = ast.parse(old_text), ast.parse(new_text)
    except SyntaxError as exc:
        return [f'the file does not parse: {exc.msg} (line {exc.lineno})']

    def skeleton(tree):
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                node.body = [ast.Pass()]
        return ast.dump(tree)
    old_f, new_f = _def_dumps(old_tree), _def_dumps(new_tree)
    if skeleton(old_tree) != skeleton(new_tree) or list(old_f) != list(new_f):
        return ['a local_fix changed code outside function bodies (a definition, decorator, import, class or module line)']
    heads = sorted(n for n in old_f if old_f[n][0] != new_f[n][0])
    if heads:
        return ['a local_fix changed a signature, default, decorator or annotation: ' + ', '.join(heads[:5])]
    changed = sorted(n for n in old_f if old_f[n][1] != new_f[n][1])
    out = []
    if not changed:
        out.append('a local_fix changed no function body')
    if len(changed) > LOCAL_FIX_FUNCTIONS_MAX:
        out.append(f'a local_fix may change at most {LOCAL_FIX_FUNCTIONS_MAX} function bodies, it changed {len(changed)}')
    stray = [n for n in changed if n not in allowed_functions]
    if stray:
        out.append('a local_fix may change only the functions the traceback names: ' + ', '.join(stray[:5]))
    return out


def function_at(text, lineno):
    """The identity (_def_nodes) of the innermost function whose lines include `lineno` in this module text, or ''."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return ''
    best = ''
    for ident, node in _def_nodes(tree):
        if node.lineno <= lineno <= (node.end_lineno or node.lineno):
            best = ident
    return best


TRACE_RX = re.compile(r'File "([^"\n]+\.py)", line (\d+), in ([A-Za-z_][A-Za-z0-9_]*|<module>)')


def _trace_rel(path, root):
    rel = os.path.normpath(os.path.relpath(path, root)) if os.path.isabs(path) else path
    parts = rel.split('/')
    if (rel.startswith('/') or any(p in ('', '.', '..') for p in parts) or TEST_RX.match(rel) or GATE_DENY_RX.match(rel)
            or not re.fullmatch(PATH_TOKEN, rel)):
        return ''
    return rel


def traceback_files(text, root):
    """Repository-relative .py paths a unittest traceback names (File "<root>/<path>.py"), tests/ and protected paths
    and every path with an empty, . or .. component excluded, in order of appearance, at most LOCAL_FIX_FILES_MAX."""
    out = []
    for m in re.finditer(r'File "([^"\n]+\.py)"', text or ''):
        rel = _trace_rel(m.group(1), root)
        if rel and rel not in out:
            out.append(rel)
    return out[:LOCAL_FIX_FILES_MAX]


def traceback_functions(text, root):
    """{file: [function identities]} for each file traceback_files returns: every frame (file, line N, in NAME) is
    resolved against the file as it is in `root` (the clone at the base commit, read without following a link) to the
    identity of the innermost definition holding line N, kept only when its last name part is NAME (<module> frames
    and unresolvable frames are dropped). So `run` in one class never authorizes another class's `run`."""
    files = traceback_files(text, root)
    out = {f: [] for f in files}
    sources = {}
    for m in TRACE_RX.finditer(text or ''):
        rel = _trace_rel(m.group(1), root)
        if rel not in out or m.group(3) == '<module>':
            continue
        if rel not in sources:
            try:
                sources[rel] = read_in(root, rel, 4 << 20).decode('utf-8')
            except (OSError, UnicodeDecodeError):
                sources[rel] = ''
        ident = function_at(sources[rel], int(m.group(2)))
        if (ident and len(ident.split('#')[0]) <= QUALNAME_MAX and ident.split('#')[0].rsplit('.', 1)[-1] == m.group(3)
                and ident not in out[rel]):
            out[rel].append(ident)
    return out


def last_exception_line(text):
    """The LAST line of a unittest output that reads "Name: message" or "Name" with Name ending in Error, Exception,
    Failure or Exit (or AssertionError), or None."""
    found = None
    for ln in (text or '').splitlines():
        m = re.match(r'^([A-Za-z_][\w.]*(?:Error|Exception|Failure|Exit))(?::\s*(.*))?$', ln.strip())
        if m:
            found = m
    return found


def env_error(rc, tail, root):
    """A watched-test run that failed for its ENVIRONMENT, never for its code (then it is never a finding): rc 125
    (the sandbox refused) or 127; or the LAST exception line (last_exception_line) is ModuleNotFoundError naming a
    module whose top-level name is neither <name>.py nor a <name>/ package at the clone root (a missing third-party
    package); or it is PermissionError, ConnectionRefusedError or OSError with errno 13, 11 or 111 whose message does
    not name a path inside the clone. A test name or an assertion that merely mentions sandbox, Landlock or ImportError
    is a finding like any other."""
    if rc in (125, 127):
        return True
    m = last_exception_line(tail)
    if not m:
        return False
    cls, msg = m.group(1).rsplit('.', 1)[-1], m.group(2) or ''
    mod = re.match(r"No module named '([A-Za-z0-9_.]+)'", msg)
    if cls == 'ModuleNotFoundError' and mod:
        top = mod.group(1).split('.')[0]
        return not (os.path.isfile(os.path.join(root, top + '.py')) or os.path.isdir(os.path.join(root, top)))
    if cls in ('PermissionError', 'ConnectionRefusedError', 'OSError') and re.search(r'Errno (1[13]|111)\b', msg):
        return root not in msg
    return False


def failure_fingerprint(text):
    """(exception class, normalized message) of the LAST exception line of a unittest failure (last_exception_line);
    digits, hex runs and quoted strings in the message normalized away; None when no such line exists (the run is
    then an error)."""
    found = last_exception_line(text)
    if not found:
        return None
    msg = re.sub(r"'[^']*'|\"[^\"]*\"", "''", found.group(2) or '')
    msg = re.sub(r'0x[0-9a-fA-F]+|\b[0-9a-f]{8,}\b|\d+', '#', msg)
    return found.group(1).rsplit('.', 1)[-1], norm_text(msg)[:160]


# ------------------------------------------------------------------------------------------- migrations

IDENT = r'[a-z][a-z0-9_]{0,39}'                    # a column name; never sqlite_... (refused separately)
TABLE = r'org_[a-z0-9_]{1,40}'                     # a table or index name
LITERAL = r"(?:-?[0-9]{1,18}(?:\.[0-9]{1,18})?|'(?:[^']|'')*'|NULL)"
COLUMN_RX = re.compile(r'(' + IDENT + r') (TEXT|INTEGER|REAL|BLOB|NUMERIC)((?: NOT NULL| UNIQUE| PRIMARY KEY| DEFAULT '
                       + LITERAL + r'| REFERENCES ' + TABLE + r' ?\(' + IDENT + r'\))*)')
TABLE_CONSTRAINT_RX = re.compile(r'(?:PRIMARY KEY|UNIQUE) ?\((' + IDENT + r'(?:, ?' + IDENT + r')*)\)')
MIGRATION_RX = re.compile(
    r'(CREATE TABLE IF NOT EXISTS (' + TABLE + r') \((.+)\)|'
    r'CREATE (UNIQUE )?INDEX IF NOT EXISTS (' + TABLE + r') ON (' + TABLE + r') ?\((' + IDENT + r'(?:, ?' + IDENT + r')*)\)|'
    r'ALTER TABLE (' + TABLE + r') ADD COLUMN (.+))', re.S)
DENY_WORDS = r'DROP|DELETE|UPDATE|INSERT|REPLACE|ATTACH|DETACH|PRAGMA|VACUUM|TRIGGER|VIEW|REINDEX|ANALYZE'
MIGRATION_HEAD_DENY_RX = re.compile(r'(?i)^\s*(?:\w+\s+){0,2}(' + DENY_WORDS + r')\b')
FUNCTION_DENY_RX = re.compile(r'(?i)\b(load_extension|readfile|writefile|fts\d?|zipfile|edit|sqlar_\w+)\s*\(')
WORD_DENY_RX = re.compile(r'(?i)\b(AUTOINCREMENT|WITHOUT\s+ROWID|STRICT|CHECK|GENERATED|COLLATE|CONFLICT|CASCADE|'
                          r'RESTRICT|DEFERRABLE)\b')
REFERENCES_RX = re.compile(r'(?i)\bREFERENCES\b')
REFERENCE_NAME_RX = re.compile(r'\bREFERENCES (org_[a-z0-9_]{1,40}) ?\(([a-z][a-z0-9_]{0,39})\)')


# The grammar the gate enforces, as the database agent reads it: written as MIGRATION-RULES.txt into every database
# workspace next to schema-snapshot.sql (committed with it), and named by organs/database.lines.txt.
MIGRATION_RULES = """LIFE migration rules (the apply stage refuses anything else: life_common.migration_problems)
1. The file holds 1 to 24 SQLite statements, at most 16384 bytes; EVERY statement ends with a semicolon.
2. Every statement is exactly one of these forms, key words in upper case exactly as shown, one space between words:
   CREATE TABLE IF NOT EXISTS org_<name> (<column>, <column>, ..., <optional table constraint>)
   CREATE INDEX IF NOT EXISTS org_<name> ON org_<table> (<column name>, ...)
   CREATE UNIQUE INDEX IF NOT EXISTS org_<name> ON org_<table> (<column name>, ...)
   ALTER TABLE org_<table> ADD COLUMN <column>
3. A <column> is: <name> <TYPE> followed by none or more of NOT NULL, UNIQUE, PRIMARY KEY, DEFAULT <value>,
   REFERENCES org_<table> (<column name>). <name> uses lower-case letters, digits and underscores, starts with a
   letter, has at most 40 characters and never starts with sqlite_. <TYPE> is exactly TEXT, INTEGER, REAL, BLOB or
   NUMERIC. <value> is a number, a text in single quotes, or NULL. An ADD COLUMN takes no UNIQUE and no PRIMARY KEY.
4. A table constraint is PRIMARY KEY (<column name>, ...) or UNIQUE (<column name>, ...).
5. A table or index name is org_ plus lower-case letters, digits and underscores, at most 44 characters.
6. A created table or index name, and an added column, does not exist in schema-snapshot.sql. A table you alter or index
   exists in schema-snapshot.sql or is created earlier in this same file.
7. A UNIQUE index (or a UNIQUE or PRIMARY KEY column) may be created only on a table created in this same file, never
   on a table listed in schema-snapshot.sql: its rows are not visible to you.
8. REFERENCES names an org_ table that exists (rule 6) and one of its columns that is that table's single-column
   PRIMARY KEY or has a single-column UNIQUE constraint or UNIQUE index.
9. Never use: DROP, DELETE, UPDATE, INSERT, REPLACE, ATTACH, DETACH, PRAGMA, VACUUM, TRIGGER, VIEW, REINDEX, ANALYZE,
   AUTOINCREMENT, WITHOUT ROWID, STRICT, CHECK, GENERATED, COLLATE, ON CONFLICT, CASCADE, RESTRICT, DEFERRABLE, a block
   comment, a quoted identifier ("x", [x] or `x`), an expression, or the functions load_extension, readfile,
   writefile, fts, zipfile, edit and sqlar_.
10. A line comment starts with two hyphens.
11. Validation: the whole file is applied twice in a row on a copy of the organism (with its rows while it is at most
    64 MiB, else on the schema only), with foreign keys enforced; the second application must change nothing (an ADD
    COLUMN's "duplicate column" on the second pass is expected and ignored); the resulting schema must again be a valid
    schema snapshot.
"""


def split_sql(text, terminated=False):
    """Statements of a restricted DDL text: `--` comments and `;` are recognised only outside '...' and "..."
    literals; whitespace outside literals collapses to one space; literal contents are kept exactly. A block comment
    is refused (ValueError), so no hidden text exists. terminated=True: text after the last `;` (other than white space
    and comments) is refused (every statement ends with a semicolon)."""
    statements, buf, quote, i = [], [], '', 0
    text = text or ''
    while i < len(text):
        c = text[i]
        if quote:
            buf.append(c)
            if c == quote:
                if i + 1 < len(text) and text[i + 1] == quote:
                    buf.append(text[i + 1])
                    i += 1
                else:
                    quote = ''
        elif c in '\'"':
            quote = c
            buf.append(c)
        elif c == '-' and text[i:i + 2] == '--':
            j = text.find('\n', i)
            i = len(text) if j < 0 else j
            continue
        elif c == '/' and text[i:i + 2] == '/*':
            raise ValueError('a block comment (/* */)')
        elif c == ';':
            statements.append(''.join(buf))
            buf = []
        elif c.isspace():
            if buf and buf[-1] != ' ':
                buf.append(' ')
        else:
            buf.append(c)
        i += 1
    if quote:
        raise ValueError('an unterminated quoted literal')
    if terminated and ''.join(buf).strip():
        raise ValueError('a statement does not end with a semicolon')
    statements.append(''.join(buf))
    return [s.strip() for s in statements if s.strip()]


def code_text(statement):
    """The statement with the contents of every '...' literal removed (the quotes stay): what word and character
    rules look at, so a word inside a literal is never mistaken for SQL."""
    out, inside, i = [], False, 0
    while i < len(statement):
        c = statement[i]
        if inside:
            if c == "'" and statement[i + 1:i + 2] == "'":
                i += 2
                continue
            if c == "'":
                inside = False
                out.append(c)
        elif c == "'":
            inside = True
            out.append(c)
        else:
            out.append(c)
        i += 1
    return ''.join(out)


def migration_statements(sql_text):
    return split_sql(sql_text, terminated=True)


def snapshot_sql(conn):
    """The CREATE statements of a database in creation order (sqlite_master rowid: a table always precedes its
    indexes), SQLite's internal sqlite_* objects excluded, joined as `stmt;\\n`: what schema-snapshot.sql holds."""
    rows = conn.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite\\_%' ESCAPE '\\' "
                        'ORDER BY rowid').fetchall()
    return ''.join(r[0] + ';\n' for r in rows)


def snapshot_problems(snapshot_sql_text):
    """A schema snapshot may hold only CREATE TABLE and CREATE [UNIQUE] INDEX statements (what sqlite_master holds
    for the organism), no denied statement head, no denied function or word outside literals, no sqlite_ name. Words
    inside identifiers (a column named view) are allowed: only statement heads and function calls are checked; since
    migration_problems refuses every sqlite_ identifier, an accepted migration never makes a snapshot fail here."""
    out = []
    if len((snapshot_sql_text or '').encode('utf-8')) > SNAPSHOT_MAX_BYTES:
        return [f'the schema snapshot is larger than {SNAPSHOT_MAX_BYTES} bytes']
    try:
        statements = split_sql(snapshot_sql_text)
    except ValueError as exc:
        return [f'snapshot: {exc}']
    for s in statements:
        code = code_text(s)
        if (not re.match(r'(?i)^CREATE (TABLE|(UNIQUE )?INDEX) ', s) or MIGRATION_HEAD_DENY_RX.match(s)
                or FUNCTION_DENY_RX.search(code) or re.search(r'(?i)\b(AUTOINCREMENT|WITHOUT\s+ROWID|STRICT)\b', code)
                or re.search(r'(?i)\bsqlite_', code)):
            out.append(f'snapshot statement not allowed: {s[:80]}')
    return out


def deadline_handler(seconds):
    """A SQLite progress handler that aborts the running statement once `seconds` have passed or STOP appears."""
    end = time.monotonic() + seconds
    return lambda: 1 if time.monotonic() > end or stop_present() else 0


def split_defs(body):
    """The top-level comma-separated parts of a CREATE TABLE body (commas inside parentheses or quotes do not split)."""
    parts, buf, depth, quote = [], [], 0, ''
    for c in body:
        if quote:
            buf.append(c)
            if c == quote:
                quote = ''
            continue
        if c in '\'"':
            quote = c
        elif c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        elif c == ',' and depth == 0:
            parts.append(''.join(buf).strip())
            buf = []
            continue
        buf.append(c)
    parts.append(''.join(buf).strip())
    return parts


def logical_bytes(db_path):
    """page_count x page_size of a database, read-only (the logical size; WAL-resident pages included)."""
    src = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    try:
        return src.execute('PRAGMA page_count').fetchone()[0] * src.execute('PRAGMA page_size').fetchone()[0]
    finally:
        src.close()


def physical_bytes(db_path):
    """The database file plus its -wal and -shm files, as stored (the physical footprint)."""
    return sum(os.path.getsize(db_path + s) for s in ('', '-wal', '-shm') if os.path.exists(db_path + s))


def _statement_problems(s, created):
    """Grammar problems of one statement (MIGRATION_RULES 2-5 and 9); `created` collects tables created so far."""
    code = code_text(s)
    if MIGRATION_HEAD_DENY_RX.match(s) or FUNCTION_DENY_RX.search(code) or WORD_DENY_RX.search(code):
        return [f'denied statement, word or function in: {s[:80]}']
    if re.search(r'["`\[\]]', code):
        return [f'identifiers are never quoted (no " [ ] or ` outside \'...\' literals): {s[:80]}']
    if re.search(r'(?i)\bsqlite_', code):
        return [f'no name may start with sqlite_: {s[:80]}']
    m = MIGRATION_RX.fullmatch(s)
    if not m:
        return [f'not an allowed additive form: {s[:80]}']
    if m.group(2):
        parts = split_defs(m.group(3))
        cols = [p for p in parts if COLUMN_RX.fullmatch(p)]
        bad = [p for p in parts if not COLUMN_RX.fullmatch(p) and not TABLE_CONSTRAINT_RX.fullmatch(p)]
        if bad or not cols:
            return [f'not a column or table constraint of rule 3 or 4: {(bad or [s])[0][:80]}']
        created.add(m.group(2))
    elif m.group(8):
        col = COLUMN_RX.fullmatch(m.group(9))
        if not col or re.search(r' (UNIQUE|PRIMARY KEY)\b', col.group(3)):
            return [f'ADD COLUMN takes one column of rule 3 without UNIQUE or PRIMARY KEY: {s[:80]}']
    if len(REFERENCES_RX.findall(code)) != len(REFERENCE_NAME_RX.findall(code)):
        return [f'every REFERENCES names an unquoted org_ table followed by (column): {s[:80]}']
    return []


def migration_problems(sql_text, snapshot_sql_text='', db_path=None):
    """An organism migration is valid only when it follows MIGRATION_RULES exactly: 1..24 statements, each ended by a
    semicolon and each one of the four additive forms with the column grammar; only org_ tables and indexes that do
    not exist yet (ADD COLUMN: a column that does not exist yet on an existing table); a UNIQUE index or UNIQUE /
    PRIMARY KEY column only on a table this file creates; references only to an existing org_ table's single-column
    primary key or unique column; no quoted identifier, sqlite_ name, denied word or function outside literals; and
    the whole applies cleanly TWICE in memory, with foreign keys enforced and foreign_key_check clean, with the same
    resulting schema, which must itself pass snapshot_problems: on a copy of the database WITH its rows when db_path
    is given and its logical size is at most ORGANISM_VALIDATE_MAX_BYTES, else on the snapshot; the copy, both passes
    and the checks share ONE MIGRATION_SECONDS deadline (the copy in pages with a deadline check between batches)."""
    out = []
    if len((sql_text or '').encode('utf-8')) > MIGRATION_MAX_BYTES:
        return [f'migration is larger than {MIGRATION_MAX_BYTES} bytes']
    try:
        statements = split_sql(sql_text, terminated=True)
    except ValueError as exc:
        return [str(exc)]
    if not 1 <= len(statements) <= MIGRATION_STATEMENTS_MAX:
        out.append(f'a migration has 1..{MIGRATION_STATEMENTS_MAX} statements')
    created = set()
    for s in statements:
        out += _statement_problems(s, created)
    if out:
        return out
    if snapshot_sql_text:
        problems = snapshot_problems(snapshot_sql_text)
        if problems:
            return problems
    end = time.monotonic() + MIGRATION_SECONDS

    def past():
        return time.monotonic() > end or stop_present()
    db = sqlite3.connect(':memory:')
    db.set_progress_handler(lambda: 1 if past() else 0, 10000)
    try:
        if db_path and logical_bytes(db_path) <= ORGANISM_VALIDATE_MAX_BYTES:
            src = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)

            def progress(_status, _remaining, _total):
                if past():
                    raise TimeoutError('the validation copy passed its deadline or STOP appeared')
            try:
                src.backup(db, pages=256, progress=progress)
            finally:
                src.close()
        elif snapshot_sql_text:
            for s in split_sql(snapshot_sql_text):
                db.execute(s)
        db.execute('PRAGMA foreign_keys=ON')
        existing = {r[0] for r in db.execute("SELECT name FROM sqlite_master")}
        before = set(existing)
        cols = {}
        for s in statements:
            m = MIGRATION_RX.fullmatch(s)
            name = m.group(2) or m.group(5)
            if name and name in existing:
                out.append(f'{name} already exists: a migration creates new names only')
            if m.group(5):
                if m.group(6) not in existing:
                    out.append(f'index {m.group(5)} is on {m.group(6)}, which does not exist')
                elif m.group(4) and m.group(6) in before:
                    out.append(f'a UNIQUE index on {m.group(6)}: unique indexes only on tables this file creates (rule 7)')
            if m.group(8):
                table = m.group(8)
                if table not in existing:
                    out.append(f'ALTER TABLE {table}: no such table')
                have = cols.setdefault(table, {r[1] for r in db.execute(f'PRAGMA table_info("{table}")')}
                                       if table in existing else set())
                col = COLUMN_RX.fullmatch(m.group(9)).group(1)
                if col in have:
                    out.append(f'{table}.{col} already exists')
                have.add(col)
            for ref, _col in REFERENCE_NAME_RX.findall(code_text(s)):
                if ref not in existing and ref != m.group(2):
                    out.append(f'REFERENCES {ref}: no such org_ table in the snapshot or earlier in this migration')
            if name:
                existing.add(name)
        if out:
            return out
        schemas = []
        for _ in (1, 2):
            for s in statements:
                if past():
                    raise TimeoutError('the validation passed its deadline or STOP appeared')
                try:
                    db.execute(s)
                except sqlite3.OperationalError as exc:
                    if s.startswith('ALTER TABLE') and 'duplicate column' in str(exc) and schemas:
                        continue                  # the second application of an ADD COLUMN (rule 11)
                    raise
            schemas.append(sorted(tuple(r) for r in db.execute('SELECT type, name, sql FROM sqlite_master')))
        if schemas[0] != schemas[1]:
            out.append('a second application changed the schema')
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='sqlite_sequence'").fetchone():
            out.append('the migration created the internal sqlite_sequence table (AUTOINCREMENT)')
        for table in sorted(existing - before):
            if not table.startswith('org_') or db.execute("SELECT type FROM sqlite_master WHERE name=?", (table,)).fetchone()[0] != 'table':
                continue
            for fk in db.execute(f'PRAGMA foreign_key_list("{table}")').fetchall():
                parent, to = fk[2], fk[4]
                pk = [r[1] for r in db.execute(f'PRAGMA table_info("{parent}")') if r[5]]
                unique = any(ix[2] and [c[2] for c in db.execute(f'PRAGMA index_info("{ix[1]}")')] == [to]
                             for ix in db.execute(f'PRAGMA index_list("{parent}")'))
                if pk != [to] and not unique:
                    out.append(f'{table} REFERENCES {parent} ({to}): not its single-column primary key or a unique column')
        if db.execute('PRAGMA foreign_key_check').fetchone():
            out.append('foreign_key_check found rows that break a reference')
        out += [f'resulting schema: {p}' for p in snapshot_problems(snapshot_sql(db))]
    except (sqlite3.Error, TimeoutError) as exc:
        out.append(f'sqlite refused: {exc}')
    finally:
        db.close()
    return out


# ------------------------------------------------------------------------------------------- genome rules

# The instruction is the LAST top-level quoted string before " from ": the type may hold quoted enum descriptions.
ASK_RX = re.compile(r'(?P<indent>[ \t]*)ask (?P<name>[a-z_][a-z0-9_]*): (?P<type>.*) "(?P<instr>(?:[^"\\]|\\.)*)" '
                    r'(?P<tail>from [^"]*)')
NOTE_RX = re.compile(r'[ \t]*note ')


def genome_protected_problems(old_text, new_text):
    """A selfdev proposal may change only the quoted instruction of ask lines. Every other line (notes, blank lines
    and indentation included), and every ask's indentation, name, type (enum descriptions included) and trailing
    from/with clause stay byte-identical and in order; each changed instruction keeps exactly the same {name}
    placeholders; at least one instruction changes."""
    old = (old_text or '').splitlines(True)
    new = (new_text or '').splitlines(True)
    if len(old) != len(new):
        return ['the number of lines changed']
    out, changed = [], 0
    for n, (a, b) in enumerate(zip(old, new, strict=True), 1):
        if a == b:
            continue
        ma, mb = ASK_RX.fullmatch(a.rstrip('\n')), ASK_RX.fullmatch(b.rstrip('\n'))
        if a.endswith('\n') != b.endswith('\n') or not (ma and mb) or any(
                ma.group(k) != mb.group(k) for k in ('indent', 'name', 'type', 'tail')):
            out.append(f'line {n}: only the quoted instruction of an ask line may change')
        elif sorted(FIELD_RX.findall(ma.group('instr'))) != sorted(FIELD_RX.findall(mb.group('instr'))):
            out.append(f'line {n}: the instruction must keep exactly the same {{placeholders}}')
        else:
            changed += 1
    if not out and changed == 0:
        out.append('no ask instruction changed')
    return out


PLACEMENT_RX = re.compile(r'\b(by|applicator|model|node|engine)\s*=')


def genome_placement_problems(text):
    """A genome program never chooses its own model, node or engine: outside quoted strings, no `by=`, `applicator=`,
    `model=`, `node=` or `engine=` option (an ask-level by would win over the tick's --by). check_release refuses it."""
    bare = re.sub(r'"(?:[^"\\]|\\.)*"', '""', text or '')
    return [f'line {n}: a placement option ({m.group(1)}=) is not allowed in a genome program'
            for n, line in enumerate(bare.splitlines(), 1) for m in PLACEMENT_RX.finditer(line)]


VERIFY_LINES = {
    'codebase': re.compile(r'finding=[0-9a-f]{16} test=tests\.[A-Za-z0-9_.]+'),
    'selfdev': re.compile(r'lesson=[0-9a-f]{16} program=[a-z-]+'),
    'database': re.compile(r'migration=[0-9]{4}_[a-z0-9_]{1,40}'),
}


def verify_line_problems(organ, data, expected):
    """verify.txt must be exactly the expected line, optionally followed by one LF: no BOM, CR, spaces or other
    lines. `data` is the file's bytes."""
    if isinstance(data, str):
        data = data.encode('utf-8')
    if not VERIFY_LINES[organ].fullmatch(expected):
        return ['the expected verify line has the wrong form']
    if data not in (expected.encode('ascii'), expected.encode('ascii') + b'\n'):
        return ['verify.txt must be exactly the line ' + expected]
    return []


# ------------------------------------------------------------------------------------------- loopback adapter


class Telemetry(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status                    # the HTTP status code, or None when there was no HTTP answer


def _finite_float(text):
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(f'a non-finite number {text[:20]}')
    return value


def _depth_ok(value, depth=0):
    if depth > JSON_MAX_DEPTH:
        return False
    if isinstance(value, dict):
        return all(_depth_ok(v, depth + 1) for v in value.values())
    if isinstance(value, list):
        return all(_depth_ok(v, depth + 1) for v in value)
    return True


def strict_json(raw):
    """JSON as LIFE accepts it from any platform answer: duplicate keys, NaN/Infinity, numbers that overflow to an
    infinite float and nesting deeper than JSON_MAX_DEPTH are refused (ValueError)."""
    try:
        value = json.loads(raw, object_pairs_hook=_no_dup_keys, parse_float=_finite_float,
                           parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))
    except RecursionError:
        raise ValueError('JSON nested too deeply') from None
    if not _depth_ok(value):
        raise ValueError(f'JSON nested deeper than {JSON_MAX_DEPTH}')
    return value


def _http_once(path, body, timeout, box=None):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    data = None if body is None else json.dumps(body).encode('utf-8')
    req = urllib.request.Request(DASH + path, data=data, method='GET' if body is None else 'POST')
    req.add_header('Host', '127.0.0.1:8080')
    req.add_header('Accept', 'application/json')
    req.add_header('User-Agent', 'life-tick')
    if data is not None:
        req.add_header('Content-Type', 'application/json')
    try:
        with opener.open(req, timeout=timeout) as res:
            if box is not None:
                box['res'] = res
            raw = res.read(HTTP_MAX_BYTES + 1)
        if len(raw) > HTTP_MAX_BYTES:
            raise Telemetry(f'{path}: answer larger than {HTTP_MAX_BYTES} bytes')
        value = strict_json(raw.decode('utf-8'))
    except urllib.error.HTTPError as exc:
        raise Telemetry(f'{path}: HTTP {exc.code}', exc.code) from None
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
        raise Telemetry(f'{path}: {type(exc).__name__}: {str(exc)[:200]}') from None
    if not isinstance(value, dict):
        raise Telemetry(f'{path}: answer is not a JSON object')
    return value


_HTTP_OPEN = [0]
_HTTP_LOCK = threading.Lock()


def http_json(path, body=None, timeout=HTTP_TIMEOUT):
    """GET (body None) or POST JSON to the loopback dashboard with bin/symblic-task's header shape: no proxy,
    no redirect, Host 127.0.0.1:8080. ONE deadline of `timeout` seconds covers connecting, the headers, the body and
    decoding: the exchange runs in a helper thread and a caller never waits longer. At the deadline the caller closes
    the response (which ends a blocked read) and raises; an exchange that still has not ended counts as outstanding,
    and at HTTP_OUTSTANDING_MAX outstanding exchanges a new one is refused (Telemetry). A timed-out POST is an
    unresolved intent: callers reconcile it (a start by its run id, a job by its label), never by repeating blindly.
    Any HTTP error (status kept), oversize answer (> HTTP_MAX_BYTES), strict_json refusal, non-object answer or the
    deadline raises Telemetry."""
    with _HTTP_LOCK:
        if _HTTP_OPEN[0] >= HTTP_OUTSTANDING_MAX:
            raise Telemetry(f'{path}: {_HTTP_OPEN[0]} earlier loopback exchanges are still open; refused')
        _HTTP_OPEN[0] += 1
    box = {}

    def work():
        try:
            box['value'] = _http_once(path, body, timeout, box)
        except Telemetry as exc:
            box['error'] = exc
        except Exception as exc:  # noqa: BLE001 - any other failure is a Telemetry failure
            box['error'] = Telemetry(f'{path}: {type(exc).__name__}: {str(exc)[:200]}')
        finally:
            with _HTTP_LOCK:
                _HTTP_OPEN[0] -= 1
    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        res = box.get('res')
        if res is not None:
            try:
                res.close()
            except Exception:  # noqa: BLE001 - closing is best effort; the exchange stays counted until it ends
                pass
        raise Telemetry(f'{path}: no complete answer within {timeout} s')
    if 'error' in box:
        raise box['error']
    return box['value']


# ------------------------------------------------------------------------------------------- processes


class Procs:
    """Every subprocess LIFE starts, so STOP (or a timeout) ends them the same way: SIGTERM to the process group,
    then SIGKILL to the whole group KILL_GRACE seconds later, whether or not the leader already exited. Output goes to
    temporary files (memory stays bounded); a process that writes more than OUTPUT_KILL_BYTES is ended and returns
    OUTPUT_LIMIT_RC (checked while it runs AND after it exits). A process is registered in `live` the instant it
    exists, so STOP always sees it. `tracked=False` is for the cancel calls STOP itself makes and the agent start
    (which must not be killed half-way); `admit` is the final admission callable checked immediately before the
    process is created (launch_allowed for new work)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.live = {}
        self.stopped = set()                    # pids kill_all ended for STOP (their run returns STOPPED_RC)

    def run(self, argv, timeout, cwd=None, env=None, tracked=True, admit=None):
        """Returns (rc, stdout, stderr): rc None = timeout, OUTPUT_LIMIT_RC = output limit, STOPPED_RC = STOP ended it,
        NOT_ADMITTED_RC = no process was created (STOP present, admission refused, or no time left in the stage),
        127 = the program could not start, negative = signal. ONE monotonic deadline is computed before launch and each
        wait uses at most the time left, so a process never completes successfully past its deadline. Any exception
        while waiting ends the process group before it is unregistered."""
        if tracked and stop_present():
            return NOT_ADMITTED_RC, '', 'STOP present: not started'
        if admit is not None and not admit():
            return NOT_ADMITTED_RC, '', 'not admitted: STOP, FREEZE, disarm, a kit/platform/decisions change or the host load'
        if timeout <= 0:
            return NOT_ADMITTED_RC, '', 'no time left in this stage'
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            end = time.monotonic() + timeout
            with self.lock:
                try:
                    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                            start_new_session=True, close_fds=True)
                except (OSError, ValueError) as exc:
                    return 127, '', f'could not start {argv[0] if argv else "?"}: {type(exc).__name__}: {exc}'
                if tracked:
                    self.live[proc.pid] = proc
            rc = None

            def size():
                return os.fstat(out.fileno()).st_size + os.fstat(err.fileno()).st_size
            try:
                while True:
                    try:
                        rc = proc.wait(timeout=max(0.05, min(1.0, end - time.monotonic())))
                        break
                    except subprocess.TimeoutExpired:
                        pass
                    if size() > OUTPUT_KILL_BYTES:
                        self.end([proc])
                        rc = OUTPUT_LIMIT_RC
                        break
                    if time.monotonic() >= end:
                        self.end([proc])
                        rc = None
                        break
                if rc not in (None, OUTPUT_LIMIT_RC):
                    self.end([proc], leader_done=True)     # descendants still in the group end too
                    if size() > OUTPUT_KILL_BYTES:
                        rc = OUTPUT_LIMIT_RC
            finally:
                if proc.poll() is None:
                    self.end([proc])
                if tracked:
                    with self.lock:
                        self.live.pop(proc.pid, None)
                        if proc.pid in self.stopped:
                            self.stopped.discard(proc.pid)
                            rc = STOPPED_RC
            out.seek(0)
            err.seek(0)
            return rc, out.read(OUTPUT_KEEP_BYTES).decode('utf-8', 'replace'), err.read(ERR_KEEP_BYTES).decode('utf-8', 'replace')

    @staticmethod
    def end(procs, leader_done=False):
        """SIGTERM every group, wait up to KILL_GRACE for the leaders, then SIGKILL every group (a group whose members
        are all gone answers ESRCH, which is ignored), reap the leaders for at most 5 s. leader_done: the leader
        already exited normally; only a SIGKILL to its group follows (no grace: nothing should remain). Returns the
        number of leaders still not reaped (unresolved)."""
        if not leader_done:
            for proc in procs:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except OSError:
                    pass
            deadline = time.monotonic() + KILL_GRACE
            for proc in procs:
                try:
                    proc.wait(timeout=max(0.1, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    pass
        unresolved = 0
        for proc in procs:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                unresolved += 1
        return unresolved

    def kill_all(self, reason='stop'):
        """End every live process group (reason 'stop': their runs return STOPPED_RC; 'cleanup': the end of a phase).
        Returns (targeted, unresolved): how many groups were signalled and how many leaders were still not reaped."""
        with self.lock:
            procs = list(self.live.values())
            if reason == 'stop':
                self.stopped.update(p.pid for p in procs)
        unresolved = self.end(procs) if procs else 0
        return len(procs), unresolved


_RUNNER = Procs()


def run_bounded(argv, *, timeout, cwd=None, env=None, tracked=True):
    """One process through the shared runner (life-ctl, life-check and the cancel calls)."""
    return _RUNNER.run(argv, timeout, cwd=cwd, env=env, tracked=tracked)


PROTECTED_ENV = re.compile(r'^(PATH|HOME|LANG|LC_\w+|PYTHON\w*|DASH_URL|SYMBLIC_\w*|LD_\w+|DASHBOARD_DIR|GIT_\w+)$')


def child_env(extra=None):
    """The environment every trusted LIFE subprocess gets: nothing inherited, fixed PATH, thermal guard on (it only
    refuses on a hot node: a call named @NODE is never re-placed, symblic_apply pins it), git's system and global
    configuration off (GIT_CONFIG_NOSYSTEM, GIT_CONFIG_GLOBAL=/dev/null), replacement refs and system attributes
    ignored (GIT_NO_REPLACE_OBJECTS, GIT_ATTR_NOSYSTEM). `extra` may add only keys outside
    PROTECTED_ENV. Candidate (agent-written) code never runs with this environment: it runs under sandbox_argv() with
    an empty temporary HOME."""
    env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/home/operator', 'LANG': 'C.UTF-8',
           'PYTHONDONTWRITEBYTECODE': '1', 'DASH_URL': DASH, 'SYMBLIC_THERMAL': '1',
           'SYMBLIC_CALL_WALL_S': str(CALL_TIMEOUT), 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
           'GIT_TERMINAL_PROMPT': '0', 'GIT_NO_REPLACE_OBJECTS': '1', 'GIT_ATTR_NOSYSTEM': '1'}
    for key, value in (extra or {}).items():
        if PROTECTED_ENV.match(key):
            raise ValueError(f'child_env: {key} is protected')
        env[key] = str(value)
    return env


# Every git command LIFE runs in a workspace that candidate code could have written. GIT_SAFE disables hooks,
# fsmonitor, external diff, pagers, proxies, ssh commands, credential helpers and askpass, and child_env() turns off
# system/global configuration, system attributes and replacement objects. Filters, includes, aliases and every other
# config-driven command are NOT neutralised key by key: git_admin_problems() (an allowlist of the whole .git/config,
# no commondir, no alternates) runs before every trusted git command, and git_meta_sha256() is compared around every
# sandboxed run (a sandboxed run that a crash interrupted is distrusted at the next tick: workspace_guard rows).
GIT_SAFE = ('-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false', '-c', 'core.sshCommand=/bin/false',
            '-c', 'diff.external=', '-c', 'protocol.ext.allow=never', '-c', 'core.pager=cat',
            '-c', 'core.attributesFile=/dev/null', '-c', 'core.gitProxy=', '-c', 'core.alternateRefsCommand=',
            '-c', 'credential.helper=', '-c', 'core.askPass=')
GIT_META = ('config', 'config.worktree', 'info', 'hooks', 'objects/info', 'HEAD', 'packed-refs', 'refs', 'worktrees',
            'shallow', 'commondir', 'modules', 'gitdir')
# The only configuration a LIFE workspace may hold (what clone, sparse-checkout and symblic-task workspace write):
# {section or (section, subsection): keys}; '*' = any subsection. Anything else (include, filter, diff, alias, url,
# credential, core.* keys outside the list, a continuation line) is a workspace problem.
GIT_CONFIG_ALLOWED = {
    'core': {'repositoryformatversion', 'filemode', 'bare', 'logallrefupdates', 'sparsecheckout', 'sparsecheckoutcone',
             'ignorecase', 'precomposeunicode'},
    ('remote', 'origin'): {'url', 'fetch', 'tagopt'},
    ('branch', '*'): {'remote', 'merge'},
    'extensions': {'worktreeconfig'},
}


def _sha_nofollow(path):
    """sha256 of a regular file opened with O_NOFOLLOW | O_NONBLOCK (a FIFO never blocks), checked on the descriptor."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError(f'{path} is not a regular file')
        h = hashlib.sha256()
        while True:
            block = os.read(fd, 1 << 16)
            if not block:
                return h.hexdigest()
            h.update(block)
    finally:
        os.close(fd)


def git_meta_sha256(ws):
    """sha256 over the administrative parts of ws/.git that change what git reads or runs: GIT_META (configuration,
    info/ with attributes and grafts, hooks, objects/info with alternates, HEAD, packed-refs, refs (replace refs
    included), worktrees, shallow, commondir, modules, gitdir) by content, plus the names and sizes of every loose
    object (objects/??/*; packs are immutable). Visited with lstat; a symlink, FIFO, socket or device anywhere, more
    than GIT_META_MAX_ENTRIES entries, more than GIT_META_MAX_BYTES of content, or more than GIT_TIMEOUT seconds raises
    ValueError (the caller treats the workspace as broken). Taken before candidate code runs in ws and compared after."""
    base = os.path.join(ws, '.git')
    if not stat.S_ISDIR(os.lstat(base).st_mode):
        raise ValueError('.git is not a real directory')
    h = hashlib.sha256()
    state = {'n': 0, 'bytes': 0, 'end': time.monotonic() + GIT_TIMEOUT}

    def visit(rel):
        state['n'] += 1
        if state['n'] > GIT_META_MAX_ENTRIES or time.monotonic() > state['end']:
            raise ValueError('the .git administrative tree is too large to inspect')
        path = os.path.join(base, rel)
        st = os.lstat(path)
        if stat.S_ISREG(st.st_mode):
            state['bytes'] += st.st_size
            if state['bytes'] > GIT_META_MAX_BYTES:
                raise ValueError('the .git administrative files are too large to inspect')
            h.update(rel.encode() + b'\0f\0' + _sha_nofollow(path).encode() + b'\n')
        elif stat.S_ISDIR(st.st_mode):
            h.update(rel.encode() + b'\0d\n')
            for name in sorted(os.listdir(path)):
                visit(rel + '/' + name)
        else:
            raise ValueError(f'.git/{rel} is not a regular file or directory')
    for rel in GIT_META:
        if os.path.lexists(os.path.join(base, rel)):
            visit(rel)
        else:
            h.update(rel.encode() + b'\0absent\n')
    objects = os.path.join(base, 'objects')
    for d in sorted(os.listdir(objects)) if os.path.isdir(objects) else []:
        if re.fullmatch(r'[0-9a-f]{2}', d):
            dpath = os.path.join(objects, d)
            if not stat.S_ISDIR(os.lstat(dpath).st_mode):
                raise ValueError(f'.git/objects/{d} is not a directory')
            for name in sorted(os.listdir(dpath)):
                state['n'] += 1
                if state['n'] > GIT_META_MAX_ENTRIES:
                    raise ValueError('too many loose objects to inspect')
                st = os.lstat(os.path.join(dpath, name))
                if not stat.S_ISREG(st.st_mode):
                    raise ValueError(f'.git/objects/{d}/{name} is not a regular file')
                h.update(f'objects/{d}/{name}\0{st.st_size}\n'.encode())
    return h.hexdigest()


def git_config_problems(ws):
    """Every line of ws/.git/config and config.worktree must be a comment, a section header [name] or [name "sub"],
    or a key = value line whose (section, key) GIT_CONFIG_ALLOWED lists; each file a regular file of at most 64 KiB."""
    out = []
    for name in ('config', 'config.worktree'):
        path = os.path.join(ws, '.git', name)
        try:
            st = os.lstat(path)
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(st.st_mode) or st.st_size > 65536:
            out.append(f'.git/{name} is not a regular file of at most 64 KiB')
            continue
        section = None
        for raw in read_in(os.path.join(ws, '.git'), name, 65536).decode('utf-8', 'replace').splitlines():
            ln = raw.strip()
            if not ln or ln[0] in '#;':
                continue
            m = re.fullmatch(r'\[([A-Za-z][A-Za-z0-9-]*)(?:\s+"([^"\\]*)")?\]', ln)
            if m:
                section = (m.group(1).lower(), m.group(2))
                continue
            m = re.fullmatch(r'([A-Za-z][A-Za-z0-9-]*)\s*(?:=\s*([^\\]*))?', ln)
            if not m or section is None:
                out.append(f'.git/{name}: a line git_config_problems cannot read: {ln[:60]}')
                continue
            key = m.group(1).lower()
            sect, sub = section
            allowed = (GIT_CONFIG_ALLOWED.get(sect) if sub is None else
                       GIT_CONFIG_ALLOWED.get((sect, sub)) or GIT_CONFIG_ALLOWED.get((sect, '*')))
            if not allowed or key not in allowed:
                out.append(f'.git/{name}: {sect}{"." + sub if sub else ""}.{key} is not an allowed setting')
    return out


def git_admin_problems(ws):
    """Checked before EVERY trusted git command in a LIFE workspace (Tick.git, life-ctl git): ws/.git is a real
    directory (not a file, not a symlink: never a pointer to other storage); no commondir, gitdir or
    objects/info/alternates file; the configuration passes git_config_problems. A problem means git never runs there:
    the workspace is deleted and re-created from a trusted source."""
    base = os.path.join(ws, '.git')
    try:
        if not stat.S_ISDIR(os.lstat(base).st_mode):
            return ['.git is not a real directory']
    except OSError as exc:
        return [f'.git: {exc.strerror}']
    out = [f'.git/{rel} exists' for rel in ('commondir', 'gitdir', 'objects/info/alternates')
           if os.path.lexists(os.path.join(base, rel))]
    try:
        out += git_config_problems(ws)
    except OSError as exc:
        out.append(f'.git/config: {exc}')
    return out


TOOL_ROOT_RX = re.compile(r'(/home/operator/agent-upgrades/envs/[A-Za-z0-9._-]+|/home/operator/\.local/share/uv/tools/'
                          r'[A-Za-z0-9._-]+)/bin/[A-Za-z0-9._-]+')


def devcheck_tools():
    """(env additions, read-exec dirs, refused) so bin/devcheck finds ruff and ast-grep inside the sandbox: the same
    candidate paths scripts/devcheck.py:find_ruff/find_ast_grep use, resolved through symlinks. A tool is granted ONLY
    when its real path matches TOOL_ROOT_RX (an isolated tool environment: agent-upgrades/envs/<name> or
    .local/share/uv/tools/<name>), and the grant is that environment's root, never a parent of STATE; a tool that
    exists but resolves elsewhere is listed in `refused` (life-check sandboxed then exits 125). RAYON_NUM_THREADS=4
    bounds both Rust tools' threads (SCOPE_TASKS_MAX)."""
    env, dirs, refused = {'RAYON_NUM_THREADS': '4'}, [], []
    for var, candidates in (('DEVCHECK_RUFF', ('/home/operator/agent-upgrades/envs/ruff/bin/ruff', '/home/operator/.local/bin/ruff')),
                            ('DEVCHECK_AST_GREP', ('/home/operator/.local/bin/ast-grep',
                                                   '/home/operator/.local/share/uv/tools/ast-grep-cli/bin/ast-grep'))):
        for path in candidates:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                real = os.path.realpath(path)
                m = TOOL_ROOT_RX.fullmatch(real)
                if m:
                    env[var] = real
                    dirs.append(m.group(1))
                else:
                    refused.append(real)
                break
    return env, sorted(set(dirs)), refused


def sandbox_argv(cwd, home, command, rx=(), env_extra=None):
    """Candidate code (a watched test, check 0 of a codebase run, the gate) runs ONLY like this: the repository's
    Landlock launcher with --require (a kernel without Landlock network rules, ABI 4, refuses with exit 125, never an
    unsandboxed run), the system read-only, `cwd` and the empty temporary `home` the only writable places besides the
    launcher's SYSTEM_RW devices (/dev/shm among them: GAP 17), the rest of /home/operator (STATE, ~/.ssh, ~/.config,
    the live checkout, .env) absent, NO TCP connect and no TCP bind (--net-connect with an empty port list), no unix
    sockets (--no-unix: a seccomp filter, abstract ones included), signals only inside the sandbox (Landlock scoping,
    ABI 6; the host has 8; the probe checks it), only stdin/stdout/stderr inherited (close_fds), and an environment
    built from nothing. NOT blocked: UDP (the launcher has no UDP rule: GAP 15) and metadata changes such as chmod on
    paths it cannot read (Landlock does not cover them: GAP 16; STOP and FREEZE then read as present)."""
    env = ['PATH=/usr/local/bin:/usr/bin:/bin', 'HOME=' + home, 'LANG=C.UTF-8', 'TMPDIR=' + home,
           'PYTHONDONTWRITEBYTECODE=1']
    for key, value in (env_extra or {}).items():
        env.append(f'{key}={value}')
    argv = ['env', '-i', *env, SYS_PY, '-I', '-B', SANDBOX_LAUNCHER, '--cwd', cwd, '--rw', cwd, '--rw', home,
            '--require', '--no-unix', '--net-connect', '']
    for path in rx:
        argv += ['--rx', path]
    return argv + ['--', *command]


# What the sandbox probe asserts from INSIDE the sandbox (life-ctl gate-selftest and arm run it with the gate's own
# read-exec grants; exit 0 = every boundary held, 1 = one broke, 2 = inconclusive). argv: the sentinel file, the pid of
# a process outside the sandbox, then the paths that must be unreadable. Every denial must be a PermissionError (the
# policy's answer): a missing target, a refused connection or a timeout is inconclusive, never a pass. The trusted side
# first proves every target exists and is reachable from outside (sandbox_probe_targets). It writes and removes one
# file in /dev/shm and opens one UDP socket, and reports both as known gaps (GAP 15, GAP 17), not as failures.
SANDBOX_PROBE = (
    "import os, socket, sys\n"
    "sentinel, outside, paths = sys.argv[1], int(sys.argv[2]), sys.argv[3:]\n"
    "bad, odd, info = [], [], []\n"
    "def denied(what, fn):\n"
    "    try:\n"
    "        fn(); bad.append(what + ' allowed')\n"
    "    except PermissionError:\n"
    "        pass\n"
    "    except OSError as exc:\n"
    "        odd.append(what + ' ' + type(exc).__name__)\n"
    "for p in [sentinel] + paths:\n"
    "    denied('read ' + p, (lambda p=p: open(p, 'rb').close()) if os.path.isfile(p) or p == sentinel else (lambda p=p: os.listdir(p)))\n"
    "def tcp():\n"
    "    s = socket.create_connection(('127.0.0.1', 8080), 2); s.close()\n"
    "denied('tcp 127.0.0.1:8080', tcp)\n"
    "denied('unix socket', lambda: socket.socket(socket.AF_UNIX).close())\n"
    "denied('signal outside', lambda: os.kill(outside, 0))\n"
    "try:\n"
    "    p = '/dev/shm/life-probe-%d' % os.getpid(); open(p, 'w').close(); os.remove(p); info.append('/dev/shm writable (GAP 17)')\n"
    "except OSError:\n"
    "    info.append('/dev/shm not writable')\n"
    "try:\n"
    "    socket.socket(socket.AF_INET, socket.SOCK_DGRAM).close(); info.append('udp sockets open (GAP 15)')\n"
    "except OSError:\n"
    "    info.append('udp sockets denied')\n"
    "verdict = 'BROKEN: ' + ', '.join(bad) if bad else 'INCONCLUSIVE: ' + ', '.join(odd) if odd else 'held'\n"
    "print('sandbox probe:', verdict, '|', '; '.join(info)); sys.exit(1 if bad else 2 if odd else 0)\n")


def sandbox_probe_targets(sentinel):
    """The trusted side of the probe: the paths the sandbox must not read (STATE, ~/.ssh, the live checkout, the
    sentinel file) each exist and are readable HERE, and 127.0.0.1:8080 accepts a connection HERE. Returns the problems
    (non-empty: the probe would be inconclusive, so it is not run)."""
    import socket
    out = []
    for p in (sentinel, STATE, '/home/operator/.ssh', REPO):
        try:
            if os.path.isdir(p):
                os.listdir(p)
            else:
                open(p, 'rb').close()
        except OSError as exc:
            out.append(f'{p} is not readable outside the sandbox ({type(exc).__name__}): the probe would prove nothing')
    try:
        socket.create_connection(('127.0.0.1', 8080), 2).close()
    except OSError as exc:
        out.append(f'127.0.0.1:8080 does not answer outside the sandbox ({type(exc).__name__})')
    return out


def shm_entries():
    """{(name, inode)} of this uid's entries in /dev/shm (sandboxed code can write there: GAP 17)."""
    out = set()
    try:
        for e in os.scandir('/dev/shm'):
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            if st.st_uid == os.getuid():
                out.add((e.name, st.st_ino))
    except OSError:
        pass
    return out


def shm_cleanup(before):
    """Remove every entry of this uid in /dev/shm that did not exist (same name and inode) before a sandboxed run, so
    nothing RAM-backed outlives it and nothing carries from one candidate run to the next. Returns the count."""
    n = 0
    for name, _ino in shm_entries() - before:
        path = os.path.join('/dev/shm', name)
        try:
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path, ignore_errors=True)
            else:
                os.remove(path)
            n += 1
        except OSError:
            pass
    return n


def scope_env():
    """child_env plus XDG_RUNTIME_DIR, so systemd-run --user reaches the user manager from the tick's unit (or from
    the dashboard's, for life-check.py sandboxed)."""
    return child_env({'XDG_RUNTIME_DIR': f'/run/user/{os.getuid()}'})


def scope_argv(command, memory='4G', runtime=None, name='work'):
    """Heavy local work (watched tests, the gate, clones, git fetches, page fetches, slot programs, check 0 of a
    codebase run) runs in its own transient scope in work.slice (CLAUDE.md: new local workloads get separate
    work.slice scopes), outside the tick's and the dashboard's MemoryMax: unit life-<name>-<8 hex>.scope, MemoryMax
    `memory`, CPUQuota 200 %, TasksMax SCOPE_TASKS_MAX, RuntimeMaxSec `runtime` + KILL_GRACE (runtime is MANDATORY and
    positive: a scope without a lifetime is refused), so a process that outlives the tick still ends; STOP and the
    unit's ExecStopPost stop every life-*.scope (stop_scopes). A scope that cannot be created fails the work (systemd-run
    exits non-zero); it is never run unscoped."""
    if not runtime or int(runtime) <= 0:
        raise ValueError('scope_argv needs a positive runtime')
    unit = f'life-{name}-{secrets.token_hex(4)}'
    return ['systemd-run', '--user', '--scope', '--quiet', '--collect', f'--unit={unit}', '--slice=work.slice',
            '-p', f'MemoryMax={memory}', '-p', 'CPUQuota=200%', '-p', f'TasksMax={SCOPE_TASKS_MAX}',
            '-p', f'RuntimeMaxSec={int(runtime) + KILL_GRACE}', '--nice=19', '--', *command]


def stop_scopes():
    """systemctl --user stop 'life-*.scope' (every transient scope LIFE started), then the list of life-*.scope units
    still loaded (empty = every scope ended). Returns (rc, still loaded)."""
    rc = run_bounded(['systemctl', '--user', 'stop', 'life-*.scope'], timeout=CANCEL_TIMEOUT, env=scope_env(),
                     tracked=False)[0]
    _rc, out, _err = run_bounded(['systemctl', '--user', 'list-units', '--no-legend', '--plain', 'life-*.scope'],
                                 timeout=CANCEL_TIMEOUT, env=scope_env(), tracked=False)
    return rc, [ln.split()[0] for ln in (out or '').splitlines() if ln.strip()]


# ------------------------------------------------------------------------------------------- node holds


HOLD_CAUSES = ('infra', 'timeout', 'orphan', 'job')


def hold_node(conn, node, cause, subject, until, reason):
    """Add or extend ONE hold of a node: (node, cause, subject) is its key, so independent holds never overwrite one
    another, and renewing a hold never shortens it (until = the later of the two). cause: infra (the node answered
    infra), timeout (subject = the program that timed out: only that program waits), orphan (a killed or stopped
    call may still run its fleet-runner run), job (subject = the job id or label; until 0 = no expiry: only a listing that
    shows the job ended, or the operator, releases it)."""
    if cause not in HOLD_CAUSES:
        raise ValueError(f'unknown hold cause {cause!r}')
    conn.execute('INSERT INTO node_holds (node, cause, subject, until, reason) VALUES (?, ?, ?, ?, ?) ON CONFLICT '
                  '(node, cause, subject) DO UPDATE SET until=CASE WHEN node_holds.until = 0 OR excluded.until = 0 THEN 0 '
                  'ELSE max(node_holds.until, excluded.until) END, reason=excluded.reason',
                  (node, cause, subject, int(until), one_line(reason, 400)))


def node_held(conn, node, program=None, t=None):
    """True while any hold of the node applies: an infra, orphan or job hold, or a timeout hold for `program` (a
    program-less question asks about every hold but timeouts). A job hold with until 0 never expires by itself."""
    t = now() if t is None else t
    return bool(conn.execute("SELECT 1 FROM node_holds WHERE node=? AND (until=0 OR until > ?) AND (cause != 'timeout' "
                             'OR subject=?)', (node, t, program or '')).fetchone())


# ------------------------------------------------------------------------------------------- STOP


def find_jobs_by_label(labels):
    """{label: [job rows]} for LIFE's benchmark labels in the paged jobs listing (JOBS_PAGE per page, at most
    JOBS_PAGES_MAX pages), and whether the listing was read completely (a capped or failed listing is never proof that
    a label has no job)."""
    found, offset, complete = {}, 0, False
    try:
        for _ in range(JOBS_PAGES_MAX):
            page = http_json(f'/api/cluster/jobs?kind=map&limit={JOBS_PAGE}&offset={offset}', timeout=HTTP_SLOW_TIMEOUT)
            jobs = page.get('jobs') if isinstance(page.get('jobs'), list) else []
            for j in jobs:
                label = (j.get('meta') or {}).get('label') if isinstance(j, dict) else None
                if label in labels:
                    found.setdefault(label, []).append(j)
            offset += JOBS_PAGE
            total = page.get('total') if type(page.get('total')) is int else None
            if total is None:
                break
            if not jobs or offset >= total:
                complete = True
                break
    except Telemetry:
        complete = False
    return found, complete


def stop_everything(conn, procs=None, reason='owner STOP'):
    """Needs only the registry (never the active release, never a schema check). In this order: start stopping every
    life-*.scope in a helper thread and, at the same time, end every local LIFE process group (one shared grace);
    remove ARMED (a STOP disarms: after unstop the operator arms again); ask the platform to cancel EVERY LIFE autogen run
    and benchmark job, each target on its own (one failure never skips the rest; the answers are collected first; a
    benchmark with no job id yet is looked up by its label first); then record what it can, each record in its own
    transaction (a registry that cannot be written never blocks a cancel): a cancel the platform accepted is only a
    REQUEST, so the run or job stays live/running with cancel_cause 'stop' (set only when no cause is recorded yet;
    the diagnostic detail is never overwritten) until a poll sees it end; every open call intent holds its node
    ORPHAN_HOLD_SECONDS and model-stage items return to the queue; a `stopped` notice names every target whose
    cancel was not accepted and every scope or process group not yet confirmed ended. Safe to call at every tick while
    STOP exists."""
    scope_box = {}
    scope_thread = threading.Thread(target=lambda: scope_box.update(result=stop_scopes()), daemon=True)
    scope_thread.start()
    targeted, unresolved_procs = procs.kill_all('stop') if procs else (0, 0)
    try:
        os.remove(ARMED_FILE)
    except OSError:
        pass
    runs, benches = [], []
    try:
        runs = conn.execute("SELECT request_id, run_id FROM runs WHERE state IN ('submitting','live','submit_unknown')").fetchall()
    except sqlite3.Error as exc:
        log(f'STOP: runs unreadable: {exc}')
    try:
        benches = conn.execute("SELECT item_id, payload FROM items WHERE state='running' AND stage='bench'").fetchall()
    except sqlite3.Error as exc:
        log(f'STOP: benchmark items unreadable: {exc}')
    answers = []
    for run in runs:
        try:
            rc, _out, err = run_bounded([TASK, 'autogen', 'cancel', run['run_id']], timeout=CANCEL_TIMEOUT,
                                        env=child_env(), tracked=False)
            answers.append(('run', run['request_id'], run['run_id'], rc == 0))
        except Exception:  # noqa: BLE001 - one failed cancel never skips the rest
            answers.append(('run', run['request_id'], run['run_id'], False))
    jobs, labels = {}, set()
    for item in benches:
        try:
            p = json.loads(item['payload']) or {}
        except ValueError:
            p = {}
        jobs[item['item_id']] = [str(p.get('job_id') or '')] if p.get('job_id') else []
        if not p.get('job_id') and p.get('label'):
            labels.add(p['label'])
            jobs[item['item_id']] = ('label', p['label'])
    by_label, _complete = find_jobs_by_label(labels) if labels else ({}, True)
    for item_id, target in jobs.items():
        ids = [str(j.get('id') or '') for j in by_label.get(target[1], [])] if isinstance(target, tuple) else target
        ok = bool(ids)
        for job in ids:
            try:
                ok = http_json('/api/cluster/job/cancel', {'id': job}, timeout=JOB_CANCEL_TIMEOUT).get('success') is True and ok
            except Telemetry:
                ok = False
        answers.append(('job', item_id, ','.join(ids) or f'label {target[1] if isinstance(target, tuple) else "?"}', ok))
    for kind, key, _target, ok in answers:
        try:
            with Tx(conn):
                if kind == 'run':
                    conn.execute("UPDATE runs SET cancel_cause=CASE WHEN cancel_cause='' THEN 'stop' ELSE cancel_cause END "
                                 'WHERE request_id=?', (key,))
                else:
                    conn.execute('UPDATE items SET outcome=? WHERE item_id=?',
                                 ('benchmark cancel requested (STOP)' if ok else 'benchmark cancel not confirmed (STOP)', key))
        except sqlite3.Error:
            pass
    unresolved = [target for _k, _key, target, ok in answers if not ok]
    scope_thread.join(CANCEL_TIMEOUT * 2 + KILL_GRACE)
    scopes_left = (scope_box.get('result') or (1, ['unknown']))[1]
    try:
        with Tx(conn):
            for r in conn.execute('SELECT node, call_id FROM call_intents').fetchall():
                hold_node(conn, r['node'], 'orphan', r['call_id'], now() + ORPHAN_HOLD_SECONDS,
                          'STOP: an ended model process may leave its fleet-runner run')
            conn.execute('DELETE FROM call_intents')
            conn.execute("UPDATE items SET state='queued', updated_at=? WHERE state='running' AND stage NOT IN "
                         "('patch','draft','bench')", (now(),))
            notice(conn, 'stopped', 'STOP', f'{reason}: {targeted} local process group(s) signalled ({unresolved_procs} '
                   f'not yet reaped), scopes still loaded: {", ".join(scopes_left) or "none"}; ARMED removed; cancel '
                   f'requested for {len(answers) - len(unresolved)} run(s)/job(s); not confirmed: '
                   f'{", ".join(unresolved) or "none"}. Runs and jobs stay live until a poll sees them end. '
                   'life-ctl unstop removes STOP; life-ctl arm is needed again; cancelled work returns to its queue and '
                   'starts again only after that arm.')
    except sqlite3.Error as exc:
        log(f'STOP: the registry could not record the stop: {exc}')
    log(f'STOP: asked {len(answers)} cancel(s), signalled {targeted}, not confirmed {len(unresolved)}, scopes left '
        f'{len(scopes_left)}')
    return len(answers) - len(unresolved), unresolved


# ------------------------------------------------------------------------------------------- platform contract

CONTRACT = (                                      # (file, regex, the fact LIFE relies on); LIFE.md section 17
    ('symblicos/autogen.py', r"run_id = 'autogen-' \+ hashlib\.sha256\(request_id\.encode\(\)\)\.hexdigest\(\)\[:24\]",
     'run id derivation'),
    ('symblicos/autogen.py', r"if row\['request_digest'\] != request_digest:",
     'a repeated start with the same request id and the same statements and policy returns the existing run'),
    ('symblicos/autogen.py', r"ADMITTED_ENGINES = \([^)]*'agy'", 'agy admitted for autogen'),
    ('symblicos/autogen.py', r"TERMINAL = \{'completed', 'failed', 'cancelled', 'unknown', 'stuck'\}", 'terminal run states'),
    ('symblicos/autogen.py', r"os\.path\.isdir\(os\.path\.join\(cwd, '\.git'\)\)", 'cwd must be a git workspace'),
    ('symblicos/autogen.py', r"^CHECK_TIMEOUT = 120$", 'policy checks time out at 120 s'),
    ('symblicos/autogen.py', r"'base': base, 'policy': policy, 'lines': lines,", 'a run row carries its base, policy (with sha256) and lines'),
    ('symblicos/autogen.py', r"base = \{'engine': engine, 'model': body\.get\('model'\) or '', 'effort': body\.get\('effort'\) or '', 'node': node,",
     'the run base names its engine, node and cwd'),
    ('symblicos/autogen.py', r"if row\['status'\] not in \('completed', 'failed', 'cancelled'\) and not row\['cancel_requested'\]:",
     'autogen cancel only REQUESTS the end of a run (and answers ok for an ended one)'),
    ('symblicos/autogen.py', r"def sandbox_prefix\(folder, home, extra_files=\(\)\):", 'the Landlock check sandbox exists'),
    ('symblicos/autogen.py', r"def _run\(argv, cwd, timeout=CHECK_TIMEOUT, shell=False, limit=MAX_OUTPUT\):",
     'policy checks run in the dashboard process (so life-check.py sandboxed puts candidate code in its own scope)'),
    ('symblicos/autogen.py', r"attempt\['agent_id'\] = step\.get\('agent_id'\) or ''",
     'each run attempt names its hub agent (nodes[].attempts[].agent_id), whose checkout LIFE discards after collection'),
    ('agent_hub.py', r"'work/discard': lambda: work_action\('discard', data\.get\('id'\)\),",
     'POST /api/agents/work/discard removes an agent\'s checkout on the host and on its node'),
    ('agent_hub.py', r"wt = os\.path\.join\(os\.path\.dirname\(top\), f'\{os\.path\.basename\(top\)\}\.agents', f'\{name\}-\{stamp\}'\)",
     'an agent checkout on the host is <workspace>.agents/<name>-<stamp> (counted by the storage rule)'),
    ('symblicos_engine.py', r"result = \{'version': symblic_autogen\.VERSION, 'limits': symblic_autogen\.LIMITS,\s*'defaults': symblic_autogen\.DEFAULTS",
     'the autogen catalogue answers version and defaults'),
    ('symblic_autogen.py', r"^VERSION = 1$", 'autogen policy version 1'),
    ('symblic_autogen.py', r"^VERBS = \('create', 'extend', 'add', 'write', 'run', 'make', 'build', 'update',",
     'statement verbs (each LIFE template line starts with one: VALIDATE)'),
    ('symblic_autogen.py', r"'wall_seconds': \(300, 172800\)", 'wall_seconds limits (LIFE uses 2700)'),
    ('symblic_autogen.py', r"'agents_max': \(1, 96\)", 'agents_max limits'),
    ('symblic_autogen.py', r"def normalize\(spec, \*, engines=\(\), nodes=\(\)\)", 'normalize signature'),
    ('symblic_autogen.py', r"policy\['sha256'\] = digest\(\{k: v for k, v in policy\.items\(\) if k not in \('engines', 'nodes'\)\}\)",
     'the policy sha256 excludes engines and nodes'),
    ('symblic_autogen.py', r"'perpetual': False, 'checks': \{\}, 'final': \[\], 'hidden': \[\], 'syntax': True, 'require_change': True,",
     'defaults of the flagless fields (perpetual, final, hidden, syntax, require_change)'),
    ('symblic_autogen.py', r"'until_done': False, 'novelty_limit': 2, 'self_split': True, 'designer': False, 'saturation': 0,",
     'defaults of the flagless fields (until_done, designer)'),
    ('symblic_autogen.py', r"'interval_seconds': 900,\s*'feedback_chars': 2000,", 'defaults of the flagless fields (interval_seconds, feedback_chars)'),
    ('symblic_autogen.py', r"^FAILURE_CLASSES = \('INFRASTRUCTURE', 'REFUSAL', 'NO_OUTPUT',", 'attempt failure labels'),
    ('symblic_autogen.py', r"\\b\(\?:the previous\|the last\|as before\|like above\|earlier\)\\b", 'lint back-reference words'),
    ('bin/symblic-task', r"'--novelty-limit', '--saturation'\}", 'start flags'),
    ('bin/symblic-task', r"FLAGS_WITH_VALUE = \{'--root', '--cwd', '--node', '--engine', '--model', '--effort',",
     'start takes --model and --effort'),
    ('bin/symblic-task', r"for key in \('engine', 'model', 'effort'\):\n\s+if o\.get\(key\):\n\s+body\[key\] = o\[key\]",
     'start sends --model and --effort to autogen (the run base records them)'),
    ('bin/symblic-task', r"def cmd_autogen_get", 'autogen get'),
    ('bin/symblic-task', r"def cmd_autogen_control\(action, o, args\):", 'autogen cancel'),
    ('bin/symblic-task', r"raise ApiError\(f'HTTP \{e\.code\}", 'an HTTP error from start exits REFUSED (1) and prints HTTP <code>'),
    ('bin/symblic-task', r"def cmd_catalog\(o\):\n    d = request\('catalog'\)\n    if o\.get\('json'\):\n        print\(json\.dumps\(d, indent=2",
     'catalog --json prints the catalogue object (nodes[].id, online, ready)'),
    ('bin/symblic-task', r"d = request\('workspace/create', \{'name': args\[0\]\}\)", 'workspace NAME creates a symblicos workspace'),
    ('bin/symblic-task', r"Where a statement names the folder \{cwd\}, use the same relative path inside your checkout",
     'remote agents map the host workspace path into their own checkout'),
    ('bin/symblic', r"p\.add_argument\('--max-calls'", 'symblic run --max-calls'),
    ('bin/symblic', r"p\.add_argument\('--ollama-limits'", 'symblic run --ollama-limits'),
    ('bin/symblic', r"p\.add_argument\('--input', action='append'", 'symblic run --input NAME=VALUE (JSON or text)'),
    ('bin/symblic', r"p\.add_argument\('--dir'", 'symblic run --dir'),
    ('bin/symblic', r"p\.add_argument\('--json', action='store_true'", 'symblic run --json'),
    ('symblic_run.py', r"by = self\._opt\(s, 'by', env\)\n\s+if by is None:\n\s+by = self\.defaults\.get\('applicator'\) or self\.opts\.get\('by'\)",
     'ask-level by wins over --by'),
    ('symblic_run.py', r"signal\.signal\(signal\.SIGTERM, on_signal\)", 'symblic run stops its calls on SIGTERM'),
    ('symblic_run.py', r"return \{'program': self\.program, 'status': self\.status, 'error': self\.error,",
     'the run report carries status and error'),
    ('symblic_run.py', r"'asks': self\.asks, 'calls': self\.calls,", 'the run report counts calls'),
    ('symblic_run.py', r"self\.status = 'done'", 'a finished run reports status done'),
    ('symblic_run.py', r"row = \{'kind': s\.k, 'line': s\.line, 'label': label, 'value': S\.to_plain\(value\),",
     'a return output carries kind and value'),
    ('symblic_apply.py', r"THERMAL_HOT, THERMAL_COOL, THERMAL_TTL = 85\.0, 75\.0", 'thermal thresholds'),
    ('symblic_apply.py', r"placed = node in \('', 'auto', 'nodes'\)", 'a call named @NODE is never re-placed (thermal only refuses)'),
    ('symblic_apply.py', r"os\.environ\.get\('SYMBLIC_CALL_WALL_S'\)", 'SYMBLIC_CALL_WALL_S sets the call wall'),
    ('symblic_apply.py', r"cancelled = ba\.cancel\(\{'id': row\['id'\]\}\)", 'a stopped call cancels its fleet-runner run'),
    ('fleet_runner.py', r"def _check_capacity\(run: dict, kind: str, node_id: str, account: str, cfg: dict\)",
     'one model process per node'),
    ('fleet_runner.py', r"^def cancel\(run: dict\) -> bool:", 'the fleet runner run cancel'),
    ('fleet_runner.py', r"^KV_BYTES_PER_TOKEN_B = 36_000", 'the KV-cache estimate per token per billion parameters (KV_ALLOWANCE_MIB)'),
    ('fleet_runner.py', r"^OLLAMA_OVERHEAD = 256 \* 2\*\*20", 'the Ollama runner overhead (KV_ALLOWANCE_MIB)'),
    ('fleet_runner.py', r"^NODE_CTX_BUCKETS = \(4096, 8192, 16384, 32768\)", 'worker node context buckets (KV_CTX_TOKENS)'),
    ('fleet_runner.py', r"est = chars // 3 \+ 256 \+ \(min\(predict, reply\) if predict > 0 else reply\)",
     'a worker node call\'s context = chars // 3 + 256 + num_predict, rounded up to a bucket'),
    ('fleet_runner.py', r"# worker node Ollama is not capped", 'the model runs in the node\'s uncapped Ollama service (LIFE bounds it by memory admission and the duty cycle)'),
    ('local_research.py', r'def read_page\(url: str, chars: int = PAGE_CHARS\) -> str:', 'read_page'),
    ('local_research.py', r"\+ \('\\n\[…page continues…\]' if len\(text\) > chars else ''\)", 'read_page continuation marker'),
    ('local_research.py', r"^def _denied\(url: str\) -> str:", 'the research URL deny rule'),
    ('local_research.py', r"^def page_text\(html: str\) -> str:", 'HTML to text'),
    ('local_research.py', r"^def pdf_text\(data: bytes", 'PDF to text'),
    ('local_research.py', r"'timeout': STEP_TIMEOUT, 'role': run_label", 'research generations read STEP_TIMEOUT at call time'),
    ('local_research.py', r"deadline = time\.time\(\) \+ STEP_TIMEOUT \+ 120", 'a generation is polled STEP_TIMEOUT + 120 s'),
    ('local_research.py', r"row = ba\.launch\(req\)", 'research generations go through fleet_runner.launch'),
    ('local_research.py', r"^def research\(question: str, model: str = DEFAULT_MODEL, node: str = DEFAULT_NODE, max_tools: int = MAX_TOOLS,\n\s+log=None, gen=None, stop=None\) -> dict:",
     'research signature (stop is checked before every generation)'),
    ('local_research.py', r"for _ in range\(max_tools \+ 2\):", 'research makes at most max_tools + 2 generations'),
    ('local_research.py', r"return \{'model': model, 'node': node, 'answer': answer, 'sources': sources, 'steps': steps,",
     'research returns answer, sources and steps'),
    ('bin/local-research', r"p\.add_argument\('--list'", 'local-research --list (model inventory)'),
    ('bin/local-research', r"print\(f\"\{t\['node'\]:10\} \{t\['model'\]:28\}", 'the inventory line is <node> <model> <size>'),
    ('deep_research.py', r"def safe_fetch\(url: str, max_hops: int = 5, binary: bool = False,", 'safe_fetch: at most 5 hops'),
    ('deep_research.py', r"out = \{'status': r\.status_code, 'url': cur, 'ctype': ctype,", 'safe_fetch returns the HTTP status'),
    ('deep_research.py', r"raise RuntimeError\(f'that file is larger than the \{max_bytes // 1048576\}MB cap'\)", 'safe_fetch: a byte cap'),
    ('deep_research.py', r"raise RuntimeError\('too many redirects'\)", 'safe_fetch: refuses past its redirect limit'),
    ('landlock_sandbox.py', r"if a in \('--ro', '--rx', '--rw', '--cwd'\) and i \+ 1 < len\(argv\):", 'sandbox path flags'),
    ('landlock_sandbox.py', r"if a in \('--require', '--no-unix', '--net-bind-ephemeral'\):", 'sandbox --require/--no-unix'),
    ('landlock_sandbox.py', r"if a == '--net-connect' and i \+ 1 < len\(argv\):", 'sandbox --net-connect'),
    ('landlock_sandbox.py', r"NET_ABI_ERROR = 'network rules need Landlock ABI 4'", 'a kernel without network rules is refused'),
    ('landlock_sandbox.py', r"UDP \(DNS\) and Unix sockets are not network rules", 'the sandbox does not block UDP (GAP 15)'),
    ('landlock_sandbox.py', r"An empty string means no TCP connect at all\.", 'an empty --net-connect list denies every TCP connect'),
    ('landlock_sandbox.py', r"return struct\.pack\('=QQQ', handled, handled_net, SCOPE_SIGNAL\)", 'signals are scoped at Landlock ABI 6 and newer'),
    ('landlock_sandbox.py', r"SYSTEM_RW = \('/dev/null', '/dev/zero', '/dev/random', '/dev/urandom', '/dev/tty',\s+'/dev/pts', '/dev/ptmx', '/dev/shm'\)",
     'sandboxed code can write /dev/shm (GAP 17; LIFE removes what a run left)'),
    ('bin/devcheck', r"bin/devcheck --changed BASE", 'devcheck --changed BASE'),
    ('scripts/devcheck.py', r"r = git\(root, 'diff', '-U0', '--no-color', '--no-ext-diff', '--no-renames', base, '--'\)",
     'devcheck --changed BASE diffs the working tree (uncommitted changes included) against BASE'),
    ('scripts/devcheck.py', r"say\(f'devcheck: \{what\}: \{len\(ctx\.changes\)\} file\(s\)'", 'devcheck prints how many files it checks'),
    ('scripts/devcheck.py', r"tests = 'skip' if args\.hook or args\.no_tests else", 'devcheck --no-tests runs no test (the gate runs the focused test itself)'),
    ('scripts/devtest.py', r"def uv_command\(\):", 'bin/devtest needs uv and a package cache (why the gate passes --no-tests)'),
    ('cluster_engine.py', r"if route == 'map':", 'cluster map route'),
    ('cluster_engine.py', r"^CMD_TIMEOUT_MAX = 3600", 'a map job timeout is at most 3600 s'),
    ('cluster_engine.py', r"^OUT_HEAD = 40_000", 'a job keeps the first 40000 bytes of each node output'),
    ('cluster_engine.py', r"shlex\.quote\(cmd\.replace\('\{\{item\}\}', '\"\$1\"'\) \+ ' 2>&1'\)", 'map passes {{item}} as "$1"'),
    ('cluster_engine.py', r"'label': str\(data\.get\('label'\) or ''\)\[:80\],", 'map stores the label in meta.label'),
    ('cluster_engine.py', r"_fanout_job\('map', targets, make, meta, timeout, heavy=True\)", 'map is a job'),
    ('cluster_engine.py', r"'out': _head\(body\),", 'a job keeps each node output under out[node].out'),
    ('cluster_engine.py', r"limit = _int\(handler\.get_query_param\('limit'\), 40, 1, 200\)", 'jobs listing pages of 200'),
    ('cluster_engine.py', r"handler\.send_json\(\{'jobs': page, 'total': len\(rows\), 'offset': offset,", 'the jobs listing gives total'),
    ('cluster_engine.py', r"'ts': int\(time\.time\(\)\)\}\)", 'status ts is the answer time'),
    ('cluster_engine.py', r"'online': online,", 'status rows carry online as a boolean'),
    ('cluster_engine.py', r"'memAvailMiB': int\(v\['memavail'\] / 1048576\)", 'vitals.memavail is in bytes'),
    ('cluster_engine.py', r"for key in \('cpu', 'temp', 'uptime', 'volts'\):", 'vitals.cpu and vitals.temp are numbers'),
    ('cluster_engine.py', r"p load \"\$\(cut -d' ' -f1-3 /proc/loadavg", 'vitals.load is the node\'s 1, 5 and 15 minute load averages'),
    ('cluster_engine.py', r"p cpus \"\$\(nproc", 'vitals.cpus is the node\'s processor count'),
    ('cluster_engine.py', r"vit\['load'\] = \[float\(x\) for x in vit\['load'\]\.split\(','\)\[:3\]\]", 'vitals.load arrives as a list of three numbers'),
    ('cluster_engine.py', r"TENANT_STACKS = \{'node-h': \('protected service stack'", 'node-h hosts the protected service stack'),
    ('host_routes.py', r"route in \('job/cancel', 'jobs/cancel'\)", 'job cancel route'),
    ('host_routes.py', r"handler\.send_json\(\{'success': ok,", 'job cancel answers success (a request, not an end)'),
    ('host_routes.py', r"\('queued', 'running', 'done', 'failed', 'cancelled', 'unknown'\)", 'job statuses'),
    ('cluster_highpower.py', r"route=='state'", 'highpower state route'),
    ('cluster_highpower.py', r"'restUntil':rest_until\(s\),'cool':cool", 'highpower view: restUntil and cool'),
    ('cluster_highpower.py', r"isinstance\(s\.get\('started'\),\(int,float\)\):return 0", 'restUntil is 0 when no rest is pending'),
    ('cluster_highpower.py', r"s\.get\('phase'\) not in \('off','applying','active','partial','restoring','restore_pending'\)",
     'highpower phase values'),
    ('agent_hub.py', r"'node': str\(r\['id'\]\)\.startswith\('node'\), 'ready': ready, 'notes': notes,", 'catalog ready per engine'),
    ('agent_hub.py', r"REMOTE_ENGINES = \([^)]*'agy'", 'agy runs remotely'),
    ('agent_hub.py', r"worktree add -q \{q\(wt\)\} \{q\(git\[\"branch\"\]\)\}", 'a worker node agent checkout is a full worktree of the branch'),
    ('restart-host.sh', r"\S", 'the operator restart script life-ctl apply names exists'),
)


def contract_problems():
    """The platform facts LIFE relies on, checked from the source text (no import with side effects). Any problem
    holds all new work and opens a `contract` notice. Recovery: read the platform change; if LIFE's assumption still
    holds, update the matching CONTRACT row here and LIFE.md section 17 together, run VALIDATE.sh (must end STATIC
    PASS), re-arm (the kit hash changed), and run life-ctl.py contract (must print 'contract holds'); the hold clears
    at the next tick. If the fact changed by accident, revert the platform change instead."""
    out = []
    if sqlite3.sqlite_version_info < (3, 32):
        out.append(f'SQLite {sqlite3.sqlite_version} is older than 3.32 (reports bind up to REPORT_TRAVERSE_MAX ids)')
    for rel, pattern, what in CONTRACT:
        path = os.path.join(REPO, rel)
        try:
            with open(path, encoding='utf-8') as handle:
                text = handle.read()
        except OSError as exc:
            out.append(f'{what}: cannot read {rel}: {exc.strerror}')
            continue
        if not re.search(pattern, text, re.M):
            out.append(f'{what}: pattern not found in {rel}')
    return out


# ------------------------------------------------------------------------------------------- generated documentation

LIMITS_LINE_RX = re.compile(r'^([A-Z_][A-Z0-9_]*(?:, [A-Z_][A-Z0-9_]*)*) = (.+?)\s+#\s+(.+)$')


def limits_rows():
    """[(names, shown value, meaning)] of every line of this module's limits block, read from this file's own text.
    LIFE.md section 13 is exactly these rows; VALIDATE.sh check 13 compares. A limits line without a trailing comment
    raises ValueError (every number has a written meaning)."""
    with open(os.path.abspath(__file__), encoding='utf-8') as handle:
        src = handle.read()
    block = src.split('# ' + '-' * 91 + ' limits\n', 1)[1].split('# ' + '-' * 91 + ' small helpers', 1)[0]
    rows = []
    for line in block.splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        m = LIMITS_LINE_RX.match(line)
        if not m:
            raise ValueError(f'a limits line without a meaning: {line[:80]}')
        shown = []
        for name in m.group(1).split(', '):
            value = globals()[name]
            if isinstance(value, dict):
                shown.append(', '.join(f'{k} {v}' for k, v in value.items()))
            elif isinstance(value, re.Pattern):
                shown.append(value.pattern)
            else:
                shown.append(str(value))
        rows.append((m.group(1), ' / '.join(shown), m.group(3).strip()))
    return rows


def limits_table():
    return '\n'.join(['| name | value | meaning |', '|------|-------|---------|']
                     + [f'| {n} | {v.replace("|", "&#124;")} | {m.replace("|", "&#124;")} |' for n, v, m in limits_rows()])


def contract_table():
    return '\n'.join(['| file | fact |', '|------|------|'] + [f'| `{f}` | {what} |' for f, _rx, what in CONTRACT])


def _cell(text):
    """A Markdown table cell: | escaped as &#124;, < and > as entities (placeholder text stays visible)."""
    return str(text).replace('|', '&#124;').replace('<', '&lt;').replace('>', '&gt;')


def notices_table():
    return '\n'.join(['| kind | subject |', '|------|---------|'] + [f'| {k} | {_cell(s)} |' for k, s in NOTICE_KINDS.items()])


def worst_values(organ, fixtures):
    """The largest legal template values of an organ, built from the shared limits (used by VALIDATE.sh and by
    life-ctl's check_release): a TEST_ID_MAX test id, a depth-10 workspace, the longest legal review note, three
    80-character paths with three longest qualified names, the longest request, lesson and migration id."""
    ws = {o: f'{PROJECTS}/life-{o}-10-ffffffff' for o in AGENT_ORGANS}
    if organ == 'codebase':
        test = 'tests.' + 'a' * 64 + '.' + 'b' * 64 + '.' + 'c' * (TEST_ID_MAX - 6 - 64 - 1 - 64 - 1)
        qn = 'q' * 12 + '.' + 'q' * 12 + '.' + 'q' * 11 + '.' + 'q' * 10     # QUALNAME_MAX characters
        return dict(fixtures['codebase'], ws=ws['codebase'], test_id=test, finding_text='x' * FINDING_CUTS[-1],
                    review_note='r' * 240, scope=local_fix_scope([qn] * 3, ['p' * 77 + '.py'] * 3))
    if organ == 'database':
        return dict(fixtures['database'], ws=ws['database'], request='y' * REQUEST_MAX_CHARS, migration_id='9999_' + 'z' * 40)
    return dict(fixtures['selfdev'], ws=ws['selfdev'], lesson='y' * LESSON_MAX_CHARS, program='propose-experiment')
