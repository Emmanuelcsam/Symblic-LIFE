#!/usr/bin/env bash
# LIFE kit validator: STATIC checks only. No model, no agent, no network, no task start, no file written
# outside a private temporary folder (Python runs with -B, so no bytecode cache is written either).
#   1 inventory   every required file exists (regular, no symlink); entry points are executable
#   2 genome      bin/symblic check on each of the nine programs (exit 0 and "ok"); no placement option in any
#   3 organs      organs/organs.json passes life_common.organs_problems (closed schema, non-thinking ladder models)
#   4 templates   each raw agent template (organs/<organ>.lines.txt, placeholders unfilled) lints with ZERO
#                 findings and no root and starts every line with a symblic_autogen verb; each renders with
#                 organs/fixtures.json into exactly two statements that lint with ZERO findings; its policy equals the
#                 fixed LIFE policy with the organ's exact checks and passes symblic_autogen.normalize; policy_flags()
#                 fed through bin/symblic-task's OWN parser and autogen_policy() normalizes to the same sha256 (the round
#                 trip the server sees); the largest legal values (life_common.worst_values, each field checked to be at
#                 its maximum) still fit; the release validator life-ctl check_release passes on the kit
#   5 syntax      bash -n on every shell file; ast.parse on every Python file; every JSON file parses
#   6 databases   db/life.sql and db/organism.sql applied twice in memory; required tables; CHECK constraints, triggers
#                 and indexes refuse 28 bad rows (see the list in the check)
#   7 canaries    exactly the nine program checks and the registry check, each once, in order, each target present
#   8 benchmarks  benchmarks/benchmarks.example.json passes the tick's own bench_problems rules; a backtracking
#                 param_rx is refused; the generated run wrapper (bench_wrapper) runs under sh on a printf command and
#                 frames LIFE_RUN / LIFE_RC / LIFE_TRUNC / LIFE_END exactly (no model, no network, a private temp file)
#   9 embedding   every "### <path>" block in LIFE.md equals that file byte for byte; no duplicate or extra block; every
#                 kit file (except LIFE.md, BRIEF.md, workshop/, __pycache__/) is embedded
#  10 contract    life_common.contract_problems() is empty (the platform facts LIFE relies on hold)
#  11 rules       pure-function negative and positive cases: protected lines, placement, migrations and snapshots,
#                 the credential screen, verify lines, the gate's path and local_fix rules, path classes, cell ids, test
#                 ids, payload schemas, failure fingerprints, lint rewrites, the unit file, every stage budget fits the
#                 tick, the research and benchmark bounds, every CONTRACT file is gate-protected, every notice kind and
#                 meta key the code writes is declared, /proc/pressure/io and /proc/pressure/memory readable, the two
#                 credential tiers, typechanges, nested signatures and duplicate definitions, traceback identities,
#                 environment errors, the migration grammar, payload values, notice keys, the derived limits (KV
#                 context, model-call wall, division ticks, storage), protocol limits equal in code, SQL and regexes
#  12 numbers     no timing literal in any bin/*.py program except life_common.py (every number lives there), and the
#                 gate script's two timeouts equal GATE_DEVCHECK_TIMEOUT and GATE_TEST_TIMEOUT
#  13 generated   LIFE.md sections 13, 14 and 17 hold exactly the tables life_common generates (numbers, notice kinds,
#                 contract rows)
# It prints PASS/FAIL per check and ends with STATIC PASS or SOME FAILED. Exit 0 only on STATIC PASS.
# STATIC PASS is not an admission test: the coordinator's behaviour under concurrency, crashes and STOP is
# not exercised here (LIFE.md section 18, GAP 8).
set -u
shopt -s nullglob
KIT="/home/operator/host-checkout/docs/life"
REPO="/home/operator/host-checkout"
PY="/usr/bin/python3 -B -I"
fail=0
pass() { printf 'PASS  %-10s %s\n' "$1" "$2"; }
bad()  { printf 'FAIL  %-10s %s\n' "$1" "$2"; fail=1; }

echo "== 1 inventory =="
required=(BRIEF.md README.md DECISIONS.md LIFE.md VALIDATE.sh
  bin/life_common.py bin/life-tick.py bin/life-ctl.py bin/life-status.py bin/life-check.py bin/life-seed.sh
  bin/life-fetch.py bin/life-research.py
  checks/devcheck-gate.sh checks/canaries.txt db/life.sql db/organism.sql
  organs/organs.json organs/fixtures.json organs/codebase.lines.txt organs/selfdev.lines.txt organs/database.lines.txt
  policies/codebase.json policies/selfdev.json policies/database.json
  spawn/PROTOCOL.md spawn/example/division.json units/life-tick.service units/life-tick.timer
  benchmarks/benchmarks.example.json)
for p in classify-command triage-error extract-source distill-lesson propose-experiment rank-experiment review-patch reproduce assign-item; do
  required+=("genome/$p.sym"); done
inv=0
for f in "${required[@]}"; do
  if [ -f "$KIT/$f" ] && [ ! -L "$KIT/$f" ]; then :; else bad inventory "$f missing"; inv=1; fi; done
for f in VALIDATE.sh bin/life-tick.py bin/life-ctl.py bin/life-status.py bin/life-check.py bin/life-seed.sh bin/life-fetch.py \
         bin/life-research.py checks/devcheck-gate.sh; do
  [ -x "$KIT/$f" ] || { bad inventory "$f is not executable"; inv=1; }; done
[ "$inv" = 0 ] && pass inventory "${#required[@]} files"

