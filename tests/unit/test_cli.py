"""CLI smoke tests."""

from __future__ import annotations

from typer.testing import CliRunner

from fpl_agent.cli import app

runner = CliRunner()


def test_validate_config_ok() -> None:
    result = runner.invoke(app, ["validate-config", "--path", "config/settings.example.yaml"])
    assert result.exit_code == 0
    assert "OK" in result.stdout


def test_doctor_redacts_secret(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-super-secret-value")
    result = runner.invoke(app, ["doctor", "--mode", "deadline"])
    assert result.exit_code == 0
    assert "sk-super-secret-value" not in result.stdout
    assert "sk-super-secret-value" not in result.stderr


def test_rules_diff() -> None:
    result = runner.invoke(
        app,
        ["rules", "diff", "--bootstrap", "tests/fixtures/bootstrap_static_reduced.json"],
    )
    assert result.exit_code == 0


def test_predeadline_skips_when_far_from_deadline() -> None:
    result = runner.invoke(app, ["predeadline", "--offline", "--no-save"])
    assert result.exit_code == 0
    assert "SKIPPED" in result.stdout or "keep" in result.stdout.lower() or "more than a day" in result.stdout.lower()


def test_materialize_from_env(tmp_path, monkeypatch) -> None:
    import base64
    import json
    from datetime import UTC, datetime

    dest = tmp_path / "current.json"
    payload = {
        "schema_version": "1.0.0",
        "season": "2026-27",
        "applies_before_gameweek": 1,
        "as_of": datetime.now(UTC).isoformat(),
        "player_ids": list(range(1, 16)),
        "bank_tenths": 15,
        "free_transfers": 1,
        "purchase_prices_tenths": {str(i): 50 for i in range(1, 16)},
        "chip_instances": [],
    }
    raw = json.dumps(payload)
    monkeypatch.setenv("FPL_PRIVATE_STATE_B64", base64.b64encode(raw.encode()).decode())
    result = runner.invoke(app, ["team-state", "materialize-from-env", "--dest", str(dest)])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert dest.exists()
    assert raw not in result.stdout
    assert raw not in result.stderr


def test_materialize_from_env_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("FPL_PRIVATE_STATE_B64", raising=False)
    dest = tmp_path / "current.json"
    result = runner.invoke(app, ["team-state", "materialize-from-env", "--dest", str(dest)])
    assert result.exit_code != 0
    assert "missing" in (result.stdout + result.stderr).lower()
    assert not dest.exists()


def test_prices_workflow_wired() -> None:
    from pathlib import Path

    text = Path(".github/workflows/fpl-prices.yml").read_text(encoding="utf-8")
    assert "fpl-agent prices" in text
    assert "FPL_PRIVATE_STATE_B64" in text
    assert "materialize-from-env" in text
    assert "cron:" in text
    assert "0 19 * * *" in text
    assert "*/2" not in text
    assert "run-log.md" in text
    assert "README.md" in text
    assert "reports/" in text
    assert "OPENAI_API_KEY" not in text
