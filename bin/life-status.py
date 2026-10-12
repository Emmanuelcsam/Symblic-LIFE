#!/usr/bin/env python3
"""LIFE status for the operator. Read-only: opens the registry with mode=ro inside ONE read transaction (one consistent
registry snapshot), reads the control switches separately, writes nothing, calls nothing.

    life-status.py           control, governor, budgets, live cells, live runs, open notices
    life-status.py --json    the same as one JSON object

Exit 0 when the registry and the control files were read; 1 UNKNOWN (not seeded, a seed that did not finish, a
registry schema other than life_common.SCHEMA_VERSION, not exactly one governor-or-none and one active release row,
the registry unreadable, or ARMED malformed or unreadable: an unknown grant is never shown as an ordinary disarm): no
traceback, no invented state; 2 usage (any argument but --json, or more than one). The registry and the control switches are two samples, each with its
own time (registry_sampled_at, control_sampled_at); when ARMED, STOP or FREEZE changes while the registry is read, the
control is read again once and the output says so.
Every string from the registry, identifiers included, is printed through life_common.one_line (control
characters removed, length capped); the JSON columns of the governor (hot, reasons, node_rest) are decoded first and
--json keeps them as JSON lists and objects.
"""
import sys
sys.dont_write_bytecode = True                  # no .pyc is ever written under bin/ (kit_sha256 hashes __pycache__)
import json  # noqa: E402
import os  # noqa: E402
import sqlite3  # noqa: E402
import time  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import life_common as L  # noqa: E402


def age(t):
    if not t:
        return 'never'
    s = max(0, L.now() - int(t))
    return f'{s}s ago' if s < 2 * 60 else f'{s // 60}m ago' if s < 2 * L.HOUR else f'{s // L.HOUR}h ago'


def clean(row, limit=300):
    return {k: (L.one_line(v, limit) if isinstance(v, str) else v) for k, v in dict(row).items()}


def governor_view(gov):
    """The governor row with its JSON columns decoded (a column that does not decode is shown as UNKNOWN)."""
    out = clean(gov)
    for key in ('hot', 'reasons', 'node_rest'):
        try:
            out[key] = json.loads(gov[key])
        except (TypeError, ValueError):
            out[key] = 'UNKNOWN'
    return out


