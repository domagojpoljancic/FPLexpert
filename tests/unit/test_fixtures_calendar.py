"""Fixture calendar tests."""

from __future__ import annotations

from fpl_agent.strategy.fixtures_calendar import calendar_for_horizon, fixture_counts_by_club_gw


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
