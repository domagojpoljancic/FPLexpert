"""Daily assistant and evidence tests."""

from __future__ import annotations

from datetime import UTC, datetime

from fpl_agent.evidence.news import claims_from_bootstrap_news, source_tier_for_url
from fpl_agent.llm.client import (
    DailyAdvice,
    DailyMove,
    FakeOpenAIClient,
    MoveType,
    PlanAction,
    validate_daily_advice,
)


def test_reddit_is_community_tier() -> None:
    assert source_tier_for_url("https://www.reddit.com/r/FantasyPL/comments/x") == "community"
    assert source_tier_for_url("https://www.premierleague.com/news/1") == "official"
    assert source_tier_for_url("https://www.fantasyfootballscout.co.uk/team-news") == "established"


def test_bootstrap_news_claim_for_injured_squad_player() -> None:
    claims = claims_from_bootstrap_news(
        elements=[
            {
                "id": 10,
                "team": 1,
                "status": "i",
                "news": "Hamstring injury - Expected back in a week",
                "chance_of_playing_next_round": 0,
            },
            {"id": 11, "team": 1, "status": "a", "news": "", "chance_of_playing_next_round": 100},
        ],
        player_ids={10, 11},
        now=datetime.now(UTC),
    )
    assert len(claims) == 1
    assert claims[0].player_ids == [10]
    assert claims[0].proposed_override == {"availability": "out"}


def test_validate_daily_drops_unknown_players_and_sources() -> None:
    advice = DailyAdvice(
        plan_action=PlanAction.REVISE,
        headline="Test",
        suggested_moves=[
            DailyMove(
                move_type=MoveType.TRANSFER,
                summary="Sell unknown",
                player_ids=[1, 999],
                cited_source_ids=["ok", "bad"],
            )
        ],
        cited_source_ids=["ok", "bad"],
        do_not_transfer_just_because_ran=False,
    )
    cleaned = validate_daily_advice(
        advice,
        allowed_player_ids={1},
        allowed_source_ids={"ok"},
    )
    assert cleaned.suggested_moves[0].player_ids == [1]
    assert cleaned.suggested_moves[0].cited_source_ids == ["ok"]
    assert cleaned.cited_source_ids == ["ok"]
    assert cleaned.do_not_transfer_just_because_ran is True
    assert any("unknown_player" in w for w in cleaned.warnings)


def test_fake_daily_does_not_churn_without_triggers() -> None:
    client = FakeOpenAIClient()
    advice, meta = client.synthesize_daily({"attention_triggers": [], "what_changed": [], "sources": []})
    assert advice.plan_action == PlanAction.KEEP
    assert meta.fallback is True


def test_predeadline_report_explains_insufficient() -> None:
    from datetime import timedelta

    from fpl_agent.daily import DailyReport, render_daily_text

    report = DailyReport(
        gameweek=1,
        plan_action="watch",
        headline="Watch a defender",
        what_changed=[],
        attention_triggers=["low start chance"],
        suggested_moves=[],
        uncertainty=[],
        warnings=["private squad stale", "private squad stale", "keep FT"],
        sources=[],
        model_meta={"model": "gpt-5-2025-08-07", "web_search_calls": 0},
        executability="INSUFFICIENT",
        used_live_ai=True,
        squad_as_of=datetime(2026, 8, 15, 20, 39, tzinfo=UTC),
        squad_max_age_hours=24,
        timezone="Europe/Zagreb",
    )
    text = render_daily_text(report)
    assert "not executable" in text.lower()
    assert "24 hours" in text
    assert "gpt-5-2025-08-07" in text
    assert "Web searches actually made: 0" in text
    assert text.count("private squad stale") == 0
    assert "keep FT" in text
    assert "## TLDR" not in text
    assert "## Do this" in text
    assert datetime.now(UTC) - report.squad_as_of > timedelta(hours=24)