echo "== 2 genome (bin/symblic check, no model) =="
for f in "$KIT"/genome/*.sym; do
  out="$("$REPO/bin/symblic" check "$f" 2>&1)"; rc=$?
  placement="$($PY -c 'import sys; sys.path.insert(0, sys.argv[1] + "/bin"); import life_common as L; print("; ".join(L.genome_placement_problems(open(sys.argv[2], encoding="utf-8").read())))' "$KIT" "$f")"
  if [ "$rc" = 0 ] && printf '%s' "$out" | tail -1 | grep -q ': ok' && [ -z "$placement" ]; then pass check "$(basename "$f")"; else bad check "$(basename "$f") $placement"; fi
done

echo "== 3-4 organs and templates (lint zero findings, normalize, fixed policy, CLI round trip) =="
if $PY - <<'PYEOF'
import importlib.machinery, importlib.util, json, sys
sys.path.insert(0, '/home/operator/host-checkout'); sys.path.insert(0, '/home/operator/host-checkout/docs/life/bin')
import life_common as L
import symblic_autogen as A
ok = True
problems = L.organs_problems(json.load(open(L.KIT + '/organs/organs.json', encoding='utf-8'), object_pairs_hook=L._no_dup_keys))
print(('PASS  organs     ' if not problems else 'FAIL  organs     ') + ('organs.json' if not problems else '; '.join(problems)))
ok &= not problems
loader = importlib.machinery.SourceFileLoader('symblic_task_cli', L.TASK)
spec = importlib.util.spec_from_loader('symblic_task_cli', loader)
cli = importlib.util.module_from_spec(spec)
loader.exec_module(cli)
fixtures = json.load(open(L.KIT + '/organs/fixtures.json', encoding='utf-8'))
for organ in L.AGENT_ORGANS:
    raw = A.statements(open(f'{L.KIT}/organs/{organ}.lines.txt', encoding='utf-8').read())
    raw_findings = A.lint(raw)                  # the raw template, no root: it must name its absolute folder itself
    print(('PASS  raw lint   ' if not raw_findings else 'FAIL  raw lint   ') + f'{organ}: ' +
          ('0 lint findings without a root' if not raw_findings else '; '.join(f'{lv} line {n}: {m}' for lv, n, m in raw_findings)))
    ok &= not raw_findings
    try:
        lines, policy, sha = L.render_run(L.KIT, organ, fixtures[organ])
        flags = L.policy_flags(policy)
        opts, _args = cli.parse(flags)
        round_trip = A.normalize(cli.autogen_policy(opts, lines))['sha256']
        if round_trip != sha:
            raise ValueError(f'bin/symblic-task would send a policy with sha256 {round_trip[:12]}, LIFE expects {sha[:12]}')
        print(f'PASS  template   {organ}: {len(lines)} statements, 0 lint findings, policy sha256 {sha[:12]} = CLI round trip, {len(flags)} flags')
    except Exception as exc:
        print(f'FAIL  template   {organ}: {exc}'); ok = False
worst = {o: L.worst_values(o, fixtures) for o in L.AGENT_ORGANS}
w = worst['codebase']
assert len(w['test_id']) == L.TEST_ID_MAX and w['ws'].endswith(f'-{L.MAX_DEPTH}-ffffffff') and len(w['review_note']) == 240, 'worst fixture'
assert all(len(p) == 80 for p in w['scope'].split(' inside the files ')[1].split(L.LOCAL_FIX_RULE)[0].split(', ')), 'worst paths'
assert len(worst['database']['request']) == L.REQUEST_MAX_CHARS and len(worst['selfdev']['lesson']) == L.LESSON_MAX_CHARS
for organ, values in worst.items():
    try:
        L.render_run(L.KIT, organ, values)
        print(f'PASS  worst      {organ}: the largest values render within {L.STATEMENT_MAX} characters')
    except Exception as exc:
        print(f'FAIL  worst      {organ}: {exc}'); ok = False
for organ in L.AGENT_ORGANS:
    raw = A.statements(open(f'{L.KIT}/organs/{organ}.lines.txt', encoding='utf-8').read())
    if any(line.split()[0].lower() not in A.VERBS for line in raw):
        print(f'FAIL  verbs      {organ}: a template line does not start with a symblic_autogen verb'); ok = False
sys.path.insert(0, L.KIT + '/bin')
ctl_spec = importlib.util.spec_from_file_location('life_ctl', L.KIT + '/bin/life-ctl.py')
ctl = importlib.util.module_from_spec(ctl_spec); ctl_spec.loader.exec_module(ctl)
release = ctl.check_release(L.KIT)
print(('PASS  release    ' if not release else 'FAIL  release    ') + ('check_release accepts the kit' if not release else '; '.join(release)))
ok &= not release
sys.exit(0 if ok else 1)
PYEOF
then :; else fail=1; fi

echo "== 5 syntax =="
for f in "$KIT"/bin/*.sh "$KIT"/checks/*.sh "$KIT/VALIDATE.sh"; do
  if bash -n "$f" 2>/dev/null; then pass "bash -n" "${f#$KIT/}"; else bad "bash -n" "${f#$KIT/}"; fi; done
for f in "$KIT"/bin/*.py; do
  if $PY -c 'import ast,sys; ast.parse(open(sys.argv[1],encoding="utf-8").read(), sys.argv[1])' "$f" 2>/dev/null; then
    pass ast "${f#$KIT/}"; else bad ast "${f#$KIT/}"; fi; done
for f in "$KIT"/organs/*.json "$KIT"/policies/*.json "$KIT"/spawn/example/*.json "$KIT"/benchmarks/*.json; do
  if $PY -c 'import json,sys; json.load(open(sys.argv[1],encoding="utf-8"))' "$f" 2>/dev/null; then :; else bad json "${f#$KIT/}"; fi; done

echo "== 6 databases (in memory, applied twice) =="
if $PY - "$KIT" <<'PYEOF'
import sqlite3, sys
kit = sys.argv[1]
c = sqlite3.connect(':memory:'); c.execute('PRAGMA foreign_keys=ON')
for _ in (1, 2):
    c.executescript(open(kit + '/db/life.sql', encoding='utf-8').read())
need = {'meta','releases','cells','cell_events','cell_programs','items','calls','runs','divisions','commands','sources',
        'question_sources','answers','knowledge','patches','proposals','experiments','results','migrations','samples',
        'governor','node_holds','budget','metrics','notices','call_intents','workspace_guard'}
have = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
assert need <= have, need - have
c.execute("INSERT INTO releases (release, at, source, manifest, active) VALUES (1, 0, 'kit', '{}', 1)")
n = 0
def refused(sql):
    global n
    try:
        c.execute(sql)
    except sqlite3.IntegrityError:
        n += 1
        return True
    return False
cell = "INSERT INTO cells (cell_id, organ, kind, parent_id, depth, focus, node, workspace, state, born_at, release) VALUES "
item = "INSERT INTO items (item_id, organ, kind, stage, state, taint, payload, created_at, updated_at, cell_id) VALUES "
assert refused("INSERT INTO releases (release, at, source, manifest, active) VALUES (2, 0, 'kit', '{}', 1)")
assert refused(cell + "('learning.11.00000000', 'learning', 'model', NULL, 11, 'research something', 'node-d', NULL, 'active', 0, 1)")
assert refused(cell + "('brain.0.00000000', 'brain', 'model', NULL, 0, 'think about things', 'node-d', NULL, 'active', 0, 1)")
assert refused(cell + "('learning.00.00000000', 'learning', 'model', NULL, 0, 'research something', 'node-d', NULL, 'active', 0, 1)")
assert refused(cell + "('learning.0.0000000g', 'learning', 'model', NULL, 0, 'research something', 'node-d', NULL, 'active', 0, 1)")
assert refused(cell + "('codebase.0.00000000', 'codebase', 'model', NULL, 0, 'fix failing tests', 'node-i', NULL, 'active', 0, 1)")
assert refused(cell + "('codebase.0.00000000', 'codebase', 'agent', NULL, 0, 'fix failing tests', 'node-h', '/w/a', 'active', 0, 1)")
assert refused(cell + "(NULL, 'learning', 'model', NULL, 0, 'research something', 'node-d', NULL, 'active', 0, 1)")
assert refused(cell + "('learning.1.5.000000', 'learning', 'model', NULL, 1.5, 'research something', 'node-d', NULL, 'active', 0, 1)")
c.execute(cell + "('learning.0.00000000', 'learning', 'model', NULL, 0, 'research the open questions', 'node-d', NULL, 'active', 0, 1)")
c.execute(cell + "('codebase.0.00000000', 'codebase', 'agent', NULL, 0, 'fix failing tests', 'node-i', '/w/a', 'active', 0, 1)")
assert refused(cell + "('codebase.1.0000000a', 'codebase', 'agent', 'codebase.0.00000000', 1, 'fix other tests', 'node-i', '/w/a', 'active', 0, 1)")
assert refused(cell + "('digest.1.0000000b', 'digest', 'model', 'learning.0.00000000', 1, 'digest other things', 'node-b', NULL, 'active', 0, 1)")
assert refused(cell + "('learning.3.0000000c', 'learning', 'model', 'learning.0.00000000', 3, 'research deeper things', 'node-d', NULL, 'active', 0, 1)")
assert refused("UPDATE cells SET depth=1 WHERE cell_id='learning.0.00000000'")
assert refused(item + "('learning:0123456789abcdef', 'learning', 'source', 'research', 'queued', 'owner', '{}', 0, 0, NULL)")
assert refused(item + "('learning:0123456789abcdeg', 'learning', 'question', 'research', 'queued', 'owner', '{}', 0, 0, NULL)")
assert refused(item + "('immune:0123456789abcdef', 'immune', 'lesson', 'review', 'queued', 'code', '{}', 0, 0, NULL)")
assert refused(item + "('digest:0123456789abcdef', 'digest', 'source', 'apply', 'queued', 'web', '{}', 0, 0, NULL)")
assert refused(item + "('digest:0123456789abcdef', 'digest', 'source', 'fetch', 'queued', 'web', '{}', 0, 0, 'learning.0.00000000')")
c.execute(item + "('immune:0123456789abcdef', 'immune', 'patch', 'review', 'queued', 'code', '{}', 0, 0, NULL)")
assert refused("UPDATE items SET taint='owner' WHERE item_id='immune:0123456789abcdef'")
assert refused("UPDATE items SET priority=1.5 WHERE item_id='immune:0123456789abcdef'")
c.execute("INSERT INTO divisions (division_id, parent_id, stage, release, snapshot, started_at) VALUES ('d1', 'learning.0.00000000', 'foci', 1, '[]', 0)")
assert refused("INSERT INTO divisions (division_id, parent_id, stage, release, snapshot, started_at) VALUES ('d2', 'codebase.0.00000000', 'workspaces', 1, '[]', 0)")
c.execute("INSERT INTO budget (day) VALUES ('2026-10-11')")
assert refused("UPDATE budget SET births = -1")
assert refused("INSERT INTO migrations (migration_id, item_id, sha256, state, at) VALUES ('0001_x', NULL, 'a', 'pending', 0)")
assert refused("INSERT INTO metrics (organ, day, items_done) VALUES ('learning', '2026-10-11', 1.5)")
assert refused("INSERT INTO metrics (organ, day) VALUES ('brain', '2026-10-11')")
assert refused("INSERT INTO notices (notice_id, kind, subject, text, state, at, last_at, count) VALUES ('0123456789ab', 'held', 's', 't', 'open', 0, 0, 1.5)")
assert refused("INSERT INTO node_holds (node, cause, subject, until, reason) VALUES ('node-d', 'reboot', '', 5, '')")
assert refused("INSERT INTO node_holds (node, cause, subject, until, reason) VALUES ('node-d', 'infra', '', 0, '')")
o = sqlite3.connect(':memory:')
for _ in (1, 2):
    o.executescript(open(kit + '/db/organism.sql', encoding='utf-8').read())
assert {r[0] for r in o.execute("SELECT name FROM sqlite_master WHERE type='table'")} == {'schema_migrations'}
print(f'PASS  sqlite     life.sql (schema 5), organism.sql, {n} bad rows refused')
sys.exit(0 if n == 28 else 1)
PYEOF
then :; else bad sqlite "life.sql or organism.sql"; fi

echo "== 7 canaries =="
if $PY - "$KIT" <<'PYEOF'
import os, shlex, sys
kit = sys.argv[1]
lines = [ln.strip() for ln in open(kit + '/checks/canaries.txt', encoding='utf-8') if ln.strip() and not ln.startswith('#')]
programs = ['classify-command', 'triage-error', 'extract-source', 'distill-lesson', 'propose-experiment', 'rank-experiment',
            'review-patch', 'reproduce', 'assign-item']
want = [f'/home/operator/host-checkout/bin/symblic check {{release_dir}}/genome/{p}.sym' for p in programs]
want.append('/usr/bin/python3 -B {kit}/bin/life-check.py registry')
assert lines == want, 'checks/canaries.txt must be exactly the nine program checks and the registry check, in order'
for line in lines:
    argv = shlex.split(line.replace('{release_dir}', kit).replace('{kit}', kit))
    assert os.path.isfile(argv[0]) and os.path.isfile(argv[-1] if argv[-1].endswith('.sym') else argv[-2]), line
PYEOF
then pass canaries "10 lines, exact"; else bad canaries "checks/canaries.txt"; fi

echo "== 8 benchmarks example =="
if $PY - "$KIT" <<'PYEOF'
import importlib.util, json, sys
kit = sys.argv[1]
sys.path.insert(0, kit + '/bin')
spec = importlib.util.spec_from_file_location('life_tick', kit + '/bin/life-tick.py')
tick = importlib.util.module_from_spec(spec); spec.loader.exec_module(tick)
d = json.load(open(kit + '/benchmarks/benchmarks.example.json', encoding='utf-8'))
assert d['version'] == 2 and d['benchmarks']
ids = [b['id'] for b in d['benchmarks']]
assert len(ids) == len(set(ids))
for b in d['benchmarks']:
    assert not tick.bench_problems(b), (b.get('id'), tick.bench_problems(b))
assert tick.bench_problems(dict(d['benchmarks'][0], baseline='6; rm -rf ~'))
assert tick.bench_problems(dict(d['benchmarks'][0], param_rx='^' + 'a*' * 20 + 'b$', baseline='b')), 'a backtracking param_rx'
assert tick.bench_problems(dict(d['benchmarks'][0], param_rx='^(a|b)+$', baseline='a')), 'a repeated group'
# the generated run wrapper, run by sh exactly as the map route runs it: "$1" = k:value
import shlex, subprocess, tempfile
cmd = tick.bench_wrapper("printf 'LIFE_RESULT 1.5 s\\n'; printf %s {{item}} >/dev/null", 30)
with tempfile.TemporaryDirectory() as tmp:
    for item in ('2:7', "4:x'y", '0:a:b'):
        body = shlex.quote(cmd.replace('{{item}}', '"$1"') + ' 2>&1')
        r = subprocess.run(['sh', '-c', f'sh -c {body} life-map {shlex.quote(item)}'], capture_output=True, text=True,
                           timeout=30, env={'PATH': '/usr/bin:/bin', 'TMPDIR': tmp})
        k = item.split(':')[0]
        m = tick.RUN_RX.search(r.stdout)
        assert m and m.group(1) == k and m.group(3) == '0' and not m.group(4) and 'LIFE_RESULT 1.5 s' in m.group(2), (item, r.stdout, r.stderr)
    long = tick.bench_wrapper("head -c 5000 /dev/zero | tr '\\0' x; printf %s {{item}} >/dev/null", 30)
    r = subprocess.run(['sh', '-c', f'sh -c {shlex.quote(long.replace("{{item}}", chr(34) + "$1" + chr(34)) + " 2>&1")} life-map 1:v'],
                       capture_output=True, text=True, timeout=30, env={'PATH': '/usr/bin:/bin', 'TMPDIR': tmp})
    m = tick.RUN_RX.search(r.stdout)
    assert m and m.group(4), ('a long output is marked LIFE_TRUNC', r.stdout[-200:])
PYEOF
then pass bench "benchmarks.example.json, param grammar, run wrapper framing"; else bad bench "benchmarks.example.json"; fi

echo "== 9 LIFE.md embeds every file verbatim =="
if $PY - "$KIT" <<'PYEOF'
import os, re, sys
kit = sys.argv[1]
data = open(kit + '/LIFE.md', 'rb').read()
text = data.decode('utf-8')
blocks = re.findall(r'^### (\S+)\n\n(`{3,4})[a-z]*\n(.*?)\n\2$', text, re.M | re.S)
seen, bad = set(), []
for path, _fence, body in blocks:
    if path in seen:
        bad.append(path + ' embedded twice')
    seen.add(path)
    full = os.path.normpath(os.path.join(kit, path))
    if path.startswith('/') or '..' in path.split('/') or not full.startswith(kit + '/') or os.path.islink(full):
        bad.append(path + ' is not a kit path')
        continue
    try:
        if open(full, 'rb').read() != (body + '\n').encode('utf-8'):
            bad.append(path + ' differs')
    except OSError:
        bad.append(path + ' missing')
want = set()
for root, dirs, files in os.walk(kit):
    rel_root = os.path.relpath(root, kit)
    dirs[:] = [d for d in dirs if d != '__pycache__' and not (rel_root == '.' and d == 'workshop')]
    for f in files:
        rel = os.path.normpath(os.path.join(rel_root, f))
        if rel not in ('LIFE.md', 'BRIEF.md'):
            want.add(rel)
bad += [p + ' not embedded' for p in sorted(want - seen)]
bad += [p + ' embedded but not a kit file' for p in sorted(seen - want)]
if bad:
    print('\n'.join(bad))
sys.exit(1 if bad else 0)
PYEOF
then pass embed "LIFE.md appendices"; else bad embed "LIFE.md appendices"; fi

echo "== 10 platform contract =="
if out="$($PY -c 'import sys; sys.path.insert(0, "/home/operator/host-checkout/docs/life/bin"); import life_common as L; p = L.contract_problems(); print("; ".join(p)); sys.exit(1 if p else 0)')"; then
  pass contract "platform facts hold"; else bad contract "$out"; fi

echo "== 11 rules (pure functions, no model) =="
if $PY - "$KIT" <<'PYEOF'
import ast, math, re, sqlite3, sys
kit = sys.argv[1]
sys.path.insert(0, kit + '/bin')
sys.path.insert(1, '/home/operator/host-checkout')
import life_common as L
import symblic_autogen as A
checks = 0
def expect(cond, what):
    global checks
    checks += 1
    if not cond:
        raise AssertionError(what)
g = lambda n: open(f'{kit}/genome/{n}.sym', encoding='utf-8').read()
a = g('assign-item')
expect(L.genome_protected_problems(a, a.replace('"the item fits the first focus better"', '"the item fits the second focus better"')),
       'an enum description swap must be refused')
expect(not L.genome_protected_problems(a, a.replace('"Which focus fits this item better?', '"Which of the two foci fits this item best?')),
       'a real instruction edit of assign-item must be accepted')
e = g('extract-source')
expect(not L.genome_protected_problems(e, e.replace('"State one specific factual claim this text supports, in your own words."',
                                                   '"State one specific factual claim that this text supports."')),
       'an indented ask instruction edit must be accepted')
expect(L.genome_protected_problems(a, a.replace(' Item: {item_text}"', '"')), 'removing a placeholder must be refused')
expect(L.genome_protected_problems(e, e.replace('note Worker', 'note Changed worker')), 'a note edit must be refused')
expect(L.genome_protected_problems(e, e), 'no change must be refused')
expect(L.genome_placement_problems(a.replace('with effort=low, retries=2', 'with effort=low, retries=2, by=claude:haiku')),
       'an ask-level by= must be refused')
expect('review-patch' in L.SELFDEV_PROTECTED and not L.PLACEHOLDERS['program'].fullmatch('review-patch'), 'review-patch is protected')
expect(not re.search(r'ask program: one of \{[^}]*review-patch', g('distill-lesson')), 'distill-lesson never offers a protected program')
for p_ in L.PROGRAMS:
    expect(all(L.ASK_RX.fullmatch(ln) for ln in g(p_).splitlines() if ln.lstrip().startswith('ask ')), f'{p_}: every ask line parses')
# migrations and snapshots
expect(not L.migration_problems('CREATE TABLE IF NOT EXISTS org_pages (page_id TEXT, view INTEGER, note TEXT DEFAULT \'a; b\');'),
       'a column named view and a literal holding ; must be accepted')
expect(L.migration_problems('DROP TABLE org_x;'), 'DROP must be refused')
expect(L.migration_problems('CREATE TABLE IF NOT EXISTS org_x (a INTEGER REFERENCES schema_migrations(migration_id));'),
       'a reference to a non-org table must be refused')
expect(L.migration_problems('CREATE TABLE IF NOT EXISTS org_x (a INTEGER REFERENCES [schema_migrations](migration_id));'),
       'a quoted reference must be refused')
expect(L.migration_problems('CREATE TABLE IF NOT EXISTS org_x (a INTEGER REFERENCES "org_y"(id));'), 'a double-quoted identifier is refused')
expect(L.migration_problems('CREATE TABLE IF NOT EXISTS org_x (a INTEGER REFERENCES org_y (id));'),
       'a reference to an org_ table that does not exist must be refused')
expect(not L.migration_problems('CREATE TABLE IF NOT EXISTS org_y (id INTEGER PRIMARY KEY); CREATE TABLE IF NOT EXISTS org_x '
                                '(a INTEGER REFERENCES org_y (id));'), 'a reference to a table created above it is accepted')
expect(L.migration_problems('CREATE TABLE IF NOT EXISTS org_x (a);', 'CREATE TABLE org_x (a);'), 'an existing table must be refused')
expect(L.migration_problems('CREATE TABLE IF NOT EXISTS org_x (a TEXT DEFAULT (readfile(\'/etc/passwd\')));'), 'readfile must be refused')
expect(L.migration_problems('CREATE TABLE IF NOT EXISTS org_a (id INTEGER PRIMARY KEY AUTOINCREMENT, x TEXT);'), 'AUTOINCREMENT is refused')
expect(L.migration_problems('CREATE TABLE IF NOT EXISTS org_a (x TEXT); /* hidden */'), 'a block comment is refused')
expect(L.snapshot_problems("ATTACH DATABASE '/tmp/x' AS y;"), 'an ATTACH in a snapshot must be refused')
expect(L.migration_problems('CREATE TABLE IF NOT EXISTS org_x (sqlite_note TEXT);'), 'a sqlite_ column is refused before it poisons a snapshot')
expect(L.migration_problems('CREATE TABLE IF NOT EXISTS org_x (claim TEXT UNIQUE ON CONFLICT REPLACE);'), 'ON CONFLICT REPLACE is refused')
expect(L.migration_problems('CREATE TABLE IF NOT EXISTS org_x (Title TEXT);'), 'an upper-case column name is refused')
expect(L.migration_problems('CREATE TABLE IF NOT EXISTS org_x (a TEXT)'), 'a statement without its semicolon is refused')
expect(L.migration_problems("ALTER TABLE org_papers ADD COLUMN 'title' TEXT;", 'CREATE TABLE org_papers (doi TEXT);'), 'a quoted column is refused')
expect(L.migration_problems('ALTER TABLE org_papers ADD COLUMN title VARCHAR;', 'CREATE TABLE org_papers (doi TEXT);'), 'an unknown type is refused')
expect(L.migration_problems('CREATE TABLE IF NOT EXISTS org_x (a TEXT CHECK (a != 1));'), 'CHECK is refused')
expect(L.migration_problems('CREATE TABLE IF NOT EXISTS org_y (id INTEGER PRIMARY KEY, n TEXT); CREATE TABLE IF NOT EXISTS org_x '
                            '(a TEXT REFERENCES org_y (n));'), 'a reference to a column that is not a key is refused')
