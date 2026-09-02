"""Replay and process grading."""

from __future__ import annotations

from fpl_agent.domain.models import Position
from fpl_agent.evaluation.replay import ProcessQuality, OutcomeQuality, grade_process_outcome, replay_scenario
from fpl_agent.rules.engine import LineupPick
from fpl_agent.rules.season import load_season_rules_2026_27


def test_replay_applies_captain_and_hit() -> None:
    rules = load_season_rules_2026_27()
    picks = [
        LineupPick(player_id=1, position=Position.GKP, is_starter=True, bench_order=None, is_captain=True),
        LineupPick(player_id=2, position=Position.DEF, is_starter=True, bench_order=None),
        LineupPick(player_id=3, position=Position.DEF, is_starter=True, bench_order=None),
        LineupPick(player_id=4, position=Position.DEF, is_starter=True, bench_order=None),
        LineupPick(player_id=5, position=Position.MID, is_starter=True, bench_order=None),
        LineupPick(player_id=6, position=Position.MID, is_starter=True, bench_order=None),
        LineupPick(player_id=7, position=Position.MID, is_starter=True, bench_order=None),
        LineupPick(player_id=8, position=Position.MID, is_starter=True, bench_order=None),
        LineupPick(player_id=9, position=Position.FWD, is_starter=True, bench_order=None),
        LineupPick(player_id=10, position=Position.FWD, is_starter=True, bench_order=None),
        LineupPick(player_id=11, position=Position.FWD, is_starter=True, bench_order=None),
        LineupPick(player_id=12, position=Position.GKP, is_starter=False, bench_order=0),
        LineupPick(player_id=13, position=Position.DEF, is_starter=False, bench_order=1),
        LineupPick(player_id=14, position=Position.MID, is_starter=False, bench_order=2),
        LineupPick(player_id=15, position=Position.FWD, is_starter=False, bench_order=3),
    ]
    points = {i: 2 for i in range(1, 16)}
    points[1] = 10
    minutes = {i: 90 for i in range(1, 16)}
    total = replay_scenario(
        picks=picks,
        player_points=points,
        minutes=minutes,
        hit_cost=4,
        bench_boost=False,
        triple_captain=False,
        rules=rules,
    )
    # Captain 10×2 + ten other starters at 2 each − 4 hit = 36
    assert total == 36


def test_grade_process_outcome_variance() -> None:
    process, outcome, _root = grade_process_outcome(
        recommendation_net=50,
        roll_net=40,
        actual_net=37,
        predeadline_ev_positive=True,
    )
    assert process == ProcessQuality.GOOD
    assert outcome == OutcomeQuality.NEGATIVE