def main(argv):
    if argv not in ([], ['--json']):
        print('usage: life-status.py [--json]')
        return 2
    try:
        ctl_before = L.control_state()
        conn = L.connect(readonly=True)
        conn.execute('BEGIN')
        gov = conn.execute('SELECT * FROM governor WHERE id=1').fetchone()
        rel = conn.execute('SELECT release FROM releases WHERE active=1').fetchone()
        budget = conn.execute('SELECT * FROM budget WHERE day=?', (L.utc_day(),)).fetchone()
        cells = conn.execute("SELECT * FROM cells WHERE state != 'retired' ORDER BY organ, cell_id").fetchall()
        queued = {r[0]: r[1] for r in conn.execute("SELECT cell_id, COUNT(*) FROM items WHERE state='queued' GROUP BY cell_id")}
        runs = conn.execute("SELECT * FROM runs WHERE state IN ('submitting','live','submit_unknown') ORDER BY submitted_at").fetchall()
        notes = conn.execute("SELECT * FROM notices WHERE state='open' ORDER BY at").fetchall()
        unassigned = conn.execute("SELECT COUNT(*) FROM items WHERE state='queued' AND cell_id IS NULL").fetchone()[0]
        meta = {r['key']: r['value'] for r in conn.execute("SELECT key, value FROM meta WHERE key IN ('tick_no','fault_hold',"
                                                            "'canary_failed','codebase_branch','schema','seed_complete',"
                                                            "'working_tick_no')")}
        releases = conn.execute('SELECT COUNT(*) FROM releases WHERE active=1').fetchone()[0]
        conn.execute('COMMIT')
        if meta.get('schema') != L.SCHEMA_VERSION or meta.get('seed_complete') != '1' or releases != 1:
            raise ValueError(f'registry schema {meta.get("schema")!r}, seed_complete {meta.get("seed_complete")!r}, '
                             f'{releases} active release(s): not a finished seed of this kit')
        armed_state, _armed = L.armed_read()
        if armed_state in ('malformed', 'unreadable'):
            raise ValueError(f'control/ARMED is {armed_state}')
        registry_at = L.now()
        conn.close()
        ctl_after = L.control_state()
        reread = {k: ctl_before[k] for k in ('stop', 'freeze', 'armed')} != {k: ctl_after[k] for k in ('stop', 'freeze', 'armed')}
        ctl = L.control_state() if reread else ctl_after
        control_at = L.now()
    except (sqlite3.Error, OSError, ValueError) as exc:
        print(f'LIFE status UNKNOWN: {L.one_line(str(exc), 200)}')
        return 1
    data = {'at': L.now(), 'registry_sampled_at': registry_at, 'control_sampled_at': control_at,
            'control_changed_while_reading': reread, 'control': ctl, 'release': rel[0] if rel else None, 'tick_no': meta.get('tick_no'), 'codebase_branch': L.one_line(meta.get('codebase_branch'), 100),
            'fault_hold': L.one_line(meta.get('fault_hold'), 200), 'canary_failed': L.one_line(meta.get('canary_failed'), 300),
            'governor': governor_view(gov) if gov else None, 'budget': dict(budget) if budget else None,
            'working_tick_no': meta.get('working_tick_no'),
            'cells': [dict(clean(c, 120), queued=queued.get(c['cell_id'], 0)) for c in cells], 'unassigned': unassigned,
            'runs': [clean(r) for r in runs], 'notices': [clean(n) for n in notes]}
    if argv == ['--json']:
        print(json.dumps(data, indent=1, sort_keys=True, default=str))
        return 0
    state = ('STOP' if ctl['stop'] else 'frozen' if ctl['freeze'] else 'armed' if ctl['admit']
             else 'armed, KIT, PLATFORM OR DECISIONS CHANGED (observe only)' if ctl['armed'] else 'disarmed (observe only)')
    print(f'LIFE {time.strftime("%Y-%m-%d %H:%M:%S")}  release {data["release"]}  tick {L.one_line(data["tick_no"], 12)}  {state}'
          f'  selfdev {"armed" if ctl["selfdev"] else "off"}  codebase branch {data["codebase_branch"]}')
    if data['fault_hold'] or data['canary_failed']:
        print(f'  HOLD: {data["fault_hold"] or ""} {data["canary_failed"] or ""}')
    g = data['governor']
    if g:
        print(f'  governor {g["state"]} (sampled {age(g["at"])}): {g["continuous_seconds"]}s loaded, {g["quiet_seconds"]}s quiet, '
              f'hot {L.one_line(json.dumps(g["hot"]), 80)}, resting {L.one_line(json.dumps(g["node_rest"]), 80)}, '
              f'reasons {L.one_line(json.dumps(g["reasons"]), 200)}')
    if budget:
        print(f'  today: program runs {budget["program_runs"]}/{L.PROGRAM_RUNS_PER_DAY}, model calls {budget["model_calls"]}/'
              f'{L.MODEL_CALLS_PER_DAY}, agent runs {budget["agent_runs"]}/{L.AGENT_RUNS_PER_DAY}, bench jobs '
              f'{budget["bench_jobs"]}/{L.BENCH_JOBS_PER_DAY}, births {budget["births"]}/{L.BIRTHS_PER_DAY}')
    print(f'  cells ({len(cells)} live, {unassigned} unassigned item(s)):')
    for c in data['cells']:
        print(f'    {c["cell_id"]:24} {c["state"]:11} {c["node"]:7} queued {c["queued"]:4} done {c["items_done"]:5} '
              f'fail-run {c["failures_in_a_row"]}  {L.one_line(c["focus"], 60)}')
    for r in data['runs']:
        print(f'  run {r["run_id"]} {r["state"]} {r["organ"]} on {r["node"]} submitted {age(r["submitted_at"])}')
    for n in data['notices']:
        print(f'  notice {n["notice_id"]} x{n["count"]} {n["kind"]}: {n["subject"]}: {n["text"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
