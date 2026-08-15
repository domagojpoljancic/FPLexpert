"""Projection and strategy tests."""

from __future__ import annotations

from fpl_agent.domain.models import Executability, RiskProfile
from fpl_agent.projections.backtest import run_backtest
from fpl_agent.projections.model import minutes_states, project_horizon, project_player_gw
from fpl_agent.rules.season import load_season_rules_2026_27
from fpl_agent.strategy.engine import generate_scenarios


def test_minutes_sum_to_one() -> None:
    a, b, c = minutes_states(0.8, 0.3)
    assert abs(a + b + c - 1.0) < 1e-9


def test_blank_gw_zero() -> None:
    p = project_player_gw(
        player_id=1,
        gameweek=1,
        recent_minutes=[90],
        recent_points=[5],
        position_prior_minutes=70,
        team_attack=0,
        team_defence=0,
        opp_attack=0,
        opp_defence=0,
        is_home=True,
        fixtures_in_gw=0,
    )
    assert p.expected_points == 0.0


def test_ownership_ignored() -> None:
    kwargs = dict(
        player_id=1,
        gameweek=1,
        recent_minutes=[90, 90],
        recent_points=[5, 6],
        position_prior_minutes=70,
        team_attack=0.1,
        team_defence=0.0,
        opp_attack=0.0,
        opp_defence=0.0,
        is_home=True,
        fixtures_in_gw=1,
    )
    a = project_player_gw(**kwargs, ownership=0.01)
    b = project_player_gw(**kwargs, ownership=0.99)
    assert a.expected_points == b.expected_points


def test_horizon_weights() -> None:
    hz = project_horizon(
        player_id=1,
        gameweeks=[1, 2, 3],
        weights=[1.0, 0.5, 0.25],
        per_gw_kwargs=[
            {
                "recent_minutes": [90],
                "recent_points": [4],
                "position_prior_minutes": 70,
                "team_attack": 0,
                "team_defence": 0,
                "opp_attack": 0,
                "opp_defence": 0,
                "is_home": True,
                "fixtures_in_gw": 1,
            }
        ]
        * 3,
    )
    assert hz.weighted_total == sum(w * x for w, x in zip(hz.by_gw and [1, 0.5, 0.25], hz.unweighted_by_gw, strict=True))


def test_backtest_no_leakage() -> None:
    rows = [
        {
            "player_id": 1,
            "gameweek": 1,
            "recent_minutes": [90],
            "recent_points": [4],
            "actual_points": 5,
            "position": "MID",
            "is_home": True,
            "fixtures_in_gw": 1,
        }
    ]
    result = run_backtest(rows)
    assert result.n == 1


def test_backtest_rejects_leakage_field() -> None:
    import pytest

    with pytest.raises(ValueError):
        run_backtest([{"future_leak": 1, "player_id": 1, "gameweek": 1, "recent_minutes": [], "recent_points": [], "actual_points": 0}])


def test_roll_always_present_when_legal() -> None:
    rules = load_season_rules_2026_27()
    squad = []
    # minimal fake 15 with positions
    positions = ["GKP"] * 2 + ["DEF"] * 5 + ["MID"] * 5 + ["FWD"] * 3
    for i, pos in enumerate(positions, start=1):
        squad.append({"player_id": i, "position": pos, "club_id": i})
    xp = {i: [5.0] * 6 for i in range(1, 16)}
    scenarios, _ = generate_scenarios(
        rules=rules,
        executability=Executability.EXECUTABLE,
        bank_tenths=10,
        free_transfers=1,
        squad=squad,
        xp_by_player=xp,
        weights=[1, 0.9, 0.8, 0.7, 0.6, 0.5],
        max_hit=8,
        hits_enabled=True,
        risk_profile=RiskProfile.MODERATE,
    )
    assert any(s.hit_cost == 0 and not s.transfers for s in scenarios)


def test_insufficient_blocks_scenarios() -> None:
    rules = load_season_rules_2026_27()
    scenarios, diag = generate_scenarios(
        rules=rules,
        executability=Executability.INSUFFICIENT,
        bank_tenths=None,
        free_transfers=None,
        squad=[],
        xp_by_player={},
        weights=[1, 0.9, 0.8, 0.7, 0.6, 0.5],
        max_hit=8,
        hits_enabled=True,
    )
    assert scenarios == []
    assert "insufficient_team_state" in diag.pruned
