# RaceBench Coordination Glossary

Canonical terminology for reasoning about concurrent coding agents in RaceBench.

## Terms

**Coordination granularity**:
The unit a strategy protects or compares, such as a file, top-level symbol, or dependency edge. Finer granularity can preserve more safe parallelism.
_Avoid_: Lock size

**False-positive stall**:
A coordination delay triggered even though the concurrent edits are provably disjoint and could safely proceed together.
_Avoid_: False conflict

**Advisory notification**:
A warning that shared state read by an agent may have changed; the agent judges whether its plan is invalid and whether to repair it.
_Avoid_: Conflict prevention

**Stale read**:
A decision made from an older version of shared state after another agent has changed that state.
_Avoid_: Old context

**Lost update**:
When one agent's write silently overwrites another agent's earlier write, so the earlier change disappears from the final state.
_Avoid_: Overwrite bug
