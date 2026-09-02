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
    assert "## TLDR" in text
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
    assert text.index("## TLDR") < text.index("## Why")
    assert text.index("## Why") < text.index("## Sources checked")
    assert "Injuries and bans" in text
    assert "fantasyfootballscout.co.uk/injuries" in text
    assert "returned this run" in text
    assert "not returned this run" in text
    assert "FPL GW1 team news" in text
    assert "No material injury news" in text
    assert "Why: No injury news and no affordable upgrade beat rolling." in text
    assert "you can act" in text
    assert text.index("## TLDR") < text.index("## Do this")


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
            "best_affordable": None,
            "best_stretch": {
                "out_name": "Thiago",
                "in_name": "Haaland",
                "bank_shortfall_tenths": 20,
            },
            "chips": [
                {"kind": "3xc", "action": "hold", "available": True, "reason": "not an outlier week"},
            ],
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
    assert "## Model decisions" in text
    assert "### This week (GW3)" in text
    assert "### Horizon (model XI xP by gameweek)" in text
    assert "B.Fernandes" in text
    assert "Roll the FT" in text
    assert "Haaland" in text
    assert "Last week (GW2 actuals)" in text
    assert "hold 3xc" in text or "Chips: hold" in text
    assert text.index("## TLDR") < text.index("## Model decisions")
    assert text.index("## Model decisions") < text.index("## Do this")


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
