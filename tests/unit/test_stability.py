"""Repeated-run stability gate (deterministic 100%; live opt-in)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from fpl_agent.llm.client import (
    DailyAdvice,
    DailyMove,
    FakeOpenAIClient,
    MoveType,
    PlanAction,
    validate_daily_advice,
)
from fpl_agent.projections.preseason import PlayerProjection
from fpl_agent.strategy.transfers import (
    PRIMARY_EPSILON_WEIGHTED_XP,
    TransferCandidate,
    TransferPlan,
    select_primary_move,
)

FIXTURE = Path("tests/fixtures/stability_gw3_payload.json")
N_RUNS = 20


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


def _gw3_shaped_conflict() -> tuple[list[int], dict[int, dict], dict[int, PlayerProjection]]:
    types = [1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 4, 4, 4]
    owned = list(range(1, 16))
    catalog: dict[int, dict] = {}
    projections: dict[int, PlayerProjection] = {}
    for pid, et in zip(owned, types, strict=True):
        catalog[pid] = {
            "id": pid,
            "web_name": f"P{pid}",
            "team": pid,
            "element_type": et,
            "now_cost": 50,
            "status": "a",
        }
        if pid == 5:
            catalog[5]["web_name"] = "Onien"
            projections[5] = _proj(5, element_type=2, team_id=5, price=50, weighted=2.0, gw=1.0, p_start=0.40, name="Onien")
        elif pid == 6:
            catalog[6]["web_name"] = "Virgil"
            projections[6] = _proj(6, element_type=2, team_id=6, price=50, weighted=5.5, gw=2.0, p_start=0.90, name="Virgil")
        else:
            projections[pid] = _proj(
                pid,
                element_type=et,
                team_id=pid,
                price=50,
                weighted=6.0 if et != 1 else 4.0,
                gw=2.5 if et != 1 else 3.0,
                name=f"P{pid}",
            )
    catalog[100] = {"id": 100, "web_name": "Egan", "team": 16, "element_type": 2, "now_cost": 50, "status": "a"}
    projections[100] = _proj(100, element_type=2, team_id=16, price=50, weighted=8.5, gw=3.8, p_start=0.85, name="Egan")
    catalog[101] = {"id": 101, "web_name": "Ajayi", "team": 17, "element_type": 2, "now_cost": 50, "status": "a"}
    projections[101] = _proj(101, element_type=2, team_id=17, price=50, weighted=6.8, gw=5.5, p_start=0.90, name="Ajayi")
    return owned, catalog, projections


def _one_move_plan(
    *,
    out_id: int,
    in_id: int,
    out_name: str,
    in_name: str,
    weighted: float,
    gw: float,
) -> TransferPlan:
    move = TransferCandidate(
        out_id=out_id,
        in_id=in_id,
        out_name=out_name,
        in_name=in_name,
        element_type=2,
        sell_tenths=50,
        buy_tenths=50,
        bank_after_tenths=0,
        bank_shortfall_tenths=0,
        affordable=True,
        delta_weighted_xp=weighted,
        delta_gw_xp=gw,
        out_p_start=0.4,
        in_p_start=0.9,
        in_starts=True,
    )
    return TransferPlan(
        moves=(move,),
        free_transfers_used=1,
        hit_cost=0,
        delta_weighted_xp=weighted,
        delta_gw_xp=gw,
        net_gw_xp=gw,
        bank_after_tenths=0,
        affordable=True,
    )


def test_repeated_primary_selection_is_identical() -> None:
    owned, catalog, projections = _gw3_shaped_conflict()
    kwargs = dict(
        owned_ids=owned,
        bank_tenths=0,
        free_transfers=1,
        purchase_prices_tenths={str(i): 50 for i in owned},
        catalog=catalog,
        projections=projections,
    )
    ids = []
    for _ in range(N_RUNS):
        primary = select_primary_move(**kwargs)
        assert primary.plan is not None
        ids.append((primary.plan.moves[-1].out_id, primary.plan.moves[-1].in_id))
    assert len(set(ids)) == 1


def test_repeated_fake_client_matches_primary() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    weekly = fixture["weekly_plan"]
    primary = weekly["primary_move"]
    payload = {
        "attention_triggers": [],
        "what_changed": [],
        "sources": [],
        "weekly_plan": weekly,
        "transfer_candidates": [
            {
                "out_id": 1,
                "in_id": 999,
                "out_name": "Decoy",
                "in_name": "DecoyIn",
                "in_starts": True,
            }
        ],
    }
    client = FakeOpenAIClient()
    results = []
    for _ in range(N_RUNS):
        advice, _ = client.synthesize_daily(payload)
        cleaned = validate_daily_advice(
            advice,
            allowed_player_ids={int(primary["out_id"]), int(primary["in_id"]), 1, 999},
            allowed_source_ids=set(),
            owned_player_ids={int(primary["out_id"])},
            primary_move=primary,
            alternatives=weekly.get("alternatives") or [{"action": "hold"}],
            veto_claims=[],
        )
        transfer = next(m for m in cleaned.suggested_moves if m.move_type == MoveType.TRANSFER)
        results.append(tuple(transfer.player_ids))
        assert weekly["model_captain"]["web_name"]
        assert weekly["model_vice"]["web_name"] == "Raya"
    assert len(set(results)) == 1
    assert results[0][-1] == int(primary["in_id"])


def test_epsilon_near_tie_stable_across_runs() -> None:
    alpha = _one_move_plan(out_id=1, in_id=10, out_name="Out", in_name="Alpha", weighted=4.0, gw=3.0)
    beta = _one_move_plan(
        out_id=2,
        in_id=11,
        out_name="Out2",
        in_name="Beta",
        weighted=4.0 - PRIMARY_EPSILON_WEIGHTED_XP / 2,
        gw=2.0,
    )
    owned, catalog, projections = _gw3_shaped_conflict()
    base = dict(
        owned_ids=owned,
        bank_tenths=0,
        free_transfers=1,
        purchase_prices_tenths={str(i): 50 for i in owned},
        catalog=catalog,
        projections=projections,
    )
    winners = []
    for i in range(N_RUNS):
        plans = [beta, alpha] if i % 2 else [alpha, beta]
        primary = select_primary_move(**base, plans=plans)
        assert primary.plan is not None
        winners.append(primary.plan.moves[-1].in_name)
    assert set(winners) == {"Alpha"}


def test_official_veto_alternative_is_stable() -> None:
    primary = {
        "action": "transfer",
        "out_id": 539,
        "in_id": 277,
        "out_name": "O'Nien",
        "in_name": "Egan",
        "reason": "primary",
    }
    alt = {"action": "transfer", "out_id": 356, "in_id": 279, "out_name": "Virgil", "in_name": "Ajayi"}
    claim = {
        "claim_id": "fpl-277-injury",
        "source_tier": "official",
        "category": "injury",
        "player_ids": [277],
    }
    stub = DailyAdvice(
        plan_action=PlanAction.REVISE,
        headline="Pivot",
        suggested_moves=[
            DailyMove(
                move_type=MoveType.TRANSFER,
                summary="Virgil to Ajayi",
                player_ids=[356, 279],
                cited_source_ids=["fpl-277-injury"],
            )
        ],
        cited_source_ids=["fpl-277-injury"],
    )
    buys = []
    for _ in range(N_RUNS):
        cleaned = validate_daily_advice(
            stub,
            allowed_player_ids={539, 277, 356, 279},
            allowed_source_ids={"fpl-277-injury"},
            owned_player_ids={539, 356},
            primary_move=primary,
            alternatives=[alt, {"action": "hold"}],
            veto_claims=[claim],
        )
        transfer = next(m for m in cleaned.suggested_moves if m.move_type == MoveType.TRANSFER)
        buys.append(transfer.player_ids[-1])
    assert set(buys) == {279}

    restored = []
    stub2 = DailyAdvice(
        plan_action=PlanAction.REVISE,
        headline="Ajayi",
        suggested_moves=[
            DailyMove(move_type=MoveType.TRANSFER, summary="Ajayi", player_ids=[356, 279])
        ],
    )
    for _ in range(N_RUNS):
        cleaned = validate_daily_advice(
            stub2,
            allowed_player_ids={539, 277, 356, 279},
            allowed_source_ids=set(),
            owned_player_ids={539, 356},
            primary_move=primary,
            alternatives=[alt, {"action": "hold"}],
            veto_claims=[],
        )
        transfer = next(m for m in cleaned.suggested_moves if m.move_type == MoveType.TRANSFER)
        restored.append(transfer.player_ids[-1])
    assert set(restored) == {277}


@pytest.mark.skipif(os.environ.get("FPL_LIVE_STABILITY") != "1", reason="opt-in live stability")
def test_live_stability_opt_in() -> None:
    """Live OpenAI repeated-run gate (90%). Not required in CI."""
    from fpl_agent.llm.client import ResponsesOpenAIClient

    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload = {
        "attention_triggers": [],
        "what_changed": [],
        "sources": [],
        "weekly_plan": fixture["weekly_plan"],
        "suggested_source_hubs": [],
        "transfer_candidates": [],
        "policy": {"recommend_only": True},
    }
    client = ResponsesOpenAIClient(web_search_budget=0)
    primary = fixture["weekly_plan"]["primary_move"]
    buys = []
    for _ in range(5):
        advice, _meta = client.synthesize_daily(payload)
        cleaned = validate_daily_advice(
            advice,
            allowed_player_ids={int(primary["out_id"]), int(primary["in_id"])},
            allowed_source_ids=set(),
            owned_player_ids={int(primary["out_id"])},
            primary_move=primary,
            alternatives=[{"action": "hold"}],
            veto_claims=[],
        )
        transfer = next((m for m in cleaned.suggested_moves if m.move_type == MoveType.TRANSFER), None)
        buys.append(None if transfer is None else transfer.player_ids[-1])
    assert buys.count(int(primary["in_id"])) / len(buys) >= 0.9
