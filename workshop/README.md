# The LIFE workshop: five rounds of AI critique of a script that never ran

This folder is the review record of [LIFE](../README.md), a design for a self-running "cell organism" of small
local models on a private cluster. Nobody ran LIFE. What happened instead is recorded here: on 2026-10-11, over about
nine hours, an AI workflow sent the kit to three AI critics in each round (from round 2 on, ChatGPT got `LIFE.md`'s
specification of the two largest programs instead of their source), an AI "fold" agent applied what they found, a
static validator checked the result, and an AI judge decided whether another round was needed.

| Critic | What it was |
|---|---|
| ChatGPT (web) | the kit pasted into the ChatGPT web interface at its highest effort setting (`packet-chatgpt.md`) |
| Claude (cloud) | a Claude cloud task given the kit files as attachments (`prompt-cloud.md`) |
| Local | a local agent session on the same machine as the kit (`critique-local.md`) |

Four rounds were folded into the kit (LIFE v2.0 to v2.3). A fifth was started and stopped unfinished at the
operator's request, so `round-5/` holds only what was prepared for it. [WORKSHOP-RECORD.md](WORKSHOP-RECORD.md) has
the finding counts per critic and round and the fold agents' own summaries; [LOG.md](LOG.md) is the running log.

## Files

| Path | What it holds |
|---|---|
| `round-N/packet-chatgpt.md` | the brief and the kit's text as pasted into ChatGPT in round N (round 5's was only prepared); rounds 2-5 leave out `bin/life-tick.py` and `bin/life-ctl.py`, which `LIFE.md` specifies |
| `round-N/prompt-cloud.md` | the brief given to the Claude cloud critic |
| `round-N/critique-chatgpt.md`, `critique-cloud.md`, `critique-local.md` (rounds 1-4) | the three critiques as written, apart from the replacements described below |
| `round-N/decisions.md` (rounds 1-4) | every finding the fold agent did not apply as written (rejected, applied in part or in another form, already true), one line each with the reason; all other findings were applied (in round 1 some instead lapsed with the v1 mechanism they described) |
| `round-5/files.txt` | the files prepared as attachments for the round-5 cloud critic |
| `WORKSHOP-RECORD.md`, `LOG.md` | the summary and the running log |

The packets are plain text as pasted into a chat window, not Markdown; read them with GitHub's Raw view.

## What this folder holds beyond the critiques

- `round-N/part-K.txt`: the packet split into chat-sized pieces, most with a one-line header, each with a closing
  instruction ("Reply only with the word RECEIVED" on every part but the last, which asks for the critique). Apart
  from those lines and the blank lines around them, they are byte-for-byte pieces of `packet-chatgpt.md`. Rounds 1-4
  were sent this way; round 5's were prepared, and only part 1 had started sending.
- `round-N/sources/`: copies made for the cloud critic's upload: in round 1 the schema only (the other files were
  attached from the kit as it stood); none in round 2; in rounds 3-5 `LIFE.md`, `VALIDATE.sh` and the two schemas,
  with the test fixture strings replaced as each `prompt-cloud.md` says.
- `round-N/send-log.*`: the sender's log (when each part was sent and answered, retries, exit codes, the reply's size
  and its text or the start of it: RECEIVED for every part but the last). The link to the ChatGPT conversation was
  replaced with a placeholder.
- `round-5/`: what was prepared for the fifth round (packet, 26 parts, cloud prompt, file list, source copies). The
  send log shows part 1 had started sending when the round was stopped; no reply arrived (`.resp-1.txt` is empty;
  `.err-1.txt` holds the browser helper's start-up lines). There are critiques for rounds 1-4 only.
- `harness/life-script-workshop.js`: the orchestration script that drafted the kit, validated it and ran the five
  rounds. It is written for Claude Code's workflow runner, which supplies `agent`, `parallel`, `phase` and `log`. Even
  there it cannot run from this repository: every step drives tools that existed only on the original host
  (`bin/web-ai`, `bin/claude-cloud`, `bin/symblic-task`, `VALIDATE.sh`). It is kept as the record of what each agent was asked; the
  facts it inserted into the prompts at run time are not recorded.
- Twenty kit files missing from the export this repository was built from (the genome programs, `DECISIONS.md` and
  others) were restored byte for byte from `LIFE.md`'s appendices; nothing in this folder changed because of that.
- Names of people, machines, accounts, paths, services and research topics were replaced throughout, with the same
  rules as the kit itself (see the notes at the top of [../README.md](../README.md)). A few account-bound identifiers
  (a conversation id, a workflow run id, cloud review result paths and commit ids, a branch name), a private database
  path and one clock reading were also removed; inside a critique, square brackets mark each such removal. Line
  numbers quoted by the critics refer to the packets as they were sent, before that replacement, so some may be off
  by a line or two.

## How to read it

The critiques are long lists of numbered findings with severities. Their counts fell from round to round (ChatGPT's
high-severity findings went 157, 119, 87, 44), but a falling count from AI critics reading a 900 kB document in
parts is not evidence that the design is complete or correct. Every check here is static: the kit's code was
syntax-checked and its validator passed, but the coordinator never executed, not even against fakes, apart from one
probe of the sandbox wrapper with harmless commands in round 3.
