"""Tests for applying prior-GW reflection outcomes to live projections."""

from __future__ import annotations

from pathlib import Path

from fpl_agent.config import ReflectionSettings
from fpl_agent.evaluation.learning import (
    apply_learning_to_projections,
    build_learning_application,
)
from fpl_agent.evaluation.plan_store import save_weekly_plan
from fpl_agent.projections.preseason import PlayerProjection


def _proj(pid: int, xp: float = 4.0) -> PlayerProjection:
    return PlayerProjection(
        player_id=pid,
        web_name=f"P{pid}",
        team_id=1,
        element_type=2,
        price_tenths=50,
        p_start=0.9,
        expected_minutes=80.0,
        points_per_90=4.0,
        xp_by_gw=(xp, xp, xp),
        weighted_xp=xp * 2.5,
    )


def test_prior_transfer_beaters_adjust_projections(tmp_path: Path) -> None:
    plans = tmp_path / "plans"
    save_weekly_plan(
        3,
        {
            "ok": True,
            "xi": [],
            "best_affordable": {
                "out_id": 10,
                "in_id": 115,
                "out_name": "Shaw",
                "in_name": "De Cuyper",
            },
            "also_considered": [],
        },
        plans_dir=plans,
    )
    reflection = {
        "gameweek": 3,
        "transfer_out_name": "Shaw",
        "transfer_in_name": "De Cuyper",
        "transfer_actual_delta": 0,
        "what_could_have_been_better": "Egan beat the pick.",
        "alternatives_reviewed": [
            {
                "in_name": "Egan",
                "in_id": 277,
                "predicted_delta": 4.6,
                "actual_delta": 6,
                "beat_the_pick": True,
            }
        ],
    }
    settings = ReflectionSettings(
        apply_backtested_lessons=False,
        apply_prior_transfer_outcomes=True,
    )
    learning = build_learning_application(
        gameweek=4,
        reflection=reflection,
        settings=settings,
        plans_dir=plans,
    )
    assert learning.applied is True
    assert learning.player_factors[277] > 1.0
    assert learning.player_factors[115] < 1.0

    catalog = {
        115: {"element_type": 2, "now_cost": 48},
        277: {"element_type": 2, "now_cost": 41},
        999: {"element_type": 2, "now_cost": 50},
    }
    projections = {115: _proj(115, 5.0), 277: _proj(277, 5.0), 999: _proj(999, 5.0)}
    adjusted = apply_learning_to_projections(projections, catalog, learning)
    assert adjusted[277].weighted_xp > projections[277].weighted_xp
    assert adjusted[115].weighted_xp < projections[115].weighted_xp
    assert adjusted[999].weighted_xp == projections[999].weighted_xp


def test_learning_disabled_via_settings(tmp_path: Path) -> None:
    settings = ReflectionSettings(
        apply_backtested_lessons=False,
        apply_prior_transfer_outcomes=False,
    )
    learning = build_learning_application(
        gameweek=4,
        reflection={
            "gameweek": 3,
            "alternatives_reviewed": [
                {"in_id": 1, "in_name": "X", "beat_the_pick": True, "actual_delta": 5}
            ],
            "transfer_actual_delta": -2,
        },
        settings=settings,
        plans_dir=tmp_path,
    )
    assert learning.applied is False
    assert learning.player_factors == {}
