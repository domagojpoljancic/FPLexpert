"""Golden anti-patterns for pre-deadline advice lint."""

from __future__ import annotations

from fpl_agent.advice_lint import lint_predeadline_advice
from fpl_agent.daily import _apply_advice_lint, reconcile_transfer_advice, render_daily_text
from fpl_agent.daily import DailyReport
from fpl_agent.llm.client import DailyAdvice, DailyMove, MoveType, PlanAction
from fpl_agent.rules.season import load_season_rules_2026_27
from fpl_agent.strategy.transfers import TransferCandidate


def _anderson_tavernier() -> TransferCandidate:
    return TransferCandidate(
        out_id=10,
        in_id=20,
        out_name="Anderson",
        in_name="Tavernier",
        element_type=3,
        sell_tenths=55,
        buy_tenths=55,
        bank_after_tenths=3,
        bank_shortfall_tenths=0,
        affordable=True,
        delta_weighted_xp=1.75,
        delta_gw_xp=2.16,
        out_p_start=0.9,
        in_p_start=0.9,
        in_starts=True,
    )


def test_lint_flags_roll_with_transfer_and_no_hit() -> None:
    plan = {
        "transfer_decision": {
            "action": "roll",
            "hit_points_if_transfer": 4,
            "free_transfers_now": 0,
            "free_transfers_if_roll": 1,
            "free_transfers_if_transfer": 1,
        },
        "chips": [],
    }
    issues = lint_predeadline_advice(
        weekly_plan=plan,
        suggested_moves=[
            {
                "move_type": "transfer",
                "summary": "Sell Anderson for Tavernier",
                "why": "Raises projected points this week (4.3 vs 2.1). Bank left £0.3m.",
            },
            {
                "move_type": "hold",
                "summary": "Roll the transfer",
                "why": "Rolling and transferring both leave one free transfer.",
            },
        ],
        report_text=(
            "transfer: Sell Anderson for Tavernier (+2.2 this week)\n"
            "hold: Roll — both leave 1 FT\n"
        ),
    )
    codes = {i.code for i in issues}
    assert "roll_with_transfer_move" in codes
    assert "roll_hold_missing_hit" in codes or "report_missing_hit_on_roll" in codes


def test_lint_flags_wildcard_start_chance_only() -> None:
    plan = {
        "transfer_decision": {"action": "roll", "hit_points_if_transfer": 0},
        "chips": [
            {
                "kind": "wildcard",
                "action": "play",
                "reason": "3 starters are below 40% start chance (A, B, C).",
            }
        ],
    }
    issues = lint_predeadline_advice(weekly_plan=plan, suggested_moves=[])
    assert any(i.code == "wildcard_start_chance_only" for i in issues)


def test_lint_clean_when_roll_discloses_hit() -> None:
    plan = {
        "transfer_decision": {
            "action": "roll",
            "hit_points_if_transfer": 4,
            "free_transfers_now": 0,
        },
        "chips": [
            {
                "kind": "wildcard",
                "action": "hold",
                "reason": "Squad health, fixture trend, and transfer-plan value look fine.",
            }
        ],
    }
    issues = lint_predeadline_advice(
        weekly_plan=plan,
        suggested_moves=[
            {
                "move_type": "hold",
                "summary": "Hold — Anderson→Tavernier costs −4 (net -1.8)",
                "why": "Gross +2.2 before a −4 hit is net -1.8 this week.",
            }
        ],
        report_text="Hold path (skip Anderson → Tavernier, −4 / net -1.8). FT after: next GW 1; transfer costs −4 now.",
    )
    assert issues == []


