"""Deterministic initial-squad selection for a fresh season.

Builds a legal 15-player squad under SeasonRules (quotas, club limit, budget)
that maximises weighted horizon expected points for the likely starting XI.
Bench value is deliberately discounted because bench players rarely score.
"""

from __future__ import annotations

from dataclasses import dataclass

from fpl_agent.projections.preseason import PlayerProjection
from fpl_agent.rules.season import SeasonRules

# Bench points are only collected via autosubs or Bench Boost.
BENCH_WEIGHT = 0.12
# Candidate pool size per position; keeps local search fast and deterministic.
POOL_PER_POSITION = 60
MAX_LOCAL_SEARCH_PASSES = 12
# Bounded breadth for the paired upgrade/downgrade move.
PAIR_MOVE_UPGRADES = 12
PAIR_MOVE_DOWNGRADES = 10
# Max picks from one position (5) plus spares for club-limit repair.
DOMINANCE_DEPTH = 8

ELEMENT_TYPE_TO_QUOTA_KEY = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


@dataclass(frozen=True)
class DraftSquad:
    players: tuple[PlayerProjection, ...]
    xi: tuple[PlayerProjection, ...]
    bench: tuple[PlayerProjection, ...]
    captain: PlayerProjection
    vice_captain: PlayerProjection
    total_cost_tenths: int
    bank_tenths: int
    objective: float
    formation: str


def _quota(rules: SeasonRules, element_type: int) -> tuple[int, int, int]:
    from fpl_agent.domain.models import Position

    position = Position(ELEMENT_TYPE_TO_QUOTA_KEY[element_type])
    quota = rules.position_quotas[position]
    return quota.squad_count, quota.min_starters, quota.max_starters


def select_best_xi(
    squad: list[PlayerProjection],
    rules: SeasonRules,
    *,
    gameweek_index: int | None = None,
) -> tuple[list[PlayerProjection], list[PlayerProjection], str]:
    """Pick the highest-scoring legal XI, plus ordered bench."""

    def score(player: PlayerProjection) -> float:
        if gameweek_index is None:
            return player.weighted_xp
        if gameweek_index < len(player.xp_by_gw):
            return player.xp_by_gw[gameweek_index]
        return 0.0

    by_type: dict[int, list[PlayerProjection]] = {1: [], 2: [], 3: [], 4: []}
    for player in squad:
        by_type[player.element_type].append(player)
    for players in by_type.values():
        players.sort(key=lambda p: (-score(p), p.player_id))

    best: tuple[float, list[PlayerProjection], str] | None = None
    _, def_min, def_max = _quota(rules, 2)
    _, mid_min, mid_max = _quota(rules, 3)
    _, fwd_min, fwd_max = _quota(rules, 4)

    for n_def in range(def_min, def_max + 1):
        for n_mid in range(mid_min, mid_max + 1):
            n_fwd = rules.starters - 1 - n_def - n_mid
            if n_fwd < fwd_min or n_fwd > fwd_max:
                continue
            if len(by_type[2]) < n_def or len(by_type[3]) < n_mid or len(by_type[4]) < n_fwd:
                continue
            if not by_type[1]:
                continue
            starters = (
                by_type[1][:1] + by_type[2][:n_def] + by_type[3][:n_mid] + by_type[4][:n_fwd]
            )
            total = sum(score(p) for p in starters)
            formation = f"{n_def}-{n_mid}-{n_fwd}"
            if best is None or total > best[0]:
                best = (total, starters, formation)

    if best is None:
        ordered = sorted(squad, key=lambda p: (-score(p), p.player_id))
        return ordered[: rules.starters], ordered[rules.starters :], "unknown"

    starter_ids = {p.player_id for p in best[1]}
    bench_outfield = sorted(
        [p for p in squad if p.player_id not in starter_ids and p.element_type != 1],
        key=lambda p: (-score(p), p.player_id),
    )
    bench_gk = [p for p in squad if p.player_id not in starter_ids and p.element_type == 1]
    return best[1], bench_gk + bench_outfield, best[2]


