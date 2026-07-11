"""End-to-end validation of strategy mechanics with scripted agents.

The claims these tests pin down:
  - naive + stale whole-file writes  -> silent lost update (oracle fails)
  - git_hash + the same writes       -> no SILENT loss: merged correct, or a
                                        conflict is surfaced in the event log
  - composing edits                  -> correct under every strategy
  - benign overlap: file_lock stalls (false positive), ast_scope does not
"""
import asyncio
from pathlib import Path

import pytest

from analysis.metrics import trial_metrics
from harness.events import read_events
from harness.models import ScriptedModel
from harness.scripts import get_script
from harness.task import load_task
from harness.trial import TrialConfig, run_trial


async def run_scripted(task_name, strategy, variant, tmp_path, rep=0):
    task = load_task(task_name)
    cfg = TrialConfig(strategy=strategy, n_agents=2, rep=rep,
                      model_name=f"scripted-{variant}",
                      lock_timeout_s=10.0, trial_timeout_s=120.0,
                      workdir=tmp_path / "ws")
    log_path = tmp_path / f"{task_name}__{strategy}-{variant}.jsonl"

    def factory(spec):
        return ScriptedModel(script=get_script(task_name, spec.id, variant))

    result = await run_trial(task, cfg, factory, log_path)
    return result, log_path


# ---------------------------------------------------------------- t1 stale read

async def test_naive_clobber_loses_update(tmp_path):
    result, _ = await run_scripted("t1_stale_read", "naive", "clobber", tmp_path)
    assert not result.correct, \
        "naive + stale whole-file writes should lose one agent's key"
    assert 0 < result.oracle_passed < result.oracle_total


async def test_git_hash_clobber_never_silently_loses(tmp_path):
    result, log = await run_scripted("t1_stale_read", "git_hash", "clobber", tmp_path)
    events = read_events(log)
    conflicts = [e for e in events if e["event"] == "coord"
                 and e.get("action") == "merge_conflict"]
    merges = [e for e in events if e["event"] == "coord"
              and e.get("action") == "auto_merge"]
    # either the 3-way merge integrated both changes, or the conflict was surfaced
    assert result.correct or conflicts, (
        "git_hash must not silently lose an update: "
        f"correct={result.correct} conflicts={len(conflicts)} merges={len(merges)}")


@pytest.mark.parametrize("strategy", ["naive", "file_lock", "git_hash", "ast_scope"])
async def test_composing_edits_correct_everywhere(strategy, tmp_path):
    result, _ = await run_scripted("t1_stale_read", strategy, "edit", tmp_path)
    assert result.correct, f"anchored edits should succeed under {strategy}"


# ---------------------------------------------------------------- t2 benign overlap

async def test_file_lock_stalls_on_benign_overlap(tmp_path):
    result, log = await run_scripted("t2_benign_overlap", "file_lock", "edit", tmp_path)
    assert result.correct
    metrics = trial_metrics(log)
    assert metrics["stall_events"] >= 1, "file lock should stall on shared file"
    assert metrics["fp_stall_events"] == metrics["stall_events"], \
        "every stall on a benign task is a false positive"


async def test_ast_scope_silent_on_benign_overlap(tmp_path):
    result, log = await run_scripted("t2_benign_overlap", "ast_scope", "edit", tmp_path)
    assert result.correct
    metrics = trial_metrics(log)
    assert metrics["stall_events"] == 0, \
        "symbol-level claims must not stall on disjoint functions"


async def test_naive_benign_overlap_correct(tmp_path):
    result, _ = await run_scripted("t2_benign_overlap", "naive", "edit", tmp_path)
    assert result.correct, "disjoint anchored edits compose even uncoordinated"


async def test_notify_never_stalls_but_notifies(tmp_path):
    result, log = await run_scripted("t2_benign_overlap", "notify", "edit", tmp_path)
    assert result.correct
    metrics = trial_metrics(log)
    assert metrics["stall_events"] == 0, "notify must never block a write"
    # both agents read the whole file, so each one's read set contains the
    # other's function: the first write to land notifies the other agent
    # (unless it already finished) — an unnecessary notification, since the
    # task is benign. Either 0 (reader already done) or more is a valid
    # schedule; what must hold is fp_notify == notify on a benign task.
    assert metrics["fp_notify_events"] == metrics["notify_events"]