expect(L.migration_problems('CREATE UNIQUE INDEX IF NOT EXISTS org_u ON org_papers (doi);', 'CREATE TABLE org_papers (doi TEXT);'),
       'a UNIQUE index on a snapshot table is refused (its rows are not visible to the agent)')
expect(not L.migration_problems('CREATE TABLE IF NOT EXISTS org_r (fact_id TEXT PRIMARY KEY, claim TEXT, n INTEGER DEFAULT 0, '
                                "note TEXT DEFAULT 'x'); CREATE UNIQUE INDEX IF NOT EXISTS org_r_claim ON org_r (claim);"),
       'the column grammar accepts a store-shaped table and a unique index on a table created in the file')
db = sqlite3.connect(':memory:')
for s_ in L.split_sql(open(kit + '/db/organism.sql', encoding='utf-8').read()):
    db.execute(s_)
for s_ in L.split_sql('CREATE TABLE IF NOT EXISTS org_papers (doi TEXT, view INTEGER); CREATE INDEX IF NOT EXISTS org_papers_doi ON org_papers (doi);'):
    db.execute(s_)
snap = L.snapshot_sql(db)
expect(snap.index('CREATE TABLE org_papers') < snap.index('CREATE INDEX org_papers_doi') and not L.snapshot_problems(snap),
       'a snapshot lists a table before its index and accepts a column named view')
