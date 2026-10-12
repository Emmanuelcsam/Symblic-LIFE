# LIFE division protocol (reproduction, admitted and executed by code)

A cell divides only through a **division transaction** in the registry (`divisions` table of
`/home/operator/.local/state/life/life.sqlite3`). There is no spawn-record file queue: no model,
agent or worker can write a birth request, and nothing a worker writes is ever read as one. The
coordinator `bin/life-tick.py` is the only writer of the registry; the reproducer (the cell's second
agent) only names foci and sorts items, through two genome programs with kernel checks.

## 1. Eligibility (code; checked by `Tick.division_start` every armed working tick)

A cell may start a division only when ALL hold:

| # | rule | value |
|---|------|-------|
| 1 | cell state | `active` |
| 2 | failures_in_a_row (terminal failed items in a row) | `0` |
| 3 | depth | `< 10` (life_common.MAX_DEPTH); a child is born at parent depth + 1, so at most 10 |
| 4 | backlog_ticks | `>= 3` consecutive armed WORKING ticks (any observe-only tick resets it to 0) with **workable** queued items `>= divide_backlog` (organs.json's value: command, learning and digest 12; codebase, immune, selfdev, compute and database 6). Not workable: selfdev items while SELFDEV_ARMED is off or aimed at a protected program; web- or model-derived agent items without a current operator approval; codebase agent items while CODEBASE_HISTORY_OK is missing; database agent items while the database organ holds; compute propose/rank items without a valid benchmarks.json |
| 5 | live cells of the organ (active, dividing, quarantined) | `+1 <= 3` (a division adds one net cell) |
| 6 | live cells of the organism | `+1 <= 16` (the parent retires in the same transaction) |
| 7 | births today (UTC) | `+2 <= 8` |
| 8 | open divisions fleet-wide (stage foci, assign or workspaces) | `0` (code checks; the unique index `divisions_one_open` enforces it) |
| 9 | last `divide_aborted` event of this cell | at least 21600 s ago |
| 10 | organ efficiency over the two complete UTC days before today | `(items_done + items_abstained) / (program_runs + 3 x agent_runs) >= 0.2` (program_runs include reproduction calls), or fewer than 20 cost units |
| 11 | a second node exists | a LIFE node other than the parent's, available this tick (online, not hot, not held, not resting, not past its daily duty, not benchmarking), with `< 4` live cells, and (agent organs) agy ready there, (model organs) the top rung of every program the organ runs installed there per a readable inventory |
| 12 | the tick may start work | governor `work`, no hold reason, admitted (ARMED for this boot, kit, platform files and DECISIONS.md unchanged, not FROZEN, STOP absent), before TICK_DEADLINE |
| 13 | the cell's workspace is not busy | no run in submitting/live/submit_unknown and no item queued or running at gate or apply (`life_common.WORKSPACE_STAGES`, `Tick.workspace_busy`) |

Order: the organ whose last committed division is oldest (never divided = oldest) goes first, then
the lowest `cell_id`; the first eligible cell starts. The division records the active release; the
parent's state becomes `dividing`; new items for its organ stop going to it (dispatch gives items only to
`active` cells), and it starts no agent run (its queued agent items wait for the children).

## 2. Stages

1. **foci** (the parent node's slot; at most every 2nd WORKING tick: `meta.working_tick_no` counts only admitted working
   ticks) — `genome/reproduce.sym` at the parent's
   reproduce rung plus the division's foci retries, with `organ`, `parent_focus` and `sample_items` = the labels
   of the first 12 snapshot items still queued (snapshot order = priority, then oldest `updated_at`, then item
   id), each cut to 120 characters, joined by ` | `, cut to 1600 characters. Code re-checks both foci: 8..120
   characters, different from each other AND from the parent after `norm_text`, no credential-shaped text. A
   `failed` answer retries ONCE at the next rung in a later slot (`foci_retries`), then the division aborts;
   `infra` retries at a later tick. Both reproducer programs tune the parent's rung window like any program.
