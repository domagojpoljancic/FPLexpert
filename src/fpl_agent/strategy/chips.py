"""This-week chip play/hold advice. Not a 38-week optimiser."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fpl_agent.domain.models import ChipHalf, ChipKind
from fpl_agent.rules.engine import available_chip_instances, chip_half_for_event
from fpl_agent.rules.season import SeasonRules, load_season_rules_2026_27

TC_MIN_XP = 8.0
TC_MIN_CEILING_HAUL = 0.25
TC_VS_NEXT_BEST = 1.35
TC_MIN_P_START = 0.85
BB_MIN_BENCH_XP = 8.0
BB_MIN_OUTFIELD_P_START = 0.55
FH_VS_MEDIAN = 0.72
FH_MIN_GAP = 8.0
WC_LOW_START_COUNT = 3
WC_LOW_P_START = 0.40


@dataclass(frozen=True)
class ChipAdvice:
    kind: str
    action: str
    available: bool
    reason: str
    metric: float | None = None

    def as_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "action": self.action,
            "available": self.available,
            "reason": self.reason,
            "metric": None if self.metric is None else round(self.metric, 3),
        }


def recommend_chips(
    *,
    gameweek: int,
    weekly_plan: dict[str, Any],
    chip_instances: list[Any] | None = None,
    rules: SeasonRules | None = None,
) -> list[ChipAdvice]:
    """Play vs hold for chips still available this half."""
    rules = rules or load_season_rules_2026_27()
    available = _available_kinds(gameweek, chip_instances, rules)
    horizon = list(weekly_plan.get("horizon") or [])
    this_row = next((row for row in horizon if int(row.get("gw") or 0) == gameweek), None)
    if this_row is None and horizon:
        this_row = horizon[0]
    xi_xp = float((this_row or {}).get("xi_xp") or 0.0)
    captain = weekly_plan.get("model_captain") or {}
    bench = list(weekly_plan.get("bench") or [])
    xi = list(weekly_plan.get("xi") or [])

    order = (
        ChipKind.TRIPLE_CAPTAIN,
        ChipKind.BENCH_BOOST,
        ChipKind.FREE_HIT,
        ChipKind.WILDCARD,
    )
    out: list[ChipAdvice] = []
    for kind in order:
        key = kind.value
        if key not in available:
            out.append(
                ChipAdvice(
                    kind=key,
                    action="hold",
                    available=False,
                    reason="Not available this half (already used, wrong window, or not listed).",
                )
            )
            continue
        if kind == ChipKind.TRIPLE_CAPTAIN:
            out.append(_triple_captain(captain, horizon, gameweek))
        elif kind == ChipKind.BENCH_BOOST:
            out.append(_bench_boost(bench))
        elif kind == ChipKind.FREE_HIT:
            out.append(_free_hit(gameweek, xi_xp, horizon, rules))
        else:
            out.append(_wildcard(gameweek, xi, rules))
    return out


def _available_kinds(
    gameweek: int,
    chip_instances: list[Any] | None,
    rules: SeasonRules,
) -> set[str]:
    used: set[tuple[ChipKind, ChipHalf]] = set()
    listed_available: set[str] = set()
    saw_list = False
    for raw in chip_instances or []:
        saw_list = True
        kind, half, available, used_gw = _parse_instance(raw)
        if kind is None or half is None:
            continue
        if used_gw is not None or available is False:
            used.add((kind, half))
            continue
        if available:
            listed_available.add(kind.value)
    legal = {
        kind.value
        for kind, _half in available_chip_instances(
            event=gameweek,
            used=used,
            rules=rules,
        )
    }
    if saw_list and listed_available:
        return legal & listed_available
    return legal


def _parse_instance(raw: Any) -> tuple[ChipKind | None, ChipHalf | None, bool | None, int | None]:
    if hasattr(raw, "kind"):
        kind = ChipKind(raw.kind) if not isinstance(raw.kind, ChipKind) else raw.kind
        half = ChipHalf(raw.half) if not isinstance(raw.half, ChipHalf) else raw.half
        available = bool(getattr(raw, "available", True))
        used_gw = getattr(raw, "used_in_gameweek", None)
        return kind, half, available, int(used_gw) if used_gw else None
    if isinstance(raw, dict):
        try:
            kind = ChipKind(str(raw.get("kind")))
            half = ChipHalf(str(raw.get("half") or chip_half_for_event(1).value))
        except ValueError:
            return None, None, None, None
        used_gw = raw.get("used_in_gameweek")
        available = raw.get("available")
        return kind, half, None if available is None else bool(available), int(used_gw) if used_gw else None
    return None, None, None, None


def _triple_captain(
    captain: dict[str, Any],
    horizon: list[dict[str, Any]],
    gameweek: int,
) -> ChipAdvice:
    xp = float(captain.get("xp_next") or captain.get("captain_xp") or 0.0)
    p_start = float(captain.get("p_start") or 0.0)
    rationale = captain.get("captain_rationale") or captain
    haul = float(rationale.get("haul_proxy") or rationale.get("ceiling", xp) / max(xp, 0.01) - 1.0)
    ceiling = float(rationale.get("ceiling") or xp * (1.0 + haul))
    others = [
        float(row.get("captain_xp") or 0.0)
        for row in horizon
        if int(row.get("gw") or 0) != gameweek
    ]
    next_best = max(others) if others else 0.0
    metric = ceiling / next_best if next_best > 0 else ceiling
    if (
        xp >= TC_MIN_XP
        and p_start >= TC_MIN_P_START
        and haul >= TC_MIN_CEILING_HAUL
        and (not others or xp >= TC_VS_NEXT_BEST * next_best)
    ):
        return ChipAdvice(
            kind=ChipKind.TRIPLE_CAPTAIN.value,
            action="play",
            available=True,
            reason=(
                f"Captain ceiling {ceiling:.2f} (haul proxy {haul:.2f}) with {p_start:.0%} start "
                f"is an outlier vs next-best week {next_best:.2f}."
            ),
            metric=metric,
        )
    return ChipAdvice(
        kind=ChipKind.TRIPLE_CAPTAIN.value,
        action="hold",
        reason=(
            f"Captain mean xP {xp:.2f} lacks ceiling for TC (haul proxy {haul:.2f}, need ≥{TC_MIN_CEILING_HAUL:.2f}); "
            f"hold until a genuine haul week (DGW detection pending)."
        ),
        available=True,
        metric=metric,
    )


def _bench_boost(bench: list[dict[str, Any]]) -> ChipAdvice:
    bench_xp = sum(float(p.get("xp_next") or 0.0) for p in bench)
    outfield = [p for p in bench if str(p.get("position") or "") != "GKP"]
    min_p = min((float(p.get("p_start") or 0.0) for p in outfield), default=0.0)
    if bench_xp >= BB_MIN_BENCH_XP and (not outfield or min_p >= BB_MIN_OUTFIELD_P_START):
        return ChipAdvice(
            kind=ChipKind.BENCH_BOOST.value,
            action="play",
            available=True,
            reason=(
                f"Bench xP {bench_xp:.2f} with outfield start ≥{min_p:.0%} looks like a Bench Boost week."
            ),
            metric=bench_xp,
        )
    return ChipAdvice(
        kind=ChipKind.BENCH_BOOST.value,
        action="hold",
        available=True,
        reason=(
            f"Bench xP {bench_xp:.2f} (need ≥{BB_MIN_BENCH_XP:.0f}) or outfield start risk "
            f"(min {min_p:.0%}) is not enough to spend Bench Boost."
        ),
        metric=bench_xp,
    )


def _free_hit(
    gameweek: int,
    xi_xp: float,
    horizon: list[dict[str, Any]],
    rules: SeasonRules,
) -> ChipAdvice:
    if gameweek in rules.free_hit_forbidden_events:
        return ChipAdvice(
            kind=ChipKind.FREE_HIT.value,
            action="hold",
            available=True,
            reason=f"Free Hit is not allowed in GW{gameweek}.",
            metric=xi_xp,
        )
    others = [
        float(row.get("xi_xp") or 0.0)
        for row in horizon
        if int(row.get("gw") or 0) != gameweek
    ]
    if not others:
        return ChipAdvice(
            kind=ChipKind.FREE_HIT.value,
            action="hold",
            available=True,
            reason="Not enough horizon weeks to judge a Free Hit blank/spike.",
            metric=xi_xp,
        )
    ordered = sorted(others)
    mid = len(ordered) // 2
    median = (ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2)
    gap = median - xi_xp
    if median > 0 and xi_xp <= FH_VS_MEDIAN * median and gap >= FH_MIN_GAP:
        return ChipAdvice(
            kind=ChipKind.FREE_HIT.value,
            action="play",
            available=True,
            reason=(
                f"This week's XI xP {xi_xp:.1f} is a blank vs the horizon median {median:.1f} "
                f"(gap {gap:.1f}). Free Hit is for a one-week reset, not a long rebuild."
            ),
            metric=gap,
        )
    return ChipAdvice(
        kind=ChipKind.FREE_HIT.value,
        action="hold",
        available=True,
        reason=(
            f"This week's XI xP {xi_xp:.1f} is close enough to the horizon median {median:.1f}; hold Free Hit."
        ),
        metric=gap,
    )


def _wildcard(gameweek: int, xi: list[dict[str, Any]], rules: SeasonRules) -> ChipAdvice:
    first_wc = next(
        (inst for inst in rules.chip_instances if inst.kind == ChipKind.WILDCARD),
        None,
    )
    if first_wc and gameweek < first_wc.start_event:
        return ChipAdvice(
            kind=ChipKind.WILDCARD.value,
            action="hold",
            available=True,
            reason=f"Wildcard is not available until GW{first_wc.start_event}.",
        )
    low = [p for p in xi if float(p.get("p_start") or 1.0) < WC_LOW_P_START]
    metric = float(len(low))
    if len(low) >= WC_LOW_START_COUNT:
        names = ", ".join(str(p.get("web_name") or p.get("player_id")) for p in low[:5])
        return ChipAdvice(
            kind=ChipKind.WILDCARD.value,
            action="play",
            available=True,
            reason=(
                f"{len(low)} modelled starters are below {WC_LOW_P_START:.0%} start chance ({names}). "
                "That is a rebuild signal, not a one-week Free Hit."
            ),
            metric=metric,
        )
    return ChipAdvice(
        kind=ChipKind.WILDCARD.value,
        action="hold",
        available=True,
        reason=(
            f"Only {len(low)} XI player(s) have start chance below {WC_LOW_P_START:.0%}; keep Wildcard."
        ),
        metric=metric,
    )