def test_report_lists_openai_pages_and_hubs() -> None:
    from fpl_agent.daily import DailyReport, render_daily_text

    report = DailyReport(
        gameweek=1,
        plan_action="keep",
        headline="Hold FT",
        what_changed=[],
        attention_triggers=[],
        suggested_moves=[{"urgency": "low", "move_type": "hold", "summary": "Roll the FT", "why": "No injury news and no affordable upgrade beat rolling."}],
        uncertainty=["Pressers still to come"],
        warnings=[],
        sources=[
            {
                "claim_id": "web-abc",
                "tier": "established",
                "url": "https://www.fantasyfootballscout.co.uk/injuries",
                "title": "Injuries and bans",
            }
        ],
        model_meta={"model": "gpt-5", "web_search_calls": 4},
        executability="EXECUTABLE",
        used_live_ai=True,
        tldr=["Hold the FT", "Keep Bruno captain"],
        detail="No material injury news on the XI.",
        search_queries=["FPL GW1 team news", "O'Nien Sunderland"],
        suggested_hubs=[
            {"name": "Fantasy Football Scout", "url": "https://www.fantasyfootballscout.co.uk/"},
            {"name": "r/FantasyPL", "url": "https://www.reddit.com/r/FantasyPL/"},
        ],
    )
    text = render_daily_text(report)
    assert text.index("## Do this") < text.index("## Why")
    assert text.index("## Why") < text.index("## Sources")
    assert "Injuries and bans" in text
    assert "fantasyfootballscout.co.uk/injuries" in text
    assert "No material injury news" in text
    assert "No injury news and no affordable upgrade beat rolling." in text
    assert "you can act" in text
    assert "## Notes" not in text
    assert "returned this run" not in text


def test_report_includes_weekly_model_decisions() -> None:
    from fpl_agent.daily import DailyReport, render_daily_text

    report = DailyReport(
        gameweek=3,
        plan_action="keep",
        headline="Hold",
        what_changed=[],
        attention_triggers=[],
        suggested_moves=[],
        uncertainty=[],
        warnings=[],
        sources=[],
        model_meta={},
        executability="EXECUTABLE",
        used_live_ai=False,
        weekly_plan={
            "ok": True,
            "formation": "3-5-2",
            "model_captain": {"web_name": "B.Fernandes", "xp_next": 4.2, "p_start": 0.95},
            "model_vice": {"web_name": "Raya", "xp_next": 3.1, "p_start": 0.95},
            "xi": [{"web_name": "Raya"}, {"web_name": "B.Fernandes"}],
            "bench": [{"web_name": "O'Nien", "p_start": 0.4}],
            "horizon": [
                {"gw": 3, "xi_xp": 42.1, "captain": "B.Fernandes", "captain_xp": 4.2},
                {"gw": 4, "xi_xp": 38.0, "captain": "Haaland", "captain_xp": 5.1},
            ],
            "best_affordable": {
                "out_name": "O'Nien",
                "in_name": "Egan",
                "in_starts": True,
                "xi_drop_name": "Virgil",
            },
            "after_transfer": {
                "out_name": "O'Nien",
                "in_name": "Egan",
                "xi_drop_name": "Virgil",
                "formation": "3-5-2",
                "xi": [{"web_name": "Raya"}, {"web_name": "Egan"}, {"web_name": "B.Fernandes"}],
                "bench": [{"web_name": "Virgil", "p_start": 0.84}],
                "model_captain": {"web_name": "B.Fernandes", "xp_next": 4.2, "p_start": 0.95},
                "model_vice": {"web_name": "Raya", "xp_next": 3.1, "p_start": 0.95},
            },
            "best_stretch": {
                "out_name": "Thiago",
                "in_name": "Haaland",
                "bank_shortfall_tenths": 20,
            },
            "also_considered": [
                {
                    "in_name": "Egan",
                    "element_type": 2,
                    "picked": True,
                    "reason": (
                        "Egan is likelier to start than O'Nien (80% vs 40%) "
                        "and should add more to the XI this week (+2.8 pts this week; +4.6 over the next few GWs)."
                    ),
                },
                {
                    "in_name": "Ajayi",
                    "element_type": 2,
                    "picked": False,
                    "reason": (
                        "adds less this week than Egan but looks stronger over the next few gameweeks. "
                        "It would sell Virgil instead of O'Nien. (+3.4 pts this week; +3.5 over the next few GWs)."
                    ),
                },
                {
                    "in_name": "De Cuyper",
                    "element_type": 2,
                    "picked": False,
                    "reason": "is close to Egan this week over a similar run of gameweeks. (+2.5 pts this week).",
                },
            ],
            "chips": [
                {"kind": "3xc", "action": "hold", "available": True, "reason": "not an outlier week"},
            ],
            "horizon_impact": {
                "by_gw": [
                    {"gw": 3, "hold_xi_xp": 40.0, "after_xi_xp": 42.8, "delta_xp": 2.8},
                    {"gw": 4, "hold_xi_xp": 38.0, "after_xi_xp": 40.0, "delta_xp": 2.0},
                ],
                "weighted_delta": 4.6,
                "reason": "Adds +2.8 pts to the XI this GW and keeps paying later (GW4 +2.0; +4.6 weighted overall).",
            },
            "transfer_decision": {
                "action": "transfer",
                "reason": "Spend the FT: +4.6 horizon xP clears the bar (+2.8 this GW).",
                "free_transfers_now": 1,
                "free_transfers_if_roll": 2,
                "free_transfers_if_transfer": 1,
            },
            "previous_scorecard": {
                "gameweek": 2,
                "model_xi_points": 55,
                "model_captain_points": 16,
                "model_captain_name": "B.Fernandes",
                "transfer_delta": 3,
                "transfer_out_points": 2,
                "transfer_in_points": 5,
            },
        },
    )
    text = render_daily_text(report)
    assert "## This week" in text
    assert "Egan" in text
    assert "After **O'Nien → Egan**" in text
    assert "Virgil drops out of the XI" in text
    assert "Compared with other affordable defenders:" in text
    assert "**Egan** (recommended)" in text
    assert "Transfer vs hold (XI pts):" in text
    assert "FT timing (Spend FT now):" in text
    assert "Future weeks:" in text
    assert "**Ajayi** (also looked at)" in text
    assert "## Model decisions" not in text
    assert "### Horizon" not in text
    assert "Last week (GW2 actuals)" not in text
    assert "B.Fernandes" in text
    assert "Chips: hold" in text
    assert text.index("## Do this") < text.index("## This week")
    assert text.index("## This week") < text.index("## Why")


