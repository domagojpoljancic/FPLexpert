"""Backtest harness and CLI tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fpl_agent.cli import app
from fpl_agent.projections.backtest import run_backtest, run_backtest_report
from fpl_agent.projections.dataset import load_dataset, validate_row

FIXTURE = Path("tests/fixtures/backtest/holdout_min.json")
runner = CliRunner()


def _rows() -> list[dict]:
    return load_dataset(FIXTURE)["rows"]


def test_backtest_rejects_unknown_or_future_feature() -> None:
    base = dict(_rows()[0])
    with pytest.raises(ValueError, match="future leakage"):
        validate_row({**base, "future_leak": 1})
    with pytest.raises(ValueError, match="non-allowlisted"):
        validate_row({**base, "post_deadline_points": 9})


def test_backtest_cli_offline(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    result = runner.invoke(
        app,
        [
            "backtest",
            "--rows",
            str(FIXTURE),
            "--model",
            "xp-v2",
            "--reports",
            str(reports),
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "MAE=" in result.stdout
    assert "ep_next" in result.stdout
    assert "DEF" in result.stdout or "MID" in result.stdout
    json_files = list(reports.glob("backtest-*.json"))
    assert json_files, "expected reports/backtest-*.json"
    payload = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert payload["model"]["n"] == 4
    assert payload["ep_next_baseline"]["n"] == 4


def test_backtest_xp_v2_selectable() -> None:
    rows = _rows()
    xp = run_backtest(rows, model="xp-v2")
    baseline = run_backtest(rows, model="baseline-v1")
    assert xp.model_version.startswith("xp-v2")
    assert baseline.model_version == "baseline-v1"
    assert xp.mae != baseline.mae or xp.bias != baseline.bias


def test_backtest_rules_mismatch_labeled() -> None:
    dataset_2025 = {
        "season": "2025-26",
        "rules_version": "2025-26",
        "rows": _rows(),
    }
    report = run_backtest_report(
        dataset_2025["rows"],
        model="xp-v2",
        dataset_season=dataset_2025["season"],
    )
    assert report.rules_mismatch is True

    report_ok = run_backtest_report(
        _rows(),
        model="xp-v2",
        season="2026-27",
        dataset_season="2026-27",
    )
    assert report_ok.rules_mismatch is False
