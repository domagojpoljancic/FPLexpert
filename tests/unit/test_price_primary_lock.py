"""Price timing may escalate the primary, never choose a different IN."""

from __future__ import annotations

from fpl_agent.daily import _align_price_actions_to_primary
from fpl_agent.llm.client import (
    DailyAdvice,
    DailyMove,
    MoveType,
    PlanAction,
    validate_daily_advice,
)


PRIMARY = {
    "action": "transfer",
    "out_id": 539,
    "in_id": 277,
    "out_name": "O'Nien",
    "in_name": "Egan",
    "reason": "Locked primary",
}


def test_act_now_on_non_primary_demotes_to_watch() -> None:
    block = {
        "price_status": "ACT TONIGHT (conditional)",
        "price_actions": [
            {"action_class": "act_now_conditional", "player_ids": [356], "web_names": ["Virgil"]},
        ],
    }
    aligned = _align_price_actions_to_primary(block, PRIMARY)
    assert aligned["price_status"] == "WATCH"
    assert aligned["price_actions"][0]["action_class"] == "watch"
    assert aligned["price_actions"][0].get("demoted_from_act_now") is True
    assert aligned.get("primary_price_urgency") == "low"
    assert any("Virgil" in n or "356" in n for n in aligned.get("price_watch_notes") or [])


def test_act_now_on_primary_keeps_act_tonight() -> None:
    block = {
        "price_status": "WATCH",
        "price_actions": [
            {"action_class": "act_now_conditional", "player_ids": [277, 539]},
        ],
    }
    aligned = _align_price_actions_to_primary(block, PRIMARY)
    assert "ACT TONIGHT" in str(aligned["price_status"])
    assert aligned["price_actions"][0]["action_class"] == "act_now_conditional"
    assert aligned.get("primary_price_urgency") == "high"


def test_hold_primary_not_flipped_by_foreign_act_now() -> None:
    advice = DailyAdvice(
        plan_action=PlanAction.REVISE,
        headline="Buy Virgil now",
        suggested_moves=[
            DailyMove(
                move_type=MoveType.TRANSFER,
                summary="Buy because price",
                player_ids=[356, 279],
            )
        ],
    )
    cleaned = validate_daily_advice(
        advice,
        allowed_player_ids={539, 356, 277, 279},
        allowed_source_ids=set(),
        owned_player_ids={539, 356},
        primary_move={"action": "hold", "reason": "Roll FT"},
        alternatives=[{"action": "hold"}],
        price_actions=[{"action_class": "act_now_conditional", "player_ids": [356]}],
        veto_claims=[],
    )
    assert all(m.move_type != MoveType.TRANSFER for m in cleaned.suggested_moves)
    assert cleaned.plan_action in {PlanAction.KEEP, PlanAction.WATCH, PlanAction.REVISE}
