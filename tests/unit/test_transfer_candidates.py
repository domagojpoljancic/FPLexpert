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


def test_this_week_upgrade_requires_buy_to_start() -> None:
    from fpl_agent.strategy.transfers import TransferCandidate, this_week_upgrade

    def cand(*, in_id: int, in_starts: bool) -> TransferCandidate:
        return TransferCandidate(
            out_id=1,
            in_id=in_id,
            out_name="Out",
            in_name="In",
            element_type=2,
            sell_tenths=50,
            buy_tenths=50,
            bank_after_tenths=0,
            bank_shortfall_tenths=0,
            affordable=True,
            delta_weighted_xp=2.0,
            delta_gw_xp=1.0,
            out_p_start=0.4,
            in_p_start=0.8,
            in_starts=in_starts,
        )

    assert this_week_upgrade([cand(in_id=10, in_starts=False)]) is None
    pick = this_week_upgrade(
        [cand(in_id=10, in_starts=False), cand(in_id=11, in_starts=True)]
    )
    assert pick is not None
    assert pick.in_id == 11


def test_explain_transfer_puts_numbers_in_brackets() -> None:
    from fpl_agent.strategy.transfers import TransferCandidate, explain_transfer

    cand = TransferCandidate(
        out_id=1,
        in_id=10,
        out_name="O'Nien",
        in_name="Egan",
        element_type=2,
        sell_tenths=40,
        buy_tenths=40,
        bank_after_tenths=5,
        bank_shortfall_tenths=0,
        affordable=True,
        delta_weighted_xp=4.563,
        delta_gw_xp=2.83,
        out_p_start=0.4,
        in_p_start=0.8,
        in_starts=True,
        xi_drop_name="Virgil",
        out_xp_next=0.6,
        in_xp_next=5.7,
        xi_drop_xp_next=2.1,
    )
    text = explain_transfer(cand)
    assert "Sell O'Nien for Egan" in text
    assert "5.7 vs 0.6 pts" in text
    assert "only 40% likely to play" in text
    assert "start Egan (5.7 pts) ahead of Virgil (2.1 pts)" in text
    assert "not by how easy the opponent looks" in text
    assert "Bank left: £0.5m." in text
    assert "(+2.8 pts this week; +4.6 over the next few GWs)." in text
    assert "weighted xP" not in text
    assert "net GW" not in text
    assert cand.as_payload()["reason"] == text


def test_explain_xi_choice_names_new_starter_and_bench_drop() -> None:
    from fpl_agent.strategy.transfers import explain_xi_choice

    text = explain_xi_choice(
        xi=[{"web_name": "Egan", "xp_next": 5.7}, {"web_name": "Tzolis", "xp_next": 2.2}],
        bench=[{"web_name": "Virgil", "xp_next": 2.1}],
        formation="3-5-2",
        in_name="Egan",
        drop_name="Virgil",
    )
    assert "Why this XI" in text
    assert "Egan (5.7 pts)" in text
    assert "Virgil (2.1 pts)" in text
    assert "fixture" in text or "slots" in text


def test_same_position_shortlist_puts_pick_first() -> None:
    from fpl_agent.strategy.transfers import TransferCandidate, explain_vs_pick, same_position_shortlist

    def cand(*, in_id: int, in_name: str, gw: float, weighted: float, out_name: str = "Virgil") -> TransferCandidate:
        return TransferCandidate(
            out_id=1 if out_name == "Virgil" else 2,
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
            out_p_start=0.84,
            in_p_start=0.8,
            in_starts=True,
        )

    pick = cand(in_id=10, in_name="Ajayi", gw=3.5, weighted=1.3)
    de_cuyper = cand(in_id=11, in_name="De Cuyper", gw=3.4, weighted=3.5)
    egan = cand(in_id=12, in_name="Egan", gw=2.8, weighted=4.6, out_name="O'Nien")
    mid = TransferCandidate(
        out_id=3,
        in_id=20,
        out_name="Rogers",
        in_name="Cherki",
        element_type=3,
        sell_tenths=50,
        buy_tenths=50,
        bank_after_tenths=0,
        bank_shortfall_tenths=0,
        affordable=True,
        delta_weighted_xp=2.0,
        delta_gw_xp=1.0,
        out_p_start=0.9,
        in_p_start=0.9,
        in_starts=True,
    )
    short = same_position_shortlist(pick, [pick, de_cuyper, egan, mid], limit=3)
    assert [c.in_name for c in short] == ["Ajayi", "De Cuyper", "Egan"]
    vs = explain_vs_pick(de_cuyper, pick)
    assert "is roughly level with Ajayi on points this week" in vs
    assert "looks better over the next few gameweeks" in vs
    assert "(+3.4 pts this week; +3.5 over the next few GWs)." in vs
    assert "O'Nien" in explain_vs_pick(egan, pick)


