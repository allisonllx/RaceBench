# Mission: Understand RaceBench Coordination Strategies

## Why
Understand how RaceBench's coordination strategies work well enough to explain the research accurately, critique its claims, and eventually propose better mechanisms.

## Success looks like
- Explain each strategy as a read/write protocol, including what it prevents and what it misses
- Predict how a strategy behaves on destructive and benign concurrent edits
- Interpret benchmark tradeoffs without reducing them to a single correctness ranking
- Propose improvements tied to a specific observed failure mode

## Constraints
- Introduce concurrency and program-analysis concepts as they become relevant
- Ground explanations in the repository implementation and primary sources
- Progress from the baseline mechanisms to the three post-grid extensions

## Out of scope
- Full distributed-systems theory unless a strategy needs it
- External-runtime comparisons until the Level A strategies are understood
