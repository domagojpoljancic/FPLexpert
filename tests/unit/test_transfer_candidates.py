"""Transfer candidate ranking and validation guards."""

from __future__ import annotations

from fpl_agent.llm.client import DailyAdvice, DailyMove, MoveType, PlanAction, validate_daily_advice
from fpl_agent.projections.preseason import PlayerProjection
from fpl_agent.strategy.transfers import rank_transfer_candidates


def _proj(
    player_id: int,
    *,
    element_type: int,
    team_id: int,
    price: int,
    weighted: float,
    gw: float,
    p_start: float = 0.9,
    name: str = "X",
) -> PlayerProjection:
    return PlayerProjection(
        player_id=player_id,
        web_name=name,
        team_id=team_id,
        element_type=element_type,
        price_tenths=price,
        p_start=p_start,
        expected_minutes=80.0,
        points_per_90=4.0,
        xp_by_gw=(gw, gw, gw, gw, gw, gw),
        weighted_xp=weighted,
    )


def test_rank_transfer_candidates_returns_affordable_and_stretch() -> None:
    catalog = {
        1: {"id": 1, "web_name": "OutA", "team": 1, "element_type": 4, "now_cost": 50, "status": "a"},
        2: {"id": 2, "web_name": "KeepB", "team": 2, "element_type": 3, "now_cost": 70, "status": "a"},
        10: {"id": 10, "web_name": "InCheap", "team": 3, "element_type": 4, "now_cost": 50, "status": "a"},
        11: {"id": 11, "web_name": "InStretch", "team": 4, "element_type": 4, "now_cost": 70, "status": "a"},
    }
    projections = {
        1: _proj(1, element_type=4, team_id=1, price=50, weighted=5.0, gw=2.0, name="OutA"),
        2: _proj(2, element_type=3, team_id=2, price=70, weighted=8.0, gw=3.0, name="KeepB"),
        10: _proj(10, element_type=4, team_id=3, price=50, weighted=8.0, gw=3.5, name="InCheap"),
        11: _proj(11, element_type=4, team_id=4, price=70, weighted=12.0, gw=5.0, name="InStretch"),
    }
    affordable, stretch = rank_transfer_candidates(
        owned_ids=[1, 2],
        bank_tenths=0,
        purchase_prices_tenths={"1": 50, "2": 70},
        catalog=catalog,
        projections=projections,
    )
    assert affordable
    assert affordable[0].out_id == 1
    assert affordable[0].in_id == 10
    assert affordable[0].affordable is True
    assert stretch
    assert any(c.in_id == 11 and c.affordable is False for c in stretch)


def test_validate_allows_football_sell_of_ignore_owned_player() -> None:
    advice = DailyAdvice(
        plan_action=PlanAction.REVISE,
        headline="Upgrade fodder",
        suggested_moves=[
            DailyMove(
                move_type=MoveType.TRANSFER,
                summary="Sell ignore-tagged owned player for candidate",
                player_ids=[1, 10],
                urgency="high",
            )
        ],
    )
    cleaned = validate_daily_advice(
        advice,
        allowed_player_ids={1, 10},
        allowed_source_ids=set(),
        price_actions=[{"action_class": "ignore", "player_ids": [1]}],
        owned_player_ids={1},
    )
    assert cleaned.suggested_moves[0].move_type == MoveType.TRANSFER


def test_validate_still_blocks_ignore_price_buy() -> None:
    advice = DailyAdvice(
        plan_action=PlanAction.REVISE,
        headline="Buy now",
        suggested_moves=[
            DailyMove(move_type=MoveType.TRANSFER, summary="invented rise", player_ids=[20], urgency="high")
        ],
    )
    cleaned = validate_daily_advice(
        advice,
        allowed_player_ids={20},
        allowed_source_ids=set(),
        price_actions=[{"action_class": "ignore", "player_ids": [20]}],
        owned_player_ids=set(),
    )
    assert cleaned.suggested_moves[0].move_type == MoveType.HOLD
    assert any("price_ignore" in w for w in cleaned.warnings)
