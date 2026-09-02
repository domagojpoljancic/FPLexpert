"""Double/blank gameweek detection from fixtures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GameweekFixtureSummary:
    gameweek: int
    clubs_with_fixtures: int
    double_clubs: tuple[int, ...]
    blank_clubs: tuple[int, ...]
    is_double_gw: bool
    is_blank_gw: bool


def fixture_counts_by_club_gw(fixtures: list[dict[str, Any]]) -> dict[int, dict[int, int]]:
    """Map gameweek -> club_id -> fixture count."""
    out: dict[int, dict[int, int]] = {}
    for fixture in fixtures:
        event = fixture.get("event")
        if event is None:
            continue
        gw = int(event)
        home = int(fixture["team_h"])
        away = int(fixture["team_a"])
        out.setdefault(gw, {})
        out[gw][home] = out[gw].get(home, 0) + 1
        out[gw][away] = out[gw].get(away, 0) + 1
    return out


def summarize_gameweek(
    gw: int,
    counts: dict[int, dict[int, int]],
    *,
    all_clubs: set[int] | None = None,
) -> GameweekFixtureSummary:
    by_club = counts.get(gw, {})
    clubs_present = set(by_club)
    if all_clubs:
        blank = tuple(sorted(all_clubs - clubs_present))
        universe = all_clubs
    else:
        blank = ()
        universe = clubs_present
    doubles = tuple(sorted(cid for cid, n in by_club.items() if n >= 2))
    n_clubs = len(clubs_present)
    is_blank = bool(universe) and n_clubs <= max(1, len(universe) // 2)
    is_double = len(doubles) >= max(1, len(universe) // 4) if universe else bool(doubles)
    return GameweekFixtureSummary(
        gameweek=gw,
        clubs_with_fixtures=n_clubs,
        double_clubs=doubles,
        blank_clubs=blank,
        is_double_gw=is_double,
        is_blank_gw=is_blank,
    )


def calendar_for_horizon(
    fixtures: list[dict[str, Any]],
    gameweeks: list[int],
    *,
    all_clubs: set[int] | None = None,
) -> list[GameweekFixtureSummary]:
    counts = fixture_counts_by_club_gw(fixtures)
    return [summarize_gameweek(gw, counts, all_clubs=all_clubs) for gw in gameweeks]