2. **assign** (the parent node's slot; at most every 2nd working tick) — `genome/assign-item.sym` for at most the
   first 16 snapshot items still queued, at most 4 per slot (life_common.ASSIGN_PER_SLOT), each bounded to 225 s.
   A `failed` assignment is recorded at once as the parity side (below) and never asked again; an `infra` one is
   retried at a later tick.
3. **workspaces** (agent organs only; code, `lifecycle`, no model) — when nothing is left to assign, the stage
   becomes `workspaces`. Each armed working tick creates at most ONE missing child workspace (CLONE_TIMEOUT 600 s
   for the whole clone, in its own scope), admitted by `can_start(CLONE_TIMEOUT)`; a failed clone aborts the
   division and removes any child workspace it created that no cell owns. The child ids and paths follow from
   the lineage (section 3), so a crash between ticks leaves nothing ownerless: an abort removes them.
4. **commit** (code, `lifecycle`, no model; model organs commit straight after assign) — code re-checks rules 5-7
   and 12, that the parent is still `dividing`, picks child b's node again (rule 11), and, for agent organs,
   that both workspaces exist; any failure aborts, except missing workspaces (the workspaces stage continues) and a
   live run of the parent (a dividing cell starts none, so only a crash can leave one: the commit waits for it, the
   division staying open and counted). Every item still queued under the parent, except items at gate or apply,
   goes to child **a** or **b**:
   its recorded side if it has one, else `a` when `int(sha256(item_id), 16)` is even and `b` when odd. If either
   side is empty the division aborts. Then, in ONE registry transaction: both children are inserted, the items
   move, the parent becomes `retired` with `end_reason='divided'`, the day's `births` grows by 2, and
   `cell_events` records `born` twice and `divided` once. Items the parent is still running (a benchmark job) and
   items at gate or apply keep the parent's id; they are served in the parent's workspace, which is kept until
   they end; any other item re-queued later loses its cell and is dispatched again.

A division aborts when it has been counted in more than 27 ticks (DIVISION_MAX_TICKS = DIVISION_STEP_EVERY x (1 +
FOCI_RETRIES + ceil(ASSIGN_MAX / ASSIGN_PER_SLOT)) + 3 + 12: the slowest legal path plus 12 ticks of slack; a tick is
counted in `divisions.ticks` by `lifecycle` only when it is a working tick and the parent's node is available, so a
held or resting node never uses the division's ticks up), when the active release changes under it, or, checked at
every tick even while held, when it is older than 86400 s (DIVISION_MAX_SECONDS, the wall backstop).

## 3. Child identity

- `hex8 = sha256(parent_cell_id + "\n" + letter + "\n" + focus)[:8]`, `letter` = `a` or `b`.
- `cell_id = <organ>.<depth>.<hex8>` with `depth = parent depth + 1`, depth spelled without leading
  zeros (life_common.CELL_RX; the registry CHECK rebuilds the id from organ, depth and hex8, and a trigger
  requires the parent's organ and depth parent + 1).
- Child **a** stays on the parent's node; child **b** goes to the node rule 11 picks (fewest cells
  of this organ, then fewest cells, then the order node-a, node-b, node-d, node-f, node-i).
- A `cell_id` that already exists aborts the division (`lineage key ... already exists`): the same
  parent with the same focus is never born twice, however the text around it varies.
- Each child copies the parent's ladder rungs (`cell_programs`, with their rung_up_at) with an empty window.
- Agent children get their own workspace `/home/operator/symblicos/projects/life-<organ>-<depth>-<hex8>`
  (unique per cell: index `cells_one_workspace`). codebase: a single-branch clone of host-checkout's
  committed history with `.backups/` outside the sparse checkout; selfdev and database: a clone of the
  parent workspace's COMMITS (never its uncommitted files). A child whose workspace later goes missing
  gets it re-created by the lifecycle sweep.

## 4. Endings

| ending | trigger (code) | effect |
|--------|----------------|--------|
| apoptosis | empty and idle (nothing queued or running) for 86400 s (`idle_since`) AND another active cell of the organ exists AND its workspace is not busy | `retired`, `end_reason='idle'`; never the organ's last active cell |
| quarantine | `failures_in_a_row >= 8` (terminal failed items only) | `quarantined`; a notice. Queued items of a quarantined or retired cell (not at gate or apply) lose their cell at the next dispatch and wait unassigned while the organ has no active cell. `life-ctl.py release-cell` returns it. The organ's ONLY live cell is released automatically 86400 s after its quarantine, at the top model rung of every program, at most once per cell in any rolling 7 days (counted from its last automatic release; an operator release does not reset that): the one automatic restart the operator accepts at arm (DECISIONS.md line 8) |
| operator | `life-ctl.py retire CELL` | its open division aborts first; `retired`, `end_reason='owner'`; refused for the organ's last active cell or a cell with a live run without `--force` (which requests the run's cancel and abandons the run as `life-ctl.py abandon-run` does: its row ends `unknown` and collected, its item goes to the operator) |
| workspace | its workspace could not be re-created 3 times since it was last made or released | `retired`, `end_reason='workspace'`, its gate/apply items fail and its other queued items return to the organ; the organ's LAST live cell is quarantined instead (release-cell lets the sweep try again) |
| revive (a birth) | `life-ctl.py revive ORGAN NODE` for an organ with no live cell, the node below 4 live cells, the organism below 16 and the day's births below 8 | a new depth-0 cell with the seed focus; births + 1 |
| moved (not an ending) | its node was reported offline (online false in its own row of a readable status list; a node missing from the list is no evidence) in every sample of the last 21600 s, with at least 6 such samples, the registry holding samples of that node reaching back the whole 21600 s, and its workspace not busy | the cell moves to the node rule 11 picks (`moved` event and notice); `life-ctl.py move CELL NODE` does it by hand when that node is online in the latest sample and the cell is not dividing, has no running item and its workspace is not busy |

Retired and quarantined cells never divide. Cell and event rows are never deleted. A retired codebase
cell's clone is deleted once its workspace is not busy and it has no unfinished item
(`STATE/retired/<cell>.json` records its last commit); selfdev and database workspaces are kept.

## 5. Worked example

`example/division.json` walks one division of the seed learning cell through its stages with
the registry rows it produces.
