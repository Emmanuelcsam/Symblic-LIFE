# LIFE: a never-run design for a self-running AI cluster (kit v2.3)

> **What it is.** LIFE is a design, not working software: a coordinator meant to run one private host and its small
> cluster of worker machines as a self-running system. Small local models (0.5B-4B) and a cloud coding agent (`agy`)
> take the operator's commands, research questions on the web, fix failing tests the operator lists, benchmark the
> operator's templates, add tables to their own database and propose changes to their own prompts. Plain code
> (`bin/life-tick.py`) admits, checks and records everything.
>
> **It has never run, and it cannot run here.** It calls the original host's own tools, services and paths, which are
> not in this repository, so `VALIDATE.sh` cannot pass in a clone; it would also report `.git/`, `LICENSE` and
> `.gitignore`, which were added for publication, as files `LIFE.md` does not embed. Only static checks were made: the
> Python and shell files parse, and the nine `genome/*.sym` programs pass `tools/symblic check` in the Symblic
> repository. The one exception is a probe of the kit's sandbox wrapper with harmless commands in workshop round 3.
>
> **Who wrote it.** AI coding agents wrote everything here, directed by one person on 2026-10-10 and 2026-10-11,
> except the request quoted in `BRIEF.md`, which is that person's own words.
>
> **Symblic.** The genome programs are written in Symblic, which is kept in its own repository. That repository's
> `docs/MAP.md` says where Symblic's own files went, and its `docs/MADE-WITH-AI.md` and `docs/HONEST-ASSESSMENT.md`
> apply here too.
>
> **Replaced for publication.** Names of people, machines, accounts, services, paths and research topics were
> replaced. "The operator" is the person who directed the work, "the host" is the main machine, `node-a` to `node-i`
> are the cluster's other machines and `node-arm` its small ARM manager board, `/home/operator/host-checkout` is the
> host's checkout of its private repository, and "the dashboard" is the host's web application. Paths written
> `docs/life/...` anywhere here mean this repository's root. Design facts were kept: each node's role and memory, the
> model ladder and the fleet rules. Twenty kit files missing from the export this repository was built from were
> restored byte for byte from `LIFE.md`'s appendices.
>
> The review record (packets, critiques, fold decisions, send logs and the harness script) is described in
> [workshop/README.md](workshop/README.md). License: MIT (`LICENSE`).

## The kit's own README (written for the original host)

This folder is a **script kit, not a running system**. Nothing here has been started, installed or
armed. The operator starts it, once, when they choose. Read this file, then `DECISIONS.md` (what the kit
bounds and why; arming accepts it), then `LIFE.md` (the master script: every rule, number, path and
file, with every file embedded verbatim).

LIFE is a cell organism on the cluster. Each **cell** is one subline of work with two agents: a
**worker** that does one exact task on a light local model (or, for three organs, a bounded `agy` run),
and a **reproducer** that, when code says the cell may divide, splits its work into two child cells
on two worker nodes. One code program, `bin/life-tick.py`, runs 300 s after the previous tick ends on the host:
it admits, schedules, checks and records everything. Models propose; code decides. The host only
orchestrates: it runs code, the gates, the watched tests, clones and page fetches, each in its own bounded scope,
and never a model. The three agent organs (codebase, selfdev, database) use the operator's cloud agy login on the model
named in `control/agy-model.txt`, at most 12 runs a day; everything else uses 0.5B-4B local models on the worker nodes.

What the brief's words mean here, exactly (DECISIONS.md is the full list): "optimises the codebase" = it measures
benchmark templates you write and reports passed experiments with a ready-to-send command; code changes come only
from failing tests. "Fixes errors" = it fixes only failing tests you list in `control/watch.txt` or name in a command
(`fix: tests.test_x`); it never reads the dashboard's logs. "Creates databases" = additive tables in its own
organism database; rows arrive only in tables shaped for its quote-verified knowledge. The top-level loop is the
Python coordinator `bin/life-tick.py`; the Symblic parts are the nine genome programs (`genome/*.sym`) and the three
two-line statement templates (`organs/*.lines.txt`): the Symblic program is the gcode, the tick is the printer's
firmware, and there is no separate runnable LIFE statement script.

## Start it (operator, on the host)

1. **Validate** (static: no model, no agent, no network):
   ```
   /home/operator/host-checkout/docs/life/VALIDATE.sh      # must end STATIC PASS
   ```
2. **Seed** (creates `/home/operator/.local/state/life`, release 1, three workspaces and the eight seed
   cells; starts nothing; a seed that stopped halfway is finished by running it again with the same branch).
   `--branch` names the branch the codebase organ tracks for its whole life (default `main`). To start over
   instead (a changed kit refuses to resume), remove `~/.local/state/life` AND the three folders
   `/home/operator/symblicos/projects/life-{codebase,selfdev,database}-0-00000000` by hand, then seed again:
   ```
   /home/operator/host-checkout/docs/life/bin/life-seed.sh --branch main   # type START
   ```
