"""In-season minutes and xG adjustment tests."""

from __future__ import annotations

from fpl_agent.projections.preseason import (
    apply_xg_adjustment,
    finished_gameweeks,
    start_probability,
)


def test_finished_gameweeks_counts_only_finished() -> None:
    bootstrap = {
        "events": [
            {"id": 1, "finished": True},
            {"id": 2, "finished": True},
            {"id": 3, "finished": False, "is_next": True},
        ]
    }
    assert finished_gameweeks(bootstrap) == 2


def test_in_season_nailed_gk_is_not_backup() -> None:
    element = {
        "starts": 2,
        "minutes": 180,
        "now_cost": 60,
        "element_type": 1,
    }
    p_pre, _ = start_probability(element, games_played=0)
    p_in, warn = start_probability(element, games_played=2)
    assert p_pre <= 0.35
    assert p_in == 0.95
    assert "in_season_minutes" in warn


def test_in_season_unused_outfielder_is_capped() -> None:
    element = {
        "starts": 0,
        "minutes": 0,
        "now_cost": 45,
        "element_type": 4,
    }
    p, warn = start_probability(element, games_played=2)
    assert p <= 0.10
    assert "no_minutes_this_season" in warn


def test_xg_adjustment_raises_underperformer() -> None:
    element = {
        "minutes": 180,
        "element_type": 4,
        "expected_goals": 1.8,
        "expected_assists": 0.1,
        "goals_scored": 0,
        "assists": 0,
    }
    adjusted, warn = apply_xg_adjustment(element, 3.0)
    assert adjusted > 3.0
    assert "xg_adjustment" in warn
