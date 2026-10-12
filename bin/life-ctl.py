#!/usr/bin/env python3
"""LIFE operator control. Every lifecycle authority a model or agent never has lives here, run by the operator.

  command                                         lock   effect
  seed --confirm START [--branch NAME]            yes    create (or finish creating) STATE, the registry, release 1, the
                                                         three agent workspaces and the 8 seed cells; NAME (default main)
                                                         is the branch the codebase organ tracks; starts nothing
  arm --confirm ARM-UNTESTED --decisions HEX16    ctl    allow new work for THIS boot with THIS kit, platform and
                                                         DECISIONS.md (HEX16 = the first 16 hex of sha256(DECISIONS.md),
                                                         which you read); needs a finished seed, VALIDATE.sh STATIC PASS,
                                                         the installed units as the kit defines them and the sandbox probe;
                                                         the confirm word stays while the admission tests (LIFE.md GAP 8)
                                                         are absent
  disarm | freeze | thaw                          no     forbid new work / pause / resume
  selfdev-arm | selfdev-disarm                    no     allow / forbid selfdev agent runs
  stop                                            ctl*   STOP: end processes, ask to cancel every LIFE run and job, DISARM
  unstop                                          ctl    remove STOP (then arm again)
  clear-fault                                     yes    end the fault hold (three tick faults in a row)
  command "TEXT"                                  no     one operator command into the inbox (6..4000 bytes, no credential)
  notices | ack ID                                ack    open operator notices; acknowledge one
  show ITEM | report COMMAND                      no     print an item (payload as data) / a command's report
  approve ITEM --confirm APPROVE                  yes    a web- or model-derived lesson/request may start its agent run
                                                         (the approval binds its current text; its taint stays)
  apply PATCH --confirm APPLY [--unreviewed] [--moved-base]   yes   apply a gated patch to the live checkout (no commit)
  recover-apply PATCH --confirm RECOVER           yes    finish undoing an interrupted apply (before-bytes back)
  revert PATCH --confirm REVERT                   yes    undo an applied patch when no touched file changed since
  adopt PROPOSAL --confirm ADOPT [--unreviewed]   yes    a genome proposal becomes the next active release
  new-release --confirm RELEASE                   yes    the kit's genome/organs/policies become the next active release
  release-cell CELL                               yes    a quarantined cell returns to active (failure streak 0, rungs kept)
  retire CELL [--force]                           yes    retire a cell (aborts its open division; --force for an organ's last
                                                         active cell or a cell with a live run: its cancel is requested and
                                                         the run is abandoned as abandon-run does)
  revive ORGAN NODE                               yes    a new depth-0 cell for an organ with no live cell (one birth)
  requeue ITEM --confirm REQUEUE                  yes    an item that ended owner or failed, or a source that abstained
                                                         (OVERFLOW, EMPTY, fetch refused), is queued again (counters 0)
  abandon-run RUN_ID --confirm ABANDON            yes    a run the platform cannot confirm: its cancel is requested, its row
                                                         ends unknown and collected, its item goes to the operator, its
                                                         workspace is reset
  move CELL NODE                                  yes    move a live cell to another LIFE node (cap NODE_CELL_CAP; refused
                                                         while its workspace is busy or it is dividing)
  release-hold NODE                               yes    remove every hold of a node (an unknown or lost benchmark job included)
  canaries                                        yes    run the canary round now; clears or sets the canary hold
  gate-selftest TEST_ID                           yes    the sandbox probe, then the gate on an idle active codebase clone
                                                         twice: a harmless comment must PASS, a syntax error must FAIL at
                                                         devcheck; a PASS proves the codebase gate for this kit and these
                                                         platform files (meta gate_selftest; without it codebase gates wait)
  restore registry|organism FILE --confirm RESTORE   yes  replace a database with a backup (STOP must be present)
  forget-migration ID --confirm FORGET            yes    after a restore: an applied migration the organism lacks is
                                                         marked refused, so the database organ stops holding
  purge-refused --confirm PURGE                   no     delete the refused inbox files (operator-private copies)
  contract                                        no     print the platform contract problems ('contract holds' when none)

Lock = the tick's flock: life-ctl waits up to CTL_LOCK_WAIT s (a tick may hold it up to TICK_HARD s), printing a line
every CTL_LOCK_PROGRESS s, then refuses. ctl = the short control lock (STATE/control.lock): stop, unstop and the final
publication of ARMED by arm are serialized under it, and arm refuses when a STOP happened after it began (the
STOP_GENERATION file). *stop never waits for the tick's lock: it asks the CLI and the job API to cancel itself and
leaves the registry rows to the tick when the lock is busy. Commands that start processes (seed, arm, apply, adopt,
new-release, canaries, gate-selftest) refuse while STOP is present. Exit 0 done, 1 refused (the reason is printed),
2 usage. Unknown arguments fail before any change. Calls no model and starts no agent.
"""
import sys
sys.dont_write_bytecode = True                  # no .pyc is ever written under bin/ (kit_sha256 hashes __pycache__)
import fcntl  # noqa: E402
import importlib.machinery  # noqa: E402
import importlib.util
import json
import os
import re
import secrets
import shutil
import sqlite3
import stat
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import life_common as L  # noqa: E402

OK, REFUSED, USAGE = 0, 1, 2


def say(msg):
    print(f'life-ctl: {msg}', flush=True)


def lock(wait=L.CTL_LOCK_WAIT):
    """The tick's lock: registry writes from here never interleave with a tick."""
    handle = L.open_lock(L.LOCK_FILE)
    start = time.monotonic()
    shown = start
    while True:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return handle
        except BlockingIOError:
            if time.monotonic() - start > wait:
                raise SystemExit('life-ctl: a tick still holds the lock; try again after it ends') from None
            if time.monotonic() - shown >= L.CTL_LOCK_PROGRESS:
                shown = time.monotonic()
                say(f'waiting for the running tick to release the lock ({int(shown - start)} s so far)')
            time.sleep(2)


def no_stop(what):
    """Commands that start processes refuse while STOP is present (the shared runner would refuse every process)."""
    if L.stop_present():
        say(f'{what} refused: control/STOP is present or control/ cannot be inspected (life-ctl.py unstop first)')
        return False
    return True


def control_lock():
    """The short control lock (STATE/control.lock): stop, unstop and arm's final publication of ARMED hold it."""
    handle = L.open_lock(L.CONTROL_LOCK)
    fcntl.flock(handle, fcntl.LOCK_EX)
    return handle


def stop_generation():
    try:
        return int(L.read_owner_file(L.STOP_GENERATION_FILE, 32).decode('ascii').strip() or '0')
    except (OSError, ValueError, UnicodeDecodeError):
        return 0


def touch(path, text=''):
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    L.write_atomic(path, text)