def test_ranked_candidates_mark_starting_buys() -> None:
    from fpl_agent.strategy.transfers import this_week_upgrade

    owned, catalog, projections = _fifteen()
    affordable, _stretch = rank_transfer_candidates(
        owned_ids=owned,
        bank_tenths=0,
        purchase_prices_tenths={str(i): 50 for i in owned},
        catalog=catalog,
        projections=projections,
    )
    assert affordable
    pick = this_week_upgrade(affordable)
    assert pick is not None
    assert pick.in_starts is True


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


def _fifteen(
    *,
    weak_ids: tuple[int, ...] = (13, 14),
    in_ids: tuple[int, ...] = (20, 21),
) -> tuple[list[int], dict[int, dict], dict[int, PlayerProjection]]:
    types = [1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 4, 4, 4]
    owned = list(range(1, 16))
    catalog: dict[int, dict] = {}
    projections: dict[int, PlayerProjection] = {}
    for pid, et in zip(owned, types, strict=True):
        weak = pid in weak_ids
        catalog[pid] = {
            "id": pid,
            "web_name": f"Out{pid}" if weak else f"Keep{pid}",
            "team": pid,
            "element_type": et,
            "now_cost": 50,
            "status": "a",
        }
        projections[pid] = _proj(
            pid,
            element_type=et,
            team_id=pid,
            price=50,
            weighted=3.0 if weak else 6.0,
            gw=1.0 if weak else 2.5,
            name=catalog[pid]["web_name"],
        )
    for inn, team in zip(in_ids, (16, 17), strict=True):
        catalog[inn] = {
            "id": inn,
            "web_name": f"In{inn}",
            "team": team,
            "element_type": 4,
            "now_cost": 50,
            "status": "a",
        }
        projections[inn] = _proj(
            inn,
            element_type=4,
            team_id=team,
            price=50,
            weighted=12.0,
            gw=7.0,
            name=f"In{inn}",
        )
    return owned, catalog, projections


def test_two_free_transfers_plan_has_no_hit() -> None:
    from fpl_agent.strategy.transfers import rank_transfer_plans

    owned, catalog, projections = _fifteen()
    plans = rank_transfer_plans(
        owned_ids=owned,
        bank_tenths=0,
        free_transfers=2,
        purchase_prices_tenths={str(i): 50 for i in owned},
        catalog=catalog,
        projections=projections,
    )
    doubles = [p for p in plans if len(p.moves) == 2]
    assert doubles
    assert doubles[0].hit_cost == 0
    assert doubles[0].net_gw_xp == doubles[0].delta_gw_xp
    assert {m.in_id for m in doubles[0].moves} == {20, 21}


def test_hit_plan_only_when_net_gw_beats_four() -> None:
    from fpl_agent.strategy.transfers import rank_transfer_plans

    owned, catalog, projections = _fifteen()
    plans = rank_transfer_plans(
        owned_ids=owned,
        bank_tenths=0,
        free_transfers=1,
        purchase_prices_tenths={str(i): 50 for i in owned},
        catalog=catalog,
        projections=projections,
        hits_enabled=True,
    )
    hits = [p for p in plans if p.hit_cost == 4]
    assert hits
    assert hits[0].net_gw_xp >= 0.5
    assert hits[0].net_gw_xp == hits[0].delta_gw_xp - 4


