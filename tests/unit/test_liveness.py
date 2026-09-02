"""Overnight price-job liveness."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fpl_agent.monitoring.liveness import evaluate_last_success_file, evaluate_price_liveness


def test_missing_file_is_stale(tmp_path: Path) -> None:
    result = evaluate_last_success_file(tmp_path / "missing.json", now=datetime(2026, 9, 2, 12, tzinfo=UTC))
    assert result.stale is True
    assert result.missing is True


def test_fresh_success_is_not_stale() -> None:
    now = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
    result = evaluate_price_liveness(
        {"utc": "2026-09-01T21:40Z", "gameweek": 3, "status": "NO ACTION"},
        now=now,
        max_age_hours=26,
    )
    assert result.stale is False
    assert result.age_hours is not None
    assert result.age_hours < 26


def test_old_success_is_stale() -> None:
    now = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
    result = evaluate_price_liveness({"utc": "2026-09-01T21:40Z"}, now=now, max_age_hours=26)
    assert result.stale is True
    assert "skipped" in result.message.lower() or "ago" in result.message.lower()
