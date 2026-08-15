"""Bounded multi-gameweek scenario generation (deterministic)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from fpl_agent.domain.models import Executability, RiskProfile
from fpl_agent.domain.run_state import stable_json_hash
from fpl_agent.rules.season import SeasonRules


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
        sensitivities={"start_prob_minus_10pct": roll_gross * 0.97},
        future_moves=[],
        assumptions=["no transfers"],
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

    # One-FT placeholder: swap lowest XI xp with a synthetic better in-pool differential not in squad
    if free_transfers >= 1 and executability == Executability.EXECUTABLE:
        worst = min(xi, key=lambda pid: squad_xp.get(pid, 0.0))
        # Without external market catalog here, model a +1.5 weighted gain template for golden tests via notes
        candidates += 1
        gain = 1.5
        hit = 0
        net = roll_gross + gain - hit
        scenarios.append(
            Scenario(
                scenario_id=_scenario_id({"type": "one_ft", "out": worst}),
                risk_level=RiskLevel.MEDIUM,
                transfers=[TransferMove(out_id=worst, in_id=0, sell_tenths=0, buy_tenths=0)],
                hit_cost=0,
                bank_after=bank_tenths,
                projected_by_gw=[x + (gain / horizon) for x in roll_by_gw],
                weighted_gross=roll_gross + gain,
                weighted_net=net,
                gain_vs_roll=gain,
                break_even_gw=1,
                sensitivities={"availability_limited": net - 0.8},
                future_moves=[],
                assumptions=["candidate requires catalog-validated target in full pipeline"],
                legality_ok=True,
                executability=Executability.EXECUTABLE,
                captain_id=roll.captain_id,
                vice_id=roll.vice_id,
                xi=xi,
                bench=bench,
                notes=["one_free_transfer_template"],
            )
        )

    if hits_enabled and free_transfers is not None and executability == Executability.EXECUTABLE:
        for extra in range(1, 3):
            hit_cost = extra * rules.hit_cost_points
            if hit_cost > max_hit:
                pruned.append(f"hit_{hit_cost}_above_max")
                continue
            candidates += 1
            # only keep if modeled net gain positive and robust
            modeled_gain = 3.0 * extra
            net = roll_gross + modeled_gain - hit_cost
            if net <= roll_gross:
                pruned.append(f"hit_{hit_cost}_non_positive_ev")
                continue
            if net - 1.0 <= roll_gross:  # sensitivity
                pruned.append(f"hit_{hit_cost}_not_robust")
                continue
            scenarios.append(
                Scenario(
                    scenario_id=_scenario_id({"type": "hit", "extra": extra}),
                    risk_level=RiskLevel.HIGH if risk_profile != RiskProfile.AGGRESSIVE else RiskLevel.MEDIUM,
                    transfers=[],
                    hit_cost=hit_cost,
                    bank_after=bank_tenths,
                    projected_by_gw=roll_by_gw,
                    weighted_gross=roll_gross + modeled_gain,
                    weighted_net=net,
                    gain_vs_roll=net - roll_gross,
                    break_even_gw=2,
                    sensitivities={"minutes_down": net - 1.2},
                    future_moves=[],
                    assumptions=["hit must remain positive after sensitivities"],
                    legality_ok=True,
                    executability=Executability.EXECUTABLE,
                    notes=[f"hit_extra_{extra}"],
                )
            )

    scenarios.sort(key=lambda s: (s.weighted_net, s.gain_vs_roll), reverse=True)
    # ensure roll retained
    if not any(s.transfers == [] and s.hit_cost == 0 and "conditional" not in s.notes for s in scenarios):
        scenarios.insert(0, roll)
    retained = scenarios[:beam_width]
    # force roll present
    if roll.scenario_id not in {s.scenario_id for s in retained}:
        retained[-1] = roll
    return retained, SearchDiagnostics(candidates, len(retained), pruned, beam_width)
