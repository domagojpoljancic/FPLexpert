"""Captaincy policy tests."""

from __future__ import annotations

from fpl_agent.projections.preseason import PlayerProjection
from fpl_agent.strategy.captaincy import captain_components, pick_captain_and_vice
from fpl_agent.strategy.chips import recommend_chips


def _player(
    pid: int,
    *,
    et: int = 4,
    price: int = 90,
    gw: float = 6.0,
    p_start: float = 0.9,
    name: str = "P",
) -> PlayerProjection:
    return PlayerProjection(
        player_id=pid,
        web_name=name,
        team_id=1,
        element_type=et,
        price_tenths=price,
        p_start=p_start,
        expected_minutes=78.0,
        points_per_90=5.0,
        xp_by_gw=(gw,) * 6,
        weighted_xp=gw * 4,
    )


def test_captain_prefers_higher_ceiling_when_means_tie() -> None:
    a = _player(1, gw=6.0, p_start=0.92, name="Safe")
    b = _player(2, gw=6.0, p_start=0.92, name="Premium")
    catalog = {2: {"penalties_order": 1, "expected_goals": 0.8}}
    cap, _, _ = pick_captain_and_vice([a, b], catalog=catalog)
    assert cap.player_id == 2


def test_captain_respects_nailedness() -> None:
    rotation = _player(1, gw=6.5, p_start=0.45, name="Rotation")
    nailed = _player(2, gw=6.0, p_start=0.95, name="Nailed")
    cap, _, _ = pick_captain_and_vice([rotation, nailed])
    assert cap.player_id == 2


def test_horizon_captain_uses_same_policy() -> None:
    from fpl_agent.strategy.plan import build_weekly_plan

    owned = [1, 2]
    projections = {
        1: _player(1, et=3, gw=5.0, p_start=0.5, name="A"),
        2: _player(2, et=4, gw=5.0, p_start=0.95, name="B", price=120),
    }
    catalog = {2: {"penalties_order": 1}}
    plan = build_weekly_plan(
        owned_ids=owned,
        projections=projections,
        gameweeks=[1, 2],
        catalog=catalog,
    )
    assert plan["horizon"][0]["captain"] == plan["model_captain"]["web_name"]


def test_vice_is_nailed_backup() -> None:
    cap = _player(1, gw=7.0, p_start=0.95, name="Cap")
    vice = _player(2, gw=5.0, p_start=0.98, name="Vice")
    risky = _player(3, gw=6.5, p_start=0.4, name="Risk")
    _, picked, _ = pick_captain_and_vice([cap, vice, risky])
    assert picked is not None
    assert picked.player_id == 2


def test_tc_requires_ceiling_not_just_mean() -> None:
    plan = {
        "ok": True,
        "model_captain": {
            "web_name": "Safe",
            "xp_next": 9.0,
            "p_start": 0.95,
            "captain_rationale": {"haul_proxy": 0.05, "ceiling": 9.5},
        },
        "xi": [],
        "bench": [{"web_name": "B", "position": "DEF", "p_start": 0.8, "xp_next": 2.0}],
        "horizon": [
            {"gw": 5, "xi_xp": 50.0, "captain_xp": 9.0},
            {"gw": 6, "xi_xp": 48.0, "captain_xp": 5.0},
        ],
    }
    rows = recommend_chips(gameweek=5, weekly_plan=plan)
    tc = next(r for r in rows if r.kind == "3xc")
    assert tc.action == "hold"
    assert "ceiling" in tc.reason.lower() or "haul" in tc.reason.lower()