expect(not L.migration_problems('ALTER TABLE org_papers ADD COLUMN title TEXT;', snap), 'ADD COLUMN on an indexed table is accepted')
db.execute('CREATE TABLE org_seq (id INTEGER PRIMARY KEY AUTOINCREMENT)'); db.execute('INSERT INTO org_seq DEFAULT VALUES')
expect('sqlite_sequence' not in L.snapshot_sql(db), 'snapshots never hold sqlite_ objects')
# credentials
expect(not L.has_secret('Research how password hashing with argon2 compares to bcrypt'), 'the word password alone passes')
expect(L.has_secret('password = hunter22x'), 'a password value is refused')
expect(L.has_secret('token=abcdefghijk'), 'a token value is refused')
expect(L.has_secret('PASSWORD: "two words here"'), 'a quoted password value is refused')
expect(L.has_secret('https://user:pw@example.org/x'), 'URL userinfo is refused')
for kw in ('token', 'password', 'api_key', 'secret'):
    for code_ in (f"{kw} = request.headers.get('X-Token')", f'{kw} = getpass.getpass()', f"{kw} = os.environ['API_KEY']",
                  f'def check_{kw}({kw}=None):', f'{kw}: ceramic foams absorb water'):
        expect(not L.has_secret_code(code_), f'code is not a credential: {code_}')
    expect(L.has_secret_code(f'{kw}=abcd1234efgh5678ij'), f'{kw}= with 18 letters and digits is a credential in code')
    expect(L.has_secret_code(f'{kw} = "s3cr3t-value"'), f'a quoted {kw} literal is a credential in code')
