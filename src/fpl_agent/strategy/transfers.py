"""Deterministic legal 1-FT upgrade candidates for pre-deadline advice.

The LLM must not invent buy targets. This module ranks same-position swaps from
bootstrap projections and private bank/selling prices so the model can only
choose among real IDs.

With £0.0m bank, affordable upgrades are often empty for a strong squad. We still
surface *stretch* upgrades (positive ΔxP that need more bank) so the assistant can
name concrete targets instead of rubber-stamping the same XV.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fpl_agent.projections.preseason import PlayerProjection
from fpl_agent.rules.engine import budget_after_transfers, selling_price_tenths
from fpl_agent.rules.season import SeasonRules, load_season_rules_2026_27
from fpl_agent.strategy.draft import BENCH_WEIGHT, select_best_xi

MIN_IN_P_START = 0.40


def _starter_ids(
    owned_ids: list[int],
    projections: dict[int, PlayerProjection],
    rules: SeasonRules,
) -> set[int] | None:
    players = [projections[pid] for pid in owned_ids if pid in projections]
    if len(players) != len(owned_ids) or len(players) != rules.squad_size:
        return None
    xi, _bench, _formation = select_best_xi(players, rules)
    return {p.player_id for p in xi}


def _xi_objective(
    owned_ids: list[int],
    projections: dict[int, PlayerProjection],
    rules: SeasonRules,
) -> tuple[float, float] | None:
    players = [projections[pid] for pid in owned_ids if pid in projections]
    if len(players) != len(owned_ids) or len(players) != rules.squad_size:
        return None
    xi, bench, _ = select_best_xi(players, rules)
    weighted = sum(p.weighted_xp for p in xi) + BENCH_WEIGHT * sum(p.weighted_xp for p in bench)
    gw = sum((p.xp_by_gw[0] if p.xp_by_gw else 0.0) for p in xi)
    return weighted, gw


DEFAULT_LIMIT = 12
STRETCH_LIMIT = 8
MIN_WEIGHTED_DELTA = 0.25
CANDIDATES_PER_OUT = 30
# Stretch list ignores budget but still caps how far above bank we bother listing.
MAX_STRETCH_SHORTFALL_TENTHS = 30  # £3.0m
PAIR_POOL = 8
MIN_HIT_NET_GW = 0.5
MAX_TRANSFERS_IN_PLAN = 2


@dataclass(frozen=True)
class TransferCandidate:
    out_id: int
    in_id: int
    out_name: str
    in_name: str
    element_type: int
    sell_tenths: int
    buy_tenths: int
    bank_after_tenths: int
    bank_shortfall_tenths: int
    affordable: bool
    delta_weighted_xp: float
    delta_gw_xp: float
    out_p_start: float
    in_p_start: float
    in_starts: bool = True
    xi_drop_name: str | None = None

    def as_payload(self) -> dict[str, Any]:
        return {
            "out_id": self.out_id,
            "in_id": self.in_id,
            "out_name": self.out_name,
            "in_name": self.in_name,
            "element_type": self.element_type,
            "sell_tenths": self.sell_tenths,
            "buy_tenths": self.buy_tenths,
            "bank_after_tenths": self.bank_after_tenths,
            "bank_shortfall_tenths": self.bank_shortfall_tenths,
            "affordable": self.affordable,
            "delta_weighted_xp": round(self.delta_weighted_xp, 3),
            "delta_gw_xp": round(self.delta_gw_xp, 3),
            "out_p_start": round(self.out_p_start, 3),
            "in_p_start": round(self.in_p_start, 3),
            "in_starts": self.in_starts,
            "xi_drop_name": self.xi_drop_name,
        }


@dataclass(frozen=True)
class TransferPlan:
    """One or two legal swaps, with hit cost taken from unused free transfers."""

    moves: tuple[TransferCandidate, ...]
    free_transfers_used: int
    hit_cost: int
    delta_weighted_xp: float
    delta_gw_xp: float
    net_gw_xp: float
    bank_after_tenths: int
    affordable: bool

    def as_payload(self) -> dict[str, Any]:
        return {
            "moves": [move.as_payload() for move in self.moves],
            "n_transfers": len(self.moves),
            "free_transfers_used": self.free_transfers_used,
            "hit_cost": self.hit_cost,
            "delta_weighted_xp": round(self.delta_weighted_xp, 3),
            "delta_gw_xp": round(self.delta_gw_xp, 3),
            "net_gw_xp": round(self.net_gw_xp, 3),
            "bank_after_tenths": self.bank_after_tenths,
            "affordable": self.affordable,
            "summary": _plan_summary(self),
        }


def _plan_summary(plan: TransferPlan) -> str:
    swaps = ", ".join(f"{m.out_name}→{m.in_name}" for m in plan.moves)
    hit = f", -{plan.hit_cost} hit" if plan.hit_cost else ""
    return f"{swaps} ({plan.net_gw_xp:+.2f} net GW xP{hit})"


def _is_available(element: dict[str, Any]) -> bool:
    status = str(element.get("status") or "a")
    if status in {"u", "n", "i", "s"}:
        return False
    chance = element.get("chance_of_playing_next_round")
    if chance is not None:
        try:
            if float(chance) < 25:
                return False
        except (TypeError, ValueError):
            pass
    return True


def _club_ok(
    *,
    owned_team_by_id: dict[int, int],
    out_id: int,
    in_team_id: int,
    club_limit: int,
) -> bool:
    counts: dict[int, int] = {}
    for pid, team_id in owned_team_by_id.items():
        if pid == out_id:
            continue
        counts[team_id] = counts.get(team_id, 0) + 1
    return counts.get(in_team_id, 0) + 1 <= club_limit


def _dedupe_top(candidates: list[TransferCandidate], *, limit: int) -> list[TransferCandidate]:
    candidates = sorted(
        candidates,
        key=lambda c: (-int(c.in_starts), -c.delta_gw_xp, -c.delta_weighted_xp, c.out_id, c.in_id),
    )
    per_out: dict[int, int] = {}
    selected: list[TransferCandidate] = []
    for cand in candidates:
        if per_out.get(cand.out_id, 0) >= 2:
            continue
        selected.append(cand)
        per_out[cand.out_id] = per_out.get(cand.out_id, 0) + 1
        if len(selected) >= limit:
            break
    return selected


def rank_transfer_candidates(
    *,
    owned_ids: list[int],
    bank_tenths: int,
    purchase_prices_tenths: dict[str, int],
    catalog: dict[int, dict[str, Any]],
    projections: dict[int, PlayerProjection],
    rules: SeasonRules | None = None,
    limit: int = DEFAULT_LIMIT,
    stretch_limit: int = STRETCH_LIMIT,
    min_weighted_delta: float = MIN_WEIGHTED_DELTA,
) -> tuple[list[TransferCandidate], list[TransferCandidate]]:
    """Return (affordable_upgrades, stretch_upgrades)."""
    rules = rules or load_season_rules_2026_27()
    owned = set(owned_ids)
    owned_team_by_id = {
        pid: int(catalog[pid]["team"]) for pid in owned_ids if pid in catalog and "team" in catalog[pid]
    }

    market_by_pos: dict[int, list[PlayerProjection]] = {1: [], 2: [], 3: [], 4: []}
    for proj in projections.values():
        if proj.player_id in owned:
            continue
        el = catalog.get(proj.player_id)
        if not el or not _is_available(el):
            continue
        market_by_pos.setdefault(proj.element_type, []).append(proj)
    for pos, rows in market_by_pos.items():
        rows.sort(key=lambda p: (-p.weighted_xp, p.player_id))
        market_by_pos[pos] = rows[: max(CANDIDATES_PER_OUT * 3, 50)]

    affordable: list[TransferCandidate] = []
    stretch: list[TransferCandidate] = []

    base_xi = _xi_objective(owned_ids, projections, rules)

    for out_id in owned_ids:
        out_el = catalog.get(out_id)
        out_proj = projections.get(out_id)
        if not out_el or not out_proj:
            continue
        element_type = int(out_el.get("element_type") or out_proj.element_type)
        purchase = int(
            purchase_prices_tenths.get(str(out_id), out_el.get("now_cost") or out_proj.price_tenths)
        )
        current = int(out_el.get("now_cost") or out_proj.price_tenths)
        sell = selling_price_tenths(purchase, current, rules)

        for inn in market_by_pos.get(element_type, [])[:CANDIDATES_PER_OUT]:
            if inn.p_start < MIN_IN_P_START and inn.p_start <= out_proj.p_start:
                continue
            buy = int(catalog.get(inn.player_id, {}).get("now_cost") or inn.price_tenths)
            bank_after = budget_after_transfers(
                bank_tenths=bank_tenths,
                sells=[(purchase, current)],
                buys_current_tenths=[buy],
                rules=rules,
            )
            if not _club_ok(
                owned_team_by_id=owned_team_by_id,
                out_id=out_id,
                in_team_id=inn.team_id,
                club_limit=rules.club_limit,
            ):
                continue
            if base_xi is not None:
                new_ids = [inn.player_id if pid == out_id else pid for pid in owned_ids]
                new_xi = _xi_objective(new_ids, projections, rules)
                if new_xi is None:
                    continue
                delta_w = new_xi[0] - base_xi[0]
                delta_gw = new_xi[1] - base_xi[1]
                old_starters = _starter_ids(owned_ids, projections, rules) or set()
                new_starters = _starter_ids(new_ids, projections, rules) or set()
                in_starts = inn.player_id in new_starters
                dropped = [
                    projections[pid].web_name
                    for pid in old_starters
                    if pid not in new_starters and pid in projections
                ]
                xi_drop_name = dropped[0] if dropped else None
            else:
                delta_w = inn.weighted_xp - out_proj.weighted_xp
                out_gw = out_proj.xp_by_gw[0] if out_proj.xp_by_gw else 0.0
                in_gw = inn.xp_by_gw[0] if inn.xp_by_gw else 0.0
                delta_gw = in_gw - out_gw
                in_starts = True
                xi_drop_name = None
            if delta_w < min_weighted_delta:
                continue
            shortfall = max(0, -bank_after)
            cand = TransferCandidate(
                out_id=out_id,
                in_id=inn.player_id,
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
            )
            if cand.affordable:
                affordable.append(cand)
            elif shortfall <= MAX_STRETCH_SHORTFALL_TENTHS:
                stretch.append(cand)

    return _dedupe_top(affordable, limit=limit), _dedupe_top(stretch, limit=stretch_limit)


def this_week_upgrade(candidates: list[TransferCandidate]) -> TransferCandidate | None:
    """Best affordable swap whose buy target starts this GW. Bench-only upgrades are not a weekly FT."""
    for cand in candidates:
        if cand.affordable and cand.in_starts:
            return cand
    return None


def rank_transfer_plans(
    *,
    owned_ids: list[int],
    bank_tenths: int,
    free_transfers: int,
    purchase_prices_tenths: dict[str, int],
    catalog: dict[int, dict[str, Any]],
    projections: dict[int, PlayerProjection],
    rules: SeasonRules | None = None,
    hits_enabled: bool = True,
    max_hit: int | None = None,
) -> list[TransferPlan]:
    """Rank 1- and 2-swap plans. Hits cost `hit_cost_points` per extra transfer."""
    rules = rules or load_season_rules_2026_27()
    hit_points = rules.hit_cost_points
    cap = max_hit if max_hit is not None else 2 * hit_points
    affordable, _stretch = rank_transfer_candidates(
        owned_ids=owned_ids,
        bank_tenths=bank_tenths,
        purchase_prices_tenths=purchase_prices_tenths,
        catalog=catalog,
        projections=projections,
        rules=rules,
    )
    base_xi = _xi_objective(owned_ids, projections, rules)
    plans: list[TransferPlan] = []
    for move in affordable:
        plan = _plan_from_moves(
            owned_ids=owned_ids,
            bank_tenths=bank_tenths,
            free_transfers=free_transfers,
            moves=(move,),
            projections=projections,
            rules=rules,
            base_xi=base_xi,
            hit_points=hit_points,
        )
        if plan is not None and plan.hit_cost <= cap:
            plans.append(plan)

    if MAX_TRANSFERS_IN_PLAN >= 2:
        pool = affordable[:PAIR_POOL]
        for i, first in enumerate(pool):
            for second in pool[i + 1 :]:
                if not hits_enabled and free_transfers < 2:
                    continue
                if first.out_id == second.out_id or first.in_id == second.in_id:
                    continue
                combined_bank = first.bank_after_tenths + second.bank_after_tenths - bank_tenths
                if combined_bank < 0:
                    continue
                if not _club_ok_two(
                    owned_ids=owned_ids,
                    catalog=catalog,
                    first=first,
                    second=second,
                    club_limit=rules.club_limit,
                ):
                    continue
                plan = _plan_from_moves(
                    owned_ids=owned_ids,
                    bank_tenths=bank_tenths,
                    free_transfers=free_transfers,
                    moves=(first, second),
                    projections=projections,
                    rules=rules,
                    base_xi=base_xi,
                    hit_points=hit_points,
                    bank_after_override=combined_bank,
                )
                if plan is None or plan.hit_cost > cap:
                    continue
                if plan.hit_cost > 0 and plan.net_gw_xp < MIN_HIT_NET_GW:
                    continue
                plans.append(plan)

    return sorted(
        plans,
        key=lambda p: (-p.net_gw_xp, -p.delta_weighted_xp, p.hit_cost, len(p.moves)),
    )


def _plan_from_moves(
    *,
    owned_ids: list[int],
    bank_tenths: int,
    free_transfers: int,
    moves: tuple[TransferCandidate, ...],
    projections: dict[int, PlayerProjection],
    rules: SeasonRules,
    base_xi: tuple[float, float] | None,
    hit_points: int,
    bank_after_override: int | None = None,
) -> TransferPlan | None:
    new_ids = list(owned_ids)
    for move in moves:
        if move.out_id not in new_ids:
            return None
        new_ids = [move.in_id if pid == move.out_id else pid for pid in new_ids]
    new_xi = _xi_objective(new_ids, projections, rules)
    if new_xi is None or base_xi is None:
        return None
    delta_w = new_xi[0] - base_xi[0]
    delta_gw = new_xi[1] - base_xi[1]
    paid = max(0, len(moves) - max(0, free_transfers))
    hit_cost = paid * hit_points
    bank_after = bank_after_override if bank_after_override is not None else moves[-1].bank_after_tenths
    return TransferPlan(
        moves=moves,
        free_transfers_used=min(len(moves), max(0, free_transfers)),
        hit_cost=hit_cost,
        delta_weighted_xp=delta_w,
        delta_gw_xp=delta_gw,
        net_gw_xp=delta_gw - hit_cost,
        bank_after_tenths=bank_after,
        affordable=bank_after >= 0,
    )


def _club_ok_two(
    *,
    owned_ids: list[int],
    catalog: dict[int, dict[str, Any]],
    first: TransferCandidate,
    second: TransferCandidate,
    club_limit: int,
) -> bool:
    counts: dict[int, int] = {}
    for pid in owned_ids:
        if pid in {first.out_id, second.out_id}:
            continue
        el = catalog.get(pid) or {}
        team = int(el.get("team") or 0)
        if team:
            counts[team] = counts.get(team, 0) + 1
    for inn in (first, second):
        team = int((catalog.get(inn.in_id) or {}).get("team") or 0)
        if not team:
            continue
        counts[team] = counts.get(team, 0) + 1
        if counts[team] > club_limit:
            return False
    return True