def squad_objective(squad: list[PlayerProjection], rules: SeasonRules) -> float:
    xi, bench, _ = select_best_xi(squad, rules)
    return sum(p.weighted_xp for p in xi) + BENCH_WEIGHT * sum(p.weighted_xp for p in bench)


def _is_legal(squad: list[PlayerProjection], rules: SeasonRules, budget_tenths: int) -> bool:
    if len(squad) != rules.squad_size:
        return False
    if sum(p.price_tenths for p in squad) > budget_tenths:
        return False
    counts: dict[int, int] = {}
    clubs: dict[int, int] = {}
    for player in squad:
        counts[player.element_type] = counts.get(player.element_type, 0) + 1
        clubs[player.team_id] = clubs.get(player.team_id, 0) + 1
    for element_type in (1, 2, 3, 4):
        squad_count, _, _ = _quota(rules, element_type)
        if counts.get(element_type, 0) != squad_count:
            return False
    return max(clubs.values(), default=0) <= rules.club_limit


def build_candidate_pool(
    projections: list[PlayerProjection],
    *,
    min_start_probability: float = 0.10,
) -> dict[int, list[PlayerProjection]]:
    """Per-position candidates: best value, best points-per-cost, and cheap fodder."""
    pool: dict[int, list[PlayerProjection]] = {}
    for element_type in (1, 2, 3, 4):
        available = [
            p
            for p in projections
            if p.element_type == element_type and p.p_start >= min_start_probability
        ]
        by_value = sorted(available, key=lambda p: (-p.weighted_xp, p.player_id))
        by_efficiency = sorted(
            available,
            key=lambda p: (-(p.weighted_xp / max(p.price_tenths, 1)), p.player_id),
        )
        cheapest = sorted(available, key=lambda p: (p.price_tenths, -p.weighted_xp, p.player_id))
        seen: dict[int, PlayerProjection] = {}
        for group, limit in (
            (by_value, POOL_PER_POSITION),
            (by_efficiency, POOL_PER_POSITION),
            (cheapest, 15),
        ):
            for player in group[:limit]:
                seen[player.player_id] = player
        pool[element_type] = sorted(seen.values(), key=lambda p: (-p.weighted_xp, p.player_id))
    return pool


def _greedy_seed(
    pool: dict[int, list[PlayerProjection]],
    rules: SeasonRules,
    budget_tenths: int,
) -> list[PlayerProjection]:
    """Fill quotas by efficiency while guaranteeing the remaining slots stay affordable."""
    squad: list[PlayerProjection] = []
    clubs: dict[int, int] = {}
    remaining_slots: dict[int, int] = {}
    for element_type in (1, 2, 3, 4):
        squad_count, _, _ = _quota(rules, element_type)
        remaining_slots[element_type] = squad_count

    cheapest_price: dict[int, int] = {
        element_type: min((p.price_tenths for p in players), default=40)
        for element_type, players in pool.items()
    }

    spent = 0
    # Fill the most valuable positions first so premiums are secured early.
    order = [3, 4, 2, 1]
    for element_type in order:
        candidates = sorted(
            pool[element_type],
            key=lambda p: (-(p.weighted_xp / max(p.price_tenths, 1)), -p.weighted_xp, p.player_id),
        )
        while remaining_slots[element_type] > 0:
            picked = None
            for candidate in candidates:
                if any(candidate.player_id == p.player_id for p in squad):
                    continue
                if clubs.get(candidate.team_id, 0) >= rules.club_limit:
                    continue
                slots_after = dict(remaining_slots)
                slots_after[element_type] -= 1
                floor_cost = sum(
                    cheapest_price[et] * n for et, n in slots_after.items() if n > 0
                )
                if spent + candidate.price_tenths + floor_cost > budget_tenths:
                    continue
                picked = candidate
                break
            if picked is None:
                # Fall back to the cheapest legal option for this slot.
                for candidate in sorted(candidates, key=lambda p: (p.price_tenths, p.player_id)):
                    if any(candidate.player_id == p.player_id for p in squad):
                        continue
                    if clubs.get(candidate.team_id, 0) >= rules.club_limit:
                        continue
                    picked = candidate
                    break
            if picked is None:
                break
            squad.append(picked)
            spent += picked.price_tenths
            clubs[picked.team_id] = clubs.get(picked.team_id, 0) + 1
            remaining_slots[element_type] -= 1
    return squad