expect(not L.has_secret('akia' + 'a' * 16) and not L.has_secret('begin the private key exchange'), 'token prefixes are case-sensitive')
expect(L.has_secret('AKIA' + 'A' * 16) and L.has_secret('Bearer ' + 'a' * 20), 'upper-case prefixes and bearer still match')
# verify lines
expect(not L.verify_line_problems('database', b'migration=0001_org_x\n', 'migration=0001_org_x'), 'exact verify line passes')
expect(L.verify_line_problems('database', b' migration=0001_org_x\n', 'migration=0001_org_x'), 'a leading space fails')
expect(L.verify_line_problems('database', b'migration=0001_org_x\n\n', 'migration=0001_org_x'), 'an extra line fails')
expect(not L.verify_line_problems('selfdev', b'lesson=0123456789abcdef program=reproduce\n', 'lesson=0123456789abcdef program=reproduce'),
       'the selfdev verify line names the lesson')
# the gate
expect(L.patch_problems(['bin/devcheck'], 'local_fix', '+x\n', ('bin/devcheck',)), 'a patch to bin/ is refused')
expect(L.patch_problems(['scripts/devcheck.py'], 'local_fix', '+x\n', ('scripts/devcheck.py',)), 'a patch to scripts/ is refused')
expect(L.patch_problems(['tests/test_x.py'], 'test_only', '-    self.assertEqual(a, b)\n+    pass\n', ('tests/test_x.py',)), 'removing an assertion is refused')
expect(L.patch_problems(['tests/test_x.py'], 'test_only', '+    @unittest.skip("x")\n', ('tests/test_x.py',)), 'adding a skip is refused')
expect(L.patch_problems(['tests/test_y.py'], 'test_only', '+    x = 1\n', ('tests/test_x.py',)), 'test_only touches only its own module')
expect(L.patch_problems(['other.py'], 'local_fix', '+x\n', ('named.py',)), 'a local_fix outside the named files is refused')
expect(not L.patch_problems(['named.py'], 'local_fix', '+x = 1\n', ('named.py',)), 'a local_fix inside the named files passes')
expect(L.patch_problems(['README.md'], 'comment_or_doc', '+x\n'), 'a root README is not docs/**/*.md')
expect(L.patch_problems(['docs/agents/CONTRACTS.md'], 'comment_or_doc', '+x\n'), 'agent instructions are protected')
expect(all(L.GATE_DENY_RX.match(p_) for p_ in ('config/.env', 'app/secrets_data/x', 'ruff.toml', '.ruff.toml', 'conftest.py',
                                                'requirements-devtest.lock', 'sub/.gitattributes')), 'judge configuration and private paths anywhere')