def test_hits_disabled_skips_two_swap_when_one_ft() -> None:
    from fpl_agent.strategy.transfers import rank_transfer_plans

    owned, catalog, projections = _fifteen()
    plans = rank_transfer_plans(
        owned_ids=owned,
        bank_tenths=0,
        free_transfers=1,
        purchase_prices_tenths={str(i): 50 for i in owned},
        catalog=catalog,
        projections=projections,
        hits_enabled=False,
    )
    assert all(len(p.moves) == 1 for p in plans)


def test_cross_position_restructure_surfaces() -> None:
    from fpl_agent.strategy.transfers import rank_cross_position_plans

    owned = list(range(1, 16))
    types = [1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 4, 4, 4]
    catalog: dict[int, dict] = {}
    projections: dict[int, PlayerProjection] = {}
    for pid, et in zip(owned, types, strict=True):
        catalog[pid] = {
            "id": pid,
            "web_name": f"P{pid}",
            "team": pid,
            "element_type": et,
            "now_cost": 50 if et != 3 else 70,
            "status": "a",
        }
        projections[pid] = _proj(
            pid,
            element_type=et,
            team_id=pid,
            price=50 if et != 3 else 70,
            weighted=4.0 if et == 3 else 6.0,
            gw=2.0 if et == 3 else 3.0,
            name=f"P{pid}",
        )
    # Premium FWD + enabler MID funded by selling one MID and one FWD
    catalog[100] = {"id": 100, "web_name": "Premium", "team": 20, "element_type": 4, "now_cost": 100, "status": "a"}
    catalog[101] = {"id": 101, "web_name": "Enabler", "team": 21, "element_type": 3, "now_cost": 45, "status": "a"}
    projections[100] = _proj(100, element_type=4, team_id=20, price=100, weighted=18.0, gw=8.0, name="Premium")
    projections[101] = _proj(101, element_type=3, team_id=21, price=45, weighted=3.0, gw=1.5, name="Enabler", p_start=0.75)
    # weaken fwd fodder so it is in the weak pool
    projections[13] = _proj(13, element_type=4, team_id=13, price=50, weighted=3.0, gw=1.0, name="P13")
    projections[8] = _proj(8, element_type=3, team_id=8, price=70, weighted=3.5, gw=1.5, name="P8")
    plans = rank_cross_position_plans(
        owned_ids=owned,
        bank_tenths=50,
        free_transfers=2,
        purchase_prices_tenths={str(i): catalog[i]["now_cost"] for i in owned},
        catalog=catalog,
        projections=projections,
        rules=__import__("fpl_agent.rules.season", fromlist=["load_season_rules_2026_27"]).load_season_rules_2026_27(),
        hit_points=4,
        base_xi=(80.0, 12.0),
    )
    assert plans
    assert any({m.in_id for m in p.moves} == {100, 101} for p in plans)


def test_horizon_objective_beats_single_gw() -> None:
    from fpl_agent.strategy.transfers import TransferCandidate, TransferPlan, rank_transfer_plans

    owned, catalog, projections = _fifteen()
    # Artificial plan: great horizon, weak this GW
    churn = TransferPlan(
        moves=(
            TransferCandidate(
                out_id=13,
                in_id=20,
                out_name="Out13",
                in_name="In20",
                element_type=4,
                sell_tenths=50,
                buy_tenths=50,
                bank_after_tenths=0,
                bank_shortfall_tenths=0,
                affordable=True,
                delta_weighted_xp=8.0,
                delta_gw_xp=-1.0,
                out_p_start=0.9,
                in_p_start=0.9,
                in_starts=True,
            ),
        ),
        free_transfers_used=1,
        hit_cost=0,
        delta_weighted_xp=8.0,
        delta_gw_xp=-1.0,
        net_gw_xp=-1.0,
        bank_after_tenths=0,
        affordable=True,
    )
    plans = rank_transfer_plans(
        owned_ids=owned,
        bank_tenths=0,
        free_transfers=1,
        purchase_prices_tenths={str(i): 50 for i in owned},
        catalog=catalog,
        projections=projections,
    )
    assert plans
    assert plans[0].delta_weighted_xp >= plans[0].delta_gw_xp or plans[0].delta_weighted_xp > 0
    assert churn.delta_weighted_xp > churn.delta_gw_xp


