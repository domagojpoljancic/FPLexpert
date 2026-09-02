"""Initial-squad optimiser tests, including exactness against brute force."""

from __future__ import annotations

from itertools import combinations

import pytest

from fpl_agent.projections.preseason import PlayerProjection
from fpl_agent.rules.season import load_season_rules_2026_27
from fpl_agent.strategy.draft import (
    _dominant_candidates,
    _knapsack_by_position,
    build_candidate_pool,
    optimise_initial_squad,
    select_best_xi,
)


def _player(pid: int, element_type: int, price: int, xp: float, team: int) -> PlayerProjection:
    return PlayerProjection(
        player_id=pid,
        web_name=f"P{pid}",
        team_id=team,
        element_type=element_type,
        price_tenths=price,
        p_start=0.9,
        expected_minutes=70.0,
        points_per_90=xp / 6,
        xp_by_gw=(xp / 6,) * 6,
        weighted_xp=xp,
    )


def _synthetic_pool() -> list[PlayerProjection]:
    players: list[PlayerProjection] = []
    pid = 1
    # Enough players per position to build many legal squads across 12 clubs.
    for element_type, count in ((1, 8), (2, 16), (3, 16), (4, 10)):
        for i in range(count):
            price = 40 + (i % 8) * 5
            xp = 4.0 + (price - 40) * 0.18 + (i % 3)
            players.append(_player(pid, element_type, price, xp, team=(pid % 12) + 1))
            pid += 1
    return players


def test_knapsack_matches_brute_force() -> None:
    candidates = [
        _player(1, 3, 45, 5.0, 1),
        _player(2, 3, 60, 9.0, 2),
        _player(3, 3, 75, 11.0, 3),
        _player(4, 3, 50, 7.5, 4),
        _player(5, 3, 100, 14.0, 5),
        _player(6, 3, 55, 6.0, 6),
    ]
    budget = 190
    slots = 3
    values, picks = _knapsack_by_position(candidates, slots, budget)

    best_brute = max(
        (
            sum(p.weighted_xp for p in combo)
            for combo in combinations(candidates, slots)
            if sum(p.price_tenths for p in combo) <= budget
        ),
        default=float("-inf"),
    )
    best_dp = max(values)
    assert best_dp == pytest.approx(best_brute)

    best_spend = max(range(len(values)), key=lambda s: values[s])
    chosen = picks[best_spend]
    assert len({p.player_id for p in chosen}) == slots
    assert sum(p.price_tenths for p in chosen) <= budget


def test_dominance_pruning_keeps_multi_slot_options() -> None:
    # Three identical-price players: all must survive when several are needed.
    players = [
        _player(1, 2, 50, 9.0, 1),
        _player(2, 2, 50, 8.5, 2),
        _player(3, 2, 50, 8.0, 3),
        _player(4, 2, 50, 7.5, 4),
    ]
    kept = _dominant_candidates(players, max_needed=3)
    assert len(kept) >= 3


def test_optimised_squad_is_legal_and_unique() -> None:
    rules = load_season_rules_2026_27()
    squad = optimise_initial_squad(_synthetic_pool(), rules)

    ids = [p.player_id for p in squad.players]
    assert len(ids) == 15
    assert len(set(ids)) == 15, "no player may be selected twice"
    assert squad.total_cost_tenths <= rules.initial_budget_tenths
    assert squad.bank_tenths >= 0

    counts: dict[int, int] = {}
    clubs: dict[int, int] = {}
    for player in squad.players:
        counts[player.element_type] = counts.get(player.element_type, 0) + 1
        clubs[player.team_id] = clubs.get(player.team_id, 0) + 1
    assert counts == {1: 2, 2: 5, 3: 5, 4: 3}
    assert max(clubs.values()) <= rules.club_limit

    assert len(squad.xi) == 11
    assert len(squad.bench) == 4
    assert squad.captain.player_id != squad.vice_captain.player_id
    assert squad.captain.player_id in {p.player_id for p in squad.xi}


def test_selected_xi_respects_formation_rules() -> None:
    rules = load_season_rules_2026_27()
    squad = optimise_initial_squad(_synthetic_pool(), rules)
    xi, bench, formation = select_best_xi(list(squad.players), rules)

    by_type: dict[int, int] = {}
    for player in xi:
        by_type[player.element_type] = by_type.get(player.element_type, 0) + 1
    assert by_type[1] == 1
    assert 3 <= by_type.get(2, 0) <= 5
    assert 2 <= by_type.get(3, 0) <= 5
    assert 1 <= by_type.get(4, 0) <= 3
    assert len(bench) == 4
    assert bench[0].element_type == 1, "reserve goalkeeper is listed first"
    assert formation != "unknown"


def test_optimiser_is_deterministic() -> None:
    rules = load_season_rules_2026_27()
    pool = _synthetic_pool()
    first = optimise_initial_squad(pool, rules)
    second = optimise_initial_squad(pool, rules)
    assert [p.player_id for p in first.players] == [p.player_id for p in second.players]
    assert first.objective == second.objective


def test_candidate_pool_excludes_non_starters() -> None:
    benched = _player(999, 3, 45, 6.0, 1)
    benched = PlayerProjection(**{**benched.__dict__, "p_start": 0.0})
    pool = build_candidate_pool([*_synthetic_pool(), benched])
    assert all(p.player_id != 999 for p in pool[3])


def test_bench_orders_higher_start_probability_first() -> None:
    rules = load_season_rules_2026_27()
    squad: list[PlayerProjection] = []
    pid = 1
    for team in (1, 2):
        squad.append(_player(pid, 1, 45, 8.0, team))
        pid += 1
    for i in range(5):
        xp = 8.0 if i < 4 else 1.0
        p_start = 0.9 if i < 4 else 0.85
        row = _player(pid, 2, 45, xp, 3 + i)
        squad.append(PlayerProjection(**{**row.__dict__, "p_start": p_start}))
        pid += 1
    for i in range(5):
        squad.append(_player(pid, 3, 50, 8.0, 8 + i))
        pid += 1
    likely = _player(pid, 4, 45, 1.0, 13)
    likely = PlayerProjection(**{**likely.__dict__, "p_start": 0.70})
    squad.append(likely)
    pid += 1
    unlikely = _player(pid, 4, 45, 0.9, 14)
    unlikely = PlayerProjection(**{**unlikely.__dict__, "p_start": 0.10})
    squad.append(unlikely)
    pid += 1
    squad.append(_player(pid, 4, 70, 9.0, 15))

    _xi, bench, _ = select_best_xi(squad, rules)
    outfield = [p for p in bench if p.element_type != 1]
    assert outfield[0].p_start >= outfield[-1].p_start
    names = [p.player_id for p in outfield]
    assert names.index(likely.player_id) < names.index(unlikely.player_id)
