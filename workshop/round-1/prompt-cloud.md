You critique LIFE, a Symblic script kit meant to turn a home cluster into a perpetually living self-improving system (cells = worker + reproducer agent pairs on lightweight local models; autogen lanes; reproduction admitted only by code). The kit is under docs/life (read LIFE.md fully, then the organs, policies, genome, checks, spawn protocol, db schema, README). Highest effort.

Your job: find EVERY detail that is not atomically defined (any threshold, file, schema, interval, model, engine, node, check, exit code, failure path, race, ordering, budget, unit or ownership that a lightweight model or a fresh agent could interpret in two ways), every contradiction with the platform facts in docs/life/BRIEF.md, every unsafe or unbounded behaviour (runaway spawning, resource exhaustion, heat, secrets, writes outside the workspace, live-code damage, restart loops), and every missing organ or path the operator's brief requires.

This is a review only: do not run anything, do not start agents or models, do not change files. Write your findings as the report.

Output numbered findings: severity (high/medium/low), location (file and section or line number), the exact ambiguity or defect, and the atomic definition or fix to adopt (write the replacement text where possible).

End with two integers on their own lines: FINDINGS_TOTAL=<n> and UNDEFINED_DETAILS=<n> (the count of findings that are undefined or ambiguous details), and a final line VERDICT=<CONVERGED|CHANGES NEEDED>.

The kit files are attached as sources; read every one.
Note: db/schema.sql is attached as docs/life/workshop/round-1/sources/schema.sql.txt (identical copy; the cloud source filter does not accept .sql).