def test_single_move_hit_requires_horizon_ev() -> None:
    from fpl_agent.strategy.transfers import TransferCandidate, TransferPlan, hit_clears_horizon_bar, rank_transfer_plans

    owned, catalog, projections = _fifteen()
    weak = TransferPlan(
        moves=(
            TransferCandidate(
                out_id=13,
                in_id=20,
                out_name="Out",
                in_name="In",
                element_type=4,
                sell_tenths=50,
                buy_tenths=50,
                bank_after_tenths=0,
                bank_shortfall_tenths=0,
                affordable=True,
                delta_weighted_xp=1.0,
                delta_gw_xp=3.0,
                out_p_start=0.9,
                in_p_start=0.9,
                in_starts=True,
            ),
        ),
        free_transfers_used=1,
        hit_cost=4,
        delta_weighted_xp=1.0,
        delta_gw_xp=3.0,
        net_gw_xp=-1.0,
        bank_after_tenths=0,
        affordable=True,
    )
    assert not hit_clears_horizon_bar(weak, margin=1.0)
    plans = rank_transfer_plans(
        owned_ids=owned,
        bank_tenths=0,
        free_transfers=1,
        purchase_prices_tenths={str(i): 50 for i in owned},
        catalog=catalog,
        projections=projections,
        hits_enabled=True,
    )
    assert all(p.hit_cost == 0 or hit_clears_horizon_bar(p, margin=1.0) for p in plans)


def test_roll_preferred_when_no_move_clears_bar() -> None:
    from fpl_agent.strategy.transfers import roll_recommendation_reason

    reason = roll_recommendation_reason(free_transfers=1, best_plan=None, margin=1.0)
    assert "bank" in reason.lower() or "roll" in reason.lower()


def test_hit_bar_scales_with_risk_profile() -> None:
    from fpl_agent.domain.models import RiskProfile
    from fpl_agent.strategy.transfers import TransferPlan, hit_clears_horizon_bar, hit_horizon_margin

    plan = TransferPlan(
        moves=(),
        free_transfers_used=0,
        hit_cost=4,
        delta_weighted_xp=6.0,
        delta_gw_xp=2.0,
        net_gw_xp=-2.0,
        bank_after_tenths=0,
        affordable=True,
    )
    assert hit_clears_horizon_bar(plan, margin=hit_horizon_margin(risk_profile=RiskProfile.AGGRESSIVE))
    assert not hit_clears_horizon_bar(plan, margin=hit_horizon_margin(risk_profile=RiskProfile.CONSERVATIVE))


def test_ft_cap_enforced() -> None:
    from fpl_agent.strategy.transfers import MAX_BANKED_FTS

    assert MAX_BANKED_FTS == 5


def test_early_season_bar_moderately_stricter() -> None:
    from fpl_agent.domain.models import RiskProfile
    from fpl_agent.strategy.transfers import TransferPlan, hit_clears_horizon_bar, hit_horizon_margin

    plan = TransferPlan(
        moves=(),
        free_transfers_used=0,
        hit_cost=4,
        delta_weighted_xp=5.0,
        delta_gw_xp=2.0,
        net_gw_xp=-2.0,
        bank_after_tenths=0,
        affordable=True,
    )
    gw2 = hit_horizon_margin(risk_profile=RiskProfile.MODERATE, gameweek=2, early_season_boost=1.0)
    gw10 = hit_horizon_margin(risk_profile=RiskProfile.MODERATE, gameweek=10, early_season_boost=1.0)
    assert gw2 > gw10
    assert hit_clears_horizon_bar(plan, margin=gw10)
    assert not hit_clears_horizon_bar(plan, margin=gw2)