NEG_INF = float("-inf")


def _knapsack_by_position(
    candidates: list[PlayerProjection],
    slots: int,
    max_budget: int,
) -> tuple[list[float], list[tuple[PlayerProjection, ...]]]:
    """Best value picking exactly `slots` players, indexed by exact total cost.

    Cardinality-constrained 0/1 knapsack. Iterating the slot count downwards
    guarantees each candidate is used at most once. Club limits are ignored
    here and repaired afterwards.
    """
    width = max_budget + 1
    values = [[NEG_INF] * width for _ in range(slots + 1)]
    picks: list[list[tuple[PlayerProjection, ...]]] = [[()] * width for _ in range(slots + 1)]
    values[0][0] = 0.0

    for candidate in candidates:
        cost = candidate.price_tenths
        if cost > max_budget:
            continue
        gain = candidate.weighted_xp
        # Descending slot count means row `count - 1` still excludes this
        # candidate, so the chosen set it carries can never repeat a player.
        for count in range(slots, 0, -1):
            previous_values = values[count - 1]
            previous_picks = picks[count - 1]
            current_values = values[count]
            current_picks = picks[count]
            for spend in range(max_budget - cost, -1, -1):
                base = previous_values[spend]
                if base == NEG_INF:
                    continue
                total = base + gain
                target = spend + cost
                if total > current_values[target]:
                    current_values[target] = total
                    current_picks[target] = (*previous_picks[spend], candidate)

    return values[slots], picks[slots]


def _pareto_indices(values: list[float]) -> list[int]:
    """Spend levels that beat every cheaper spend level."""
    keep: list[int] = []
    best = NEG_INF
    for spend, value in enumerate(values):
        if value > best:
            best = value
            keep.append(spend)
    return keep


def _combine(
    left: tuple[list[float], list[tuple[PlayerProjection, ...]]],
    right: tuple[list[float], list[tuple[PlayerProjection, ...]]],
    max_budget: int,
) -> tuple[list[float], list[tuple[PlayerProjection, ...]]]:
    left_values, left_picks = left
    right_values, right_picks = right
    width = max_budget + 1
    combined_values = [NEG_INF] * width
    combined_picks: list[tuple[PlayerProjection, ...]] = [()] * width

    right_keep = _pareto_indices(right_values)
    for left_spend in _pareto_indices(left_values):
        left_value = left_values[left_spend]
        for right_spend in right_keep:
            total_spend = left_spend + right_spend
            if total_spend > max_budget:
                break
            total = left_value + right_values[right_spend]
            if total > combined_values[total_spend]:
                combined_values[total_spend] = total
                combined_picks[total_spend] = (
                    *left_picks[left_spend],
                    *right_picks[right_spend],
                )
    return combined_values, combined_picks


def _dominant_candidates(
    players: list[PlayerProjection],
    *,
    max_needed: int = DOMINANCE_DEPTH,
) -> list[PlayerProjection]:
    """Keep only plausibly optimal candidates for a position.

    A player is dropped only when at least `max_needed` other candidates are
    both no more expensive and worth more points, since a single position can
    require up to that many picks (plus spares for club-limit repair).
    """
    by_price = sorted(players, key=lambda p: (p.price_tenths, -p.weighted_xp, p.player_id))
    kept: list[PlayerProjection] = []
    for player in by_price:
        dominators = sum(
            1
            for other in kept
            if other.price_tenths <= player.price_tenths
            and other.weighted_xp > player.weighted_xp
        )
        if dominators < max_needed:
            kept.append(player)
    return kept


