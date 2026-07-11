# Demo video script (3:00 max)

Format: screen recording + voiceover. Record terminal at large font; pre-warm
all commands so nothing stalls on camera. Rehearse to 2:40 to leave buffer.

## 0:00–0:25 — The problem (slide or README on screen)

> "Cursor, Claude Code and Devin all run coding agents in parallel now. The
> moment two agents touch the same repo, you get database-style concurrency
> bugs. Three papers propose three fixes — CRDTs, git-hash optimism,
> LLM notifications — and each one is evaluated only by its own authors, on
> its own tasks. Nobody published the comparison table. We built it."

## 0:25–1:00 — Show a silent failure happen (terminal)

Run:

    python -m runner.run_grid --config runner/config.smoke.yaml

> "Here are two agents adding two config keys to the same file. Under naive
> parallelism — what you get by default — the run LOOKS fine: no error, no
> crash. But the oracle says 3 of 6 tests fail: one agent's feature silently
> vanished. That's a lost update. Same agents, same task under git-hash
> optimistic concurrency: six out of six. The harness caught the difference
> because every read and write flows through the coordination layer and lands
> in an event log."

Show the two `correct=` lines side by side; flash the JSONL event log briefly.

## 1:00–1:45 — The false-positive axis (the novel number)

Open `results/.../comparison_table.md` (or the notebook).

> "Coordination also fails in the opposite direction: stalling when it
> shouldn't. Task 2 is deliberately benign — two agents edit different
> functions in the same file. The right behavior is to do nothing. File
> locking stalls anyway — a false positive. Symbol-level claims, the trick
> tools like Grit and Weave use, don't stall at all. Nobody reports this
> false-positive stall rate; our harness measures it for every strategy, on
> every task, by diffing the symbols each write actually changed."

Point at the `fp_stalls_per_trial` column: file_lock 1.0, ast_scope 0.0.

## 1:45–2:25 — The real grid (results figures)

Show `analysis/figures/*.png` for the gpt-5-mini grid.

> "The full grid: six collision-seeded tasks — including a four-agent cascade
> and a cross-file interface change that every file-scoped mechanism is blind
> to — times four strategies, times five repetitions, with real models.
> Correctness, tokens, wasted work, and stalls per cell. [State the 2–3
> strongest numbers from the actual table here.]"

## 2:25–3:00 — Honesty + close (README on screen)

> "What this isn't: a new mechanism, or a general benchmark — six tasks are a
> probe suite, and our strategies are minimal reimplementations, so results
> characterize mechanism classes, not the original systems. What it is: the
> first neutral, replayable comparison — every number regenerates from the
> committed event logs with one command. The harness, tasks and logs are all
> in the repo. Next up: a CoAgent-style notify strategy and real CooperBench
> tasks."

## Recording checklist

- [ ] `pytest` green on camera-ready checkout
- [ ] smoke configs pre-run once (git init noise warms up)
- [ ] terminal ≥18pt font, dark theme, window sized for 1080p
- [ ] real-grid figures regenerated from final `results/grid-v1`
- [ ] fill the [bracketed] numbers from `comparison_table.md` before recording
