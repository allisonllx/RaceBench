from pathlib import Path

from runner.run_grid import (
    collect_pending,
    load_config,
    resolve_openai_provider,
    should_rerun_existing_log,
)


ROOT = Path(__file__).resolve().parents[1]


def test_agnes_sensitivity_config_is_144_trials(tmp_path):
    cfg = load_config(str(ROOT / "runner" / "config.agnes-sensitivity.yaml"))
    pending = collect_pending(cfg, tmp_path, calibrate=False)

    assert cfg["run_id"] == "grid-v1-agnes-sensitivity"
    assert cfg["provider"] == "agnes"
    assert cfg["model"] == "agnes-2.0-flash"
    assert cfg["parallel"] == 1
    assert cfg["request_rpm"] == 15
    assert cfg["rerun_infra_errors"] is True
    assert cfg["budget"]["max_total_tokens"] == 12000000
    assert len(pending) == 144
    assert {job.strategy for job in pending} == {
        "naive",
        "file_lock",
        "git_hash",
        "ast_scope",
        "notify",
        "ast_dep",
    }
    assert {job.n for job in pending if job.task_name == "t04_cascade"} == {4}
    assert {job.n for job in pending if job.task_name == "t01_stale_clobber"} == {2}
    assert {job.n for job in pending if job.task_name == "rw_d_tag_antidependency"} == {2}
    assert {job.n for job in pending if job.task_name == "rw_e_cascade"} == {3}


def test_peer_targeted_config_includes_peer_strategies(tmp_path):
    cfg = load_config(str(ROOT / "runner" / "config.peer-targeted.yaml"))
    pending = collect_pending(cfg, tmp_path, calibrate=False)

    assert cfg["run_id"] == "grid-v1-peer-targeted-v5"
    assert cfg["provider"] == "openai"
    assert cfg["reps"] == 1
    assert cfg["parallel"] == 2
    assert cfg["budget"]["max_usd"] == 3
    assert {job.strategy for job in pending} == {
        "peer_contract",
        "peer_broker",
    }
    assert {
        "t02_benign_overlap",
        "t03_fetch_clobber",
        "t04_cascade",
        "rw_d_tag_antidependency",
        "rw_e_cascade",
    } <= {job.task_name for job in pending}
    assert {job.n for job in pending if job.task_name == "t04_cascade"} == {4}
    assert {job.n for job in pending if job.task_name == "rw_e_cascade"} == {3}


def test_adaptive_lease_targeted_config_runs_only_new_strategy(tmp_path):
    cfg = load_config(str(ROOT / "runner" / "config.adaptive-lease-targeted.yaml"))
    pending = collect_pending(cfg, tmp_path, calibrate=False)

    assert cfg["run_id"] == "grid-v1-adaptive-lease-targeted-v2"
    assert cfg["provider"] == "openai"
    assert cfg["reps"] == 1
    assert cfg["parallel"] == 2
    assert cfg["budget"]["max_usd"] == 2
    assert {job.strategy for job in pending} == {"adaptive_lease"}
    assert {
        "t01_stale_clobber",
        "t02_benign_overlap",
        "t03_fetch_clobber",
        "t04_cascade",
        "rw_d_tag_antidependency",
        "rw_e_cascade",
    } <= {job.task_name for job in pending}
    assert {job.n for job in pending if job.task_name == "t04_cascade"} == {4}
    assert {job.n for job in pending if job.task_name == "rw_e_cascade"} == {3}


def test_extensions_full_config_runs_new_strategies_on_full_task_set(tmp_path):
    cfg = load_config(str(ROOT / "runner" / "config.extensions-full.yaml"))
    pending = collect_pending(cfg, tmp_path, calibrate=False)

    assert cfg["run_id"] == "grid-v1-extensions-full"
    assert cfg["provider"] == "openai"
    assert cfg["reps"] == 5
    assert cfg["parallel"] == 2
    assert cfg["budget"]["max_usd"] == 18
    assert cfg["budget"]["max_total_tokens"] == 30000000
    assert len(pending) == 240
    assert {job.strategy for job in pending} == {
        "peer_contract",
        "peer_broker",
        "adaptive_lease",
    }
    assert {job.n for job in pending if job.task_name == "t04_cascade"} == {4}
    assert {job.n for job in pending if job.task_name == "rw_e_cascade"} == {3}
    assert {job.n for job in pending if job.task_name == "t01_stale_clobber"} == {2}


