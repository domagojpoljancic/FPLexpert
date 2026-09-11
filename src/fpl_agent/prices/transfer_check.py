"""Squad-relative upgrade checks for price-watch market movers.

Pure / deterministic: no LLM, no invented IDs. Reuses the same XI objective and
budget primitives as pre-deadline transfer ranking.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from fpl_agent.prices.external import MarketMover
from fpl_agent.prices.types import LikelihoodBand, PriceDirection
from fpl_agent.projections.preseason import PlayerProjection
from fpl_agent.rules.engine import budget_after_transfers, selling_price_tenths
from fpl_agent.rules.season import SeasonRules, load_season_rules_2026_27
from fpl_agent.strategy.transfers import (
    MIN_WEIGHTED_DELTA,
    TransferCandidate,
    _club_ok,
    _is_available,
    _starter_ids,
    _xi_objective,
    xi_drop_for_swap,
)

VerdictKind = Literal["riser", "faller"]

# Include watch-band risers so future-planning targets still get a points verdict.
_RISER_BANDS = {LikelihoodBand.LIKELY_NEXT_WINDOW, LikelihoodBand.WATCH}
_FALLER_BANDS = {LikelihoodBand.LIKELY_NEXT_WINDOW, LikelihoodBand.WATCH}


@dataclass(frozen=True)
class UpgradeVerdict:
    kind: VerdictKind
    in_id: int
    in_name: str
    cost: float | None
    out_id: int | None
    out_name: str | None
    delta_gw_xp: float
    delta_weighted_xp: float
    affordable: bool
    bank_shortfall_tenths: int
    is_upgrade: bool
    band: LikelihoodBand
    likely: bool


def _purchase_map(team: Any, private: Any | None = None) -> dict[str, int]:
    if private is not None and getattr(private, "purchase_prices_tenths", None):
        return {str(k): int(v) for k, v in private.purchase_prices_tenths.items()}
    out: dict[str, int] = {}
    for p in team.squad.value or []:
        if p.purchase_price_tenths is not None:
            out[str(p.player_id)] = int(p.purchase_price_tenths)
        elif p.current_price_tenths is not None:
            out[str(p.player_id)] = int(p.current_price_tenths)
    return out


def _owned_ids(team: Any) -> list[int]:
    return [p.player_id for p in (team.squad.value or [])]


def _bank_tenths(team: Any) -> int:
    val = team.bank_tenths.value
    return int(val) if val is not None else 0


def _candidate_for_swap(
    *,
    out_id: int,
    in_id: int,
    owned_ids: list[int],
    bank_tenths: int,
    purchase_prices_tenths: dict[str, int],
    catalog: dict[int, dict[str, Any]],
    projections: dict[int, PlayerProjection],
    rules: SeasonRules,
    base_xi: tuple[float, float] | None,
    owned_team_by_id: dict[int, int],
) -> TransferCandidate | None:
    """Evaluate one same-position swap with the same numbers as rank_transfer_candidates."""
    out_el = catalog.get(out_id)
    out_proj = projections.get(out_id)
    inn = projections.get(in_id)
    in_el = catalog.get(in_id)
    if not out_el or not out_proj or not inn or not in_el:
        return None
    if not _is_available(in_el):
        return None
    element_type = int(out_el.get("element_type") or out_proj.element_type)
    if int(in_el.get("element_type") or inn.element_type) != element_type:
        return None
    if inn.p_start < 0.40 and inn.p_start <= out_proj.p_start:
        return None
    if not _club_ok(
        owned_team_by_id=owned_team_by_id,
        out_id=out_id,
        in_team_id=inn.team_id,
        club_limit=rules.club_limit,
    ):
        return None

    purchase = int(
        purchase_prices_tenths.get(str(out_id), out_el.get("now_cost") or out_proj.price_tenths)
    )
    current = int(out_el.get("now_cost") or out_proj.price_tenths)
    sell = selling_price_tenths(purchase, current, rules)
    buy = int(in_el.get("now_cost") or inn.price_tenths)
    bank_after = budget_after_transfers(
        bank_tenths=bank_tenths,
        sells=[(purchase, current)],
        buys_current_tenths=[buy],
        rules=rules,
    )

    if base_xi is not None:
        new_ids = [in_id if pid == out_id else pid for pid in owned_ids]
        new_xi = _xi_objective(new_ids, projections, rules)
        if new_xi is None:
            return None
        delta_w = new_xi[0] - base_xi[0]
        delta_gw = new_xi[1] - base_xi[1]
        new_starters = _starter_ids(new_ids, projections, rules) or set()
        in_starts = in_id in new_starters
        drop_id, xi_drop_name = xi_drop_for_swap(
            owned_ids=owned_ids,
            out_id=out_id,
            in_id=in_id,
            projections=projections,
            rules=rules,
        )
        drop_proj = projections.get(drop_id) if drop_id is not None else None
        xi_drop_xp = float(drop_proj.xp_by_gw[0]) if drop_proj and drop_proj.xp_by_gw else None
    else:
        delta_w = inn.weighted_xp - out_proj.weighted_xp
        out_gw = out_proj.xp_by_gw[0] if out_proj.xp_by_gw else 0.0
        in_gw = inn.xp_by_gw[0] if inn.xp_by_gw else 0.0
        delta_gw = in_gw - out_gw
        in_starts = True
        xi_drop_name = None
        xi_drop_xp = None

    shortfall = max(0, -bank_after)
    return TransferCandidate(
        out_id=out_id,
        in_id=in_id,
        out_name=str(out_el.get("web_name") or out_proj.web_name),
        in_name=inn.web_name,
        element_type=element_type,
        sell_tenths=sell,
        buy_tenths=buy,
        bank_after_tenths=bank_after,
        bank_shortfall_tenths=shortfall,
        affordable=bank_after >= 0,
        delta_weighted_xp=delta_w,
        delta_gw_xp=delta_gw,
        out_p_start=out_proj.p_start,
        in_p_start=inn.p_start,
        in_starts=in_starts,
        xi_drop_name=xi_drop_name,
        out_xp_next=float(out_proj.xp_by_gw[0]) if out_proj.xp_by_gw else 0.0,
        in_xp_next=float(inn.xp_by_gw[0]) if inn.xp_by_gw else 0.0,
        xi_drop_xp_next=xi_drop_xp,
    )


def best_swap_for_buy(
    *,
    in_id: int,
    owned_ids: list[int],
    bank_tenths: int,
    purchase_prices_tenths: dict[str, int],
    catalog: dict[int, dict[str, Any]],
    projections: dict[int, PlayerProjection],
    rules: SeasonRules | None = None,
) -> TransferCandidate | None:
    """Best same-position OUT for a fixed buy target (any ΔxP, including negative)."""
    rules = rules or load_season_rules_2026_27()
    inn = projections.get(in_id)
    in_el = catalog.get(in_id)
    if not inn or not in_el:
        return None
    element_type = int(in_el.get("element_type") or inn.element_type)
    owned_team_by_id = {
        pid: int(catalog[pid]["team"]) for pid in owned_ids if pid in catalog and "team" in catalog[pid]
    }
    base_xi = _xi_objective(owned_ids, projections, rules)
    best: TransferCandidate | None = None
    for out_id in owned_ids:
        out_el = catalog.get(out_id)
        if not out_el:
            continue
        if int(out_el.get("element_type") or 0) != element_type:
            continue
        cand = _candidate_for_swap(
            out_id=out_id,
            in_id=in_id,
            owned_ids=owned_ids,
            bank_tenths=bank_tenths,
            purchase_prices_tenths=purchase_prices_tenths,
            catalog=catalog,
            projections=projections,
            rules=rules,
            base_xi=base_xi,
            owned_team_by_id=owned_team_by_id,
        )
        if cand is None:
            continue
        if best is None or (cand.delta_weighted_xp, cand.delta_gw_xp, -cand.bank_shortfall_tenths) > (
            best.delta_weighted_xp,
            best.delta_gw_xp,
            -best.bank_shortfall_tenths,
        ):
            best = cand
    return best


def best_replacement_for_out(
    *,
    out_id: int,
    owned_ids: list[int],
    bank_tenths: int,
    purchase_prices_tenths: dict[str, int],
    catalog: dict[int, dict[str, Any]],
    projections: dict[int, PlayerProjection],
    rules: SeasonRules | None = None,
    affordable_only: bool = True,
) -> TransferCandidate | None:
    """Best same-position IN to replace an owned player (prefer affordable upgrades)."""
    rules = rules or load_season_rules_2026_27()
    out_el = catalog.get(out_id)
    out_proj = projections.get(out_id)
    if not out_el or not out_proj:
        return None
    element_type = int(out_el.get("element_type") or out_proj.element_type)
    owned = set(owned_ids)
    owned_team_by_id = {
        pid: int(catalog[pid]["team"]) for pid in owned_ids if pid in catalog and "team" in catalog[pid]
    }
    base_xi = _xi_objective(owned_ids, projections, rules)
    best: TransferCandidate | None = None
    for inn in projections.values():
        if inn.player_id in owned:
            continue
        in_el = catalog.get(inn.player_id)
        if not in_el or int(in_el.get("element_type") or inn.element_type) != element_type:
            continue
        cand = _candidate_for_swap(
            out_id=out_id,
            in_id=inn.player_id,
            owned_ids=owned_ids,
            bank_tenths=bank_tenths,
            purchase_prices_tenths=purchase_prices_tenths,
            catalog=catalog,
            projections=projections,
            rules=rules,
            base_xi=base_xi,
            owned_team_by_id=owned_team_by_id,
        )
        if cand is None:
            continue
        if affordable_only and not cand.affordable:
            continue
        if cand.delta_weighted_xp < 0:
            continue
        if best is None or (cand.delta_weighted_xp, cand.delta_gw_xp) > (
            best.delta_weighted_xp,
            best.delta_gw_xp,
        ):
            best = cand
    return best


def _verdict_from_candidate(
    *,
    kind: VerdictKind,
    cand: TransferCandidate,
    cost: float | None,
    band: LikelihoodBand,
) -> UpgradeVerdict:
    return UpgradeVerdict(
        kind=kind,
        in_id=cand.in_id,
        in_name=cand.in_name,
        cost=cost,
        out_id=cand.out_id,
        out_name=cand.out_name,
        delta_gw_xp=cand.delta_gw_xp,
        delta_weighted_xp=cand.delta_weighted_xp,
        affordable=cand.affordable,
        bank_shortfall_tenths=cand.bank_shortfall_tenths,
        is_upgrade=cand.delta_weighted_xp >= MIN_WEIGHTED_DELTA,
        band=band,
        likely=band == LikelihoodBand.LIKELY_NEXT_WINDOW,
    )


def evaluate_market_upgrades(
    *,
    market: list[MarketMover],
    projections: dict[int, PlayerProjection] | list[PlayerProjection],
    team: Any,
    catalog: dict[int, dict[str, Any]],
    rules: SeasonRules | None = None,
    private: Any | None = None,
    min_weighted_delta: float = MIN_WEIGHTED_DELTA,
) -> list[UpgradeVerdict]:
    """Return structured upgrade verdicts for unowned risers and owned fallers."""
    _ = min_weighted_delta  # callers may pass explicitly; is_upgrade uses MIN_WEIGHTED_DELTA
    rules = rules or load_season_rules_2026_27()
    if isinstance(projections, list):
        proj_map = {p.player_id: p for p in projections}
    else:
        proj_map = projections
    if not proj_map:
        return []

    owned_ids = _owned_ids(team)
    if not owned_ids:
        return []
    bank = _bank_tenths(team)
    purchases = _purchase_map(team, private)

    verdicts: list[UpgradeVerdict] = []
    seen_risers: set[int] = set()

    risers = [
        m
        for m in market
        if m.direction == PriceDirection.RISE and not m.owned and m.band in _RISER_BANDS
    ]
    # Likely first so report ordering matches importance.
    risers.sort(key=lambda m: (0 if m.band == LikelihoodBand.LIKELY_NEXT_WINDOW else 1, -abs(m.external_progress)))

    for mover in risers:
        if mover.player_id in seen_risers:
            continue
        seen_risers.add(mover.player_id)
        cand = best_swap_for_buy(
            in_id=mover.player_id,
            owned_ids=owned_ids,
            bank_tenths=bank,
            purchase_prices_tenths=purchases,
            catalog=catalog,
            projections=proj_map,
            rules=rules,
        )
        if cand is None:
            # No legal same-position OUT — still surface a non-upgrade stub.
            verdicts.append(
                UpgradeVerdict(
                    kind="riser",
                    in_id=mover.player_id,
                    in_name=mover.web_name,
                    cost=mover.cost_millions,
                    out_id=None,
                    out_name=None,
                    delta_gw_xp=0.0,
                    delta_weighted_xp=0.0,
                    affordable=False,
                    bank_shortfall_tenths=0,
                    is_upgrade=False,
                    band=mover.band,
                    likely=mover.band == LikelihoodBand.LIKELY_NEXT_WINDOW,
                )
            )
            continue
        verdicts.append(
            _verdict_from_candidate(
                kind="riser",
                cand=cand,
                cost=mover.cost_millions,
                band=mover.band,
            )
        )

    fallers = [
        m
        for m in market
        if m.direction == PriceDirection.FALL and m.owned and m.band in _FALLER_BANDS
    ]
    fallers.sort(key=lambda m: (0 if m.band == LikelihoodBand.LIKELY_NEXT_WINDOW else 1, -abs(m.external_progress)))

    for mover in fallers:
        cand = best_replacement_for_out(
            out_id=mover.player_id,
            owned_ids=owned_ids,
            bank_tenths=bank,
            purchase_prices_tenths=purchases,
            catalog=catalog,
            projections=proj_map,
            rules=rules,
            affordable_only=True,
        )
        if cand is None:
            continue
        # Only nudge when the replacement is at least lateral (Δ ≥ 0) — already filtered.
        cost = cand.buy_tenths / 10.0
        verdicts.append(
            _verdict_from_candidate(
                kind="faller",
                cand=cand,
                cost=cost,
                band=mover.band,
            )
        )

    return verdicts
