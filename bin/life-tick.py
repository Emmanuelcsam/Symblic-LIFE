#!/usr/bin/env python3
"""LIFE v2.3 coordinator tick: the organism's only control loop. Code only; it never decides with a model.

Run by the operator's systemd user timer (units/life-tick.timer: 300 s after the previous tick ENDS). One tick, in this
exact order (LIFE.md section 4 is the authoritative text; these numbers are its numbers):

   1. lock          STATE/tick.lock (flock, non-blocking): held -> print and exit 0. From here a watcher thread re-reads
                    control/STOP every second and ends every LIFE process group and life-*.scope when it appears
   2. stop          control/STOP present (or control/ not inspectable) -> stop_everything (needs only the registry,
                    no schema check), then, when the schema is right, a reconciliation-only pass (recover, poll runs
                    and jobs, no start, no re-send), exit 3; then the registry schema must be 5 (else exit 5)
   3. recover       call intents and model items a killed tick left -> nodes held, items queued; a sandboxed run a
                    killed tick never checked -> that workspace deleted; terminal runs not collected -> collected
   4. integrity     STATE directories, active release == its manifest (exact inventory), kit/platform/decisions hashes
                    == the ones at arm, platform contract, server autogen defaults, canary result, fault hold
   5. metabolism    /api/cluster/status + highpower state, the host load, io and memory pressure, LIFE's own per-node
                    load ledger -> governor (work/rest/hold), per-node rest, the nodes available for new work
   6. canaries      hourly, and at every tick while a round has never passed or the last one failed
   7. runs          poll LIFE autogen runs (re-send an uncertain start) and benchmark jobs; collect the ended ones
   8. reconcile     open divisions past the wall backstop abort; organism and registry migration ledgers compared
   9. upkeep        storage (its hold stops intake), inbox (operator command files), daily backup + retention, reports
  10. gate          STOP -> stop_everything + reconciliation, exit 3. Not admitted (disarmed, FROZEN, a changed
                    kit/platform/decisions hash), no release, or any hold -> observe only: hold notices, status, exit 0
                    or 5
   -- below only when admitted, with no hold and governor work; meta working_tick_no + 1 --
  11. agenda        the operator's recurring commands (current period only)
  12. findings      one due watched test, sandboxed, in a codebase clone
  13. dispatch      unassigned queued items -> the best-matching active cell of their organ
  14. The host work  source fetches, operator-finding confirmation, gates, the migration apply, agent run starts
  15. lifecycle     counters, quarantine, apoptosis, divisions (count, abort, workspaces, commit), workspaces, moves,
                    the store adapter, settled questions, derived questions, a division start
  16. dispatch      again
  17. node slots    the installed-model inventory (daily); light-model actions on every available LIFE worker node in
                    parallel threads, each node refilled after its action ends (at most SLOT_ACTIONS_MAX per tick)
      On every ODD working tick steps 12 and 14 run AFTER step 17 (12 13 15 16 17 then 12 14), so a long slot action
      (a 2100 s research run must start by tick second 510) is never starved by the host stages every tick.
  18. status        STATE/operator/status.json (also written on every other exit after step 2), with its disposition

Exit codes: 0 tick done (also observe-only, held, or another tick running), 1 a tick fault (a notice; three in a row
-> fault hold), 3 STOP handled, 4 ended by SIGTERM (systemd stop or TimeoutStartSec; not a fault), 5 integrity or
contract hold or a wrong schema, 6 not seeded. The unit lists 1 3 4 5 6 as SuccessExitStatus (faults surface as
notices, never as a failed unit); Restart=no. Nothing here restarts the
dashboard, commits to host-checkout, pushes, or writes outside STATE and the LIFE workspaces under
/home/operator/symblicos/projects/life-*.
"""
import sys
sys.dont_write_bytecode = True                  # no .pyc is ever written under bin/ (kit_sha256 hashes __pycache__)
import fcntl  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import shlex  # noqa: E402
import shutil  # noqa: E402
import signal  # noqa: E402
import sqlite3  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import unicodedata  # noqa: E402
from fractions import Fraction  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import life_common as L  # noqa: E402

EXIT_OK, EXIT_FAULT, EXIT_STOP, EXIT_TERM, EXIT_HOLD, EXIT_UNSEEDED = 0, 1, 3, 4, 5, 6
# The infrastructure vocabulary. A structured error kind decides first: a kind in INFRA_KINDS is infra, any other
# non-empty kind is a semantic failure whatever its message says. Only an error with NO kind (research error strings
# written by local_research, not by a model) is matched against INFRA_RX. Every infra outcome counts in
# items.infra_runs, so a misclassified failure still ends at INFRA_RUNS_MAX.
INFRA_KINDS = ('unavailable', 'capacity', 'timeout')
INFRA_RX = re.compile(r'no capacity|node offline|offline|unavailable|cooldown|paused|stalled|not installed|unreachable|'
                      r'timed? ?out|did not answer in time|is busy|searxng|connection', re.I)
# A watched-test run that failed for its environment, not its code, is never a finding: life_common.env_error.
NON_SEMANTIC = ('INFRASTRUCTURE', 'REFUSAL', 'CANCELLED', 'CONFLICT', 'FETCH_FAILURE', 'TIMEOUT')
RESULT_RX = re.compile(r'LIFE_RESULT ([0-9]{1,12}(?:\.[0-9]{1,9})?) ([A-Za-z/%]{1,12})')
RUN_RX = re.compile(r'^LIFE_RUN ([0-9]+)\n(.*?)^LIFE_RC \1 ([0-9]{1,3})\n(LIFE_TRUNC \1\n)?LIFE_END \1$', re.M | re.S)
COOLDOWN_RX = re.compile(r'cooldown|quota|usage limit|rate limit', re.I)   # an agy start refused for its model's quota
SLUG_RX = re.compile(r'[a-z0-9]+')
TAINT_ORDER = ('owner', 'code', 'model', 'web')          # derived items take the most external parent taint
NOT_STARTED = 'not started: STOP or admission refused'   # a workspace step that never ran (nothing is counted)
REFUSED_4XX_RX = re.compile(r'HTTP 4(?!09)[0-9]{2}')       # bin/symblic-task printed a refusal (409 = id conflict)


def derive_taint(*taints):
    return max((t for t in taints if t in TAINT_ORDER), key=TAINT_ORDER.index, default='code')


