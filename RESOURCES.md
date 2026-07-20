# RaceBench Coordination Resources

## Knowledge

- [RaceBench strategy interface](harness/strategies/base.py)
  Primary implementation source for the read/write protocol shared by every Level A strategy.
- [RaceBench baseline strategy implementations](harness/strategies/)
  Primary implementation source for the exact behavior of `naive`, `file_lock`, `git_hash`, `ast_scope`, `ast_dep`, and `notify`.
- [RaceBench submission write-up](writeup/writeup_1000.md)
  Primary project source for the research question, experimental framing, headline results, and limitations.
- [Python `asyncio` synchronization primitives](https://docs.python.org/3/library/asyncio-sync.html)
  Official reference for mutex locks and conditions; use for understanding blocking strategies.
- [Git `merge-file`](https://git-scm.com/docs/git-merge-file)
  Official reference for the three-way file merge used by `git_hash`.
- [Python `ast`](https://docs.python.org/3/library/ast.html)
  Official reference for the syntax-tree representation used by `ast_scope` and `ast_dep`.
- [MegaAgent paper](https://arxiv.org/abs/2408.09955)
  Primary research source for the git-hash concurrency mechanism that inspired RaceBench's minimal `git_hash` reimplementation.
- [CoAgent paper](https://arxiv.org/abs/2606.15376)
  Primary research source for advisory concurrency control; RaceBench's `notify` isolates only its notify-and-self-repair idea.
- [Verified Detection and Prevention of Concurrency Anomalies](https://arxiv.org/abs/2606.17182)
  Primary research source for several failure modes represented in the benchmark task suite.

## Wisdom (Communities)

- RaceBench repository discussions and review feedback
  Use for testing whether an explanation or proposed strategy matches the implementation and research claims.

## Gaps

- Add primary sources for peer negotiation and semantic leases before beginning the post-grid extension lessons.
