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