def finite(value, lo=None, hi=None):
    """value as a float when it is a finite real number within [lo, hi], else None (bool is not a number)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        return None
    return float(value)


class Tick:
    def __init__(self, conn, procs):
        self.conn = conn
        self.procs = procs
        self.t0 = time.monotonic()
        self.now = L.now()
        self.day = L.utc_day(self.now)
        self.holds = []
        self.available = []          # (node, memAvailMiB) that may take a new LIFE action this tick
        self.sampled_at = 0.0        # monotonic time of the last full governor sample
        self.agy_ready = None        # node -> bool, read once per tick from the task-engine catalogue
        self.release = self.rdir = self.manifest = self.organs = self.ladders = None
        self.stage_deadline = None   # monotonic deadline of the host stage now running (its processes share it)
        self._benchmarks = None      # control/benchmarks.json, validated once per tick
        self.slot_started = False    # the slot phase planned at least one action this tick
        self.database_hold = False   # set by migration_reconcile: the two migration ledgers disagree
        self.codebase_unproven = ''  # set by integrity: why the codebase organ's gate is not proven (gate_selftest)
        self.gov_cont = 0            # the governor's continuous loaded seconds after this tick's sample
        self.daily_capped = set()    # nodes past NODE_BUSY_PER_DAY today
        self.disposition = 'started'
        self.tick_no = int(self.meta('tick_no', '0'))
        self.working_tick_no = int(self.meta('working_tick_no', '0'))

    # ------------------------------------------------------------------ small helpers
    def meta(self, key, default=''):
        row = self.conn.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
        return row['value'] if row else default

    def set_meta(self, key, value):
        if key not in L.META_KEYS:
            raise ValueError(f'unknown meta key {key!r}')
        self.conn.execute('INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                          (key, str(value)))

    def elapsed(self):
        return time.monotonic() - self.t0

    def time_left(self):
        """Seconds until TICK_DEADLINE (after it, no new the host stage, agent start, division step or slot action)."""
        return L.TICK_DEADLINE - self.elapsed()

    def can_start(self, budget):
        """A stage or process with this budget may start: before TICK_DEADLINE, and able to end (budget + KILL_GRACE +
        START_MARGIN) before TICK_HARD; never while STOP exists."""
        return (not self.stopping() and self.time_left() > 0
                and self.elapsed() + budget + L.KILL_GRACE + L.START_MARGIN <= L.TICK_HARD)

    def may_admit(self):
        """Every admission re-reads the switches and hashes: STOP absent, ARMED for this boot, kit, platform and
        decisions unchanged since arm, not FROZEN."""
        return L.control_state()['admit']

    def stopping(self):
        return L.stop_present()

    def begin_stage(self, budget):
        self.stage_deadline = time.monotonic() + budget

    def end_stage(self):
        self.stage_deadline = None

    def t(self, timeout):
        """A process timeout clipped to what is left of the current stage's shared budget (0 = nothing left)."""
        if self.stage_deadline is None:
            return timeout
        return max(0, min(timeout, int(self.stage_deadline - time.monotonic())))

    def proc(self, argv, timeout, admit=False, heavy=False, **kw):
        """One process through the tick's runner, its timeout clipped to the stage; admit=True checks launch_allowed
        immediately before the process is created (new work: fetches, gates, watched tests, clones, slot actions);
        heavy=True also requires the host to be fit for heavy work (L.heavy_allowed)."""
        check = L.heavy_allowed if heavy else L.launch_allowed if admit else None
        return self.procs.run(argv, self.t(timeout), admit=check, **kw)

    def event(self, cell_id, event, detail=''):
        self.conn.execute('INSERT INTO cell_events (cell_id, at, event, detail) VALUES (?, ?, ?, ?)',
                          (cell_id, L.now(), event, L.one_line(detail, 400)))

    def item_update(self, item_id, **fields):
        """Update one item. A payload is checked against the closed schema of the stage it will be at (PAYLOAD_KEYS,
        PAYLOAD_MAX) before the write. A stage change resets the per-stage counters (faults, infra_runs, rung_extra,
        timeouts) unless the caller sets them."""
        row = self.item(item_id)
        stage = fields.get('stage', row['stage'])
        if 'payload' in fields or stage != row['stage']:
            payload = json.loads(fields['payload']) if 'payload' in fields else json.loads(row['payload'])
            problems = L.payload_problems(row['kind'], stage, payload)
            if problems:
                raise ValueError('; '.join(problems))
        if stage != row['stage']:
            for key in ('faults', 'infra_runs', 'rung_extra', 'timeouts'):
                fields.setdefault(key, 0)
        fields['updated_at'] = L.now()
        cols = ', '.join(f'{k}=?' for k in fields)
        self.conn.execute(f'UPDATE items SET {cols} WHERE item_id=?', (*fields.values(), item_id))

    def queue_full(self, organ):
        return self.conn.execute("SELECT COUNT(*) FROM items WHERE organ=? AND state='queued'",
                                 (organ,)).fetchone()[0] >= L.QUEUE_CAP_PER_ORGAN

    def new_item(self, organ, kind, identity, payload, taint, origin='', priority=1, stage=None, reoccur=None):
        """Create a queued item unless one with the same identity exists. Returns (item_id, created). When the existing
        item has ENDED and `reoccur` is given (the operator command or period that asks again), a new occurrence is
        created with identity + (reoccur,): deduplication stops duplicate CONCURRENT work, never later work. At 200 or
        more queued items of the organ, a new non-owner item is recorded as abstained with outcome OVERFLOW: (created
        False); an OVERFLOW row is not an ending: when the same identity is asked for again and the queue has room,
        that row is queued again with this payload (created True)."""
        stage = stage or L.STAGES[organ][0]
        problems = L.payload_problems(kind, stage, payload)
        if problems:
            raise ValueError('; '.join(problems))
        iid = L.item_id(organ, kind, *identity)
        row = self.item(iid)
        if row is not None and row['state'] == 'abstained' and row['outcome'].startswith('OVERFLOW:'):
            if taint == 'owner' or not self.queue_full(organ):
                self.conn.execute("UPDATE items SET state='queued', stage=?, payload=?, outcome='', updated_at=? WHERE item_id=?",
                                  (stage, json.dumps(payload, sort_keys=True), L.now(), iid))
                return iid, True
            return iid, False
        if row is not None and reoccur is not None and row['state'] not in ('queued', 'running'):
            iid = L.item_id(organ, kind, *identity, reoccur)
            row = self.item(iid)
        if row is not None:
            return iid, False
        state, outcome = 'queued', ''
        if taint != 'owner' and self.queue_full(organ):
            state, outcome = 'abstained', 'OVERFLOW: the organ queue is full'
            L.notice(self.conn, 'overflow', f'{organ} {self.day}', f'the {organ} queue holds {L.QUEUE_CAP_PER_ORGAN} items; '
                     'new web/code items are recorded as abstained until it drains')
        self.conn.execute(
            'INSERT INTO items (item_id, organ, kind, cell_id, stage, state, priority, taint, origin, payload, outcome,'
            ' created_at, updated_at) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (iid, organ, kind, stage, state, priority, taint, origin, json.dumps(payload, sort_keys=True), outcome,
             L.now(), L.now()))
        return iid, state == 'queued'

    def git(self, ws, *args, timeout=L.GIT_TIMEOUT):
        """A trusted git command in a LIFE workspace: first git_admin_problems (a real .git, no commondir or
        alternates, an allowlisted configuration: else git does NOT run, the result is rc 128 and notice workspace);
        then git with GIT_SAFE (hooks, fsmonitor, external diff, pagers, proxies and credential helpers off) and
        child_env (system/global configuration, replacement objects and system attributes off), the timeout clipped to
        the stage."""
        problems = L.git_admin_problems(ws)
        if problems:
            L.notice(self.conn, 'workspace', ws, 'trusted git refused to run there: ' + '; '.join(problems)[:400]
                     + ' (the workspace sweep deletes and re-creates it)')
            return 128, '', 'git admin check: ' + '; '.join(problems)[:300]
        return self.proc(['git', *L.GIT_SAFE, '-C', ws, *args], timeout, env=L.child_env())

    def cell(self, cid):
        return self.conn.execute('SELECT * FROM cells WHERE cell_id=?', (cid,)).fetchone()

    def item(self, iid):
        return self.conn.execute('SELECT * FROM items WHERE item_id=?', (iid,)).fetchone()

    def load_release(self):
        self.release, self.rdir, self.manifest = L.active_release(self.conn)
        self.organs = L.load_organs(self.rdir)
        self.ladders = self.organs['ladders']

    def workspace_busy(self, cell_id, except_item=None):
        """The ONE workspace exclusion rule: a cell's workspace is busy while it has a run in submitting, live or
        submit_unknown, or an item queued or running at a WORKSPACE_STAGES stage (gate, apply; except_item: the item
        about to use it). No watched test, confirmation, agent start, division, apoptosis, move (operator moves included),
        clone removal or self-test touches a busy workspace."""
        q = ','.join('?' * len(L.WORKSPACE_STAGES))
        return bool(self.conn.execute(
            "SELECT 1 FROM runs WHERE cell_id=? AND state IN ('submitting','live','submit_unknown')", (cell_id,)).fetchone()
            or self.conn.execute(f"SELECT 1 FROM items WHERE cell_id=? AND state IN ('queued','running') AND stage IN "
                                 f"({q}) AND item_id IS NOT ?", (cell_id, *L.WORKSPACE_STAGES, except_item)).fetchone())

    # ------------------------------------------------------------------ 3. recovery of a killed tick
    def recover(self):
        """Every call intent a killed or crashed tick left (call_intents: program runs AND division steps) holds its
        node ORPHAN_HOLD_SECONDS, because a SIGKILLed bin/symblic run can leave its fleet-runner run going until its own
        RuntimeMaxSec; model-stage items left `running` return to their queue (their cell's node is held too). A
        workspace_guard row means a sandboxed run's end was never checked: that workspace is deleted (the sweep
        re-creates it) before any trusted git runs there. A run copied to a terminal state but not collected (a crash
        between the two) is collected now."""
        with L.Tx(self.conn):
            for r in self.conn.execute('SELECT node, call_id FROM call_intents').fetchall():
                L.hold_node(self.conn, r['node'], 'orphan', r['call_id'], self.now + L.ORPHAN_HOLD_SECONDS,
                            'a killed tick may have left this call running')
            self.conn.execute('DELETE FROM call_intents')
            for r in self.conn.execute("SELECT i.item_id, c.node FROM items i JOIN cells c ON c.cell_id=i.cell_id WHERE"
                                       " i.state='running' AND i.stage NOT IN ('patch','draft','bench')").fetchall():
                L.hold_node(self.conn, r['node'], 'orphan', r['item_id'], self.now + L.ORPHAN_HOLD_SECONDS,
                            'a killed tick may have left a model run')
            self.conn.execute("UPDATE items SET state='queued', updated_at=? WHERE state='running' AND stage NOT IN "
                              "('patch','draft','bench')", (self.now,))
        for g in self.conn.execute('SELECT * FROM workspace_guard').fetchall():
            cell = self.conn.execute('SELECT * FROM cells WHERE workspace=?', (g['workspace'],)).fetchone()
            if cell is not None:
                self.git_meta_broken(cell, 'a sandboxed run that a killed tick never checked')
            with L.Tx(self.conn):
                self.conn.execute('DELETE FROM workspace_guard WHERE workspace=?', (g['workspace'],))
        for run in self.conn.execute("SELECT * FROM runs WHERE state IN ('completed','failed','stuck','cancelled','unknown')"
                                     ).fetchall():
            row = self.api_run(run['run_id']) or {'status': run['state'], 'nodes': []}
            self.guard(run['item_id'], lambda run=run, row=row: self.collect(run, row, run['state']))

    # ------------------------------------------------------------------ 4. integrity
    def integrity(self):
        for problem in L.state_problems():
            L.notice(self.conn, 'integrity', 'state', problem)
            self.holds.append('integrity')
        try:
            self.load_release()
        except Exception as exc:  # noqa: BLE001 - any failure to load the release is an integrity hold
            L.notice(self.conn, 'integrity', 'release', f'the active release cannot be loaded: {type(exc).__name__}: {exc}')
            self.holds.append('integrity')
            self.release = None
        if self.release is not None:
            problems = L.release_problems(self.rdir, self.manifest)
            if problems:
                L.notice(self.conn, 'integrity', f'release {self.release}', '; '.join(problems)[:600])
                self.holds.append('integrity')
        ctl = L.control_state()
        if ctl['armed']:
            for key, subject, what in (('kit_ok', 'kit', 'the kit code (bin, checks, db, units, VALIDATE.sh)'),
                                       ('platform_ok', 'platform', 'a pinned platform file (' + ', '.join(L.PLATFORM_PINS) + ')'),
                                       ('decisions_ok', 'decisions', 'DECISIONS.md')):
                if not ctl[key]:
                    L.notice(self.conn, 'integrity', subject, f'{what} changed since arm: read the change, run VALIDATE.sh '
                             '(STATIC PASS), then life-ctl.py arm again')
                    self.holds.append('integrity')
        contract = L.contract_problems()
        if ctl['armed']:
            contract += self.server_defaults_problems()
        if contract:
            L.notice(self.conn, 'contract', 'platform', '; '.join(contract)[:440] + '. Recovery: LIFE.md section 17.')
            self.holds.append('contract')
        if self.meta('canary_failed'):
            self.holds.append('canary')
        if self.meta('fault_hold'):
            self.holds.append('fault')
        proof = self.meta('gate_selftest').split()
        if ctl['armed'] and (len(proof) < 3 or proof[0] != L.kit_sha256() or proof[1] != L.platform_sha256()):
            self.codebase_unproven = ('no passing life-ctl.py gate-selftest for this kit and these platform files; '
                                      'codebase gates wait')
            L.notice(self.conn, 'gate_unproven', 'codebase', self.codebase_unproven + ' (run life-ctl.py gate-selftest '
                     'TEST_ID with a test that passes on the tracked branch)')

    def server_defaults_problems(self):
        """The RUNNING server's autogen defaults (it may have imported an older symblic_autogen) must equal LIFE's
        values for the fields bin/symblic-task has no flag for. A catalogue without a defaults object is ONE problem."""
        try:
            cat = L.http_json('/api/symblicos/autogen/catalog', timeout=L.HTTP_TIMEOUT)
        except L.Telemetry as exc:
            return [f'server autogen catalogue unreadable: {exc}']
        if not isinstance(cat.get('defaults'), dict):
            return ['the server autogen catalogue has no defaults object']
        defaults = cat['defaults']
        out = [f'server default {k} is {defaults.get(k)!r}, LIFE needs {L.AGENT_POLICY_FIXED[k]!r}'
               for k in L.DEFAULT_FIELDS if defaults.get(k) != L.AGENT_POLICY_FIXED[k]]
        if cat.get('version') != L.AGENT_POLICY_FIXED['version']:
            out.append(f'server autogen version is {cat.get("version")!r}')
        return out

    # ------------------------------------------------------------------ 5. metabolism
    def busy_seconds(self, node, t0, t1):
        """Seconds of [t0, t1] during which LIFE kept `node` busy: the union of its program, research, division and
        benchmark call intervals (calls rows; a bench job still running counts to now), its agent runs (submitted_at to
        ended_at; a run with no end, including submit_unknown, counts to now; a not_submitted run counts zero) and any
        node hold for an unknown or lost job (to now)."""
        spans = [(r['started_at'], r['ended_at']) for r in self.conn.execute(
            'SELECT started_at, ended_at FROM calls WHERE node=? AND ended_at > ? AND started_at < ?', (node, t0, t1))]
        spans += [(r['submitted_at'], r['ended_at'] or t1) for r in self.conn.execute(
            "SELECT submitted_at, ended_at FROM runs WHERE node=? AND state != 'not_submitted' AND submitted_at < ?"
            ' AND (ended_at IS NULL OR ended_at > ?)', (node, t1, t0))]
        for r in self.conn.execute("SELECT payload FROM items WHERE state='running' AND stage='bench'"):
            p = json.loads(r['payload'])
            if p.get('node') == node and isinstance(p.get('started'), int):
                spans.append((p['started'], t1))
        if self.conn.execute("SELECT 1 FROM node_holds WHERE node=? AND cause='job'", (node,)).fetchone():
            spans.append((t0, t1))
        total, end = 0, t0
        for a, b in sorted((max(a, t0), min(b, t1)) for a, b in spans):
            if b <= a:
                continue
            if a < end:
                a = end
            if b > a:
                total += b - a
                end = b
        return total

    def read_status(self):
        """{node: row} from /api/cluster/status, and the hold reasons. Rows are kept only for LIFE nodes; a node listed
        twice or a missing status list is a reason (and then no row is used at all). A LIFE node with no row is
        MISSING (neither online nor offline evidence)."""
        reasons, rows = [], {}
        try:
            status = L.http_json('/api/cluster/status', timeout=L.HTTP_SLOW_TIMEOUT)
            if not isinstance(status.get('status'), list):
                return {}, ['telemetry: /api/cluster/status has no status list']
            for row in status['status']:
                if isinstance(row, dict) and row.get('id') in L.NODES:
                    if row['id'] in rows:
                        reasons.append(f'telemetry: {row["id"]} listed twice')
                    rows[row['id']] = row
        except L.Telemetry as exc:
            return {}, ['telemetry: ' + str(exc)[:120]]
        return ({} if reasons else rows), reasons

    def highpower_reasons(self):
        try:
            sm = L.http_json('/api/cluster/highpower/state', timeout=L.HTTP_TIMEOUT)
        except L.Telemetry as exc:
            return ['telemetry: ' + str(exc)[:120]]
        out = []
        cool = sm.get('cool')
        if not isinstance(cool, dict) or cool.get('error') or cool.get('phase') != 'off':
            out.append('cool mode is on, restoring or unreadable')
        if sm.get('enabled') is not False:
            out.append('a high-power mode lease is active or unreadable')
        if sm.get('phase') != 'off':
            out.append(f'high-power mode phase is {str(sm.get("phase"))[:20]!r}, not off (applying, active or restoring)')
        rest = sm.get('restUntil')
        if type(rest) is not int or rest < 0:
            out.append('high-power mode restUntil is not integer Unix seconds')
        elif rest > self.now:
            out.append(f'high-power mode rests until {rest}')
        return out

    def vitals(self, row):
        """(online, load per cpu, temp, mem MiB) of one status row; anything missing, of the wrong type or out of range
        is None (never zero): online must be the boolean true; load per cpu = vitals.load[1] (the 5-minute average, a
        finite number >= 0) / vitals.cpus (an integer >= 1); temp a finite TEMP_MIN_C..TEMP_MAX_C; memavail a non-negative
        integer number of bytes, not above memtotal when that is given."""
        vit = row.get('vitals') if isinstance(row.get('vitals'), dict) else {}
        on = row.get('online') is True
        load, cpus = vit.get('load'), vit.get('cpus')
        per_cpu = None
        if isinstance(load, list) and len(load) == 3 and finite(load[1], 0) is not None and type(cpus) is int and cpus >= 1:
            per_cpu = load[1] / cpus
        temp = finite(vit.get('temp'), L.TEMP_MIN_C, L.TEMP_MAX_C)
        mem_b, total_b = vit.get('memavail'), vit.get('memtotal')
        mem = None
        if type(mem_b) is int and mem_b >= 0 and (type(total_b) is not int or mem_b <= total_b):
            mem = mem_b // 1048576
        return on, per_cpu, temp, mem

    def metabolism(self):
        """Governor (LIFE.md section 10). Telemetry is never replaced by zero: a missing value is unavailable. A sample
        is OBSERVED only when the status list is readable, every LIFE node has exactly one row, and every online LIFE
        node has a load reading; an unobserved interval counts as loaded (never as quiet) and never ends a rest. Quiet
        seconds accrue only for an interval whose previous AND current samples were observed. Samples are written for
        the nodes that have a row (a missing node is neither online nor offline evidence)."""
        rows, reasons = self.read_status()
        observed = bool(rows) and not reasons and set(rows) == set(L.NODES)
        reasons += self.highpower_reasons() + L.host_problems()
        prev = self.conn.execute('SELECT * FROM governor WHERE id=1').fetchone()
        prev_hot = set(json.loads(prev['hot'])) if prev else set()
        node_rest = json.loads(prev['node_rest']) if prev else {}
        raw_dt = self.now - prev['at'] if prev else 0
        if raw_dt < 0 or raw_dt > L.TICK_SECONDS + L.TICK_HARD + L.UNIT_TIMEOUT:
            L.notice(self.conn, 'clock', 'governor', f'the wall clock moved {raw_dt} s between two samples: the interval '
                     'counts as loaded and unobserved')
            observed = False
        dt = max(0, min(raw_dt, L.TICK_SECONDS + L.TICK_HARD)) if prev else 0
        hot, loaded, online, mems = set(), [], [], {}
        for node in L.NODES:
            on, load, temp, mem = self.vitals(rows.get(node) or {})
            if rows and node in rows:
                self.conn.execute('INSERT OR REPLACE INTO samples (at, node, online, cpu, temp, mem_avail_mib) VALUES (?, ?, ?, ?, ?, ?)',
                                  (self.now, node, int(on), None if load is None else round(load * 100, 1), temp, mem))
            if on and load is None:
                observed = False
            own = self.busy_seconds(node, prev['at'], self.now) if prev and dt > 0 else 0
            if self.busy_seconds(node, L.now() - (self.now % L.DAY), L.now()) >= L.NODE_BUSY_PER_DAY:
                self.daily_capped.add(node)
            # per-node duty cycle: busy >= NODE_BUSY_MAX of the last NODE_WINDOW rests the node until NODE_REST idle seconds
            if node in node_rest:
                if self.busy_seconds(node, self.now - L.NODE_REST, self.now) == 0 and self.now - node_rest[node] >= L.NODE_REST:
                    del node_rest[node]
            elif self.busy_seconds(node, self.now - L.NODE_WINDOW, self.now) >= L.NODE_BUSY_MAX:
                node_rest[node] = self.now
                L.log(f'{node}: rest: LIFE kept it busy for {L.NODE_BUSY_MAX}+ s of the last {L.NODE_WINDOW} s')
            if not on:
                continue
            online.append(node)
            mems[node] = mem
            if (load is not None and load >= L.FLEET_LOAD5_PER_CPU) or (dt > 0 and own >= L.LOADED_OWN_FRACTION * dt):
                loaded.append(node)
            if temp is None or temp >= L.HOT_C or (node in prev_hot and temp >= L.COOL_C):
                hot.add(node)                     # unknown temperature is treated as hot (fail closed)
            recent = [r['temp'] for r in self.conn.execute('SELECT temp FROM samples WHERE node=? AND online=1 ORDER BY at DESC'
                                                            ' LIMIT ?', (node, L.TEMP_MISSING_SAMPLES))]
            if len(recent) == L.TEMP_MISSING_SAMPLES and all(t is None for t in recent):
                L.notice(self.conn, 'telemetry', node, f'no temperature in /api/cluster/status for {L.TEMP_MISSING_SAMPLES} '
                         'samples; LIFE treats the node as hot (it takes no LIFE work)')
        cont = prev['continuous_seconds'] if prev else 0
        quiet = prev['quiet_seconds'] if prev else 0
        need = max(1, math.ceil(L.FLEET_LOADED_FRACTION * len(online)))
        prev_observed = bool(prev and prev['observed'])
        if not observed or len(loaded) >= need:
            cont, quiet = cont + dt, 0            # unobserved counts as loaded: it never ends a rest
        elif prev_observed:
            quiet += dt
            if quiet >= L.REST_SECONDS:
                cont = 0
        if reasons:
            state = 'hold'                        # a hold never resets the window: cont and quiet keep counting
        elif cont >= L.WORK_WINDOW or (prev and prev['state'] == 'rest' and quiet < L.REST_SECONDS):
            state = 'rest'
        else:
            state = 'work'
        self.conn.execute('INSERT OR REPLACE INTO governor (id, at, state, continuous_seconds, quiet_seconds, hot, reasons,'
                          ' node_rest, observed) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)',
                          (self.now, state, cont, quiet, json.dumps(sorted(hot)), json.dumps(reasons),
                           json.dumps(node_rest, sort_keys=True), int(observed)))
        if state != 'work':
            self.holds.append(f'governor {state}: ' + ('; '.join(reasons) or f'{cont} s of fleet load, resting'))
        self.gov_cont = cont
        self.sampled_at = time.monotonic()
        self.set_available(online, mems, hot, node_rest)

    def set_available(self, online, mems, hot, node_rest):
        bench = {json.loads(r['payload']).get('node') for r in
                 self.conn.execute("SELECT payload FROM items WHERE state='running' AND stage='bench'")}
        self.available = [(n, mems[n]) for n in online if n not in hot and not L.node_held(self.conn, n)
                          and n not in bench and n not in node_rest and n not in self.daily_capped
                          and mems.get(n) is not None]

    def refresh_available(self, force=False):
        """Before EVERY slot action and right after any agent start (force), when the last sample is older than
        TELEMETRY_REFRESH: EVERY governor input is read again (status, high-power mode, the host load, io and memory
        pressure). Any hold reason empties the available list, is added to this tick's holds and rewrites the governor
        row's reasons (status.json then says why the slot phase refused); a node now offline, hot or without a memory
        reading leaves it."""
        if not force and time.monotonic() - self.sampled_at < L.TELEMETRY_REFRESH:
            return
        rows, reasons = self.read_status()
        reasons += self.highpower_reasons() + L.host_problems()
        self.sampled_at = time.monotonic()
        if reasons or not rows:
            self.available = []
            why = reasons or ['telemetry: no status rows']
            self.holds += [f'governor hold: {r}' for r in why if f'governor hold: {r}' not in self.holds]
            self.conn.execute("UPDATE governor SET state='hold', reasons=? WHERE id=1", (json.dumps(why),))
            L.log('slot phase: governor inputs refreshed: ' + '; '.join(why))
            return
        keep = []
        for node, _mem in self.available:
            on, _cpu, temp, mem = self.vitals(rows.get(node) or {})
            if on and temp is not None and temp < L.HOT_C and mem is not None and not L.node_held(self.conn, node):
                keep.append((node, mem))
        self.available = keep

    def node_ok(self, node, model, budget=0, program=None):
        """The node is available, is not held for `program` (a timeout hold), has the memory for `model` (MEM_RESERVE_MIB
        + the model + KV_ALLOWANCE_MIB, + AGENT_RUN_MIB while a LIFE agent run is live there), its duty cycle can take
        `budget` more seconds, and the fleet's work window has room for it (fleet_allows)."""
        for n, mem in self.available:
            if n == node:
                need = L.MEM_RESERVE_MIB + L.MODEL_MIB.get(model, L.MODEL_MIB_UNKNOWN) + L.KV_ALLOWANCE_MIB
                if self.node_has_agent_run(node):
                    need += L.AGENT_RUN_MIB
                return (mem >= need and not (program and L.node_held(self.conn, node, program))
                        and self.duty_allows(node, budget) and self.fleet_allows(budget))
        return False

    def duty_allows(self, node, budget):
        """An action is admitted only when the node's LIFE busy time in [now - NODE_WINDOW, now] plus the action's
        worst-case seconds stays at or below NODE_BUSY_MAX, and the node has not passed NODE_BUSY_PER_DAY today (both
        ends of the window read the clock once: t1 = now)."""
        t1 = L.now()
        return node not in self.daily_capped and self.busy_seconds(node, t1 - L.NODE_WINDOW, t1) + budget <= L.NODE_BUSY_MAX

    def fleet_allows(self, budget):
        """The fleet's work window has room: the governor's continuous loaded seconds + the action's worst case <=
        WORK_WINDOW. Actions already running finish; a new one never pushes the fleet past its window."""
        return self.gov_cont + budget <= L.WORK_WINDOW

    # ------------------------------------------------------------------ 7. runs and benchmark jobs
    def api_run(self, run_id):
        """The server's run row; {} when the server answers 404 (no such run); None when there is no usable answer
        (no answer, another HTTP error, or a row whose id is not run_id)."""
        try:
            run = L.http_json('/api/symblicos/autogen/get?id=' + run_id, timeout=L.HTTP_SLOW_TIMEOUT).get('run')
        except L.Telemetry as exc:
            return {} if exc.status == 404 else None
        return run if isinstance(run, dict) and run.get('id') == run_id else None

    def run_identity_problems(self, run, row):
        """A run is LIFE's only when the server row matches what LIFE submitted: policy sha256, the exact statements,
        engine agy, the model and effort LIFE passed, the node recorded in the run row at submit (immutable: never the
        cell's current node) and the cell's workspace as cwd."""
        out = []
        policy = row.get('policy') if isinstance(row.get('policy'), dict) else {}
        if policy.get('sha256') != run['policy_sha256']:
            out.append('policy sha256 differs')
        lines = row.get('lines')
        if not isinstance(lines, list) or L.sha('\n'.join(str(x) for x in lines) + '\n') != run['statements_sha256']:
            out.append('statements differ')
        base = row.get('base') if isinstance(row.get('base'), dict) else {}
        if base.get('engine') != L.ENGINE or base.get('node') != run['node'] or base.get('cwd') != run['workspace']:
            out.append('engine, node or workspace differs')
        if (base.get('model') or '') != run['model'] or (base.get('effort') or '') != run['effort']:
            out.append('model or effort differs')
        return out

    def poll_runs(self, reconcile_only=False):
        """Poll every run in submitting, live or submit_unknown. reconcile_only (a STOP tick): record what the server
        proves (terminal states are collected), never re-send, never request anything new."""
        for run in self.conn.execute("SELECT * FROM runs WHERE state IN ('submitting','live','submit_unknown')").fetchall():
            row = self.api_run(run['run_id'])
            if row is None:                                # no answer: try next tick, never a new request id
                if run['state'] in ('submitting', 'submit_unknown') and self.now - run['submitted_at'] > L.RUN_UNKNOWN_NOTICE:
                    L.notice(self.conn, 'run_unknown', run['run_id'], 'LIFE cannot confirm whether this run exists; its item '
                             'stays running and its workspace busy until the dashboard answers (check: bin/symblic-task '
                             f'autogen get {run["run_id"]}; if it never existed: life-ctl.py abandon-run {run["run_id"]} '
                             '--confirm ABANDON)')
                continue
            if row == {}:
                if run['state'] == 'live':                 # the server lost a run it had: a terminal unknown
                    self.guard(run['item_id'], lambda run=run: self.collect(run, {'status': 'unknown', 'nodes': []}, 'unknown'))
                elif not reconcile_only:                   # never stored, or not yet: re-send the identical start
                    self.guard(run['item_id'], lambda run=run: self.resend(run))
                continue
            status = row.get('status')
            if run['state'] != 'live':
                problems = self.run_identity_problems(run, row)
                if problems:
                    self.procs.run([L.TASK, 'autogen', 'cancel', run['run_id']], L.CANCEL_TIMEOUT, env=L.child_env(), tracked=False)
                    with L.Tx(self.conn):
                        self.conn.execute("UPDATE runs SET state='live', detail=?, cancel_cause=CASE WHEN cancel_cause='' THEN "
                                          "'mismatch' ELSE cancel_cause END WHERE request_id=?",
                                          (L.one_line('mismatch, cancel requested: ' + '; '.join(problems), 400), run['request_id']))
                        L.notice(self.conn, 'policy_mismatch', run['run_id'], 'the server run differs from what LIFE submitted ('
                                 + '; '.join(problems) + '); cancel requested, its item handed to the operator')
                        it, cell = self.item(run['item_id']), self.cell(run['cell_id'])
                        self.finish_item(it, cell, 'owner', 'run mismatch: ' + '; '.join(problems), tx=False)
                    continue
                self.conn.execute("UPDATE runs SET state='live' WHERE request_id=?", (run['request_id'],))
            if status in ('queued', 'active'):
                if (not reconcile_only and self.now - run['submitted_at'] > L.AGENT_RUN_KILL_SECONDS
                        and run['cancel_cause'] != 'age'):
                    rc, _o, _e = self.procs.run([L.TASK, 'autogen', 'cancel', run['run_id']], L.CANCEL_TIMEOUT,
                                                env=L.child_env(), tracked=False)
                    self.conn.execute("UPDATE runs SET cancel_cause=CASE WHEN cancel_cause='' THEN 'age' ELSE cancel_cause END,"
                                      ' detail=? WHERE request_id=?',
                                      ('life kill: cancel requested' if rc == 0 else 'life kill: cancel not confirmed',
                                       run['request_id']))
                continue
            if status in ('completed', 'failed', 'stuck', 'cancelled', 'unknown'):
                self.guard(run['item_id'], lambda run=run, row=row, status=status: self.collect(run, row, status))
                collected = self.conn.execute("SELECT 1 FROM runs WHERE request_id=? AND state='collected'",
                                              (run['request_id'],)).fetchone()
                if collected and not reconcile_only:
                    self.discard_checkouts(run, row)

    def discard_checkouts(self, run, row):
        """After a run is collected, every hub agent checkout its attempts used (nodes[].attempts[].agent_id and
        checkout_agent) is discarded through the hub's own route (POST /api/agents/work/discard: the worktree under
        <workspace>.agents/ on the host, its branch, and the checkout under ~/agents-work on the node). A discard the
        hub refuses is listed in STATE/operator/node-cleanup.txt with notice node_cleanup; LIFE never removes a hub
        checkout by any other path."""
        ids = []
        for n in row.get('nodes') or []:
            for a in (n.get('attempts') or []) if isinstance(n, dict) else []:
                for key in ('agent_id', 'checkout_agent'):
                    v = a.get(key) if isinstance(a, dict) else None
                    if isinstance(v, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,80}', v) and v not in ids:
                        ids.append(v)
        failed = []
        for agent_id in ids:
            try:
                L.http_json('/api/agents/work/discard', {'id': agent_id}, timeout=L.HTTP_SLOW_TIMEOUT)
            except L.Telemetry as exc:
                failed.append(f'{agent_id}: {L.one_line(str(exc), 120)}')
        if failed:
            try:
                with open(L.AGENT_CLEANUP, 'a', encoding='utf-8', opener=lambda p, f: os.open(p, f, 0o600)) as handle:
                    for line in failed:
                        handle.write(f'{L.utc_day(self.now)} run {run["run_id"]} node {run["node"]} agent {line}\n')
            except OSError:
                pass
            L.notice(self.conn, 'node_cleanup', run['node'], f'{len(failed)} agent checkout(s) of run {run["run_id"]} could '
                     f'not be discarded; listed in {L.AGENT_CLEANUP}')

    def resend(self, run):
        """A run the server does not know (404) after an uncertain start is re-sent with the IDENTICAL request, rebuilt
        ONLY from its manifest (STATE/runs/<request_id>/manifest.json: ids, workspace, node, engine, model, effort,
        base commit, release and the sha256 of statements.txt and policy.json; a missing or mismatched file refuses the
        re-send): autogen answers the existing run for a known request id and creates it once otherwise, so this can
        never make a twin. A re-send happens only on a fully admitted working tick (never observe-only, frozen, held or
        STOP). After RUN_RESENDS_MAX re-sends the run STAYS submit_unknown (its workspace stays busy, nothing new
        starts for its cell) and the operator decides (notice run_unknown; life-ctl.py abandon-run); an HTTP 4xx refusal is
        a refused start (start_refusals)."""
        item = self.item(run['item_id'])
        if run['resends'] >= L.RUN_RESENDS_MAX:
            if run['detail'] != 'resends exhausted: the operator decides':
                with L.Tx(self.conn):
                    self.conn.execute("UPDATE runs SET state='submit_unknown', detail='resends exhausted: the operator decides' "
                                      'WHERE request_id=?', (run['request_id'],))
                    L.notice(self.conn, 'run_unknown', run['run_id'], f'the start was re-sent {L.RUN_RESENDS_MAX} times and the '
                             'server still does not know the run; it may still appear. Its workspace stays busy. Check '
                             f'bin/symblic-task autogen list, then life-ctl.py abandon-run {run["run_id"]} --confirm ABANDON')
            return
        if not self.may_admit() or self.holds or not self.can_start(L.START_TIMEOUT):
            return
        snap = os.path.join(L.RUNS_DIR, run['request_id'])
        try:
            manifest = L.strict_json(open(os.path.join(snap, 'manifest.json'), encoding='utf-8').read())
            policy = L.strict_json(open(os.path.join(snap, 'policy.json'), encoding='utf-8').read())
            ok = (manifest.get('request_id') == run['request_id'] and manifest.get('run_id') == run['run_id']
                  and manifest.get('workspace') == run['workspace'] and manifest.get('node') == run['node']
                  and manifest.get('model') == run['model'] and manifest.get('effort') == run['effort']
                  and manifest.get('statements_sha256') == L.file_sha(os.path.join(snap, 'statements.txt'))
                  and manifest.get('policy_sha256') == L.file_sha(os.path.join(snap, 'policy.json')))
        except (OSError, ValueError, AttributeError):
            ok = False
        if not ok:
            L.notice(self.conn, 'run_unknown', run['run_id'], 'the run manifest is missing or does not match the run row: '
                     'it is never re-sent; the operator decides (life-ctl.py abandon-run)')
            return
        argv = [L.TASK, 'start', '--lines', os.path.join(snap, 'statements.txt'), '--root', run['workspace'], '--cwd',
                run['workspace'], '--node', run['node'], '--engine', L.ENGINE, '--model', run['model'], '--effort',
                run['effort'], '--id', run['request_id'], '--json'] + L.policy_flags(policy)
        rc, _out, err = self.procs.run(argv, L.START_TIMEOUT, env=L.child_env(), tracked=False)
        with L.Tx(self.conn):
            if rc != 0 and REFUSED_4XX_RX.search(err) and self.api_run(run['run_id']) == {}:
                self.conn.execute("UPDATE runs SET state='not_submitted', ended_at=?, resends=resends+1, detail=? WHERE "
                                  'request_id=?', (L.now(), L.one_line(err[-300:], 300), run['request_id']))
                self.start_refused(item, err)
            else:
                self.conn.execute('UPDATE runs SET state=?, resends=resends+1, detail=? WHERE request_id=?',
                                  ('submitting' if rc == 0 else 'submit_unknown', L.one_line(err[-300:], 300), run['request_id']))

    def start_refused(self, item, err):
        """A start the server refused (HTTP 4xx, nothing stored): start_refusals + 1 and a new attempt number; failed at
        START_ATTEMPTS_MAX. Inside the caller's transaction."""
        n = item['start_refusals'] + 1
        if n >= L.START_ATTEMPTS_MAX:
            self.item_update(item['item_id'], start_refusals=n)
            self.finish_item(self.item(item['item_id']), self.cell(item['cell_id']), 'failed',
                             f'start refused {n} times: ' + L.one_line(err[-200:], 200), tx=False)
        else:
            self.item_update(item['item_id'], state='queued', start_refusals=n, attempts=item['attempts'] + 1,
                             outcome='start refused: ' + L.one_line(err[-200:], 200))

    def collect(self, run, row, status):
        """Record a run's terminal status and collect it in ONE transaction (a crash leaves neither or both)."""
        with L.Tx(self.conn):
            self.conn.execute('UPDATE runs SET state=?, ended_at=COALESCE(ended_at, ?) WHERE request_id=?',
                              (status, L.now(), run['request_id']))
            self.collect_run(dict(run), row, status)

    def collect_run(self, run, row, status):
        """Inside the caller's transaction. Precedence, first match wins: (1) an item that is no longer running (handed
        to the operator meanwhile: a mismatch, an abandon) only has its run collected and its workspace reset; (2)
        completed -> the next stage, whatever cancel was requested; (3) cancel_cause age (LIFE cancelled it at
        AGENT_RUN_KILL_SECONDS) -> failed; (4) cancel_cause stop -> queued again with a new attempt, not counted (it
        starts again only on a fully admitted tick, i.e. after the operator arms again); (5) infra when every attempt
        failure is non-semantic (or a cancelled/unknown run has none), otherwise failed. The cause is the structured
        runs.cancel_cause, never the detail text."""
        item, cell = self.item(run['item_id']), self.cell(run['cell_id'])
        nxt = {'codebase': 'gate', 'selfdev': 'gate', 'database': 'apply'}[run['organ']]
        cause = run.get('cancel_cause') or ''
        if item is None or item['state'] != 'running':
            self.reset_workspace(cell['workspace'] if cell else '')
        elif status == 'completed':
            self.item_update(item['item_id'], state='queued', stage=nxt, outcome=f'run {run["run_id"]} completed')
        elif cause == 'age':
            self.reset_workspace(cell['workspace'])
            self.finish_item(item, cell, 'failed', f'run exceeded {L.AGENT_RUN_KILL_SECONDS} s and was cancelled', tx=False)
        elif cause == 'stop':
            self.reset_workspace(cell['workspace'])
            self.item_update(item['item_id'], state='queued', attempts=item['attempts'] + 1, outcome=f'run {status} by STOP')
        else:
            failures = [a.get('failure') for n in row.get('nodes') or [] if isinstance(n, dict)
                        for a in n.get('attempts') or [] if isinstance(a, dict) and a.get('failure')]
            infra = bool(failures) and all(f in NON_SEMANTIC for f in failures)
            if not failures and status in ('cancelled', 'unknown'):
                infra = True                       # cancelled/lost before any attempt failed: not the cell's fault
            self.reset_workspace(cell['workspace'])
            if infra:
                self.item_update(item['item_id'], attempts=item['attempts'] + 1)
                self.count_infra(self.item(item['item_id']), cell, f'run {status}: infrastructure', tx=False)
            else:
                self.finish_item(item, cell, 'failed', f'run {status}: ' + ', '.join(str(f) for f in failures[-4:]), tx=False)
        self.conn.execute("UPDATE runs SET state='collected' WHERE request_id=?", (run['request_id'],))

    def owned_jobs(self, job_ids, labels):
        """(found, by label, complete): the jobs LIFE owns, found by id or by meta.label in the paged listing (pages of
        JOBS_PAGE until the listing's total is reached, at most JOBS_PAGES_MAX pages per tick). complete is True only
        when the whole listing was read: a capped, failed or total-less listing is never proof that a job is absent.
        by label lists EVERY job carrying a label (more than one is an ambiguity, never resolved by guessing)."""
        found, by_label, offset, complete = {}, {}, 0, False
        for _ in range(L.JOBS_PAGES_MAX):
            page = L.http_json(f'/api/cluster/jobs?kind=map&limit={L.JOBS_PAGE}&offset={offset}', timeout=L.HTTP_SLOW_TIMEOUT)
            jobs = page.get('jobs') if isinstance(page.get('jobs'), list) else []
            for j in jobs:
                if not isinstance(j, dict):
                    continue
                label = (j.get('meta') or {}).get('label')
                if j.get('id') in job_ids or label in labels:
                    found[j.get('id')] = j
                if label in labels:
                    by_label.setdefault(label, []).append(j)
            offset += L.JOBS_PAGE
            total = page.get('total') if type(page.get('total')) is int else None
            if total is None:
                break
            if not jobs or offset >= total:
                complete = True
                break
        return found, by_label, complete

    def hold_job_node(self, node, key, why):
        """An unknown or lost benchmark job keeps its node held (cause job, subject = its id or label, no expiry) until
        the jobs listing shows the job ended or the operator runs life-ctl release-hold NODE."""
        L.hold_node(self.conn, node, 'job', str(key), 0, f'job:{key} {why}')

    def poll_benches(self):
        running = self.conn.execute("SELECT * FROM items WHERE state='running' AND stage='bench'").fetchall()
        holds = self.conn.execute("SELECT * FROM node_holds WHERE cause='job'").fetchall()
        if not running and not holds:
            return
        payloads = {i['item_id']: json.loads(i['payload']) for i in running}
        hold_keys = [(h['node'], h['subject']) for h in holds]
        try:
            jobs, by_label, complete = self.owned_jobs(
                {p.get('job_id') for p in payloads.values() if p.get('job_id')} | {k for _n, k in hold_keys},
                {p.get('label') for p in payloads.values()} | {k for _n, k in hold_keys})
        except L.Telemetry:
            return
        for node, key in hold_keys:
            matches = [jobs[key]] if key in jobs else by_label.get(key, [])
            if len(matches) == 1 and matches[0].get('status') in ('done', 'failed', 'cancelled'):
                self.conn.execute("DELETE FROM node_holds WHERE node=? AND cause='job' AND subject=?", (node, key))
                L.log(f'{node}: hold released: job {key} ended ({matches[0].get("status")})')
        for item in running:
            p = payloads[item['item_id']]
            cell = self.cell(item['cell_id'])
            labelled = by_label.get(p.get('label'), [])
            if not p.get('job_id') and len(labelled) > 1:
                with L.Tx(self.conn):
                    L.notice(self.conn, 'job_ambiguous', str(p.get('label')), f'{len(labelled)} jobs carry LIFE label '
                             f'{p.get("label")}: none is assumed to be LIFE\'s; the node stays held and the item is with the '
                             f'owner (cancel the right job, then life-ctl.py release-hold {p.get("node")} and requeue)')
                    self.hold_job_node(p.get('node') or cell['node'], p.get('label'), 'ambiguous label')
                    self.finish_item(item, cell, 'owner', f'job_ambiguous: label {p.get("label")}', tx=False)
                continue
            job = jobs.get(p.get('job_id')) if p.get('job_id') else (labelled[0] if len(labelled) == 1 else None)
            if job is not None and not p.get('job_id'):
                p['job_id'] = str(job.get('id') or '')     # a submit whose answer was lost, found again by its label
                self.item_update(item['item_id'], payload=json.dumps(p, sort_keys=True))
            age = self.now - p.get('started', self.now)
            status = job.get('status') if job is not None else None
            if job is None and (age <= p.get('timeout', 0) + L.BENCH_GRACE or not complete):
                continue                                    # absence from an incomplete listing proves nothing
            if job is None or status == 'unknown' or (status in ('queued', 'running')
                                                      and age > p.get('timeout', 0) + 2 * L.BENCH_GRACE):
                kind = 'job_lost' if job is None else 'job_unknown'
                key = p.get('job_id') or p.get('label')
                self.guard(item['item_id'], lambda item=item, cell=cell, p=p, kind=kind, key=key, status=status:
                           self.bench_to_owner(item, cell, p, kind, key, status))
            elif status in ('queued', 'running'):
                if age > p.get('timeout', 0) + L.BENCH_GRACE and 'cancel requested' not in item['outcome']:
                    try:
                        L.http_json('/api/cluster/job/cancel', {'id': p.get('job_id')}, timeout=L.JOB_CANCEL_TIMEOUT)
                        self.conn.execute('UPDATE items SET outcome=? WHERE item_id=?', ('past its timeout: cancel requested',
                                                                                         item['item_id']))
                    except L.Telemetry:
                        pass
            elif status == 'cancelled':
                self.guard(item['item_id'], lambda item=item, cell=cell, p=p: self.bench_infra(item, cell, p, 'the job was cancelled'))
            elif status in ('done', 'failed'):
                self.guard(item['item_id'], lambda item=item, cell=cell, p=p, job=job: self.finish_bench(item, cell, p, job))

    def bench_to_owner(self, item, cell, p, kind, key, status):
        with L.Tx(self.conn):
            self.hold_job_node(p.get('node') or cell['node'], key, kind)
            L.notice(self.conn, kind, key, f'benchmark job {key} on {p.get("node")} is '
                     + ('not in the jobs listing' if kind == 'job_lost' else str(status)) + ' past its timeout; the node stays '
                     'held until the listing shows the job ended or you run life-ctl.py release-hold ' + str(p.get('node')))
            self.finish_item(item, cell, 'owner', f'{kind}: job {key}', tx=False)

    def bench_infra(self, item, cell, p, why):
        """A benchmark job that ended without a measurement for a reason outside the experiment (cancelled, or failed
        with no LIFE_RESULT at all): the experiment goes back to ranked, the item to its queue (infra)."""
        with L.Tx(self.conn):
            self.conn.execute("UPDATE experiments SET state='ranked' WHERE experiment_id=?", (p['experiment_id'],))
            self.item_update(item['item_id'], payload=json.dumps({'seed_text': p['seed_text'],
                                                                  'experiment_id': p['experiment_id']}, sort_keys=True))
            self.count_infra(self.item(item['item_id']), cell, 'bench: ' + why, tx=False)

    def finish_bench(self, item, cell, p, job):
        """Score one ended job. Only a job whose status is `done` is scored; a `failed` job with no LIFE_RESULT at all
        is infra, with measurements it fails the experiment (a failed run invalidates the set). Its node output must
        hold exactly BENCH_RUNS blocks `LIFE_RUN k`, the run's output (at most BENCH_OUT_BYTES), `LIFE_RC k <exit
        status>`, an optional `LIFE_TRUNC k`, `LIFE_END k`, for k = 0..BENCH_RUNS-1, each once; every run must have
        exit status 0 and no LIFE_TRUNC (the status is the wrapper's record of the command's own exit, never the
        command's stdout); blocks 0 and 1 are the discarded warm-ups (baseline, then candidate); every scored block
        holds exactly one LIFE_RESULT line in the benchmark's unit and follows BENCH_ORDER (pair k = the k-th baseline
        and the k-th candidate). Values are exact fractions; gain_k = (baseline - candidate) / baseline x 100 when lower
        is better, else (candidate - baseline) / baseline x 100; passed when every gain is above 0 and the median gain
        is at least min_gain_pct, compared exactly. The result shows the observed pairs; ABBA order reduces linear drift
        and does not prove that every drift cancelled."""
        exp = self.conn.execute('SELECT * FROM experiments WHERE experiment_id=?', (p['experiment_id'],)).fetchone()
        out = ((job.get('out') or {}).get(p['node']) or {}).get('out') or ''
        if job.get('status') == 'failed' and 'LIFE_RESULT' not in out:
            return self.bench_infra(item, cell, p, 'the job failed before any measurement')
        found = [(int(m.group(1)), m.group(2), int(m.group(3)), bool(m.group(4))) for m in RUN_RX.finditer(out)]
        values, why = {}, ''
        for k, body, _rc, _trunc in found:
            res = [RESULT_RX.fullmatch(ln.strip()) for ln in body.splitlines() if ln.strip().startswith('LIFE_RESULT')]
            if len(res) == 1 and res[0] and res[0].group(2) == p['unit']:
                values[k] = res[0].group(1)
        if job.get('status') != 'done':
            why = f'the job ended {job.get("status")}: a failed run invalidates every measurement'
        elif sorted(k for k, *_ in found) != list(range(L.BENCH_RUNS)):
            why = f'need exactly the run blocks 0..{L.BENCH_RUNS - 1} once each'
        elif any(rc != 0 or trunc for _k, _b, rc, trunc in found):
            why = 'a run exited nonzero or its output was truncated: every measurement is invalid'
        elif any(k not in values for k in range(L.BENCH_WARMUP_RUNS, L.BENCH_RUNS)):
            why = f'every scored run needs exactly one LIFE_RESULT line in {p["unit"]}'
        gains = []
        if not why:
            scored = [Fraction(values[k]) for k in range(L.BENCH_WARMUP_RUNS, L.BENCH_RUNS)]
            if any(v <= 0 for v in scored):
                why = 'a measurement is not above zero'
            else:
                base = [v for v, role in zip(scored, L.BENCH_ORDER, strict=True) if role == 'baseline']
                cand = [v for v, role in zip(scored, L.BENCH_ORDER, strict=True) if role == 'candidate']
                gains = [(b - c) / b * 100 if exp['better'] == 'lower' else (c - b) / b * 100 for b, c in zip(base, cand, strict=True)]
        with L.Tx(self.conn):
            self.conn.execute('INSERT INTO calls (call_id, cell_id, item_id, program, release, applicator, node, outcome,'
                              ' model_calls, started_at, ended_at, dir, detail) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)',
                              (L.sha16('bench', item['item_id'], p.get('job_id'), self.now), item['cell_id'], item['item_id'],
                               'bench', self.release or 0, f'job:{p.get("job_id")}@{p["node"]}', p['node'],
                               'failed' if why else 'done', p.get('started', self.now), L.now(), '', L.one_line(why, 400)))
            if why:
                self.conn.execute("UPDATE experiments SET state='failed' WHERE experiment_id=?", (p['experiment_id'],))
                self.finish_item(item, cell, 'failed', why, tx=False)
                return
            median = sorted(gains)[len(gains) // 2]
            passed = all(g > 0 for g in gains) and median >= exp['min_gain_pct']
            self.conn.execute('INSERT OR REPLACE INTO results (experiment_id, node, job_id, measurements, gains_pct, median_gain_pct,'
                              ' passed, ran_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                              (exp['experiment_id'], p['node'], p['job_id'], json.dumps([values.get(k, '') for k in range(L.BENCH_RUNS)]),
                               json.dumps([f'{g.numerator}/{g.denominator}' for g in gains]),
                               f'{median.numerator}/{median.denominator}', int(passed), L.now()))
            self.conn.execute("UPDATE experiments SET state='measured' WHERE experiment_id=?", (exp['experiment_id'],))
            shown = f'{float(median):.2f}'
            if passed:
                L.notice(self.conn, 'experiment_passed', exp['experiment_id'],
                         f'{exp["benchmark_id"]} param {exp["param"]}: median gain {shown} % over {L.BENCH_PAIRS} ABBA pairs '
                         f'(min {exp["min_gain_pct"]} %). Hypothesis (model text): {exp["hypothesis"]}. To adopt it in '
                         'code, write a test that fails until the change is made, then send: life-ctl.py command "fix: '
                         'tests.<your_test> path.py:function"')
            self.finish_item(item, cell, 'done', f'median gain {shown} %, passed={int(passed)}', tx=False)

    # ------------------------------------------------------------------ 9. inbox, 11. agenda
    INBOX_NAME = re.compile(r'[0-9]{8}T[0-9]{6}Z-[a-z0-9-]{1,40}-[0-9a-f]{6}\.txt')

    def archive(self, src, folder, name):
        """Move an inbox file into inbox-done/ or inbox-refused/ without ever overwriting: an existing destination with
        the same bytes means an earlier tick archived it already (the source is removed); different bytes get a suffix."""
        dest = os.path.join(folder, name)
        try:
            if L.publish_noreplace(src, dest):
                return
            if os.path.isfile(dest) and not os.path.islink(src) and L.file_sha(dest) == L.file_sha(src):
                os.remove(src)
            else:
                L.publish_noreplace(src, f'{dest}.{os.urandom(3).hex()}')
        except OSError as exc:
            L.log(f'inbox: could not archive {L.sha16(name)}: {exc.strerror}')

    def ingest_inbox(self):
        """At most INBOX_PER_TICK files, oldest name first. Each is read with read_owner_file (no symlink, no FIFO wait,
        a regular file owned by the operator, at most COMMAND_MAX_BYTES). command_id = first 16 hex of sha256(file name +
        "\\n" + the file's bytes decoded as UTF-8, unstripped); the stored text is stripped and must keep at least one
        character. The command row and its item are one transaction BEFORE the file is archived, so a crash in between
        re-reads the same file into the same command id (INSERT OR IGNORE): nothing doubles. A refused file moves to
        inbox-refused/ (operator-private; purge with life-ctl purge-refused); its notice subject is sha16(file name) and
        never quotes it."""
        names = sorted(n for n in os.listdir(L.INBOX) if not n.startswith('.'))[:L.INBOX_PER_TICK]
        for name in names:
            path = os.path.join(L.INBOX, name)
            refuse, raw, text = '', b'', ''
            try:
                if not self.INBOX_NAME.fullmatch(name):
                    refuse = 'name is not <YYYYmmddTHHMMSSZ>-<slug>-<6 hex>.txt'
                else:
                    raw = L.read_owner_file(path, L.COMMAND_MAX_BYTES)
                    text = raw.decode('utf-8').strip()
                    if len(text.encode('utf-8')) < L.COMMAND_MIN_BYTES:
                        refuse = f'shorter than {L.COMMAND_MIN_BYTES} bytes after stripping white space'
                    elif L.has_secret(text):
                        refuse = 'looks like it contains a credential (text not stored)'
            except (OSError, UnicodeDecodeError) as exc:
                refuse = f'not a readable regular UTF-8 operator file of at most {L.COMMAND_MAX_BYTES} bytes ({type(exc).__name__})'
            if refuse:
                self.archive(path, L.INBOX_REFUSED, name)
                L.notice(self.conn, 'inbox_refused', L.sha16(name), refuse)
                continue
            self.add_command(L.sha16(name, raw.decode('utf-8')), name, text)
            self.archive(path, L.INBOX_DONE, name)

    def add_command(self, cid, source, text):
        """One operator command: its row and, in the same transaction, either its route (a COMMAND_PREFIXES prefix or
        the exact word status: code routes it, no model is asked, restated stays empty) or its classify item."""
        with L.Tx(self.conn):
            if self.conn.execute('SELECT 1 FROM commands WHERE command_id=?', (cid,)).fetchone():
                return
            self.conn.execute("INSERT INTO commands (command_id, file, text, state, created_at, updated_at)"
                              " VALUES (?, ?, ?, 'received', ?, ?)", (cid, source, text, L.now(), L.now()))
            low = text.lower()
            if low == 'status':
                self.route_command(cid, 'heartbeat', 'normal', '', text, prefixed=True)
                return
            for prefix, route in L.COMMAND_PREFIXES:
                if low.startswith(prefix):
                    self.route_command(cid, route, 'normal', '', text[len(prefix):].strip(), prefixed=True)
                    return
            self.new_item('command', 'command', (cid,), {'command_id': cid}, 'owner', origin=cid, priority=2)

    def agenda(self):
        """control/agenda.json (operator file): {"version": 1, "entries": [{"id", "text", "every_hours"}]}, read only on an
        admitted working tick. Each entry's revision = sha16(id, text, every_hours); its period = floor(now / (every_hours
        x HOUR)) (counted from the Unix epoch). Only the CURRENT period enters (command_id = sha16("agenda", revision,
        period)), so an entry fires once in every period, including the period in which it is added or edited; missed
        periods are skipped with notice agenda_skipped; an edited entry is a new revision. Duplicate
        ids or JSON keys, or a file that is not valid, are refused with notice agenda_invalid; entries after the 20th
        are ignored (notice). LIFE never writes the file."""
        try:
            data = json.loads(L.read_owner_file(L.AGENDA_FILE, L.AGENDA_FILE_MAX_BYTES).decode('utf-8'),
                              object_pairs_hook=L._no_dup_keys)
        except FileNotFoundError:
            return
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            L.notice(self.conn, 'agenda_invalid', 'agenda.json', f'control/agenda.json is not a valid operator file: {exc}')
            return
        entries = data.get('entries') if isinstance(data, dict) and data.get('version') == 1 and set(data) == {'version', 'entries'} else None
        if not isinstance(entries, list):
            L.notice(self.conn, 'agenda_invalid', 'agenda.json', 'control/agenda.json needs exactly {"version": 1, "entries": [...]}')
            return
        ids = [e.get('id') for e in entries if isinstance(e, dict)]
        if len(ids) != len(set(ids)):
            L.notice(self.conn, 'agenda_invalid', 'agenda.json', 'two entries share an id: the whole agenda is ignored')
            return
        if len(entries) > L.AGENDA_MAX:
            L.notice(self.conn, 'agenda_invalid', 'agenda.json', f'more than {L.AGENDA_MAX} entries: entries after the '
                     f'{L.AGENDA_MAX}th are ignored')
        state = json.loads(self.meta('agenda_state', '{}') or '{}')
        keep = {}
        for e in entries[:L.AGENDA_MAX]:
            if not (isinstance(e, dict) and set(e) == {'id', 'text', 'every_hours'} and isinstance(e['id'], str)
                    and re.fullmatch(r'[a-z0-9-]{2,40}', e['id']) and isinstance(e['text'], str)
                    and L.COMMAND_MIN_BYTES <= len(e['text'].strip().encode('utf-8')) <= L.COMMAND_MAX_BYTES
                    and not L.has_secret(e['text']) and type(e['every_hours']) is int
                    and L.AGENDA_HOURS_MIN <= e['every_hours'] <= L.AGENDA_HOURS_MAX):
                L.notice(self.conn, 'agenda_invalid', str(e.get('id') if isinstance(e, dict) else '?')[:40],
                         f'an agenda entry needs exactly id ([a-z0-9-]{{2,40}}), text ({L.COMMAND_MIN_BYTES}..'
                         f'{L.COMMAND_MAX_BYTES} bytes after stripping, no credential) and every_hours (integer '
                         f'{L.AGENDA_HOURS_MIN}..{L.AGENDA_HOURS_MAX})')
                continue
            rev = L.sha16(e['id'], e['text'], e['every_hours'])
            period = self.now // (e['every_hours'] * L.HOUR)
            last = state.get(rev)
            if isinstance(last, int) and period - last > 1:
                L.notice(self.conn, 'agenda_skipped', e['id'], f'{period - last - 1} period(s) passed while LIFE was not '
                         'working; only the current one enters')
            if last != period:
                cid = L.sha16('agenda', rev, period)
                if not self.conn.execute('SELECT 1 FROM commands WHERE command_id=?', (cid,)).fetchone():
                    self.add_command(cid, f'agenda:{e["id"]}', e['text'].strip())
            keep[rev] = period
        self.set_meta('agenda_state', json.dumps(keep, sort_keys=True))

    # ------------------------------------------------------------------ 6. canaries, 9. upkeep
    def canaries(self):
        """A round runs when one is due (CANARY_EVERY_SECONDS since the last), at every tick while no round ever passed,
        and at every tick after a failed round. It runs before the polls, so slow polling never starves it."""
        last = int(self.meta('canary_at', '0') or 0)
        due = not self.meta('canary_ok_ever') or bool(self.meta('canary_failed')) or self.now - last >= L.CANARY_EVERY_SECONDS
        if self.release is None or not due or not self.can_start(L.CANARY_ROUND_SECONDS):
            return
        failed = run_canaries(self.rdir, self.procs)
        self.set_meta('canary_at', str(self.now))
        if failed:
            self.set_meta('canary_failed', '; '.join(failed)[:600])
            L.notice(self.conn, 'canary_failed', 'canaries', '; '.join(failed))
            if 'canary' not in self.holds:
                self.holds.append('canary')
        else:
            self.set_meta('canary_failed', '')
            self.set_meta('canary_ok_ever', '1')
            if 'canary' in self.holds:
                self.holds.remove('canary')

    def backup(self):
        """First tick of each UTC day: retention, then (unless storage holds) both databases through the SQLite backup
        API into backups/{life,organism}-YYYY-MM-DD.sqlite3 (written as .partial, then renamed; 0600; newest BACKUP_KEEP
        per database kept). A backup starts only when its filesystem has the source size + BACKUP_MARGIN_BYTES free;
        otherwise notice storage (backup) and the day is retried next tick."""
        if self.meta('backup_day') == self.day:
            return
        self.retention()
        if 'storage' in self.holds:
            return
        for name, path in (('life', L.REGISTRY), ('organism', L.ORGANISM)):
            size = L.physical_bytes(path)
            if shutil.disk_usage(L.BACKUPS).free < size + L.BACKUP_MARGIN_BYTES:
                L.notice(self.conn, 'storage', 'backup', f'no room for the {name} backup ({size} bytes + margin); retried next tick')
                return
            dest = os.path.join(L.BACKUPS, f'{name}-{self.day}.sqlite3')
            tmp = dest + '.partial'
            src = sqlite3.connect(path) if name == 'organism' else self.conn
            out = sqlite3.connect(tmp)
            try:
                src.backup(out)
            finally:
                out.close()
                if name == 'organism':
                    src.close()
            os.chmod(tmp, 0o600)
            os.replace(tmp, dest)
            kept = sorted(f for f in os.listdir(L.BACKUPS) if re.fullmatch(name + r'-\d{4}-\d{2}-\d{2}\.sqlite3', f))
            for old in kept[:-L.BACKUP_KEEP]:
                os.remove(os.path.join(L.BACKUPS, old))
        self.premigration_retention()
        self.set_meta('backup_day', self.day)

    def premigration_retention(self):
        """organism-before-<id> copies, newest first: kept while both PREMIGRATION_KEEP files and PREMIGRATION_KEEP_BYTES
        bytes hold; older ones are deleted (runs in retention, also under a storage hold, and before every migration)."""
        pre = sorted((f for f in os.listdir(L.BACKUPS) if f.startswith('organism-before-')),
                     key=lambda f: os.path.getmtime(os.path.join(L.BACKUPS, f)), reverse=True)
        total = 0
        for n, name in enumerate(pre):
            path = os.path.join(L.BACKUPS, name)
            total += os.path.getsize(path)
            if n >= L.PREMIGRATION_KEEP or total > L.PREMIGRATION_KEEP_BYTES:
                os.remove(path)

    def retention(self):
        """Daily deletions (section 13 lists them): call folders whose call ended CALLS_KEEP_DAYS ago (division calls
        included) unless their item is still queued or running; calls rows ended CALL_ROWS_KEEP_DAYS ago; STATE/runs
        folders of collected runs ended RUNS_DIR_KEEP_DAYS ago; inbox-done files older than INBOX_DONE_KEEP_DAYS;
        acknowledged notices older than NOTICES_KEEP_DAYS; samples older than SAMPLES_KEEP_DAYS; abandoned temporary
        artifacts (.life-tmp-* workspaces, release .tmp-* folders, inbox-tmp files) older than TMP_KEEP_SECONDS; the
        pre-migration copies beyond their count or bytes. Retention runs under a storage hold too."""
        cutoff = self.now - L.CALLS_KEEP_DAYS * L.DAY
        for r in self.conn.execute("SELECT c.dir FROM calls c LEFT JOIN items i ON i.item_id=c.item_id WHERE c.ended_at < ? AND"
                                   " c.dir != '' AND (i.item_id IS NULL OR i.state NOT IN ('queued','running'))", (cutoff,)):
            d = r['dir']
            if d.startswith(L.CALLS + '/') and os.path.isdir(d) and not os.path.islink(d):
                shutil.rmtree(d, ignore_errors=True)
        self.conn.execute('DELETE FROM calls WHERE ended_at < ?', (self.now - L.CALL_ROWS_KEEP_DAYS * L.DAY,))
        for r in self.conn.execute("SELECT request_id FROM runs WHERE state IN ('collected','not_submitted') AND ended_at < ?",
                                   (self.now - L.RUNS_DIR_KEEP_DAYS * L.DAY,)):
            d = os.path.join(L.RUNS_DIR, r['request_id'])
            if os.path.isdir(d) and not os.path.islink(d):
                shutil.rmtree(d, ignore_errors=True)
        for folder, keep, prefix in ((L.INBOX_DONE, L.INBOX_DONE_KEEP_DAYS * L.DAY, ''), (L.INBOX_TMP, L.TMP_KEEP_SECONDS, ''),
                                     (L.RELEASES, L.TMP_KEEP_SECONDS, '.tmp-'), (L.PROJECTS, L.TMP_KEEP_SECONDS, '.life-tmp-')):
            for name in (os.listdir(folder) if os.path.isdir(folder) else []):
                path = os.path.join(folder, name)
                try:
                    if name.startswith(prefix) and self.now - os.lstat(path).st_mtime > keep:
                        if os.path.isdir(path) and not os.path.islink(path):
                            shutil.rmtree(path, ignore_errors=True)
                        else:
                            os.remove(path)
                except OSError:
                    pass
        self.conn.execute("DELETE FROM notices WHERE state='acked' AND last_at < ?", (self.now - L.NOTICES_KEEP_DAYS * L.DAY,))
        self.conn.execute('DELETE FROM samples WHERE at < ?', (self.now - L.SAMPLES_KEEP_DAYS * L.DAY,))
        self.premigration_retention()

    def storage(self):
        """Allocated bytes (st_blocks x 512, each (device, inode) once, symlinks never followed) of STATE and every
        PROJECTS/life-* path (each workspace and its <workspace>.agents sibling of hub checkouts), walked on ticks 1,
        13, 25, ... within STORAGE_WALK_SECONDS (a walk that runs out keeps the previous total); free space on the STATE
        and the PROJECTS filesystems every tick. Over STATE_MAX_BYTES or under DISK_FREE_MIN on either: notice storage
        and the storage hold, which stops new work AND intake (inbox files wait unread, the agenda, reports and backups
        pause; retention runs)."""
        if self.tick_no % L.STORAGE_EVERY_TICKS == 1 or not self.meta('state_bytes'):
            total, seen, end, complete = 0, set(), time.monotonic() + L.STORAGE_WALK_SECONDS, True
            roots = [L.STATE] + [os.path.join(L.PROJECTS, d) for d in (os.listdir(L.PROJECTS) if os.path.isdir(L.PROJECTS)
                                                                       else []) if d.startswith('life-')]
            for top in roots:
                for root, dirs, files in os.walk(top):
                    if time.monotonic() > end:
                        complete = False
                        dirs[:] = []
                        break
                    for f in files + dirs:
                        try:
                            st = os.lstat(os.path.join(root, f))
                        except OSError:
                            continue
                        if (st.st_dev, st.st_ino) not in seen:
                            seen.add((st.st_dev, st.st_ino))
                            total += st.st_blocks * 512
            if complete or not self.meta('state_bytes'):
                self.set_meta('state_bytes', str(total))
            else:
                L.log(f'storage: the walk passed {L.STORAGE_WALK_SECONDS} s; the previous total is kept')
        total = int(self.meta('state_bytes', '0'))
        free = min(shutil.disk_usage(p).free for p in (L.STATE, L.PROJECTS) if os.path.isdir(p))
        if total > L.STATE_MAX_BYTES or free < L.DISK_FREE_MIN:
            L.notice(self.conn, 'storage', 'state', f'LIFE state and workspaces use {total} bytes, {free} bytes free: new '
                     'work and intake hold until the operator frees space (STATE/calls and STATE/runs are safe to prune; '
                     'leftover hub checkouts under PROJECTS/life-*.agents/ are listed in STATE/operator/node-cleanup.txt; '
                     'STATE/text files named by knowledge rows must stay).')
            self.holds.append('storage')

    def models_inventory(self):
        """meta.models = {node: [models]} from bin/local-research --list (lines `<node> <model> <size> GB`), re-read once
        a day (no model is called). A successful listing that names no LIFE node opens notice inventory_shape."""
        age = self.now - int(self.meta('models_at', '0') or 0)
        due = age >= L.MODELS_REFRESH_SECONDS or (self.meta('models_retry') == '1' and age >= L.MODELS_RETRY_SECONDS)
        if not due or not self.can_start(L.CATALOG_TIMEOUT):
            return
        self.set_meta('models_retry', '')
        rc, out, _ = self.proc([L.RESEARCH, '--list'], L.CATALOG_TIMEOUT, env=L.child_env())
        self.set_meta('models_at', str(self.now))
        if rc != 0:
            return
        inv = {}
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] in L.NODES:
                inv.setdefault(parts[0], []).append(parts[1])
        if inv:
            self.set_meta('models', json.dumps(inv, sort_keys=True))
        else:
            L.notice(self.conn, 'inventory_shape', 'inventory', 'bin/local-research --list answered but named no LIFE node; '
                     'the model inventory is unknown (every rung is tried; infra counters bound the rest)')

    def model_installed(self, node, model):
        """A readable inventory that names some LIFE node but not this one says this node has NO known model (it was
        offline at inventory time): no rung is tried there and the inventory is re-read after MODELS_RETRY_SECONDS. An
        empty or unread inventory never blocks (every rung is tried; infra counters bound what follows)."""
        inv = json.loads(self.meta('models', '{}') or '{}')
        if not inv:
            return True
        if node not in inv:
            self.set_meta('models_retry', '1')
            return False
        return model in inv[node]

    def hold_notices(self):
        """The same hold for HOLD_NOTICE_TICKS ticks in a row opens notice `held`; a working tick resets the count."""
        reason = self.holds[0] if self.holds else ''
        prev, count = self.meta('hold_reason'), int(self.meta('hold_ticks', '0') or 0)
        count = count + 1 if reason and reason.split(':')[0] == prev.split(':')[0] else (1 if reason else 0)
        self.set_meta('hold_reason', reason)
        self.set_meta('hold_ticks', str(count))
        if count >= L.HOLD_NOTICE_TICKS:
            L.notice(self.conn, 'held', reason.split(':')[0][:120], f'LIFE has started no work for {count} ticks: {reason}')

    # ------------------------------------------------------------------ command reports
    def descendants(self, cid):
        """(every item reachable from the command through origin links, truncated): breadth first, each item once (a
        cycle is impossible to follow twice); truncated is True when more than REPORT_TRAVERSE_MAX items exist."""
        out, frontier, seen = [], [cid], {cid}
        while frontier:
            rows = self.conn.execute(f'SELECT * FROM items WHERE origin IN ({",".join("?" * len(frontier))})', frontier).fetchall()
            frontier = []
            for r in rows:
                if r['item_id'] not in seen:
                    seen.add(r['item_id'])
                    out.append(r)
                    frontier.append(r['item_id'])
                    if len(out) > L.REPORT_TRAVERSE_MAX:
                        return out, True
        return out, False

    def approval_stale(self, item):
        return (item['kind'] in ('lesson', 'request') and item['taint'] in ('web', 'model') and not item['approved']
                and item['state'] == 'queued' and self.now - item['created_at'] > L.APPROVAL_STALE_DAYS * L.DAY)

    def reports(self):
        """Dispatched commands, the REPORT_COMMANDS_PER_TICK least recently examined first (an examined command's
        updated_at moves to now, so the next tick reads the next ones). A command whose every descendant item has ended
        (a web- or model-derived lesson or request waiting for approval longer than APPROVAL_STALE_DAYS counts as
        ended) gets STATE/operator/reports/<command_id>.md, state done (failed when every item failed) and notice
        command_done. Every text in a report passes one_line (control characters removed); at most REPORT_ITEMS_MAX
        items are listed, with a line saying how many more exist."""
        if 'storage' in self.holds:
            return
        for cmd in self.conn.execute("SELECT * FROM commands WHERE state='dispatched' ORDER BY updated_at, command_id LIMIT ?",
                                     (L.REPORT_COMMANDS_PER_TICK,)).fetchall():
            items, truncated = self.descendants(cmd['command_id'])
            items = [i for i in items if i['kind'] != 'command']
            if truncated:
                L.notice(self.conn, 'report_truncated', cmd['command_id'], f'more than {L.REPORT_TRAVERSE_MAX} items descend '
                         'from this command; its report waits')
            if truncated or not items or any(i['state'] in ('queued', 'running') and not self.approval_stale(i) for i in items):
                self.conn.execute('UPDATE commands SET updated_at=? WHERE command_id=?', (L.now(), cmd['command_id']))
                continue
            self.write_report(cmd, items)

    def write_report(self, cmd, items):
        ol = L.one_line
        ids = [i['item_id'] for i in items]
        q = ','.join('?' * len(ids))
        lines = [f'# Command {cmd["command_id"]}', '', f'Text: {ol(cmd["text"], 4000)}',
                 f'Route: {ol(cmd["organ"], 20)}  urgency {ol(cmd["urgency"], 10)}  received '
                 f'{time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(cmd["created_at"]))}', '', '## Items', '']
        lines += [f'- {i["item_id"]} ({i["kind"]}, {i["stage"]}): {i["state"]}'
                  + (' (waiting for approval)' if self.approval_stale(i) else '') + f': {ol(i["outcome"], 300)}'
                  for i in items[:L.REPORT_ITEMS_MAX]]
        if len(items) > L.REPORT_ITEMS_MAX:
            lines.append(f'- ... and {len(items) - L.REPORT_ITEMS_MAX} more items (not listed)')
        answers = self.conn.execute(f'SELECT * FROM answers WHERE item_id IN ({q})', ids).fetchall()
        if answers:
            lines += ['', '## Research answers (model text, unverified; the latest per question)', '']
            lines += [f'- {ol(a["applicator"], 80)}: {ol(a["answer"], 4000)}' for a in answers]
        srcs = self.conn.execute(f'SELECT s.* FROM sources s JOIN question_sources qs ON qs.source_key=s.source_key WHERE '
                                 f'qs.question_id IN ({q})', ids).fetchall()
        if srcs:
            lines += ['', '## Sources (search hits and pages the model asked to read)', '']
            lines += [f'- {ol(s["url"], 2000)} ({s["fetch_state"]})' for s in srcs]
            keys = [s['source_key'] for s in srcs]
            facts = self.conn.execute(f'SELECT k.*, s.url FROM knowledge k JOIN sources s ON s.source_key=k.source_key '
                                      f'WHERE k.source_key IN ({",".join("?" * len(keys))})', keys).fetchall()
            if facts:
                lines += ['', '## Quote-verified claims (the quote is in the page; the claim is not verified)', '']
                lines += [f'- {ol(f["claim"], 300)} — "{ol(f["quote"], 400)}" ({ol(f["url"], 2000)})' for f in facts]
        for table, key in (('patches', 'patch_id'), ('proposals', 'proposal_id'), ('experiments', 'experiment_id'),
                           ('migrations', 'migration_id')):
            rows = self.conn.execute(f'SELECT * FROM {table} WHERE item_id IN ({q})', ids).fetchall()
            if rows:
                lines += ['', f'## {table}', ''] + [f'- {r[key]}: {r["state"]}' for r in rows]
        merged = self.conn.execute('SELECT command_id FROM commands WHERE merged_into=?', (cmd['command_id'],)).fetchall()
        if merged:
            lines += ['', '## Commands merged into this one', ''] + [f'- {m["command_id"]}' for m in merged]
        L.write_atomic(os.path.join(L.REPORTS, f'{cmd["command_id"]}.md'), '\n'.join(lines) + '\n')
        state = 'failed' if all(i['state'] == 'failed' for i in items) else 'done'
        with L.Tx(self.conn):
            self.conn.execute('UPDATE commands SET state=?, updated_at=? WHERE command_id=?', (state, L.now(), cmd['command_id']))
            L.notice(self.conn, 'command_done', cmd['command_id'], f'command {state}: life-ctl.py report {cmd["command_id"]}')

    # ------------------------------------------------------------------ 12. findings (codebase)
    def guard_begin(self, ws):
        """Before candidate code runs in ws: its git_meta_sha256, recorded (workspace_guard) and committed BEFORE the
        run, so a tick killed during the run leaves the evidence that the end was never checked (recover deletes the
        workspace). Returns the hash, or '' when the .git tree cannot be inspected (the run must not happen)."""
        try:
            meta0 = L.git_meta_sha256(ws)
        except (OSError, ValueError):
            return ''
        with L.Tx(self.conn):
            self.conn.execute('INSERT OR REPLACE INTO workspace_guard (workspace, sha256, at) VALUES (?, ?, ?)', (ws, meta0, L.now()))
        return meta0

    def guard_end(self, ws, meta0, shm0):
        """After the run: /dev/shm entries the run left are removed (GAP 17), the guard row goes, and the .git tree must
        hash as before (False: the caller deletes the workspace)."""
        L.shm_cleanup(shm0)
        try:
            same = L.git_meta_sha256(ws) == meta0
        except (OSError, ValueError):
            same = False
        with L.Tx(self.conn):
            self.conn.execute('DELETE FROM workspace_guard WHERE workspace=?', (ws,))
        return same

    def watch_run(self, ws, test):
        """One unittest run of `test` in the clone `ws`: /usr/bin/python3 -s -B -m unittest under prlimit (address space
        4 GiB, file size 2 GiB), inside the Landlock sandbox (empty temporary HOME, no STATE, no TCP), inside a
        life-watch-*.scope in work.slice (MemoryMax 4G), killed at
        WATCH_TIMEOUT, admitted as heavy the host work. Returns (rc, raw output tail, wall seconds, git_ok): git_ok is
        False when the .git tree could not be inspected or the run changed it (git_meta_sha256); the clone is then
        never touched by trusted git again."""
        import tempfile
        meta0 = self.guard_begin(ws)
        if not meta0:
            return 125, 'the clone\'s .git tree cannot be inspected', 0.0, False
        shm0 = L.shm_entries()
        home = tempfile.mkdtemp(prefix='life-watch-')
        try:
            argv = L.scope_argv(L.sandbox_argv(ws, home, ['/usr/bin/prlimit', f'--as={L.BENCH_AS_BYTES}',
                                                          f'--fsize={L.BENCH_FSIZE_BYTES}', L.SYS_PY, '-s', '-B', '-m',
                                                          'unittest', test]), runtime=L.WATCH_TIMEOUT, name='watch')
            start = time.monotonic()
            rc, out, err = self.proc(argv, L.WATCH_TIMEOUT, heavy=True, cwd=ws, env=L.scope_env())
            wall = time.monotonic() - start
        finally:
            shutil.rmtree(home, ignore_errors=True)
        git_ok = self.guard_end(ws, meta0, shm0)
        if git_ok:
            self.reset_workspace(ws)
        return rc, '\n'.join((err + '\n' + out).strip().splitlines()[-L.TAIL_LINES:]), wall, git_ok

    def git_meta_broken(self, cell, where):
        """Candidate code changed the clone's git configuration: the clone is deleted (the workspace sweep re-creates it)
        and the operator is told. Trusted git never runs in it again."""
        ws = cell['workspace']
        if ws and ws.startswith(f'{L.PROJECTS}/life-') and not os.path.islink(ws):
            shutil.rmtree(ws, ignore_errors=True)
        L.notice(self.conn, 'workspace', ws or '?', f'{where} changed or hid the clone\'s .git administrative files '
                 '(configuration, refs, objects, hooks); the clone was deleted and will be re-created')

    def codebase_cell_for_watch(self):
        for c in self.conn.execute("SELECT * FROM cells WHERE organ='codebase' AND state='active' AND workspace IS NOT NULL"
                                   ' ORDER BY cell_id').fetchall():
            if not self.workspace_busy(c['cell_id']):
                return c
        return None

    def watch_outcome(self, rc, tail, wall, test, root):
        """'pass' | 'timeout' | 'sandbox' | 'stopped' | 'slow' | 'error' (not a unittest failure) | 'fail'. pass needs exit 0
        AND a `Ran N tests` line with N >= 1, an `OK` line and fewer skips than tests; fail needs a nonzero exit, a
        `FAILED (` line, an exception line failure_fingerprint can read, and no environment error (life_common.env_error:
        decided by the LAST exception line, never by a word anywhere in the output). Slowness (wall time of the
        sandboxed run, scope and sandbox start-up included, over WATCH_SLOW) is judged for passing and failing runs
        alike. STOP or a refused admission ('stopped') is nothing: no notice, no counter."""
        if rc in (L.STOPPED_RC, L.NOT_ADMITTED_RC):
            return 'stopped' 
        ran = re.search(r'^Ran ([0-9]+) tests? in ', tail, re.M)
        skipped = re.search(r'skipped=([0-9]+)', tail)
        if rc == 125:
            L.notice(self.conn, 'sandbox', 'landlock', 'the Landlock launcher refused (exit 125): LIFE runs no candidate code '
                     'without it, so the codebase organ waits')
            return 'sandbox'
        if rc is None:
            L.notice(self.conn, 'watch_timeout', test, f'the test did not finish in {L.WATCH_TIMEOUT} s; it is not a finding')
            return 'timeout'
        if wall > L.WATCH_SLOW:
            L.notice(self.conn, 'watch_too_slow', test, f'the sandboxed run took {int(wall)} s; autogen checks stop at 120 s, so '
                     f'LIFE never patches a test slower than {L.WATCH_SLOW} s')
            return 'slow'
        why = ''
        if rc == 0:
            n = int(ran.group(1)) if ran else 0
            if n >= 1 and re.search(r'^OK\b', tail, re.M) and (not skipped or int(skipped.group(1)) < n):
                return 'pass'
            why = 'exit 0 but no test ran, or every test was skipped'
        elif rc in (127, L.OUTPUT_LIMIT_RC) or L.env_error(rc, tail, root) or 'FAILED (' not in tail \
                or L.failure_fingerprint(tail) is None:
            why = 'not a readable unittest failure (environment, sandbox, scope or output error)'
        if why:
            L.notice(self.conn, 'watch_error', test, why + '; it is not a finding: ' + L.one_line(L.redact(tail)[-300:], 300))
            return 'error'
        return 'fail'

    def findings(self):
        """One due watched test per admitted tick (LIFE.md section 7.4)."""
        if not self.can_start(L.WATCH_STAGE_SECONDS) or not self.may_admit():
            return
        try:
            raw = L.read_owner_file(L.WATCH_FILE, L.WATCH_FILE_MAX_BYTES).decode('utf-8').splitlines()
        except FileNotFoundError:
            return
        except (OSError, UnicodeDecodeError) as exc:
            L.notice(self.conn, 'watch_invalid', 'watch.txt', f'control/watch.txt is not a regular UTF-8 operator file of at '
                     f'most {L.WATCH_FILE_MAX_BYTES} bytes ({type(exc).__name__}: {exc}); no watched test runs')
            return
        tests = []
        for t in (ln.strip() for ln in raw):
            if t and not t.startswith('#') and L.valid_test_id(t) and t not in tests:
                tests.append(t)
        tests = tests[:L.WATCH_MAX]
        state = json.loads(self.meta('watch_state', '{}') or '{}')
        due = sorted((t for t in tests if self.now >= state.get(t, {}).get('next', 0)), key=lambda t: (state.get(t, {}).get('ran', 0), t))
        cell = self.codebase_cell_for_watch()
        if not due or not cell or not os.path.isdir(os.path.join(cell['workspace'], '.git')):
            return
        test = due[0]
        st = state.setdefault(test, {})
        if st.get('finding') and self.conn.execute("SELECT 1 FROM items WHERE item_id=? AND state IN ('queued','running')",
                                                   (st['finding'],)).fetchone():
            return                                          # one open finding per watched test
        self.begin_stage(L.WATCH_STAGE_SECONDS)
        try:
            base = self.refresh_clone(cell['workspace'], None)
            if base is None:
                return
            if not base:
                L.notice(self.conn, 'workspace', cell['workspace'], f'the codebase clone could not be refreshed, so the '
                         f'watched test {test} did not run')
                return
            rc, tail, wall, git_ok = self.watch_run(cell['workspace'], test)
        finally:
            self.end_stage()
        if not git_ok:
            self.git_meta_broken(cell, f'the watched test {test}')
            return
        outcome = self.watch_outcome(rc, tail, wall, test, cell['workspace'])
        if outcome == 'stopped':
            return
        st['ran'] = self.now
        fails = st.get('fails', 0)
        if outcome == 'pass':
            st.update(fails=0, next=self.now + L.WATCH_BACKOFF[0])
        elif outcome != 'fail':
            st['next'] = self.now + (L.WATCH_BACKOFF[-1] if outcome == 'slow' else L.WATCH_BACKOFF[0])
        else:
            text = L.redact(tail)
            cls, msg = L.failure_fingerprint(text) or L.failure_fingerprint(tail) or ('Unknown', '')
            line = f'{cls}: {msg}'
            prev = self.item(st['finding']) if st.get('finding') else None
            unacked = prev is not None and self.conn.execute(
                "SELECT 1 FROM notices WHERE subject=? AND state='open'", (prev['item_id'],)).fetchone()
            waiting = prev is not None and prev['state'] == 'done' and line == st.get('line') and self.conn.execute(
                "SELECT 1 FROM patches WHERE item_id=? AND state IN ('bundled','ready','owner')", (prev['item_id'],)).fetchone()
            st.update(fails=fails + 1, next=self.now + L.WATCH_BACKOFF[min(fails, len(L.WATCH_BACKOFF) - 1)])
            if not ((prev is not None and prev['state'] in ('owner', 'failed') and line == st.get('line') and unacked)
                    or waiting):
                occurrence = st.get('occurrence', 0) + 1
                with L.Tx(self.conn):
                    iid, _ = self.new_item('codebase', 'finding', (test, base, line, str(occurrence)),
                                           {'test_id': test, 'finding_text': L.lint_safe(text, L.FINDING_CHARS) or 'the test failed',
                                            'base_commit': base, 'source': 'watch', 'wall_s': int(wall),
                                            'trace_files': L.traceback_files(text, cell['workspace']),
                                            'trace_functions': L.traceback_functions(text, cell['workspace'])}, 'code', stage='triage')
                st.update(finding=iid, line=line, occurrence=occurrence)
        self.set_meta('watch_state', json.dumps(state, sort_keys=True))

    def confirm_finding(self, item, cell):
        """Owner findings: run the named test at the branch head first. Passing -> operator (already_passing); a unittest
        failure -> the real output and base commit are recorded and the finding goes to triage."""
        p = json.loads(item['payload'])
        base = self.refresh_clone(cell['workspace'], None)
        if base is None:
            return None
        if not base:
            L.notice(self.conn, 'workspace', cell['workspace'], 'the codebase clone could not be refreshed')
            return self.count_infra(item, cell, 'confirm: the codebase clone could not be refreshed')
        rc, tail, wall, git_ok = self.watch_run(cell['workspace'], p['test_id'])
        if not git_ok:
            self.git_meta_broken(cell, f'the confirmation of {p["test_id"]}')
            return self.count_infra(item, cell, 'confirm: the clone was re-created')
        outcome = self.watch_outcome(rc, tail, wall, p['test_id'], cell['workspace'])
        if outcome == 'stopped':
            return self.item_update(item['item_id'], state='queued', outcome='confirm: stopped before it ran (no count)')
        if outcome == 'pass':
            L.notice(self.conn, 'already_passing', item['item_id'], f'{p["test_id"]} passes at {base[:12]}; LIFE writes no patch')
            self.finish_item(item, cell, 'owner', 'the named test already passes')
        elif outcome in ('timeout', 'sandbox'):
            self.count_infra(item, cell, f'confirm: {outcome}')
        elif outcome != 'fail':
            self.finish_item(item, cell, 'owner', f'confirm: {outcome}')
        else:
            text = L.redact(tail)
            # the command may name extra functions as path.py:qualified.name (a bare file name names nothing)
            named = {}
            for f, fn in re.findall(r'\b([A-Za-z0-9_][A-Za-z0-9_/.-]*\.py):([A-Za-z_][A-Za-z0-9_.]{0,200})',
                                    p.get('command_text', '')):
                if (not L.TEST_RX.match(f) and not L.GATE_DENY_RX.match(f) and '..' not in f.split('/')
                        and re.fullmatch(L.PATH_TOKEN, f) and L.QUALNAME_RX.fullmatch(fn)):
                    named.setdefault(f, []).append(fn)
            files = list(dict.fromkeys(L.traceback_files(text, cell['workspace']) + list(named)))[:L.LOCAL_FIX_FILES_MAX]
            funcs = L.traceback_functions(text, cell['workspace'])
            p.update(base_commit=base, wall_s=int(wall), finding_text=L.lint_safe(p['finding_text'] + ' Test output: ' + text, L.FINDING_CHARS),
                     trace_files=files, trace_functions={f: list(dict.fromkeys(funcs.get(f, []) + named.get(f, [])))[:20]
                                                         for f in files})
            p.pop('command_text', None)
            self.item_update(item['item_id'], stage='triage', state='queued', payload=json.dumps(p, sort_keys=True))

    def refresh_clone(self, ws, base):
        """Bring a codebase clone to `base` (or to origin/<branch recorded at seed> when None). The fetch runs in its own
        life-fetchgit-*.scope (MemoryMax 2G, outside the tick's 1G) and is admitted as heavy the host work. Returns the
        HEAD commit, '' on a failure, or None when the fetch never started (STOP or admission: the caller waits)."""
        branch = self.meta('codebase_branch')
        problems = L.git_admin_problems(ws)
        if problems:
            L.notice(self.conn, 'workspace', ws, 'trusted git refused to run there: ' + '; '.join(problems)[:400])
            return ''
        argv = L.scope_argv(['git', *L.GIT_SAFE, '-C', ws, 'fetch', '-q', 'origin', branch], memory='2G',
                            runtime=L.GIT_FETCH_TIMEOUT, name='fetchgit')
        rc = self.proc(argv, L.GIT_FETCH_TIMEOUT, heavy=True, env=L.scope_env())[0]
        if rc in (L.STOPPED_RC, L.NOT_ADMITTED_RC):
            return None                                   # not started: the caller waits, nothing is counted
        if rc != 0:
            return ''
        target = base or f'origin/{branch}'
        if self.git(ws, 'reset', '-q', '--hard', target)[0] != 0 or self.git(ws, 'clean', '-ffdxq')[0] != 0:
            return ''
        rc, out, _ = self.git(ws, 'rev-parse', 'HEAD')
        return out.strip() if rc == 0 and re.fullmatch(r'[0-9a-f]{40}', out.strip()) else ''

    def reset_workspace(self, ws):
        """git reset --hard HEAD and git clean -ffdx (ignored files too): nothing a run, a test or a gate wrote survives."""
        if ws and os.path.isdir(os.path.join(ws, '.git')):
            self.git(ws, 'reset', '-q', '--hard', 'HEAD')
            self.git(ws, 'clean', '-ffdxq')

    def make_workspace(self, organ, ws, model_ws):
        """Create an agent cell's workspace in a temporary folder, then rename it into place; every git step shares ONE
        CLONE_TIMEOUT deadline and runs in a life-clone-*.scope. codebase: a single-branch clone of host-checkout's
        committed history with .backups/ outside the sparse checkout; selfdev and database: a clone of the model
        workspace's commits (model_ws None or not a git workspace: built from nothing as the seed builds it,
        build_workspace). Every clone is admitted as heavy the host work. Returns '' on success, else the reason."""
        if os.path.isdir(os.path.join(ws, '.git')):
            return ''
        if os.path.lexists(ws):
            return f'{ws} exists but is not a git workspace'
        tmp = os.path.join(L.PROJECTS, f'.life-tmp-{L.sha16(ws, time.time())[:8]}')
        branch = self.meta('codebase_branch')
        safe = list(L.GIT_SAFE)
        if organ == 'codebase':
            steps = [['git', *safe, 'clone', '-q', '--no-local', '--single-branch', '--branch', branch, '--no-tags',
                      '--no-checkout', L.REPO, tmp],
                     ['git', *safe, '-C', tmp, 'sparse-checkout', 'set', '--no-cone', '/*', '!/.backups/'],
                     ['git', *safe, '-C', tmp, 'checkout', '-q', branch]]
        elif not model_ws or not os.path.isdir(os.path.join(model_ws, '.git')) or L.git_admin_problems(model_ws):
            return self.build_workspace(organ, ws)
        else:
            steps = [['git', *safe, 'clone', '-q', '--no-local', model_ws, tmp]]
        end = time.monotonic() + L.CLONE_TIMEOUT
        for argv in steps:
            left = int(end - time.monotonic())
            rc, _, err = self.proc(L.scope_argv(argv, runtime=max(1, left), name='clone'), left, heavy=True, env=L.scope_env())
            if rc != 0:
                shutil.rmtree(tmp, ignore_errors=True)
                return NOT_STARTED if rc in (L.STOPPED_RC, L.NOT_ADMITTED_RC) else 'git failed: ' + L.one_line(err[-200:], 200)
        os.rename(tmp, ws)
        return ''

    def build_workspace(self, organ, ws):
        """A selfdev or database workspace with no trusted source to clone from is built as the seed builds it:
        bin/symblic-task workspace NAME, then selfdev: genome/ and genome-base/ = the active release, database:
        migrations/.keep, schema-snapshot.sql and MIGRATION-RULES.txt; one commit. Returns '' on success."""
        rc, out, err = self.proc([L.TASK, 'workspace', os.path.basename(ws)], L.GIT_TIMEOUT, heavy=True, env=L.child_env())
        if rc in (L.STOPPED_RC, L.NOT_ADMITTED_RC):
            return NOT_STARTED
        if rc != 0 or not os.path.isdir(os.path.join(ws, '.git')):
            return 'symblic-task workspace failed: ' + L.one_line((out + err)[-200:], 200)
        if organ == 'selfdev':
            self.sync_selfdev(ws)
        else:
            os.makedirs(os.path.join(ws, 'migrations'), exist_ok=True)
            L.write_atomic(os.path.join(ws, 'migrations', '.keep'), '', 0o644)
            self.git(ws, 'add', '--', 'migrations/.keep')
            self.write_snapshot(ws)
        rc, out, _ = self.git(ws, 'rev-parse', 'HEAD')
        return '' if rc == 0 and re.fullmatch(r'[0-9a-f]{40}', out.strip()) else 'the built workspace has no commit'

    # ------------------------------------------------------------------ 14. The host-side stages
    def host_stages(self):
        """Fetches, then at most one confirmation, one codebase gate (only while the gate is proven: gate_selftest),
        one selfdev gate and one database apply, each admitted again; then agent starts."""
        self.fetch_sources()
        for organ, stage, fn, budget in (('codebase', 'confirm', self.confirm_finding, L.CONFIRM_STAGE_SECONDS),
                                         ('codebase', 'gate', self.gate_patch, L.GATE_STAGE_SECONDS),
                                         ('selfdev', 'gate', self.gate_proposal, L.SELFDEV_GATE_STAGE_SECONDS),
                                         ('database', 'apply', self.apply_migration, L.APPLY_STAGE_SECONDS)):
            if not self.can_start(budget) or not self.may_admit():
                continue
            if organ == 'database' and self.database_hold:
                continue
            if organ == 'codebase' and stage == 'gate' and self.codebase_unproven:
                continue
            item = self.conn.execute("SELECT * FROM items WHERE organ=? AND stage=? AND state='queued' AND cell_id IS NOT NULL"
                                     ' ORDER BY priority DESC, updated_at, item_id LIMIT 1', (organ, stage)).fetchone()
            if not item:
                continue
            cell = self.cell(item['cell_id'])
            if not os.path.isdir(os.path.join(cell['workspace'] or '', '.git')):
                continue                                     # the sweep re-creates it first
            if stage == 'confirm' and (cell['state'] != 'active' or self.workspace_busy(cell['cell_id'], except_item=item['item_id'])):
                continue                                     # confirmation needs an idle clone
            self.begin_stage(budget)
            try:
                self.guard(item['item_id'], lambda fn=fn, item=item, cell=cell: fn(item, cell))
            finally:
                self.end_stage()
        self.start_agent_runs()

    def fetch_sources(self):
        rows = self.conn.execute("SELECT * FROM items WHERE organ='digest' AND stage='fetch' AND state='queued' AND"
                                 ' cell_id IS NOT NULL ORDER BY priority DESC, updated_at, item_id LIMIT ?', (L.FETCHES_PER_TICK,)).fetchall()
        for item in rows:
            if not self.can_start(L.FETCH_TIMEOUT) or not self.may_admit():
                return
            self.guard(item['item_id'], lambda item=item: self.fetch_one(item))

    def fetch_one(self, item):
        """bin/life-fetch.py (deep_research.safe_fetch once, then local_research.page_text/pdf_text) in its own process,
        its own life-fetch-*.scope (MemoryMax FETCH_MEMORY) and prlimit --as FETCH_AS_BYTES, admitted as heavy the host
        work. Outcome table: text of at least SOURCE_TEXT_MIN characters -> credential-shaped spans redacted
        (sources.redacted = 1 when any was), then stored, stage extract; text whose sha256 equals an already fetched
        source's snapshot -> abstained DUPLICATE_TEXT (fetch_state duplicate, duplicate_of that source, every question
        linked to this source is linked to that one); shorter -> abstained EMPTY; refused (robots, address, size,
        type, an HTTP 401/403/404/410/451 or another non-2xx status) -> abstained; transient (a network fault, HTTP
        408/425/429/5xx, a timeout) -> infra (re-queued, INFRA_RUNS_MAX); STOP or a refused admission -> nothing."""
        p = json.loads(item['payload'])
        cell = self.cell(item['cell_id'])
        py = L.REPO_PY if os.path.exists(L.REPO_PY) else L.SYS_PY
        argv = L.scope_argv(['prlimit', f'--as={L.FETCH_AS_BYTES}', py, '-I', '-B', L.FETCHER, p['url']],
                            memory=L.FETCH_MEMORY, runtime=L.FETCH_TIMEOUT, name='fetch')
        rc, out, err = self.proc(argv, L.FETCH_TIMEOUT, heavy=True, env=L.scope_env())
        if rc in (L.STOPPED_RC, L.NOT_ADMITTED_RC):
            return
        try:
            res = L.strict_json(out) if rc == 0 else {'ok': False, 'kind': 'error', 'detail': f'rc {rc}: {err[-200:]}'}
        except ValueError:
            res = {'ok': False, 'kind': 'error', 'detail': 'no JSON from life-fetch'}
        if not isinstance(res, dict) or not res.get('ok'):
            res = res if isinstance(res, dict) else {'kind': 'error', 'detail': 'not a JSON object'}
            if res.get('kind') == 'refused':
                self.conn.execute("UPDATE sources SET fetch_state='failed' WHERE source_key=?", (p['source_key'],))
                self.finish_item(item, cell, 'abstained', 'fetch refused: ' + L.one_line(res.get('detail'), 200))
            else:
                self.count_infra(item, cell, 'fetch: ' + L.one_line(res.get('detail'), 200))
            return
        text = str(res.get('text') or '')
        if len(text.strip()) < L.SOURCE_TEXT_MIN:
            self.conn.execute("UPDATE sources SET fetch_state='empty' WHERE source_key=?", (p['source_key'],))
            self.finish_item(item, cell, 'abstained', f'EMPTY: under {L.SOURCE_TEXT_MIN} characters of text')
            return
        redacted = L.has_secret(text)
        if redacted:
            text = L.redact(text)
        digest = L.sha(text)
        twin = self.conn.execute("SELECT source_key FROM sources WHERE text_sha256=? AND fetch_state='fetched' AND "
                                 'source_key != ?', (digest, p['source_key'])).fetchone()
        if twin is not None:
            with L.Tx(self.conn):
                self.conn.execute("UPDATE sources SET fetch_state='duplicate', duplicate_of=? WHERE source_key=?",
                                  (twin['source_key'], p['source_key']))
                for q in self.conn.execute('SELECT question_id FROM question_sources WHERE source_key=?', (p['source_key'],)).fetchall():
                    self.conn.execute('INSERT OR IGNORE INTO question_sources (question_id, source_key, at) VALUES (?, ?, ?)',
                                      (q['question_id'], twin['source_key'], L.now()))
                self.finish_item(item, cell, 'abstained', f'DUPLICATE_TEXT of {twin["source_key"][:80]}', tx=False)
            return
        path = os.path.join(L.TEXTS, L.sha16(p['source_key']) + '.txt')
        L.write_atomic(path, text)
        digest = L.file_sha(path)
        with L.Tx(self.conn):
            self.conn.execute("UPDATE sources SET fetch_state='fetched', text_path=?, text_sha256=?, redacted=? WHERE source_key=?",
                              (path, digest, int(redacted), p['source_key']))
            p.update(text_path=path, text_sha256=digest)
            self.item_update(item['item_id'], stage='extract', state='queued', payload=json.dumps(p, sort_keys=True))

    def count_infra(self, item, cell, detail, tx=True):
        """An infrastructure outcome: re-queue (nothing counts against the cell) until INFRA_RUNS_MAX, then operator."""
        n = item['infra_runs'] + 1
        if n >= L.INFRA_RUNS_MAX:
            def body():
                L.notice(self.conn, 'infra_repeat', item['item_id'], f'{n} infrastructure outcomes; last: {detail}')
                self.finish_item(item, cell, 'owner', f'infra {n} times: {detail}', tx=False)
            if tx:
                with L.Tx(self.conn):
                    body()
            else:
                body()
        else:
            self.item_update(item['item_id'], state='queued', infra_runs=n, outcome='infra: ' + L.one_line(detail, 380))

    def staged_diff(self, ws, base):
        """(names, raw, diff, ok) of everything in ws against `base`, every untracked file staged first; the platform
        control files at the root are excluded; no external diff and no textconv ever runs."""
        self.git(ws, 'add', '-A')
        spec = ['--', '.'] + [f':(exclude,top){n}' for n in L.CONTROL_NAMES]
        rc1, names, _ = self.git(ws, 'diff', '--cached', '--no-renames', '--no-ext-diff', '--no-textconv', '--name-only', base, *spec)
        rc2, raw, _ = self.git(ws, 'diff', '--cached', '--no-renames', '--no-ext-diff', '--no-textconv', '--raw', base, *spec)
        rc3, diff, _ = self.git(ws, 'diff', '--cached', '--no-renames', '--no-ext-diff', '--no-textconv', base, *spec)
        files = [f for f in names.splitlines() if f.strip()]
        return files, raw, diff, rc1 == rc2 == rc3 == 0

    @staticmethod
    def mode_problems(raw):
        """Only regular files: a new file 100644, a changed file keeps its mode; no symlink, submodule, type change
        (T: a file replaced by a symlink or submodule) or mode change; any raw line of another kind is refused too."""
        out = []
        for ln in raw.splitlines():
            if not ln.strip():
                continue
            m = re.match(r':(\d{6}) (\d{6}) \S+ \S+ ([A-Z])[0-9]*\t(.+)$', ln)
            if not m:
                out.append(f'unreadable raw diff line: {ln[:80]}')
                continue
            old, new, kind, path = m.groups()
            if kind not in 'AMD':
                out.append(f'{path}: {kind} change {old} -> {new} is refused (only additions, modifications and deletions '
                           'of regular files)')
            elif kind == 'A' and new != '100644' or kind == 'M' and (old != new or new not in ('100644', '100755')) \
                    or kind == 'D' and old not in ('100644', '100755'):
                out.append(f'{path}: mode {old} -> {new} ({kind}) is not a plain text change')
        return out

    def publish_bundle(self, folder, bundle_id, files):
        """Write a bundle's files into a private temporary folder (each written and fsynced by write_atomic), fsync the
        folder, rename it into place without replacing anything, and fsync the parent, all BEFORE the caller commits a
        registry row naming it. An existing bundle with this content-derived id is reused only when it holds exactly
        these files with exactly these bytes; anything else raises (a tick fault on the item: immutable evidence is
        never overwritten)."""
        dest = os.path.join(L.BUNDLES, folder, bundle_id)
        if os.path.lexists(dest):
            have = sorted(os.listdir(dest)) if os.path.isdir(dest) and not os.path.islink(dest) else None
            if have != sorted(files) or any(L.file_sha(os.path.join(dest, n)) != L.sha(t) for n, t in files.items()):
                raise RuntimeError(f'bundle {folder}/{bundle_id} exists with other content')
            return dest
        tmp = os.path.join(L.BUNDLES, folder, f'.tmp-{bundle_id}-{os.urandom(4).hex()}')
        os.makedirs(tmp, mode=0o700)
        for name, text in files.items():
            L.write_atomic(os.path.join(tmp, name), text)
        L.fsync_dir(tmp)
        if os.path.lexists(dest):
            shutil.rmtree(tmp, ignore_errors=True)
            raise RuntimeError(f'bundle {folder}/{bundle_id} appeared while it was written')
        os.rename(tmp, dest)
        L.fsync_dir(os.path.join(L.BUNDLES, folder))
        return dest

    def gate_patch(self, item, cell):
        """The codebase gate (LIFE.md section 7.4): every path and content rule, the local_fix body rule, the sandboxed
        gate script, the unchanged-after-gate check; a pass bundles the patch and queues its review."""
        ws, p = cell['workspace'], json.loads(item['payload'])
        base = p.get('base_commit') or ''
        files, raw, diff, ok = self.staged_diff(ws, base)
        problems = [] if ok and re.fullmatch(r'[0-9a-f]{40}', base) else ['git could not diff against the base commit']
        if not problems:
            if p['change_class'] == 'test_only':
                module = L.resolve_test_module(ws, p['test_id'])
                allowed = (module,) if module else ()
            else:
                allowed = tuple(p.get('trace_files') or ())
            problems += L.patch_problems(files, p['change_class'], diff, allowed)
            problems += self.mode_problems(raw)
        if not problems and p['change_class'] == 'local_fix':
            funcs = p.get('trace_functions') or {}
            for f in files:
                rc, old, _ = self.git(ws, 'show', f'{base}:{f}')
                try:
                    new = L.read_in(ws, f, L.DIFF_MAX_BYTES * 8).decode('utf-8')
                except (OSError, UnicodeDecodeError) as exc:
                    problems.append(f'{f}: unreadable ({type(exc).__name__})')
                    continue
                if rc != 0:
                    problems.append(f'{f}: a local_fix may not add a file')
                    continue
                problems += [f'{f}: {x}' for x in L.local_fix_problems(old, new, funcs.get(f, []))]
        if not problems:
            meta0 = self.guard_begin(ws)
            if not meta0:
                self.git_meta_broken(cell, 'the gate (its .git tree cannot be inspected)')
                return self.count_infra(item, cell, 'gate: the clone was re-created')
            shm0 = L.shm_entries()
            argv = L.scope_argv(['bash', L.GATE_SCRIPT, ws, p['test_id'], base], runtime=L.GATE_TIMEOUT, name='gate')
            rc, out, err = self.proc(argv, L.GATE_TIMEOUT, heavy=True, env=L.scope_env())
            if not self.guard_end(ws, meta0, shm0):
                self.git_meta_broken(cell, 'the gate run')
                return self.finish_item(item, cell, 'failed', 'the gate run changed the clone\'s git administrative files')
            if rc in (L.STOPPED_RC, L.NOT_ADMITTED_RC):
                self.reset_workspace(ws)
                return self.item_update(item['item_id'], state='queued', outcome='gate: stopped or not admitted (no count)')
            if rc != 0:
                problems.append(f'devcheck-gate rc {rc} ({L.GATE_EXITS.get(rc, "a step failed")}): '
                                + L.one_line(L.redact((err or out)[-200:]), 200))
            else:
                _f2, _r2, diff2, ok2 = self.staged_diff(ws, base)
                if not ok2 or diff2 != diff:
                    problems.append('the gate changed the workspace (a check wrote files): refused')
        if problems:
            self.reset_workspace(ws)
            self.finish_item(item, cell, 'failed', '; '.join(problems))
            return
        patch_id = L.sha16(diff)
        prior = self.conn.execute('SELECT state FROM patches WHERE patch_id=?', (patch_id,)).fetchone()
        self.publish_bundle('patches', patch_id, {'patch.diff': diff, 'meta.json': json.dumps({
            'patch_id': patch_id, 'finding': item['item_id'], 'test_id': p['test_id'], 'base_commit': base, 'files': files,
            'change_class': p['change_class'], 'path_class': L.path_class(files), 'diff_sha256': L.sha(diff),
            'gate': 'checks/devcheck-gate.sh passed', 'previous_patch': p.get('previous_patch', '')}, indent=1, sort_keys=True)})
        with L.Tx(self.conn):
            if prior is not None:
                L.notice(self.conn, 'patch_repeat', patch_id, f'the run produced patch {patch_id} again (state {prior["state"]}); '
                         'the operator decides')
                self.finish_item(item, cell, 'owner', f'patch {patch_id} was already bundled ({prior["state"]})', tx=False)
            else:
                self.conn.execute("INSERT INTO patches (patch_id, item_id, base_commit, files, change_class, path_class, gate_rc,"
                                  " state, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 0, 'bundled', ?, ?)",
                                  (patch_id, item['item_id'], base, json.dumps(files), p['change_class'], L.path_class(files),
                                   L.now(), L.now()))
                # the diff was written by a model (agy): its review item is at least model-tainted
                self.new_item('immune', 'patch', (patch_id,), {'subject': 'patch', 'patch_id': patch_id},
                              derive_taint(item['taint'], 'model'), origin=item['item_id'])
                # the finding is counted done once, when its patch leaves review (count=False here)
                self.finish_item(item, cell, 'done', f'patch {patch_id} bundled', tx=False, count=False)
        self.reset_workspace(ws)

    def gate_proposal(self, item, cell):
        """The run may change only genome/<program>.sym (plus root control files); the change must pass the protected-line
        rule against the release the draft started from, the placement rule and bin/symblic check."""
        ws, p = cell['workspace'], json.loads(item['payload'])
        rel = f'genome/{p["program"]}.sym'
        base_release = p.get('base_release')
        if base_release != self.release:
            self.reset_workspace(ws)
            self.finish_item(item, cell, 'abstained', f'release changed during the draft ({base_release} -> {self.release})')
            return
        files, _raw, _diff, ok = self.staged_diff(ws, p.get('base_commit') or 'HEAD')
        problems = [] if ok else ['git could not diff against the draft base']
        if p['program'] in L.SELFDEV_PROTECTED:
            problems.append(f'{p["program"]} is protected from selfdev')
        if ok and files != [rel]:
            problems.append('the run must change exactly ' + rel + ', it changed: ' + ', '.join(files[:5] or ['nothing']))
        new = old = ''
        if not problems:
            try:
                new = L.read_in(ws, rel, L.GENOME_MAX_BYTES).decode('utf-8')
                with open(os.path.join(self.rdir, rel), encoding='utf-8') as handle:
                    old = handle.read(L.GENOME_MAX_BYTES + 1)
                rc, mode, _ = self.git(ws, 'ls-files', '-s', '--', rel)
                if rc != 0 or not mode.startswith('100644 '):
                    problems.append(f'{rel} must stay a regular file of mode 100644')
            except (OSError, UnicodeDecodeError) as exc:
                problems.append(f'cannot read the proposal: {exc}')
        if not problems:
            problems += L.genome_protected_problems(old, new) + L.genome_placement_problems(new)
        if not problems:
            tmp = os.path.join(L.BUNDLES, 'proposals', f'check-{L.sha16(item["item_id"], new)}.sym')
            L.write_atomic(tmp, new)
            rc, out, err = self.proc([L.SYMBLIC, 'check', tmp], L.GIT_TIMEOUT, env=L.child_env())
            os.remove(tmp)
            if rc != 0:
                problems.append('bin/symblic check failed: ' + L.one_line((out + err)[-200:], 200))
        self.reset_workspace(ws)
        if problems:
            self.finish_item(item, cell, 'failed', '; '.join(problems))
            return
        pid = L.sha16(item['item_id'], L.sha(new))
        import difflib
        diff = ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), f'a/{rel}', f'b/{rel}'))
        self.publish_bundle('proposals', pid, {f'{p["program"]}.sym': new, 'proposal.diff': diff, 'meta.json': json.dumps(
            {'proposal_id': pid, 'program': p['program'], 'lesson': p['lesson'], 'lesson_id': p['lesson_id'],
             'base_release': self.release, 'lesson_item': item['item_id'], 'new_sha256': L.sha(new)}, indent=1, sort_keys=True)})
        with L.Tx(self.conn):
            self.conn.execute("INSERT OR IGNORE INTO proposals (proposal_id, item_id, program, base_release, base_sha256, new_sha256,"
                              " state, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'bundled', ?, ?)",
                              (pid, item['item_id'], p['program'], self.release, L.sha(old), L.sha(new), L.now(), L.now()))
            self.new_item('immune', 'proposal', (pid,), {'subject': 'proposal', 'proposal_id': pid},
                          derive_taint(item['taint'], 'model'), origin=item['item_id'])
            self.finish_item(item, cell, 'done', f'proposal {pid} bundled', tx=False)

    def apply_migration(self, item, cell):
        """Apply migrations/<id>.sql (LIFE.md section 7.8), in this order: the run changed exactly that file and it is a
        regular file of mode 100644 (read without following a link); the organism's physical footprint is within
        ORGANISM_MAX_BYTES; the text is written to bundles/migrations/<id>.sql BEFORE any decision (so a refused text
        survives with <id>.refused.txt beside it); an `applying` registry row with another sha256 refuses; the
        schema_migrations ledger (same id and sha256 = a crash after the organism commit: recovered as applied; another
        sha256 = refused); the full validation on a copy of the organism WITH its rows; the durable evidence (the
        migrations row 'applying'); the pre-migration backup (0600, retention first); ONE organism transaction
        (statements + its schema_migrations row) under a MIGRATION_SECONDS deadline that also stops at STOP, with STOP
        checked again immediately before COMMIT (STOP first: rolled back, the item waits; COMMIT first: recorded);
        then the registry row 'applied' or 'refused', the workspace commit and the item's end."""
        ws, p = cell['workspace'], json.loads(item['payload'])
        mid = p['migration_id']
        rel = f'migrations/{mid}.sql'
        files, raw, _diff, ok = self.staged_diff(ws, p.get('base_commit') or 'HEAD')
        if not ok or files != [rel] or self.mode_problems(raw):
            self.reset_workspace(ws)
            self.finish_item(item, cell, 'failed', f'the run must change exactly {rel} as a regular file, it changed: '
                             + ', '.join(files[:5] or ['nothing']))
            return
        try:
            sql = L.read_in(ws, rel, L.MIGRATION_MAX_BYTES).decode('utf-8')
        except (OSError, UnicodeDecodeError) as exc:
            self.reset_workspace(ws)
            self.finish_item(item, cell, 'failed', f'cannot read {rel}: {exc}')
            return
        if L.physical_bytes(L.ORGANISM) > L.ORGANISM_MAX_BYTES:
            L.notice(self.conn, 'storage', 'organism', f'organism.sqlite3 is over {L.ORGANISM_MAX_BYTES} bytes: migrations wait')
            return
        digest = L.sha(sql)
        bundle = os.path.join(L.BUNDLES, 'migrations', f'{mid}.sql')
        if not os.path.exists(bundle):
            L.write_atomic(bundle, sql)
        elif L.file_sha(bundle) != digest:
            L.write_atomic(os.path.join(L.BUNDLES, 'migrations', f'{mid}.{digest[:12]}.sql'), sql)
        prior = self.conn.execute('SELECT * FROM migrations WHERE migration_id=?', (mid,)).fetchone()
        org = sqlite3.connect(L.ORGANISM, isolation_level=None, timeout=L.SQLITE_TIMEOUT)
        problems, already, stopped = [], False, False
        try:
            done = org.execute('SELECT sha256 FROM schema_migrations WHERE migration_id=?', (mid,)).fetchone()
            if prior is not None and prior['state'] == 'applying' and prior['sha256'] != digest:
                problems.append('an earlier apply of this id recorded other text (applying row); the operator decides')
            elif done:
                already = done[0] == digest
                if not already:
                    problems.append('this migration id was already applied with other text')
            else:
                problems = L.migration_problems(sql, L.snapshot_sql(org), db_path=L.ORGANISM)
                if not problems:
                    with L.Tx(self.conn):
                        self.conn.execute('INSERT OR REPLACE INTO migrations (migration_id, item_id, sha256, state, detail, at)'
                                          " VALUES (?, ?, ?, 'applying', '', ?)", (mid, item['item_id'], digest, L.now()))
                    self.premigration_retention()
                    backup_path = os.path.join(L.BACKUPS, f'organism-before-{mid}.sqlite3')
                    backup = sqlite3.connect(backup_path)
                    try:
                        org.backup(backup)
                    finally:
                        backup.close()
                    os.chmod(backup_path, 0o600)
                    org.set_progress_handler(L.deadline_handler(L.MIGRATION_SECONDS), 10000)
                    org.execute('PRAGMA foreign_keys=ON')
                    org.execute('BEGIN IMMEDIATE')
                    try:
                        for statement in L.migration_statements(sql):
                            org.execute(statement)
                        org.execute('INSERT INTO schema_migrations (migration_id, sha256, applied_at) VALUES (?, ?, ?)',
                                    (mid, digest, L.now()))
                        if self.stopping():
                            raise InterruptedError('STOP appeared before COMMIT')
                        org.execute('COMMIT')
                    except (sqlite3.Error, InterruptedError) as exc:
                        if org.in_transaction:
                            org.execute('ROLLBACK')
                        if isinstance(exc, InterruptedError) or self.stopping():
                            stopped = True
                        else:
                            problems.append(f'apply failed and was rolled back: {exc}')
        finally:
            org.close()
        if stopped:
            with L.Tx(self.conn):
                self.conn.execute("DELETE FROM migrations WHERE migration_id=? AND state='applying'", (mid,))
                self.item_update(item['item_id'], state='queued', outcome='apply: STOP before COMMIT; rolled back (no count)')
            return
        if problems:
            L.write_atomic(os.path.join(L.BUNDLES, 'migrations', f'{mid}.refused.txt'), '\n'.join(problems) + '\n')
        else:
            self.git(ws, 'add', '--', rel)
            self.git(ws, '-c', 'user.name=life', '-c', 'user.email=life@localhost', 'commit', '-q', '-m', f'LIFE migration {mid}')
        self.reset_workspace(ws)
        with L.Tx(self.conn):
            if prior is None or prior['state'] != 'applying' or prior['sha256'] == digest:
                self.conn.execute('INSERT OR REPLACE INTO migrations (migration_id, item_id, sha256, state, detail, at) VALUES'
                                  ' (?, ?, ?, ?, ?, ?)', (mid, item['item_id'], digest, 'refused' if problems else 'applied',
                                                          L.one_line('; '.join(problems), 400), L.now()))
            if problems:
                self.finish_item(item, cell, 'failed', '; '.join(problems), tx=False)
            else:
                shaped = self.store_shape_tables()
                L.notice(self.conn, 'migration_applied', mid, f'organism.sqlite3 gained migration {mid}'
                         + (' (recovered after a crash)' if already else ' (backup taken first)')
                         + '. Tables that receive rows from LIFE (the store adapter shape): '
                         + (', '.join(shaped) or 'none') + '; every other table stays operator-filled (GAP 13).')
                self.finish_item(item, cell, 'done', f'migration {mid} applied', tx=False)

    def migration_reconcile(self):
        """The organism's schema_migrations and the registry's migrations rows must agree; every combination of
        registry state x presence in the organism x sha256 is decided here (LIFE.md section 7.8):
          organism has id, registry applied, same sha256            -> nothing
          organism has id, registry applying, same sha256           -> applied (the organism commit happened)
          organism has id, no registry row (id and sha256 well-formed) -> imported (row with no item, notice)
          organism has id, any other registry state or sha256       -> HOLD (notice migration_recovery_required)
          organism lacks id, registry applied                       -> HOLD (a restore from an older backup)
          organism lacks id, registry applying                      -> nothing (its apply item retries the SAME text)
          organism lacks id, registry refused                       -> nothing
          an organism ledger row that is not well-formed            -> HOLD
        The hold stops the database organ (no draft, no apply, no store) until the operator restores or forgets."""
        self.database_hold = False
        if not os.path.isfile(L.ORGANISM):
            return
        org = sqlite3.connect(f'file:{L.ORGANISM}?mode=ro', uri=True)
        try:
            in_org = dict(org.execute('SELECT migration_id, sha256 FROM schema_migrations').fetchall())
        finally:
            org.close()
        reg = {r['migration_id']: r for r in self.conn.execute('SELECT * FROM migrations')}

        def hold(mid, why):
            self.database_hold = True
            L.notice(self.conn, 'migration_recovery_required', mid, why + ': the database organ holds; LIFE.md section 12 '
                     'says how to recover (restore an organism backup that matches, or life-ctl.py forget-migration)')
        with L.Tx(self.conn):
            for mid, digest in in_org.items():
                row = reg.get(mid)
                if not (isinstance(mid, str) and re.fullmatch(r'[0-9]{4}_[a-z0-9_]{1,40}', mid)
                        and isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest)):
                    hold(str(mid)[:45], 'the organism ledger holds a malformed row')
                elif row is None:
                    self.conn.execute("INSERT INTO migrations (migration_id, item_id, sha256, state, detail, at) VALUES "
                                      "(?, NULL, ?, 'applied', 'imported from the organism ledger', ?)", (mid, digest, L.now()))
                    L.notice(self.conn, 'migration_imported', mid, 'organism.sqlite3 holds a migration the registry did not '
                             'record; it was imported')
                elif row['sha256'] != digest:
                    hold(mid, f'the organism applied this id with other text than the registry records ({row["state"]})')
                elif row['state'] == 'applying':
                    self.conn.execute("UPDATE migrations SET state='applied', detail='recovered: the organism commit happened' "
                                      'WHERE migration_id=?', (mid,))
                elif row['state'] != 'applied':
                    hold(mid, f'the organism applied this id but the registry calls it {row["state"]}')
            for mid, row in reg.items():
                if row['state'] == 'applied' and mid not in in_org:
                    hold(mid, 'the registry records this migration as applied but organism.sqlite3 lacks it (restored from '
                         'an older backup?)')

    def store_shape_tables(self):
        """The organism tables the store adapter writes (store_table_ok)."""
        if not os.path.isfile(L.ORGANISM):
            return []
        org = sqlite3.connect(f'file:{L.ORGANISM}?mode=ro', uri=True)
        try:
            return [t for t in self.org_tables(org) if self.store_table_ok(org, t)]
        finally:
            org.close()

    @staticmethod
    def org_tables(org):
        return [r[0] for r in org.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'org\\_%' "
                                          "ESCAPE '\\' ORDER BY name") if re.fullmatch(r'org_[a-z0-9_]{1,40}', r[0])]

    @staticmethod
    def store_table_ok(org, t):
        """A table receives knowledge rows only when its full column inventory (table_xinfo: hidden and generated
        columns included) is fact_id plus a subset of the other STORE_COLUMNS, none hidden or generated, fact_id
        declared TEXT and the table's single-column PRIMARY KEY or a single-column UNIQUE constraint or index, every
        other column declared TEXT (created_at INTEGER or TEXT), and no NOT NULL column outside those LIFE fills."""
        cols = org.execute(f'PRAGMA table_xinfo("{t}")').fetchall()      # cid, name, type, notnull, dflt, pk, hidden
        names = [c[1] for c in cols]
        if 'fact_id' not in names or not set(names) <= set(L.STORE_COLUMNS) or any(c[6] for c in cols):
            return False
        types = {c[1]: (c[2] or '').upper() for c in cols}
        if types['fact_id'] != 'TEXT' or any(types[n] not in ('TEXT', 'INTEGER' if n == 'created_at' else 'TEXT')
                                             for n in names if n != 'fact_id'):
            return False
        pk = [c[1] for c in cols if c[5]]
        unique = any(ix[2] and [c[2] for c in org.execute(f'PRAGMA index_info("{ix[1]}")')] == ['fact_id']
                     for ix in org.execute(f'PRAGMA index_list("{t}")'))
        return pk == ['fact_id'] or unique

    def store(self):
        """The store adapter: every organism table store_table_ok accepts receives the quote-verified knowledge rows
        (fact_id, source_url, claim, quote, created_at; only its own columns), in knowledge rowid order from its
        per-table mark (meta store_marks), each inserted only when its fact_id is not there yet (INSERT OR IGNORE,
        parameters bound, never built SQL text). STORE_ROWS_PER_TICK bounds the (table, row) insert ATTEMPTS of the
        whole tick across all tables, served round-robin starting at meta store_next. Each table is one organism
        transaction under a MIGRATION_SECONDS deadline that also stops at STOP, with STOP checked again before COMMIT.
        A table whose insert fails is disabled for its current schema (meta store_disabled {table: schema sha256},
        notice store_failed); its mark is kept and other tables go on. No model writes a row."""
        if self.database_hold or 'storage' in self.holds or not os.path.isfile(L.ORGANISM):
            return
        marks = json.loads(self.meta('store_marks', '{}') or '{}')
        disabled = json.loads(self.meta('store_disabled', '{}') or '{}')
        budget = L.STORE_ROWS_PER_TICK
        org = sqlite3.connect(L.ORGANISM, isolation_level=None, timeout=L.SQLITE_TIMEOUT)
        try:
            tables = [t for t in self.org_tables(org) if self.store_table_ok(org, t)]
            start = self.meta('store_next')
            if start in tables:
                tables = tables[tables.index(start):] + tables[:tables.index(start)]
            for n, t in enumerate(tables):
                if budget <= 0 or self.stopping():
                    self.set_meta('store_next', t)
                    break
                schema = L.sha(org.execute('SELECT sql FROM sqlite_master WHERE name=?', (t,)).fetchone()[0])
                if disabled.get(t) == schema:
                    continue
                cols = [r[1] for r in org.execute(f'PRAGMA table_info("{t}")')]
                if t not in marks:
                    marks[t] = 0
                    L.notice(self.conn, 'store_table', t, 'LIFE copies every quote-verified knowledge row into this table '
                             f'({", ".join(cols)})')
                rows = self.conn.execute('SELECT k.rowid AS rid, k.fact_id, s.url AS source_url, k.claim, k.quote, k.created_at '
                                         'FROM knowledge k JOIN sources s ON s.source_key=k.source_key WHERE k.rowid > ? '
                                         'ORDER BY k.rowid LIMIT ?', (marks[t], budget)).fetchall()
                if not rows:
                    continue
                budget -= len(rows)
                org.set_progress_handler(L.deadline_handler(L.MIGRATION_SECONDS), 10000)
                org.execute('BEGIN IMMEDIATE')
                try:
                    for r in rows:
                        org.execute(f'INSERT OR IGNORE INTO "{t}" ({", ".join(cols)}) VALUES ({", ".join("?" for _ in cols)})',
                                    [r[c] for c in cols])
                    if self.stopping():
                        raise InterruptedError('STOP appeared before COMMIT')
                    org.execute('COMMIT')
                except (sqlite3.Error, InterruptedError) as exc:
                    if org.in_transaction:
                        org.execute('ROLLBACK')
                    if isinstance(exc, InterruptedError) or isinstance(exc, sqlite3.OperationalError) and 'locked' in str(exc):
                        continue                         # STOP or a lock: retried later, the mark unchanged
                    disabled[t] = schema
                    L.notice(self.conn, 'store_failed', t, f'inserting knowledge rows failed ({exc}); LIFE stops writing '
                             'this table until its schema changes; other tables go on')
                    continue
                marks[t] = rows[-1]['rid']
                self.set_meta('store_next', tables[(n + 1) % len(tables)])
        finally:
            org.close()
        self.set_meta('store_marks', json.dumps(marks, sort_keys=True))
        self.set_meta('store_disabled', json.dumps(disabled, sort_keys=True))

    # ------------------------------------------------------------------ agent run starts
    def catalogue_ready(self, node):
        """agy readiness per node from bin/symblic-task catalog --json, read once per tick: nodes[].id, online (not
        false) and ready.agy (true). A catalogue that parses but names no LIFE node opens notice catalogue_shape."""
        if self.agy_ready is None:
            self.agy_ready = {}
            rc, out, _ = self.proc([L.TASK, 'catalog', '--json'], L.CATALOG_TIMEOUT, env=L.child_env())
            try:
                nodes = L.strict_json(out).get('nodes') if rc == 0 else None
            except (ValueError, AttributeError):
                nodes = None
            for n in nodes if isinstance(nodes, list) else []:
                if isinstance(n, dict) and n.get('id') in L.NODES:
                    self.agy_ready[n['id']] = n.get('online') is not False and (n.get('ready') or {}).get(L.ENGINE) is True
            if rc == 0 and not self.agy_ready:
                L.notice(self.conn, 'catalogue_shape', 'catalog', 'bin/symblic-task catalog --json answered but named no LIFE '
                         'node with a ready map; agent work waits')
        return self.agy_ready.get(node, False)

    def agent_item_blocked(self, item, ctl):
        """Why an agent-stage item cannot start now ('' = it can)."""
        p = json.loads(item['payload'])
        if item['organ'] == 'selfdev' and not ctl['selfdev']:
            return 'SELFDEV_ARMED is off'
        if item['organ'] == 'selfdev' and p.get('program') in L.SELFDEV_PROTECTED:
            return 'protected program'
        if item['taint'] in ('web', 'model') and not (item['approved'] and item['approved_sha'] == L.operative_sha(item['kind'], p)):
            return 'web-derived text waits for life-ctl approve'
        if item['organ'] == 'codebase' and not ctl['history_ok']:
            return 'CODEBASE_HISTORY_OK is missing'
        if item['organ'] == 'codebase' and self.codebase_unproven:
            return 'the codebase gate is unproven (gate_selftest)'
        if item['organ'] == 'database' and self.database_hold:
            return 'the database organ holds (migration_recovery_required)'
        if not L.agy_model():
            return 'agy model missing: control/agy-model.txt'
        return ''

    def start_agent_runs(self):
        """Start agent runs for queued agent-stage items of ACTIVE cells (a dividing cell starts none: its queued agent
        items wait for the children), at most AGENT_RUNS_LIVE_MAX live fleet-wide, one per cell, the day's budget
        re-read before every start. A start needs its node available, agy ready there, the operator's agy model
        (control/agy-model.txt), and the node idle of LIFE work for the whole last NODE_WINDOW (duty_allows with
        AGENT_RUN_KILL_SECONDS = NODE_BUSY_MAX), so one run can never push a node past its duty cycle. After a start
        every governor input is read again before anything else is placed (refresh_available(force=True))."""
        live = self.conn.execute("SELECT COUNT(*) FROM runs WHERE state IN ('submitting','live','submit_unknown')").fetchone()[0]
        if live >= L.AGENT_RUNS_LIVE_MAX:
            return
        ctl = L.control_state()
        rows = self.conn.execute(
            "SELECT i.*, c.node AS c_node, c.workspace AS c_ws FROM items i JOIN cells c ON c.cell_id=i.cell_id"
            " WHERE i.state='queued' AND c.state='active' AND ((i.organ='codebase' AND i.stage='patch')"
            " OR (i.organ='selfdev' AND i.stage='draft') OR (i.organ='database' AND i.stage='draft'))"
            ' ORDER BY i.priority DESC, i.updated_at, i.item_id').fetchall()
        avail = {n for n, _ in self.available}
        started_cells = set()
        for item in rows:
            if live >= L.AGENT_RUNS_LIVE_MAX or item['cell_id'] in started_cells or self.workspace_busy(item['cell_id']):
                continue
            if L.budget_row(self.conn, self.day)['agent_runs'] + 1 > L.AGENT_RUNS_PER_DAY:
                L.notice(self.conn, 'budget', 'agent_runs ' + self.day, 'the daily agent-run budget is spent')
                return
            if not self.can_start(L.START_STAGE_SECONDS) or not self.may_admit():
                return
            why = self.agent_item_blocked(item, ctl)
            if why:
                if 'approve' in why:
                    L.notice(self.conn, 'approve_needed', item['item_id'], f'{item["organ"]} {item["kind"]} from web or model '
                             'text waits: read it with life-ctl.py show ' + item['item_id'] + ', then life-ctl.py approve it')
                elif 'HISTORY' in why:
                    L.notice(self.conn, 'tracked_private_data', 'codebase', 'codebase agent runs wait: every agent checkout on '
                             'a worker node is a full worktree of the branch, so the tracked .backups/ files (the private library '
                             'database among them) are plain files in the agent\'s folder and the whole history is in the '
                             'worker node\'s bare mirror. Read LIFE.md section 18 GAP 11, then create control/CODEBASE_HISTORY_OK '
                             'only if you accept that.')
                elif 'protected' in why:
                    self.finish_item(item, self.cell(item['cell_id']), 'failed', 'a lesson may not target a protected program')
                elif 'agy model' in why:
                    L.notice(self.conn, 'agy_model', 'agy-model.txt', 'agent runs wait: write the exact agy model id LIFE '
                             'may use (one line, a model `agy models` lists) into control/agy-model.txt; DECISIONS.md line 11')
                continue
            if item['c_node'] not in avail or not item['c_ws'] or not os.path.isdir(os.path.join(item['c_ws'], '.git')):
                continue
            if not self.duty_allows(item['c_node'], L.AGENT_RUN_KILL_SECONDS):
                continue
            if not self.catalogue_ready(item['c_node']):
                L.notice(self.conn, 'agy_not_ready', item['c_node'], f'agy is not ready on {item["c_node"]}; LIFE agent work '
                         'for cells on that node waits (it never migrates to the host)')
                continue
            self.begin_stage(L.START_STAGE_SECONDS)
            try:
                started = self.guard(item['item_id'], lambda item=item: self.start_run(item))
            finally:
                self.end_stage()
            if started:
                live += 1
                started_cells.add(item['cell_id'])
                self.refresh_available(force=True)
                avail = {n for n, _ in self.available}

    def start_run(self, item):
        """Render, record and submit one agent run (LIFE.md section 7.9). Returns True when a run may exist now."""
        organ, ws, p = item['organ'], item['c_ws'], json.loads(item['payload'])
        cell = self.cell(item['cell_id'])
        values = {'ws': ws, 'kit': L.KIT}
        text = ''
        if organ == 'codebase':
            base = self.refresh_clone(ws, p.get('base_commit') or None)
            if base is None:
                return False
            if not base:
                L.notice(self.conn, 'workspace', ws, 'the codebase clone could not be brought to its base commit')
                self.count_infra(item, cell, 'start: the codebase clone could not be refreshed')
                return False
            p['base_commit'] = base
            if p['change_class'] == 'local_fix':
                files = [f for f in p.get('trace_files') or [] if os.path.isfile(os.path.join(ws, f))]
                funcs = [fn for f in files for fn in (p.get('trace_functions') or {}).get(f, [])]
                if not files or not funcs:
                    L.notice(self.conn, 'finding_owner', item['item_id'], 'local_fix without a named source file and function')
                    self.finish_item(item, cell, 'owner', 'local_fix but the failure names no source file and function LIFE may change')
                    return False
                p['trace_files'] = files
                scope = L.local_fix_scope(funcs, files)
            elif p['change_class'] == 'test_only':
                module = L.resolve_test_module(ws, p['test_id'])
                if not module:
                    L.notice(self.conn, 'finding_owner', item['item_id'], f'{p["test_id"]} does not resolve to a file in the clone')
                    self.finish_item(item, cell, 'owner', 'test_only but the test id names no file')
                    return False
                scope = 'the file ' + module
            else:
                scope = L.SCOPES[p['change_class']]
            text = p['finding_text']
            values.update(test_id=p['test_id'], finding_id=item['item_id'].split(':')[1], scope=scope,
                          review_note=L.lint_safe(p.get('review_note') or 'none', 240) or 'none')
        elif organ == 'selfdev':
            self.reset_workspace(ws)
            lid = item['item_id'].split(':')[1]
            p.update(lesson_id=lid, base_release=self.release, base_commit=self.sync_selfdev(ws))
            values.update(lesson_id=lid, program=p['program'], lesson=L.lint_safe(p['lesson'], L.LESSON_MAX_CHARS))
        else:
            self.reset_workspace(ws)
            if not p.get('migration_id'):
                p['migration_id'] = self.next_migration_id(p['request'])
                if not p['migration_id']:
                    L.notice(self.conn, 'migration_numbers', 'database', f'migration numbers reached {L.MIGRATION_NUMBER_MAX}')
                    return False
            p['snapshot_sha'], p['base_commit'] = self.write_snapshot(ws)
            values.update(migration_id=p['migration_id'], request=L.lint_safe(p['request'], L.REQUEST_MAX_CHARS),
                          snapshot_sha=p['snapshot_sha'])
        if not re.fullmatch(r'[0-9a-f]{40}', p.get('base_commit') or ''):
            L.notice(self.conn, 'workspace', ws, 'the workspace has no base commit')
            self.count_infra(item, cell, 'start: the workspace has no base commit')
            return False
        try:
            for limit in L.FINDING_CUTS:                  # a long finding text is cut until every statement fits
                if organ == 'codebase':
                    values['finding_text'] = L.lint_safe(text, limit)
                try:
                    lines, policy, policy_sha = L.render_run(self.rdir, organ, values)
                    break
                except ValueError as exc:
                    if organ != 'codebase' or 'longer than' not in str(exc) or limit == L.FINDING_CUTS[-1]:
                        raise
            flags = L.policy_flags(policy)
        except (ValueError, KeyError) as exc:
            # a deterministic render failure: the item goes to the operator, no budget is charged, nothing retries it
            with L.Tx(self.conn):
                L.notice(self.conn, 'render', item['item_id'], str(exc))
                self.finish_item(item, cell, 'owner', f'cannot render a lint-clean run: {exc}', tx=False)
            return False
        request_id = L.request_id_for(item['cell_id'], item['item_id'], item['attempts'] + 1)
        run_id = L.autogen_run_id(request_id)
        model = L.agy_model()
        snap = os.path.join(L.RUNS_DIR, request_id)
        os.makedirs(snap, mode=0o700, exist_ok=True)
        statements = '\n'.join(lines) + '\n'
        L.write_atomic(os.path.join(snap, 'statements.txt'), statements)
        L.write_atomic(os.path.join(snap, 'policy.json'), json.dumps(policy, indent=1, sort_keys=True))
        # the versioned manifest a re-send is rebuilt from (never from the current configuration)
        L.write_atomic(os.path.join(snap, 'manifest.json'), json.dumps({
            'version': 1, 'request_id': request_id, 'run_id': run_id, 'item_id': item['item_id'], 'cell_id': item['cell_id'],
            'workspace': ws, 'node': item['c_node'], 'engine': L.ENGINE, 'model': model, 'effort': L.AGY_EFFORT,
            'base_commit': p['base_commit'], 'release': self.release, 'policy_sha256_normalized': policy_sha,
            'statements_sha256': L.file_sha(os.path.join(snap, 'statements.txt')),
            'policy_sha256': L.file_sha(os.path.join(snap, 'policy.json'))}, indent=1, sort_keys=True, allow_nan=False))
        with L.Tx(self.conn):
            self.conn.execute("INSERT OR REPLACE INTO runs (request_id, run_id, cell_id, item_id, organ, workspace, node, engine,"
                              " policy_sha256, release, base_commit, statements_sha256, model, effort, state, submitted_at)"
                              " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'submitting', ?)",
                              (request_id, run_id, item['cell_id'], item['item_id'], organ, ws, item['c_node'], L.ENGINE,
                               policy_sha, self.release, p['base_commit'], L.sha(statements), model, L.AGY_EFFORT, L.now()))
            self.item_update(item['item_id'], state='running', payload=json.dumps(p, sort_keys=True))
            L.budget_add(self.conn, 'agent_runs', day=self.day)
            L.metric_add(self.conn, organ, 'agent_runs', day=self.day)
        if not self.may_admit():
            with L.Tx(self.conn):
                self.conn.execute("UPDATE runs SET state='not_submitted', ended_at=?, detail='stopped before submit' WHERE "
                                  'request_id=?', (L.now(), request_id))
                self.item_update(item['item_id'], state='queued', attempts=item['attempts'] + 1, outcome='not submitted: stopped')
            return False
        argv = [L.TASK, 'start', '--lines', os.path.join(snap, 'statements.txt'), '--root', ws, '--cwd', ws,
                '--node', item['c_node'], '--engine', L.ENGINE, '--model', model, '--effort', L.AGY_EFFORT,
                '--id', request_id, '--json'] + flags
        rc, out, err = self.procs.run(argv, L.START_TIMEOUT, env=L.child_env(), tracked=False)
        # rc 0: submitted (the next poll confirms the run and its identity). Otherwise the expected run id is asked:
        # a run -> submitting (confirmed by the poll); 404 after an HTTP 4xx refusal -> not_submitted (a refused
        # start); anything else (a timeout, a 5xx, no answer) -> submit_unknown, which the polls resolve by re-sending
        # the IDENTICAL start (never a new request id while the first may exist).
        state = 'submitting'
        if rc != 0:
            row = self.api_run(run_id)
            state = 'submitting' if row else 'not_submitted' if row == {} and REFUSED_4XX_RX.search(err) else 'submit_unknown'
        with L.Tx(self.conn):
            self.conn.execute('UPDATE runs SET state=?, detail=? WHERE request_id=?', (state, L.one_line(err[-300:], 300), request_id))
            if state == 'not_submitted':
                self.conn.execute('UPDATE runs SET ended_at=? WHERE request_id=?', (L.now(), request_id))
                if COOLDOWN_RX.search(err):
                    L.notice(self.conn, 'agy_quota', item['c_node'], f'agy refused the start for its model\'s quota or '
                             f'cooldown ({model}); the item waits as infrastructure: ' + L.one_line(err[-200:], 200))
                    self.item_update(item['item_id'], attempts=item['attempts'] + 1)
                    self.count_infra(self.item(item['item_id']), cell, 'agy quota or cooldown', tx=False)
                else:
                    self.start_refused(self.item(item['item_id']), err)
        if state == 'not_submitted':
            return False
        L.log(f'run {request_id} -> {run_id} on {item["c_node"]} (start rc {rc}; {state})')
        return True

    def sync_selfdev(self, ws):
        """genome/ and genome-base/ of the selfdev workspace both equal the active release, committed; returns the commit."""
        changed = False
        for sub in ('genome', 'genome-base'):
            os.makedirs(os.path.join(ws, sub), exist_ok=True)
            for name in sorted(os.listdir(os.path.join(self.rdir, 'genome'))):
                src, dst = os.path.join(self.rdir, 'genome', name), os.path.join(ws, sub, name)
                if not os.path.exists(dst) or L.file_sha(dst) != L.file_sha(src):
                    shutil.copyfile(src, dst)
                    changed = True
        if changed:
            self.git(ws, 'add', '-A', '--', 'genome', 'genome-base')
            self.git(ws, '-c', 'user.name=life', '-c', 'user.email=life@localhost', 'commit', '-q', '-m',
                     f'LIFE genome = release {self.release}')
        rc, out, _ = self.git(ws, 'rev-parse', 'HEAD')
        return out.strip() if rc == 0 else ''

    def write_snapshot(self, ws):
        """schema-snapshot.sql = the organism's CREATE statements in creation order, sqlite_* excluded (snapshot_sql), and
        MIGRATION-RULES.txt = life_common.MIGRATION_RULES, both committed; returns (the snapshot's sha256, the commit)."""
        org = sqlite3.connect(f'file:{L.ORGANISM}?mode=ro', uri=True)
        try:
            text = L.snapshot_sql(org)
        finally:
            org.close()
        changed = False
        for name, body in (('schema-snapshot.sql', text), ('MIGRATION-RULES.txt', L.MIGRATION_RULES)):
            path = os.path.join(ws, name)
            if not os.path.exists(path) or open(path, encoding='utf-8').read() != body:
                L.write_atomic(path, body, 0o644)
                self.git(ws, 'add', '--', name)
                changed = True
        if changed:
            self.git(ws, '-c', 'user.name=life', '-c', 'user.email=life@localhost', 'commit', '-q', '-m', 'LIFE schema snapshot')
        rc, out, _ = self.git(ws, 'rev-parse', 'HEAD')
        return L.sha(text), (out.strip() if rc == 0 else '')   # L.sha of one part = sha256 of the file's UTF-8 bytes

    def next_migration_id(self, request):
        """<4-digit number>_<slug>: number = 1 + the highest number ever allocated: the allocation journal
        STATE/migration-numbers.txt (append-only, fsynced BEFORE the number is used anywhere, outside both databases so
        no restore can lower it), the meta high-water mark, the migrations table (applied, applying, refused), every
        database item's payload, the organism's own ledger and the bundle file names (the tick is the only writer,
        under the lock); allocated once per request and kept through every retry. slug = the request's lowercase ASCII
        words joined by _, cut to 30 characters, 'table' when empty. '' past MIGRATION_NUMBER_MAX."""
        used = [int(self.meta('migration_high', '0') or 0)]
        try:
            with open(L.MIGRATION_JOURNAL, encoding='ascii') as handle:
                used += [int(ln.split()[0]) for ln in handle if re.match(r'^\d{1,4} ', ln)]
        except FileNotFoundError:
            pass
        mig_dir = os.path.join(L.BUNDLES, 'migrations')
        used += [int(n[:4]) for n in (os.listdir(mig_dir) if os.path.isdir(mig_dir) else []) if re.match(r'^\d{4}_', n)]
        used += [int(r[0][:4]) for r in self.conn.execute('SELECT migration_id FROM migrations') if re.match(r'^\d{4}_', r[0])]
        for r in self.conn.execute("SELECT payload FROM items WHERE organ='database'"):
            mid = json.loads(r['payload']).get('migration_id') or ''
            if re.match(r'^\d{4}_', mid):
                used.append(int(mid[:4]))
        if os.path.isfile(L.ORGANISM):
            org = sqlite3.connect(f'file:{L.ORGANISM}?mode=ro', uri=True)
            try:
                used += [int(r[0][:4]) for r in org.execute('SELECT migration_id FROM schema_migrations') if re.match(r'^\d{4}_', r[0])]
            finally:
                org.close()
        number = max(used) + 1
        if number > L.MIGRATION_NUMBER_MAX:
            return ''
        slug = '_'.join(SLUG_RX.findall(request.lower()))[:30].strip('_') or 'table'
        fd = os.open(L.MIGRATION_JOURNAL, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        try:
            os.write(fd, f'{number} {number:04d}_{slug} {L.now()}\n'.encode('ascii'))
            os.fsync(fd)
        finally:
            os.close(fd)
        self.set_meta('migration_high', str(number))
        return f'{number:04d}_{slug}'

    # ------------------------------------------------------------------ item endings and counters
    def finish_item(self, item, cell, state, outcome, tx=True, count=True):
        """End an item (done/abstained/failed/owner). Only these TERMINAL endings touch the cell's failure streak:
        done and abstained reset it, failed adds one, owner leaves it. The cell's recent-endings window and the day's
        metrics are updated (count=False: the gate defers a finding's count until its patch leaves review). A command
        item that ends failed or owner marks its command failed with a notice; a finding that ends failed opens notice
        finding_failed (the watched-test dedup rule reads it)."""
        def body():
            self.item_update(item['item_id'], state=state, outcome=L.one_line(outcome, 400))
            if count:
                self.count_ending(item['organ'], item['cell_id'], state)
            if item['kind'] == 'command' and state in ('failed', 'owner'):
                command_id = json.loads(item['payload']).get('command_id')
                self.conn.execute("UPDATE commands SET state='failed', updated_at=? WHERE command_id=?", (L.now(), command_id))
                L.notice(self.conn, 'command_failed', command_id, 'the classifier could not route this command; re-send it '
                         'or act on it by hand: ' + L.one_line(outcome, 300))
            if item['kind'] == 'finding' and state == 'failed':
                L.notice(self.conn, 'finding_failed', item['item_id'], 'the finding ended failed: ' + L.one_line(outcome, 300))
        if tx:
            with L.Tx(self.conn):
                body()
        else:
            body()

    def count_ending(self, organ, cid, state):
        letter = {'done': 'd', 'abstained': 'a', 'failed': 'f', 'owner': 'o'}[state]
        if cid:
            if state in ('done', 'abstained'):
                self.conn.execute('UPDATE cells SET failures_in_a_row=0, items_done=items_done+?, recent=substr(recent || ?, -20)'
                                  ' WHERE cell_id=?', (1 if state == 'done' else 0, letter, cid))
            elif state == 'failed':
                self.conn.execute('UPDATE cells SET failures_in_a_row=failures_in_a_row+1, recent=substr(recent || ?, -20)'
                                  ' WHERE cell_id=?', (letter, cid))
            else:
                self.conn.execute('UPDATE cells SET recent=substr(recent || ?, -20) WHERE cell_id=?', (letter, cid))
        if state != 'owner':
            L.metric_add(self.conn, organ, {'done': 'items_done', 'abstained': 'items_abstained',
                                            'failed': 'items_failed'}[state], day=self.day)

    # ------------------------------------------------------------------ 13. dispatch
    def label(self, row):
        """The routing label of an item (its words decide which sibling cell gets it): command -> the command text;
        question -> the question; source -> the URL; finding -> the test id and its finding_text up to the first ': ' or
        80 characters, whichever is shorter; lesson -> the lesson; request -> the request; experiment -> the seed text;
        patch and proposal -> their origin's label."""
        p = json.loads(row['payload'])
        kind = row['kind']
        if kind == 'command':
            cmd = self.conn.execute('SELECT text FROM commands WHERE command_id=?', (p.get('command_id'),)).fetchone()
            text = cmd['text'] if cmd else ''
        elif kind == 'finding':
            text = p.get('test_id', '') + ' ' + (p.get('finding_text') or '').split(': ')[0][:80]
        elif kind in ('patch', 'proposal'):
            origin = self.item(row['origin']) if row['origin'] else None
            text = self.label(origin) if origin is not None and origin['kind'] not in ('patch', 'proposal') else ''
        else:
            text = p.get('question') or p.get('url') or p.get('lesson') or p.get('request') or p.get('seed_text') or ''
        return L.one_line(text or row['item_id'], 120)

    def dispatch(self):
        """Queued items of a quarantined or retired cell (not at a WORKSPACE_STAGES stage, which needs that cell's
        workspace) lose their cell and wait unassigned while their organ has no active cell. Every unassigned queued
        item then goes to the active cell of its organ whose focus shares the most routing words (4+ letters) with the
        item's label, at least one; otherwise, and on ties, the cell with the fewest queued-or-running items, then the
        lowest cell id. A slot-stage item never goes to a cell whose node has no installed rung of its program (a
        readable inventory says so; an unread one never blocks)."""
        q = ','.join('?' * len(L.WORKSPACE_STAGES))
        self.conn.execute(f"UPDATE items SET cell_id=NULL WHERE state='queued' AND stage NOT IN ({q}) AND cell_id IN"
                          " (SELECT cell_id FROM cells WHERE state IN ('retired','quarantined'))", L.WORKSPACE_STAGES)
        for item in self.conn.execute("SELECT * FROM items WHERE cell_id IS NULL AND state='queued' ORDER BY priority DESC,"
                                      ' created_at, item_id').fetchall():
            cells = self.conn.execute(
                "SELECT c.cell_id, c.focus, c.node, (SELECT COUNT(*) FROM items i WHERE i.cell_id=c.cell_id AND i.state IN"
                " ('queued','running')) AS q FROM cells c WHERE c.organ=? AND c.state='active'", (item['organ'],)).fetchall()
            if (item['organ'], item['stage']) in L.SLOT_STAGES and item['stage'] != 'bench':
                ladder = self.ladders.get(self.program_for(item)) or []
                cells = [c for c in cells if any(self.model_installed(c['node'], m) for m in ladder)] or []
            if not cells:
                continue
            words = L.words(self.label(item))
            best = min(cells, key=lambda c: (-len(words & L.words(c['focus'])), c['q'], c['cell_id']))
            self.conn.execute('UPDATE items SET cell_id=? WHERE item_id=?', (best['cell_id'], item['item_id']))

    # ------------------------------------------------------------------ 15. lifecycle
    def workable(self, item, ctl, bench_ok):
        if item['organ'] == 'compute' and item['stage'] in ('propose', 'rank') and not bench_ok:
            return False
        if (item['organ'], item['stage']) in L.AGENT_STAGES and self.agent_item_blocked(item, ctl):
            return False
        return True

    def lifecycle(self):
        ctl = L.control_state()
        bench_ok = bool(self.benchmarks())
        with L.Tx(self.conn):
            for cell in self.conn.execute("SELECT * FROM cells WHERE state IN ('active','dividing')").fetchall():
                queued = self.conn.execute("SELECT * FROM items WHERE cell_id=? AND state='queued'", (cell['cell_id'],)).fetchall()
                work = sum(1 for i in queued if self.workable(i, ctl, bench_ok))
                busy = self.conn.execute("SELECT COUNT(*) FROM items WHERE cell_id=? AND state='running'", (cell['cell_id'],)).fetchone()[0]
                limit = self.organs['organs'][cell['organ']]['divide_backlog']
                idle = not queued and busy == 0
                self.conn.execute('UPDATE cells SET backlog_ticks=?, idle_since=? WHERE cell_id=?',
                                  (cell['backlog_ticks'] + 1 if work >= limit else 0,
                                   (cell['idle_since'] or self.now) if idle else None, cell['cell_id']))
            for cell in self.conn.execute("SELECT * FROM cells WHERE state='active'").fetchall():
                siblings = self.conn.execute("SELECT * FROM cells WHERE organ=? AND state='active' AND cell_id != ?",
                                             (cell['organ'], cell['cell_id'])).fetchall()
                if cell['failures_in_a_row'] >= L.QUARANTINE_FAILURES:
                    self.conn.execute("UPDATE cells SET state='quarantined' WHERE cell_id=?", (cell['cell_id'],))
                    self.event(cell['cell_id'], 'quarantined', f'{cell["failures_in_a_row"]} failed items in a row')
                    L.notice(self.conn, 'quarantine', cell['cell_id'], f'{cell["failures_in_a_row"]} failed items in a row; '
                             + ('its queued items move to its siblings' if siblings else 'it was the only active cell of its '
                                f'organ: its items wait, and LIFE releases it automatically after {L.LAST_CELL_AUTO_RELEASE} s at '
                                'the top model rung (at most once a week)')
                             + '. Release now with life-ctl.py release-cell ' + cell['cell_id'])
                elif (cell['idle_since'] and self.now - cell['idle_since'] >= L.APOPTOSIS_IDLE_SECONDS and siblings
                      and not self.workspace_busy(cell['cell_id'])
                      and not self.conn.execute("SELECT 1 FROM items WHERE cell_id=? AND state IN ('queued','running')",
                                                (cell['cell_id'],)).fetchone()):
                    self.conn.execute("UPDATE cells SET state='retired', ended_at=?, end_reason='idle' WHERE cell_id=?",
                                      (L.now(), cell['cell_id']))
                    self.event(cell['cell_id'], 'retired', f'idle since {cell["idle_since"]}; {len(siblings)} sibling(s) remain')
                recent = cell['recent'] or ''
                if len(recent) >= L.ABSTAIN_WINDOW and recent[-L.ABSTAIN_WINDOW:].count('a') >= L.ABSTAIN_RATE * L.ABSTAIN_WINDOW:
                    L.notice(self.conn, 'abstain_rate', cell['cell_id'], f'{int(L.ABSTAIN_RATE * 100)} % or more of the last '
                             f'{L.ABSTAIN_WINDOW} items abstained: the cell may be broken rather than right')
            self.auto_release()
        self.division_progress()
        self.workspace_sweep()
        self.remove_retired_workspace()
        self.move_offline_cells()
        self.store()
        self.settle_questions()
        self.self_questions(ctl)
        self.division_start()

    def settle_questions(self):
        """A question whose usable links reached QUESTION_SOURCE_LIMIT waits (no research run) while any linked source
        is still pending; once none is pending it is done when its FETCHED links still reach the limit, else it is
        researched again (its found count is the fetched one). So pending links reserve room but never finish a
        question by themselves."""
        for item in self.conn.execute("SELECT * FROM items WHERE organ='learning' AND state='queued'").fetchall():
            p = json.loads(item['payload'])
            if p.get('found', 0) < L.QUESTION_SOURCE_LIMIT:
                continue
            counts = dict(self.conn.execute("SELECT s.fetch_state, COUNT(*) FROM question_sources qs JOIN sources s ON "
                                            "s.source_key=qs.source_key WHERE qs.question_id=? GROUP BY s.fetch_state",
                                            (item['item_id'],)).fetchall())
            if counts.get('pending'):
                continue
            with L.Tx(self.conn):
                p['found'] = min(counts.get('fetched', 0), L.QUESTION_SOURCE_LIMIT)
                self.item_update(item['item_id'], payload=json.dumps(p, sort_keys=True))
                if p['found'] >= L.QUESTION_SOURCE_LIMIT:
                    self.finish_item(self.item(item['item_id']), self.cell(item['cell_id']) if item['cell_id'] else None,
                                     'done', f'{p["found"]} fetched sources', tx=False)

    def auto_release(self):
        """An organ's ONLY live cell, quarantined for LAST_CELL_AUTO_RELEASE seconds, is released with every program at
        its top rung, at most once per cell in any rolling AUTO_RELEASE_WINDOW (counted from its last automatic release;
        an operator release does not reset it)."""
        for cell in self.conn.execute("SELECT * FROM cells WHERE state='quarantined'").fetchall():
            if len(L.live_cells(self.conn, organ=cell['organ'])) != 1:
                continue
            last_q = self.conn.execute("SELECT MAX(at) FROM cell_events WHERE cell_id=? AND event='quarantined'",
                                       (cell['cell_id'],)).fetchone()[0]
            last_auto = self.conn.execute("SELECT MAX(at) FROM cell_events WHERE cell_id=? AND event='released' AND detail LIKE "
                                          "'auto%'", (cell['cell_id'],)).fetchone()[0]
            if not last_q or self.now - last_q < L.LAST_CELL_AUTO_RELEASE or (last_auto and self.now - last_auto < L.AUTO_RELEASE_WINDOW):
                continue
            self.conn.execute("UPDATE cells SET state='active', failures_in_a_row=0 WHERE cell_id=?", (cell['cell_id'],))
            for program, ladder in self.ladders.items():
                self.conn.execute('INSERT OR REPLACE INTO cell_programs (cell_id, program, rung, window, rung_up_at) VALUES '
                                  '(?, ?, ?, ?, ?)', (cell['cell_id'], program, len(ladder) - 1, '', self.now))
            self.event(cell['cell_id'], 'released', 'auto: the only live cell of its organ, at the top rung')
            L.notice(self.conn, 'auto_released', cell['cell_id'], 'released automatically at the top model rung; the next '
                     f'automatic release can come no sooner than {L.AUTO_RELEASE_WINDOW} s from now')

    def workspace_sweep(self):
        """One active or dividing agent cell per tick whose workspace is missing gets it re-created (CLONE_TIMEOUT).
        After WORKSPACE_FAILURES_MAX failures since its last workspace_made or release, the cell retires (end_reason
        workspace; its gate/apply items fail, its other queued items return to the organ), except the organ's last live
        cell, which is quarantined instead (life-ctl release-cell makes the sweep try again)."""
        if not self.can_start(L.CLONE_TIMEOUT) or not self.may_admit():
            return
        for cell in self.conn.execute("SELECT * FROM cells WHERE state IN ('active','dividing') AND workspace IS NOT NULL"
                                      ' ORDER BY cell_id').fetchall():
            if os.path.isdir(os.path.join(cell['workspace'], '.git')):
                if L.git_admin_problems(cell['workspace']) and not self.workspace_busy(cell['cell_id']):
                    self.git_meta_broken(cell, 'a failed git administrative check')
                continue
            model = self.conn.execute('SELECT workspace FROM cells WHERE organ=? AND workspace IS NOT NULL AND cell_id != ? AND'
                                      " state IN ('active','dividing','quarantined') ORDER BY depth, cell_id",
                                      (cell['organ'], cell['cell_id'])).fetchone()
            source = model['workspace'] if model and os.path.isdir(os.path.join(model['workspace'], '.git')) else \
                f'{L.PROJECTS}/life-{cell["organ"]}-0-00000000'
            if cell['organ'] != 'codebase' and not os.path.isdir(os.path.join(source, '.git')):
                source = ''                                  # no trusted source: build_workspace builds it from nothing
            why = self.make_workspace(cell['organ'], cell['workspace'], source)
            if why == NOT_STARTED:
                return
            with L.Tx(self.conn):
                if not why:
                    self.event(cell['cell_id'], 'workspace_made', cell['workspace'])
                    return
                self.event(cell['cell_id'], 'workspace_failed', why)
                since = self.conn.execute("SELECT MAX(at) FROM cell_events WHERE cell_id=? AND event IN ('workspace_made',"
                                          "'released','born')", (cell['cell_id'],)).fetchone()[0] or 0
                n = self.conn.execute("SELECT COUNT(*) FROM cell_events WHERE cell_id=? AND event='workspace_failed' AND at >= ?",
                                      (cell['cell_id'], since)).fetchone()[0]
                if n >= L.WORKSPACE_FAILURES_MAX:
                    if len(L.live_cells(self.conn, organ=cell['organ'])) <= 1:
                        self.conn.execute("UPDATE cells SET state='quarantined' WHERE cell_id=?", (cell['cell_id'],))
                        self.event(cell['cell_id'], 'quarantined', 'workspace unavailable')
                        L.notice(self.conn, 'quarantine', cell['cell_id'], f'its workspace could not be re-created {n} times; '
                                 'as its organ\'s last cell it is quarantined, not retired. Fix the cause, then life-ctl.py '
                                 'release-cell ' + cell['cell_id'])
                    else:
                        self.conn.execute("UPDATE cells SET state='retired', ended_at=?, end_reason='workspace' WHERE cell_id=?",
                                          (L.now(), cell['cell_id']))
                        for it in self.conn.execute("SELECT * FROM items WHERE cell_id=? AND state='queued' AND stage IN "
                                                    "('gate','apply')", (cell['cell_id'],)).fetchall():
                            self.finish_item(it, cell, 'failed', 'its cell\'s workspace was lost', tx=False)
                        self.event(cell['cell_id'], 'retired', f'workspace could not be created {n} times')
                L.notice(self.conn, 'workspace', cell['workspace'], f'could not create the workspace ({n}): {why}')
            return

    def remove_retired_workspace(self):
        """One retired codebase cell per tick whose workspace is not busy and has no unfinished item loses its clone (a
        full checkout) and its <workspace>.agents sibling (hub checkouts of its runs, removed FIRST so no worktree is
        left pointing into a deleted .git); STATE/retired/<cell>.json records the last commit and the time. Selfdev and
        database workspaces are kept (they are small and hold the organism's own history)."""
        for cell in self.conn.execute("SELECT * FROM cells WHERE state='retired' AND organ='codebase' AND workspace IS NOT NULL"
                                      ' ORDER BY ended_at').fetchall():
            ws = cell['workspace']
            if not os.path.isdir(ws) or self.workspace_busy(cell['cell_id']) or self.conn.execute(
                    "SELECT 1 FROM items WHERE cell_id=? AND state IN ('queued','running')", (cell['cell_id'],)).fetchone():
                continue
            rc, out, _ = self.git(ws, 'rev-parse', 'HEAD')
            L.write_atomic(os.path.join(L.RETIRED, f'{cell["cell_id"]}.json'), json.dumps(
                {'cell_id': cell['cell_id'], 'workspace': ws, 'head': out.strip() if rc == 0 else '', 'removed_at': L.now()}))
            if ws.startswith(f'{L.PROJECTS}/life-codebase-') and not os.path.islink(ws):
                sibling = ws + '.agents'
                if os.path.isdir(sibling) and not os.path.islink(sibling):
                    shutil.rmtree(sibling, ignore_errors=True)
                shutil.rmtree(ws, ignore_errors=True)
                with L.Tx(self.conn):
                    self.event(cell['cell_id'], 'workspace_removed', ws)
            return

    def move_offline_cells(self):
        """A live, not busy cell whose node was reported offline (online = 0, from a READABLE status list) in every
        sample of the last NODE_OFFLINE_MOVE seconds, with at least OFFLINE_MIN_SAMPLES such samples and samples of that
        node reaching back the whole window, moves to the node child_node picks; agent workspaces live on the host, so
        nothing is copied. An unreadable status writes no sample, so it is never offline evidence."""
        for cell in self.conn.execute("SELECT * FROM cells WHERE state='active' ORDER BY cell_id").fetchall():
            rows = self.conn.execute('SELECT online FROM samples WHERE node=? AND at >= ?', (cell['node'], self.now - L.NODE_OFFLINE_MOVE)).fetchall()
            oldest = self.conn.execute('SELECT MIN(at) FROM samples WHERE node=?', (cell['node'],)).fetchone()[0]
            if (len(rows) < L.OFFLINE_MIN_SAMPLES or any(r['online'] for r in rows) or not oldest
                    or oldest > self.now - L.NODE_OFFLINE_MOVE or self.workspace_busy(cell['cell_id'])):
                continue
            node = self.child_node(cell['organ'], cell['node'])
            if node:
                with L.Tx(self.conn):
                    self.conn.execute('UPDATE cells SET node=? WHERE cell_id=?', (node, cell['cell_id']))
                    self.event(cell['cell_id'], 'moved', f'{cell["node"]} offline for {L.NODE_OFFLINE_MOVE} s -> {node}')
                    L.notice(self.conn, 'moved', cell['cell_id'], f'moved from {cell["node"]} (offline) to {node}')
                return

    def self_questions(self, ctl):
        """Learning asks its own questions: at most SELF_QUESTIONS_PER_DAY a UTC day, only while the learning organ has
        fewer than SELF_QUESTION_QUEUE_MAX queued questions and control/NO_SELF_QUESTIONS is absent. The question is
        'What evidence supports or contradicts: <claim>' from the newest of the SELF_QUESTION_CANDIDATES newest knowledge
        rows without one; it is a search query for bin/life-research.py (taint web, priority 0), never a statement."""
        if not ctl['self_questions'] or L.budget_row(self.conn, self.day)['self_questions'] >= L.SELF_QUESTIONS_PER_DAY:
            return
        if self.conn.execute("SELECT COUNT(*) FROM items WHERE organ='learning' AND state='queued'").fetchone()[0] >= L.SELF_QUESTION_QUEUE_MAX:
            return
        for k in self.conn.execute('SELECT * FROM knowledge ORDER BY created_at DESC LIMIT ?', (L.SELF_QUESTION_CANDIDATES,)).fetchall():
            question = L.one_line('What evidence supports or contradicts: ' + k['claim'], L.QUESTION_CHARS)
            with L.Tx(self.conn):
                _iid, created = self.new_item('learning', 'question', (k['fact_id'], 'derived'),
                                              {'question': question, 'command_id': '', 'found': 0}, 'web', origin=k['fact_id'],
                                              priority=0)
                if created:
                    L.budget_add(self.conn, 'self_questions', day=self.day)
                    return

    # ------------------------------------------------------------------ reproduction
    def efficiency_ok(self, organ):
        """(items done + items abstained) / (program runs + 3 x agent runs) over the two complete UTC days before today,
        reproduction calls included in program runs; >= EFFICIENCY_FLOOR, or fewer than EFFICIENCY_MIN_RUNS cost units."""
        days = [L.utc_day(self.now - L.DAY * k) for k in (1, 2)]
        r = self.conn.execute('SELECT SUM(items_done) d, SUM(items_abstained) a, SUM(program_runs) p, SUM(agent_runs) g FROM metrics'
                              ' WHERE organ=? AND day IN (?, ?)', (organ, *days)).fetchone()
        cost = (r['p'] or 0) + 3 * (r['g'] or 0)
        return cost < L.EFFICIENCY_MIN_RUNS or ((r['d'] or 0) + (r['a'] or 0)) / cost >= L.EFFICIENCY_FLOOR

    def child_node(self, organ, exclude):
        """An available LIFE node other than `exclude` with fewer than NODE_CELL_CAP live cells (agent organs: agy
        ready there; model organs: the TOP rung of every program the organ runs installed there, per a readable
        inventory): fewest cells of this organ, then fewest cells, then the order node-a, node-b, node-d, node-f, node-i."""
        best = None
        programs = {'command': ('classify-command',), 'learning': ('local-research',), 'digest': ('extract-source', 'distill-lesson'),
                    'immune': ('review-patch',), 'compute': ('propose-experiment', 'rank-experiment')}.get(organ, ())
        for node in L.NODES:
            if node == exclude or not any(n == node for n, _ in self.available):
                continue
            if organ in L.AGENT_ORGANS and not self.catalogue_ready(node):
                continue
            if any(not self.model_installed(node, self.ladders[p][-1]) for p in programs):
                continue
            count = len(L.live_cells(self.conn, node=node))
            if count >= L.NODE_CELL_CAP:
                continue
            key = (len(L.live_cells(self.conn, organ=organ, node=node)), count, L.NODES.index(node))
            if best is None or key < best[0]:
                best = (key, node)
        return best[1] if best else None

    def division_gate(self, organ):
        """The organism-wide division rules that are re-checked at start AND at commit."""
        if L.budget_row(self.conn, self.day)['births'] + 2 > L.BIRTHS_PER_DAY:
            return 'the daily birth budget is spent'
        if len(L.live_cells(self.conn)) + 1 > L.LIFE_MAX_CELLS:
            return f'the organism has {L.LIFE_MAX_CELLS} live cells'
        if len(L.live_cells(self.conn, organ=organ)) + 1 > L.ORGAN_CELL_CAP:
            return f'the {organ} organ has {L.ORGAN_CELL_CAP} live cells'
        if not self.may_admit():
            return 'control switches changed'
        return ''

    def division_start(self):
        if not self.may_admit() or self.time_left() <= 0 or self.conn.execute(
                "SELECT COUNT(*) FROM divisions WHERE stage IN ('foci','assign','workspaces')").fetchone()[0] >= L.DIVISIONS_OPEN_MAX:
            return
        # fairness: the organ whose last committed division is oldest goes first, then the lowest cell id
        rows = self.conn.execute(
            "SELECT c.*, (SELECT MAX(d.ended_at) FROM divisions d JOIN cells p ON p.cell_id=d.parent_id WHERE p.organ=c.organ AND"
            " d.stage='committed') AS last_div FROM cells c WHERE c.state='active' AND c.failures_in_a_row=0 AND c.depth < ? AND"
            ' c.backlog_ticks >= ? ORDER BY COALESCE(last_div, 0), c.cell_id', (L.MAX_DEPTH, L.DIVIDE_SUSTAIN)).fetchall()
        for cell in rows:
            if self.division_gate(cell['organ']) or self.workspace_busy(cell['cell_id']):
                continue
            last = self.conn.execute("SELECT MAX(at) FROM cell_events WHERE cell_id=? AND event='divide_aborted'",
                                     (cell['cell_id'],)).fetchone()[0]
            if last and self.now - last < L.DIVISION_COOLDOWN:
                continue
            if not self.efficiency_ok(cell['organ']) or not self.child_node(cell['organ'], cell['node']):
                continue
            snapshot = [r['item_id'] for r in self.conn.execute(
                "SELECT item_id FROM items WHERE cell_id=? AND state='queued' ORDER BY priority DESC, updated_at, item_id",
                (cell['cell_id'],))]
            did = L.sha16(cell['cell_id'], self.now)
            with L.Tx(self.conn):
                self.conn.execute("INSERT INTO divisions (division_id, parent_id, stage, release, snapshot, started_at) VALUES "
                                  "(?, ?, 'foci', ?, ?, ?)", (did, cell['cell_id'], self.release, json.dumps(snapshot), L.now()))
                self.conn.execute("UPDATE cells SET state='dividing' WHERE cell_id=?", (cell['cell_id'],))
                self.event(cell['cell_id'], 'divide_started', f'division {did}: {len(snapshot)} queued items')
            return

    def division_kids(self, div, parent):
        """[(cell id, focus, workspace)] of the two children a division's foci name (deterministic from the lineage)."""
        depth = parent['depth'] + 1
        out = []
        for letter, focus in (('a', div['focus_a']), ('b', div['focus_b'])):
            cid = L.cell_id(parent['organ'], depth, L.sha(parent['cell_id'], letter, focus)[:8])
            out.append((cid, focus, L.workspace_for(cid)))
        return out

    def division_abort(self, div, reason, tx=True):
        """Abort an open division: the parent becomes active again, the event is recorded, and any child workspace the
        division created that no cell owns is removed (crash-safe: the paths follow from the lineage)."""
        def body():
            self.conn.execute("UPDATE divisions SET stage='aborted', ended_at=?, reason=? WHERE division_id=? AND stage IN"
                              " ('foci','assign','workspaces')", (L.now(), L.one_line(reason, 400), div['division_id']))
            self.conn.execute("UPDATE cells SET state='active' WHERE cell_id=? AND state='dividing'", (div['parent_id'],))
            self.event(div['parent_id'], 'divide_aborted', reason)
        if tx:
            with L.Tx(self.conn):
                body()
        else:
            body()
        parent = self.cell(div['parent_id'])
        if parent is not None and parent['organ'] in L.AGENT_ORGANS and div['focus_a'] and div['focus_b']:
            for cid, _f, ws in self.division_kids(div, parent):
                if ws and os.path.isdir(ws) and not self.cell(cid) and ws.startswith(f'{L.PROJECTS}/life-') and not os.path.islink(ws):
                    shutil.rmtree(ws, ignore_errors=True)

    def division_expiry(self):
        """Reconciliation, run before the observe-only gate (even while held): an open division older than
        DIVISION_MAX_SECONDS aborts."""
        for div in self.conn.execute("SELECT * FROM divisions WHERE stage IN ('foci','assign','workspaces') AND started_at < ?",
                                     (self.now - L.DIVISION_MAX_SECONDS,)).fetchall():
            self.division_abort(div, f'the division was open longer than {L.DIVISION_MAX_SECONDS} s')

    def division_progress(self):
        """The open division's code steps on an armed working tick: its tick count grows (past DIVISION_MAX_TICKS it
        aborts); a changed active release aborts it; an assign stage with nothing left to assign moves on (agent organs:
        to workspaces; model organs: commit); in the workspaces stage at most ONE child workspace is created per tick
        (CLONE_TIMEOUT), and the commit follows once both exist."""
        div = self.conn.execute("SELECT * FROM divisions WHERE stage IN ('foci','assign','workspaces')").fetchone()
        if div is None:
            return
        node = (self.cell(div['parent_id']) or {'node': ''})['node']
        if any(n == node for n, _ in self.available):     # a tick only counts when the parent's node could serve it
            with L.Tx(self.conn):
                self.conn.execute('UPDATE divisions SET ticks=ticks+1 WHERE division_id=?', (div['division_id'],))
        div = self.conn.execute('SELECT * FROM divisions WHERE division_id=?', (div['division_id'],)).fetchone()
        parent = self.cell(div['parent_id'])
        if parent is None or parent['state'] != 'dividing':
            return self.division_abort(div, 'the parent is no longer dividing')
        if div['release'] != self.release:
            return self.division_abort(div, f'the active release changed during the division ({div["release"]} -> {self.release})')
        if div['ticks'] > L.DIVISION_MAX_TICKS:
            return self.division_abort(div, f'the division did not finish within {L.DIVISION_MAX_TICKS} counted ticks')
        if div['stage'] == 'assign':
            queued = {r['item_id'] for r in self.conn.execute("SELECT item_id FROM items WHERE cell_id=? AND state='queued'",
                                                              (parent['cell_id'],))}
            assigned = json.loads(div['assigned'])
            if any(i in queued and i not in assigned for i in json.loads(div['snapshot'])[:L.ASSIGN_MAX]):
                return
            if parent['organ'] not in L.AGENT_ORGANS:
                return self.guard(div['division_id'], lambda: self.division_commit(div))
            with L.Tx(self.conn):
                self.conn.execute("UPDATE divisions SET stage='workspaces' WHERE division_id=?", (div['division_id'],))
            div = self.conn.execute('SELECT * FROM divisions WHERE division_id=?', (div['division_id'],)).fetchone()
        if div['stage'] != 'workspaces':
            return
        for cid, _focus, ws in self.division_kids(div, parent):
            if os.path.isdir(os.path.join(ws, '.git')):
                continue
            if not self.can_start(L.CLONE_TIMEOUT) or not self.may_admit():
                return
            why = self.make_workspace(parent['organ'], ws, parent['workspace'])
            if why == NOT_STARTED:
                return None
            if why:
                return self.division_abort(div, f'workspace for {cid}: {why}')
            return                                      # one clone per tick; the next tick continues
        self.guard(div['division_id'], lambda: self.division_commit(div))

    def division_commit(self, div):
        """Re-check every organism-wide rule, then ONE registry transaction: both children (agent organs: their
        workspaces already exist), the items, the parent retired (divided), births + 2, the events. Items at a
        WORKSPACE_STAGES stage (gate, apply) stay with the parent (they need its workspace; it is kept until they end).
        A dividing cell starts no agent run, so a live run at commit can only be one that a crash left: the commit then
        waits (the division stays open, counted in ticks) instead of aborting."""
        parent = self.cell(div['parent_id'])
        if parent is None or parent['state'] != 'dividing':
            return self.division_abort(div, 'the parent is no longer dividing')
        if self.conn.execute("SELECT 1 FROM runs WHERE cell_id=? AND state IN ('submitting','live','submit_unknown')",
                             (parent['cell_id'],)).fetchone():
            return None
        why = self.division_gate(parent['organ'])
        if why:
            return self.division_abort(div, why)
        assigned = json.loads(div['assigned'])
        q = ','.join('?' * len(L.WORKSPACE_STAGES))
        queued = [r['item_id'] for r in self.conn.execute(f"SELECT item_id FROM items WHERE cell_id=? AND state='queued' AND "
                                                          f"stage NOT IN ({q})", (parent['cell_id'], *L.WORKSPACE_STAGES))]
        side = {i: assigned.get(i) or ('a' if int(L.sha(i), 16) % 2 == 0 else 'b') for i in queued}
        a = [i for i in queued if side[i] == 'a']
        b = [i for i in queued if side[i] == 'b']
        if not a or not b:
            return self.division_abort(div, 'one side of the partition is empty')
        node_b = self.child_node(parent['organ'], parent['node'])
        if not node_b:
            return self.division_abort(div, 'no node can host the second child')
        kids = self.division_kids(div, parent)
        for cid, _f, ws in kids:
            if self.cell(cid) is not None:
                return self.division_abort(div, f'lineage key {cid} already exists')
            if parent['organ'] in L.AGENT_ORGANS and not os.path.isdir(os.path.join(ws, '.git')):
                return None                                  # the workspaces stage is not finished
        depth = parent['depth'] + 1
        with L.Tx(self.conn):
            for (cid, focus, ws), node, items in ((kids[0], parent['node'], a), (kids[1], node_b, b)):
                self.conn.execute("INSERT INTO cells (cell_id, organ, kind, parent_id, depth, focus, node, workspace, state, born_at,"
                                  " release) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)",
                                  (cid, parent['organ'], parent['kind'], parent['cell_id'], depth, focus, node, ws, L.now(), self.release))
                self.conn.execute("INSERT INTO cell_programs (cell_id, program, rung, window, rung_up_at) SELECT ?, program, rung, '',"
                                  ' rung_up_at FROM cell_programs WHERE cell_id=?', (cid, parent['cell_id']))
                self.conn.executemany('UPDATE items SET cell_id=? WHERE item_id=?', [(cid, i) for i in items])
                self.event(cid, 'born', f'child of {parent["cell_id"]} on {node}: {focus}')
            self.conn.execute("UPDATE cells SET state='retired', ended_at=?, end_reason='divided' WHERE cell_id=?",
                              (L.now(), parent['cell_id']))
            self.event(parent['cell_id'], 'divided', f'into {kids[0][0]} and {kids[1][0]}')
            self.conn.execute("UPDATE divisions SET stage='committed', child_a=?, child_b=?, ended_at=? WHERE division_id=?",
                              (kids[0][0], kids[1][0], L.now(), div['division_id']))
            L.budget_add(self.conn, 'births', 2, day=self.day)
        return None

    # ------------------------------------------------------------------ 17. node slots
    def node_benchmarking(self, node):
        return any(json.loads(r['payload']).get('node') == node for r in
                   self.conn.execute("SELECT payload FROM items WHERE state='running' AND stage='bench'"))

    def node_has_agent_run(self, node):
        return bool(self.conn.execute("SELECT 1 FROM runs WHERE node=? AND state IN ('submitting','live','submit_unknown')",
                                      (node,)).fetchone())

    def plan_slot(self, node):
        """The next light-model action of this node, or None. Main thread only: it reads the registry, computes every
        input and model now, and the caller marks the item running, so worker threads touch no connection. Order (the
        ONE cross-cell rule): the open division of a cell on this node, when its last step was at least
        DIVISION_STEP_EVERY WORKING ticks ago (meta working_tick_no); else the node's cells: a command cell first only
        when its oldest queued item has waited longer than TICK_SECONDS, then the least recently served
        (last_served_at, updated only when an action is admitted), then the lowest cell id; inside a cell: priority,
        then the oldest updated_at, then the lowest item id (a benchmark start and a program run are both items in that
        order). An item that cannot run here now is skipped, never blocks the node."""
        if not self.may_admit():
            return None
        div = self.conn.execute("SELECT d.* FROM divisions d JOIN cells c ON c.cell_id=d.parent_id WHERE d.stage IN"
                                " ('foci','assign') AND c.node=?", (node,)).fetchone()
        if div and self.working_tick_no - div['last_step_tick'] >= L.DIVISION_STEP_EVERY:
            plan = self.plan_division(node, div)
            if plan:
                return plan
        cells = self.conn.execute(
            "SELECT c.*, (SELECT MIN(i.created_at) FROM items i WHERE i.cell_id=c.cell_id AND i.state='queued') AS oldest"
            " FROM cells c WHERE c.node=? AND c.state IN ('active','dividing')", (node,)).fetchall()
        cells = sorted(cells, key=lambda c: (0 if c['organ'] == 'command' and c['oldest'] and self.now - c['oldest'] > L.TICK_SECONDS
                                             else 1, c['last_served_at'], c['cell_id']))
        for cell in cells:
            for item in self.conn.execute("SELECT * FROM items WHERE cell_id=? AND state='queued' ORDER BY priority DESC,"
                                          ' updated_at, item_id', (cell['cell_id'],)).fetchall():
                if (item['organ'], item['stage']) not in L.SLOT_STAGES:
                    continue
                if item['organ'] == 'compute' and item['stage'] in ('rank', 'bench'):
                    exp = self.conn.execute('SELECT benchmark_id FROM experiments WHERE experiment_id=?',
                                            (json.loads(item['payload']).get('experiment_id'),)).fetchone()
                    if self.benchmarks() and (exp is None or exp['benchmark_id'] not in self.benchmarks()):
                        self.finish_item(item, cell, 'failed', 'its benchmark left control/benchmarks.json (no model was asked)')
                        continue
                if item['stage'] == 'bench':
                    bench = (self.benchmarks() or {})
                    exp = self.conn.execute('SELECT benchmark_id FROM experiments WHERE experiment_id=?',
                                            (json.loads(item['payload']).get('experiment_id'),)).fetchone()
                    t = (bench.get(exp['benchmark_id']) or {}).get('timeout', L.BENCH_TIMEOUT_MAX) if exp else L.BENCH_TIMEOUT_MAX
                    job_seconds = L.BENCH_RUNS * (t + L.BENCH_RUN_SLACK) + L.BENCH_JOB_EXTRA
                    if (L.budget_row(self.conn, self.day)['bench_jobs'] >= L.BENCH_JOBS_PER_DAY or not bench
                            or self.node_has_agent_run(node) or not self.duty_allows(node, job_seconds)
                            or not self.fleet_allows(job_seconds)):
                        continue
                    return ('bench', cell, item)
                if item['organ'] == 'learning' and json.loads(item['payload']).get('found', 0) >= L.QUESTION_SOURCE_LIMIT:
                    continue                                # its reserved links are still being fetched (settle_questions)
                program = self.program_for(item)
                timeout = L.RESEARCH_TIMEOUT if program == 'local-research' else L.CALL_TIMEOUT
                if not self.can_start(timeout):
                    continue
                if item['organ'] == 'compute' and item['stage'] in ('propose', 'rank') and not self.benchmarks():
                    L.notice(self.conn, 'benchmarks_missing', 'compute', 'compute items wait: control/benchmarks.json is '
                             'missing or invalid (copy and edit benchmarks/benchmarks.example.json)')
                    continue
                model, eff = self.model_for(cell, item, program, node)
                if model is None:
                    L.notice(self.conn, 'model_absent', f'{node} {program}', f'no model of the {program} ladder at or above '
                             f'the cell rung is installed on {node} (bin/local-research --list)')
                    continue
                if not self.node_ok(node, model, timeout, program):
                    continue
                if item['organ'] == 'immune' and not self.review_inputs(item):
                    continue
                try:
                    inputs = self.inputs_for(cell, item, program)
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    self.finish_item(item, cell, 'failed', f'inputs unavailable: {exc}')
                    continue
                return ('program', cell, item, program, model, inputs, timeout, eff)
        return None

    def plan_division(self, node, div):
        """A reproducer step on the parent's node: foci (reproduce.sym at the parent's rung + the division's foci retries)
        or up to ASSIGN_PER_SLOT assign-item.sym runs."""
        parent = self.cell(div['parent_id'])
        snapshot = json.loads(div['snapshot'])
        queued = {r['item_id']: r for r in self.conn.execute("SELECT * FROM items WHERE cell_id=? AND state='queued'",
                                                             (parent['cell_id'],))}
        if div['stage'] == 'foci':
            model, _eff = self.model_for(parent, None, 'reproduce', node, extra=div['foci_retries'])
            if model is None or not self.node_ok(node, model, L.CALL_TIMEOUT, 'reproduce') or not self.can_start(L.CALL_TIMEOUT):
                return None
            sample = ' | '.join(self.label(queued[i]) for i in snapshot[:L.SAMPLE_LABELS] if i in queued)[:L.SAMPLE_CHARS]
            inputs = {'organ': parent['organ'], 'parent_focus': parent['focus'], 'sample_items': sample or 'no queued items'}
            return ('division', div, 'foci', model, [('foci', inputs)])
        assigned = json.loads(div['assigned'])
        todo = [i for i in snapshot[:L.ASSIGN_MAX] if i in queued and i not in assigned][:L.ASSIGN_PER_SLOT]
        if not todo:
            return None                                   # lifecycle moves the division on (workspaces or commit)
        model, _eff = self.model_for(parent, None, 'assign-item', node)
        if model is None or not self.node_ok(node, model, L.CALL_TIMEOUT, 'assign-item') or not self.can_start(L.CALL_TIMEOUT):
            return None
        steps = [(iid, {'focus_a': div['focus_a'], 'focus_b': div['focus_b'], 'item_text': self.label(queued[iid])}) for iid in todo]
        return ('division', div, 'assign', model, steps)

    @staticmethod
    def program_for(item):
        return {('command', 'classify'): 'classify-command', ('learning', 'research'): 'local-research',
                ('digest', 'extract'): 'extract-source', ('digest', 'distill'): 'distill-lesson',
                ('codebase', 'triage'): 'triage-error', ('immune', 'review'): 'review-patch',
                ('compute', 'propose'): 'propose-experiment', ('compute', 'rank'): 'rank-experiment'}[(item['organ'], item['stage'])]

    def rung(self, cell, program):
        row = self.conn.execute('SELECT rung FROM cell_programs WHERE cell_id=? AND program=?', (cell['cell_id'], program)).fetchone()
        return row['rung'] if row else 0

    def model_for(self, cell, item, program, node, extra=None):
        """(model, effective rung): the ladder model at min(cell rung + item escalation, top), or the next rung up that is
        installed on the node; (None, None) when no such rung is installed."""
        ladder = self.ladders[program]
        extra = (item['rung_extra'] if item is not None else 0) if extra is None else extra
        start = min(self.rung(cell, program) + extra, len(ladder) - 1)
        for index in range(start, len(ladder)):
            if self.model_installed(node, ladder[index]):
                return ladder[index], index
        return None, None

    def benchmarks(self):
        """The operator's valid benchmark templates by id (LIFE.md section 7.7), validated once per tick: the file is a
        regular operator file of at most BENCH_FILE_MAX_BYTES with at most BENCH_MAX entries; an entry failing any rule is
        skipped (notice benchmarks_invalid); duplicate ids or duplicate JSON keys invalidate the whole file."""
        if self._benchmarks is not None:
            return self._benchmarks or None
        self._benchmarks = {}
        try:
            data = json.loads(L.read_owner_file(L.BENCH_FILE, L.BENCH_FILE_MAX_BYTES).decode('utf-8'), object_pairs_hook=L._no_dup_keys)
        except (OSError, ValueError, UnicodeDecodeError):
            return None
        if not isinstance(data, dict) or set(data) != {'version', 'benchmarks'} or data.get('version') != 2 \
                or not isinstance(data.get('benchmarks'), list) or len(data['benchmarks']) > L.BENCH_MAX:
            L.notice(self.conn, 'benchmarks_invalid', 'benchmarks.json', f'needs exactly {{"version": 2, "benchmarks": [...]}} '
                     f'with at most {L.BENCH_MAX} entries')
            return None
        ids = [b.get('id') for b in data['benchmarks'] if isinstance(b, dict)]
        if len(ids) != len(set(ids)):
            L.notice(self.conn, 'benchmarks_invalid', 'benchmarks.json', 'two benchmarks share an id: the file is ignored')
            return None
        for b in data['benchmarks']:
            problems = bench_problems(b)
            if problems:
                L.notice(self.conn, 'benchmarks_invalid', str(b.get('id') if isinstance(b, dict) else '?')[:40], '; '.join(problems))
                continue
            self._benchmarks[b['id']] = dict(b, sha=L.sha(json.dumps(b, sort_keys=True)))
        return self._benchmarks or None

    def review_inputs(self, item):
        p = json.loads(item['payload'])
        if p['subject'] == 'patch':
            row = self.conn.execute('SELECT * FROM patches WHERE patch_id=?', (p['patch_id'],)).fetchone()
            path = os.path.join(L.BUNDLES, 'patches', p['patch_id'], 'patch.diff')
        else:
            row = self.conn.execute('SELECT * FROM proposals WHERE proposal_id=?', (p['proposal_id'],)).fetchone()
            path = os.path.join(L.BUNDLES, 'proposals', p['proposal_id'], 'proposal.diff')
        try:
            size = os.path.getsize(path)
        except OSError:
            size = -1
        if row is None or size < 0 or size > L.DIFF_REVIEW_BYTES:
            with L.Tx(self.conn):
                if row is not None:
                    table, key = ('patches', 'patch_id') if p['subject'] == 'patch' else ('proposals', 'proposal_id')
                    self.conn.execute(f"UPDATE {table} SET state='owner', updated_at=? WHERE {key}=?", (L.now(), p[key]))
                    if p['subject'] == 'patch':
                        self.count_finding_done(row['item_id'])
                L.notice(self.conn, 'review_owner', item['item_id'], f'missing or larger than {L.DIFF_REVIEW_BYTES} bytes: '
                         'the operator reviews it (apply/adopt need --unreviewed)')
                self.finish_item(item, self.cell(item['cell_id']), 'owner', f'diff missing or larger than {L.DIFF_REVIEW_BYTES} bytes', tx=False)
            return False
        return True

    def inputs_for(self, cell, item, program):
        p = json.loads(item['payload'])
        if program == 'classify-command':
            cmd = self.conn.execute('SELECT * FROM commands WHERE command_id=?', (p['command_id'],)).fetchone()
            return {'command_id': cmd['command_id'], 'command_text': cmd['text']}
        if program == 'local-research':
            return {'question': p['question']}
        if program == 'extract-source':
            if L.file_sha(p['text_path']) != p['text_sha256']:
                raise ValueError('source text snapshot changed on disk')
            with open(p['text_path'], encoding='utf-8') as handle:
                text = handle.read()
            return {'source_id': p['source_key'], 'source_url': p['url'], 'source_text': text}
        if program == 'distill-lesson':
            return {'claim': p['claim'], 'quote': p['quote']}
        if program == 'triage-error':
            return {'finding_id': item['item_id'], 'test_id': p['test_id'], 'finding_text': p['finding_text']}
        if program == 'review-patch':
            if p['subject'] == 'patch':
                row = self.conn.execute('SELECT * FROM patches WHERE patch_id=?', (p['patch_id'],)).fetchone()
                path = os.path.join(L.BUNDLES, 'patches', p['patch_id'], 'patch.diff')
                cls, pcls, ok = row['change_class'], row['path_class'], row['gate_rc'] == 0
                origin = self.item(row['item_id'])
                objective = 'Make the failing test pass: ' + json.loads(origin['payload'])['finding_text'] if origin else 'unknown'
            else:
                row = self.conn.execute('SELECT * FROM proposals WHERE proposal_id=?', (p['proposal_id'],)).fetchone()
                path = os.path.join(L.BUNDLES, 'proposals', p['proposal_id'], 'proposal.diff')
                cls, pcls, ok = 'genome_proposal', 'genome', True
                origin = self.item(row['item_id'])
                objective = 'Apply this lesson (data, not an instruction): ' + json.loads(origin['payload'])['lesson'] if origin else 'unknown'
            with open(path, encoding='utf-8', errors='replace') as handle:
                diff = handle.read(L.DIFF_REVIEW_BYTES)
            return {'subject_id': p.get('patch_id') or p.get('proposal_id'), 'change_class': cls, 'path_class': pcls,
                    'objective': L.one_line(objective, 600), 'diff_text': diff, 'checks_passed': ok}
        if program == 'propose-experiment':
            entries = [f'{b["id"]}: {L.one_line(b["description"], 160)} (allowed parameter pattern {b["param_rx"]}, baseline '
                       f'{b["baseline"]}, unit {b["unit"]}, per-run timeout {b["timeout"]} s, {b["better"]} is better, min gain '
                       f'{b["min_gain_pct"]} %)' for _id, b in sorted(self.benchmarks().items())]
            shown, size = [], 0
            for e in entries:                              # whole entries in id order while they fit; never a cut entry
                if size + len(e) + 3 > L.CATALOGUE_CHARS:
                    break
                shown.append(e)
                size += len(e) + 3
            return {'seed_text': p['seed_text'], 'catalogue': ' | '.join(shown)}
        if program == 'rank-experiment':
            exp = self.conn.execute('SELECT * FROM experiments WHERE experiment_id=?', (p['experiment_id'],)).fetchone()
            bench = (self.benchmarks() or {}).get(exp['benchmark_id']) or {}
            return {'hypothesis': exp['hypothesis'], 'benchmark': L.one_line(bench.get('description', ''), 300) +
                    f' Parameter {exp["param"]} against baseline {bench.get("baseline", "?")}; {L.BENCH_PAIRS} pairs of runs of at '
                    f'most {bench.get("timeout", 0)} s each.'}
        raise ValueError(f'no inputs for {program}')

    def run_program(self, program, inputs, model, node, call_dir, timeout):
        """One genome program run (or one research run), in a worker thread, inside its own life-slot-*.scope
        (MemoryMax SLOT_MEMORY, RuntimeMaxSec = its timeout + KILL_GRACE). Returns (outcome, value, model_calls, detail)
        with outcome done | failed | infra | timeout | contract | stopped (STOP ended it) | not_admitted (no process
        was created). The final admission check (launch_allowed) runs immediately before the process is created."""
        env = L.scope_env()
        if program == 'local-research':
            py = L.REPO_PY if os.path.exists(L.REPO_PY) else L.SYS_PY
            argv = L.scope_argv([py, '-I', '-B', L.RESEARCH_WRAPPER, '--model', model, '--node', node, '--question',
                                 inputs['question']], memory=L.SLOT_MEMORY, runtime=timeout, name='slot')
            rc, out, err = self.procs.run(argv, timeout, env=env, admit=L.launch_allowed)
            if rc in (L.STOPPED_RC, L.NOT_ADMITTED_RC):
                return ('stopped' if rc == L.STOPPED_RC else 'not_admitted'), None, 0, L.one_line(err, 200)
            if rc is None:
                return 'timeout', None, 0, 'research timed out'
            if rc == 127:
                return 'infra', None, 0, L.one_line(err, 200)
            try:
                result = L.strict_json(out)
            except ValueError:
                return 'infra', None, 0, 'research printed no JSON: ' + L.one_line(err[-200:], 200)
            if not isinstance(result, dict) or set(result) != {'model', 'node', 'answer', 'sources', 'steps', 'error'}:
                return 'contract', None, 0, 'the research wrapper printed an object of the wrong shape'
            calls = result.get('steps') if type(result.get('steps')) is int else 0
            if result.get('error'):
                why = str(result['error'])
                if why.startswith('contract:'):
                    return 'contract', None, calls, L.one_line(why, 200)
                return ('infra' if INFRA_RX.search(why) else 'failed'), None, calls, L.one_line(why, 200)
            if not isinstance(result.get('sources'), list):
                return 'failed', None, calls, 'research returned no source list'
            return 'done', result, max(1, calls), ''
        argv = [L.SYMBLIC, 'run', os.path.join(self.rdir, 'genome', f'{program}.sym'), '--by', f'ollama:{model}@{node}', '--json',
                '--max-calls', str(L.CALL_MAX_MODEL_CALLS), '--ollama-limits', json.dumps(L.OLLAMA_LIMITS), '--dir', call_dir]
        for name, value in inputs.items():
            argv += ['--input', f'{name}={json.dumps(value)}']
        argv = L.scope_argv(argv, memory=L.SLOT_MEMORY, runtime=timeout, name='slot')
        rc, out, err = self.procs.run(argv, timeout, cwd=L.STATE, env=env, admit=L.launch_allowed)
        if rc in (L.STOPPED_RC, L.NOT_ADMITTED_RC):
            return ('stopped' if rc == L.STOPPED_RC else 'not_admitted'), None, 0, L.one_line(err, 200)
        if rc is None:
            return 'timeout', None, 0, 'program timed out'
        if rc == L.OUTPUT_LIMIT_RC:
            return 'failed', None, 0, f'the program wrote more than {L.OUTPUT_KILL_BYTES} bytes'
        if rc == 127:
            return 'infra', None, 0, L.one_line(err, 200)
        try:
            rep = L.strict_json(out)
        except ValueError:
            return 'infra', None, 0, 'no JSON report: ' + L.one_line(err[-200:], 200)
        if not isinstance(rep, dict) or ('status' not in rep and 'error' not in rep):
            return 'contract', None, 0, 'the bin/symblic run report has neither status nor error'
        calls = rep.get('calls') if type(rep.get('calls')) is int else 0
        if rep.get('status') == 'done' and rc == 0:
            values = [o.get('value') for o in rep.get('outputs') or [] if isinstance(o, dict) and o.get('kind') == 'return']
            if len(values) == 1 and isinstance(values[0], dict):
                return 'done', values[0], calls, ''
            return 'failed', None, calls, 'the program returned no single record'
        error = rep.get('error') if isinstance(rep.get('error'), dict) else {}
        kind = str(error.get('kind') or '')
        why = f'{kind}: {error.get("message", "")}'
        infra = kind in INFRA_KINDS if kind else bool(INFRA_RX.search(why))
        return ('infra' if infra else 'failed'), None, calls, L.one_line(why, 200)

    def slot_reserve(self, plan):
        """The model calls an action reserves from the day's budget before launch (never refunded)."""
        if plan[0] == 'program':
            return L.RESEARCH_GENERATIONS if plan[3] == 'local-research' else L.CALL_MAX_MODEL_CALLS
        return len(plan[4]) * L.CALL_MAX_MODEL_CALLS

    def launch_slot(self, node, counts, running):
        """Plan, charge and start the next action of `node` (main thread). Every governor input is read again first
        when the last sample is older than TELEMETRY_REFRESH. The budget charge, the item's running state and one
        call_intents row per model process are ONE transaction committed before any process starts. Returns True when a
        thread started."""
        if counts[node] >= L.SLOT_ACTIONS_MAX or self.stopping() or not self.may_admit():
            return False
        self.refresh_available()
        if node not in {n for n, _ in self.available} or self.node_benchmarking(node) or L.node_held(self.conn, node):
            return False
        plan = self.plan_slot(node)
        if not plan:
            return False
        counts[node] += 1
        self.slot_started = True
        if plan[0] == 'bench':
            self.guard(plan[2]['item_id'], lambda: self.start_bench(node, plan[1], plan[2]))
            return False
        budget = L.budget_row(self.conn, self.day)
        reserve = self.slot_reserve(plan)
        if budget['program_runs'] >= L.PROGRAM_RUNS_PER_DAY or budget['model_calls'] + reserve > L.MODEL_CALLS_PER_DAY:
            L.notice(self.conn, 'budget', 'program_runs ' + self.day, 'the daily program-run or model-call budget is spent')
            return False
        dirs = []
        with L.Tx(self.conn):                  # the budget is charged (reserved) before launch, never refunded
            if plan[0] == 'program':
                self.item_update(plan[2]['item_id'], state='running')
                self.conn.execute('UPDATE cells SET last_served_at=? WHERE cell_id=?', (self.now, plan[1]['cell_id']))
                L.metric_add(self.conn, plan[2]['organ'], 'program_runs', day=self.day)
                L.budget_add(self.conn, 'program_runs', day=self.day)
                dirs.append(os.path.join(L.CALLS, L.sha16(plan[1]['cell_id'], plan[2]['item_id'], plan[3], time.time())))
                intents = [(dirs[0], plan[1]['cell_id'], plan[2]['item_id'], plan[3])]
            else:
                parent = self.cell(plan[1]['parent_id'])
                self.conn.execute('UPDATE divisions SET last_step_tick=? WHERE division_id=?', (self.working_tick_no, plan[1]['division_id']))
                L.metric_add(self.conn, parent['organ'], 'program_runs', len(plan[4]), day=self.day)
                L.budget_add(self.conn, 'program_runs', len(plan[4]), day=self.day)
                program = 'reproduce' if plan[2] == 'foci' else 'assign-item'
                dirs = [os.path.join(L.CALLS, L.sha16(plan[1]['division_id'], key, time.time())) for key, _ in plan[4]]
                intents = [(d, parent['cell_id'], None, program) for d in dirs]
            for d, cell_id, item_id, program in intents:
                self.conn.execute('INSERT INTO call_intents (call_id, node, cell_id, item_id, program, started_at) VALUES '
                                  '(?, ?, ?, ?, ?, ?)', (os.path.basename(d), node, cell_id, item_id, program, L.now()))
            L.budget_add(self.conn, 'model_calls', reserve, day=self.day)
        plan = plan + (dirs,)
        box = {}

        def work():
            try:
                box['result'] = self.execute(node, plan)
            except Exception as exc:  # noqa: BLE001 - recorded; the item returns to the queue
                box['result'] = ('error', f'{type(exc).__name__}: {str(exc)[:200]}')
        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        timeout = plan[6] if plan[0] == 'program' else (L.CALL_TIMEOUT if plan[2] == 'foci' else L.ASSIGN_TIMEOUT * len(plan[4]))
        running[node] = (thread, plan, box, time.monotonic() + timeout + L.KILL_GRACE + L.SLOT_WAIT_EXTRA)
        return True

    def serve_nodes(self):
        """The slot phase: one action per available node in parallel threads (one thread per node, so one model process
        per node, as the fleet runner also enforces); when a node's action ends, its result is recorded in the main thread and the
        node plans its next action (at most SLOT_ACTIONS_MAX per tick, each admitted by can_start, may_admit, node_ok
        and the duty-cycle reservation). Nothing a slot started outlives the slot phase."""
        self.refresh_available()
        counts = {n: 0 for n, _ in self.available}
        running = {}
        self.slot_started = False
        self.serve_loop(counts, running)

    def serve_loop(self, counts, running):
        for node in list(counts):
            self.launch_slot(node, counts, running)
        while running:
            time.sleep(1)
            for node, (thread, plan, box, deadline) in list(running.items()):
                if thread.is_alive() and time.monotonic() < deadline:
                    continue
                del running[node]
                subject = plan[2]['item_id'] if plan[0] == 'program' else plan[1]['division_id']
                result = box.get('result', ('error', 'the slot thread did not finish'))
                self.guard(subject, lambda node=node, plan=plan, result=result: self.record(node, plan, result))
                if not thread.is_alive() and not self.stopping():
                    self.launch_slot(node, counts, running)
        self.procs.kill_all('cleanup')
        queued = self.conn.execute("SELECT COUNT(*) FROM items WHERE state='queued' AND cell_id IS NOT NULL AND organ || '/' || stage IN "
                                   f"({','.join(repr(f'{o}/{s}') for o, s in L.SLOT_STAGES)})").fetchone()[0]
        n = 0 if self.slot_started or not queued else int(self.meta('no_capacity_ticks', '0') or 0) + 1
        self.set_meta('no_capacity_ticks', str(n))
        if n >= L.NO_CAPACITY_TICKS:
            L.notice(self.conn, 'no_capacity', 'slots', f'{n} working ticks in a row with {queued} queued slot items and no node '
                     'that could take one (memory, heat, holds, rests, the installed models or the duty cycle)')

    def guard(self, subject, fn):
        """One item's fault never stops the tick (and never poisons later ticks): it is logged, its item goes back to
        the queue, and after FAULTS_MAX such faults at one stage the item fails with the fault as its outcome."""
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            if self.conn.in_transaction:
                self.conn.execute('ROLLBACK')
            why = f'{type(exc).__name__}: {str(exc)[:200]}'
            L.log(f'fault on {subject}: {why}')
            row = self.item(subject)
            if row is not None:
                if row['faults'] + 1 >= L.FAULTS_MAX:
                    self.finish_item(row, self.cell(row['cell_id']), 'failed', 'tick fault: ' + why)
                else:
                    with L.Tx(self.conn):
                        self.conn.execute('UPDATE items SET state=?, faults=?, outcome=?, updated_at=? WHERE item_id=?',
                                          ('queued' if row['state'] == 'running' else row['state'], row['faults'] + 1,
                                           L.one_line('tick fault: ' + why, 400), L.now(), subject))
            return None

    def execute(self, node, plan):
        """Thread body: no registry access at all; only model processes and files."""
        if plan[0] == 'program':
            _, cell, item, program, model, inputs, timeout, _eff, dirs = plan
            call_dir = dirs[0]
            started = L.now()
            return ('program', self.run_program(program, inputs, model, node, call_dir, timeout), started, call_dir, model)
        _, div, stage, model, steps, dirs = plan
        out = []
        for (key, inputs), call_dir in zip(steps, dirs, strict=True):
            if self.stopping():
                break
            program = 'reproduce' if stage == 'foci' else 'assign-item'
            timeout = L.CALL_TIMEOUT if stage == 'foci' else L.ASSIGN_TIMEOUT
            started = L.now()
            out.append((key, self.run_program(program, inputs, model, node, call_dir, timeout), started, L.now(), call_dir))
        return ('division', stage, out)

    def record(self, node, plan, result):
        """Main thread: record one slot action. Every call intent of the action is removed in the same transaction as
        its calls row. stopped / not_admitted (STOP ended the process, or no process was created): the item returns to
        its queue with no counter, hold, call row or tuning change (an orphan hold covers a stopped the fleet runner run). A
        timeout holds the node for THAT program only (NODE_HOLD_SECONDS); at the second timeout at one rung the item
        escalates one rung, and with no higher rung it goes to the operator (outcome TIMEOUT_LIMIT, notice timeout_limit;
        the cell's failure streak is unchanged). infra and contract hold the node for every program."""
        dirs = plan[-1] if isinstance(plan[-1], list) else []
        if result[0] == 'error':
            with L.Tx(self.conn):
                if plan[0] == 'program':
                    self.item_update(plan[2]['item_id'], state='queued', outcome='tick error: ' + result[1])
                for d in dirs:
                    self.conn.execute('DELETE FROM call_intents WHERE call_id=?', (os.path.basename(d),))
                    L.hold_node(self.conn, node, 'orphan', os.path.basename(d), L.now() + L.ORPHAN_HOLD_SECONDS,
                                'the slot thread did not finish cleanly')
            L.log(f'{node}: {result[1]}')
            return
        if result[0] == 'division':
            with L.Tx(self.conn):
                for d in dirs:
                    self.conn.execute('DELETE FROM call_intents WHERE call_id=?', (os.path.basename(d),))
            return self.record_division(node, plan[1], plan[3], result[1], result[2])
        _, cell, item, program, model, _inputs, _timeout, eff, _dirs = plan
        _, (outcome, value, calls, detail), started, call_dir, model = result
        item = self.item(item['item_id'])
        with L.Tx(self.conn):
            self.conn.execute('DELETE FROM call_intents WHERE call_id=?', (os.path.basename(call_dir),))
            if outcome in ('stopped', 'not_admitted'):
                self.item_update(item['item_id'], state='queued', outcome=f'{outcome}: no count')
                if outcome == 'stopped':
                    L.hold_node(self.conn, node, 'orphan', os.path.basename(call_dir), L.now() + L.ORPHAN_HOLD_SECONDS,
                                'STOP ended this call; its fleet-runner run may outlive it')
                return
        if outcome == 'done':
            mismatch = self.binding_problem(program, item, value)
            if mismatch:
                outcome, detail = 'failed', mismatch
        ladder = self.ladders[program]
        base = self.rung(cell, program)
        with L.Tx(self.conn):
            self.conn.execute('INSERT INTO calls (call_id, cell_id, item_id, program, release, applicator, node, outcome,'
                              ' model_calls, started_at, ended_at, dir, detail) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                              (os.path.basename(call_dir), cell['cell_id'], item['item_id'], program, self.release,
                               f'ollama:{model}@{node}', node, 'infra' if outcome in ('timeout', 'contract') else outcome,
                               calls, started, L.now(), call_dir, L.one_line(detail, 400)))
            if outcome == 'contract':
                L.notice(self.conn, 'contract', 'platform', f'{program}: {detail}. Recovery: LIFE.md section 17.')
            if outcome == 'timeout':
                L.hold_node(self.conn, node, 'timeout', program, L.now() + L.NODE_HOLD_SECONDS, L.one_line(detail, 400))
                if item['timeouts'] + 1 >= L.TIMEOUTS_ESCALATE:
                    if eff + 1 < len(ladder) and eff + 1 - base <= 2:
                        self.item_update(item['item_id'], state='queued', rung_extra=eff + 1 - base, timeouts=0,
                                         outcome=f'timed out twice at {model}; escalated')
                    else:
                        L.notice(self.conn, 'timeout_limit', item['item_id'], f'{program} timed out {L.TIMEOUTS_ESCALATE} '
                                 f'times at its top installed rung ({model}); requeue it when the cause is fixed')
                        self.finish_item(item, cell, 'owner', f'TIMEOUT_LIMIT: {program} at {model}', tx=False)
                    return
                self.item_update(item['item_id'], state='queued', timeouts=item['timeouts'] + 1,
                                 outcome=f'timed out at {model}; retried')
                return
            if outcome in ('infra', 'contract'):
                L.hold_node(self.conn, node, 'infra', '', L.now() + L.NODE_HOLD_SECONDS, L.one_line(detail, 400))
                self.count_infra(self.item(item['item_id']), cell, detail, tx=False)
                return
            if outcome == 'failed':
                if eff + 1 < len(ladder) and eff + 1 - base <= 2:
                    self.item_update(item['item_id'], state='queued', rung_extra=eff + 1 - base,
                                     outcome=f'failed at {model}; escalated: {L.one_line(detail, 300)}')
                    return
                self.tune(cell, program, 'f')
                if program in L.PROGRAMS and program not in L.SELFDEV_PROTECTED:
                    # code-written lesson text only (no model or error text); one per program per release
                    self.new_item('selfdev', 'lesson', (program, 'failed', self.release),
                                  {'program': program, 'lesson': f'The program {program} failed at every rung of its ladder on '
                                   f'a {item["kind"]} input; make its ask instructions clearer for small models.'},
                                  'code', origin=item['item_id'])
                self.finish_item(item, cell, 'failed', f'{program} failed at every rung: {detail}', tx=False)
                return
            self.tune(cell, program, 'b' if eff == base else 'e')
            self.apply_value(cell, item, program, value, model, node)

    def binding_problem(self, program, item, v):
        """Protocol checks by code: the record must echo the subject it was asked about; a proposed experiment must name
        an existing benchmark id, a parameter that FULLY matches both its param_rx and PARAM_RX (no salvage: the answer
        is taken after trimming outer white space only) and differs from the baseline, and a 20..300 character
        hypothesis. A violation is a semantic failure (it escalates like any failed answer)."""
        p = json.loads(item['payload'])
        want = {'classify-command': ('command', p.get('command_id')), 'triage-error': ('finding', item['item_id']),
                'extract-source': ('source', p.get('source_key')),
                'review-patch': ('subject', p.get('patch_id') or p.get('proposal_id'))}.get(program)
        if want and v.get(want[0]) != want[1]:
            return f'the record names {want[0]} {str(v.get(want[0]))[:40]!r}, not {want[1]!r}'
        if program == 'propose-experiment':
            bench = (self.benchmarks() or {}).get(str(v.get('benchmark_id') or '').strip())
            param = str(v.get('param') or '').strip()
            hyp = L.one_line(v.get('hypothesis'), 300)
            if not bench or not re.fullmatch(bench['param_rx'], param) or not L.PARAM_RX.fullmatch(param) \
                    or param == bench['baseline'] or len(hyp) < 20:
                return 'the proposal named no valid benchmark id, parameter (full match, not the baseline) or hypothesis'
        return ''

    def tune(self, cell, program, letter):
        """Per cell, per program: a window of the last 10 outcomes (b = done at base, e = needed escalation, f = failed).
        5 or more e/f moves the base rung up (rung_up_at = now); 10 b in a row moves it down one, but never within
        RUNG_DOWN_HOLD of the last rung_up (no up/down oscillation); a move clears the window."""
        row = self.conn.execute('SELECT * FROM cell_programs WHERE cell_id=? AND program=?', (cell['cell_id'], program)).fetchone()
        top = len(self.ladders[program]) - 1
        rung, window, up_at = (min(row['rung'], top), row['window'], row['rung_up_at']) if row else (0, '', 0)
        window = (window + letter)[-10:]
        if len(window) == 10 and sum(1 for c in window if c in 'ef') >= 5 and rung < top:
            rung, window, up_at = rung + 1, '', self.now
            self.event(cell['cell_id'], 'rung_up', f'{program} -> {self.ladders[program][rung]}')
        elif len(window) == 10 and window == 'b' * 10 and rung > 0 and self.now - up_at >= L.RUNG_DOWN_HOLD:
            rung, window = rung - 1, ''
            self.event(cell['cell_id'], 'rung_down', f'{program} -> {self.ladders[program][rung]}')
        self.conn.execute('INSERT OR REPLACE INTO cell_programs (cell_id, program, rung, window, rung_up_at) VALUES (?, ?, ?, ?, ?)',
                          (cell['cell_id'], program, rung, window, up_at))

    # ------------------------------------------------------------------ program answers -> registry rows
    def apply_value(self, cell, item, program, v, model, node):
        """Turn one checked program answer into registry rows. Called inside the record() transaction. Stage successes
        never touch the cell's failure streak (only terminal endings do: finish_item)."""
        getattr(self, 'on_' + program.replace('-', '_'))(cell, item, json.loads(item['payload']), v, f'ollama:{model}@{node}')

    def heartbeat_text(self):
        gov = self.conn.execute('SELECT state FROM governor WHERE id=1').fetchone()
        live = self.conn.execute("SELECT COUNT(*) FROM cells WHERE state IN ('active','dividing','quarantined')").fetchone()[0]
        queued = self.conn.execute("SELECT COUNT(*) FROM items WHERE state='queued'").fetchone()[0]
        runs = self.conn.execute("SELECT COUNT(*) FROM runs WHERE state IN ('submitting','live','submit_unknown')").fetchone()[0]
        notes = self.conn.execute("SELECT COUNT(*) FROM notices WHERE state='open'").fetchone()[0]
        return (f'LIFE status: governor {gov["state"] if gov else "unknown"}, {live} live cells, {queued} queued items, '
                f'{runs} agent runs live, {notes} open notices. Details: life-status.py')

    def on_classify_command(self, cell, item, p, v, app):
        """The classifier's labels (an organ outside ROUTES is none; an urgency outside low/normal/high is normal) feed
        route_command; the command's original text stays the only authoritative instruction."""
        route = v.get('organ') if v.get('organ') in L.ROUTES else 'none'
        urgency = v.get('urgency') if v.get('urgency') in ('low', 'normal', 'high') else 'normal'
        cmd = self.conn.execute('SELECT * FROM commands WHERE command_id=?', (p['command_id'],)).fetchone()
        self.route_command(p['command_id'], route, urgency, L.one_line(L.redact(str(v.get('restated') or '')), 160),
                           cmd['text'], prefixed=False)
        self.finish_item(item, cell, 'done', f'routed to {route}', tx=False)

    def route_command(self, cid, route, urgency, restated, body, prefixed):
        """Dispatch by code (LIFE.md section 7.1), inside the caller's transaction. body = the command text (after its
        prefix when `prefixed`: code chose the route from a COMMAND_PREFIXES prefix or the word status, no model was
        asked). Every route checks its own length limits on the FULL body (never a silent cut); an operator command that
        asks again for work that already ended makes a new occurrence (reoccur = the command id). The database route
        needs the operator's database: prefix (a classifier label alone never changes the organism database). A command
        that creates no item ends in state owner: its notice is its only output and no report is written."""
        prio = {'low': 0, 'normal': 1, 'high': 2}[urgency]
        self.conn.execute("UPDATE commands SET organ=?, urgency=?, restated=?, state='routed', updated_at=? WHERE command_id=?",
                          (route, urgency, restated, L.now(), cid))
        text, made, created = body, '', False

        def too_long(limit):
            L.notice(self.conn, 'command_too_long', cid, f'a {route} command is at most {limit} characters; nothing was cut, '
                     'send a shorter one')
        if route == 'learning':
            if len(text) <= L.QUESTION_CHARS:
                made, created = self.new_item('learning', 'question', (L.norm_text(text),), {'question': text,
                                              'command_id': cid, 'found': 0}, 'owner', origin=cid, priority=prio, reoccur=cid)
            else:
                too_long(L.QUESTION_CHARS)
        elif route == 'codebase':
            test = next((t for t in re.findall(r'\btests\.[A-Za-z0-9_.]+', text) if L.valid_test_id(t.rstrip('.'))), None)
            if test and len(text) <= L.COMMAND_MAX_BYTES:
                test = test.rstrip('.')
                made, created = self.new_item('codebase', 'finding', (test, 'owner', cid),
                                              {'test_id': test, 'finding_text': L.lint_safe(text, L.FINDING_CHARS) or 'fix the test',
                                               'base_commit': '', 'source': 'owner', 'command_text': text}, 'owner', origin=cid,
                                              priority=prio, stage='confirm')
            else:
                L.notice(self.conn, 'command_needs_test', cid, 'a codebase command must name the failing test id '
                         '(tests.test_x) that proves the fix; the first valid one named is used. Name a function to fix as '
                         'path.py:Class.function')
        elif route == 'database':
            req = text if prefixed else (text[len(L.DATABASE_PREFIX):].strip()
                                         if text.lower().startswith(L.DATABASE_PREFIX) else None)
            if req is None:
                L.notice(self.conn, 'command_database_confirm', cid, 'a schema change needs the operator\'s explicit prefix: '
                         f'resend the command starting with "{L.DATABASE_PREFIX}" if you want a new table, column or index')
            elif len(req) > L.REQUEST_MAX_CHARS:
                too_long(L.REQUEST_MAX_CHARS)
            elif len(req) < L.REQUEST_MIN_CHARS:
                L.notice(self.conn, 'command_database_confirm', cid, f'the request after {L.DATABASE_PREFIX} is '
                         f'{L.REQUEST_MIN_CHARS}..{L.REQUEST_MAX_CHARS} characters')
            else:
                made, created = self.new_item('database', 'request', (cid,), {'request': req}, 'owner', origin=cid, priority=prio)
        elif route == 'compute':
            if len(text) <= L.REQUEST_MAX_CHARS:
                made, created = self.new_item('compute', 'experiment', (cid,), {'seed_text': text}, 'owner', origin=cid, priority=prio)
            else:
                too_long(L.REQUEST_MAX_CHARS)
        elif route == 'selfdev':
            named = [g for g in L.PROGRAMS if re.search(r'(?<![\w-])' + re.escape(g) + r'(?![\w-])', text)]
            if len(named) == 1 and named[0] not in L.SELFDEV_PROTECTED and L.LESSON_MIN_CHARS <= len(text) <= L.LESSON_MAX_CHARS:
                made, created = self.new_item('selfdev', 'lesson', (cid,), {'program': named[0], 'lesson': text}, 'owner',
                                              origin=cid, priority=prio)
            elif len(text) > L.LESSON_MAX_CHARS:
                too_long(L.LESSON_MAX_CHARS)
            else:
                L.notice(self.conn, 'command_needs_program', cid, 'a selfdev command must name exactly one genome program it '
                         'may change: ' + ', '.join(g for g in L.PROGRAMS if g not in L.SELFDEV_PROTECTED)
                         + ' (review-patch is protected)')
        elif route == 'heartbeat':
            L.notice(self.conn, 'command_heartbeat', cid, self.heartbeat_text())
        else:
            L.notice(self.conn, f'command_{route}', cid, 'for the operator (no organ acts on it): '
                     + (restated or L.one_line(L.redact(text), 300)))
        state = 'dispatched' if made and created else 'owner'
        if made and not created:
            existing = self.item(made)
            original = existing['origin'] if existing is not None else ''
            self.conn.execute('UPDATE commands SET merged_into=? WHERE command_id=?', (original, cid))
            L.notice(self.conn, 'command_merged', cid, f'the same work is already running as {made} (command {original}); '
                     f'its report covers this command: life-ctl.py report {original}')
            state = 'done'
        self.conn.execute('UPDATE commands SET state=? WHERE command_id=?', (state, cid))

    DOI_RX = re.compile(r'\b(10\.[0-9]{4,9}/[^\s"<>?#]+)')

    @staticmethod
    def canonical_url(url):
        """The URL with its scheme and host lower-cased, the scheme's default port and the fragment removed, and one
        trailing slash of a non-root path removed; path and query otherwise kept as written."""
        import urllib.parse
        parts = urllib.parse.urlsplit(url)
        host = parts.netloc.lower()
        for scheme, port in (('http', ':80'), ('https', ':443')):
            if parts.scheme.lower() == scheme and host.endswith(port):
                host = host[:-len(port)]
        path = parts.path[:-1] if len(parts.path) > 1 and parts.path.endswith('/') else parts.path
        return urllib.parse.urlunsplit((parts.scheme.lower(), host, path, parts.query, ''))

    def source_key(self, url):
        """The ONE source identity (BRIEF: dedup keyed by DOI, URL or text): 'doi:' + the lower-cased DOI when the URL
        names one (10.<4-9 digits>/...); else symblic_autogen.items_key of canonical_url(url) (so http/https, a default
        port, a trailing slash or a fragment never make a second source); when that is longer than SOURCE_KEY_MAX - 4
        characters: 'sha256:' + 56 hex of the canonical URL. Identical fetched text is the third key (fetch_one marks
        the later source a duplicate)."""
        from symblic.autogen import policy as A            # noqa: E402 - REPO is on sys.path (see main)
        import urllib.parse
        m = self.DOI_RX.search(urllib.parse.unquote(url))
        if m:
            key = 'doi:' + m.group(1).lower().rstrip('.')
            if len(key) <= L.SOURCE_KEY_MAX:
                return key
        canon = self.canonical_url(url)
        key = A.items_key(canon)
        if len(key) > L.SOURCE_KEY_MAX - 4:
            key = 'sha256:' + L.sha(canon)[:56]
        return key

    def on_local_research(self, cell, item, p, v, app):
        """The latest answer is kept (redacted). found = this question's USABLE source links (sources whose fetch_state
        is pending or fetched); sources are taken in hit order until the run's quota of new usable links (min(
        NEW_SOURCES_PER_RUN, QUESTION_SOURCE_LIMIT - found)) is reached; the rest are ignored for this run (neither
        recorded nor linked). Zero progress adds a dry run. A known source whose fetch failed, was empty or a duplicate
        is linked but never counted. A new source whose digest item overflowed (OVERFLOW) is recorded as failed, so it
        never counts as usable (life-ctl requeue revives it). A question that reaches the limit waits for its pending
        fetches (settle_questions) instead of ending on reservations."""
        self.conn.execute('INSERT OR REPLACE INTO answers (item_id, applicator, answer, at) VALUES (?, ?, ?, ?)',
                          (item['item_id'], app, L.one_line(L.redact(str(v.get('answer') or '')), L.ANSWER_CHARS), L.now()))

        def usable():
            return self.conn.execute("SELECT COUNT(*) FROM question_sources qs JOIN sources s ON s.source_key=qs.source_key "
                                     "WHERE qs.question_id=? AND s.fetch_state IN ('pending','fetched')", (item['item_id'],)).fetchone()[0]
        found = usable()
        quota, seen = min(L.NEW_SOURCES_PER_RUN, L.QUESTION_SOURCE_LIMIT - found), set()
        for src in v.get('sources') or []:
            url = str((src or {}).get('url') or '') if isinstance(src, dict) else ''
            if usable() - found >= quota or not re.match(r'^https?://', url) or len(url) > L.URL_MAX or L.has_secret(url):
                continue
            key = self.source_key(url)
            if key in seen:
                continue
            seen.add(key)
            if not self.conn.execute('SELECT 1 FROM sources WHERE source_key=?', (key,)).fetchone():
                self.conn.execute('INSERT INTO sources (source_key, url, title, question_id, found_at) VALUES (?, ?, ?, ?, ?)',
                                  (key, url, L.one_line(L.redact(str(src.get('title') or '')), 200), item['item_id'], L.now()))
                sid, created = self.new_item('digest', 'source', (key,), {'source_key': key, 'url': url}, 'web', origin=item['item_id'])
                if not created and (self.item(sid) or {'state': ''})['state'] == 'abstained':
                    self.conn.execute("UPDATE sources SET fetch_state='failed' WHERE source_key=?", (key,))
            self.conn.execute('INSERT OR IGNORE INTO question_sources (question_id, source_key, at) VALUES (?, ?, ?)',
                              (item['item_id'], key, L.now()))
        total = usable()
        counted = total - found
        dry = item['dry_runs'] + 1 if counted == 0 else 0
        p['found'] = total
        if total >= L.QUESTION_SOURCE_LIMIT and dry < L.QUESTION_DRY_LIMIT:
            self.item_update(item['item_id'], state='queued', dry_runs=dry, rung_extra=0, infra_runs=0, timeouts=0,
                             payload=json.dumps(p, sort_keys=True), outcome=f'{total} links reserved; waits for their fetches')
            return
        if dry >= L.QUESTION_DRY_LIMIT:
            self.item_update(item['item_id'], payload=json.dumps(p, sort_keys=True), dry_runs=dry)
            self.finish_item(self.item(item['item_id']), cell, 'done',
                             f'{total} sources; {"exhausted after " + str(dry) + " dry runs" if dry else "limit reached"}', tx=False)
        else:
            self.item_update(item['item_id'], state='queued', dry_runs=dry, rung_extra=0, infra_runs=0, timeouts=0,
                             payload=json.dumps(p, sort_keys=True), outcome=f'{counted} new source link(s) this run; researched again later')

    def on_extract_source(self, cell, item, p, v, app):
        if v.get('supported') is not True:
            self.finish_item(item, cell, 'abstained', 'NO_SUPPORTED_CLAIM', tx=False)
            return
        with open(p['text_path'], encoding='utf-8') as handle:
            text = handle.read()
        quote, claim = str(v.get('quote') or ''), str(v.get('claim') or '')

        def squash(s):
            return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', s)).strip()
        found = re.search(r'(?<!\w)' + re.escape(squash(quote)) + r'(?!\w)', squash(text)) if quote.strip() else None
        if not (12 <= len(quote) <= 400 and 20 <= len(claim) <= 300 and found) or L.has_secret(quote + ' ' + claim):
            self.finish_item(item, cell, 'abstained', 'quote not found again by code (NFC, whole words) in the stored snapshot', tx=False)
            return
        fact = L.sha16(p['source_key'], quote)
        self.conn.execute('INSERT OR IGNORE INTO knowledge (fact_id, source_key, text_sha256, claim, quote, quote_verified,'
                          ' applicator, created_at) VALUES (?, ?, ?, ?, ?, 1, ?, ?)',
                          (fact, p['source_key'], p['text_sha256'], claim, quote, app, L.now()))
        p.update(fact_id=fact, claim=claim, quote=quote)
        self.item_update(item['item_id'], stage='distill', state='queued', payload=json.dumps(p, sort_keys=True))

    def on_distill_lesson(self, cell, item, p, v, app):
        target, lesson = v.get('target'), L.one_line(v.get('lesson'), L.LESSON_MAX_CHARS)
        taint = derive_taint(item['taint'], 'web')
        if lesson.lower().startswith('no lesson') or len(lesson) < L.LESSON_MIN_CHARS:
            target = 'none'
        if target == 'genome' and v.get('program') in L.PROGRAMS and v.get('program') not in L.SELFDEV_PROTECTED:
            self.new_item('selfdev', 'lesson', (p['fact_id'], 'genome'), {'program': v['program'], 'lesson': lesson},
                          taint, origin=item['item_id'])
        elif target == 'compute':
            self.new_item('compute', 'experiment', (p['fact_id'],), {'seed_text': lesson}, taint, origin=item['item_id'])
        elif target == 'database':
            self.new_item('database', 'request', (p['fact_id'],), {'request': lesson}, taint, origin=item['item_id'])
        self.finish_item(item, cell, 'done', f'fact {p["fact_id"]}; lesson target {target}', tx=False)

    def on_triage_error(self, cell, item, p, v, app):
        cls = v.get('change_class')
        why = ''
        if cls not in ('test_only', 'comment_or_doc', 'local_fix') or v.get('confident') is not True:
            why = f'triaged {cls}, confident {v.get("confident")}; LIFE writes no patch for it'
        elif cls == 'local_fix' and not p.get('trace_files'):
            why = 'local_fix, but the failure names no source file LIFE may change'
        if why:
            L.notice(self.conn, 'finding_owner', item['item_id'], f'{p["test_id"]}: {why}. To try again with the function '
                     f'named: life-ctl.py command "fix: {p["test_id"]} path.py:Class.function"')
            self.finish_item(item, cell, 'owner', why, tx=False)
            return
        p['change_class'] = cls
        self.item_update(item['item_id'], stage='patch', state='queued', payload=json.dumps(p, sort_keys=True))

    def count_finding_done(self, finding_id):
        """A finding is counted done ONCE, when its patch leaves review (accept, reject, owner) — never at the gate, so a
        needs_work round never counts it twice."""
        finding = self.item(finding_id)
        if finding is not None:
            self.count_ending(finding['organ'], finding['cell_id'], 'done')

    def on_review_patch(self, cell, item, p, v, app):
        """accept -> ready + patch_ready (a test_only patch is never ready from a model accept: it goes to the operator,
        notice patch_test_only); reject -> rejected; needs_work -> rejected, and for a patch whose finding had fewer
        than NEEDS_WORK_MAX rounds the finding is re-queued at patch with the reason as review_note and the old patch id
        as previous_patch. A proposal's needs_work is a rejection."""
        verdict, reason = v.get('verdict'), L.one_line(L.redact(str(v.get('reason') or '')), 240)
        state = {'accept': 'ready', 'reject': 'rejected', 'needs_work': 'rejected'}[verdict]
        if p['subject'] == 'patch':
            row = self.conn.execute('SELECT * FROM patches WHERE patch_id=?', (p['patch_id'],)).fetchone()
            if verdict == 'accept' and row['change_class'] == 'test_only':
                state = 'owner'
            self.conn.execute('UPDATE patches SET review=?, review_reason=?, state=?, updated_at=? WHERE patch_id=?',
                              (verdict, reason, state, L.now(), p['patch_id']))
            finding = self.item(row['item_id'])
            if verdict == 'accept' and state == 'owner':
                L.notice(self.conn, 'patch_test_only', p['patch_id'], 'the reviewer accepted a test-only patch; a model never '
                         f'makes a judging test change ready: read it, then life-ctl.py apply {p["patch_id"]} --confirm APPLY '
                         '--unreviewed')
                self.count_finding_done(row['item_id'])
            elif verdict == 'accept':
                L.notice(self.conn, 'patch_ready', p['patch_id'], f'reviewed and gated; apply with life-ctl.py apply {p["patch_id"]} --confirm APPLY')
                self.count_finding_done(row['item_id'])
            elif verdict == 'needs_work' and finding is not None and finding['review_rounds'] < L.NEEDS_WORK_MAX:
                fp = json.loads(finding['payload'])
                fp.update(review_note=L.lint_safe(reason, 240) or 'none', previous_patch=p['patch_id'])
                self.item_update(finding['item_id'], state='queued', stage='patch', attempts=finding['attempts'] + 1,
                                 review_rounds=finding['review_rounds'] + 1, payload=json.dumps(fp, sort_keys=True),
                                 outcome='the reviewer asked for one fix')
            else:
                if verdict == 'needs_work' and finding is not None:
                    L.notice(self.conn, 'finding_owner', finding['item_id'], f'the reviewer asked for work {L.NEEDS_WORK_MAX} times')
                self.count_finding_done(row['item_id'])
        else:
            # a proposal's needs_work is a rejection; its lesson is not re-queued (the operator may re-send it as a command)
            self.conn.execute('UPDATE proposals SET review=?, review_reason=?, state=?, updated_at=? WHERE proposal_id=?',
                              (verdict, reason, state, L.now(), p['proposal_id']))
            if verdict == 'accept':
                L.notice(self.conn, 'proposal_ready', p['proposal_id'], f'adopt with life-ctl.py adopt {p["proposal_id"]} --confirm ADOPT')
        self.finish_item(item, cell, 'done', f'{verdict}: {reason}', tx=False)

    def on_propose_experiment(self, cell, item, p, v, app):
        bench = self.benchmarks()[str(v.get('benchmark_id')).strip()]      # binding_problem checked every field
        param, hypothesis = str(v.get('param')).strip(), L.one_line(L.redact(str(v.get('hypothesis'))), 300)
        eid = L.sha16(bench['sha'], param)
        if self.conn.execute('SELECT 1 FROM experiments WHERE experiment_id=?', (eid,)).fetchone():
            self.finish_item(item, cell, 'abstained', f'experiment {eid} was already proposed', tx=False)
            return
        self.conn.execute("INSERT INTO experiments (experiment_id, item_id, benchmark_id, bench_sha256, param, hypothesis, better,"
                          " min_gain_pct, state, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'proposed', ?)",
                          (eid, item['item_id'], bench['id'], bench['sha'], param, hypothesis, bench['better'], bench['min_gain_pct'], L.now()))
        p['experiment_id'] = eid
        self.item_update(item['item_id'], stage='rank', state='queued', payload=json.dumps(p, sort_keys=True))

    def on_rank_experiment(self, cell, item, p, v, app):
        score = v.get('score') if type(v.get('score')) is int else 0
        eligible = v.get('feasible') is True and v.get('risk') == 'low' and score >= 60
        self.conn.execute('UPDATE experiments SET feasible=?, novelty=?, risk=?, score=?, state=? WHERE experiment_id=?',
                          (int(v.get('feasible') is True), v.get('novelty') if v.get('novelty') in ('none', 'small', 'large') else None,
                           v.get('risk') if v.get('risk') in ('low', 'medium', 'high') else None, max(0, min(100, score)),
                           'ranked' if eligible else 'ineligible', p['experiment_id']))
        if eligible:
            self.item_update(item['item_id'], stage='bench', state='queued')
        else:
            self.finish_item(item, cell, 'done', f'ineligible: feasible={v.get("feasible")} risk={v.get("risk")} score={score}', tx=False)

    def record_division(self, node, div, model, stage, outs):
        """Main thread: store what the reproducer and assign-item runs returned for one division (one calls row per
        step, so the node's load ledger and the organ's cost include reproduction). Both programs tune the parent's
        rung like any program. A failed foci answer retries FOCI_RETRIES time(s) at the next rung in a later slot, then
        the division aborts; a failed assignment takes the parity side at once."""
        parent = self.cell(div['parent_id'])
        program = 'reproduce' if stage == 'foci' else 'assign-item'
        with L.Tx(self.conn):
            for _key, (outcome, _value, calls, detail), started, ended, call_dir in outs:
                if outcome in ('stopped', 'not_admitted'):
                    if outcome == 'stopped':
                        L.hold_node(self.conn, node, 'orphan', os.path.basename(call_dir), L.now() + L.ORPHAN_HOLD_SECONDS,
                                    'STOP ended this division call')
                    continue
                self.conn.execute('INSERT INTO calls (call_id, cell_id, item_id, program, release, applicator, node, outcome,'
                                  ' model_calls, started_at, ended_at, dir, detail) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                                  (os.path.basename(call_dir), parent['cell_id'], program, self.release, f'ollama:{model}@{node}',
                                   node, 'infra' if outcome in ('timeout', 'contract') else outcome, calls, started, ended,
                                   call_dir, L.one_line(detail, 400)))
                if outcome == 'timeout':
                    L.hold_node(self.conn, node, 'timeout', program, L.now() + L.NODE_HOLD_SECONDS, L.one_line(detail, 400))
                elif outcome in ('infra', 'contract'):
                    L.hold_node(self.conn, node, 'infra', '', L.now() + L.NODE_HOLD_SECONDS, L.one_line(detail, 400))
                elif outcome in ('done', 'failed'):
                    self.tune(parent, program, 'b' if outcome == 'done' else 'f')
        if stage == 'foci':
            if not outs:
                return
            outcome, value, _calls, detail = outs[0][1]
            if outcome == 'done' and isinstance(value.get('focus_a'), str) and isinstance(value.get('focus_b'), str):
                fa, fb = L.one_line(value['focus_a'], 120), L.one_line(value['focus_b'], 120)
                pf = L.norm_text(parent['focus'])
                if len(fa) >= 8 and len(fb) >= 8 and len({L.norm_text(fa), L.norm_text(fb), pf}) == 3 \
                        and not L.has_secret(fa + ' ' + fb):
                    with L.Tx(self.conn):
                        self.conn.execute("UPDATE divisions SET stage='assign', focus_a=?, focus_b=? WHERE division_id=?",
                                          (fa, fb, div['division_id']))
                    return
                outcome, detail = 'failed', 'foci failed the code check (8..120 characters, different from each other and the parent)'
            if outcome == 'failed':
                if div['foci_retries'] < L.FOCI_RETRIES:
                    with L.Tx(self.conn):
                        self.conn.execute('UPDATE divisions SET foci_retries=foci_retries+1 WHERE division_id=?', (div['division_id'],))
                else:
                    self.division_abort(div, f'reproducer failed: {detail}')
            return
        with L.Tx(self.conn):
            row = self.conn.execute('SELECT assigned FROM divisions WHERE division_id=?', (div['division_id'],)).fetchone()
            assigned = json.loads(row['assigned'])
            for iid, (outcome, value, _calls, _detail), _s, _e, _d in outs:
                if outcome == 'done' and (value or {}).get('side') in ('a', 'b'):
                    assigned[iid] = value['side']
                elif outcome == 'failed':
                    assigned[iid] = 'a' if int(L.sha(iid), 16) % 2 == 0 else 'b'
            self.conn.execute('UPDATE divisions SET assigned=? WHERE division_id=?', (json.dumps(assigned), div['division_id']))

    def start_bench(self, node, cell, item):
        """Persist the job intent (label life-<experiment>-<attempt>, the bench budget charged) BEFORE POST
        /api/cluster/map, so a lost answer is found again by its label. One job runs BENCH_RUNS runs in order, each
        item `<k>:<value>` (k = 0..7: the warm-ups baseline then candidate, then BENCH_ORDER); each run prints LIFE_RUN k,
        the first BENCH_OUT_BYTES of its output (kept in a temporary file the wrapper removes), LIFE_RC k with the
        command's own exit status, LIFE_TRUNC k when the output was longer, and LIFE_END k; each run is the operator's
        command under timeout (whole process group), nice 15 and prlimit, on this node only. bench_wrapper() builds the
        command; VALIDATE runs it on printf."""
        p = json.loads(item['payload'])
        exp = self.conn.execute('SELECT * FROM experiments WHERE experiment_id=?', (p['experiment_id'],)).fetchone()
        bench = (self.benchmarks() or {}).get(exp['benchmark_id'])
        if not bench or bench['sha'] != exp['bench_sha256']:
            self.finish_item(item, cell, 'failed', 'its benchmark left or changed in control/benchmarks.json')
            return
        if not self.may_admit():
            return
        t = bench['timeout']
        cmd = bench_wrapper(bench['cmd'], t)
        values = [bench['baseline'] if role == 'baseline' else exp['param'] for role in L.BENCH_WARMUP_ORDER + L.BENCH_ORDER]
        label = f'life-{exp["experiment_id"]}-{item["attempts"] + 1}'
        body = {'cmd': cmd, 'items': [f'{k}:{v}' for k, v in enumerate(values)], 'targets': [node], 'parallel': 1,
                'timeout': L.BENCH_RUNS * (t + L.BENCH_RUN_SLACK) + L.BENCH_JOB_EXTRA, 'label': label}
        p.update(job_id='', node=node, unit=bench['unit'], started=L.now(), timeout=body['timeout'], label=label)
        with L.Tx(self.conn):
            self.item_update(item['item_id'], state='running', attempts=item['attempts'] + 1, payload=json.dumps(p, sort_keys=True))
            L.budget_add(self.conn, 'bench_jobs', day=self.day)
        try:
            job = L.http_json('/api/cluster/map', body, timeout=L.HTTP_SLOW_TIMEOUT).get('job') or {}
        except L.Telemetry as exc:
            if exc.status is not None:              # the server answered: nothing was started
                with L.Tx(self.conn):
                    L.notice(self.conn, 'bench_refused', exp['experiment_id'], str(exc))
                    self.item_update(item['item_id'], payload=json.dumps({'seed_text': p['seed_text'],
                                                                          'experiment_id': p['experiment_id']}, sort_keys=True))
                    self.count_infra(self.item(item['item_id']), cell, f'map refused: {exc}', tx=False)
            return                                  # no answer: the job may exist; the poll looks for its label
        p['job_id'] = str(job.get('id') or '') if isinstance(job, dict) else ''
        with L.Tx(self.conn):
            self.item_update(item['item_id'], payload=json.dumps(p, sort_keys=True))

    # ------------------------------------------------------------------ 18. status
    def write_status(self, disposition):
        gov = self.conn.execute('SELECT * FROM governor WHERE id=1').fetchone()
        cells = [dict(c) for c in self.conn.execute("SELECT cell_id, organ, node, state, depth, focus, failures_in_a_row,"
                                                    " items_done FROM cells WHERE state != 'retired' ORDER BY cell_id")]
        for c in cells:
            c['queued'] = self.conn.execute("SELECT COUNT(*) FROM items WHERE cell_id=? AND state='queued'", (c['cell_id'],)).fetchone()[0]
        status = {'tick_started_at': self.now, 'tick_finished_at': L.now(), 'disposition': disposition, 'tick': self.tick_no,
                  'working_tick': self.working_tick_no, 'release': self.release, 'control': L.control_state(), 'holds': self.holds,
                  'runs_cancel_requested': self.conn.execute("SELECT COUNT(*) FROM runs WHERE state IN ('submitting','live',"
                                                             "'submit_unknown') AND cancel_cause != ''").fetchone()[0],
                  'governor': dict(gov) if gov else None, 'budget': dict(L.budget_row(self.conn, self.day)), 'cells': cells,
                  'runs_live': self.conn.execute("SELECT COUNT(*) FROM runs WHERE state IN ('submitting','live','submit_unknown')").fetchone()[0],
                  'notices_open': self.conn.execute("SELECT COUNT(*) FROM notices WHERE state='open'").fetchone()[0]}
        L.write_atomic(os.path.join(L.OWNER, 'status.json'), json.dumps(status, indent=1, sort_keys=True))

    # ------------------------------------------------------------------ the tick
    def reconcile_only(self):
        """A STOP tick after stop_everything: recover what a killed tick left, then poll runs and benchmark jobs and
        record what the platform proves (terminal runs collected), with no start, no re-send and no new request."""
        self.recover()
        self.poll_runs(reconcile_only=True)
        self.poll_benches()

    def run(self):
        """One tick (the module docstring is the order). Returns the exit code and sets self.disposition: worked |
        observe:<first hold> | stop | integrity."""
        self.tick_no += 1
        self.set_meta('tick_no', str(self.tick_no))
        L.ensure_dirs()
        self.recover()
        self.integrity()
        self.metabolism()
        self.canaries()
        self.poll_runs()
        self.poll_benches()
        self.division_expiry()
        self.migration_reconcile()
        self.storage()
        if 'storage' not in self.holds:
            self.ingest_inbox()
        self.backup()
        self.reports()
        ctl = L.control_state()
        if ctl['stop']:
            L.stop_everything(self.conn, self.procs)
            self.reconcile_only()
            self.disposition = 'stop'
            return EXIT_STOP
        if not ctl['admit'] or self.holds or self.release is None:
            why = ('not armed for this boot' if not ctl['armed'] else 'frozen' if ctl['freeze']
                   else 'the kit, a pinned platform file or DECISIONS.md changed since arm' if not ctl['admit']
                   else '; '.join(self.holds) or 'no release')
            self.holds = self.holds or [why]
            self.conn.execute('UPDATE cells SET backlog_ticks=0 WHERE backlog_ticks != 0')   # consecutive WORKING ticks only
            self.hold_notices()
            L.log('observe only: ' + why)
            integrity = {'integrity', 'contract'} & set(self.holds)
            self.disposition = 'integrity' if integrity else 'observe:' + self.holds[0].split(':')[0][:60]
            return EXIT_HOLD if integrity else EXIT_OK
        self.working_tick_no += 1
        self.set_meta('working_tick_no', str(self.working_tick_no))
        self.agenda()
        self.hold_notices()
        if self.working_tick_no % 2 == 1:      # odd working ticks: node slots before the host stages (no starvation)
            self.dispatch()
            self.lifecycle()
            self.dispatch()
            self.models_inventory()
            self.serve_nodes()
            self.findings()
            self.host_stages()
        else:
            self.findings()
            self.dispatch()
            self.host_stages()
            self.lifecycle()
            self.dispatch()
            self.models_inventory()
            self.serve_nodes()
        if L.control_state()['stop']:
            L.stop_everything(self.conn, self.procs)
            self.reconcile_only()
            self.disposition = 'stop'
            return EXIT_STOP
        self.disposition = 'worked'
        return EXIT_OK


