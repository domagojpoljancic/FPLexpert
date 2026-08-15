"""Season rules engine tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fpl_agent.domain.models import ChipHalf, ChipKind, Position
from fpl_agent.errors import AgentError
from fpl_agent.rules.diff import DriftSeverity, compare_rules_to_bootstrap
from fpl_agent.rules.engine import (
    LineupPick,
    SquadMember,
    available_chip_instances,
    free_transfer_rollover,
    manager_gameweek_total,
    resolve_autosubs,
    selling_price_tenths,
    validate_lineup,
    validate_squad,
)
from fpl_agent.rules.season import load_season_rules, load_season_rules_2026_27


@pytest.fixture
def rules():
    return load_season_rules_2026_27()


def _squad() -> list[SquadMember]:
    members: list[SquadMember] = []
    pid = 1
    # 2 GKP different clubs
    for club in (1, 2):
        members.append(SquadMember(pid, Position.GKP, club))
        pid += 1
    for club in (1, 2, 3, 4, 5):
        members.append(SquadMember(pid, Position.DEF, club))
        pid += 1
    for club in (6, 7, 8, 9, 10):
        members.append(SquadMember(pid, Position.MID, club))
        pid += 1
    for club in (11, 12, 13):
        members.append(SquadMember(pid, Position.FWD, club))
        pid += 1
    return members


def test_valid_squad(rules) -> None:
    assert validate_squad(_squad(), rules).ok


def test_club_limit(rules) -> None:
    members = _squad()
    # force 4 from club 1
    members[0] = SquadMember(1, Position.GKP, 1)
    members[2] = SquadMember(3, Position.DEF, 1)
    members[3] = SquadMember(4, Position.DEF, 1)
    members[7] = SquadMember(8, Position.MID, 1)
    assert not validate_squad(members, rules).ok


def _lineup(n_def: int, n_mid: int, n_fwd: int) -> list[LineupPick]:
    """Build a 15-man lineup for formation checks (squad composition may be illegal)."""
    picks: list[LineupPick] = []
    pid = 1
    picks.append(LineupPick(pid, Position.GKP, True, None, True, False))
    pid += 1
    for _ in range(n_def):
        picks.append(LineupPick(pid, Position.DEF, True, None, False, pid == 2))
        pid += 1
    for _ in range(n_mid):
        picks.append(LineupPick(pid, Position.MID, True, None))
        pid += 1
    for _ in range(n_fwd):
        picks.append(LineupPick(pid, Position.FWD, True, None))
        pid += 1
    picks.append(LineupPick(pid, Position.GKP, False, 0))
    pid += 1
    for order, pos in enumerate((Position.DEF, Position.MID, Position.FWD), start=1):
        picks.append(LineupPick(pid, pos, False, order))
        pid += 1
    return picks


@pytest.mark.parametrize(
    "n_def,n_mid,n_fwd,ok",
    [
        (3, 4, 3, True),
        (3, 5, 2, True),
        (4, 4, 2, True),
        (4, 3, 3, True),
        (5, 3, 2, True),
        (5, 2, 3, True),
        (2, 5, 3, False),
        (5, 5, 0, False),
    ],
)
def test_formations(rules, n_def, n_mid, n_fwd, ok) -> None:
    picks = _lineup(n_def, n_mid, n_fwd)
    assert len(picks) == 15
    assert validate_lineup(picks, rules).ok is ok


@pytest.mark.parametrize(
    "purchase,current,expected",
    [
        (50, 51, 50),  # +0.1 -> +0
        (50, 52, 51),  # +0.2 -> +0.1
        (50, 53, 51),  # +0.3 -> +0.1
        (50, 54, 52),  # +0.4 -> +0.2
        (50, 49, 49),  # fall passes through
        (50, 50, 50),
    ],
)
def test_selling_price(rules, purchase, current, expected) -> None:
    assert selling_price_tenths(purchase, current, rules) == expected


@pytest.mark.parametrize("ft", [0, 1, 2, 3, 4, 5])
def test_ft_rollover(rules, ft) -> None:
    nxt, hit = free_transfer_rollover(previous_ft=ft, transfers_made=0, rules=rules)
    assert hit == 0
    assert 1 <= nxt <= rules.max_banked_free_transfers


def test_hit_calculation(rules) -> None:
    nxt, hit = free_transfer_rollover(previous_ft=1, transfers_made=3, rules=rules)
    assert hit == 8
    assert nxt == 1  # 0 remaining + 1


def test_ft_preserved_on_wildcard(rules) -> None:
    nxt, hit = free_transfer_rollover(
        previous_ft=3, transfers_made=10, rules=rules, wildcard_or_free_hit=True
    )
    assert hit == 0
    assert nxt == 4


def test_chips_eight_instances(rules) -> None:
    assert len(rules.chip_instances) == 8


def test_fh_not_gw1(rules) -> None:
    avail = available_chip_instances(event=1, used=set(), rules=rules)
    assert (ChipKind.FREE_HIT, ChipHalf.FIRST) not in avail
    assert (ChipKind.BENCH_BOOST, ChipHalf.FIRST) in avail


def test_consecutive_fh_blocked(rules) -> None:
    avail = available_chip_instances(
        event=20, used=set(), rules=rules, previous_event_chip=ChipKind.FREE_HIT
    )
    assert all(k != ChipKind.FREE_HIT for k, _ in avail)


def test_first_half_expiry(rules) -> None:
    avail = available_chip_instances(event=20, used=set(), rules=rules)
    assert all(h == ChipHalf.SECOND for _, h in avail)


def test_autosub_gk_and_formation(rules) -> None:
    picks = [
        LineupPick(1, Position.GKP, True, None, True, False),
        LineupPick(2, Position.DEF, True, None, False, True),
        LineupPick(3, Position.DEF, True, None),
        LineupPick(4, Position.DEF, True, None),
        LineupPick(5, Position.MID, True, None),
        LineupPick(6, Position.MID, True, None),
        LineupPick(7, Position.MID, True, None),
        LineupPick(8, Position.MID, True, None),
        LineupPick(9, Position.FWD, True, None),
        LineupPick(10, Position.FWD, True, None),
        LineupPick(11, Position.FWD, True, None),
        LineupPick(12, Position.GKP, False, 0),
        LineupPick(13, Position.DEF, False, 1),
        LineupPick(14, Position.MID, False, 2),
        LineupPick(15, Position.FWD, False, 3),
    ]
    minutes = {i: 90 for i in range(1, 16)}
    minutes[1] = 0
    minutes[11] = 0
    minutes[15] = 0  # cannot sub FWD for FWD if formation breaks? 3 fwd already - skip
    # bench1 DEF can replace a DEF who didn't play — set def 4 out
    minutes[4] = 0
    minutes[13] = 90
    result = resolve_autosubs(picks, minutes=minutes, rules=rules)
    assert 12 in result.final_starters  # GK sub
    assert 13 in result.final_starters


def test_triple_captain_and_bench_boost(rules) -> None:
    picks = [
        LineupPick(1, Position.GKP, True, None, True, False),
        LineupPick(2, Position.DEF, True, None, False, True),
        LineupPick(3, Position.DEF, True, None),
        LineupPick(4, Position.DEF, True, None),
        LineupPick(5, Position.MID, True, None),
        LineupPick(6, Position.MID, True, None),
        LineupPick(7, Position.MID, True, None),
        LineupPick(8, Position.MID, True, None),
        LineupPick(9, Position.FWD, True, None),
        LineupPick(10, Position.FWD, True, None),
        LineupPick(11, Position.FWD, True, None),
        LineupPick(12, Position.GKP, False, 0),
        LineupPick(13, Position.DEF, False, 1),
        LineupPick(14, Position.MID, False, 2),
        LineupPick(15, Position.DEF, False, 3),
    ]
    points = {i: 2 for i in range(1, 16)}
    points[1] = 10
    points[13] = 6
    minutes = {i: 90 for i in range(1, 16)}
    total = manager_gameweek_total(
        player_points=points,
        picks=picks,
        minutes=minutes,
        hit_cost=4,
        bench_boost=True,
        triple_captain=True,
        rules=rules,
    )
    # XI 11 players: captain 10*3=30, others 10*2=20, bench 3 outfield+gk = 4*2? bench 12,13,14,15 = 8
    # starters non-captain: 10 players * 2 = 20; captain 30; bench 2+6+2+2=12; hit -4 => 58
    assert total == 58


def test_unsupported_season() -> None:
    with pytest.raises(AgentError):
        load_season_rules("1999-00")


def test_rules_diff_clean() -> None:
    boot = json.loads(Path("tests/fixtures/bootstrap_static_reduced.json").read_text())
    sev, _ = compare_rules_to_bootstrap(load_season_rules_2026_27(), boot)
    assert sev in {DriftSeverity.NONE, DriftSeverity.NON_BREAKING}


def test_rules_diff_material() -> None:
    boot = json.loads(Path("tests/fixtures/bootstrap_static_reduced.json").read_text())
    boot["game_settings"]["squad_squadsize"] = 16
    sev, notes = compare_rules_to_bootstrap(load_season_rules_2026_27(), boot)
    assert sev == DriftSeverity.MATERIAL
    assert notes
