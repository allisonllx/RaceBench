# Tasks (Level B)

Twelve purpose-built mini-repos in `tasks/` (probe suite) plus a **FastAPI
Conduit external-validity track** (`rw_*`). Each has a collision map, hidden
pytest oracle, and reference solution.

For claim-level narrative (hardening, Conduit limits, ruled-out suite choices),
see [`writeup/writeup_1000.md`](../writeup/writeup_1000.md) (Task Suite appendix).

| Task | Failure mode | Agents | Notes |
|---|---|---|---|
| `t01_stale_clobber` | stale read / lost update (whole-file rewrite) | 2 | hardened; v1 in `tasks/_archive/` |
| `t02_benign_overlap` | disjoint functions, same file (FP probe) | 2 | `benign: true` |
| `t03_fetch_clobber` | write-write on the same function (whole-fetch rewrite) | 2 | hardened; v1 in `tasks/_archive/` |
| `t04_cascade` | causal cascade across a dependency chain | 4 | multi-module |
| `t05_cross_file` | cross-file symbol dependency | 2 | multi-module |
| `t06_feature_pair` | CooperBench-style feature pair | 2 | multi-module |
| `t07_rw_canary` | antidependency / silent invalidation | 2 | |
| `t08_livelock` | lock wait-cycle / livelock stress | 2 | opposite edit order |
| `t09_overhead` | overhead-masks-benefit (disjoint pkgs) | 2 | `benign: true` |
| `t10_phantom_tool` | tool-registry drift | 2 | needs `list_tools` |
| `t11_irreversible` | external-effect reordering | 2 | `.effects.jsonl` order |
| `t12_split_view` | worktree divergence | 2 | `isolation: worktree` |
| `rw_c_benign_overlap` | benign same-file on Conduit | 2 | FastAPI+SQLite+Pydantic |
| `rw_b_signature_drift` | stale-read / signature drift | 2 | Conduit `format_article` |
| `rw_d_tag_antidependency` | tag filter vs count silent invalidation | 2 | Conduit tags |
| `rw_e_cascade` | 3-agent causal cascade | 3 | Conduit Article.summary |

## Conduit track

The Conduit base lives in `tasks/_conduit_base/` (shared source). Host deps
include `fastapi`, `httpx`, and `pydantic`; reinstall with
`pip install -e ".[dev]"` after pull. Oracles use FastAPI `TestClient` (no
live server / Newman / Postgres).

## Agent tools

Agents get instrumented file tools (`read_file`, `write_file`, `edit_file`,
`list_files`, `run_tests`, `done`) plus `grep` / `glob`. Tasks with a
`registry:` block also expose `list_tools` / `invoke_tool` and irreversible
effect tools (`send_email`, `deploy`, `charge`). Workspace isolation is
`shared` (default) or `worktree` (per-agent trees merged before the oracle).
