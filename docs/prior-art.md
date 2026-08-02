# Prior art and attribution

RaceBench reimplements mechanism *classes* for neutral measurement. It does not
claim to invent these coordination ideas.

- CodeCRDT: arXiv:2510.18893 (CRDT coordination; motivates the confound metrics)
- CoAgent / MTPO: arXiv:2606.15376 (notification-based advisory control)
- MegaAgent: arXiv:2408.09955 (git-hash + mutex; basis of `git_hash`)
- Verified Detection of Concurrency Anomalies: arXiv:2606.17182 (failure-mode taxonomy)
- CooperBench: arXiv:2601.13295 (collaborative coding tasks; complementary axis:
  it varies communication, we vary the coordination mechanism)
- Contract Net Protocol: Smith, IEEE Transactions on Computers 1980,
  DOI: https://doi.org/10.1109/TC.1980.1675516
  (classic peer negotiation and task-allocation protocol; background for the
  peer-negotiation framing)
- POANCD: Li, Vo, and Kowalczyk, UAI 2011 / arXiv:1202.3740
  (distributed negotiation over combinatorial domains under incomplete
  information; inspiration for `peer_contract` / `peer_broker`, not directly
  implemented)
- Lock granularity: Gray, Lorie, Putzolu, and Traiger, VLDB 1975,
  https://www.vldb.org/dblp/db/conf/vldb/GrayLPT75.html
  (prior art for locks over resources at different granularities)
- Semantic multigranularity locking: Journal of Systems Architecture 1998,
  DOI: https://doi.org/10.1016/S1383-7621(97)00069-6
  (prior art for using application/object semantics to increase concurrency)
- Adaptive locks: Usui et al., Journal of Parallel and Distributed Computing
  2010, DOI: https://doi.org/10.1016/j.jpdc.2010.02.006
  (prior art for adapting locking behavior to recover concurrency)
- Specification Gap: arXiv:2603.24284, and the tools Grit, Phantom, Weave
  (prior art for AST-level conflict detection; `ast_scope` is our neutral
  reimplementation for measurement, not a novel mechanism)