def test_horizon_transfer_impact_reports_per_gw_delta() -> None:
    from fpl_agent.rules.season import load_season_rules_2026_27
    from fpl_agent.strategy.transfers import horizon_transfer_impact

    rules = load_season_rules_2026_27()
    owned = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
    after = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16]
    projections = {
        pid: _proj(
            pid,
            element_type=3 if pid <= 10 else 2,
            team_id=pid,
            price=60,
            weighted=5.0 + pid * 0.1,
            gw=3.0 + pid * 0.1,
            name=f"P{pid}",
        )
        for pid in set(owned + after)
    }
    projections[15] = _proj(
        15, element_type=2, team_id=15, price=40, weighted=2.0, gw=1.0, name="OutDef", p_start=0.3
    )
    projections[16] = _proj(
        16, element_type=2, team_id=16, price=45, weighted=8.0, gw=4.0, name="InDef", p_start=0.9
    )
    impact = horizon_transfer_impact(
        owned_ids=owned,
        after_ids=after,
        projections=projections,
        rules=rules,
        gameweeks=[3, 4, 5, 6],
        weights=[1.0, 0.9, 0.78, 0.66],
    )
    assert impact["by_gw"]
    assert impact["weighted_delta"] != 0.0
    assert "GW" in impact["reason"]


def test_compare_roll_vs_transfer_banks_marginal_move() -> None:
    from fpl_agent.rules.season import load_season_rules_2026_27
    from fpl_agent.strategy.transfers import TransferCandidate, TransferPlan, compare_roll_vs_transfer

    rules = load_season_rules_2026_27()
    move = TransferCandidate(
        out_id=1,
        in_id=2,
        out_name="A",
        in_name="B",
        element_type=2,
        sell_tenths=40,
        buy_tenths=45,
        bank_after_tenths=0,
        bank_shortfall_tenths=0,
        affordable=True,
        delta_weighted_xp=0.4,
        delta_gw_xp=0.3,
        out_p_start=0.5,
        in_p_start=0.8,
        in_starts=True,
    )
    plan = TransferPlan(
        moves=(move,),
        free_transfers_used=1,
        hit_cost=0,
        delta_weighted_xp=0.4,
        delta_gw_xp=0.3,
        net_gw_xp=0.3,
        bank_after_tenths=0,
        affordable=True,
    )
    decision = compare_roll_vs_transfer(
        free_transfers=1,
        best_plan=plan,
        margin=1.0,
        rules=rules,
        ft_bank_option_value=0.35,
    )
    assert decision.action == "roll"
    assert decision.free_transfers_if_roll == 2
    assert decision.free_transfers_if_transfer == 1
    assert "bank" in decision.reason.lower() or "marginal" in decision.reason.lower()


def test_compare_roll_vs_transfer_spends_clear_edge() -> None:
    from fpl_agent.rules.season import load_season_rules_2026_27
    from fpl_agent.strategy.transfers import TransferCandidate, TransferPlan, compare_roll_vs_transfer

    rules = load_season_rules_2026_27()
    move = TransferCandidate(
        out_id=1,
        in_id=2,
        out_name="A",
        in_name="B",
        element_type=2,
        sell_tenths=40,
        buy_tenths=45,
        bank_after_tenths=0,
        bank_shortfall_tenths=0,
        affordable=True,
        delta_weighted_xp=3.5,
        delta_gw_xp=2.0,
        out_p_start=0.5,
        in_p_start=0.8,
        in_starts=True,
    )
    plan = TransferPlan(
        moves=(move,),
        free_transfers_used=1,
        hit_cost=0,
        delta_weighted_xp=3.5,
        delta_gw_xp=2.0,
        net_gw_xp=2.0,
        bank_after_tenths=0,
        affordable=True,
    )
    decision = compare_roll_vs_transfer(
        free_transfers=1,
        best_plan=plan,
        margin=1.0,
        rules=rules,
        ft_bank_option_value=0.35,
    )
    assert decision.action == "transfer"
    assert "spend" in decision.reason.lower()
