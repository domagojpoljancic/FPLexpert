"""This-week chip play/hold planner."""

from __future__ import annotations

from fpl_agent.domain.models import ChipHalf, ChipKind
from fpl_agent.strategy.chips import recommend_chips
from fpl_agent.team_state.private import PrivateChipInstance


def _plan(*, captain_xp: float, bench_xp: float, this_xi: float, other_xi: float, low_starts: int = 0) -> dict:
    xi = [
        {"player_id": i, "web_name": f"P{i}", "p_start": 0.2 if i <= low_starts else 0.9, "xp_next": 4.0}
        for i in range(1, 12)
    ]
    bench = [
        {"web_name": f"B{i}", "position": "DEF", "p_start": 0.8, "xp_next": bench_xp / 3}
        for i in range(3)
    ]
    return {
        "ok": True,
        "model_captain": {"web_name": "Haaland", "xp_next": captain_xp, "p_start": 0.95},
        "xi": xi,
        "bench": bench,
        "horizon": [
            {"gw": 5, "xi_xp": this_xi, "captain": "Haaland", "captain_xp": captain_xp},
            {"gw": 6, "xi_xp": other_xi, "captain": "Salah", "captain_xp": 5.0},
            {"gw": 7, "xi_xp": other_xi, "captain": "Salah", "captain_xp": 5.0},
        ],
    }


def test_triple_captain_play_on_outlier_week() -> None:
    plan = _plan(captain_xp=12.0, bench_xp=4.0, this_xi=48.0, other_xi=46.0)
    plan["model_captain"]["captain_rationale"] = {"haul_proxy": 0.45, "ceiling": 16.0}
    rows = recommend_chips(gameweek=5, weekly_plan=plan)
    by_kind = {r.kind: r for r in rows}
    assert by_kind["3xc"].action == "play"
    assert by_kind["bboost"].action == "hold"
    assert by_kind["freehit"].action == "hold"
    assert by_kind["wildcard"].action == "hold"


def test_bench_boost_play_when_bench_is_strong() -> None:
    rows = recommend_chips(gameweek=5, weekly_plan=_plan(captain_xp=5.0, bench_xp=9.5, this_xi=48.0, other_xi=46.0))
    assert next(r for r in rows if r.kind == "bboost").action == "play"


def test_free_hit_play_on_blank_week() -> None:
    rows = recommend_chips(gameweek=5, weekly_plan=_plan(captain_xp=5.0, bench_xp=4.0, this_xi=20.0, other_xi=45.0))
    assert next(r for r in rows if r.kind == "freehit").action == "play"


def test_wildcard_play_when_several_starters_look_benched() -> None:
    rows = recommend_chips(
        gameweek=5,
        weekly_plan=_plan(captain_xp=5.0, bench_xp=4.0, this_xi=40.0, other_xi=42.0, low_starts=3),
    )
    assert next(r for r in rows if r.kind == "wildcard").action == "play"


def test_used_chip_is_unavailable() -> None:
    rows = recommend_chips(
        gameweek=5,
        weekly_plan=_plan(captain_xp=12.0, bench_xp=4.0, this_xi=48.0, other_xi=46.0),
        chip_instances=[
            PrivateChipInstance(kind=ChipKind.TRIPLE_CAPTAIN, half=ChipHalf.FIRST, available=False, used_in_gameweek=2)
        ],
    )
    tc = next(r for r in rows if r.kind == "3xc")
    assert tc.available is False
    assert tc.action == "hold"
