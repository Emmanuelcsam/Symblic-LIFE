# LIFE requirements decisions (the operator accepts these at arm)

`life-ctl.py arm --confirm ARM-UNTESTED --decisions HEX16` requires HEX16 = the first 16 hex of sha256 of THIS file,
and ARMED records the full sha256. Any change to this file disarms LIFE (integrity hold) until the operator reads it and
arms again with the new hash. Each line names an operator word from BRIEF.md and the exact bound the kit puts on it; the
bound is a number in `bin/life_common.py` (LIFE.md section 13) unless it says otherwise. Arming accepts every line;
it never claims that the unbounded words are met as written.

## Words of 10 Oct that later binding rules bound

1. "regenerate until complete or split": an item retries across ticks and days (infra re-queues up to 6, rung
   escalation up to 2 rungs, two timeouts at the top rung end at the operator, research re-runs until 3 dry runs or 9
   fetched sources, 2 needs_work rounds); a single attempt is bounded (agent run: 900 s per attempt, 2700 s per run,
   cancel requested at 3000 s; program run: 900 s, each model call 75 s; research run: 2100 s). "Split off what they
   cannot do" is switched off: LIFE agent runs never split (self_split false, depth 0); work a run cannot do ends at
   the operator, never silently away.
2. "no time cap while they try new things": no WORK has a wall cap; every ATTEMPT does (line 1). Divisions have a
   27-counted-tick cap and a 24 h wall backstop.
3. "the master coordinator may spawn as many agents as needed": at most 16 live cells (3 per organ, 4 per node), 8
   births per UTC day (a revive is a birth), 12 agent runs (each up to 4 agents) per UTC day, 2 agent runs at once.
4. "research lanes may run for days": a question is researched again at later ticks for as long as it finds new
   sources (any number of days); each run is 3 tool uses, 5 generations, 2100 s.
5. "a living breathing cluster": LIFE breathes in ticks (300 s after the previous tick ends) and rests (fleet: after
   3000 s of load until 600 s quiet; a node: 3000 s of LIFE work in any hour, then 1800 s idle; at most 6 h of LIFE
   work per node per UTC day). An agent run starts only on a node with no LIFE work in the whole previous hour and
   consumes that node's duty window while it runs (its other cells wait).

## Binding rules that win over the 10 Oct words

6. "keep continuous all-worker node load under about an hour before resting": implemented by line 5; a new action is admitted
   only while the fleet's loaded seconds plus its worst case stay within 3000 s; a high-power mode lease or its rest, cool
   mode, or any high-power mode phase other than off holds LIFE entirely.
7. "models propose, code decides": every acceptance (gates, checks, quote verification, division, quarantine,
   budgets, routing of prefixed commands) is code; a model accept never applies, adopts or makes a test-only patch
   ready.
8. "nothing restarts itself": LIFE never restarts the dashboard, never re-arms itself (a reboot, STOP, or any kit,
   platform-file or DECISIONS change disarms), never resubmits a run under a new id while the old one may exist. Two
   accepted exceptions: an organ's only cell, quarantined for 86400 s, is released automatically at its top rung at
   most once per 604800 s (auto_release); and work that STOP cancelled returns to its queue and starts again only
   after the operator arms again.
9. "the host only orchestrates": light models run only on node-a/b/d/f/i; the host runs code, sandboxed tests, gates,
   the checks of codebase runs, fetches, clones and the clients of slot programs, each in its own bounded scope;
   agent runs are placed on the cell's worker node.
10. "no credentials in shared documents": LIFE writes no credential; inbox and agenda text with a credential-shaped
    value is refused; fetched pages are stored with credential-shaped spans redacted; web text is data.

## Scope decisions for the operator's brief

11. "extremely light weight models": the five model organs use 0.5B to 4B local models; the three agent organs
    (codebase, selfdev, database) use one bounded `agy` run per item stage, on the agy model the operator writes in
    control/agy-model.txt (effort low; until that file exists agent organs wait), a cloud model of the operator's agy
    login, counted only by the agent-run budget (12 a day). No other cloud use exists.
12. "optimizes the codebase": the compute organ measures operator-written benchmark templates (warm-ups, ABBA pairs, exact
    fractions) and reports passed experiments with a ready-to-send command; turning a measured gain into a code change
    is the operator's (GAP 12).
13. "fixes errors": only failing tests the operator lists in control/watch.txt or names in a command (`fix: tests.x`,
    optionally `path.py:Class.function`), only three change classes (test_only, comment_or_doc, local_fix of function
    bodies the traceback or the command names), only through the gate and review, applied only by the operator.
14. "learns from the internet": through SearXNG and the platform's safe fetch only; web text is quoted as data,
    lessons and requests from it wait for the operator's approval before any agent run.
15. "develops itself": genome proposals change only ask instructions (not review-patch, which is protected), are
    gated, reviewed, and adopted only by the operator.
16. "creates databases": additive org_ schema migrations (operator-prefixed or approved requests) plus the store adapter,
    which copies quote-verified knowledge into org_ tables shaped for it; no model writes a row (GAP 13).
17. "figures out new ways to compute and store data": experiments over the operator's templates; adoption is the operator's.
18. "reproduces": cells divide only when code says so (workable backlog, health, efficiency, room, a second worker node); the
    reproducer model only names foci and sorts items.
19. "the codebase organ's history exposure": codebase agent runs wait until the operator creates
    control/CODEBASE_HISTORY_OK (GAP 11: the worker node checkout holds the tracked .backups/ files).
20. "untested": arming says ARM-UNTESTED until the admission tests of GAP 8 exist and pass; codebase gates also wait
    until `life-ctl.py gate-selftest` passed for this kit and these platform files.

## Known exposures the operator accepts at arm (each is a GAP with the platform change that would close it)

21. Candidate code (watched tests, codebase checks, the gate) runs with every TCP connect and bind denied, but it can
    send UDP (GAP 15: the launcher has no UDP rule).
22. Candidate code can change the mode, file owner or times of paths it cannot read (GAP 16: Landlock does not cover
    metadata); STOP and FREEZE then read as present (fail closed) and the STATE check holds LIFE.
23. Fetched pages are downloaded and parsed outside the Landlock sandbox (they need the network and the .venv), in
    their own scope with a 1 GiB memory and address-space limit and the platform's safe-fetch path.
24. Benchmark templates run on the worker node host under per-process limits, timeout and an output cap, not in a job-wide
    cgroup (GAP 7); only templates the operator wrote run.
25. The gate's focused test runs inside the candidate's own process: it is a regression check, not an adversarial
    oracle (GAP 19); the path rules, the local_fix rule, the model review and the operator's apply stand against a hostile
    patch.
26. Sandboxed code can write /dev/shm (GAP 17); LIFE removes every entry a run left, after the run.
27. Byte pins cover the platform files LIFE runs directly, not everything they import (GAP 18).
