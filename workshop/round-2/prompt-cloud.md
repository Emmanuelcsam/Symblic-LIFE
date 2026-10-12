You critique LIFE, a Symblic script kit meant to turn a home cluster into a perpetually living self-improving system (cells = worker + reproducer agent pairs on lightweight local models; autogen lanes; reproduction admitted only by code). The kit is under /home/operator/host-checkout/docs/life (read LIFE.md fully, then the organs, policies, genome, checks, spawn protocol, db schema, README). Highest effort.

This is round 2. The kit was rewritten as v2 after round 1: db/schema.sql became db/life.sql and db/organism.sql; most organs/*.lines.txt, checks/heat-gate.sh, kill-switch.sh and verify-format.sh were removed; the controller is bin/life-tick.py with bin/life_common.py, bin/life-ctl.py, bin/life-status.py, bin/life-check.py, units/ and benchmarks/. workshop/round-1/decisions.md records what round 1 changed, superseded or rejected (with reasons); re-raise a rejected item only if you can show the reason is wrong. Open questions carried into round 2: admission tests with a fake API and a fake bin/symblic (GAP 8); recorded fixtures for the genome programs (GAP 9); whether 50 % CPU on 3 worker nodes is the right "fleet loaded" signal; whether the learning organ should generate its own questions from lessons; per-job resource limits on the worker nodes.

Your job: find EVERY detail that is not atomically defined (any threshold, file, schema, interval, model, engine, node, check, exit code, failure path, race, ordering, budget, unit or ownership that a lightweight model or a fresh agent could interpret in two ways), every contradiction with the platform facts in /home/operator/host-checkout/docs/life/BRIEF.md, every unsafe or unbounded behaviour (runaway spawning, resource exhaustion, heat, secrets, writes outside the workspace, live-code damage, restart loops), and every missing organ or path the operator's brief requires.

This is a review only: do not run anything, do not start agents or models, do not change files. Write your findings as the report.

Output numbered findings: severity (high/medium/low), location (file and section or line number), the exact ambiguity or defect, and the atomic definition or fix to adopt (write the replacement text where possible).

End with two integers on their own lines: FINDINGS_TOTAL=<n> and UNDEFINED_DETAILS=<n> (the count of findings that are undefined or ambiguous details), and a final line VERDICT=<CONVERGED|CHANGES NEEDED>.

The kit files are attached as sources; read every one.

Note: db/life.sql, db/organism.sql, units/life-tick.service and units/life-tick.timer cannot be attached (unsupported file types); each is embedded verbatim in LIFE.md, so review them there.
