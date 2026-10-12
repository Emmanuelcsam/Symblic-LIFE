# LIFE: the operator's brief (verbatim intent, 2026-10-11)

"I talked about making perpetual 'life' and I want you to write up an extremely exhaustively extensively
meticulously detailed symblic script built to make that perpetually living system turning my cluster into a
self improving system that continuously takes commands, optimizes the codebase, fixes errors, learns from the
internet, develops itself based on things it learns, creates databases, figures out new ways to compute and
store data and LIVES (reproduces and learns efficiently). Make this symblic script that will bring my cluster to
life but don't run it. Workshop this symblic script with ChatGPT (web) at its highest effort and Claude cloud at
its highest effort until every minor detail in this symblic script is atomically defined, since the subagents
running the intricate script are expected to be extremely lightweight models to keep processing power low, but
each subline has two focuses, maybe two agents per subtask: one to perform an extremely specific task and the
other to reproduce, just like how cells come with different functions but they need to subdivide to keep the
whole system going."

Earlier operator words that bind this design (10 Oct): one agent per line by default; agents regenerate until their
task is complete or they split off what they cannot do; no time cap while they try new things; the master
coordinator may spawn as many agents as needed; research lanes must avoid duplicate sources and may run for days;
"a living breathing cluster"; the Symblic program is the gcode and an agent is the 3D printer; model/agent work
runs on the worker nodes, the host only orchestrates; keep continuous all-worker node load under about an hour before resting;
models propose, code decides; no credentials in shared documents; guest internet off; nothing restarts itself.

# What exists that the script must use (facts, verify in the code before relying on a detail)

- Statement scripts: `bin/symblic-task` lines (one statement per line, 20-1500 chars, at most 64 per task,
  verbs from `symblic_autogen.VERBS`, absolute folder named, "keeping every existing part" on edits, a verify
  line writing verify.txt). Autogen policy fields: candidates, regenerate, depth, children, generations,
  agents_max, attempt_seconds, wall_seconds, interval_seconds, feedback_chars, strategies, perpetual, checks,
  final, hidden, syntax, require_change, until_done, novelty_limit, self_split, designer, saturation
  (`symblic_autogen.LIMITS/DEFAULTS`). Perpetual lanes: one generation per interval, checkpoint
  AUTOGEN-CHECKPOINT.json {version, done, left, files, items}, HANDOFF.md, dedup index AUTOGEN-INDEX.jsonl keyed
  by DOI/URL/text; saturation stop. Until-done: no caps; stall split; self-split (AUTOGEN-SPLIT.txt); designer
  (AUTOGEN-TESTS.sh, sandboxed); stuck + resume (+extend). Contracts: docs/symblic/AUTOGEN.md, RECURSION.md.
- Engines for autogen attempts: CLI agents only (agy, claude, codex, mistral, copilot), placed on a node by the
  Agents hub; verification at home in a staging checkout; promotion = commit -> apply. Local Ollama models are
  reached through the formal language (`bin/symblic run F.sym --by ollama:qwen3:4b-instruct`), English
  statements, delegate templates, spec sheets, `bin/local-research` (SearXNG web research with local models) and
  the `local` task engine (cli-agent over Ollama; refuses long inputs).
- Cluster: the host (serves the site, orchestrates only), node-arm (ARM board, manager), node-a/b/d/f (~15.5 GB),
  node-h (~28 GB), node-i (~31 GB); CLI logins exist on the host; worker nodes run agents through the hub's registered
  launch path (no SSH shortcuts, no worker node tunnel to :8080). Capacity/heat: docs/fleet-power.md; high-power mode leases
  are bounded; rest after long load.
- Safety invariants (CLAUDE.md): private stores never in prompts/docs; no new SSH bypass; service worker/CSP rules;
  Python/API changes are restart-gated and warned; never restart slices or the busy browser daemon; tests isolate
  every store; code decides acceptance; `bin/devcheck` before commits; preserve others' work.
