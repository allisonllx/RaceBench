# Adaptive Lease Strategy Plan

Goal: capture the main safety benefit of `file_lock` without paying its full
false-positive cost on benign same-file edits. The strategy should start
conservative, then shrink lock scope only when the runtime has evidence that a
narrower lease is safe.

This is a Level A strategy. It stays inside the RaceBench harness and is
comparable to `file_lock`, `ast_scope`, `ast_dep`, and the peer strategies.

## Motivation

- [x] `file_lock` has strong correctness on hard clobber and irreversible-style
      cases because it is conservative.
- [x] `file_lock` over-coordinates benign overlap, especially when two agents
      edit disjoint functions in the same file.
- [x] `ast_scope` gives useful granularity, but pure AST scope is syntax-first
      and can miss semantic dependencies.
- [x] `ast_dep` adds cross-file static dependency edges, but it is still limited
      by import/use inference and cannot represent application-level resources
      such as tag normalization or article summary semantics.

## V1: Adaptive AST/File Leases

Implemented as `adaptive_lease`.

- [x] Add a new registered strategy in `harness/strategies/adaptive_lease.py`.
- [x] Do not lock on read. Record read sets and last-read snapshots for
      observability and stale-write checks.
- [x] On write, compute touched symbols with the existing AST diff.
- [x] If the diff is precise top-level function/class scope, acquire symbol
      leases.
- [x] If the diff is module-level, whole-file, non-Python, parse-uncertain, or
      otherwise broad, acquire a file lease.
- [x] Make file leases conflict with every symbol lease in the same file.
- [x] Make symbol leases conflict only with the same symbol or a held file lease.
- [x] Hold leases until the owning agent finishes, matching the conservative
      lifetime of `file_lock` / `ast_scope`.
- [x] Refuse stale whole-file overwrites when the file changed after the agent's
      last read and the overwrite would risk dropping another agent's work.
- [x] Log `lease_acquired`, `blocked`, `read_write_intersection`, and
      `stale_overwrite_refused` events for report/replay diagnostics.
- [x] Add tests for registration, benign same-file no-stall behavior, broad
      file fallback, lease release, and stale overwrite refusal.

Expected behavior:

- `t02_benign_overlap`: should behave closer to `ast_scope` than `file_lock`.
- Whole-file or module edits: should behave closer to `file_lock`.
- Stale full-file clobbers: should refuse and force re-read rather than silently
  overwrite a peer's landed work.

## V2: Declared And Inferred Semantic Resource Leases

Implemented as the second `adaptive_lease` pass after V1 showed the expected
benefit on `t01` / `t02` / `t03`, but missed cross-file semantic dependencies
in `rw_d`, `rw_e`, and `t04`.

- [x] Add an optional `declare_scope` strategy tool.
- [x] Let agents declare:
      file paths, symbols, semantic resources, summary, exports, and
      must-preserve constraints.
- [x] Represent resources as stable strings, for example:
      `api.fetch.signature`, `api.fetch.retry_behavior`,
      `article.summary.schema`, `article.summary.feed_output`,
      `tag.normalization`, `tag.filter_semantics`.
- [x] Acquire semantic resource leases before risky writes when declarations
      overlap, even across files.
- [x] Infer a small conservative resource catalog from paths, changed symbols,
      and code text for known benchmark resources:
      `tag.normalization`, `article.summary`, `api.fetch.*`, and
      `datasource.parse_dataset.public_api`.
- [x] Log semantic read/write intersections and notify active readers to
      re-read affected files before editing.
- [ ] Verify writes post hoc against the declared file/symbol scope.
- [ ] Escalate to a file lease or refuse with a re-read/redeclare message when
      an agent touches undeclared broad scope.
- [x] Keep the fallback conservative: if the resource declaration is missing,
      vague, or unverifiable, use V1 file/symbol leases.

Expected benefit:

- Catch cross-file semantic dependencies that AST-only methods miss, such as
  tag normalization in `rw_d_tag_antidependency`.
- Avoid the token-heavy negotiation loops observed in `peer_broker` by making
  the conflict key explicit before the write.
- Preserve file-lock-like safety when semantic scope is uncertain.

Limit:

- V2 uses a seed resource catalog, not a general program-semantics engine. The
  current resource names are interpretable and testable, but still hand-authored.
  That is acceptable for an experimental strategy column as long as the writeup
  labels it as an adaptive lease prototype.

## V3: Obligation-Carrying Leases

Not implemented. This would borrow the useful part of `peer_contract` without
requiring a full private negotiation loop.

- [ ] Attach short obligations to leases, such as "preserve timeout parameter"
      or "feed output must include article.summary".
- [ ] Inject active obligations into the owning agent's future prompts until the
      agent calls `done`.
- [ ] Mark obligations as satisfied by tests, write verification, or explicit
      agent confirmation.
- [ ] Report obligation count, stale-obligation failures, and obligation token
      overhead in `analysis.make_report`.

## Evaluation Plan

- [x] Run unit tests for V1 mechanics.
- [x] Run unit tests for V2 resource mechanics.
- [x] Run offline scripted smoke with `adaptive_lease`.
- [x] Run a low-spend V1 targeted live run on:
      `t01`, `t02`, `t03`, `t04`, `rw_d`, `rw_e`.
- [x] Compare V1 against existing `file_lock`, `ast_scope`, `ast_dep`, and
      `git_hash` cells from `results/grid-v1`.
- [ ] Run the V2 targeted config:
      `results/grid-v1-adaptive-lease-targeted-v2`.
- [ ] Treat the strategy as promising only if it keeps hard-race correctness
      near `file_lock` while lowering false-positive stalls on benign overlap.