def test_reconcile_then_lint_strips_contradictory_zero_ft_transfer() -> None:
    cand = _anderson_tavernier()
    weekly = {
        "ok": True,
        "best_affordable": cand.as_payload(),
        "chips": [],
        "transfer_decision": {
            "action": "roll",
            "reason": "You have 0 FT, so Anderson→Tavernier costs a −4 hit.",
            "free_transfers_now": 0,
            "free_transfers_if_roll": 1,
            "free_transfers_if_transfer": 1,
            "hit_points_if_transfer": 4,
            "net_value_after_ft_penalty": -2.25,
        },
    }
    advice = DailyAdvice(
        plan_action=PlanAction.REVISE,
        headline="Sell Anderson for Tavernier",
        suggested_moves=[
            DailyMove(
                move_type=MoveType.TRANSFER,
                summary="Sell Anderson for Tavernier",
                why="+2.2 pts this week. Bank left £0.3m.",
                player_ids=[10, 20],
                urgency="high",
            ),
            DailyMove(
                move_type=MoveType.HOLD,
                summary="Roll the transfer",
                why="Both leave 1 FT.",
                player_ids=[],
                urgency="medium",
            ),
        ],
    )
    out = reconcile_transfer_advice(
        advice,
        weekly,
        affordable_transfers=[cand],
        owned_ids=[10],
        captain_id=1,
        vice_id=2,
        projections={},
        gameweeks=[4],
        weights=[1.0],
        season_rules=load_season_rules_2026_27(),
    )
    out = _apply_advice_lint(out, weekly, free_transfers=0)
    assert all(m.move_type != MoveType.TRANSFER for m in out.suggested_moves)
    hold = next(m for m in out.suggested_moves if m.move_type == MoveType.HOLD)
    assert "−4" in hold.summary or "-4" in hold.summary or "−4" in hold.why
    issues = lint_predeadline_advice(
        weekly_plan=weekly,
        suggested_moves=out.suggested_moves,
        free_transfers=0,
    )
    assert not any(i.code == "roll_with_transfer_move" for i in issues)


def test_finalize_transfer_discloses_hit_on_spend() -> None:
    cand = _anderson_tavernier()
    weekly = {
        "ok": True,
        "best_affordable": cand.as_payload(),
        "chips": [],
        "transfer_decision": {
            "action": "transfer",
            "reason": "Take the 4-point hit: horizon clears the bar.",
            "free_transfers_now": 0,
            "hit_points_if_transfer": 4,
        },
    }
    advice = DailyAdvice(
        plan_action=PlanAction.REVISE,
        headline="Sell Anderson for Tavernier",
        suggested_moves=[
            DailyMove(
                move_type=MoveType.TRANSFER,
                summary="Sell Anderson for Tavernier",
                why="Raises projected points this week (4.3 vs 2.1).",
                player_ids=[10, 20],
                urgency="high",
            ),
            DailyMove(
                move_type=MoveType.HOLD,
                summary="Roll the FT",
                why="Bank the FT for next week.",
                player_ids=[],
                urgency="low",
            ),
        ],
    )
    out = reconcile_transfer_advice(
        advice,
        weekly,
        affordable_transfers=[cand],
        owned_ids=[10],
        captain_id=1,
        vice_id=2,
        projections={},
        gameweeks=[4],
        weights=[1.0],
        season_rules=load_season_rules_2026_27(),
    )
    assert all(m.move_type != MoveType.HOLD for m in out.suggested_moves)
    transfer = next(m for m in out.suggested_moves if m.move_type == MoveType.TRANSFER)
    assert "−4" in transfer.summary or "hit" in transfer.why.lower()
    issues = lint_predeadline_advice(
        weekly_plan=weekly,
        suggested_moves=out.suggested_moves,
        free_transfers=0,
    )
    assert issues == []


def test_render_roll_path_mentions_hit_cost() -> None:
    cand = _anderson_tavernier()
    weekly = {
        "ok": True,
        "formation": "3-4-3",
        "xi": [{"web_name": "Anderson", "xp_next": 2.1}],
        "bench": [],
        "model_captain": {"web_name": "Odegaard", "xp_next": 4.8},
        "model_vice": {"web_name": "Raya", "xp_next": 3.4},
        "best_affordable": cand.as_payload(),
        "also_considered": [{**cand.as_payload(), "picked": True}],
        "chips": [],
        "transfer_decision": {
            "action": "roll",
            "reason": "0 FT so Anderson→Tavernier costs −4; net -1.8 this week.",
            "free_transfers_now": 0,
            "free_transfers_if_roll": 1,
            "free_transfers_if_transfer": 1,
            "hit_points_if_transfer": 4,
        },
    }
    report = DailyReport(
        gameweek=4,
        plan_action="keep",
        headline="Hold — Anderson→Tavernier costs −4 with 0 FT (net -1.8)",
        what_changed=[],
        attention_triggers=[],
        suggested_moves=[
            {
                "move_type": "hold",
                "summary": "Hold — Anderson → Tavernier would cost −4 (net -1.8 this week)",
                "why": "Gross +2.2 before a −4 hit is net -1.8.",
            }
        ],
        uncertainty=[],
        warnings=[],
        sources=[],
        model_meta={},
        executability="EXECUTABLE",
        used_live_ai=False,
        weekly_plan=weekly,
    )
    text = render_daily_text(report)
    assert "−4" in text
    issues = lint_predeadline_advice(
        weekly_plan=weekly,
        suggested_moves=report.suggested_moves,
        report_text=text,
        free_transfers=0,
    )
    assert issues == []
