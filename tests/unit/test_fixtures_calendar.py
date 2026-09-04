"""Fixture calendar tests."""

from __future__ import annotations

from fpl_agent.strategy.fixtures_calendar import (
    GameweekFixturePrior,
    attach_priors,
    calendar_for_horizon,
    fixture_counts_by_club_gw,
)


def test_detect_double_and_blank_gws() -> None:
    fixtures = [
        {"event": 10, "team_h": 1, "team_a": 2},
        {"event": 10, "team_h": 1, "team_a": 3},
        {"event": 10, "team_h": 2, "team_a": 4},
        {"event": 11, "team_h": 5, "team_a": 6},
    ]
    counts = fixture_counts_by_club_gw(fixtures)
    assert counts[10][1] == 2
    cal = calendar_for_horizon(fixtures, [10, 11], all_clubs={1, 2, 3, 4, 5, 6, 7, 8})
    by_gw = {c.gameweek: c for c in cal}
    assert by_gw[10].is_double_gw
    assert 7 in by_gw[10].blank_clubs or 8 in by_gw[10].blank_clubs


def test_priors_labelled_and_distinct_from_confirmed() -> None:
    fixtures = [
        {"event": 10, "team_h": 1, "team_a": 2},
        {"event": 10, "team_h": 1, "team_a": 3},
        {"event": 10, "team_h": 2, "team_a": 4},
        {"event": 11, "team_h": 5, "team_a": 6},
    ]
    confirmed = calendar_for_horizon(
        fixtures, [10, 11], all_clubs={1, 2, 3, 4, 5, 6, 7, 8}
    )
    priors = [
        GameweekFixturePrior(
            gameweek=26,
            kind="dgw",
            confidence=0.55,
            rationale="Historical mid-season cup reshuffle window",
        ),
        # Same GW/kind as feed DGW — must be dropped, not re-labelled confirmed.
        GameweekFixturePrior(gameweek=10, kind="dgw", confidence=0.9, rationale="dup"),
    ]
    conf_rows, prior_rows = attach_priors(confirmed, priors)
    assert all(row["status"] == "confirmed" and row["is_confirmed"] is True for row in conf_rows)
    assert any(row["gameweek"] == 10 and row["is_double_gw"] for row in conf_rows)
    assert len(prior_rows) == 1
    prior = prior_rows[0]
    assert prior["status"] == "prior"
    assert prior["is_confirmed"] is False
    assert prior["kind"] == "dgw"
    assert prior["gameweek"] == 26
    assert "PRIOR" in prior["label"]
    assert prior["confidence"] == 0.55