def _repair_club_limit(
    squad: list[PlayerProjection],
    pool: dict[int, list[PlayerProjection]],
    rules: SeasonRules,
    budget: int,
) -> list[PlayerProjection] | None:
    """Swap out surplus club-mates until the club limit holds."""
    for _ in range(rules.squad_size):
        clubs: dict[int, list[PlayerProjection]] = {}
        for player in squad:
            clubs.setdefault(player.team_id, []).append(player)
        offender = next(
            (players for players in clubs.values() if len(players) > rules.club_limit), None
        )
        if offender is None:
            return squad
        drop = min(offender, key=lambda p: (p.weighted_xp, p.player_id))
        index = next(i for i, p in enumerate(squad) if p.player_id == drop.player_id)
        squad_ids = {p.player_id for p in squad}
        spent_others = sum(p.price_tenths for p in squad) - drop.price_tenths
        club_counts: dict[int, int] = {}
        for i, player in enumerate(squad):
            if i != index:
                club_counts[player.team_id] = club_counts.get(player.team_id, 0) + 1
        replacement = next(
            (
                candidate
                for candidate in pool[drop.element_type]
                if candidate.player_id not in squad_ids
                and club_counts.get(candidate.team_id, 0) < rules.club_limit
                and spent_others + candidate.price_tenths <= budget
            ),
            None,
        )
        if replacement is None:
            return None
        squad[index] = replacement
    return None


def _exact_seed(
    pool: dict[int, list[PlayerProjection]],
    rules: SeasonRules,
    budget: int,
) -> list[PlayerProjection] | None:
    """Solve the starting XI exactly per formation with cheap bench fodder reserved."""
    fodder: dict[int, list[PlayerProjection]] = {
        element_type: sorted(players, key=lambda p: (p.price_tenths, -p.weighted_xp, p.player_id))
        for element_type, players in pool.items()
    }
    # Keep both premium and cheap enablers: a strong XI usually mixes the two.
    starters_pool: dict[int, list[PlayerProjection]] = {
        element_type: _dominant_candidates(players)
        for element_type, players in pool.items()
    }

    _, def_min, def_max = _quota(rules, 2)
    _, mid_min, mid_max = _quota(rules, 3)
    _, fwd_min, fwd_max = _quota(rules, 4)

    best_squad: list[PlayerProjection] | None = None
    best_value = float("-inf")

    for n_def in range(def_min, def_max + 1):
        for n_mid in range(mid_min, mid_max + 1):
            n_fwd = rules.starters - 1 - n_def - n_mid
            if n_fwd < fwd_min or n_fwd > fwd_max:
                continue

            bench_slots = {
                1: _quota(rules, 1)[0] - 1,
                2: _quota(rules, 2)[0] - n_def,
                3: _quota(rules, 3)[0] - n_mid,
                4: _quota(rules, 4)[0] - n_fwd,
            }
            bench: list[PlayerProjection] = []
            for element_type, count in bench_slots.items():
                bench.extend(fodder[element_type][:count])
            bench_cost = sum(p.price_tenths for p in bench)
            xi_budget = budget - bench_cost
            if xi_budget <= 0:
                continue

            bench_ids = {p.player_id for p in bench}
            slots = {1: 1, 2: n_def, 3: n_mid, 4: n_fwd}
            table: tuple[list[float], list[tuple[PlayerProjection, ...]]] | None = None
            for element_type, count in slots.items():
                candidates = [
                    p for p in starters_pool[element_type] if p.player_id not in bench_ids
                ]
                position_table = _knapsack_by_position(candidates, count, xi_budget)
                table = (
                    position_table
                    if table is None
                    else _combine(table, position_table, xi_budget)
                )
            if table is None:
                continue
            values, picks = table
            best_spend = max(range(len(values)), key=lambda s: values[s])
            if values[best_spend] == NEG_INF:
                continue

            squad = [*picks[best_spend], *bench]
            repaired = _repair_club_limit(list(squad), pool, rules, budget)
            if repaired is None:
                continue
            value = squad_objective(repaired, rules)
            if value > best_value:
                best_value = value
                best_squad = repaired

    return best_squad


def _legal_replacement(
    squad: list[PlayerProjection],
    replacements: dict[int, PlayerProjection],
    rules: SeasonRules,
    budget: int,
) -> list[PlayerProjection] | None:
    """Apply {index: new_player} and return the trial squad when it stays legal."""
    trial = list(squad)
    for index, player in replacements.items():
        trial[index] = player
    ids = {p.player_id for p in trial}
    if len(ids) != len(trial):
        return None
    if sum(p.price_tenths for p in trial) > budget:
        return None
    clubs: dict[int, int] = {}
    for player in trial:
        clubs[player.team_id] = clubs.get(player.team_id, 0) + 1
        if clubs[player.team_id] > rules.club_limit:
            return None
    return trial