3. **Check readiness** (no model is called):
   ```
   B=/home/operator/host-checkout/docs/life/bin
   /home/operator/host-checkout/bin/symblic-task catalog --json   # "ready": {"agy": true} on node-i, node-a, node-b?
   /home/operator/host-checkout/bin/local-research --list         # the ladder models installed on each LIFE worker node?
   $B/life-ctl.py gate-selftest tests.test_symblic_autogen            # must print PASS (see below)
   ```
   `gate-selftest` takes any test that passes with `/usr/bin/python3 -s -B -m unittest ID` inside the clone (no .venv,
   no network); `tests.test_symblic_autogen` is only the default suggestion. It runs the sandbox probe (a sentinel file
   in STATE, STATE itself, `~/.ssh` and the live checkout unreadable, 127.0.0.1:8080 unreachable, unix sockets and
   signals to outside processes denied, each denial the policy's own PermissionError; a target missing outside the
   sandbox makes it INCONCLUSIVE), then the gate twice on an idle codebase clone: a harmless comment added to the
   test's module must PASS with devcheck checking at least one file, and a line that does not parse must FAIL at
   devcheck (exit 4). A PASS proves the codebase gate for this kit and these platform files: until then codebase
   gates and agent runs wait (notice `gate_unproven`); run it again after any kit or platform-pin change.
   If agy is not ready on a seed agent node, log agy in there (the worker node CLI login procedure) or the
   codebase, selfdev and database organs simply wait (notice `agy_not_ready`); that is expected, not a fault.
4. **Give it work and limits** (all optional; operator files under `~/.local/state/life/control/`, each a regular
   file you own; LIFE never writes them):
   - `watch.txt`: one unittest id per line (`tests.test_x`), at most 20. Each must pass
     `life-ctl.py gate-selftest ID` and finish in under 90 s of WALL time as LIFE runs it: `/usr/bin/python3 -s -B
     -m unittest ID` (the system Python, no .venv, no network, an empty HOME, inside the sandbox and a scope, start-up
     included). A test that needs the .venv or the network ends as `watch_error`, never a finding.
   - `benchmarks.json`: copy `benchmarks/benchmarks.example.json`, read every command, keep only what you
     approve (at most 20 entries, 64 KiB) — the compute organ measures only these.
   - `agy-model.txt`: one line, the exact agy model id the three agent organs may use (a model `agy models` lists;
     a light one keeps the weekly quota). Without it agent organs wait (notice `agy_model`); every run is `--effort low`.
   - `agenda.json`: recurring commands, `{"version": 1, "entries": [{"id": "materials-weekly", "text": "Research
     ...", "every_hours": 168}]}` (6..720 hours, at most 20 entries, ids unique, text 6..4000 bytes). An entry fires
     once in every period of every_hours counted from the Unix epoch, including the period in which it is added or
     edited (on the first armed working tick of that period); missed periods are skipped (notice `agenda_skipped`),
     never caught up.
   - Commands are routed by a small model unless they start with a prefix, which code routes without asking any
     model: `research:` (a question), `fix: tests.test_x [path.py:Class.function]` (a failing test, optionally the
     function to fix), `database:` (a schema request: `database: keep a reading list of papers with title, DOI and the
     question it answers`), `measure:` (an experiment over your benchmarks), `genome:` (a lesson naming one genome
     program); the single word `status` answers with a heartbeat. A database change ALWAYS needs its prefix.
   - `CODEBASE_HISTORY_OK` (an empty regular file you own; a symlink or directory grants nothing): read LIFE.md
     section 18 GAP 11 first. An agent checkout on a worker node is
     a full worktree of the tracked branch: the tracked `.backups/` files (a private database among
     them) are plain files in the agent's folder, and the whole history sits in the worker node's bare mirror.
     Without this file, codebase agent runs wait.
   - `NO_SELF_QUESTIONS` (empty file): stops learning from asking its own follow-up questions.
5. **Install the timer** (user units; the kit never installs them):
   ```
   cp /home/operator/host-checkout/docs/life/units/life-tick.{service,timer} ~/.config/systemd/user/
   systemctl --user daemon-reload
   systemctl --user enable --now life-tick.timer
   loginctl enable-linger operator          # once: user timers keep running after logout
   ```
   `arm` checks that the LOADED units are the kit's (ExecStart, MemoryMax, TasksMax, KillMode, timeouts, exit codes,
   the timer's 300 s) and refuses otherwise; after editing the kit's units, copy them again and daemon-reload.
   Disarmed, each tick only observes: it samples the cluster, takes inbox commands, runs canaries and writes status.
6. **Arm** (for this boot, this kit, these platform files and these decisions only; a reboot, a STOP or any change
   to them comes back disarmed). Read `DECISIONS.md`, then pass the first 16 hex of its sha256:
   ```
   sha256sum /home/operator/host-checkout/docs/life/DECISIONS.md | cut -c1-16
   $B/life-ctl.py arm --confirm ARM-UNTESTED --decisions <those 16 hex>   # runs VALIDATE.sh and the sandbox probe first
   $B/life-ctl.py selfdev-arm                    # optional: genome proposals
   ```
   The word ARM-UNTESTED says it: the admission tests (LIFE.md GAP 8) do not exist yet.

