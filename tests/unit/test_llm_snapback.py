"""LLM snap-back: confirm/veto primary, never re-rank on taste."""

from __future__ import annotations

from fpl_agent.llm.client import (
    MODEL_CHOSE_UNSUPPLIED_ALTERNATIVE,
    MODEL_RERANKED_WITHOUT_VETO,
    DailyAdvice,
    DailyMove,
    FakeOpenAIClient,
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
    "reason": "Locked weighted-horizon primary.",
}
ALT = {
    "action": "transfer",
    "out_id": 356,
    "in_id": 279,
    "out_name": "Virgil",
    "in_name": "Ajayi",
}
OWNED = {539, 356, 1, 4}
ALLOWED = OWNED | {277, 279}


def test_rerank_without_veto_snaps_back_to_primary() -> None:
    advice = DailyAdvice(
        plan_action=PlanAction.REVISE,
        headline="Buy Ajayi",
        suggested_moves=[
            DailyMove(
                move_type=MoveType.TRANSFER,
                summary="Virgil to Ajayi",
                why="Better this GW",
                player_ids=[356, 279],
            )
        ],
    )
    cleaned = validate_daily_advice(
        advice,
        allowed_player_ids=ALLOWED,
        allowed_source_ids=set(),
        owned_player_ids=OWNED,
        primary_move=PRIMARY,
        alternatives=[ALT, {"action": "hold"}],
        veto_claims=[],
    )
    transfer = next(m for m in cleaned.suggested_moves if m.move_type == MoveType.TRANSFER)
    assert transfer.player_ids[-1] == 277
    assert 279 not in transfer.player_ids
    assert MODEL_RERANKED_WITHOUT_VETO in cleaned.warnings


def test_official_veto_allows_supplied_alternative() -> None:
    claim = {
        "claim_id": "fpl-277-injury",
        "source_tier": "official",
        "category": "injury",
        "player_ids": [277],
        "text": "Egan ruled out",
    }
    advice = DailyAdvice(
        plan_action=PlanAction.REVISE,
        headline="Pivot to Ajayi",
        suggested_moves=[
            DailyMove(
                move_type=MoveType.TRANSFER,
                summary="Virgil to Ajayi",
                why="Egan injured",
                player_ids=[356, 279],
                cited_source_ids=["fpl-277-injury"],
            )
        ],
        cited_source_ids=["fpl-277-injury"],
    )
    cleaned = validate_daily_advice(
        advice,
        allowed_player_ids=ALLOWED,
        allowed_source_ids={"fpl-277-injury"},
        owned_player_ids=OWNED,
        primary_move=PRIMARY,
        alternatives=[ALT, {"action": "hold"}],
        veto_claims=[claim],
    )
    transfer = next(m for m in cleaned.suggested_moves if m.move_type == MoveType.TRANSFER)
    assert transfer.player_ids[-1] == 279
    assert MODEL_RERANKED_WITHOUT_VETO not in cleaned.warnings
    assert MODEL_CHOSE_UNSUPPLIED_ALTERNATIVE not in cleaned.warnings


def test_fake_client_echoes_primary_deterministically() -> None:
    payload = {
        "attention_triggers": [],
        "what_changed": [],
        "sources": [],
        "weekly_plan": {"primary_move": PRIMARY},
        "transfer_candidates": [
            {"out_id": 356, "in_id": 279, "out_name": "Virgil", "in_name": "Ajayi", "in_starts": True}
        ],
    }
    client = FakeOpenAIClient()
    a1, _ = client.synthesize_daily(payload)
    a2, _ = client.synthesize_daily(payload)
    assert a1.suggested_moves[0].player_ids == [539, 277]
    assert a2.suggested_moves[0].player_ids == [539, 277]