def remove(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def git(cwd, *args, check=True, timeout=L.CLONE_TIMEOUT):
    """A trusted git command; in a LIFE workspace only after git_admin_problems found nothing."""
    if cwd != L.REPO:
        problems = L.git_admin_problems(cwd)
        if problems:
            raise SystemExit(f'life-ctl: git refused to run in {cwd}: ' + '; '.join(problems)[:300])
    rc, out, err = L.run_bounded(['git', *L.GIT_SAFE, '-C', cwd, *args], timeout=timeout, env=L.child_env())
    if check and rc != 0:
        raise SystemExit(f'life-ctl: git {" ".join(args[:3])} failed in {cwd}: {err.strip()[:200]}')
    return out


def commit(cwd, message):
    git(cwd, 'add', '-A')
    if git(cwd, 'status', '--porcelain').strip():
        git(cwd, '-c', 'user.name=life', '-c', 'user.email=life@localhost', 'commit', '-q', '-m', message)


def tick_module():
    spec = importlib.util.spec_from_file_location('life_tick', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'life-tick.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def meta(conn, key, default=''):
    row = conn.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
    return row[0] if row else default


def set_meta(conn, key, value):
    if key not in L.META_KEYS:
        raise SystemExit(f'life-ctl: unknown meta key {key}')
    conn.execute('INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, str(value)))


def probe_dir(conn):
    """(folder, temporary): the workspace of the lowest active codebase cell whose clone exists and is not busy, else a
    fresh PROJECTS/.life-probe-<8hex> (mode 0700, removed after the probe). The probe never depends on the seed clone,
    which retires at its first division."""
    for c in conn.execute("SELECT * FROM cells WHERE organ='codebase' AND state='active' ORDER BY depth, cell_id").fetchall():
        ws = c['workspace']
        busy = conn.execute("SELECT 1 FROM runs WHERE cell_id=? AND state IN ('submitting','live','submit_unknown')",
                            (c['cell_id'],)).fetchone() or conn.execute(
            "SELECT 1 FROM items WHERE cell_id=? AND state IN ('queued','running') AND stage IN ('gate','apply')",
            (c['cell_id'],)).fetchone()
        if ws and os.path.isdir(os.path.join(ws, '.git')) and not busy:
            return ws, False
    path = os.path.join(L.PROJECTS, f'.life-probe-{secrets.token_hex(4)}')
    os.makedirs(path, mode=0o700)
    return path, True


def sandbox_probe(ws):
    """The sandbox probe in `ws` with the gate's own read-exec grants (devcheck_tools): first the trusted side proves
    every target exists and answers outside the sandbox (a sentinel file written in STATE, STATE, ~/.ssh, the live
    checkout, 127.0.0.1:8080), then SANDBOX_PROBE runs inside (an empty temporary HOME) and every denial must be the
    policy's PermissionError (a missing target or a refused connection is inconclusive: rc 2). Returns (rc, text)."""
    import tempfile
    sentinel = os.path.join(L.STATE, f'.probe-sentinel-{secrets.token_hex(4)}')
    L.write_atomic(sentinel, 'LIFE sandbox probe sentinel\n')
    home = tempfile.mkdtemp(prefix='life-probe-')
    try:
        problems = L.sandbox_probe_targets(sentinel)
        if problems:
            return 2, 'sandbox probe: INCONCLUSIVE: ' + '; '.join(problems)
        env, rx, refused = L.devcheck_tools()
        if refused:
            return 1, 'sandbox probe: BROKEN: a devcheck tool resolves outside the allowed tool roots: ' + ', '.join(refused)
        argv = L.sandbox_argv(ws, home, [L.SYS_PY, '-I', '-c', L.SANDBOX_PROBE, sentinel, str(os.getpid()), L.STATE,
                                         '/home/operator/.ssh', L.REPO], rx=rx, env_extra=env)
        rc, out, err = L.run_bounded(argv, timeout=L.CANARY_TIMEOUT, cwd=ws, env=L.child_env())
        return rc, ((out + err).strip() + f' | read-exec grants: {", ".join(rx) or "none"}')
    finally:
        shutil.rmtree(home, ignore_errors=True)
        try:
            os.remove(sentinel)
        except OSError:
            pass


UNIT_PROPERTIES = (('life-tick.service', 'ExecStart', '/usr/bin/python3 -I -B ' + L.KIT + '/bin/life-tick.py'),
                   ('life-tick.service', 'MemoryMax', str(1024 ** 3)), ('life-tick.service', 'TasksMax', str(L.TICK_TASKS_MAX)),
                   ('life-tick.service', 'KillMode', 'control-group'), ('life-tick.service', 'Restart', 'no'),
                   ('life-tick.service', 'Slice', 'work.slice'), ('life-tick.service', 'Type', 'oneshot'),
                   ('life-tick.timer', 'Persistent', 'no'))


def unit_problems():
    """The installed, LOADED units must be the kit's: each property of UNIT_PROPERTIES (systemctl --user show) has
    its kit value (ExecStart is matched as a substring of systemd's argv display), TimeoutStartUSec is UNIT_TIMEOUT
    seconds, SuccessExitStatus lists 1 3 4 5 6, and the timer re-arms OnUnitInactiveSec TICK_SECONDS after a tick."""
    out = []
    for unit, prop, want in UNIT_PROPERTIES:
        rc, got, _ = L.run_bounded(['systemctl', '--user', 'show', unit, '-p', prop, '--value'], timeout=L.CANCEL_TIMEOUT,
                                   env=L.scope_env(), tracked=False)
        got = (got or '').strip()
        if rc != 0 or (want not in got if prop == 'ExecStart' else got != want):
            out.append(f'{unit} {prop} is {got[:80]!r}, the kit says {want!r}')
    rc, got, _ = L.run_bounded(['systemctl', '--user', 'show', 'life-tick.service', '-p', 'TimeoutStartUSec', '-p',
                                'SuccessExitStatus', '--value'], timeout=L.CANCEL_TIMEOUT, env=L.scope_env(), tracked=False)
    lines = (got or '').splitlines()
    if rc != 0 or len(lines) < 2 or lines[0].strip() not in (f'{L.UNIT_TIMEOUT // 60}min', f'{L.UNIT_TIMEOUT}s') \
            or sorted(re.findall(r'\b\d+\b', lines[1])) != ['1', '3', '4', '5', '6']:
        out.append(f'life-tick.service TimeoutStartUSec/SuccessExitStatus are {lines[:2]!r}, the kit says '
                   f'{L.UNIT_TIMEOUT} s and 1 3 4 5 6')
    rc, got, _ = L.run_bounded(['systemctl', '--user', 'show', 'life-tick.timer', '-p', 'TimersMonotonic', '--value'],
                               timeout=L.CANCEL_TIMEOUT, env=L.scope_env(), tracked=False)
    if rc != 0 or f'OnUnitInactiveUSec={L.TICK_SECONDS // 60}min' not in (got or ''):
        out.append(f'life-tick.timer does not re-arm OnUnitInactiveSec={L.TICK_SECONDS} ({(got or "").strip()[:120]!r})')
    return out


# ------------------------------------------------------------------------------------------- releases

def copy_release(src_dir, dest_dir):
    os.makedirs(dest_dir, mode=0o700)
    for sub in L.RELEASE_DIRS:
        shutil.copytree(os.path.join(src_dir, sub), os.path.join(dest_dir, sub),
                        ignore=shutil.ignore_patterns('fixtures.json', '__pycache__'))


def check_release(directory):
    """The ONE release validator (seed, adopt, new-release; VALIDATE.sh checks the kit with the same rules): the
    organs.json schema; bin/symblic check and the placement rule on every program; the distill-lesson program enum
    names no protected program; every raw agent template lints with zero findings without a root and starts each line
    with a symblic_autogen verb; every agent template renders with the kit's organs/fixtures.json AND with the largest
    legal values (life_common.worst_values) into two lint-clean statements within STATEMENT_MAX; its policy is the fixed
    policy, and policy_flags() fed through bin/symblic-task's own parser normalizes to the same sha256."""
    try:
        problems = L.organs_problems(json.load(open(os.path.join(directory, 'organs', 'organs.json'), encoding='utf-8'),
                                               object_pairs_hook=L._no_dup_keys))
    except (OSError, ValueError) as exc:
        return [f'organs.json: {exc}']
    for program in L.PROGRAMS:
        path = os.path.join(directory, 'genome', f'{program}.sym')
        rc, _out, _err = L.run_bounded([L.SYMBLIC, 'check', path], timeout=L.GIT_TIMEOUT, env=L.child_env(), tracked=False)
        if rc != 0:
            problems.append(f'{program}.sym: bin/symblic check failed')
        try:
            problems += [f'{program}.sym: {p}' for p in L.genome_placement_problems(open(path, encoding='utf-8').read())]
        except OSError as exc:
            problems.append(f'{program}.sym: {exc}')
    try:
        distill = open(os.path.join(directory, 'genome', 'distill-lesson.sym'), encoding='utf-8').read()
        problems += [f'distill-lesson.sym offers the protected program {p}' for p in L.SELFDEV_PROTECTED
                     if re.search(r'ask program: one of \{[^}]*\b' + re.escape(p) + r'\b', distill)]
    except OSError as exc:
        problems.append(f'distill-lesson.sym: {exc}')
    if L.REPO not in sys.path:
        sys.path.insert(0, L.REPO)
    from symblic.autogen import policy as A
    loader = importlib.machinery.SourceFileLoader('symblic_task_cli', L.TASK)
    spec = importlib.util.spec_from_loader('symblic_task_cli', loader)
    cli = importlib.util.module_from_spec(spec)
    loader.exec_module(cli)
    fixtures = json.load(open(os.path.join(L.KIT, 'organs', 'fixtures.json'), encoding='utf-8'))
    for organ in L.AGENT_ORGANS:
        try:
            raw = A.statements(open(os.path.join(directory, 'organs', f'{organ}.lines.txt'), encoding='utf-8').read())
            findings = A.lint(raw)
            if findings:
                problems.append(f'{organ} raw template lint: ' + '; '.join(f'{lv} line {n}: {m}' for lv, n, m in findings)[:300])
            if any(line.split()[0].lower() not in A.VERBS for line in raw):
                problems.append(f'{organ} raw template: a line does not start with a symblic_autogen verb')
            lines, policy, sha = L.render_run(directory, organ, fixtures[organ])
            opts, _args = cli.parse(L.policy_flags(policy))
            if A.normalize(cli.autogen_policy(opts, lines))['sha256'] != sha:
                problems.append(f'{organ} template: the bin/symblic-task round trip changes the policy sha256')
            L.render_run(directory, organ, L.worst_values(organ, fixtures))
        except (ValueError, KeyError, OSError) as exc:
            problems.append(f'{organ} template: {exc}')
    return problems


def build_release(conn, fill):
    """Build the next release in a private temporary folder, let `fill(tmp)` write it, validate it, then rename it
    into place; returns (number, directory) or raises SystemExit with the problems."""
    top = conn.execute('SELECT MAX(release) FROM releases').fetchone()[0] or 0
    dest = os.path.join(L.RELEASES, str(top + 1))
    if os.path.lexists(dest):
        raise SystemExit(f'life-ctl: {dest} exists without a registry row: move it aside, then retry')
    tmp = os.path.join(L.RELEASES, f'.tmp-{top + 1}-{secrets.token_hex(4)}')
    try:
        fill(tmp)
        problems = check_release(tmp)
        if problems:
            raise SystemExit('life-ctl: refused: ' + '; '.join(problems))
        os.rename(tmp, dest)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return top + 1, dest


def add_release(conn, number, directory, source, note):
    manifest = L.release_manifest(directory)
    with L.Tx(conn):
        conn.execute('UPDATE releases SET active=0 WHERE active=1')
        conn.execute('INSERT INTO releases (release, at, source, manifest, active, note) VALUES (?, ?, ?, ?, 1, ?)',
                     (number, L.now(), source, json.dumps(manifest, sort_keys=True), note))
    return number


# ------------------------------------------------------------------------------------------- seed

def seed_workspace(organ, rdir, branch):
    ws = L.workspace_for(L.cell_id(organ, 0, '00000000'))
    if os.path.isdir(os.path.join(ws, '.git')):
        return ''
    if organ == 'codebase':
        tmp = os.path.join(L.PROJECTS, f'.life-tmp-{secrets.token_hex(4)}')
        end = time.monotonic() + L.CLONE_TIMEOUT
        for argv in (['git', *L.GIT_SAFE, 'clone', '-q', '--no-local', '--single-branch', '--branch', branch, '--no-tags',
                      '--no-checkout', L.REPO, tmp],
                     ['git', *L.GIT_SAFE, '-C', tmp, 'sparse-checkout', 'set', '--no-cone', '/*', '!/.backups/'],
                     ['git', *L.GIT_SAFE, '-C', tmp, 'checkout', '-q', branch]):
            left = int(end - time.monotonic())
            rc, _o, err = L.run_bounded(L.scope_argv(argv, runtime=max(1, left), name='clone'), timeout=left, env=L.scope_env())
            if rc != 0:
                shutil.rmtree(tmp, ignore_errors=True)
                return f'git failed: {err.strip()[:200]}'
        os.rename(tmp, ws)
        return ''
    rc, out, err = L.run_bounded([L.TASK, 'workspace', os.path.basename(ws)], timeout=L.GIT_TIMEOUT, env=L.child_env())
    if rc != 0 or not os.path.isdir(os.path.join(ws, '.git')):
        return f'symblic-task workspace failed: {(out + err).strip()[:300]}'
    if L.git_admin_problems(ws):
        return 'the new workspace failed the git administrative check: ' + '; '.join(L.git_admin_problems(ws))[:300]
    if organ == 'selfdev':
        for sub in ('genome', 'genome-base'):
            shutil.copytree(os.path.join(rdir, 'genome'), os.path.join(ws, sub), dirs_exist_ok=True)
    else:
        os.makedirs(os.path.join(ws, 'migrations'), exist_ok=True)
        L.write_atomic(os.path.join(ws, 'migrations', '.keep'), '', 0o644)
        org = sqlite3.connect(f'file:{L.ORGANISM}?mode=ro', uri=True)
        try:
            text = L.snapshot_sql(org)
        finally:
            org.close()
        L.write_atomic(os.path.join(ws, 'schema-snapshot.sql'), text, 0o644)
        L.write_atomic(os.path.join(ws, 'MIGRATION-RULES.txt'), L.MIGRATION_RULES, 0o644)
    commit(ws, 'LIFE seed')
    return ''


def seed(args):
    if not (args[:2] == ['--confirm', 'START'] and (len(args) == 2 or (len(args) == 4 and args[2] == '--branch'))):
        say('seed needs --confirm START [--branch NAME]')
        return USAGE
    branch = args[3] if len(args) == 4 else 'main'
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,99}', branch) or '..' in branch:
        say('the branch name has the wrong form')
        return USAGE
    if not no_stop('seed'):
        return REFUSED
    resuming = False
    if os.path.isfile(L.REGISTRY):
        conn = L.connect()
        has_meta = conn.execute("SELECT 1 FROM sqlite_master WHERE name='meta'").fetchone()
        if has_meta and meta(conn, 'seed_complete') == '1':
            say('already seeded; nothing changed. Seeding is never a recovery step.')
            return OK
        if has_meta and meta(conn, 'seed_kit_sha256') and meta(conn, 'seed_kit_sha256') != L.kit_sha256():
            say('an earlier seed started with another kit: to start over, remove ~/.local/state/life AND the folders '
                f'{L.PROJECTS}/life-codebase-0-00000000, life-selfdev-0-00000000 and life-database-0-00000000 by hand '
                '(nothing ran yet), then seed again')
            return REFUSED
        if has_meta and meta(conn, 'codebase_branch') and meta(conn, 'codebase_branch') != branch:
            say(f'an earlier seed tracks branch {meta(conn, "codebase_branch")}; resume with the same --branch')
            return REFUSED
        resuming = True
        say('an earlier seed did not finish: resuming it (every step is idempotent)')
    rc, _out, _err = L.run_bounded(['git', '-C', L.REPO, 'rev-parse', '--verify', '-q', f'refs/heads/{branch}'],
                                   timeout=L.GIT_TIMEOUT, env=L.child_env())
    if rc != 0:
        say(f'the live checkout has no branch {branch}; name the branch the codebase organ should track with --branch')
        return REFUSED
    problems = L.contract_problems()
    if problems:
        say('platform contract problems: ' + '; '.join(problems))
        return REFUSED
    rc, out, _err = L.run_bounded(['bash', os.path.join(L.KIT, 'VALIDATE.sh')], timeout=L.VALIDATE_TIMEOUT, env=L.child_env())
    if rc != 0:
        say('VALIDATE.sh did not pass:\n' + out[-2000:])
        return REFUSED
    L.ensure_dirs()
    for path in L.STATE_DIRS:
        os.chmod(path, 0o700)
    handle = lock(L.SEED_LOCK_WAIT)
    conn = L.connect()
    L.apply_schema(conn, os.path.join(L.KIT, 'db', 'life.sql'))
    org = sqlite3.connect(L.ORGANISM)
    with open(os.path.join(L.KIT, 'db', 'organism.sql'), encoding='utf-8') as f:
        org.executescript(f.read())
    org.close()
    for path in (L.REGISTRY, L.ORGANISM):
        os.chmod(path, 0o600)
    with L.Tx(conn):
        for key, value in {'schema': L.SCHEMA_VERSION, 'seeded_at': str(L.now()), 'codebase_branch': branch,
                           'seed_kit_sha256': L.kit_sha256(),
                           'platform_commit': git(L.REPO, 'rev-parse', 'HEAD').strip()}.items():
            conn.execute('INSERT OR IGNORE INTO meta (key, value) VALUES (?, ?)', (key, value))
        conn.execute("INSERT OR IGNORE INTO meta (key, value) VALUES ('tick_no', '0')")
    if not conn.execute('SELECT 1 FROM releases').fetchone():
        number, rdir = build_release(conn, lambda tmp: copy_release(L.KIT, tmp))
        add_release(conn, number, rdir, 'kit', 'seed')
    _, rdir, _ = L.active_release(conn)
    organs = L.load_organs(rdir)
    for organ in L.AGENT_ORGANS:
        why = seed_workspace(organ, rdir, branch)
        if why:
            say(f'could not create the {organ} workspace: {why}')
            return REFUSED
    with L.Tx(conn):
        for organ in L.ORGANS:
            spec = organs['organs'][organ]
            cid = L.cell_id(organ, 0, '00000000')
            if conn.execute('SELECT 1 FROM cells WHERE cell_id=?', (cid,)).fetchone():
                continue
            conn.execute("INSERT INTO cells (cell_id, organ, kind, parent_id, depth, focus, node, workspace, state, born_at,"
                         " release) VALUES (?, ?, ?, NULL, 0, ?, ?, ?, 'active', ?, 1)",
                         (cid, organ, spec['kind'], spec['seed_focus'], spec['seed_node'], L.workspace_for(cid), L.now()))
            conn.execute("INSERT INTO cell_events (cell_id, at, event, detail) VALUES (?, ?, 'born', 'seed')", (cid, L.now()))
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('seed_complete', '1')")
    handle.close()
    say(('resumed and finished the seed' if resuming else 'seeded') + f': 8 cells, release 1, codebase branch {branch}, STATE '
        + L.STATE + '. Nothing runs yet. Next: README steps 3-6.')
    return OK


def arm(args):
    """Validate everything (seed, DECISIONS hash, contract, STATE, VALIDATE.sh, the installed units, the sandbox probe),
    then, under the short control lock, re-check that no STOP exists and that no STOP happened since this arm began
    (STOP_GENERATION unchanged) before ARMED is published. A STOP during the validation therefore always wins."""
    if len(args) != 4 or args[:2] != ['--confirm', 'ARM-UNTESTED'] or args[2] != '--decisions':
        say('arm needs --confirm ARM-UNTESTED --decisions HEX16 (the admission tests, LIFE.md GAP 8, do not exist yet; '
            'HEX16 = the first 16 hex of sha256(DECISIONS.md) after you read it)')
        return USAGE
    if not no_stop('arm'):
        return REFUSED
    generation = stop_generation()
    conn = L.connect(readonly=True)
    if meta(conn, 'seed_complete') != '1':
        say('refused: the seed is not finished (run life-seed.sh again)')
        return REFUSED
    decisions = L.decisions_sha256()
    if args[3] != decisions[:16]:
        say(f'refused: DECISIONS.md has sha256 {decisions[:16]}..., not {args[3]}: read DECISIONS.md, then pass its hash')
        return REFUSED
    problems = L.contract_problems() + L.state_problems()
    if problems:
        say('refused: ' + '; '.join(problems))
        return REFUSED
    rc, out, _err = L.run_bounded(['bash', os.path.join(L.KIT, 'VALIDATE.sh')], timeout=L.VALIDATE_TIMEOUT, env=L.child_env())
    if rc != 0:
        say('refused: VALIDATE.sh did not pass:\n' + out[-2000:])
        return REFUSED
    problems = unit_problems()
    if problems:
        say('refused: the installed units are not the kit\'s (README step 5): ' + '; '.join(problems))
        return REFUSED
    ws, temporary = probe_dir(conn)
    try:
        rc, out = sandbox_probe(ws)
    finally:
        if temporary:
            shutil.rmtree(ws, ignore_errors=True)
    if rc != 0:
        say(f'refused: the sandbox probe did not hold (rc {rc}): {out[-400:]}')
        return REFUSED
    print(out)
    handle = control_lock()
    try:
        if L.stop_present() or stop_generation() != generation:
            say('refused: a STOP happened while arm was validating; nothing was armed')
            return REFUSED
        touch(L.ARMED_FILE, json.dumps({'boot_id': L.boot_id(), 'kit_sha256': L.kit_sha256(),
                                        'platform_sha256': L.platform_sha256(), 'decisions_sha256': decisions}) + '\n')
    finally:
        handle.close()
    say('armed for this boot, this kit, these platform files and these decisions; a reboot or any change disarms')
    return OK


# ------------------------------------------------------------------------------------------- patches

def journal_path(pid):
    return os.path.join(L.APPLIED, pid, 'applied.json')


def file_hash(rel):
    path = os.path.join(L.REPO, rel)
    return L.file_sha(path) if os.path.isfile(path) and not os.path.islink(path) else None


def live_path_problems(rel):
    """A path apply or revert may write in the live checkout: every parent component a real directory (no symlink),
    the file itself absent or a regular file with exactly one link (a hardlink would change another file too)."""
    parts = rel.split('/')
    for k in range(1, len(parts)):
        p = os.path.join(L.REPO, *parts[:k])
        if os.path.islink(p) or (os.path.lexists(p) and not os.path.isdir(p)):
            return f'{rel}: the parent {"/".join(parts[:k])} is not a real directory'
    path = os.path.join(L.REPO, rel)
    if os.path.lexists(path):
        st = os.lstat(path)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            return f'{rel}: not a regular file with one link'
    return ''


def apply_patch(pid, args):
    flags = set(args) - {'--confirm', 'APPLY'}
    if args[:2] != ['--confirm', 'APPLY'] or not flags <= {'--unreviewed', '--moved-base'} or len(args) != 2 + len(flags):
        say('apply needs PATCH_ID --confirm APPLY [--unreviewed] [--moved-base]')
        return USAGE
    if not no_stop('apply'):
        return REFUSED
    handle = lock()
    conn = L.connect()
    row = conn.execute('SELECT * FROM patches WHERE patch_id=?', (pid,)).fetchone()
    if not row or row['state'] not in ('ready', 'owner') or (row['state'] == 'owner' and '--unreviewed' not in flags):
        say(f'patch {pid} is not ready (state {row["state"] if row else "unknown"}; an unreviewed patch needs --unreviewed)')
        return REFUSED
    if os.path.exists(journal_path(pid)):
        say(f'{pid} has an apply record already ({json.load(open(journal_path(pid), encoding="utf-8")).get("state")}): '
            'revert or recover-apply it first (a reverted patch moves its record to history and may be applied again)')
        return REFUSED
    live_branch = git(L.REPO, 'rev-parse', '--abbrev-ref', 'HEAD', check=False).strip()
    if live_branch != meta(conn, 'codebase_branch') and '--moved-base' not in flags:
        say(f'refused: the live checkout is on {live_branch or "a detached HEAD"}, LIFE tracks {meta(conn, "codebase_branch")}; '
            'switch branches or add --moved-base')
        return REFUSED
    diff = os.path.join(L.BUNDLES, 'patches', pid, 'patch.diff')
    with open(diff, encoding='utf-8') as fh:
        text = fh.read()
    if L.sha16(text) != pid:
        say('the bundle diff no longer matches its id; refused')
        return REFUSED
    files = json.loads(row['files'])
    denied = [f for f in files if L.GATE_DENY_RX.match(f)]
    if denied:
        say('refused: protected paths: ' + ', '.join(denied))
        return REFUSED
    bad = [p for p in (live_path_problems(rel) for rel in files) if p]
    if bad:
        say('refused: ' + '; '.join(bad))
        return REFUSED
    rc, summary, _ = L.run_bounded(['git', *L.GIT_SAFE, '-C', L.REPO, 'apply', '--summary', diff], timeout=L.GIT_TIMEOUT,
                                   env=L.child_env())
    if rc != 0 or re.search(r'mode change|create mode 120000|create mode 160000|delete mode 120000|symbolic link', summary):
        say('refused: the patch changes a file mode or creates a symlink or submodule: ' + summary.strip()[:200])
        return REFUSED
    moved = []
    for rel in files:      # blob ids, not decoded text: any byte, any size
        rc, base_blob, _ = L.run_bounded(['git', *L.GIT_SAFE, '-C', L.REPO, 'rev-parse', '-q', '--verify',
                                          f'{row["base_commit"]}:{rel}'], timeout=L.GIT_TIMEOUT, env=L.child_env())
        path = os.path.join(L.REPO, rel)
        live_blob = ''
        if os.path.isfile(path):
            _rc, live_blob, _ = L.run_bounded(['git', *L.GIT_SAFE, '-C', L.REPO, 'hash-object', '--no-filters', '--', rel],
                                              timeout=L.GIT_TIMEOUT, env=L.child_env())
        if (base_blob.strip() if rc == 0 else '') != live_blob.strip():
            moved.append(rel)
    if moved and '--moved-base' not in flags:
        say('refused: these files differ from the patch base in the live checkout (someone changed them): '
            + ', '.join(moved) + '. Read the change; add --moved-base to apply anyway.')
        return REFUSED
    rc, _out, err = L.run_bounded(['git', *L.GIT_SAFE, '-C', L.REPO, 'apply', '--check', diff], timeout=L.GIT_TIMEOUT, env=L.child_env())
    if rc != 0:
        say('git apply --check refused it against the live checkout: ' + err[:300])
        return REFUSED
    record = {'patch_id': pid, 'at': L.now(), 'state': 'intent', 'files': {}, 'prior_state': row['state'],
              'unverified_base': bool(moved) or '--moved-base' in flags}
    before_dir = os.path.join(L.APPLIED, pid, 'before')
    for rel in files:
        path = os.path.join(L.REPO, rel)
        record['files'][rel] = {'before': file_hash(rel),
                                'mode': oct(stat.S_IMODE(os.lstat(path).st_mode)) if os.path.isfile(path) else None}
        if os.path.isfile(path):
            os.makedirs(os.path.dirname(os.path.join(before_dir, rel)), mode=0o700, exist_ok=True)
            shutil.copy2(path, os.path.join(before_dir, rel))
    os.makedirs(os.path.join(L.APPLIED, pid), mode=0o700, exist_ok=True)
    L.write_atomic(journal_path(pid), json.dumps(record, indent=1, sort_keys=True))
    rc, _out, err = L.run_bounded(['git', *L.GIT_SAFE, '-C', L.REPO, 'apply', diff], timeout=L.GIT_TIMEOUT, env=L.child_env())
    if rc != 0:
        say('git apply failed after --check passed: run life-ctl.py recover-apply ' + pid + ' --confirm RECOVER: ' + err[:300])
        return REFUSED
    for rel in files:
        record['files'][rel]['after'] = file_hash(rel)
    record['state'] = 'done'
    L.write_atomic(journal_path(pid), json.dumps(record, indent=1, sort_keys=True))
    with L.Tx(conn):
        conn.execute("UPDATE patches SET state='applied', updated_at=? WHERE patch_id=?", (L.now(), pid))
    handle.close()
    say(f'applied {pid} to {L.REPO} ({len(files)} file(s)); nothing committed. Run bin/devcheck there before you commit.')
    if record['unverified_base']:
        say('UNVERIFIED: --moved-base applied the patch to files that differ from the base its gate and review saw; '
            'the gate and review say nothing about this tree (the apply record says unverified_base: true).')
    if row['path_class'] in ('restart_gated', 'mixed', 'other'):
        say('restart-gated: Python/API changes take effect only after you restart the dashboard yourself (./restart-host.sh).')
    if row['path_class'] in ('live_static', 'mixed', 'other'):
        say('static pages are live on write: the change is already served, file by file.')
    return OK


def restore_before(pid, record):
    """Every touched file back to its recorded before-bytes and mode (a file that did not exist is removed: absence is
    restored as absence; an emptied parent directory is left in place)."""
    for rel, sums in record['files'].items():
        path = os.path.join(L.REPO, rel)
        if live_path_problems(rel):
            raise SystemExit('life-ctl: ' + live_path_problems(rel) + ' (nothing more was restored)')
        if sums['before'] is None:
            remove(path)
        else:
            shutil.copyfile(os.path.join(L.APPLIED, pid, 'before', rel), path)
            if sums.get('mode'):
                os.chmod(path, int(sums['mode'], 8))


def expected_after(pid, record):
    """{file: sha256 the patch produces from the before-bytes} (computed in a private temporary folder; an interrupted
    apply recorded no after-hashes)."""
    import tempfile
    tmp = tempfile.mkdtemp(prefix='life-recover-')
    try:
        for rel, sums in record['files'].items():
            if sums['before'] is not None:
                os.makedirs(os.path.dirname(os.path.join(tmp, rel)) or tmp, exist_ok=True)
                shutil.copy2(os.path.join(L.APPLIED, pid, 'before', rel), os.path.join(tmp, rel))
        rc, _o, err = L.run_bounded(['git', *L.GIT_SAFE, 'apply', os.path.join(L.BUNDLES, 'patches', pid, 'patch.diff')],
                                    timeout=L.GIT_TIMEOUT, cwd=tmp, env=L.child_env())
        if rc != 0:
            raise SystemExit('life-ctl: cannot recompute the patched bytes: ' + err[:200])
        return {rel: (L.file_sha(os.path.join(tmp, rel)) if os.path.isfile(os.path.join(tmp, rel)) else None)
                for rel in record['files']}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def undo(pid, record, after, done_state):
    """Shared by revert and recover-apply: every file must be at its before- or after-bytes (an unexpected file stops
    everything before any change); the journal says `reverting` before the first file changes and `done_state` after."""
    unexpected = [rel for rel, sums in record['files'].items() if file_hash(rel) not in (sums['before'], after[rel])]
    if unexpected:
        say('refused: these files hold neither the pre-apply nor the patched bytes (someone else edited them); nothing '
            'was changed: ' + ', '.join(unexpected))
        return REFUSED
    record['state'] = 'reverting'
    L.write_atomic(journal_path(pid), json.dumps(record, indent=1, sort_keys=True))
    restore_before(pid, record)
    record['state'] = done_state
    L.write_atomic(journal_path(pid), json.dumps(record, indent=1, sort_keys=True))
    return OK


def revert_patch(pid, args):
    if args != ['--confirm', 'REVERT']:
        say('revert needs PATCH_ID --confirm REVERT')
        return USAGE
    handle = lock()
    conn = L.connect()
    try:
        record = json.load(open(journal_path(pid), encoding='utf-8'))
    except (OSError, ValueError):
        say(f'no applied record for {pid}')
        return REFUSED
    if record.get('state') not in ('done', 'reverting'):
        say(f'the apply record is {record.get("state")}: use life-ctl.py recover-apply {pid} --confirm RECOVER')
        return REFUSED
    if undo(pid, record, {rel: sums.get('after') for rel, sums in record['files'].items()}, 'reverted') != OK:
        return REFUSED
    with L.Tx(conn):
        conn.execute("UPDATE patches SET state=?, updated_at=? WHERE patch_id=?",
                     (record.get('prior_state') if record.get('prior_state') in ('ready', 'owner') else 'reverted', L.now(), pid))
    os.replace(journal_path(pid), os.path.join(L.APPLIED, pid, f'history-{time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())}.json'))
    handle.close()
    say(f'reverted {pid}: {len(record["files"])} file(s) restored to their pre-apply bytes; the patch is '
        f'{record.get("prior_state", "reverted")} again and its record moved to history (it may be applied again).')
    return OK


def recover_apply(pid, args):
    if args != ['--confirm', 'RECOVER']:
        say('recover-apply needs PATCH_ID --confirm RECOVER')
        return USAGE
    handle = lock()
    try:
        record = json.load(open(journal_path(pid), encoding='utf-8'))
    except (OSError, ValueError):
        say(f'no apply record for {pid}')
        return REFUSED
    if record.get('state') not in ('intent', 'reverting'):
        say(f'the apply record is {record.get("state")}: nothing to recover (revert a finished apply instead)')
        return REFUSED
    was_reverting = record.get('state') == 'reverting'
    if undo(pid, record, expected_after(pid, record), 'recovered') != OK:
        return REFUSED
    conn = L.connect()
    with L.Tx(conn):            # the patch state now says what the files are: the pre-apply state
        conn.execute("UPDATE patches SET state=?, updated_at=? WHERE patch_id=?",
                     (record.get('prior_state') if record.get('prior_state') in ('ready', 'owner') else 'reverted', L.now(), pid))
    os.replace(journal_path(pid), os.path.join(L.APPLIED, pid, f'history-{time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())}.json'))
    handle.close()
    say(f'recovered {pid}' + (' (an interrupted revert, now finished)' if was_reverting else ' (an interrupted apply, undone)')
        + ': every touched file holds its pre-apply bytes again; the patch is back in its pre-apply state and may be '
        'applied again.')
    return OK


# ------------------------------------------------------------------------------------------- releases

def adopt(pid, args):
    flags = set(args) - {'--confirm', 'ADOPT'}
    if args[:2] != ['--confirm', 'ADOPT'] or not flags <= {'--unreviewed'} or len(args) != 2 + len(flags):
        say('adopt needs PROPOSAL_ID --confirm ADOPT [--unreviewed]')
        return USAGE
    if not no_stop('adopt'):
        return REFUSED
    handle = lock()
    conn = L.connect()
    row = conn.execute('SELECT * FROM proposals WHERE proposal_id=?', (pid,)).fetchone()
    if not row or row['state'] not in ('ready', 'owner') or (row['state'] == 'owner' and '--unreviewed' not in flags):
        say(f'proposal {pid} is not ready (an unreviewed proposal needs --unreviewed)')
        return REFUSED
    if row['program'] in L.SELFDEV_PROTECTED:
        say(f'refused: {row["program"]} is protected from selfdev')
        return REFUSED
    number, rdir, _ = L.active_release(conn)
    old = open(os.path.join(rdir, 'genome', f'{row["program"]}.sym'), encoding='utf-8').read()
    new = open(os.path.join(L.BUNDLES, 'proposals', pid, f'{row["program"]}.sym'), encoding='utf-8').read()
    if number != row['base_release'] or L.sha(old) != row['base_sha256']:
        with L.Tx(conn):
            conn.execute("UPDATE proposals SET state='stale', updated_at=? WHERE proposal_id=?", (L.now(), pid))
        say('the active release changed since this proposal was drafted; it is now stale (draft it again)')
        return REFUSED
    if L.sha(new) != row['new_sha256']:
        say('the bundled genome text differs from the reviewed one; refused')
        return REFUSED
    problems = L.genome_protected_problems(old, new) + L.genome_placement_problems(new)
    if problems:
        say('refused: ' + '; '.join(problems))
        return REFUSED

    def fill(tmp):
        copy_release(rdir, tmp)
        L.write_atomic(os.path.join(tmp, 'genome', f'{row["program"]}.sym'), new, 0o600)
    number, dest = build_release(conn, fill)
    add_release(conn, number, dest, 'adopt', f'proposal {pid}')
    with L.Tx(conn):
        conn.execute("UPDATE proposals SET state='adopted', updated_at=? WHERE proposal_id=?", (L.now(), pid))
    handle.close()
    say(f'release {number} is active (proposal {pid}); program runs already started keep their release.')
    return OK


def new_release(args):
    if args != ['--confirm', 'RELEASE']:
        say('new-release needs --confirm RELEASE')
        return USAGE
    if not no_stop('new-release'):
        return REFUSED
    handle = lock()
    conn = L.connect()
    number, dest = build_release(conn, lambda tmp: copy_release(L.KIT, tmp))
    add_release(conn, number, dest, 'kit', 'owner new-release')
    handle.close()
    say(f'release {number} is active (from the kit).')
    return OK


# ------------------------------------------------------------------------------------------- cells, items, notices

def release_cell(cid):
    handle = lock()
    conn = L.connect()
    row = conn.execute('SELECT * FROM cells WHERE cell_id=?', (cid,)).fetchone()
    if not row or row['state'] != 'quarantined':
        say(f'{cid} is not quarantined')
        return REFUSED
    with L.Tx(conn):
        conn.execute("UPDATE cells SET state='active', failures_in_a_row=0 WHERE cell_id=?", (cid,))
        conn.execute("INSERT INTO cell_events (cell_id, at, event, detail) VALUES (?, ?, 'released', 'owner')", (cid, L.now()))
    handle.close()
    say(f'{cid} is active again (failure streak 0; its model rungs are kept; a missing workspace is re-created next tick)')
    return OK


def retire(cid, args):
    if not set(args) <= {'--force'}:
        say('retire needs CELL [--force]')
        return USAGE
    handle = lock()
    conn = L.connect()
    row = conn.execute('SELECT * FROM cells WHERE cell_id=?', (cid,)).fetchone()
    if not row or row['state'] == 'retired':
        say(f'{cid} is not a live cell')
        return REFUSED
    others = conn.execute("SELECT COUNT(*) FROM cells WHERE organ=? AND state='active' AND cell_id != ?",
                          (row['organ'], cid)).fetchone()[0]
    live = conn.execute("SELECT * FROM runs WHERE cell_id=? AND state IN ('submitting','live','submit_unknown')", (cid,)).fetchall()
    if (not others or live) and '--force' not in args:
        say(f'{cid} is the last active {row["organ"]} cell or has a live run; add --force')
        return REFUSED
    for run in live:
        abandon(conn, run, 'abandoned by the operator (retire --force)')
    with L.Tx(conn):
        conn.execute("UPDATE divisions SET stage='aborted', ended_at=?, reason='owner retire' WHERE parent_id=? AND stage IN"
                     " ('foci','assign','workspaces')", (L.now(), cid))
        conn.execute("UPDATE cells SET state='retired', ended_at=?, end_reason='owner' WHERE cell_id=?", (L.now(), cid))
        conn.execute("UPDATE items SET cell_id=NULL WHERE cell_id=? AND state='queued' AND stage NOT IN ('gate','apply')", (cid,))
        conn.execute("INSERT INTO cell_events (cell_id, at, event, detail) VALUES (?, ?, 'retired', 'owner')", (cid, L.now()))
    handle.close()
    say(f'{cid} retired; its queued items return to the organ (gate/apply items stay with its workspace)')
    return OK


def abandon(conn, run, why):
    """Request the run's cancel (every answer printed), then in ONE transaction: the run ends unknown with
    cancel_cause owner and is collected, its item (if still running) goes to the operator. The workspace is reset after.
    Used by abandon-run and retire --force; LIFE never resubmits the run."""
    rc, _o, _e = L.run_bounded([L.TASK, 'autogen', 'cancel', run['run_id']], timeout=L.CANCEL_TIMEOUT, env=L.child_env(),
                               tracked=False)
    say(f'cancel {run["run_id"]}: {"requested" if rc == 0 else "not confirmed"}')
    with L.Tx(conn):
        conn.execute("UPDATE runs SET state='collected', ended_at=COALESCE(ended_at, ?), detail=?, cancel_cause=CASE WHEN "
                     "cancel_cause='' THEN 'owner' ELSE cancel_cause END WHERE request_id=?", (L.now(), why, run['request_id']))
        conn.execute("UPDATE items SET state='owner', outcome=?, updated_at=? WHERE item_id=? AND state='running'",
                     (f'run abandoned: {why}'[:400], L.now(), run['item_id']))
    ws = run['workspace']
    if ws and os.path.isdir(os.path.join(ws, '.git')) and not L.git_admin_problems(ws):
        git(ws, 'reset', '-q', '--hard', 'HEAD', check=False)
        git(ws, 'clean', '-ffdxq', check=False)


def abandon_run(run_id, args):
    if args != ['--confirm', 'ABANDON']:
        say('abandon-run needs RUN_ID --confirm ABANDON (check bin/symblic-task autogen get RUN_ID first)')
        return USAGE
    handle = lock()
    conn = L.connect()
    run = conn.execute("SELECT * FROM runs WHERE run_id=? AND state IN ('submitting','live','submit_unknown')", (run_id,)).fetchone()
    if run is None:
        say(f'{run_id} is not a LIFE run in submitting, live or submit_unknown')
        return REFUSED
    abandon(conn, run, 'abandoned by the operator (abandon-run)')
    handle.close()
    say(f'{run_id} abandoned: its item is with the operator (requeue it to try again); if the run still appears later, '
        'its result is ignored')
    return OK


def revive(organ, node):
    if organ not in L.ORGANS or node not in L.NODES:
        say('revive needs ORGAN NODE (one of ' + ', '.join(L.ORGANS) + '; one of ' + ', '.join(L.NODES) + ')')
        return USAGE
    handle = lock()
    conn = L.connect()
    if L.live_cells(conn, organ=organ):
        say(f'{organ} still has a live cell; revive is only for an organ with none')
        return REFUSED
    if len(L.live_cells(conn, node=node)) >= L.NODE_CELL_CAP:
        say(f'{node} has {L.NODE_CELL_CAP} live cells')
        return REFUSED
    if len(L.live_cells(conn)) + 1 > L.LIFE_MAX_CELLS:
        say(f'the organism has {L.LIFE_MAX_CELLS} live cells')
        return REFUSED
    if L.budget_row(conn)['births'] + 1 > L.BIRTHS_PER_DAY:
        say('the daily birth budget is spent; revive tomorrow (UTC)')
        return REFUSED
    number, rdir, _ = L.active_release(conn)
    spec = L.load_organs(rdir)['organs'][organ]
    cid = L.cell_id(organ, 0, L.sha(organ, L.now(), secrets.token_hex(4))[:8])
    with L.Tx(conn):
        conn.execute("INSERT INTO cells (cell_id, organ, kind, parent_id, depth, focus, node, workspace, state, born_at, release)"
                     " VALUES (?, ?, ?, NULL, 0, ?, ?, ?, 'active', ?, ?)",
                     (cid, organ, spec['kind'], spec['seed_focus'], node, L.workspace_for(cid), L.now(), number))
        conn.execute("INSERT INTO cell_events (cell_id, at, event, detail) VALUES (?, ?, 'revived', 'owner')", (cid, L.now()))
        L.budget_add(conn, 'births', 1)
    handle.close()
    say(f'{cid} is alive on {node} with the seed focus' + (' (its workspace is created at the next armed tick)'
                                                           if organ in L.AGENT_ORGANS else ''))
    return OK


def requeue(iid, args):
    """An item that ended owner or failed, or an item that abstained with OVERFLOW (the queue was full), or a digest
    source that abstained EMPTY or with a refused fetch, is queued again with its per-stage counters at 0: a gate or
    apply item goes back to its agent stage (patch or draft), a source goes back to fetch (its sources row to pending),
    any other item keeps its stage; it loses its cell and is dispatched. No URL, credential or sandbox check is
    bypassed: the item runs every stage again."""
    if args != ['--confirm', 'REQUEUE']:
        say('requeue needs ITEM --confirm REQUEUE')
        return USAGE
    handle = lock()
    conn = L.connect()
    row = conn.execute('SELECT * FROM items WHERE item_id=?', (iid,)).fetchone()
    retryable = row is not None and row['state'] == 'abstained' and (
        row['outcome'].startswith('OVERFLOW:') or (row['kind'] == 'source' and row['outcome'].startswith(('EMPTY', 'fetch refused'))))
    if not row or (row['state'] not in ('owner', 'failed') and not retryable):
        say(f'{iid} did not end owner or failed, and is not an OVERFLOW, EMPTY or refused-fetch abstention')
        return REFUSED
    stage = {('codebase', 'gate'): 'patch', ('selfdev', 'gate'): 'draft', ('database', 'apply'): 'draft'}.get(
        (row['organ'], row['stage']), row['stage'])
    payload = json.loads(row['payload'])
    if row['kind'] == 'source':
        stage = 'fetch'
        payload = {'source_key': payload['source_key'], 'url': payload['url']}
    with L.Tx(conn):
        if row['kind'] == 'source':
            conn.execute("UPDATE sources SET fetch_state='pending' WHERE source_key=?", (payload['source_key'],))
            conn.execute('UPDATE items SET payload=? WHERE item_id=?', (json.dumps(payload, sort_keys=True), iid))
        conn.execute("UPDATE items SET state='queued', stage=?, cell_id=NULL, infra_runs=0, faults=0, start_refusals=0, timeouts=0,"
                     " rung_extra=0, outcome='requeued by the operator', updated_at=? WHERE item_id=?", (stage, L.now(), iid))
    handle.close()
    say(f'{iid} is queued again at {stage}')
    return OK


def release_hold(node):
    if node not in L.NODES:
        say('NODE must be one of ' + ', '.join(L.NODES))
        return USAGE
    handle = lock()
    conn = L.connect()
    with L.Tx(conn):
        n = conn.execute('DELETE FROM node_holds WHERE node=?', (node,)).rowcount
    handle.close()
    say(f'{node}: {n} hold(s) removed' if n else f'{node} had no hold')
    return OK


def move(cid, node):
    """Move a cell by hand. Refused when the node is not online in the latest sample; the cell then waits there like any
    cell whose node is unavailable (move does not wait for agy readiness)."""
    if node not in L.NODES:
        say('NODE must be one of ' + ', '.join(L.NODES))
        return USAGE
    handle = lock()
    conn = L.connect()
    row = conn.execute("SELECT * FROM cells WHERE cell_id=? AND state IN ('active','quarantined')", (cid,)).fetchone()
    if not row or len(L.live_cells(conn, node=node)) >= L.NODE_CELL_CAP or row['node'] == node:
        say(f'{cid} is not an active or quarantined cell (a dividing cell never moves), is already there, or {node} has '
            f'{L.NODE_CELL_CAP} live cells')
        return REFUSED
    busy = conn.execute("SELECT 1 FROM runs WHERE cell_id=? AND state IN ('submitting','live','submit_unknown')", (cid,)).fetchone() \
        or conn.execute("SELECT 1 FROM items WHERE cell_id=? AND state IN ('queued','running') AND stage IN ('gate','apply')",
                        (cid,)).fetchone() \
        or conn.execute("SELECT 1 FROM items WHERE cell_id=? AND state='running'", (cid,)).fetchone()
    if busy:
        say(f'{cid} has a live run, a running item or a gate/apply item (its workspace is busy); move it after they end')
        return REFUSED
    last = conn.execute('SELECT online FROM samples WHERE node=? ORDER BY at DESC LIMIT 1', (node,)).fetchone()
    if not last or last['online'] != 1:
        say(f'{node} is not online in the latest sample; refused')
        return REFUSED
    with L.Tx(conn):
        conn.execute('UPDATE cells SET node=? WHERE cell_id=?', (node, cid))
        conn.execute("INSERT INTO cell_events (cell_id, at, event, detail) VALUES (?, ?, 'moved', ?)", (cid, L.now(), f'owner: {row["node"]} -> {node}'))
    handle.close()
    say(f'{cid} moved to {node}')
    return OK


def show(iid):
    conn = L.connect(readonly=True)
    row = conn.execute('SELECT * FROM items WHERE item_id=?', (iid,)).fetchone()
    if not row:
        say(f'no item {iid}')
        return REFUSED
    print(f'{row["item_id"]}  {row["organ"]}/{row["kind"]}  stage {row["stage"]}  state {row["state"]}  taint {row["taint"]}  '
          f'approved {row["approved"]}  cell {row["cell_id"]}')
    for key, value in sorted(json.loads(row['payload']).items()):
        print(f'  {key}: {L.one_line(value, 2000)}')
    return OK


def approve(iid, args):
    """The operator read the item (life-ctl show) and allows its agent run: approved = 1 and approved_sha = the sha256 of
    its operative text (L.operative_sha). Its taint stays what it is; a later change of that text voids the approval."""
    if args != ['--confirm', 'APPROVE']:
        say('approve needs ITEM --confirm APPROVE (read it first with life-ctl.py show ITEM)')
        return USAGE
    handle = lock()
    conn = L.connect()
    row = conn.execute("SELECT * FROM items WHERE item_id=? AND state='queued' AND taint IN ('web','model') AND kind IN "
                       "('lesson','request')", (iid,)).fetchone()
    if row is None:
        say(f'{iid} is not a queued web- or model-derived lesson or request')
        return REFUSED
    with L.Tx(conn):
        conn.execute("UPDATE items SET approved=1, approved_sha=?, outcome='approved by the operator', updated_at=? WHERE item_id=?",
                     (L.operative_sha(row['kind'], json.loads(row['payload'])), L.now(), iid))
        conn.execute("UPDATE notices SET state='acked' WHERE kind='approve_needed' AND subject=? AND state='open'", (iid,))
    handle.close()
    say('approved: its agent run may start (the approval covers exactly the text you read)')
    return OK


def report(cid):
    import unicodedata
    path = os.path.join(L.REPORTS, f'{cid}.md')
    if not re.fullmatch(r'[0-9a-f]{16}', cid) or not os.path.isfile(path):
        say(f'no report for {cid} yet (a report is written when every item of the command has ended)')
        return REFUSED
    text = open(path, encoding='utf-8').read()
    print(''.join(c for c in text if c == '\n' or not unicodedata.category(c).startswith('C')), end='')
    return OK


def notices():
    conn = L.connect(readonly=True)
    for r in conn.execute("SELECT * FROM notices WHERE state='open' ORDER BY at"):
        print(f'{r["notice_id"]}  {time.strftime("%Y-%m-%d %H:%M", time.localtime(r["at"]))}  x{r["count"]:<3} {L.one_line(r["kind"], 24):24} '
              f'{L.one_line(r["subject"], 60)}: {L.one_line(r["text"], 300)}')
    return OK


def ack(nid):
    handle = lock()
    conn = L.connect()
    with L.Tx(conn):
        n = conn.execute("UPDATE notices SET state='acked' WHERE notice_id=? AND state='open'", (nid,)).rowcount
    handle.close()
    say('acknowledged (the condition it reports is unchanged)' if n else f'no open notice {nid}')
    return OK if n else REFUSED


def command(text):
    raw = text.strip()
    if not L.COMMAND_MIN_BYTES <= len(raw.encode('utf-8')) <= L.COMMAND_MAX_BYTES:
        say(f'a command is {L.COMMAND_MIN_BYTES}..{L.COMMAND_MAX_BYTES} bytes of text')
        return REFUSED
    if L.has_secret(raw):
        say('refused: the text looks like it contains a credential')
        return REFUSED
    for d in (L.INBOX, L.INBOX_TMP):
        os.makedirs(d, mode=0o700, exist_ok=True)
    slug = '-'.join(re.findall(r'[a-z0-9]+', raw.lower()))[:40].strip('-') or 'command'
    for _ in range(3):
        name = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + f'-{slug}-{secrets.token_hex(3)}.txt'
        tmp = os.path.join(L.INBOX_TMP, name)
        L.write_atomic(tmp, raw + '\n')
        if L.publish_noreplace(tmp, os.path.join(L.INBOX, name)):
            say(f'queued {name}; the next tick reads it')
            return OK
        os.remove(tmp)
    say('three random names collided; send it again')
    return REFUSED


def stop():
    """Under the short control lock: STOP_GENERATION + 1, STOP written, ARMED removed (an arm that is validating can
    then never publish); then the cancels."""
    os.makedirs(L.CONTROL, mode=0o700, exist_ok=True)
    handle = control_lock()
    try:
        touch(L.STOP_GENERATION_FILE, f'{stop_generation() + 1}\n')
        touch(L.STOP_FILE, 'owner STOP\n')
        remove(L.ARMED_FILE)
    finally:
        handle.close()
    say('STOP written and ARMED removed: nothing new starts; a running tick ends its processes within 1 s + 30 s grace.')
    try:
        conn = L.connect(readonly=True)
        runs = [r['run_id'] for r in conn.execute("SELECT run_id FROM runs WHERE state IN ('submitting','live','submit_unknown')")]
        jobs = [json.loads(r['payload']).get('job_id') for r in conn.execute("SELECT payload FROM items WHERE state='running' AND stage='bench'")]
        conn.close()
    except sqlite3.Error as exc:
        say(f'the registry cannot be read ({exc}); cancel LIFE runs by hand: bin/symblic-task autogen list (request ids '
            'start with life-) and the cluster jobs whose label starts with life-')
        return REFUSED
    for run_id in runs:
        rc, _o, _e = L.run_bounded([L.TASK, 'autogen', 'cancel', run_id], timeout=L.CANCEL_TIMEOUT, env=L.child_env(), tracked=False)
        say(f'cancel {run_id}: {"requested" if rc == 0 else "not confirmed (rc " + str(rc) + ")"}')
    for job in jobs:
        if not job:
            say('a benchmark job has no id yet (its label is looked up by the next tick)')
            continue
        try:
            ok = L.http_json('/api/cluster/job/cancel', {'id': job}, timeout=L.JOB_CANCEL_TIMEOUT).get('success') is True
            say(f'cancel job {job}: {"requested" if ok else "not accepted"}')
        except L.Telemetry as exc:
            say(f'cancel job {job}: not confirmed ({exc})')
    try:
        handle = L.open_lock(L.LOCK_FILE)
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        say('a tick holds the lock: it records the cancellations itself (life-ctl.py notices shows anything unresolved).')
        return OK
    L.stop_everything(L.connect())
    handle.close()
    say('registry updated; runs and jobs stay live until a tick sees them end. Then: life-ctl.py unstop, life-ctl.py arm.')
    return OK


def canaries():
    if not no_stop('canaries'):
        return REFUSED
    handle = lock()
    conn = L.connect()
    _, rdir, _ = L.active_release(conn)
    failed = tick_module().run_canaries(rdir, L.Procs())
    with L.Tx(conn):
        for key, value in (('canary_failed', '; '.join(failed)[:600]), ('canary_at', str(L.now()))) + ((('canary_ok_ever', '1'),) if not failed else ()):
            set_meta(conn, key, value)
    handle.close()
    say('canaries passed; the canary hold is clear' if not failed else 'canaries failed: ' + '; '.join(failed))
    return OK if not failed else REFUSED


def gate_selftest(test):
    """Prove the gate machinery on an idle active codebase clone (probe_dir: the lowest active codebase cell whose
    workspace is not busy; never only the seed clone), with the operator's chosen PASSING test: (0) the sandbox probe
    holds; (A) one harmless comment line appended to the test's module file: the gate must PASS and devcheck must
    report at least one checked file; (B) one line that does not parse appended instead: the gate must FAIL with exit 4
    (devcheck). The clone is reset after each phase. A PASS records meta gate_selftest = kit and platform hashes, the
    test and the time: until it matches the current hashes, codebase gates and agent runs wait (notice gate_unproven)."""
    if not L.valid_test_id(test):
        say('gate-selftest needs a test id tests.<module>[.<Class>[.<test>]]')
        return USAGE
    if not no_stop('gate-selftest'):
        return REFUSED
    handle = lock()
    conn = L.connect()
    ws, temporary = probe_dir(conn)
    if temporary:
        shutil.rmtree(ws, ignore_errors=True)
        say('no active codebase cell has an idle clone (a live run or a gate/apply item on each); try later')
        return REFUSED
    branch = meta(conn, 'codebase_branch')

    def reset():
        git(ws, 'reset', '-q', '--hard', 'HEAD', check=False)
        git(ws, 'clean', '-ffdxq', check=False)
    git(ws, 'fetch', '-q', 'origin', branch)
    git(ws, 'reset', '-q', '--hard', f'origin/{branch}')
    git(ws, 'clean', '-ffdxq')
    base = git(ws, 'rev-parse', 'HEAD').strip()
    rc0, probe = sandbox_probe(ws)
    print(probe)
    module = L.resolve_test_module(ws, test)
    if not module:
        say(f'{test} does not resolve to a file in the clone')
        return REFUSED
    results = []
    try:
        for phase, line, want in (('A', '\n# life gate selftest\n', 0), ('B', '\ndef life_gate_selftest_broken(:\n', 4)):
            with open(os.path.join(ws, module), 'a', encoding='utf-8') as fh:
                fh.write(line)
            rc, out, err = L.run_bounded(L.scope_argv(['bash', L.GATE_SCRIPT, ws, test, base], runtime=L.GATE_TIMEOUT, name='gate'),
                                         timeout=L.GATE_TIMEOUT, env=L.scope_env())
            checked = re.search(r'devcheck: [^\n]*: ([0-9]+) file\(s\)', out + err)
            ok = rc == want and (phase != 'A' or (checked and int(checked.group(1)) >= 1))
            results.append(ok)
            print(f'--- phase {phase}: rc {rc} (want {want}), devcheck checked {checked.group(1) if checked else "?"} file(s)')
            print((out + err)[-1500:])
            reset()
    finally:
        reset()
        handle.close()
    passed = rc0 == 0 and all(results)
    if passed:
        handle = lock()
        try:
            conn = L.connect()
            with L.Tx(conn):
                set_meta(conn, 'gate_selftest', f'{L.kit_sha256()} {L.platform_sha256()} {test} {L.now()}')
        finally:
            handle.close()
    say('gate self-test PASS (the codebase gate is proven for this kit and these platform files)' if passed
        else f'gate self-test FAIL (probe rc {rc0}, phases {results})')
    return OK if passed else REFUSED


def restore(which, path, args):
    """Replace the registry or the organism database with a backup file from STATE/backups (LIFE.md section 12). STOP
    must be present and the tick unit inactive; the lock is held from the first move to the integrity check."""
    if which not in ('registry', 'organism') or args != ['--confirm', 'RESTORE']:
        say('restore needs registry|organism FILE --confirm RESTORE')
        return USAGE
    if not L.stop_present():
        say('refused: run life-ctl.py stop first (STOP must be present for a restore)')
        return REFUSED
    rc, out, _ = L.run_bounded(['systemctl', '--user', 'is-active', 'life-tick.service'], timeout=L.CANCEL_TIMEOUT,
                               env=L.scope_env(), tracked=False)
    if out.strip() in ('active', 'activating', 'deactivating'):
        say('refused: life-tick.service is running; wait for it to end (systemctl --user stop life-tick.timer first)')
        return REFUSED
    src = os.path.realpath(path)
    name = os.path.basename(src)
    pattern = r'life-\d{4}-\d{2}-\d{2}\.sqlite3' if which == 'registry' else r'organism-(\d{4}-\d{2}-\d{2}|before-[0-9a-z_]+)\.sqlite3'
    if os.path.dirname(src) != os.path.realpath(L.BACKUPS) or not re.fullmatch(pattern, name) or not os.path.isfile(src):
        say(f'refused: FILE must be a {which} backup inside {L.BACKUPS}')
        return REFUSED
    dest = L.REGISTRY if which == 'registry' else L.ORGANISM
    handle = lock()
    try:
        aside = os.path.join(L.BACKUPS, 'replaced-' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()))
        os.makedirs(aside, mode=0o700)
        for suffix in ('', '-wal', '-shm'):
            if os.path.exists(dest + suffix):
                os.replace(dest + suffix, os.path.join(aside, os.path.basename(dest) + suffix))
        shutil.copyfile(src, dest)
        os.chmod(dest, 0o600)
        check = sqlite3.connect(f'file:{dest}?mode=ro', uri=True)
        try:
            ok = [r[0] for r in check.execute('PRAGMA integrity_check')] == ['ok']
            fks = check.execute('PRAGMA foreign_key_check').fetchall()
            schema = check.execute("SELECT value FROM meta WHERE key='schema'").fetchone() if which == 'registry' else (L.SCHEMA_VERSION,)
        finally:
            check.close()
    finally:
        handle.close()
    if not ok or fks or not schema or schema[0] != L.SCHEMA_VERSION:
        say(f'the restored {which} fails its check (integrity {ok}, {len(fks)} dangling reference(s), schema {schema}); the '
            f'replaced files are in {aside}')
        return REFUSED
    handle = lock()
    try:
        conn = L.connect()
        with L.Tx(conn):       # a replaced organism invalidates every store cursor: the adapter replays (idempotent)
            for key in ('store_marks', 'store_disabled', 'store_next'):
                set_meta(conn, key, '')
    finally:
        handle.close()
    say(f'{which} restored from {name}; the replaced files are in {aside}. Before unstop: (1) list bin/symblic-task autogen '
        'list and cancel every run whose request id starts with life- that the restored registry does not know; (2) list '
        '/api/cluster/jobs?kind=map and cancel every running job whose meta.label starts with life- that it does not know; '
        f'(3) wait {L.ORPHAN_HOLD_SECONDS} s for orphaned model runs to end. The next tick reconciles the two migration '
        'ledgers (migration_recovery_required if the organism lacks one). Then life-ctl.py unstop and arm.')
    return OK


def forget_migration(mid, args):
    """After a restore left the organism without a migration the registry calls applied: the row becomes refused
    (forgotten), so reconciliation stops holding the database organ. The text stays in STATE/bundles/migrations/."""
    if args != ['--confirm', 'FORGET']:
        say('forget-migration needs MIGRATION_ID --confirm FORGET')
        return USAGE
    handle = lock()
    conn = L.connect()
    with L.Tx(conn):
        n = conn.execute("UPDATE migrations SET state='refused', detail='forgotten by the operator after a restore', at=? WHERE "
                         "migration_id=? AND state='applied'", (L.now(), mid)).rowcount
    handle.close()
    say(f'{mid} forgotten (state refused); its text stays in {L.BUNDLES}/migrations/' if n else f'{mid} is not an applied migration')
    return OK if n else REFUSED


def main(argv):
    if not argv:
        print(__doc__)
        return USAGE
    cmd, args = argv[0], argv[1:]
    if cmd == 'seed':
        return seed(args)
    if cmd == 'contract' and not args:
        problems = L.contract_problems()
        print('\n'.join(problems) or 'contract holds')
        return REFUSED if problems else OK
    if not os.path.isfile(L.REGISTRY):
        say('not seeded')
        return REFUSED
    if cmd == 'arm':
        return arm(args)
    simple = {'disarm': (remove, L.ARMED_FILE), 'freeze': (touch, L.FREEZE_FILE), 'thaw': (remove, L.FREEZE_FILE),
              'selfdev-arm': (touch, L.SELFDEV_FILE), 'selfdev-disarm': (remove, L.SELFDEV_FILE),
              'unstop': (remove, L.STOP_FILE)}
    if cmd in simple and not args:
        fn, path = simple[cmd]
        handle = control_lock() if cmd == 'unstop' else None
        try:
            fn(path)
        finally:
            if handle is not None:
                handle.close()
        say(f'{cmd}: done' + ('; LIFE stays disarmed until life-ctl.py arm' if cmd == 'unstop' else ''))
        return OK
    single = {'stop': stop, 'notices': notices, 'canaries': canaries}
    if cmd in single and not args:
        return single[cmd]()
    if cmd == 'clear-fault' and not args:
        handle = lock()
        conn = L.connect()
        with L.Tx(conn):
            set_meta(conn, 'fault_hold', '')
            set_meta(conn, 'faults_in_a_row', '0')
        handle.close()
        say('the fault hold is clear')
        return OK
    one = {'command': command, 'ack': ack, 'show': show, 'report': report, 'release-cell': release_cell,
           'gate-selftest': gate_selftest, 'release-hold': release_hold}
    if cmd in one and len(args) == 1:
        return one[cmd](args[0])
    with_args = {'apply': apply_patch, 'revert': revert_patch, 'recover-apply': recover_apply, 'adopt': adopt,
                 'approve': approve, 'retire': retire, 'requeue': requeue, 'forget-migration': forget_migration,
                 'abandon-run': abandon_run}
    if cmd in with_args and args:
        return with_args[cmd](args[0], args[1:])
    if cmd == 'new-release':
        return new_release(args)
    if cmd in ('move', 'revive') and len(args) == 2:
        return (move if cmd == 'move' else revive)(args[0], args[1])
    if cmd == 'restore' and len(args) == 4:
        return restore(args[0], args[1], args[2:])
    if cmd == 'purge-refused' and args == ['--confirm', 'PURGE']:
        n = 0
        for name in os.listdir(L.INBOX_REFUSED):
            path = os.path.join(L.INBOX_REFUSED, name)
            if not os.path.isdir(path) or os.path.islink(path):
                os.remove(path)
                n += 1
        say(f'{n} refused file(s) deleted')
        return OK
    print(__doc__)
    return USAGE


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
