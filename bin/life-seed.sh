#!/usr/bin/env bash
# LIFE seed (the operator runs this ONCE, on the host):  life-seed.sh [--branch NAME]   (NAME: default main)
# It asks for START, then runs life-ctl.py seed, which: checks the platform contract and that the live checkout has the
# branch NAME, runs VALIDATE.sh, creates /home/operator/.local/state/life (mode 0700) with the registry (schema 4), the
# organism database and release 1, creates the three agent workspaces under /home/operator/symblicos/projects
# (life-codebase-0-00000000 = a single-branch clone of branch NAME of host-checkout's committed history with
# .backups/ outside its sparse checkout; life-selfdev-0-00000000 and life-database-0-00000000 = symblic-task workspaces),
# and registers the 8 seed cells. NAME is the branch the codebase organ tracks for its whole life (life-ctl apply refuses
# a live checkout on another branch). It starts NO run and calls NO model: nothing happens until the operator installs the
# timer and runs life-ctl.py arm. A seed that stopped halfway is finished by running it again with the same NAME (every
# step is idempotent; a changed kit refuses); a finished seed is never changed and seeding is never a recovery step.
set -euo pipefail
KIT="/home/operator/host-checkout/docs/life"
echo "LIFE seed: creates /home/operator/.local/state/life and three workspaces; starts nothing."
read -r -p "Type START to continue: " answer
[ "$answer" = "START" ] || { echo "aborted"; exit 1; }
exec /usr/bin/python3 -I -B "$KIT/bin/life-ctl.py" seed --confirm START "$@"
