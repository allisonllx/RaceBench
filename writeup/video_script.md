# RaceBench demo video script (3:00 max)

Format: a tightly edited product demo with voiceover, using terminal footage,
the static results explorer, and animated callouts. The five judging pillars are
the story structure, but should not be announced as a checklist.

**One-sentence message:** A multi-agent coding run can look successful while
silently losing work, and RaceBench makes that failure—and the cost of preventing
it—measurable.

**Audience:** hackathon judges who understand coding agents but may not know
database-style concurrency terminology.

**Target runtime:** rehearse to 2:45–2:50, leaving 10–15 seconds of submission
buffer. Keep the voiceover near 390 words.

## Narrative flow

| Time | Pillar | Visual purpose |
|---|---|---|
| 0:00–0:20 | Problem | Cold-open on a silent lost update; make the danger felt before naming the benchmark. |
| 0:20–0:42 | Problem | Establish why existing one-system evaluations cannot answer the comparison question. |
| 0:42–1:10 | Approach | Reveal RaceBench and show the controlled swap: same task, prompts, model, and oracle; only strategy changes. |
| 1:10–1:42 | Evidence | Show destructive overlap and the event replay that explains the failure. |
| 1:42–2:08 | Evidence | Flip to benign overlap and introduce false-positive stalls as the novel metric. |
| 2:08–2:31 | Evidence | Zoom out to the full 480-trial grid and the strategy trade-off. |
| 2:31–2:47 | Constraints | State the safety/throughput trade-off and the benchmark's realism boundary. |
| 2:47–3:00 | Honesty & Trajectory | Separate benchmark from invention and black-box product scoring; close on the next design question. |

## Shot-by-shot script

### 0:00–0:20 — Cold open: “success” that lost the feature

**Visual:** Black screen. Two agent cards appear side by side: `Agent A: done` and
`Agent B: done`. A green `RUN COMPLETE` stamp lands. It glitches into the oracle:
`3 / 6 tests passed`. Show a two-line diff where one config key disappears.

**Voiceover:**

> “Two coding agents finish. Both report success. There is no crash, no merge
> conflict, and no warning. But half the feature is gone. One agent silently
> overwrote the other. This is what failure looks like when parallel coding
> agents share a repository.”

### 0:20–0:42 — Why this needs a benchmark

**Visual:** Pull back from the lost line into three mechanism cards: optimistic
merge, file lock, notification. Each sits above a different task set; the cards
cannot be compared. Resolve into a blank comparison table.

**Voiceover:**

> “Parallel agents are already a product category. Proposed fixes include
> optimistic merges, locks, CRDTs, and agent notifications. But each is usually
> evaluated inside its own system, on its own tasks and metrics. Nobody had
> published the neutral comparison table.”

### 0:42–1:10 — Approach: reveal RaceBench

**Visual:** RaceBench title. Animate the controlled experiment as fixed blocks:
`task + briefs + model + oracle`; swap only the `coordination strategy` block.
Then flash one task folder, the hidden oracle, and a short JSONL event timeline.

**Voiceover:**

> “RaceBench is that table. It replays collision-seeded coding tasks while
> holding the repository, agent briefs, model, and hidden oracle fixed. Only the
> coordination policy changes. Every read, write, stall, token, and final test
> result becomes a replayable JSONL event. The suite covers 16 tasks and nine
> mechanism classes, from no coordination to locks, optimistic merge, symbol
> claims, notifications, peer negotiation, and adaptive leases.”

### 1:10–1:42 — Evidence I: catch the invisible clobber

**Visual:** Use the explorer or a prepared side-by-side result card for
`t01_stale_clobber` / `t03_fetch_clobber`. Highlight `naive: 0/5`, then
`file_lock: 5/5` and `git_hash: 5/5`. Open one failed replay and trace
`read → write → stale overwrite → oracle failure`.

**Voiceover:**

> “On destructive overlap, the failure is repeatable: naive parallelism passes
> zero of five runs. File locking and git-hash optimistic merge pass five of
> five. And this is not just a red cell in a chart. The replay shows the stale
> read, the competing writes, the exact overwrite, and the failing oracle.”

### 1:42–2:08 — Evidence II: safety can also be waste

