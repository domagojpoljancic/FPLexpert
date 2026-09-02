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

from fpl_agent.domain.models import RiskProfile
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
CROSS_RESTRUCTURE_OUTS = 6
CROSS_RESTRUCTURE_INS = 16
HORIZON_TIE_EPSILON = 0.15
PAIR_POOL = 8
MIN_HIT_NET_GW = 0.5  # legacy single-GW floor; horizon gate supersedes for hits
HIT_MARGIN_BY_RISK: dict[RiskProfile, float] = {
    RiskProfile.CONSERVATIVE: 1.5,
    RiskProfile.MODERATE: 1.0,
    RiskProfile.AGGRESSIVE: 0.5,
}
MAX_BANKED_FTS = 5
FT_BANK_OPTION_VALUE = 0.35
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
            "reason": explain_transfer(self),
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
    hit = f", {plan.hit_cost}-point hit" if plan.hit_cost else ""
    return f"{swaps} ({plan.net_gw_xp:+.1f} pts this week{hit})"


POSITION_LABEL = {1: "goalkeeper", 2: "defender", 3: "midfielder", 4: "forward"}


def explain_transfer(cand: TransferCandidate) -> str:
    """Plain-language reason; model numbers stay in brackets."""
    gw = f"{cand.delta_gw_xp:+.1f} pts this week"
    horizon = f"{cand.delta_weighted_xp:+.1f} over the next few GWs"
    if cand.in_starts:
        if cand.in_p_start >= cand.out_p_start + 0.1:
            body = (
                f"{cand.in_name} is likelier to start than {cand.out_name} "
                f"({cand.in_p_start:.0%} vs {cand.out_p_start:.0%}) and should add more to the XI this week"
            )
        else:
            body = (
                f"{cand.in_name} is projected to outscore {cand.out_name} this week "
                f"while still starting ({cand.in_p_start:.0%} start chance)"
            )
        if cand.xi_drop_name and cand.xi_drop_name != cand.out_name:
            body += f"; {cand.xi_drop_name} drops to the bench"
    else:
        body = (
            f"{cand.in_name} is a longer-term upgrade on {cand.out_name} "
            f"but would sit on the bench this week"
        )
    return f"{body} ({gw}; {horizon})."


def explain_vs_pick(alt: TransferCandidate, pick: TransferCandidate) -> str:
    """Why this same-position option lost (or is close) vs the recommended IN."""
    gw_gap = pick.delta_gw_xp - alt.delta_gw_xp
    w_gap = pick.delta_weighted_xp - alt.delta_weighted_xp
    if gw_gap > 0.15:
        week = f"adds less this week than {pick.in_name}"
    elif gw_gap < -0.15:
        week = f"adds a bit more this week than {pick.in_name}"
    else:
        week = f"is close to {pick.in_name} this week"
    if w_gap < -0.3:
        horizon = "and looks stronger over the next few gameweeks"
    elif w_gap > 0.3:
        horizon = "but looks weaker over the next few gameweeks"
    else:
        horizon = "over a similar run of gameweeks"
    start = ""
    if alt.out_name != pick.out_name:
        start = f" It would sell {alt.out_name} instead of {pick.out_name}."
    elif alt.in_p_start >= alt.out_p_start + 0.15:
        start = (
            f" It would replace {alt.out_name} ({alt.out_p_start:.0%} start) "
            f"with {alt.in_name} ({alt.in_p_start:.0%})."
        )
    return (
        f"{week} {horizon}.{start} "
        f"({alt.delta_gw_xp:+.1f} pts this week; {alt.delta_weighted_xp:+.1f} over the next few GWs)."
    )


def same_position_shortlist(
    pick: TransferCandidate,
    candidates: list[TransferCandidate],
    *,
    limit: int = 3,
) -> list[TransferCandidate]:
    """Recommended buy first, then other affordable starter buys in the same position."""
    same = [
        cand
        for cand in candidates
        if cand.element_type == pick.element_type and cand.in_starts and cand.affordable
    ]
    ordered = [pick] + [cand for cand in same if cand.in_id != pick.in_id]
    seen: set[int] = set()
    out: list[TransferCandidate] = []
    for cand in ordered:
        if cand.in_id in seen:
            continue
        seen.add(cand.in_id)
        out.append(cand)
        if len(out) >= limit:
            break
    return out


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


def _position_counts(owned_ids: list[int], catalog: dict[int, dict[str, Any]]) -> dict[int, int]:
    counts = {1: 0, 2: 0, 3: 0, 4: 0}
    for pid in owned_ids:
        el = catalog.get(pid) or {}
        et = int(el.get("element_type") or 0)
        if et in counts:
            counts[et] += 1
    return counts