# The only param_rx shapes LIFE accepts (each matches in linear time; Python's backtracking engine never meets a
# nested or adjacent repetition): an anchored alternation of literals ^(A|B|C)$ (each literal a PARAM_RX value, no
# regex character), or an anchored single character class with an optional bounded count ^[...]$ / ^[...]{m,n}$
# (the class lists letters, digits, ., _, :, + and ranges a-z, A-Z, 0-9 only; n <= 64).
PARAM_GRAMMAR_RX = re.compile(r'\^\((?:[A-Za-z0-9_:+]+)(?:\|[A-Za-z0-9_:+]+)*\)\$|'
                              r'\^\[(?:[A-Za-z0-9_.:+]|[a-z]-[a-z]|[A-Z]-[A-Z]|[0-9]-[0-9])+\](?:\{[0-9]{1,2}(?:,[0-9]{1,2})?\})?\$')


def bench_wrapper(owner_cmd, t):
    """The map-route command of one benchmark run: `sh -c '<wrapper>' life-run {{item}}`; the route passes the item as
    "$1" (k:value). The wrapper prints LIFE_RUN k, runs the operator's command (its {{item}} replaced by "$1" of the inner
    sh, which receives the value) under timeout --kill-after, nice 15 and prlimit with stdout and stderr into a temporary
    file, prints the file's first BENCH_OUT_BYTES, then LIFE_RC k <the command's exit status>, LIFE_TRUNC k when the
    output was longer, and LIFE_END k, and removes the file."""
    inner = owner_cmd.replace('{{item}}', '"$1"')
    run_cmd = (f'timeout --kill-after={L.BENCH_RUN_SLACK} {t} nice -n 15 prlimit --as={L.BENCH_AS_BYTES} '
               f'--fsize={L.BENCH_FSIZE_BYTES} --nofile={L.BENCH_NOFILE} sh -c {shlex.quote(inner)} life-bench "$v"')
    wrapper = (f'k=${{1%%:*}}; v=${{1#*:}}; o=$(mktemp) || exit 1; echo "LIFE_RUN $k"; {run_cmd} >"$o" 2>&1; rc=$?; '
               f'head -c {L.BENCH_OUT_BYTES} "$o"; echo; echo "LIFE_RC $k $rc"; '
               f'[ "$(wc -c < "$o")" -gt {L.BENCH_OUT_BYTES} ] && echo "LIFE_TRUNC $k"; rm -f "$o"; echo "LIFE_END $k"')
    return f'sh -c {shlex.quote(wrapper)} life-run ' + '{{item}}'


