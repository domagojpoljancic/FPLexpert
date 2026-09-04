"""Double/blank gameweek detection from fixtures (+ labelled priors beyond the feed)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class GameweekFixtureSummary:
    gameweek: int
    clubs_with_fixtures: int
    double_clubs: tuple[int, ...]
    blank_clubs: tuple[int, ...]
    is_double_gw: bool
    is_blank_gw: bool


PriorKind = Literal["dgw", "bgw"]


@dataclass(frozen=True)
class GameweekFixturePrior:
    """Likely-but-unscheduled DGW/BGW. Never treated as a confirmed fixture."""

    gameweek: int
    kind: PriorKind
    confidence: float
    rationale: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("prior confidence must be in [0, 1]")
        if self.kind not in {"dgw", "bgw"}:
            raise ValueError(f"prior kind must be dgw|bgw, got {self.kind!r}")

    def as_payload(self) -> dict[str, Any]:
        conf = round(float(self.confidence), 3)
        label = f"PRIOR {self.kind.upper()} GW{self.gameweek} (confidence {conf:.2f})"
        return {
            "gameweek": int(self.gameweek),
            "kind": self.kind,
            "confidence": conf,
            "status": "prior",
            "label": label,
            "rationale": self.rationale,
            "is_confirmed": False,
        }


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


def confirmed_payload(row: GameweekFixtureSummary) -> dict[str, Any]:
    return {
        "gameweek": row.gameweek,
        "clubs_with_fixtures": row.clubs_with_fixtures,
        "double_clubs": list(row.double_clubs),
        "blank_clubs": list(row.blank_clubs),
        "is_double_gw": row.is_double_gw,
        "is_blank_gw": row.is_blank_gw,
        "status": "confirmed",
        "is_confirmed": True,
    }


def attach_priors(
    confirmed: list[GameweekFixtureSummary],
    priors: list[GameweekFixturePrior],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split confirmed feed rows from labelled priors.

    Priors never override a feed-confirmed DGW/BGW on the same gameweek/kind.
    """
    confirmed_rows = [confirmed_payload(row) for row in sorted(confirmed, key=lambda r: r.gameweek)]
    flagged = {
        (row.gameweek, "dgw")
        for row in confirmed
        if row.is_double_gw
    } | {
        (row.gameweek, "bgw")
        for row in confirmed
        if row.is_blank_gw
    }
    prior_rows: list[dict[str, Any]] = []
    for prior in sorted(priors, key=lambda p: (p.gameweek, p.kind)):
        if (prior.gameweek, prior.kind) in flagged:
            continue
        prior_rows.append(prior.as_payload())
    return confirmed_rows, prior_rows
