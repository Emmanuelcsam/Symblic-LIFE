#!/usr/bin/env python3
"""LIFE acceptance checks that autogen runs as policy checks (and the canaries run), all code, no model.

    life-check.py verify-line ORGAN FILE EXPECTED_WORDS...   FILE's bytes are exactly the expected line (+ one LF)
    life-check.py migration FILE SNAPSHOT SHA256             SNAPSHOT exists with this sha256 and only CREATE
                                                             statements; FILE is an additive org_ migration on top
    life-check.py genome-protected NEW BASE                  only ask instructions differ between BASE and NEW
    life-check.py registry                                   PRAGMA integrity_check and foreign_key_check (read-only)
    life-check.py sandboxed [--timeout N] CMD [ARG...]       run CMD in its own life-check-*.scope (MemoryMax 4G,
                                                             TasksMax, RuntimeMaxSec) in the Landlock sandbox (cwd = this
                                                             folder, an empty temporary HOME, no STATE, no TCP), under
                                                             timeout --kill-after=10 N and prlimit --as 4 GiB --fsize
                                                             2 GiB, killed at N s (default SANDBOX_CHECK_TIMEOUT 110,
                                                             inside autogen's 120 s)

Exit 0 pass, 1 fail (the reason on stderr; for sandboxed: CMD failed, timed out or was killed, or the scope could not
be created), 2 usage, 125 the sandbox is unavailable, the host is short of memory or under pressure
(life_common.host_problems), or a devcheck tool resolves outside the allowed tool roots. `sandboxed` starts CMD in
its own process group inside its own transient scope (autogen runs checks inside the dashboard process: the scope
keeps candidate code out of the dashboard's cgroup and inside LIFE's STOP), and on its timeout, on SIGTERM and on
SIGINT SIGKILLs that whole group and stops the scope before it exits, so nothing CMD started outlives it; /dev/shm
entries the run left are removed. A scope that cannot be created fails the check; CMD never runs unscoped. Autogen runs
these in its staging checkout on the host (cwd = the checkout), with CHECK_TIMEOUT 120 s (symblicos/autogen.py). Every
file argument must be a regular file inside the current folder, opened component by component without following any
symlink (no .., no absolute path). Nothing here writes a file outside a private temporary folder.
"""
import sys
sys.dont_write_bytecode = True                  # no .pyc is ever written under bin/ (kit_sha256 hashes __pycache__)
import os  # noqa: E402
import shutil  # noqa: E402
import signal  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import life_common as L  # noqa: E402


def fail(msg):
    print(f'life-check: {msg}', file=sys.stderr)
    return 1


def read_inside(path, limit):
    """The bytes of a regular file inside the current folder (life_common.read_in: component by component with
    O_NOFOLLOW, checked on the open descriptor, at most `limit` bytes)."""
    return L.read_in(os.getcwd(), path, limit)