def bench_problems(b):
    """The rules one operator benchmark template must satisfy (LIFE.md section 7.7). Empty list = valid."""
    keys = {'id', 'description', 'cmd', 'param_rx', 'baseline', 'unit', 'timeout', 'better', 'min_gain_pct'}
    if not isinstance(b, dict) or set(b) != keys:
        return ['keys must be exactly ' + ', '.join(sorted(keys))]
    out = []
    if not isinstance(b['id'], str) or not re.fullmatch(r'[a-z0-9-]{2,40}', b['id']):
        out.append('id is [a-z0-9-]{2,40}')
    if not isinstance(b['description'], str) or not 10 <= len(b['description']) <= 600:
        out.append('description is 10..600 characters')
    if not isinstance(b['cmd'], str) or b['cmd'].count('{{item}}') < 1 or len(b['cmd']) > 2000:
        out.append('cmd contains {{item}} and is at most 2000 characters')
    try:
        rx = re.compile(b['param_rx']) if isinstance(b['param_rx'], str) and len(b['param_rx']) <= L.PARAM_RX_MAX \
            and PARAM_GRAMMAR_RX.fullmatch(b['param_rx']) else None
    except re.error:
        rx = None
    if rx is None:
        out.append(f'param_rx is at most {L.PARAM_RX_MAX} characters and one of the PARAM_GRAMMAR_RX shapes: ^(A|B|C)$ '
                   'or ^[class]$ or ^[class]{m,n}$')
    elif not isinstance(b['baseline'], str) or not L.PARAM_RX.fullmatch(b['baseline']) or not rx.fullmatch(b['baseline']):
        out.append('baseline matches param_rx and [A-Za-z0-9._:+][A-Za-z0-9._:+-]{0,63}')
    if not isinstance(b['unit'], str) or not re.fullmatch(r'[A-Za-z/%]{1,12}', b['unit']):
        out.append('unit is [A-Za-z/%]{1,12}')
    if type(b['timeout']) is not int or not L.BENCH_TIMEOUT_MIN <= b['timeout'] <= L.BENCH_TIMEOUT_MAX:
        out.append(f'timeout is an integer {L.BENCH_TIMEOUT_MIN}..{L.BENCH_TIMEOUT_MAX}')
    if b['better'] not in ('lower', 'higher'):
        out.append('better is "lower" or "higher"')
    if type(b['min_gain_pct']) is not int or not 1 <= b['min_gain_pct'] <= 90:
        out.append('min_gain_pct is an integer 1..90')
    return out