expect(L.patch_problems(['docs/x.md'], 'comment_or_doc', 'deleted file mode 100644\nnew file mode 120000\n+x\n'), 'a symlink in a diff is refused')
expect(L.patch_problems(['docs/x.md'], 'comment_or_doc', 'old mode 100644\nnew mode 100755\n'), 'a mode change is refused')
expect(not L.patch_problems(['docs/a/b.md'], 'comment_or_doc', '+x\n'), 'docs at any depth pass')
expect(all(L.GATE_DENY_RX.match(f) for f, _rx, _w in L.CONTRACT), 'every CONTRACT file is protected from patches')
expect(not L.local_fix_problems('def f(x):\n    return x\n', 'def f(x):\n    return x + 1\n', ['f']), 'a body fix passes')
expect(L.local_fix_problems('def f(x):\n    return x\n', 'def f(x, y):\n    return x\n', ['f']), 'a signature change is refused')
expect(L.local_fix_problems('def f(x):\n    return x\ndef g():\n    pass\n', 'def f(x):\n    return x\ndef g():\n    return 1\n', ['f']),
       'a function the traceback does not name is refused')
expect(L.local_fix_problems('def f():\n    def inner(x):\n        return x\n    return inner(1)\n',
                            'def f():\n    def inner(x, y=0):\n        return x\n    return inner(1)\n', ['f', 'f.inner']),
       'a nested signature change is refused')
prop_old = 'class C:\n    @property\n    def x(self):\n        return 1\n    @x.setter\n    def x(self, v):\n        pass\n'
prop_new = 'class C:\n    @property\n    def x(self):\n        return 2\n    @x.setter\n    def x(self, v):\n        pass\n'
expect(L.local_fix_problems(prop_old, prop_new, ['C.x#2']), 'a getter is not authorized by its setter (duplicate names stay distinct)')
expect(not L.local_fix_problems(prop_old, prop_new, ['C.x']), 'the first definition of C.x is C.x')
two = 'class A:\n    def run(self):\n        return 1\nclass B:\n    def run(self):\n        return 2\n'
expect(L.function_at(two, 5) == 'B.run' and L.function_at(two, 2) == 'A.run', 'a traceback line resolves to its own class')
expect(L.local_fix_problems(two, two.replace('return 1', 'return 3'), ['B.run']), 'run in B never authorizes run in A')
expect(L.path_class(['docs/a.md']) == 'docs' and L.path_class(['x.yaml']) == 'other' and L.path_class(['a.js']) == 'live_static'
       and L.path_class(['a.py', 'b.js']) == 'mixed', 'path classes')