**Visual:** Switch to `t02_benign_overlap`: two agents modify different functions
in the same file. Show all strategies at `5/5`, then reveal the second axis:
`file_lock: 1.0 false-positive stall/trial`; `naive + notify: 0`.

**Voiceover:**

> “But stopping races is only half the problem. Here, two agents edit different
> functions in the same file. Every strategy passes five of five, yet file
> locking stalls safe work once per trial. RaceBench measures that hidden tax as
> a false-positive stall. A system that stays correct by serializing everything
> has not solved parallelism.”

### 2:08–2:31 — Evidence III: the full trade-off

**Visual:** Open `results/grid-v1/report.html`. Show `480 trials`, `16 tasks`,
`6 baseline strategies`, `5 repetitions`, then the correctness chart. Pin the
two comparison cards: `file_lock: 90%, 174s` and `notify: 80%, 52s`.
Briefly flash the combined nine-strategy explorer as post-grid extensions.

**Voiceover:**

> “The headline grid contains 480 real-model trials. Solo agents pass 96.2
> percent, confirming the work itself is usually solvable. In parallel, the
> safest baseline, file locking, reaches 90 percent—but averages 174 seconds.
> Notifications reach 80 percent in 52 seconds. The right policy depends on the
> race; there is no universal winner.”

### 2:31–2:47 — Constraints: name the boundary

**Visual:** Keep the chart visible but dim it. Bring forward two compact labels:
`reproducible probes ≠ production realism` and `safety ↔ throughput`.

**Voiceover:**

> “That result has boundaries. These are fixed two-to-four-agent probes, plus a
> structured Conduit track—not long-horizon production development. And every
> safety gain must be read beside latency, tokens, wasted work, and unnecessary
> stalls.”

### 2:47–3:00 — Honesty, trajectory, and close

**Visual:** Three levels lock into place: `A — strategies`, `B — tasks/oracles`,
`C — external runtimes`. Highlight A/B; visually separate C. End on the
RaceBench wordmark and the question `What survived? At what cost?`.

**Voiceover:**

> “RaceBench is not a new coordination mechanism, and black-box products stay a
> separate external-runtime track. It is a neutral, extensible testbed. Next, it
> can test hybrids that coordinate only when risk is real. Do not ask only
> whether the agents finished. Ask what survived—and what coordination cost.”

## Five-pillar coverage check

| Criterion | What the judge hears or sees |
|---|---|
| Problem | A concrete silent lost update, why it matters now, and why prior results are not directly comparable. |
| Approach | Fixed tasks/prompts/model/oracle; pluggable coordination policy; event-level observability; 16-task, 9-class scope. |
| Evidence | 0/5 versus 5/5 destructive races; benign 5/5 with 1.0 false-positive stall; 480-trial aggregate; solo calibration. |
| Constraints | Safety-versus-throughput numbers, limited agent scale, reproducible probes rather than full production realism. |
| Honesty & Trajectory | Benchmark rather than invented mechanism; Level A/B separated from black-box Level C; hybrid next step. |

## Recording and asset checklist

- [ ] Capture a deterministic failed event replay instead of waiting for a live
  race during recording.
- [ ] Prepare clean side-by-side result cards for `naive`, `file_lock`, and
  `git_hash`; terminal text alone will be too dense at 1080p.
- [ ] Open `results/grid-v1/report.html` and
  `results/grid-v1-plus-extensions/report.html` before recording.
- [ ] Verify final headline values against the committed report immediately
  before export.
- [ ] Keep terminal text at least 18pt and never show a table wider than the
  highlighted columns.
- [ ] Use the existing figures in `assets/` as evidence plates, but animate
  crops and callouts rather than holding on full screenshots.
- [ ] Keep any music below narration and use sound design only for the false
  “success” stamp, the failed oracle reveal, and the final question.

## HyperFrames production note

This should route to the **general-video** workflow: it is a narrated custom
composition that mixes terminal capture, UI evidence, typography, and charts.
It is not a slideshow and the motion is not a standalone sub-10-second graphic.

When production starts, use a storyboard review. Build the cold open, the
controlled-experiment diagram, and the A/B/C boundary as authored HTML motion;
use real screenshots or short captures for the explorer and event replay. Avoid
recreating the whole results UI in animation—the authentic artifact is stronger
evidence.