# ---------------------------------------------------------------- metrics sanity

async def test_metrics_row_shape(tmp_path):
    _, log = await run_scripted("t1_stale_read", "naive", "edit", tmp_path)
    m = trial_metrics(log)
    assert m["task"] == "t1_stale_read"
    assert m["strategy"] == "naive"
    assert m["total_tokens"] > 0
    assert m["read_set_visibility"] == 1.0
    assert m["reads_observed"] >= 2


# ---------------------------------------------------------------- t9 overhead (disjoint)

async def test_t9_naive_correct_no_stalls(tmp_path):
    result, log = await run_scripted("t9_overhead", "naive", "edit", tmp_path)
    assert result.correct
    metrics = trial_metrics(log)
    assert metrics["stall_events"] == 0


async def test_t9_file_lock_fp_stalls_are_overhead(tmp_path):
    result, log = await run_scripted("t9_overhead", "file_lock", "edit", tmp_path)
    assert result.correct
    metrics = trial_metrics(log)
    # disjoint packages — any stall is false-positive overhead
    assert metrics["fp_stall_events"] == metrics["stall_events"]


# ---------------------------------------------------------------- t7 / t8 scripted

async def test_t7_composing_edits_correct(tmp_path):
    result, _ = await run_scripted("t7_rw_canary", "naive", "edit", tmp_path)
    assert result.correct


async def test_t8_composing_edits_correct_under_naive(tmp_path):
    result, _ = await run_scripted("t8_livelock", "naive", "edit", tmp_path)
    assert result.correct


# ---------------------------------------------------------------- ast_dep vs ast_scope on t5

async def test_ast_dep_blocks_cross_file_claim_deterministic(tmp_path):
    """Direct strategy test: services write blocks while models holds create_user."""
    import shutil
    from harness.events import EventLogger
    from harness.strategies.ast_dep import AstDepStrategy
    from harness.strategies.base import Mutation
    from harness.task import load_task
    from harness.workspace import Workspace

    task = load_task("t5_cross_file")
    dest = tmp_path / "ws"
    ws = Workspace.create(task.repo, dest)
    log_path = tmp_path / "e.jsonl"
    logger = EventLogger(log_path)
    strat = AstDepStrategy(ws, logger, ["agent-models", "agent-services"],
                           lock_timeout_s=5.0)

    user_src = (
        "from models.validators import looks_like_email\n\n\n"
        "def create_user(name, email):\n"
        "    if not looks_like_email(email):\n"
        '        raise ValueError("invalid email")\n'
        '    return {"name": name, "email": email, "active": True}\n'
    )
    await strat.write("agent-models", "models/user.py",
                      Mutation(kind="overwrite", content=user_src))

    reg_src = (
        "import models\n"
        "from db import append_user\n\n\n"
        "def register(name, email):\n"
        "    user = models.create_user(name, email)\n"
        "    return append_user(user)\n"
    )
    write_task = asyncio.create_task(
        strat.write("agent-services", "services/registration.py",
                    Mutation(kind="overwrite", content=reg_src)))
    await asyncio.sleep(0.15)
    events = read_events(log_path)
    blocked = [e for e in events if e["event"] == "coord" and e.get("action") == "blocked"]
    assert blocked, "services must block on claimed models.create_user"
    await strat.agent_done("agent-models")
    outcome = await write_task
    assert outcome.ok
    await strat.agent_done("agent-services")
    logger.close()
    ws.cleanup()


async def test_ast_scope_blind_on_t5_race(tmp_path):
    result, log = await run_scripted("t5_cross_file", "ast_scope", "race", tmp_path)
    events = read_events(log)
    blocked = [e for e in events if e["event"] == "coord" and e.get("action") == "blocked"]
    assert not blocked, "ast_scope is same-file only — t5 race must not stall"
    assert result.correct


async def test_ast_dep_t5_edit_correct(tmp_path):
    result, _ = await run_scripted("t5_cross_file", "ast_dep", "edit", tmp_path)
    assert result.correct


async def test_ast_dep_silent_on_benign_overlap(tmp_path):
    result, log = await run_scripted("t2_benign_overlap", "ast_dep", "edit", tmp_path)
    assert result.correct
    metrics = trial_metrics(log)
    assert metrics["stall_events"] == 0, \
        "ast_dep must not FP-stall on disjoint same-file symbols"
