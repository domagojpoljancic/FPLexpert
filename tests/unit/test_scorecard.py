"""Weekly plan vs official GW points."""

from __future__ import annotations

import json
from pathlib import Path

from fpl_agent.evaluation.scorecard import (
    build_previous_scorecard,
    points_from_live_payload,
    scorecard_from_plan,
)


def test_points_from_live_payload() -> None:
    points = points_from_live_payload(
        {
            "elements": [
                {"id": 1, "stats": {"total_points": 12}},
                {"id": 2, "stats": {"total_points": 2}},
            ]
        }
    )
    assert points == {1: 12, 2: 2}


def test_scorecard_captain_and_transfer_delta() -> None:
    plan = {
        "ok": True,
        "model_captain": {"player_id": 1, "web_name": "Haaland"},
        "saved_captain_id": 2,
        "xi": [
            {"player_id": 1, "web_name": "Haaland"},
            {"player_id": 2, "web_name": "Bruno"},
            {"player_id": 3, "web_name": "Raya"},
        ],
        "best_affordable": {
            "out_id": 3,
            "in_id": 9,
            "out_name": "Raya",
            "in_name": "Sels",
        },
    }
    card = scorecard_from_plan(
        gameweek=2,
        weekly_plan=plan,
        player_points={1: 10, 2: 4, 3: 2, 9: 6},
    )
    assert card.model_xi_points == 16
    assert card.model_captain_points == 20
    assert card.saved_captain_points == 8
    assert card.transfer_delta == 4
    assert any("saved captain" in n for n in card.notes)


def test_build_previous_scorecard_from_report_json(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    payload = {
        "weekly_plan": {
            "ok": True,
            "model_captain": {"player_id": 1, "web_name": "Haaland"},
            "xi": [{"player_id": 1, "web_name": "Haaland"}],
        }
    }
    (reports / "predeadline-gw2-20260828T010000Z.json").write_text(json.dumps(payload), encoding="utf-8")
    card = build_previous_scorecard(
        previous_gameweek=2,
        reports_dir=reports,
        player_points={1: 7},
    )
    assert card is not None
    assert card.model_captain_points == 14
    assert build_previous_scorecard(previous_gameweek=1, reports_dir=reports, player_points={1: 7}) is None
