#!/usr/bin/env bash
# LIFE codebase gate. bin/life-tick.py runs this on the host (timeout GATE_TIMEOUT 900 s, its own process group, a
# life-gate-*.scope in work.slice) after a codebase run promoted its change into the cell's clone and the tick staged
# it (git add -A); life-ctl.py gate-selftest runs it too.
#   devcheck-gate.sh CHECKOUT TEST_ID BASE
# CHECKOUT must be a LIFE codebase clone (/home/operator/symblicos/projects/life-codebase-<depth>-<8hex>), never the
# live checkout. TEST_ID is tests.<module>[.<Class>[.<test>]]. BASE is the 40-hex commit the run started from.
# Steps, all in CHECKOUT; steps 2 and 3 run candidate code, so they run ONLY inside the Landlock sandbox
# (life-check.py sandboxed: its own scope, an empty temporary HOME, no STATE, no ~/.ssh, no live checkout, no TCP):
#   1. the test module resolves, WITHOUT importing anything, to a regular file inside CHECKOUT (the longest dotted
#      prefix that names <path>.py or <path>/__init__.py; no symlink anywhere; the scratch-copy trap)       else exit 3
#   2. ./bin/devcheck --changed BASE --no-tests (GATE_DEVCHECK_TIMEOUT 600 s): compile, ruff F, project rules, the
#      secret scan and page checks (node lives under ~/.nvm, unreadable in the sandbox: inline scripts are then only a
#      devcheck note); NO test run here: bin/devtest needs uv, a HOME package cache and PyPI, none of which exist in
#      the sandbox, so the focused test is step 3 under /usr/bin/python3. Exit 0 AND its line "devcheck: ...: N
#      file(s)" with N >= 1 (a judge that checked nothing never passes); bin/, scripts/, rules/ and the judge's
#      configuration files are on the gate deny list, so this judge is the base commit's own bytes  else exit 4
#   3. /usr/bin/python3 -s -B -m unittest TEST_ID -v (GATE_TEST_TIMEOUT 240 s): exit 0 AND "Ran N tests" with N >= 1,
#      an OK line, and fewer skipped tests than tests run                                                  else exit 5
# Exit 0 only when all three pass; 2 = bad arguments; 125 = the sandbox is unavailable (from step 2 or 3). Calls no
# model and no agent. Never restarts, commits or pushes. Step 3 is a regression check, not an adversarial oracle: the
# candidate code runs inside the test process (GAP 19); the path rules, the local_fix rule, the review and the operator's
# apply are what stand against a hostile patch.
set -uo pipefail
KIT="/home/operator/host-checkout/docs/life"
checkout="${1:-}"
test_id="${2:-}"
base="${3:-}"
[[ "$checkout" =~ ^/home/operator/symblicos/projects/life-codebase-(0|[1-9]|10)-[0-9a-f]{8}$ ]] || { echo "devcheck-gate: not a LIFE codebase clone: $checkout" >&2; exit 2; }
[[ "$test_id" =~ ^tests\.[A-Za-z0-9_]{1,64}(\.[A-Za-z0-9_]{1,64}){0,4}$ ]] && [ "${#test_id}" -le 160 ] || { echo "devcheck-gate: bad test id: $test_id" >&2; exit 2; }
[[ "$base" =~ ^[0-9a-f]{40}$ ]] || { echo "devcheck-gate: bad base commit: $base" >&2; exit 2; }
[ -d "$checkout/.git" ] && [ ! -L "$checkout" ] || { echo "devcheck-gate: $checkout is not a git checkout" >&2; exit 2; }
cd "$checkout" || exit 2
/usr/bin/python3 -I -B - "$checkout" "$test_id" <<'PY' || exit 3
import os, sys
root, parts = os.path.realpath(sys.argv[1]), sys.argv[2].split('.')
for n in range(len(parts), 0, -1):
    for rel in ('/'.join(parts[:n]) + '.py', '/'.join(parts[:n]) + '/__init__.py'):
        path = os.path.join(root, rel)
        walk = [os.path.join(root, *rel.split('/')[:k]) for k in range(1, len(rel.split('/')) + 1)]
        if os.path.isfile(path) and not any(os.path.islink(p) for p in walk) and os.path.realpath(path).startswith(root + os.sep):
            print(f'devcheck-gate: {".".join(parts[:n])} -> {rel}')
            sys.exit(0)
print(f'devcheck-gate: {sys.argv[2]} does not resolve to a file inside the clone', file=sys.stderr)
sys.exit(1)
PY
out="$(/usr/bin/python3 -B "$KIT/bin/life-check.py" sandboxed --timeout 600 ./bin/devcheck --changed "$base" --no-tests 2>&1)"
rc=$?
printf '%s\n' "$out"
[ "$rc" = 125 ] && exit 125
[ "$rc" = 0 ] || exit 4
printf '%s\n' "$out" | grep -Eq '^devcheck: .*: [1-9][0-9]* file\(s\)' || { echo "devcheck-gate: devcheck checked no file" >&2; exit 4; }
out="$(/usr/bin/python3 -B "$KIT/bin/life-check.py" sandboxed --timeout 240 /usr/bin/python3 -s -B -m unittest "$test_id" -v 2>&1)"
rc=$?
printf '%s\n' "$out"
[ "$rc" = 125 ] && exit 125
[ "$rc" = 0 ] || exit 5
ran="$(printf '%s\n' "$out" | sed -n 's/^Ran \([0-9][0-9]*\) tests\{0,1\} in .*/\1/p' | tail -1)"
skipped="$(printf '%s\n' "$out" | sed -n 's/.*skipped=\([0-9][0-9]*\).*/\1/p' | tail -1)"
[ -n "$ran" ] && [ "$ran" -ge 1 ] && printf '%s\n' "$out" | grep -Eq '^OK( |$)' && [ "${skipped:-0}" -lt "$ran" ] || { echo "devcheck-gate: the focused test ran no test or skipped every test" >&2; exit 5; }
echo "devcheck-gate: PASS $test_id in $checkout"