## Use it

```
$B/life-ctl.py command "Research how ceramic foam porosity is measured by gas adsorption"
$B/life-status.py                 # control, governor, budgets, cells, runs, notices, the tracked branch
$B/life-ctl.py notices            # what needs you; ack with: $B/life-ctl.py ack ID
$B/life-ctl.py report COMMAND_ID  # what a finished command produced (answers, sources, claims, patches)
$B/life-ctl.py show ITEM          # read web-derived work, then: $B/life-ctl.py approve ITEM --confirm APPROVE
$B/life-ctl.py apply PATCH --confirm APPLY      # a reviewed, gated patch into the live checkout (no commit)
                                                # then run bin/devcheck in the live checkout before you commit
$B/life-ctl.py revert PATCH --confirm REVERT    # only if nobody changed those files since
$B/life-ctl.py adopt PROPOSAL --confirm ADOPT   # a reviewed genome proposal becomes the next release
$B/life-ctl.py requeue ITEM --confirm REQUEUE   # an item that went to you (or a source that overflowed or came back
                                                # empty), back to work
$B/life-ctl.py abandon-run RUN_ID --confirm ABANDON   # a run the dashboard cannot confirm (notice run_unknown)
$B/life-ctl.py revive ORGAN NODE                # a new first cell for an organ that has none (one birth)
```

LIFE never applies a patch, adopts a genome change, restarts the dashboard, commits to
host-checkout, enables high-power mode or changes guest internet. Those stay with you. A test-only patch is
never made ready by the reviewer model: you read it and apply it with `--unreviewed`.

## KILL SWITCH

| what | command | effect |
|------|---------|--------|
| stop everything now | `$B/life-ctl.py stop` | writes `control/STOP` and removes `control/ARMED`; within 1 s a running tick sends SIGTERM to every LIFE process group and stops every `life-*.scope` (SIGKILL 30 s later; a killed `bin/symblic run` or research run cancels its fleet-runner run on the worker node first); life-ctl itself asks bin/symblic-task to cancel every LIFE autogen run (60 s each) and the job API to cancel every benchmark job (30 s each); nothing new starts. A cancel is a request: runs and jobs show as live until a tick sees them end. Then `unstop` removes STOP and `arm` is needed again; cancelled work returns to its queue and starts again only after you arm |
| pause new work | `$B/life-ctl.py freeze` / `thaw` | running work finishes and is collected; nothing new starts (fetches, gates, applies, findings and agent starts are new work and wait) |
| disarm | `$B/life-ctl.py disarm` | same as a reboot: observe only until `arm` |
| stop the timer and the running tick | `systemctl --user disable --now life-tick.timer && systemctl --user stop life-tick.service` | no further tick; the running tick (if any) gets SIGTERM from the stop, ends its process groups and scopes (SIGKILL 30 s later) and exits 4. Disabling the timer alone does NOT stop a running tick |
| one cell | `$B/life-ctl.py retire CELL` | the cell ends; its queue returns to its organ |

STOP lives outside every workspace (`~/.local/state/life/control/`), which no worker can read: model
calls have no tools, agents run on the worker nodes in their own checkouts, and agent-written code that runs on
The host (check 0, the gate, watched tests) runs only inside the Landlock sandbox, where STATE is not readable. If
anything makes `control/` impossible to inspect (a chmod: GAP 16), LIFE reads that as STOP (fail closed).

## Safety summary

- Light models run only on node-a/b/d/f/i through the fleet runner (`bin/symblic run --by ollama:M@node-X`, a call
  named for a node is never re-placed; `bin/life-research.py`); never on the host, the ARM node, node-c/e or node-h.
- Agent runs are `agy` only, on the model in `control/agy-model.txt` at effort low, strategies `fresh,feedback` (no
  engine or node rotation), at most 4 agents per run, at most 2 runs at once and 12 a day, at most 2700 s each
  (cancel requested at 3000 s), no internal splitting (`self_split false`, `depth 0`); a run starts only on a node
  with no LIFE work in the previous hour.
- The heat governor rests the fleet after 3000 s of fleet load (5-minute load per processor) until 600 s are
  observed quiet, admits an action only while the fleet's loaded seconds plus its worst case stay within 3000 s and
  the node's LIFE work in the last hour plus its worst case stays within 3000 s (then the node rests 1800 s; at most
  6 h of LIFE work per node per UTC day), holds while a high-power mode lease, its rest or any phase but off is on, holds
  while the host is short of memory or under memory or io pressure (checked again before every heavy local process),
  and gives hot worker nodes (85 °C, cool again below 75 °C) no new work.
- The sandbox denies every TCP connect and bind and every unix socket; it does not block UDP (GAP 15) and cannot stop
  a chmod of a path it cannot read (GAP 16: STOP and FREEZE then read as present and LIFE holds on its STATE check).
- No credential, `.env` value or private-store value is written by LIFE; inbox text with
  credential-shaped values is refused; web text is data (taint `web`), quoted to agents only after you
  approve it, never a statement or command by itself.
