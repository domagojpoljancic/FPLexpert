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
    assert "Can you act on transfer advice?" in text
    assert "No — not as executable transfers" in text
    assert "24 hours" in text
    assert "gpt-5-2025-08-07" in text
    assert "Web searches actually made: 0" in text
    assert text.count("private squad stale") == 0
    assert "keep FT" in text
    assert datetime.now(UTC) - report.squad_as_of > timedelta(hours=24)