def test_apply_news_fail_closed_when_live_search_empty() -> None:
    from fpl_agent.llm.client import NEWS_SEARCH_EMPTY, apply_news_fail_closed

    advice = DailyAdvice(plan_action=PlanAction.KEEP, headline="Hold")
    closed = apply_news_fail_closed(advice, used_live=True, web_search_calls=0, page_count=0)
    assert NEWS_SEARCH_EMPTY in closed.warnings
    assert any("No web pages" in u for u in closed.uncertainty)
    untouched = apply_news_fail_closed(advice, used_live=True, web_search_calls=3, page_count=2)
    assert NEWS_SEARCH_EMPTY not in untouched.warnings
    fake = apply_news_fail_closed(advice, used_live=False, web_search_calls=0, page_count=0)
    assert NEWS_SEARCH_EMPTY not in fake.warnings


def test_report_flags_empty_news_search() -> None:
    from fpl_agent.daily import DailyReport, render_daily_text

    report = DailyReport(
        gameweek=3,
        plan_action="keep",
        headline="Hold",
        what_changed=[],
        attention_triggers=[],
        suggested_moves=[],
        uncertainty=["No web pages were returned this run. Treat injury/line-up claims as unverified; use FPL status fields and supplied xP only."],
        warnings=["news_search_empty"],
        sources=[],
        model_meta={"web_search_calls": 0},
        executability="EXECUTABLE",
        used_live_ai=True,
    )
    text = render_daily_text(report)
    assert "no pages" in text.lower()


