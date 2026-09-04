"""Plan explainer doc: determinism, locked primary, Mermaid, no secrets."""

from __future__ import annotations

from fpl_agent.daily import DailyReport
from fpl_agent.reporting.plan_doc import locked_primary, render_plan_doc, write_plan_doc


def _fixture_report() -> DailyReport:
    return DailyReport(
        gameweek=3,
        plan_action="revise",
        headline="Sell Shaw for De Cuyper",
        what_changed=[],
        attention_triggers=[],
        suggested_moves=[
            {
                "move_type": "transfer",
                "summary": "Sell Shaw for De Cuyper",
                "player_ids": [423, 115],
            }
        ],
        uncertainty=[],
        warnings=[],
        sources=[],
        model_meta={},
        executability="EXECUTABLE",
        used_live_ai=False,
        weekly_plan={
            "ok": True,
            "best_affordable": {
                "out_id": 423,
                "in_id": 115,
                "out_name": "Shaw",
                "in_name": "De Cuyper",
                "sell_tenths": 45,
                "buy_tenths": 47,
                "bank_after_tenths": 3,
                "delta_weighted_xp": 5.6,
                "delta_gw_xp": 3.4,
                "reason": "Sell Shaw for De Cuyper. Bank left: £0.3m.",
            },
            "after_transfer": {
                "out_id": 423,
                "in_id": 115,
                "out_name": "Shaw",
                "in_name": "De Cuyper",
            },
            "horizon_impact": {
                "by_gw": [
                    {"gw": 5, "hold_xi_xp": 25.0, "after_xi_xp": 26.0, "delta_xp": 1.0},
                    {"gw": 3, "hold_xi_xp": 40.0, "after_xi_xp": 43.4, "delta_xp": 3.4},
                    {"gw": 4, "hold_xi_xp": 26.0, "after_xi_xp": 27.0, "delta_xp": 1.0},
                ],
                "weighted_delta": 5.6,
                "reason": "Adds +3.4 pts this GW and keeps paying later.",
            },
            "transfer_decision": {
                "action": "transfer",
                "reason": "Spend the FT: +5.6 horizon xP clears the bar.",
                "free_transfers_now": 1,
                "free_transfers_if_roll": 2,
                "free_transfers_if_transfer": 1,
                "ft_banking_penalty": 0.35,
                "net_value_after_ft_penalty": 5.25,
                "deferred_upside": 4.49,
            },
            "chips": [
                {
                    "kind": "wildcard",
                    "action": "hold",
                    "available": True,
                    "reason": "Squad healthy enough to keep Wildcard.",
                },
                {
                    "kind": "3xc",
                    "action": "hold",
                    "available": True,
                    "reason": "Captain ceiling not an outlier.",
                },
            ],
            "fixture_calendar": [
                {
                    "gameweek": 4,
                    "is_double_gw": False,
                    "is_blank_gw": False,
                    "clubs_with_fixtures": 20,
                },
                {
                    "gameweek": 3,
                    "is_double_gw": False,
                    "is_blank_gw": False,
                    "clubs_with_fixtures": 20,
                },
            ],
        },
    )


def test_render_plan_doc_is_deterministic() -> None:
    report = _fixture_report()
    a = render_plan_doc(report)
    b = render_plan_doc(report)
    assert a == b


def test_render_plan_doc_matches_locked_primary_and_has_mermaid() -> None:
    report = _fixture_report()
    text = render_plan_doc(report)
    primary = locked_primary(report.weekly_plan)
    assert primary["out_name"] == "Shaw"
    assert primary["in_name"] == "De Cuyper"
    assert "Shaw" in text and "De Cuyper" in text
    assert "```mermaid" in text
    # One section / paragraph per manager question (M0 surface/explain set).
    assert "## Why this move over the next weeks" in text
    assert "## Spend now vs bank the free transfer" in text
    assert "## Bank and value after the move" in text
    assert "## Confirmed DGW / BGW in the horizon" in text
    assert "## DGW / BGW priors (not confirmed)" in text
    assert "## Chip timing" in text
    assert "Bank vs spend verdict" in text
    # Unsorted by_gw input must render GW3 before GW5.
    assert text.index("| 3 |") < text.index("| 5 |")


def test_render_plan_doc_no_secret_leak() -> None:
    report = _fixture_report()
    text = render_plan_doc(report)
    assert "FPL_PRIVATE_STATE_B64" not in text
    assert "data/private-state" not in text
    assert "private-state/current" not in text


def test_write_plan_doc_stable_path(tmp_path) -> None:
    report = _fixture_report()
    path = write_plan_doc(report, root=tmp_path)
    assert path.name == "plan-gw3.md"
    assert path.read_text(encoding="utf-8") == render_plan_doc(report)
