# Demo video script (3:00 max)

Format: screen recording + voiceover. Record terminal at large font; pre-warm
all commands so nothing stalls on camera. Rehearse to 2:40 to leave buffer.

## 0:00-0:25: The problem (slide or README on screen)

> "Cursor, Claude Code and Devin all run coding agents in parallel now. The
> moment two agents touch the same repo, you get database-style concurrency
> bugs. Three papers propose three fixes: CRDTs, git-hash optimism, and
> LLM notifications. Each one is evaluated only by its own authors, on
> its own tasks. Nobody published the comparison table. We built it."

## 0:25-1:00: Show a silent failure happen (terminal)

Run:

    python -m runner.run_grid --config runner/configs/config.smoke.yaml

> "Here are two agents adding two config keys to the same file. Under naive
> parallelism, what you get by default, the run LOOKS fine: no error, no
> crash. But the oracle says 3 of 6 tests fail: one agent's feature silently
> vanished. That's a lost update. Same agents, same task under git-hash
> optimistic concurrency: six out of six. The harness caught the difference
> because every read and write flows through the coordination layer and lands
> in an event log."

Show the two `correct=` lines side by side; flash the JSONL event log briefly.

## 1:00-1:45: The false-positive axis (the novel number)

Open `results/.../comparison_table.md` (or the notebook).

> "Coordination also fails in the opposite direction: stalling when it
> shouldn't. Task 2 is deliberately benign: two agents edit different
> functions in the same file. The right behavior is to do nothing. File
> locking stalls anyway, a false positive. Symbol-level claims, the trick
> tools like Grit and Weave use, don't stall at all. Nobody reports this
> false-positive stall rate; our harness measures it for every strategy, on
> every task, by diffing the symbols each write actually changed."

Point at the `fp_stalls_per_trial` column: file_lock 1.0, ast_scope 0.0.

## 1:45-2:25: The real grid (static explorer)

Open `results/grid-v1/report.html`.

> "The full grid is 16 tasks, 6 strategies, and 5 repetitions with gpt-5-mini:
> 480 trials from committed JSONL logs. It includes hardened clobbers, benign
> overlap, cross-file races, irreversible effects, split-view worktrees, and a
> Conduit app track. The explorer lets judges filter by task, strategy, and
> failure mode, then click through to the raw logs."

Point at one headline result: `file_lock` fixes t01/t03 but creates
false-positive stalls on benign tasks. Then point at `notify` and `naive` as
evidence that the right answer is selective, not "always coordinate more."

## 2:25-3:00: Honesty + close (README on screen)

> "What this isn't: a new coordination mechanism or a claim that external
> products are strategy columns. Level A compares mechanisms under our
> instrumented loop. Level C is black-box runtime scoring unless a product
> exposes mediation hooks. What it is: a neutral, replayable benchmark artifact.
> Every number regenerates from committed event logs, and the repo includes the
> harness, tasks, static explorer, validation command, and limits."

## Recording checklist

- [ ] `pytest` green on camera-ready checkout
- [ ] smoke configs pre-run once (git init noise warms up)
- [ ] terminal >=18pt font, dark theme, window sized for 1080p
- [ ] real-grid figures regenerated from final `results/grid-v1`
- [ ] open `results/grid-v1/report.html` before recording
