"""Extended scorecard and replay tests."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from fpl_agent.cli import app
from fpl_agent.evaluation.ledger import DecisionRecord, build_decision_id, write_decision_record
from fpl_agent.evaluation.replay import ProcessQuality, RootCause, grade_process_outcome
from fpl_agent.evaluation.scorecard import scorecard_from_plan

runner = CliRunner()


def test_scorecard_reports_xp_vs_actual() -> None:
    plan = {
        "ok": True,
        "model_captain": {"player_id": 1, "web_name": "A", "xp_next": 6.0},
        "xi": [{"player_id": 1, "web_name": "A", "xp_next": 6.0}],
    }
    card = scorecard_from_plan(gameweek=1, weekly_plan=plan, player_points={1: 4})
    assert card.predicted_xi_xp == 6.0
    assert card.predicted_captain_xp == 12.0


def test_process_vs_outcome_split() -> None:
    process, outcome, root = grade_process_outcome(
        recommendation_net=50,
        roll_net=40,
        actual_net=37,
        predeadline_ev_positive=True,
    )
    assert process == ProcessQuality.GOOD
    assert outcome.value == "negative"
    assert root == RootCause.SOUND_PROCESS_NORMAL_VARIANCE


def test_scorecard_window_scores_transfer_path() -> None:
    plan = {
        "ok": True,
        "model_captain": {"player_id": 1, "web_name": "A", "xp_next": 5.0},
        "xi": [{"player_id": 1, "web_name": "A", "xp_next": 5.0}],
        "horizon": [{"gw": 1, "xi_xp": 55.0}, {"gw": 6, "xi_xp": 48.0}],
    }
    card = scorecard_from_plan(gameweek=1, weekly_plan=plan, player_points={1: 5})
    assert card.horizon_window_delta == 7.0


def test_replay_cli_offline(tmp_path: Path) -> None:
    from fpl_agent.domain.models import Position
    from fpl_agent.evaluation.replay import replay_scenario
    from fpl_agent.evaluation.scorecard import points_from_live_payload
    from fpl_agent.rules.engine import LineupPick
    from fpl_agent.rules.season import load_season_rules_2026_27

    live = tmp_path / "live.json"
    live.write_text(
        json.dumps({"elements": [{"id": i, "stats": {"total_points": 2}} for i in range(1, 16)]}),
        encoding="utf-8",
    )
    player_points = points_from_live_payload(json.loads(live.read_text(encoding="utf-8")))
    points = {i: 2 for i in range(1, 16)}
    points[1] = 10
    minutes = {i: 90 for i in range(1, 16)}
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
    total = replay_scenario(
        picks=picks,
        player_points=points,
        minutes=minutes,
        hit_cost=4,
        bench_boost=False,
        triple_captain=False,
        rules=load_season_rules_2026_27(),
    )
    assert total == 36


def test_decision_record_written_and_immutable(tmp_path: Path) -> None:
    record = DecisionRecord(
        decision_id=build_decision_id({"gw": 1}),
        season="2026-27",
        gameweek=1,
        generated_at="2026-01-01T00:00:00Z",
        data_cutoff="2026-01-01T00:00:00Z",
        team_state={},
        executability="EXECUTABLE",
        rules_hash="r",
        catalog_hash="c",
        projection_hash="p",
        config_hash="cfg",
        code_version="0",
        roll={},
    )
    write_decision_record(tmp_path, record)
    try:
        write_decision_record(tmp_path, record)
        raised = False
    except FileExistsError:
        raised = True
    assert raised