def _squad_position_legal(counts: dict[int, int], rules: SeasonRules) -> bool:
    return counts.get(1, 0) == 2 and counts.get(2, 0) == 5 and counts.get(3, 0) == 5 and counts.get(4, 0) == 3


def _differential_tiebreak_key(
    plan: TransferPlan,
    *,
    catalog: dict[int, dict[str, Any]] | None,
    risk_profile: RiskProfile,
) -> float:
    """Display-only mild lean toward lower ownership when horizon xP is tied (moderate risk)."""
    if risk_profile != RiskProfile.MODERATE or not catalog or not plan.moves:
        return 0.0
    inn = plan.moves[-1].in_id
    el = catalog.get(inn) or {}
    try:
        ownership = float(el.get("selected_by_percent") or 50.0)
    except (TypeError, ValueError):
        ownership = 50.0
    return -ownership / 100.0


def hit_horizon_margin(
    *,
    risk_profile: RiskProfile,
    gameweek: int = 1,
    early_season_gws: int = 4,
    early_season_boost: float = 1.0,
) -> float:
    margin = HIT_MARGIN_BY_RISK.get(risk_profile, 1.0)
    if gameweek <= early_season_gws:
        margin += early_season_boost
    return margin


def hit_clears_horizon_bar(
    plan: TransferPlan,
    *,
    margin: float,
) -> bool:
    """Horizon-weighted gain must exceed hit cost by a risk-scaled margin."""
    if plan.hit_cost <= 0:
        return True
    net_horizon = plan.delta_weighted_xp - plan.hit_cost
    required = (plan.hit_cost / 4.0) * margin
    return net_horizon >= required


def roll_recommendation_reason(
    *,
    free_transfers: int,
    best_plan: TransferPlan | None,
    margin: float,
) -> str:
    if best_plan is None:
        return "No affordable move clears the horizon EV bar; banking FT preserves optionality."
    if best_plan.hit_cost == 0 and best_plan.delta_weighted_xp < margin * 0.5:
        return (
            f"Marginal +{best_plan.delta_weighted_xp:.1f} horizon xP; roll to bank FT "
            f"({free_transfers}/{MAX_BANKED_FTS} now)."
        )
    return "Top move clears bar."


def rank_cross_position_plans(
    *,
    owned_ids: list[int],
    bank_tenths: int,
    free_transfers: int,
    purchase_prices_tenths: dict[str, int],
    catalog: dict[int, dict[str, Any]],
    projections: dict[int, PlayerProjection],
    rules: SeasonRules,
    hit_points: int,
    base_xi: tuple[float, float] | None,
) -> list[TransferPlan]:
    """Two-swap restructures across positions (e.g. two mids → premium FWD + enabler)."""
    if MAX_TRANSFERS_IN_PLAN < 2 or free_transfers < 2:
        return []
    weak = sorted(
        owned_ids,
        key=lambda pid: projections[pid].weighted_xp if pid in projections else 0.0,
    )[:CROSS_RESTRUCTURE_OUTS]
    market = sorted(
        [
            p
            for p in projections.values()
            if p.player_id not in owned_ids and p.p_start >= MIN_IN_P_START
        ],
        key=lambda p: (-p.weighted_xp, p.player_id),
    )[:CROSS_RESTRUCTURE_INS]
    plans: list[TransferPlan] = []
    for i, out_a in enumerate(weak):
        for out_b in weak[i + 1 :]:
            if out_a == out_b:
                continue
            for j, in_a in enumerate(market):
                for in_b in market[j + 1 :]:
                    if in_a.player_id == in_b.player_id:
                        continue
                    out_types = {
                        int((catalog.get(out_a) or {}).get("element_type", 0)),
                        int((catalog.get(out_b) or {}).get("element_type", 0)),
                    }
                    in_types = {in_a.element_type, in_b.element_type}
                    if out_types != in_types:
                        continue
                    swap_map = {out_a: in_a.player_id, out_b: in_b.player_id}
                    if not all(out_id in owned_ids for out_id in swap_map):
                        continue
                    trial_ids = [swap_map.get(pid, pid) for pid in owned_ids]
                    counts = _position_counts(trial_ids, catalog)
                    if not _squad_position_legal(counts, rules):
                        continue
                    moves = _synthetic_moves(
                            owned_ids=owned_ids,
                            outs=(out_a, out_b),
                            ins=(in_a, in_b),
                            bank_tenths=bank_tenths,
                            purchase_prices_tenths=purchase_prices_tenths,
                            catalog=catalog,
                            projections=projections,
                            rules=rules,
                    )
                    if moves is None:
                        continue
                    plan = _plan_from_moves(
                        owned_ids=owned_ids,
                        bank_tenths=bank_tenths,
                        free_transfers=free_transfers,
                        moves=moves,
                        projections=projections,
                        rules=rules,
                        base_xi=base_xi,
                        hit_points=hit_points,
                    )
                    if plan is not None and plan.affordable:
                        plans.append(plan)
    return plans


