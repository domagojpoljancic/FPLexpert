"""Expected-points model used by pre-deadline (`xp-v2`).

Preseason uses last-season minutes/starts. After GW1 lockdown it switches to
starts / finished gameweeks and an xG/xA adjustment. Constants are transparent
defaults, not validated football truth. See docs/projection-methodology.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

PRESEASON_MODEL_VERSION = "xp-v2"

# Fixture difficulty rating (1 easy .. 5 hard) -> multiplier.
ATTACK_FDR_MULTIPLIER: dict[int, float] = {1: 1.20, 2: 1.10, 3: 1.00, 4: 0.90, 5: 0.80}
DEFENCE_FDR_MULTIPLIER: dict[int, float] = {1: 1.30, 2: 1.15, 3: 1.00, 4: 0.85, 5: 0.72}

HOME_MULTIPLIER = 1.05
AWAY_MULTIPLIER = 0.95

# Expected points per 90 implied by price when history is thin, by position.
# Anchored on "price encodes market expectation"; deliberately conservative.
PRICE_PRIOR_INTERCEPT: dict[int, float] = {1: 1.6, 2: 1.5, 3: 1.2, 4: 1.2}
PRICE_PRIOR_SLOPE_PER_TENTH: dict[int, float] = {1: 0.024, 2: 0.030, 3: 0.036, 4: 0.032}

# Shrinkage strength (in "90s played") toward the price prior.
SHRINKAGE_90S = 12.0

# Weight given to FPL's published ep_next for the next gameweek.
EP_NEXT_BLEND = 0.35
EP_NEXT_BLEND_IN_SEASON = 0.45

# FPL attacking points for a goal, by element_type.
GOAL_POINTS = {1: 6.0, 2: 6.0, 3: 5.0, 4: 4.0}

MINUTES_IF_START = 78.0
MINUTES_IF_SUB = 18.0
LEAGUE_GAMES = 38.0


@dataclass(frozen=True)
class PlayerProjection:
    player_id: int
    web_name: str
    team_id: int
    element_type: int
    price_tenths: int
    p_start: float
    expected_minutes: float
    points_per_90: float
    xp_by_gw: tuple[float, ...]
    weighted_xp: float
    availability_note: str = ""
    warnings: tuple[str, ...] = field(default_factory=tuple)


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def availability_factor(element: dict[str, Any]) -> tuple[float, str]:
    """Return (multiplier, note). Unavailable players are excluded upstream."""
    status = str(element.get("status") or "a")
    chance = element.get("chance_of_playing_next_round")
    if status in {"u", "n"}:
        return 0.0, "unavailable"
    if status == "i":
        return 0.0, "injured"
    if status == "s":
        return 0.0, "suspended"
    if chance is not None:
        pct = _f(chance) / 100.0
        if pct <= 0.0:
            return 0.0, "ruled out"
        if pct < 1.0:
            return pct, f"{int(_f(chance))}% chance of playing"
    if status == "d":
        return 0.75, "doubtful"
    return 1.0, ""


def price_prior_per_90(element_type: int, price_tenths: int) -> float:
    intercept = PRICE_PRIOR_INTERCEPT.get(element_type, 1.2)
    slope = PRICE_PRIOR_SLOPE_PER_TENTH.get(element_type, 0.03)
    return intercept + slope * max(0, price_tenths - 40)


def finished_gameweeks(bootstrap: dict[str, Any]) -> int:
    """Count official finished events. 0 means preseason / before GW1 lockdown."""
    return sum(1 for event in (bootstrap.get("events") or []) if event.get("finished"))


def apply_xg_adjustment(element: dict[str, Any], pp90: float) -> tuple[float, tuple[str, ...]]:
    """Move pp90 toward xGI when finishing has diverged from underlying chance."""
    warnings: list[str] = []
    minutes = _f(element.get("minutes"))
    element_type = int(element.get("element_type", 3))
    pen_order = element.get("penalties_order")
    if minutes < 45:
        if pen_order == 1:
            warnings.append("pen_taker_prior")
            return pp90 + 0.20, tuple(warnings)
        return pp90, ()
    nineties = minutes / 90.0
    xg = _f(element.get("expected_goals"))
    xa = _f(element.get("expected_assists"))
    if xg + xa <= 0:
        return pp90, ()
    goal_pts = GOAL_POINTS.get(element_type, 4.0)
    adj = 0.5 * (
        ((xg - _f(element.get("goals_scored"))) / nineties) * goal_pts
        + ((xa - _f(element.get("assists"))) / nineties) * 3.0
    )
    adj = max(-1.2, min(1.2, adj))
    if abs(adj) >= 0.05:
        warnings.append("xg_adjustment")
    return pp90 + adj, tuple(warnings)


def points_per_90_estimate(element: dict[str, Any]) -> tuple[float, tuple[str, ...]]:
    """Shrink observed per-90 scoring toward a price prior, then apply xGI."""
    warnings: list[str] = []
    minutes = _f(element.get("minutes"))
    total_points = _f(element.get("total_points"))
    element_type = int(element.get("element_type", 3))
    price = int(element.get("now_cost", 45))

    prior = price_prior_per_90(element_type, price)
    nineties = minutes / 90.0
    if nineties <= 0:
        warnings.append("no minutes; price prior only")
        pp90 = prior
    else:
        observed = total_points / nineties
        pp90 = (nineties * observed + SHRINKAGE_90S * prior) / (nineties + SHRINKAGE_90S)
        if nineties < 10:
            warnings.append("small minutes sample")
    adjusted, xg_warn = apply_xg_adjustment(element, pp90)
    return adjusted, tuple(warnings) + xg_warn


def start_probability(
    element: dict[str, Any],
    *,
    games_played: int = 0,
) -> tuple[float, tuple[str, ...]]:
    """Start probability.

    Preseason (`games_played == 0`) uses last-season starts / 38.
    In-season uses starts / finished gameweeks so a #1 GK with 2/2 starts is
    not treated as a backup (the /38 bug).
    """
    warnings: list[str] = []
    starts = _f(element.get("starts"))
    minutes = _f(element.get("minutes"))
    price = int(element.get("now_cost", 45))
    element_type = int(element.get("element_type", 3))

    price_prior = min(0.85, max(0.20, (price - 40) / 60.0 + 0.35))

    if games_played >= 1:
        warnings.append("in_season_minutes")
        if minutes <= 0:
            cap = 0.10 if games_played >= 2 else 0.25
            return min(price_prior, cap), tuple(warnings + ["no_minutes_this_season"])
        observed = min(1.0, starts / float(games_played))
        if element_type == 1:
            if starts >= games_played:
                return 0.95, tuple(warnings)
            if starts <= 0:
                return 0.08, tuple(warnings + ["backup_gk"])
            return max(0.20, min(0.90, observed)), tuple(warnings)
        weight = min(0.85, games_played / 6.0)
        estimate = weight * observed + (1.0 - weight) * price_prior
        if starts >= games_played:
            estimate = max(estimate, 0.80)
        return max(0.05, min(0.97, estimate)), tuple(warnings)

    if minutes <= 0:
        warnings.append("no prior-season minutes; start probability from price")
        return price_prior, tuple(warnings)

    observed = min(1.0, starts / LEAGUE_GAMES)
    weight = min(1.0, starts / 20.0)
    estimate = weight * observed + (1 - weight) * price_prior
    if element_type == 1:
        estimate = 0.95 if observed >= 0.6 else min(estimate, 0.35)
    return max(0.02, min(0.97, estimate)), tuple(warnings)


def team_fixtures_by_gw(
    fixtures: list[dict[str, Any]],
    gameweeks: list[int],
) -> dict[int, dict[int, list[tuple[int, bool]]]]:
    """Map team_id -> gameweek -> list of (difficulty, is_home)."""
    out: dict[int, dict[int, list[tuple[int, bool]]]] = {}
    wanted = set(gameweeks)
    for fixture in fixtures:
        event = fixture.get("event")
        if event is None or int(event) not in wanted:
            continue
        gw = int(event)
        home = int(fixture["team_h"])
        away = int(fixture["team_a"])
        out.setdefault(home, {}).setdefault(gw, []).append(
            (int(fixture.get("team_h_difficulty", 3)), True)
        )
        out.setdefault(away, {}).setdefault(gw, []).append(
            (int(fixture.get("team_a_difficulty", 3)), False)
        )
    return out


def _defensive_share(element_type: int) -> float:
    """Fraction of a player's points that depend on clean sheets / defensive work."""
    return {1: 0.75, 2: 0.55, 3: 0.20, 4: 0.05}.get(element_type, 0.2)