def sandboxed(cmd):
    timeout = L.SANDBOX_CHECK_TIMEOUT
    if cmd[:1] == ['--timeout']:
        if len(cmd) < 3 or not cmd[1].isdigit() or not 1 <= int(cmd[1]) <= L.SANDBOX_TIMEOUT_MAX:
            return fail(f'--timeout takes 1..{L.SANDBOX_TIMEOUT_MAX} seconds')
        timeout, cmd = int(cmd[1]), cmd[2:]
    problems = L.host_problems()
    if problems:
        print('life-check: the host cannot take candidate code now: ' + '; '.join(problems), file=sys.stderr)
        return 125
    env, rx, refused = L.devcheck_tools()
    if refused:
        print('life-check: tool root not allow-listed: ' + ', '.join(refused), file=sys.stderr)
        return 125
    home = tempfile.mkdtemp(prefix='life-check-')
    shm0 = L.shm_entries()
    child = None
    unit = f'life-check-{os.getpid()}-{os.urandom(4).hex()}'

    def kill_group():
        if child is not None:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except OSError:
                pass
        subprocess.run(['systemctl', '--user', 'stop', unit + '.scope'], env=L.scope_env(), stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=L.CANCEL_TIMEOUT, check=False)

    def on_signal(signum, _frame):
        kill_group()
        shutil.rmtree(home, ignore_errors=True)
        L.shm_cleanup(shm0)
        os._exit(128 + signum)
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    try:
        inner = ['/usr/bin/timeout', '--kill-after=10', str(timeout), '/usr/bin/prlimit', f'--as={L.BENCH_AS_BYTES}',
                 f'--fsize={L.BENCH_FSIZE_BYTES}', *cmd]
        argv = ['systemd-run', '--user', '--scope', '--quiet', '--collect', f'--unit={unit}', '--slice=work.slice',
                '-p', 'MemoryMax=4G', '-p', 'CPUQuota=200%', '-p', f'TasksMax={L.SCOPE_TASKS_MAX}',
                '-p', f'RuntimeMaxSec={timeout + 15 + L.KILL_GRACE}', '--nice=19', '--',
                *L.sandbox_argv(os.getcwd(), home, inner, rx=rx, env_extra=env)]
        child = subprocess.Popen(argv, start_new_session=True, close_fds=True, stdin=subprocess.DEVNULL, env=L.scope_env())
        try:
            rc = child.wait(timeout=timeout + 15)
        except subprocess.TimeoutExpired:
            kill_group()
            child.wait()
            print(f'life-check: the sandboxed command passed {timeout} s', file=sys.stderr)
            return 1
        kill_group()                       # descendants left in the group end with it
        if rc == 125:
            return 125
        if rc != 0:
            print(f'life-check: the sandboxed command failed (rc {rc})', file=sys.stderr)
            return 1
        return 0
    finally:
        shutil.rmtree(home, ignore_errors=True)
        L.shm_cleanup(shm0)


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    cmd, args = argv[0], argv[1:]
    try:
        if cmd == 'sandboxed' and args:
            return sandboxed(args)
        if cmd == 'verify-line' and len(args) >= 3 and args[0] in L.VERIFY_LINES:
            problems = L.verify_line_problems(args[0], read_inside(args[1], L.VERIFY_MAX_BYTES), ' '.join(args[2:]))
        elif cmd == 'migration' and len(args) == 3:
            snapshot = read_inside(args[1], L.SNAPSHOT_MAX_BYTES)
            if L.sha(snapshot.decode('utf-8')) != args[2]:
                return fail('schema-snapshot.sql differs from the snapshot LIFE wrote (never edit it)')
            problems = L.snapshot_problems(snapshot.decode('utf-8'))
            problems += L.migration_problems(read_inside(args[0], L.MIGRATION_MAX_BYTES).decode('utf-8'),
                                             snapshot.decode('utf-8')) if not problems else []
        elif cmd == 'genome-protected' and len(args) == 2:
            if not all(a.startswith(('genome/', 'genome-base/')) and a.endswith('.sym') for a in args):
                return fail('the files must be genome/<program>.sym and genome-base/<program>.sym')
            new = read_inside(args[0], L.GENOME_MAX_BYTES).decode('utf-8')
            problems = L.genome_protected_problems(read_inside(args[1], L.GENOME_MAX_BYTES).decode('utf-8'), new)
            problems += L.genome_placement_problems(new)
            if os.path.basename(args[0])[:-4] in L.SELFDEV_PROTECTED:
                problems.append('this program is protected from selfdev')
        elif cmd == 'registry' and not args:
            conn = L.connect(readonly=True)
            rows = [r[0] for r in conn.execute('PRAGMA integrity_check')]
            fks = conn.execute('PRAGMA foreign_key_check').fetchall()
            problems = ([] if rows == ['ok'] else ['integrity_check: ' + '; '.join(rows)[:300]]) + \
                       ([f'foreign_key_check: {len(fks)} dangling reference(s)'] if fks else [])
        else:
            print(__doc__)
            return 2
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        return fail(str(exc)[:300])
    except Exception as exc:  # noqa: BLE001 - any other fault is a failed check, never a pass
        return fail(f'{type(exc).__name__}: {str(exc)[:300]}')
    if problems:
        return fail('; '.join(problems)[:600])
    print('life-check: pass')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