def test_reconcile_aligns_weekly_plan_to_llm_transfer(monkeypatch) -> None:
    """LLM may pick another starter candidate; This week must follow Do this."""
    from fpl_agent import daily as daily_mod
    from fpl_agent.daily import DailyReport, reconcile_transfer_advice, render_daily_text
    from fpl_agent.llm.client import DailyAdvice, DailyMove, MoveType, PlanAction
    from fpl_agent.rules.season import load_season_rules_2026_27
    from fpl_agent.strategy.transfers import TransferCandidate

    ajayi = TransferCandidate(
        out_id=356,
        in_id=279,
        out_name="Virgil",
        in_name="Ajayi",
        element_type=2,
        sell_tenths=65,
        buy_tenths=41,
        bank_after_tenths=29,
        bank_shortfall_tenths=0,
        affordable=True,
        delta_weighted_xp=1.3,
        delta_gw_xp=3.5,
        out_p_start=0.84,
        in_p_start=0.8,
        in_starts=True,
        xi_drop_name="Virgil",
    )
    egan = TransferCandidate(
        out_id=539,
        in_id=277,
        out_name="O'Nien",
        in_name="Egan",
        element_type=2,
        sell_tenths=40,
        buy_tenths=40,
        bank_after_tenths=5,
        bank_shortfall_tenths=0,
        affordable=True,
        delta_weighted_xp=4.6,
        delta_gw_xp=2.8,
        out_p_start=0.4,
        in_p_start=0.8,
        in_starts=True,
        xi_drop_name="Tzolis",
    )
    weekly_plan = {
        "ok": True,
        "formation": "3-5-2",
        "best_affordable": ajayi.as_payload(),
        "after_transfer": {
            "out_id": 356,
            "in_id": 279,
            "out_name": "Virgil",
            "in_name": "Ajayi",
            "xi_drop_name": "Virgil",
            "formation": "3-5-2",
            "xi": [{"web_name": "Ajayi"}],
            "bench": [],
            "model_captain": {"web_name": "B.Fernandes", "xp_next": 7.5},
            "model_vice": {"web_name": "Raya", "xp_next": 3.0},
        },
        "also_considered": [
            {**ajayi.as_payload(), "picked": True},
            {**egan.as_payload(), "picked": False, "reason": "also looked at"},
        ],
        "xi": [{"web_name": "Virgil"}],
        "bench": [],
        "chips": [],
    }
    advice = DailyAdvice(
        plan_action=PlanAction.REVISE,
        headline="Sell O'Nien for Egan",
        suggested_moves=[
            DailyMove(
                move_type=MoveType.TRANSFER,
                summary="O'Nien to Egan",
                why="Egan starts more often.",
                player_ids=[539, 277],
            )
        ],
    )
    seen: list[TransferCandidate] = []

    def _fake_apply(plan, pick, **_kwargs):
        seen.append(pick)
        assert pick is not None
        plan["best_affordable"] = pick.as_payload()
        plan["after_transfer"] = {
            "out_id": pick.out_id,
            "in_id": pick.in_id,
            "out_name": pick.out_name,
            "in_name": pick.in_name,
            "xi_drop_name": pick.xi_drop_name,
            "formation": "3-5-2",
            "xi": [{"web_name": pick.in_name}],
            "bench": [{"web_name": "Shaw", "p_start": 0.8}],
            "model_captain": {"web_name": "B.Fernandes", "xp_next": 7.5},
            "model_vice": {"web_name": "Raya", "xp_next": 3.0},
        }
        plan["also_considered"] = [
            {**pick.as_payload(), "picked": True},
            {**ajayi.as_payload(), "picked": False, "reason": "also looked at"},
        ]

    monkeypatch.setattr(daily_mod, "apply_transfer_pick_to_weekly_plan", _fake_apply)
    out = reconcile_transfer_advice(
        advice,
        weekly_plan,
        affordable_transfers=[ajayi, egan],
        owned_ids=[1] * 15,
        captain_id=1,
        vice_id=1,
        projections={},
        gameweeks=[3, 4, 5],
        weights=[1.0, 0.8, 0.6],
        season_rules=load_season_rules_2026_27(),
    )
    assert out.suggested_moves[0].player_ids == [539, 277]
    assert seen and seen[0].in_name == "Egan"
    assert weekly_plan["best_affordable"]["in_name"] == "Egan"
    assert weekly_plan["after_transfer"]["out_name"] == "O'Nien"

    report = DailyReport(
        gameweek=3,
        plan_action="revise",
        headline=out.headline,
        what_changed=[],
        attention_triggers=[],
        suggested_moves=[m.model_dump(mode="json") for m in out.suggested_moves],
        uncertainty=[],
        warnings=[],
        sources=[],
        model_meta={},
        executability="EXECUTABLE",
        used_live_ai=True,
        weekly_plan=weekly_plan,
    )
    text = render_daily_text(report)
    assert "O'Nien to Egan" in text
    assert "After **O'Nien → Egan**" in text
    assert "After **Virgil → Ajayi**" not in text


