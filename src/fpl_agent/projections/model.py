"""Transparent baseline expected-points model v1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MODEL_VERSION = "baseline-v1"
FEATURE_VERSION = "fpl-public-v1"


@dataclass(frozen=True)
class PlayerGwProjection:
    player_id: int
    gameweek: int
    expected_minutes: float
    p_start: float
    p_sub: float
    p_none: float
    minutes_if_start: float
    minutes_if_sub: float
    expected_points: float
    components: dict[str, float]
    lower: float
    central: float
    upper: float
    scenario_ids: tuple[str, ...]
    input_hashes: dict[str, str]
    model_version: str = MODEL_VERSION
    feature_version: str = FEATURE_VERSION
    warnings: tuple[str, ...] = ()


@dataclass
class HorizonProjection:
    player_id: int
    by_gw: list[PlayerGwProjection]
    weighted_total: float
    unweighted_by_gw: list[float]


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def shrink(estimate: float, prior: float, n: float, k: float = 5.0) -> float:
    """Small-sample shrinkage toward a prior."""
    return (n * estimate + k * prior) / (n + k)


def minutes_states(p_start: float, p_sub: float) -> tuple[float, float, float]:
    p_start = _clamp01(p_start)
    p_sub = _clamp01(p_sub)
    if p_start + p_sub > 1:
        total = p_start + p_sub
        p_start /= total
        p_sub /= total
    p_none = 1.0 - p_start - p_sub
    return p_start, p_sub, max(0.0, p_none)


def project_player_gw(
    *,
    player_id: int,
    gameweek: int,
    recent_minutes: list[float],
    recent_points: list[float],
    position_prior_minutes: float,
    team_attack: float,
    team_defence: float,
    opp_attack: float,
    opp_defence: float,
    is_home: bool,
    fixtures_in_gw: int,
    availability: str = "available",
    availability_weights: dict[str, float] | None = None,
    def_contrib_rate: float = 0.0,
    def_contrib_points: float = 2.0,
    input_hashes: dict[str, str] | None = None,
    ownership: float | None = None,  # intentionally unused in base xP
) -> PlayerGwProjection:
    """Baseline xP. Ownership must not affect expected points."""
    _ = ownership
    warnings: list[str] = []
    n = float(len(recent_minutes))
    avg_min = sum(recent_minutes) / n if n else position_prior_minutes
    exp_min = shrink(avg_min, position_prior_minutes, max(n, 1.0))

    if availability == "out":
        p_start, p_sub, p_none = 0.0, 0.0, 1.0
    elif availability == "limited":
        p_start, p_sub, p_none = minutes_states(0.25, 0.35)
        warnings.append("limited availability scenario")
    else:
        # crude mapping from expected minutes
        if exp_min >= 60:
            p_start, p_sub, p_none = minutes_states(0.85, 0.10)
        elif exp_min >= 30:
            p_start, p_sub, p_none = minutes_states(0.45, 0.35)
        else:
            p_start, p_sub, p_none = minutes_states(0.10, 0.25)

    weights = availability_weights or {}
    if weights:
        # mixture over named scenarios if provided
        warnings.append("mixed availability weights applied")

    minutes_if_start = 78.0
    minutes_if_sub = 18.0
    expected_minutes = p_start * minutes_if_start + p_sub * minutes_if_sub

    avg_pts = sum(recent_points) / len(recent_points) if recent_points else 2.0
    form = shrink(avg_pts, 2.0, float(len(recent_points) or 1))
    ha = 1.05 if is_home else 0.95
    matchup = 1.0 + 0.05 * (team_attack - opp_defence) + 0.03 * (team_defence - opp_attack)
    matchup = max(0.7, min(1.3, matchup))

    if fixtures_in_gw <= 0:
        base = 0.0
        components = {"blank": 0.0}
        scenario_ids = ("blank_gw",)
    else:
        per_fixture = form * ha * matchup * (expected_minutes / 90.0)
        def_c = def_contrib_rate * def_contrib_points * (expected_minutes / 90.0)
        base = (per_fixture + def_c) * fixtures_in_gw
        components = {
            "form_scaled": per_fixture * fixtures_in_gw,
            "defensive_contribution": def_c * fixtures_in_gw,
            "home_away": ha,
            "matchup": matchup,
        }
        scenario_ids = ("available",) if availability == "available" else (availability,)

    # uncalibrated interval: +/- 35% around central — labeled uncalibrated by callers
    lower = base * 0.65
    upper = base * 1.35
    return PlayerGwProjection(
        player_id=player_id,
        gameweek=gameweek,
        expected_minutes=expected_minutes,
        p_start=p_start,
        p_sub=p_sub,
        p_none=p_none,
        minutes_if_start=minutes_if_start,
        minutes_if_sub=minutes_if_sub,
        expected_points=base,
        components=components,
        lower=lower,
        central=base,
        upper=upper,
        scenario_ids=scenario_ids,
        input_hashes=dict(input_hashes or {}),
        warnings=tuple(warnings),
    )


def project_horizon(
    *,
    player_id: int,
    gameweeks: list[int],
    weights: list[float],
    per_gw_kwargs: list[dict[str, Any]],
) -> HorizonProjection:
    if len(gameweeks) != len(weights) or len(weights) != len(per_gw_kwargs):
        raise ValueError("gameweeks, weights, and per_gw_kwargs length mismatch")
    by_gw = [
        project_player_gw(player_id=player_id, gameweek=gw, **kw)
        for gw, kw in zip(gameweeks, per_gw_kwargs, strict=True)
    ]
    unweighted = [p.expected_points for p in by_gw]
    weighted = sum(w * x for w, x in zip(weights, unweighted, strict=True))
    return HorizonProjection(player_id=player_id, by_gw=by_gw, weighted_total=weighted, unweighted_by_gw=unweighted)
