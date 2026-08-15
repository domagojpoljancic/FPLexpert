"""Offline pipeline integration."""

from __future__ import annotations

from fpl_agent.pipeline import run_pipeline


def test_offline_pipeline_runs() -> None:
    result = run_pipeline(mode="dry_run", offline=True)
    assert result["run_id"]
    assert result["executability"] in {"EXECUTABLE", "CONDITIONAL_ONLY", "INSUFFICIENT"}
    assert result["publish_state"] == "reconciled"