def test_reconcile_snaps_invalid_transfer_to_best_affordable(monkeypatch) -> None:
    from fpl_agent import daily as daily_mod
    from fpl_agent.daily import reconcile_transfer_advice
    from fpl_agent.llm.client import DailyAdvice, DailyMove, MoveType, PlanAction
    from fpl_agent.rules.season import load_season_rules_2026_27
    from fpl_agent.strategy.transfers import TransferCandidate

    ajayi = TransferCandidate(
        out_id=356,
        in_id=279,
        out_name="Virgil",
        in_name="Ajayi",
        element_type=2,
        sell_tenths=65,
        buy_tenths=41,
        bank_after_tenths=29,
        bank_shortfall_tenths=0,
        affordable=True,
        delta_weighted_xp=1.3,
        delta_gw_xp=3.5,
        out_p_start=0.84,
        in_p_start=0.8,
        in_starts=True,
        xi_drop_name="Virgil",
    )
    weekly_plan = {
        "ok": True,
        "best_affordable": ajayi.as_payload(),
        "after_transfer": {
            "out_id": 356,
            "in_id": 279,
            "out_name": "Virgil",
            "in_name": "Ajayi",
            "xi": [{"web_name": "Ajayi"}],
        },
        "also_considered": [],
    }
    advice = DailyAdvice(
        plan_action=PlanAction.REVISE,
        headline="Sell nobody for ghost",
        suggested_moves=[
            DailyMove(
                move_type=MoveType.TRANSFER,
                summary="Ghost transfer",
                why="invented",
                player_ids=[999, 998],
            )
        ],
    )
    monkeypatch.setattr(
        daily_mod,
        "apply_transfer_pick_to_weekly_plan",
        lambda plan, pick, **_k: plan.update({"best_affordable": pick.as_payload() if pick else None}),
    )
    out = reconcile_transfer_advice(
        advice,
        weekly_plan,
        affordable_transfers=[ajayi],
        owned_ids=[1] * 15,
        captain_id=1,
        vice_id=1,
        projections={},
        gameweeks=[3, 4, 5],
        weights=[1.0, 0.8, 0.6],
        season_rules=load_season_rules_2026_27(),
    )
    assert out.suggested_moves[0].player_ids == [356, 279]
    assert "Virgil to Ajayi" in out.suggested_moves[0].summary
    assert any("aligned_transfer_to_best_affordable" in w for w in out.warnings)