expect(L.traceback_files('File "/w/c/server_x.py", line 3\nFile "/w/c/tests/t.py"', '/w/c') == ['server_x.py'], 'traceback files')
expect(L.traceback_files('File "/w/c/ok/../../outside.py", line 3, in f', '/w/c') == [], 'a .. path is never a traceback file')
expect(L.failure_fingerprint('Traceback\nAssertionError: 3 != 4') == ('AssertionError', '# != #'), 'failure fingerprint')
expect(L.failure_fingerprint('no exception here') is None, 'no fingerprint without an exception line')
expect(not L.env_error(1, 'FAIL: test_sandbox_rules\nAssertionError: Landlock sandbox not applied', '/nonexistent'),
       'a failing test that mentions sandbox or Landlock is a finding')
expect(not L.env_error(1, "ImportError: cannot import name 'gone' from 'server_x'", '/nonexistent'), 'an ImportError the code caused is a finding')
expect(L.env_error(1, "ModuleNotFoundError: No module named 'numpy'", '/nonexistent'), 'a missing third-party module is the environment')
expect(L.env_error(125, '', '/x') and L.env_error(1, 'PermissionError: [Errno 13] Permission denied: /home/operator/.cache', '/w/c'),
       'a sandbox refusal or a denied path outside the clone is the environment')
# identities
expect(L.parse_cell('learning.10.0123abcd')[1] == 10, 'depth 10 parses')
for bad in ('learning.01.0123abcd', 'learning.11.0123abcd', 'learning.1.0123abcg', ' learning.1.0123abcd'):
    try:
        L.parse_cell(bad); expect(False, f'{bad!r} must not parse')
    except ValueError:
        checks += 1
expect(L.valid_test_id('tests.test_x.Case.test_y') and not L.valid_test_id('tests.' + 'a' * 65) and not L.valid_test_id('tests.' + '.'.join(['a'] * 6)),
       'test id bounds')
expect(not L.payload_problems('finding', 'patch', {'test_id': 'tests.test_x', 'finding_text': 'f', 'base_commit': 'a' * 40,
                                                   'source': 'watch', 'wall_s': 1, 'trace_files': ['x.py'],
                                                   'trace_functions': {'x.py': ['C.f']}, 'change_class': 'test_only'}), 'a valid payload')
expect(L.payload_problems('question', 'research', {'question': {}, 'command_id': [], 'found': True}), 'payload values are typed')
expect(L.payload_problems('question', 'research', {'question': 'q', 'command_id': '', 'found': 10}), 'found is 0..9')
expect(L.payload_problems('finding', 'patch', {'test_id': 't'}), 'a payload missing keys is refused')
expect(L.payload_problems('request', 'draft', {'request': 'x' * 10, 'extra': 1}), 'an unknown payload key is refused')
expect(L.payload_problems('request', 'draft', {'request': 'x' * (L.PAYLOAD_MAX + 1)}), 'an oversize payload is refused')
expect(L.lint_safe('as before, the last test failed earlier', 200) == 'as stated, the final test failed before', 'lint rewrites')
long_a, long_b = 'tests.' + 'a' * 150 + 'x', 'tests.' + 'a' * 150 + 'y'
expect(L.notice_subject(long_a) != L.notice_subject(long_b) and len(L.notice_subject(long_a)) == 120, 'notice keys never merge')
expect(L.plain_line('a {b} `c`', 20) == 'a {b} `c`', 'operative text keeps braces and backticks')
try:
    L.scope_argv(['true'], runtime=0); expect(False, 'a scope without a runtime must be refused')
except ValueError:
    checks += 1
# the unit and every bound
unit = open(kit + '/units/life-tick.service', encoding='utf-8').read()
expect(f'TimeoutStartSec={L.UNIT_TIMEOUT}' in unit and L.TICK_HARD + 300 == L.UNIT_TIMEOUT, 'unit timeout = UNIT_TIMEOUT = TICK_HARD + 300')
expect('SuccessExitStatus=1 3 4 5 6' in unit and 'Restart=no' in unit and f'TasksMax={L.TICK_TASKS_MAX}' in unit
       and 'ExecStart=/usr/bin/python3 -I -B ' in unit and 'ExecStopPost=-/usr/bin/systemctl --user stop life-*.scope' in unit, 'unit file')
for name in ('RESEARCH_TIMEOUT', 'CALL_TIMEOUT', 'GATE_STAGE_SECONDS', 'WATCH_STAGE_SECONDS', 'CONFIRM_STAGE_SECONDS', 'CLONE_TIMEOUT',
             'START_STAGE_SECONDS', 'APPLY_STAGE_SECONDS', 'SELFDEV_GATE_STAGE_SECONDS', 'CANARY_ROUND_SECONDS', 'FETCH_TIMEOUT'):
    expect(getattr(L, name) + L.KILL_GRACE + L.START_MARGIN <= L.TICK_HARD, f'{name} can start in some tick')
expect(L.GATE_DEVCHECK_TIMEOUT + L.GATE_TEST_TIMEOUT + 60 <= L.GATE_TIMEOUT, 'the gate script fits GATE_TIMEOUT')
expect(L.RESEARCH_TIMEOUT >= L.RESEARCH_GENERATIONS * (L.RESEARCH_STEP_TIMEOUT + L.RESEARCH_STEP_POLL_EXTRA)
       + L.RESEARCH_TOOLS * L.RESEARCH_TOOL_SECONDS, 'the research timeout covers its derived worst case')