def project_player(
    element: dict[str, Any],
    *,
    fixtures_by_gw: dict[int, list[tuple[int, bool]]],
    gameweeks: list[int],
    weights: list[float],
    games_played: int = 0,
) -> PlayerProjection:
    element_type = int(element.get("element_type", 3))
    price = int(element.get("now_cost", 45))
    team_id = int(element.get("team", 0))

    avail, note = availability_factor(element)
    per_90, warn_pts = points_per_90_estimate(element)
    p_start, warn_min = start_probability(element, games_played=games_played)
    p_start *= avail

    p_sub = min(0.25, (1.0 - p_start) * 0.3) if avail > 0 else 0.0
    expected_minutes = p_start * MINUTES_IF_START + p_sub * MINUTES_IF_SUB

    def_share = _defensive_share(element_type)
    att_share = 1.0 - def_share

    xp_by_gw: list[float] = []
    for gw in gameweeks:
        gw_total = 0.0
        for difficulty, is_home in fixtures_by_gw.get(gw, []):
            att_mult = ATTACK_FDR_MULTIPLIER.get(difficulty, 1.0)
            def_mult = DEFENCE_FDR_MULTIPLIER.get(difficulty, 1.0)
            venue = HOME_MULTIPLIER if is_home else AWAY_MULTIPLIER
            fixture_mult = (att_share * att_mult + def_share * def_mult) * venue
            gw_total += per_90 * (expected_minutes / 90.0) * fixture_mult
        xp_by_gw.append(gw_total)

    ep_next = _f(element.get("ep_next"))
    if xp_by_gw and ep_next > 0 and avail > 0:
        blend = EP_NEXT_BLEND_IN_SEASON if games_played >= 1 else EP_NEXT_BLEND
        xp_by_gw[0] = (1 - blend) * xp_by_gw[0] + blend * ep_next

    weighted = sum(w * x for w, x in zip(weights, xp_by_gw, strict=True))
    return PlayerProjection(
        player_id=int(element["id"]),
        web_name=str(element.get("web_name", "")),
        team_id=team_id,
        element_type=element_type,
        price_tenths=price,
        p_start=p_start,
        expected_minutes=expected_minutes,
        points_per_90=per_90,
        xp_by_gw=tuple(xp_by_gw),
        weighted_xp=weighted,
        availability_note=note,
        warnings=tuple(warn_pts) + tuple(warn_min),
    )


def project_all(
    *,
    bootstrap: dict[str, Any],
    fixtures: list[dict[str, Any]],
    gameweeks: list[int],
    weights: list[float],
) -> list[PlayerProjection]:
    by_team = team_fixtures_by_gw(fixtures, gameweeks)
    played = finished_gameweeks(bootstrap)
    out: list[PlayerProjection] = []
    for element in bootstrap.get("elements") or []:
        if element.get("removed"):
            continue
        team_fixtures = by_team.get(int(element.get("team", 0)), {})
        out.append(
            project_player(
                element,
                fixtures_by_gw=team_fixtures,
                gameweeks=gameweeks,
                weights=weights,
                games_played=played,
            )
        )
    out.sort(key=lambda p: (-p.weighted_xp, p.player_id))
    return out