def _synthetic_moves(
    *,
    owned_ids: list[int],
    outs: tuple[int, int],
    ins: tuple[PlayerProjection, PlayerProjection],
    bank_tenths: int,
    purchase_prices_tenths: dict[str, int],
    catalog: dict[int, dict[str, Any]],
    projections: dict[int, PlayerProjection],
    rules: SeasonRules,
) -> tuple[TransferCandidate, TransferCandidate] | None:
    moves: list[TransferCandidate] = []
    running_bank = bank_tenths
    sells: list[tuple[int, int]] = []
    for out_id, inn in zip(outs, ins, strict=True):
        out_el = catalog.get(out_id) or {}
        out_proj = projections.get(out_id)
        if not out_proj:
            return None
        purchase = int(purchase_prices_tenths.get(str(out_id), out_el.get("now_cost") or out_proj.price_tenths))
        current = int(out_el.get("now_cost") or out_proj.price_tenths)
        sell = selling_price_tenths(purchase, current, rules)
        buy = int(catalog.get(inn.player_id, {}).get("now_cost") or inn.price_tenths)
        bank_after = budget_after_transfers(
            bank_tenths=running_bank,
            sells=sells + [(purchase, current)],
            buys_current_tenths=[buy],
            rules=rules,
        )
        if bank_after < 0:
            return None
        moves.append(
            TransferCandidate(
                out_id=out_id,
                in_id=inn.player_id,
                out_name=str(out_el.get("web_name") or out_proj.web_name),
                in_name=inn.web_name,
                element_type=int(out_el.get("element_type") or out_proj.element_type),
                sell_tenths=sell,
                buy_tenths=buy,
                bank_after_tenths=bank_after,
                bank_shortfall_tenths=0,
                affordable=True,
                delta_weighted_xp=0.0,
                delta_gw_xp=0.0,
                out_p_start=out_proj.p_start,
                in_p_start=inn.p_start,
                in_starts=True,
            )
        )
        running_bank = bank_after
        sells.append((purchase, current))
    return (moves[0], moves[1])


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
    risk_profile: RiskProfile = RiskProfile.MODERATE,
    catalog_for_tiebreak: dict[int, dict[str, Any]] | None = None,
    gameweek: int = 1,
    early_season_gws: int = 4,
    early_season_hit_margin_boost: float = 1.0,
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
            if plan.hit_cost > 0 and not hit_clears_horizon_bar(
                plan,
                margin=hit_horizon_margin(
                    risk_profile=risk_profile,
                    gameweek=gameweek,
                    early_season_gws=early_season_gws,
                    early_season_boost=early_season_hit_margin_boost,
                ),
            ):
                continue
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
                if plan.hit_cost > 0 and not hit_clears_horizon_bar(
                    plan, margin=hit_horizon_margin(risk_profile=risk_profile, gameweek=gameweek)
                ):
                    continue
                plans.append(plan)

    cross = rank_cross_position_plans(
        owned_ids=owned_ids,
        bank_tenths=bank_tenths,
        free_transfers=free_transfers,
        purchase_prices_tenths=purchase_prices_tenths,
        catalog=catalog,
        projections=projections,
        rules=rules,
        hit_points=hit_points,
        base_xi=base_xi,
    )
    hit_margin = hit_horizon_margin(
        risk_profile=risk_profile,
        gameweek=gameweek,
        early_season_gws=early_season_gws,
        early_season_boost=early_season_hit_margin_boost,
    )
    cross = [p for p in cross if hit_clears_horizon_bar(p, margin=hit_margin) or p.hit_cost == 0]
    plans.extend(cross)

    def sort_key(p: TransferPlan) -> tuple[float, float, float, float, int]:
        net_horizon = p.delta_weighted_xp - (p.hit_cost / 4.0)
        tie = _differential_tiebreak_key(
            p, catalog=catalog_for_tiebreak or catalog, risk_profile=risk_profile
        )
        return (-net_horizon, -p.delta_weighted_xp, tie, -p.delta_gw_xp, p.hit_cost)

    return sorted(plans, key=sort_key)


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