def test_reconcile_detects_mislabeled_hold_transfer(monkeypatch) -> None:
    """LLM sometimes tags the transfer as hold while still citing out/in ids."""
    from fpl_agent import daily as daily_mod
    from fpl_agent.daily import DailyReport, reconcile_transfer_advice, render_daily_text
    from fpl_agent.llm.client import DailyAdvice, DailyMove, MoveType, PlanAction
    from fpl_agent.rules.season import load_season_rules_2026_27
    from fpl_agent.strategy.transfers import TransferCandidate

    ajayi = TransferCandidate(
        out_id=356,
        in_id=279,
        out_name="Virgil",
        in_name="Ajayi",
        element_type=2,
        sell_tenths=65,
        buy_tenths=41,
        bank_after_tenths=29,
        bank_shortfall_tenths=0,
        affordable=True,
        delta_weighted_xp=1.3,
        delta_gw_xp=3.5,
        out_p_start=0.84,
        in_p_start=0.8,
        in_starts=True,
        xi_drop_name="Virgil",
    )
    egan = TransferCandidate(
        out_id=539,
        in_id=277,
        out_name="O'Nien",
        in_name="Egan",
        element_type=2,
        sell_tenths=40,
        buy_tenths=40,
        bank_after_tenths=5,
        bank_shortfall_tenths=0,
        affordable=True,
        delta_weighted_xp=4.6,
        delta_gw_xp=2.8,
        out_p_start=0.4,
        in_p_start=0.8,
        in_starts=True,
        xi_drop_name="Tzolis",
    )
    weekly_plan = {
        "ok": True,
        "best_affordable": ajayi.as_payload(),
        "after_transfer": {
            "out_name": "Virgil",
            "in_name": "Ajayi",
            "xi": [{"web_name": "Ajayi"}],
            "model_captain": {"web_name": "B.Fernandes", "xp_next": 7.5},
        },
        "also_considered": [],
        "chips": [],
    }
    advice = DailyAdvice(
        plan_action=PlanAction.REVISE,
        headline="Consider O'Nien to Egan",
        suggested_moves=[
            DailyMove(
                move_type=MoveType.HOLD,
                summary="Consider O'Nien → Egan",
                why="Egan starts more often.",
                player_ids=[539, 277],
            )
        ],
    )

    def _fake_apply(plan, pick, **_kwargs):
        assert pick is not None
        plan["best_affordable"] = pick.as_payload()
        plan["after_transfer"] = {
            "out_id": pick.out_id,
            "in_id": pick.in_id,
            "out_name": pick.out_name,
            "in_name": pick.in_name,
            "xi": [{"web_name": pick.in_name}],
            "model_captain": {"web_name": "B.Fernandes", "xp_next": 7.5},
        }
        plan["also_considered"] = [{**pick.as_payload(), "picked": True}]

    monkeypatch.setattr(daily_mod, "apply_transfer_pick_to_weekly_plan", _fake_apply)
    out = reconcile_transfer_advice(
        advice,
        weekly_plan,
        affordable_transfers=[ajayi, egan],
        owned_ids=[1] * 15,
        captain_id=1,
        vice_id=1,
        projections={},
        gameweeks=[3],
        weights=[1.0],
        season_rules=load_season_rules_2026_27(),
    )
    assert out.suggested_moves[0].move_type == MoveType.TRANSFER
    assert weekly_plan["after_transfer"]["out_name"] == "O'Nien"
    text = render_daily_text(
        DailyReport(
            gameweek=3,
            plan_action="revise",
            headline=out.headline,
            what_changed=[],
            attention_triggers=[],
            suggested_moves=[m.model_dump(mode="json") for m in out.suggested_moves],
            uncertainty=[],
            warnings=[],
            sources=[],
            model_meta={},
            executability="EXECUTABLE",
            used_live_ai=True,
            weekly_plan=weekly_plan,
        )
    )
    assert "transfer: Consider O'Nien" in text or "transfer: O'Nien" in text or "O'Nien → Egan" in text
    assert "After **O'Nien → Egan**" in text
    assert "After **Virgil → Ajayi**" not in text


def test_extract_web_search_trace_collects_queries_and_pages() -> None:
    from fpl_agent.llm.client import extract_web_search_trace

    output = [
        {
            "type": "web_search_call",
            "action": {
                "query": "FPL GW1 injury news",
                "sources": [
                    {
                        "url": "https://www.premierleague.com/en/fantasy-news",
                        "title": "Fantasy News",
                    },
                    {"url": "https://www.premierleague.com/en/fantasy-news"},
                ],
            },
        },
        {
            "type": "message",
            "content": [
                {
                    "type": "output_text",
                    "annotations": [
                        {
                            "type": "url_citation",
                            "url": "https://www.bbc.com/sport/football/fantasy-football",
                            "title": "BBC FPL",
                        }
                    ],
                }
            ],
        },
    ]
    calls, sources, queries = extract_web_search_trace(output)
    assert calls == 1
    assert queries == ["FPL GW1 injury news"]
    urls = [s["url"] for s in sources]
    assert urls == [
        "https://www.premierleague.com/en/fantasy-news",
        "https://www.bbc.com/sport/football/fantasy-football",
    ]
    assert sources[0]["title"] == "Fantasy News"
