# LIFE workshop record

A Claude Code workflow run (ChatGPT web at its highest available effort, Claude cloud review at max effort, a local critic), 2026-10-11 01:38 to 10:14; four rounds folded, a fifth was started by the judge and stopped unfinished on the operator's instruction. Nothing in the kit was ever run: no tick, seed, model, agent or cluster job. Each round: three critics read the kit (from round 2 on, ChatGPT got `LIFE.md`'s specification of `bin/life-tick.py` and `bin/life-ctl.py` instead of their source), a fold agent applied the findings, `VALIDATE.sh` and a judge decided whether another round was needed.

| round | ChatGPT (findings / high) | Claude cloud (findings / high) | local (findings / high) | folded into |
|---|---|---|---|---|
| 1 | 206 / 157 | 89 / 28 | 54 / 30 | LIFE v2.0 |
| 2 | 224 / 119 | 70 / 5 | 56 / 12 | LIFE v2.1 |
| 3 | 145 / 87 | 58 / 4 | 50 / 7 | LIFE v2.2 |
| 4 | 106 / 44 | 70 / 3 | 40 / 5 | LIFE v2.3 |

## What each fold changed (the fold agents' own summaries, first lines)

### Round 1 -> LIFE v2.0

I folded all three round-1 critiques into the kit, which is now LIFE v2. `VALIDATE.sh` ends **STATIC PASS**. That means lint found zero errors and zero warnings, the policies normalize cleanly, all nine genome programs pass `bin/symblic check`, and `LIFE.md` matches every file it embeds. Nothing was run, started, armed, committed or restarted, and nothing outside `docs/life` was changed. The coordinator code has only been syntax-checked: it has never executed. …

### Round 2 -> LIFE v2.1

I've folded round 2 into the kit. It is now LIFE v2.1, and `VALIDATE.sh` ends STATIC PASS. All of it is written and statically checked only: no tick, seed, model, agent or cluster job was run, and the coordinator code has never executed against anything, not even fakes.  **Findings:** the three critiques held 350 findings: ChatGPT 224 (139 undefined details), Claude cloud 70 (42), local reviewer 56 (30). 239 were applied as written. The other 111 (C 16, G 83, Lo 12) are rejected or applied in part, with one line each and the reason in `workshop/round-2/decisions.md`. …

### Round 3 -> LIFE v2.2

Round 3 is folded into the kit, now LIFE v2.2. `VALIDATE.sh` ends STATIC PASS, ruff is clean on `bin/`, and `LIFE.md` matches every embedded file byte for byte. Nothing was started: no tick, seed, model, agent, research question or cluster job.  One exception to "only static checks": I ran the Landlock sandbox wrapper once in a scratch folder with harmless commands (`/bin/true`, `/bin/false`, `sleep`, the sandbox probe). No model, agent or cluster call is involved. That run caught a real bug before it shipped: `timeout` and `prlimit` need absolute paths inside the launcher. …

### Round 4 -> LIFE v2.3

Round 4 is folded into the kit, now LIFE v2.3. `VALIDATE.sh` ends STATIC PASS and `ruff check --select F,E9,B,PLE` passes on `bin/`, but nothing was run: no seed, arm, tick, model, agent or cluster job. So every behaviour change is checked statically only; the admission tests in GAP 8 don't exist yet.  **Counts.** 216 findings in total: 40 from the local reviewer, 70 from Claude cloud and 106 from ChatGPT. 159 were applied as written. The other 57 (local 9, cloud 9, ChatGPT 39) each have a one-line reason in `workshop/round-4/decisions.md`. …

## Where the reports are

- `docs/life/workshop/round-N/critique-{chatgpt,cloud,local}.md`: the full critiques; `packet-chatgpt.md`: what ChatGPT was sent, and `part-K.txt` the chat-sized pieces it was sent in; `decisions.md` and `LOG.md`: the fold decisions.
- `docs/life/LIFE.md`: the script itself, with every embedded file; `VALIDATE.sh`: the static checks (it ended STATIC PASS on the original host and cannot pass in a clone of this repository); `README.md`: how it is meant to be run, when the operator decides to run it; `DECISIONS.md`: the requirement decisions written down instead of built (also embedded in `LIFE.md`).

## Honest limits

- Every check is static. The organs, policies, genome and spawn protocol have never executed, not even against fakes, except one Landlock wrapper probe with `/bin/true`-class commands in round 3.
- The critics are language models reading a 900 kB document in parts; their counts fell each round (ChatGPT high findings 157, 119, 87, 44) but a falling count is not a proof of completeness.
- The lightest workers the script assumes (1B and 0.5B models) were measured shortly before the workshop with the model ladder of the Symblic repository's Kirby kit (`kits/kirby/`): they execute exact code reliably and cannot follow prose steps. Every cell the script hands to such a worker must therefore carry its code, and the reproducer cell must be a 3B or larger model or a human.
- Open operator decisions are listed in `DECISIONS.md` and at the end of `LIFE.md`.