expect(L.BENCH_RUNS * (L.BENCH_TIMEOUT_MAX + L.BENCH_RUN_SLACK) + L.BENCH_JOB_EXTRA <= 3600, 'a benchmark job fits CMD_TIMEOUT_MAX')
expect(L.BENCH_RUNS * (L.BENCH_OUT_BYTES + 64) <= 40000, 'a benchmark job output fits OUT_HEAD')
expect(len(L.BENCH_ORDER) == 2 * L.BENCH_PAIRS and L.BENCH_ORDER.count('baseline') == L.BENCH_PAIRS, 'ABBA order')
expect(L.MODEL_CALLS_PER_DAY >= L.PROGRAM_RUNS_PER_DAY * L.CALL_MAX_MODEL_CALLS, 'the model-call budget covers every reserved run')
expect(L.CALL_MAX_MODEL_CALLS * L.OLLAMA_LIMITS['timeout_seconds'] <= L.CALL_TIMEOUT, 'every model call of a program fits its process wall')
expect(L.PROMPT_CHARS_MAX // 3 + 256 + L.OLLAMA_LIMITS['num_predict'] <= L.KV_CTX_TOKENS
       and L.SOURCE_TEXT_CHARS + 3000 <= L.PROMPT_CHARS_MAX and L.DIFF_REVIEW_BYTES + 3000 <= L.PROMPT_CHARS_MAX,
       'every LIFE prompt reaches only the KV_CTX_TOKENS bucket the memory rule assumes')
expect(L.DIVISION_MAX_TICKS == L.DIVISION_STEP_EVERY * (1 + L.FOCI_RETRIES + math.ceil(L.ASSIGN_MAX / L.ASSIGN_PER_SLOT)) + 3 + 12,
       'the division tick bound is derived')
expect(L.AGENT_RUN_KILL_SECONDS <= L.NODE_BUSY_MAX and L.AGENT_WALL_SECONDS < L.AGENT_RUN_KILL_SECONDS
       and L.AGENT_POLICY_FIXED['wall_seconds'] == L.AGENT_WALL_SECONDS, 'one agent run fits one node duty window')
expect(L.PREMIGRATION_KEEP_BYTES + (1 + L.BACKUP_KEEP) * L.ORGANISM_MAX_BYTES < L.STATE_MAX_BYTES, 'storage parts fit the storage bound')
sql_text = open(kit + '/db/life.sql', encoding='utf-8').read()
expect(f'depth BETWEEN 0 AND {L.MAX_DEPTH}' in sql_text and L.CELL_RX.pattern.count('|10)') == 1
       and f'length(subject) <= 120' in sql_text and 'length(payload) <= 16384' in sql_text and L.PAYLOAD_MAX == 16384,
       'protocol limits (depth, subject, payload) are equal in code, SQL and regexes')
gate_text = open(kit + '/checks/devcheck-gate.sh', encoding='utf-8').read()
expect('./bin/devcheck --changed "$base" --no-tests' in gate_text, 'the gate runs devcheck without bin/devtest (--no-tests)')
src = open(kit + '/bin/life-tick.py', encoding='utf-8').read()
ns = re.search(r"NON_SEMANTIC = \(([^)]*)\)", src).group(1)
expect(set(re.findall(r"'([A-Z_]+)'", ns)) <= set(A.FAILURE_CLASSES), 'every NON_SEMANTIC label is an autogen failure class')
code = src + open(kit + '/bin/life_common.py', encoding='utf-8').read() + open(kit + '/bin/life-ctl.py', encoding='utf-8').read()
kinds = set(re.findall(r"L?\.?notice\((?:self\.)?conn, '([a-z_]+)'", code)) | set(re.findall(r"notice\(conn, '([a-z_]+)'", code))
kinds |= {'command_' + r for r in ('immune', 'none')}
expect(kinds <= set(L.NOTICE_KINDS), 'undeclared notice kinds: ' + ', '.join(sorted(kinds - set(L.NOTICE_KINDS))))
metas = set(re.findall(r"set_meta\((?:conn, )?'([a-z_0-9]+)'", code))
expect(metas <= set(L.META_KEYS), 'undeclared meta keys: ' + ', '.join(sorted(metas - set(L.META_KEYS))))
for name in ('io', 'memory'):
    lines = open(f'/proc/pressure/{name}', encoding='ascii').read().splitlines()
    expect(sum(1 for ln in lines if ln.startswith('full ' if name == 'io' else 'some ')) == 1, f'/proc/pressure/{name} readable')
expect(L.limits_rows() and all(m for _n, _v, m in L.limits_rows()), 'every limits line has a meaning')
print(f'{checks} rule cases')
PYEOF
then pass rules "protected lines, placement, migrations, secrets, verify, gate, local_fix, paths, ids, payloads, unit, bounds, kinds"; else bad rules "a rule case failed"; fi

echo "== 12 numbers =="
num=0
for f in "$KIT"/bin/*.py; do
  [ "$(basename "$f")" = life_common.py ] && continue
  if grep -nE 'timeout=[0-9]|\b(3600|86400|1200|2700|900)\b|time_left\(\) < [0-9]|read\([0-9]{3,}\)' "$f" | grep -v '^[0-9]*:\s*#'; then
    bad numbers "$(basename "$f") holds timing literals (move them into life_common.py)"; num=1; fi
done
if $PY -c 'import sys; sys.path.insert(0, sys.argv[1] + "/bin"); import life_common as L; t = open(sys.argv[1] + "/checks/devcheck-gate.sh").read(); sys.exit(0 if f"sandboxed --timeout {L.GATE_DEVCHECK_TIMEOUT} " in t and f"sandboxed --timeout {L.GATE_TEST_TIMEOUT} " in t else 1)' "$KIT"; then :; else
  bad numbers "checks/devcheck-gate.sh timeouts differ from GATE_DEVCHECK_TIMEOUT/GATE_TEST_TIMEOUT"; num=1; fi
[ "$num" = 0 ] && pass numbers "no timing literal outside life_common.py; gate timeouts equal"

echo "== 13 generated tables =="
if $PY - "$KIT" <<'PYEOF'
import sys
kit = sys.argv[1]
sys.path.insert(0, kit + '/bin')
import life_common as L
text = open(kit + '/LIFE.md', encoding='utf-8').read().split('\n## Appendices', 1)[0]
bad = [name for name, table in (('section 13 numbers', L.limits_table()), ('section 14 notice kinds', L.notices_table()),
                                ('section 17 contract', L.contract_table())) if '\n' + table + '\n' not in text]
if bad:
    print('; '.join(bad))
sys.exit(1 if bad else 0)
PYEOF
then pass generated "sections 13, 14 and 17 equal the tables life_common generates"; else bad generated "regenerate LIFE.md tables"; fi

echo
if [ "$fail" = 0 ]; then echo "STATIC PASS"; else echo "SOME FAILED"; fi
exit "$fail"
