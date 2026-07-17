from pathlib import Path

from runner.run_grid import (
    collect_pending,
    load_config,
    resolve_openai_provider,
    should_rerun_existing_log,
)


ROOT = Path(__file__).resolve().parents[1]


def test_agnes_sensitivity_config_is_72_trials(tmp_path):
    cfg = load_config(str(ROOT / "runner" / "config.agnes-sensitivity.yaml"))
    pending = collect_pending(cfg, tmp_path, calibrate=False)

    assert cfg["run_id"] == "grid-v1-agnes-sensitivity"
    assert cfg["provider"] == "agnes"
    assert cfg["model"] == "agnes-2.5-flash"
    assert cfg["parallel"] == 1
    assert cfg["request_rpm"] == 12
    assert cfg["rerun_infra_errors"] is True
    assert len(pending) == 72
    assert {job.strategy for job in pending} == {
        "naive",
        "file_lock",
        "notify",
        "ast_dep",
    }
    assert {job.n for job in pending if job.task_name == "t04_cascade"} == {4}
    assert {job.n for job in pending if job.task_name == "t01_stale_clobber"} == {2}


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