def run_canaries(rdir, procs):
    """Every line of checks/canaries.txt (argv by shlex, no shell, cwd STATE, CANARY_TIMEOUT each, CANARY_ROUND_SECONDS
    for the round; lines not reached count as failed). Returns the failures (empty = passed)."""
    failed, start = [], time.monotonic()
    with open(os.path.join(L.KIT, 'checks', 'canaries.txt'), encoding='utf-8') as handle:
        lines = [ln.strip() for ln in handle if ln.strip() and not ln.startswith('#')]
    if not lines:
        return ['checks/canaries.txt holds no canary']
    for line in lines:
        if time.monotonic() - start > L.CANARY_ROUND_SECONDS:
            failed.append(f'{line[:80]} -> round budget spent')
            continue
        argv = shlex.split(line.replace('{release_dir}', rdir).replace('{kit}', L.KIT))
        rc, _out, _err = procs.run(argv, L.CANARY_TIMEOUT, cwd=L.STATE, env=L.child_env())
        if rc != 0:
            failed.append(f'{line[:80]} -> rc {rc}')
    return failed


def main():
    if not os.path.isfile(L.REGISTRY):
        print('life-tick: not seeded (run docs/life/bin/life-seed.sh)')
        return EXIT_UNSEEDED
    if L.REPO not in sys.path:
        sys.path.insert(0, L.REPO)
    lock = L.open_lock(L.LOCK_FILE)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('life-tick: another tick or life-ctl holds the lock')
        return EXIT_OK
    procs = L.Procs()
    done = threading.Event()

    def watch_stop():                               # STOP ends every LIFE process within STOP_POLL + KILL_GRACE s
        scoped = False
        while not done.wait(L.STOP_POLL):
            if L.stop_present():
                if procs.live or not scoped:        # scopes are stopped once per STOP, then only while groups live
                    threading.Thread(target=L.stop_scopes, daemon=True).start()
                    scoped = True
                procs.kill_all('stop')
            else:
                scoped = False

    def on_term(signum, _frame):                    # systemd stop or TimeoutStartSec: end children, then exit 4
        threading.Thread(target=L.stop_scopes, daemon=True).start()
        procs.kill_all('stop')
        raise SystemExit(EXIT_TERM)
    signal.signal(signal.SIGTERM, on_term)
    threading.Thread(target=watch_stop, daemon=True).start()
    conn = L.connect()
    tick = None
    try:
        if L.stop_present():                        # before the schema check and anything that could fail on a broken release
            L.stop_everything(conn, procs)
            row = conn.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
            if row and row[0] == L.SCHEMA_VERSION:
                tick = Tick(conn, procs)
                tick.disposition = 'stop'
                try:
                    tick.reconcile_only()
                except Exception as exc:  # noqa: BLE001 - reconciliation is best effort under STOP; the cancels were asked
                    L.log(f'STOP reconciliation: {type(exc).__name__}: {str(exc)[:200]}')
            return EXIT_STOP
        row = conn.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
        if not row or row[0] != L.SCHEMA_VERSION:
            print(f'life-tick: registry schema is not {L.SCHEMA_VERSION}')
            return EXIT_HOLD
        tick = Tick(conn, procs)
        code = tick.run()
        conn.execute("UPDATE meta SET value='0' WHERE key='faults_in_a_row'")
        return code
    except SystemExit:
        if tick is not None:
            tick.disposition = 'killed'
        raise
    except Exception as exc:  # noqa: BLE001 - the operator sees the fault; three in a row hold new work
        if conn.in_transaction:
            conn.execute('ROLLBACK')
        L.log(f'tick fault: {type(exc).__name__}: {str(exc)[:300]}')
        try:
            n = int((conn.execute("SELECT value FROM meta WHERE key='faults_in_a_row'").fetchone() or ['0'])[0]) + 1
            conn.execute("INSERT INTO meta (key, value) VALUES ('faults_in_a_row', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(n),))
            if n >= L.FAULTS_IN_A_ROW_MAX:
                conn.execute("INSERT INTO meta (key, value) VALUES ('fault_hold', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                             (f'{n} tick faults in a row',))
            L.notice(conn, 'tick_fault', type(exc).__name__, f'{n} in a row: {str(exc)[:400]}'
                     + ('; new work holds until life-ctl.py clear-fault' if n >= L.FAULTS_IN_A_ROW_MAX else ''))
        except sqlite3.Error:
            pass
        if tick is not None:
            tick.disposition = 'fault'
        return EXIT_FAULT
    finally:
        done.set()
        procs.kill_all('cleanup')
        if tick is not None:
            try:
                tick.write_status(tick.disposition)
            except Exception:  # noqa: BLE001 - status is best effort; its absence shows as an old tick_finished_at
                pass
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
