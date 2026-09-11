"""Tests for git-trackable slim weekly plan persistence."""

from __future__ import annotations

import json
from pathlib import Path

from fpl_agent.evaluation.plan_store import load_weekly_plan, plan_path, save_weekly_plan
from fpl_agent.evaluation.scorecard import load_latest_predeadline_plan


def test_save_and_load_weekly_plan(tmp_path: Path) -> None:
    plan = {
        "ok": True,
        "xi": [{"player_id": 1, "web_name": "Raya", "xp_next": 3.5}],
        "best_affordable": {"out_id": 2, "in_id": 3, "out_name": "A", "in_name": "B"},
        "also_considered": [],
        "noise": "dropped",
    }
    path = save_weekly_plan(3, plan, plans_dir=tmp_path)
    assert path == plan_path(3, tmp_path)
    loaded = load_weekly_plan(3, plans_dir=tmp_path)
    assert loaded is not None
    assert loaded["ok"] is True
    assert loaded["best_affordable"]["in_id"] == 3
    assert "noise" not in loaded


def test_save_skips_non_ok_plan(tmp_path: Path) -> None:
    assert save_weekly_plan(3, {"ok": False}, plans_dir=tmp_path) is None
    assert load_weekly_plan(3, plans_dir=tmp_path) is None


def test_load_latest_prefers_persisted_plan(tmp_path: Path, monkeypatch) -> None:
    plans = tmp_path / "plans"
    reports = tmp_path / "reports"
    reports.mkdir()
    save_weekly_plan(
        2,
        {
            "ok": True,
            "best_affordable": {"out_id": 1, "in_id": 9, "out_name": "Out", "in_name": "Persisted"},
            "xi": [],
        },
        plans_dir=plans,
    )
    (reports / "predeadline-gw2-20990101T000000Z.json").write_text(
        json.dumps(
            {
                "weekly_plan": {
                    "ok": True,
                    "best_affordable": {
                        "out_id": 1,
                        "in_id": 8,
                        "out_name": "Out",
                        "in_name": "Local",
                    },
                    "xi": [],
                }
            }
        ),
        encoding="utf-8",
    )
    import fpl_agent.evaluation.plan_store as store
    import fpl_agent.evaluation.scorecard as scorecard

    monkeypatch.setattr(store, "DEFAULT_PLANS_DIR", plans)
    # scorecard imports load_weekly_plan by name inside the function; patch DEFAULT on store module.
    loaded = scorecard.load_latest_predeadline_plan(reports, 2)
    assert loaded is not None
    assert loaded["best_affordable"]["in_name"] == "Persisted"
