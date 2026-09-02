"""In-season minutes and xG adjustment tests."""

from __future__ import annotations

from fpl_agent.projections.preseason import (
    apply_xg_adjustment,
    configure_from_settings,
    finished_gameweeks,
    points_per_90_estimate,
    set_defcon_enabled,
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


def test_defcon_lifts_nailed_cbit_defender() -> None:
    set_defcon_enabled(True)
    base = {
        "element_type": 2,
        "now_cost": 50,
        "minutes": 270,
        "total_points": 20,
        "starts": 3,
    }
    weak = {**base, "clearances_blocks_interceptions": 2, "tackles": 1}
    strong = {**base, "clearances_blocks_interceptions": 28, "tackles": 8}
    pp_weak, _ = points_per_90_estimate(weak)
    pp_strong, _ = points_per_90_estimate(strong)
    assert pp_strong > pp_weak
    assert pp_strong - pp_weak <= 2.0


def test_defcon_higher_bar_for_mid_fwd() -> None:
    set_defcon_enabled(True)
    stats = {
        "minutes": 270,
        "now_cost": 55,
        "clearances_blocks_interceptions": 8,
        "tackles": 4,
        "recoveries": 6,
        "total_points": 18,
        "starts": 3,
    }
    def_pp, _ = points_per_90_estimate({**stats, "element_type": 2})
    mid_pp, _ = points_per_90_estimate({**stats, "element_type": 3})
    assert def_pp >= mid_pp


def test_defcon_prior_only_warns() -> None:
    set_defcon_enabled(True)
    element = {
        "element_type": 2,
        "now_cost": 45,
        "minutes": 0,
        "total_points": 0,
        "starts": 0,
    }
    _, warnings = points_per_90_estimate(element)
    assert "defcon_prior_only" in warnings


def test_enable_defcon_default_off() -> None:
    from fpl_agent.config import default_settings_path, load_settings

    settings = load_settings(default_settings_path())
    assert settings.projections.enable_defcon is False