def _local_search(
    squad: list[PlayerProjection],
    pool: dict[int, list[PlayerProjection]],
    rules: SeasonRules,
    budget: int,
) -> tuple[list[PlayerProjection], float]:
    """Hill-climb with single swaps plus paired upgrade/downgrade moves.

    The paired move matters for FPL: affording a premium usually requires
    downgrading another slot in the same step, which no single swap can do.
    """
    best_objective = squad_objective(squad, rules)

    for _ in range(MAX_LOCAL_SEARCH_PASSES):
        best_move: tuple[float, dict[int, PlayerProjection]] | None = None

        for index, current in enumerate(squad):
            for candidate in pool[current.element_type][:PAIR_MOVE_UPGRADES]:
                if candidate.player_id == current.player_id:
                    continue
                trial = _legal_replacement(squad, {index: candidate}, rules, budget)
                if trial is None:
                    continue
                objective = squad_objective(trial, rules)
                if objective > best_objective + 1e-9 and (
                    best_move is None or objective > best_move[0]
                ):
                    best_move = (objective, {index: candidate})

        upgrades = {
            element_type: players[:PAIR_MOVE_UPGRADES] for element_type, players in pool.items()
        }
        downgrades = {
            element_type: sorted(players, key=lambda p: (p.price_tenths, -p.weighted_xp))[
                :PAIR_MOVE_DOWNGRADES
            ]
            for element_type, players in pool.items()
        }
        for up_index, up_current in enumerate(squad):
            for upgrade in upgrades[up_current.element_type]:
                if upgrade.price_tenths <= up_current.price_tenths:
                    continue
                if upgrade.weighted_xp <= up_current.weighted_xp:
                    continue
                shortfall = upgrade.price_tenths - up_current.price_tenths
                for down_index, down_current in enumerate(squad):
                    if down_index == up_index:
                        continue
                    for downgrade in downgrades[down_current.element_type]:
                        if down_current.price_tenths - downgrade.price_tenths < shortfall:
                            continue
                        trial = _legal_replacement(
                            squad,
                            {up_index: upgrade, down_index: downgrade},
                            rules,
                            budget,
                        )
                        if trial is None:
                            continue
                        objective = squad_objective(trial, rules)
                        if objective > best_objective + 1e-9 and (
                            best_move is None or objective > best_move[0]
                        ):
                            best_move = (
                                objective,
                                {up_index: upgrade, down_index: downgrade},
                            )

        if best_move is None:
            break
        objective, replacements = best_move
        for index, player in replacements.items():
            squad[index] = player
        best_objective = objective

    return squad, best_objective


def optimise_initial_squad(
    projections: list[PlayerProjection],
    rules: SeasonRules,
    *,
    budget_tenths: int | None = None,
) -> DraftSquad:
    budget = budget_tenths if budget_tenths is not None else rules.initial_budget_tenths
    pool = build_candidate_pool(projections)

    squad = _exact_seed(pool, rules, budget)
    if squad is None or not _is_legal(squad, rules, budget):
        squad = _greedy_seed(pool, rules, budget)
    if not _is_legal(squad, rules, budget):
        raise ValueError("could not build a legal initial squad from the candidate pool")

    squad, best_objective = _local_search(squad, pool, rules, budget)

    xi, bench, formation = select_best_xi(squad, rules, gameweek_index=0)
    captain_order = sorted(
        xi, key=lambda p: (-(p.xp_by_gw[0] if p.xp_by_gw else 0.0), p.player_id)
    )
    total_cost = sum(p.price_tenths for p in squad)
    return DraftSquad(
        players=tuple(sorted(squad, key=lambda p: (p.element_type, -p.weighted_xp, p.player_id))),
        xi=tuple(xi),
        bench=tuple(bench),
        captain=captain_order[0],
        vice_captain=captain_order[1],
        total_cost_tenths=total_cost,
        bank_tenths=budget - total_cost,
        objective=best_objective,
        formation=formation,
    )