def test_toolarg_rerun_config_runs_only_exact_flagged_trials(tmp_path):
    cfg = load_config(str(ROOT / "runner" / "config.toolarg-rerun.yaml"))
    pending = collect_pending(cfg, tmp_path, calibrate=False)

    assert cfg["run_id"] == "grid-v1-toolarg-rerun"
    assert cfg["provider"] == "openai"
    assert len(pending) == 16
    assert {job.log_path.name for job in pending} == {
        "rw_b_signature_drift__ast_dep-n2-r4.jsonl",
        "rw_d_tag_antidependency__ast_scope-n2-r0.jsonl",
        "rw_d_tag_antidependency__naive-n2-r3.jsonl",
        "rw_d_tag_antidependency__notify-n2-r1.jsonl",
        "rw_e_cascade__peer_broker-n3-r2.jsonl",
        "t10_phantom_tool__adaptive_lease-n2-r0.jsonl",
        "t10_phantom_tool__adaptive_lease-n2-r1.jsonl",
        "t10_phantom_tool__ast_dep-n2-r0.jsonl",
        "t10_phantom_tool__ast_scope-n2-r0.jsonl",
        "t10_phantom_tool__ast_scope-n2-r4.jsonl",
        "t10_phantom_tool__naive-n2-r3.jsonl",
        "t10_phantom_tool__notify-n2-r2.jsonl",
        "t10_phantom_tool__notify-n2-r3.jsonl",
        "t10_phantom_tool__peer_broker-n2-r1.jsonl",
        "t10_phantom_tool__peer_broker-n2-r2.jsonl",
        "t10_phantom_tool__peer_contract-n2-r2.jsonl",
    }


def test_explicit_trial_config_rejects_invalid_agent_count(tmp_path):
    cfg = {
        "run_id": "bad",
        "mode": "openai",
        "model": "gpt-5-mini",
        "provider": "openai",
        "script_variant": "edit",
        "max_turns": 40,
        "lock_timeout_s": 30,
        "trial_timeout_s": 900,
        "trials": [
            {"task": "t04_cascade", "strategy": "naive", "n_agents": 2, "rep": 0}
        ],
    }

    try:
        collect_pending(cfg, tmp_path, calibrate=False)
    except ValueError as exc:
        assert "invalid n_agents=2" in str(exc)
    else:
        raise AssertionError("explicit trial config should reject invalid n_agents")


def test_resolve_agnes_provider_uses_dedicated_env(monkeypatch):
    monkeypatch.setenv("AGNES_API_KEY", "test-key")
    cfg = {
        "provider": "agnes",
        "api_key_env": "AGNES_API_KEY",
        "base_url": "https://apihub.agnes-ai.com/v1",
    }

    settings = resolve_openai_provider(cfg)

    assert settings["provider"] == "agnes"
    assert settings["api_key_env"] == "AGNES_API_KEY"
    assert settings["api_key"] == "test-key"
    assert settings["base_url"] == "https://apihub.agnes-ai.com/v1"


def test_infra_error_logs_only_rerun_when_enabled(tmp_path):
    log = tmp_path / "trial.jsonl"
    log.write_text(
        '{"event":"agent_error","error":"RateLimitError(\\"Error code: 429\\")"}\n'
        '{"event":"trial_end","correct":false}\n',
        encoding="utf-8",
    )

    assert should_rerun_existing_log(log, {"rerun_infra_errors": True})
    assert not should_rerun_existing_log(log, {"rerun_infra_errors": False})


def test_normal_completed_logs_are_not_rerun(tmp_path):
    log = tmp_path / "trial.jsonl"
    log.write_text(
        '{"event":"trial_end","correct":false,"agent_statuses":{"a":"done"}}\n',
        encoding="utf-8",
    )

    assert not should_rerun_existing_log(log, {"rerun_infra_errors": True})


def test_incomplete_logs_can_be_rerun(tmp_path):
    log = tmp_path / "trial.jsonl"
    log.write_text('{"event":"trial_start"}\n', encoding="utf-8")

    assert should_rerun_existing_log(log, {"rerun_incomplete_logs": True})
    assert not should_rerun_existing_log(log, {"rerun_incomplete_logs": False})


def test_agnes_tiny_config_is_one_trial(tmp_path):
    cfg = load_config(str(ROOT / "runner" / "config.agnes-tiny.yaml"))
    pending = collect_pending(cfg, tmp_path, calibrate=False)

    assert cfg["run_id"] == "grid-v1-agnes-tiny"
    assert cfg["provider"] == "agnes"
    assert cfg["request_timeout_s"] == 60
    assert cfg["rerun_incomplete_logs"] is True
    assert len(pending) == 1
