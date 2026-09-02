"""Bounded multi-gameweek scenario generation (deterministic)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from fpl_agent.domain.models import Executability, RiskProfile
from fpl_agent.domain.run_state import stable_json_hash
from fpl_agent.projections.preseason import PlayerProjection
from fpl_agent.rules.season import SeasonRules
from fpl_agent.strategy.transfers import TransferPlan, _plan_summary, rank_transfer_plans


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class TransferMove:
    out_id: int
    in_id: int
    sell_tenths: int
    buy_tenths: int


@dataclass
class Scenario:
    scenario_id: str
    risk_level: RiskLevel
    transfers: list[TransferMove]
    hit_cost: int
    bank_after: int | None
    projected_by_gw: list[float]
    weighted_gross: float
    weighted_net: float
    gain_vs_roll: float
    break_even_gw: int | None
    sensitivities: dict[str, float]
    future_moves: list[str]
    assumptions: list[str]
    legality_ok: bool
    executability: Executability
    chip: str | None = None
    captain_id: int | None = None
    vice_id: int | None = None
    xi: list[int] = field(default_factory=list)
    bench: list[int] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class SearchDiagnostics:
    candidate_pool: int
    retained: int
    pruned: list[str]
    beam_width: int


def _scenario_id(parts: dict[str, Any]) -> str:
    return stable_json_hash(parts)[:16]


def select_xi_by_xp(
    squad: list[dict[str, Any]],
    xp: dict[int, float],
    rules: SeasonRules,
) -> tuple[list[int], list[int]]:
    """Greedy formation-feasible XI by expected points."""
    from itertools import combinations

    by_pos: dict[str, list[dict[str, Any]]] = {"GKP": [], "DEF": [], "MID": [], "FWD": []}
    for p in squad:
        by_pos[str(p["position"])].append(p)
    for pos in by_pos:
        by_pos[pos].sort(key=lambda p: xp.get(int(p["player_id"]), 0.0), reverse=True)

    best: tuple[float, list[int], list[int]] | None = None
    # enumerate legal formation counts
    for n_def in range(3, 6):
        for n_mid in range(2, 6):
            n_fwd = 10 - n_def - n_mid  # 11 total with 1 GK
            if n_fwd < 1 or n_fwd > 3:
                continue
            if len(by_pos["DEF"]) < n_def or len(by_pos["MID"]) < n_mid or len(by_pos["FWD"]) < n_fwd:
                continue
            if len(by_pos["GKP"]) < 1:
                continue
            for defs in combinations(by_pos["DEF"], n_def):
                for mids in combinations(by_pos["MID"], n_mid):
                    for fwds in combinations(by_pos["FWD"], n_fwd):
                        gk = by_pos["GKP"][0]
                        starters = [gk, *defs, *mids, *fwds]
                        starter_ids = [int(p["player_id"]) for p in starters]
                        score = sum(xp.get(i, 0.0) for i in starter_ids)
                        bench_players = [p for p in squad if int(p["player_id"]) not in starter_ids]
                        # GK on bench first then outfield by xp
                        bench_gk = [p for p in bench_players if p["position"] == "GKP"]
                        bench_out = sorted(
                            [p for p in bench_players if p["position"] != "GKP"],
                            key=lambda p: xp.get(int(p["player_id"]), 0.0),
                            reverse=True,
                        )
                        bench_ids = [int(p["player_id"]) for p in bench_gk[:1] + bench_out]
                        if best is None or score > best[0]:
                            best = (score, starter_ids, bench_ids)
    if best is None:
        ids = [int(p["player_id"]) for p in squad]
        return ids[:11], ids[11:]
    return best[1], best[2]


def _projected_xi_by_gw(
    owned_ids: list[int],
    projections: dict[int, PlayerProjection],
    rules: SeasonRules,
    horizon: int,
) -> list[float]:
    from fpl_agent.strategy.draft import select_best_xi

    players = [projections[pid] for pid in owned_ids if pid in projections]
    if len(players) != len(owned_ids):
        return [0.0] * horizon
    out: list[float] = []
    for index in range(horizon):
        xi, _, _ = select_best_xi(players, rules, gameweek_index=index)
        total = 0.0
        for p in xi:
            if index < len(p.xp_by_gw):
                total += float(p.xp_by_gw[index])
        out.append(total)
    return out


def break_even_gw(
    base_by_gw: list[float],
    new_by_gw: list[float],
    hit_cost: int,
) -> int | None:
    """GW index (1-based within horizon) where cumulative gain covers the hit."""
    if hit_cost <= 0:
        return None
    cumulative = 0.0
    for index, (base, new) in enumerate(zip(base_by_gw, new_by_gw, strict=False)):
        cumulative += new - base
        if cumulative >= hit_cost:
            return index + 1
    return None


def _scenario_from_plan(
    *,
    plan: TransferPlan,
    roll: Scenario,
    rules: SeasonRules,
    owned_ids: list[int],
    projections: dict[int, PlayerProjection],
    weights: list[float],
    horizon: int,
    base_by_gw: list[float],
) -> Scenario:
    new_ids = list(owned_ids)
    for move in plan.moves:
        new_ids = [move.in_id if pid == move.out_id else pid for pid in new_ids]
    projected_by_gw = _projected_xi_by_gw(new_ids, projections, rules, horizon)
    weighted_gross = sum(w * x for w, x in zip(weights, projected_by_gw, strict=True))
    weighted_net = weighted_gross - plan.hit_cost
    gain = weighted_net - roll.weighted_net
    be_gw = break_even_gw(base_by_gw, projected_by_gw, plan.hit_cost)
    transfers = [
        TransferMove(
            out_id=m.out_id,
            in_id=m.in_id,
            sell_tenths=m.sell_tenths,
            buy_tenths=m.buy_tenths,
        )
        for m in plan.moves
    ]
    future: list[str] = []
    if len(plan.moves) == 1 and plan.hit_cost == 0:
        future.append("optional second move next GW if value persists")
    if plan.hit_cost > 0:
        future.append(f"hit pays back by GW+{be_gw}" if be_gw else "hit may not pay back within horizon")
    risk = RiskLevel.LOW if plan.hit_cost == 0 else RiskLevel.MEDIUM
    return Scenario(
        scenario_id=_scenario_id({"type": "plan", "moves": [(m.out_id, m.in_id) for m in plan.moves]}),
        risk_level=risk,
        transfers=transfers,
        hit_cost=plan.hit_cost,
        bank_after=plan.bank_after_tenths,
        projected_by_gw=projected_by_gw,
        weighted_gross=weighted_gross,
        weighted_net=weighted_net,
        gain_vs_roll=gain,
        break_even_gw=be_gw,
        sensitivities={
            "horizon_weighted_minus_10pct": round(weighted_net * 0.9, 3),
        },
        future_moves=future,
        assumptions=[_plan_summary(plan)],
        legality_ok=plan.affordable,
        executability=Executability.EXECUTABLE,
        notes=[_plan_summary(plan)],
    )


def generate_scenarios(
    *,
    rules: SeasonRules,
    executability: Executability,
    bank_tenths: int | None,
    free_transfers: int | None,
    squad: list[dict[str, Any]],
    xp_by_player: dict[int, list[float]],
    weights: list[float],
    max_hit: int,
    hits_enabled: bool,
    risk_profile: RiskProfile = RiskProfile.MODERATE,
    beam_width: int = 20,
    owned_ids: list[int] | None = None,
    catalog: dict[int, dict[str, Any]] | None = None,
    projections: dict[int, PlayerProjection] | None = None,
    purchase_prices_tenths: dict[str, int] | None = None,
) -> tuple[list[Scenario], SearchDiagnostics]:
    pruned: list[str] = []
    if executability == Executability.INSUFFICIENT:
        return [], SearchDiagnostics(0, 0, ["insufficient_team_state"], beam_width)

    horizon = len(weights)
    def weighted(pid: int) -> float:
        series = xp_by_player.get(pid, [0.0] * horizon)
        series = (series + [0.0] * horizon)[:horizon]
        return sum(w * x for w, x in zip(weights, series, strict=True))

    squad_xp = {int(p["player_id"]): weighted(int(p["player_id"])) for p in squad}
    xi, bench = select_xi_by_xp(squad, squad_xp, rules)
    roll_by_gw = []
    for i in range(horizon):
        roll_by_gw.append(sum(xp_by_player.get(pid, [0.0] * horizon)[i] if i < len(xp_by_player.get(pid, [])) else 0.0 for pid in xi))
        # approximate: use XI only for roll baseline
    # Better: sum starter xp per gw
    roll_by_gw = []
    for i in range(horizon):
        total = 0.0
        for pid in xi:
            series = xp_by_player.get(pid, [])
            total += series[i] if i < len(series) else 0.0
        roll_by_gw.append(total)
    roll_gross = sum(w * x for w, x in zip(weights, roll_by_gw, strict=True))

    exec_status = executability
    roll = Scenario(
        scenario_id=_scenario_id({"type": "roll", "xi": xi}),
        risk_level=RiskLevel.LOW,
        transfers=[],
        hit_cost=0,
        bank_after=bank_tenths,
        projected_by_gw=roll_by_gw,
        weighted_gross=roll_gross,
        weighted_net=roll_gross,
        gain_vs_roll=0.0,
        break_even_gw=None,
        sensitivities={"ft_bank_option_value": round(roll_gross * 0.02, 3)},
        future_moves=["roll: bank FT toward 5 for flexibility"],
        assumptions=["no transfers", "FT bank valued for optionality"],
        legality_ok=True,
        executability=exec_status,
        captain_id=max(xi, key=lambda pid: squad_xp.get(pid, 0.0)) if xi else None,
        vice_id=sorted(xi, key=lambda pid: squad_xp.get(pid, 0.0), reverse=True)[1] if len(xi) > 1 else None,
        xi=xi,
        bench=bench,
    )
    scenarios = [roll]
    candidates = 1

    if free_transfers is None or bank_tenths is None:
        pruned.append("finance_unknown_limits_transfer_branch_detail")
        # still allow conditional annotated variants without claiming affordability
        for p in squad[:3]:
            candidates += 1
            sid = _scenario_id({"type": "conditional_ft", "out": p["player_id"]})
            scenarios.append(
                Scenario(
                    scenario_id=sid,
                    risk_level=RiskLevel.MEDIUM,
                    transfers=[],
                    hit_cost=0,
                    bank_after=None,
                    projected_by_gw=roll_by_gw,
                    weighted_gross=roll_gross,
                    weighted_net=roll_gross,
                    gain_vs_roll=0.0,
                    break_even_gw=None,
                    sensitivities={},
                    future_moves=["specify bank/FT to evaluate transfer"],
                    assumptions=["conditional: finance unknown"],
                    legality_ok=False,
                    executability=Executability.CONDITIONAL_ONLY,
                    notes=["conditional_only"],
                )
            )
        scenarios = scenarios[:beam_width]
        return scenarios, SearchDiagnostics(candidates, len(scenarios), pruned, beam_width)

    # Transfer search when finance and projection context are available.
    if (
        owned_ids
        and catalog
        and projections
        and purchase_prices_tenths is not None
        and free_transfers is not None
        and bank_tenths is not None
    ):
        plans = rank_transfer_plans(
            owned_ids=owned_ids,
            bank_tenths=bank_tenths,
            free_transfers=free_transfers,
            purchase_prices_tenths=purchase_prices_tenths,
            catalog=catalog,
            projections=projections,
            rules=rules,
            hits_enabled=hits_enabled,
            max_hit=max_hit,
            risk_profile=risk_profile,
            catalog_for_tiebreak=catalog,
        )
        base_by_gw = roll_by_gw
        for plan in plans[: max(1, beam_width - 1)]:
            candidates += 1
            scenarios.append(
                _scenario_from_plan(
                    plan=plan,
                    roll=roll,
                    rules=rules,
                    owned_ids=owned_ids,
                    projections=projections,
                    weights=weights,
                    horizon=horizon,
                    base_by_gw=base_by_gw,
                )
            )
    elif hits_enabled:
        pruned.append("hits_evaluated_in_transfer_plans")

    scenarios.sort(key=lambda s: (s.weighted_net, s.gain_vs_roll), reverse=True)
    # ensure roll retained
    if not any(s.transfers == [] and s.hit_cost == 0 and "conditional" not in s.notes for s in scenarios):
        scenarios.insert(0, roll)
    retained = scenarios[:beam_width]
    # force roll present
    if roll.scenario_id not in {s.scenario_id for s in retained}:
        retained[-1] = roll
    return retained, SearchDiagnostics(candidates, len(retained), pruned, beam_width)
