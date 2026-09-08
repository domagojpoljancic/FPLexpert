"""Tests for the reflection finality gate and summary builder."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from fpl_agent.evaluation.reflection import (
    GwFinality,
    ReflectionSummary,
    build_reflection,
    gw_finality_status,
    load_reflection_summary,
    reflection_cache_path,
    reflection_gate,
)


def _bootstrap_with_event(
    *,
    event_id: int,
    data_checked: bool = True,
    finished: bool = True,
    is_next: bool = False,
) -> dict:
    return {
        "events": [
            {
                "id": event_id,
                "name": f"Gameweek {event_id}",
                "deadline_time": "2026-08-15T11:00:00Z",
                "finished": finished,
                "data_checked": data_checked,
                "is_current": not is_next and finished,
                "is_next": is_next,
                "is_previous": False,
            }
        ]
    }


def _fixtures_for_gw(
    gameweek: int,
    *,
    unfinished: bool = False,
    kickoff: str = "2026-08-16T14:00:00Z",
    missing_kickoff: bool = False,
) -> list[dict]:
    rows = [
        {
            "event": gameweek,
            "finished": not unfinished,
            "kickoff_time": None if missing_kickoff else kickoff,
        },
        {
            "event": gameweek,
            "finished": True,
            "kickoff_time": "2026-08-15T14:00:00Z",
        },
    ]
    return rows


def test_gw_finality_in_progress() -> None:
    status = gw_finality_status(
        bootstrap=_bootstrap_with_event(event_id=2),
        fixtures=_fixtures_for_gw(2, unfinished=True),
        gameweek=2,
        now=datetime(2026, 8, 20, 12, 0, tzinfo=UTC),
    )
    assert status is GwFinality.IN_PROGRESS


def test_gw_finality_provisional_before_lock() -> None:
    # Final match 16 Aug 14:00 UTC → lock is 09:00 UK on 17 Aug.
    status = gw_finality_status(
        bootstrap=_bootstrap_with_event(event_id=2, data_checked=True),
        fixtures=_fixtures_for_gw(2, kickoff="2026-08-16T14:00:00Z"),
        gameweek=2,
        now=datetime(2026, 8, 16, 20, 0, tzinfo=UTC),
    )
    assert status is GwFinality.PROVISIONAL


def test_gw_finality_provisional_data_not_checked() -> None:
    status = gw_finality_status(
        bootstrap=_bootstrap_with_event(event_id=2, data_checked=False),
        fixtures=_fixtures_for_gw(2, kickoff="2026-08-16T14:00:00Z"),
        gameweek=2,
        now=datetime(2026, 8, 20, 12, 0, tzinfo=UTC),
    )
    assert status is GwFinality.PROVISIONAL


def test_gw_finality_final() -> None:
    status = gw_finality_status(
        bootstrap=_bootstrap_with_event(event_id=2, data_checked=True),
        fixtures=_fixtures_for_gw(2, kickoff="2026-08-16T14:00:00Z"),
        gameweek=2,
        now=datetime(2026, 8, 17, 9, 0, tzinfo=UTC),  # 09:00 UK on day after
    )
    assert status is GwFinality.FINAL


def test_gw_finality_unknown_no_fixtures() -> None:
    status = gw_finality_status(
        bootstrap=_bootstrap_with_event(event_id=2),
        fixtures=[],
        gameweek=2,
        now=datetime(2026, 8, 20, 12, 0, tzinfo=UTC),
    )
    assert status is GwFinality.UNKNOWN


def test_gw_finality_unknown_missing_kickoff() -> None:
    status = gw_finality_status(
        bootstrap=_bootstrap_with_event(event_id=2),
        fixtures=_fixtures_for_gw(2, missing_kickoff=True),
        gameweek=2,
        now=datetime(2026, 8, 20, 12, 0, tzinfo=UTC),
    )
    assert status is GwFinality.UNKNOWN


def test_gw_finality_not_applicable() -> None:
    assert (
        gw_finality_status(
            bootstrap={"events": []},
            fixtures=[],
            gameweek=0,
            now=datetime(2026, 8, 1, tzinfo=UTC),
        )
        is GwFinality.NOT_APPLICABLE
    )


def test_reflection_gate_season_boundary_gw1() -> None:
    bootstrap = {
        "events": [
            {
                "id": 1,
                "name": "Gameweek 1",
                "deadline_time": "2026-08-15T11:00:00Z",
                "finished": False,
                "data_checked": False,
                "is_current": False,
                "is_next": True,
                "is_previous": False,
            }
        ]
    }
    subject_gw, status = reflection_gate(bootstrap, [], now=datetime(2026, 8, 10, tzinfo=UTC))
    assert subject_gw == 0
    assert status is GwFinality.NOT_APPLICABLE


def _sample_plan(*, ok: bool = True, with_alt_beater: bool = True) -> dict:
    also = [
        {
            "out_id": 3,
            "in_id": 9,
            "out_name": "Raya",
            "in_name": "Sels",
            "picked": True,
            "delta_weighted_xp": 1.2,
            "delta_gw_xp": 0.8,
        },
        {
            "out_id": 3,
            "in_id": 11,
            "out_name": "Raya",
            "in_name": "Areola",
            "picked": False,
            "delta_weighted_xp": 0.4,
            "delta_gw_xp": 0.2,
        },
    ]
    if with_alt_beater:
        also.append(
            {
                "out_id": 3,
                "in_id": 12,
                "out_name": "Raya",
                "in_name": "Flekken",
                "picked": False,
                "delta_weighted_xp": 0.9,
                "delta_gw_xp": 0.5,
            }
        )
    return {
        "ok": ok,
        "model_captain": {"player_id": 1, "web_name": "Haaland", "xp_next": 8.0},
        "saved_captain_id": 2,
        "xi": [
            {"player_id": 1, "web_name": "Haaland", "xp_next": 8.0},
            {"player_id": 2, "web_name": "Bruno", "xp_next": 5.0},
            {"player_id": 3, "web_name": "Raya", "xp_next": 3.0},
        ],
        "best_affordable": {
            "out_id": 3,
            "in_id": 9,
            "out_name": "Raya",
            "in_name": "Sels",
            "delta_weighted_xp": 1.2,
        },
        "after_transfer": {
            "out_id": 3,
            "in_id": 9,
            "out_name": "Raya",
            "in_name": "Sels",
        },
        "also_considered": also,
    }


def _write_plan_report(reports: Path, gameweek: int, plan: dict) -> Path:
    reports.mkdir(parents=True, exist_ok=True)
    path = reports / f"predeadline-gw{gameweek}-20260828T010000Z.json"
    path.write_text(json.dumps({"weekly_plan": plan}), encoding="utf-8")
    return path


def test_build_reflection_populated(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    evaluation = tmp_path / "evaluation"
    plan = _sample_plan()
    report_path = _write_plan_report(reports, 2, plan)
    # Flekken (12) scores 8, Raya (3) scores 2 → alt actual_delta=+6
    # Sels (9) scores 6, Raya 2 → pick actual_delta=+4 → Flekken beat the pick
    points = {1: 10, 2: 4, 3: 2, 9: 6, 11: 3, 12: 8}

    summary = build_reflection(
        gameweek=2,
        reports_dir=reports,
        bootstrap=_bootstrap_with_event(event_id=2),
        player_points=points,
        evaluation_dir=evaluation,
    )
    assert summary is not None
    assert summary.gameweek == 2
    assert summary.finality == GwFinality.FINAL.value
    assert summary.transfer_actual_delta == 4
    assert summary.transfer_out_name == "Raya"
    assert summary.transfer_in_name == "Sels"
    assert summary.actual_xi_points == 16
    assert summary.model_captain_points == 20
    assert summary.process_quality == "good"
    assert summary.outcome_quality == "positive"  # in 6 - out 2 = +4 > 2
    assert summary.root_cause == "sound_process_normal_variance"
    assert "Flekken" in summary.what_could_have_been_better
    assert "shortlist" in summary.what_could_have_been_better
    # Hindsight names never invent players outside also_considered / saved captain.
    allowed = {"Sels", "Areola", "Flekken", "Bruno", "Haaland", "Raya"}
    for name in ("Salah", "Palmer", "Isak"):
        assert name not in summary.what_could_have_been_better
    mentioned = [
        a.in_name for a in summary.alternatives_reviewed if a.in_name in summary.what_could_have_been_better
    ]
    assert mentioned
    assert all(n in allowed for n in mentioned)
    assert summary.report_path == str(report_path)
    assert "GW2" in summary.short_summary
    assert "Raya → Sels" in summary.short_summary


def test_build_reflection_none_when_no_plan(tmp_path: Path) -> None:
    summary = build_reflection(
        gameweek=2,
        reports_dir=tmp_path / "reports",
        bootstrap=_bootstrap_with_event(event_id=2),
        player_points={1: 1},
        evaluation_dir=tmp_path / "evaluation",
    )
    assert summary is None


def test_build_reflection_none_when_live_points_raise(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _write_plan_report(reports, 2, _sample_plan())

    def _boom(*_a, **_k):
        raise RuntimeError("FPL down")

    with patch("fpl_agent.evaluation.reflection.fetch_live_points", _boom):
        summary = build_reflection(
            gameweek=2,
            reports_dir=reports,
            bootstrap=_bootstrap_with_event(event_id=2),
            evaluation_dir=tmp_path / "evaluation",
        )
    assert summary is None


def test_build_reflection_none_when_plan_not_ok(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _write_plan_report(reports, 2, _sample_plan(ok=False))
    summary = build_reflection(
        gameweek=2,
        reports_dir=reports,
        bootstrap=_bootstrap_with_event(event_id=2),
        player_points={1: 10, 2: 4, 3: 2, 9: 6},
        evaluation_dir=tmp_path / "evaluation",
    )
    assert summary is None


def test_reflection_cache_round_trip(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    evaluation = tmp_path / "evaluation"
    _write_plan_report(reports, 2, _sample_plan(with_alt_beater=False))
    points = {1: 10, 2: 4, 3: 2, 9: 6, 11: 1}

    summary = build_reflection(
        gameweek=2,
        reports_dir=reports,
        bootstrap=_bootstrap_with_event(event_id=2),
        player_points=points,
        evaluation_dir=evaluation,
    )
    assert summary is not None
    path = reflection_cache_path(evaluation, 2)
    assert path.exists()
    loaded = load_reflection_summary(path)
    assert isinstance(loaded, ReflectionSummary)
    assert loaded.gameweek == summary.gameweek
    assert loaded.transfer_actual_delta == summary.transfer_actual_delta
    assert loaded.short_summary == summary.short_summary
    assert loaded.what_could_have_been_better == summary.what_could_have_been_better
    assert len(loaded.alternatives_reviewed) == len(summary.alternatives_reviewed)


def test_what_could_have_been_better_no_beater_mentions_saved_captain(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    plan = _sample_plan(with_alt_beater=False)
    # Areola scores worse than pick; saved captain Bruno (2*4=8) < model Haaland (2*10=20)
    # so neither alt nor saved captain beats — plain "no recorded alternative"
    _write_plan_report(reports, 2, plan)
    summary = build_reflection(
        gameweek=2,
        reports_dir=reports,
        bootstrap=_bootstrap_with_event(event_id=2),
        player_points={1: 10, 2: 4, 3: 2, 9: 6, 11: 1},
        evaluation_dir=tmp_path / "evaluation",
    )
    assert summary is not None
    assert summary.what_could_have_been_better == "No recorded alternative would have done better."


def test_what_could_have_been_better_saved_captain_when_no_alt_beater(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    plan = _sample_plan(with_alt_beater=False)
    _write_plan_report(reports, 2, plan)
    # Model Haaland 2 pts raw → 4 captain; saved Bruno 10 raw → 20 captain
    summary = build_reflection(
        gameweek=2,
        reports_dir=reports,
        bootstrap=_bootstrap_with_event(event_id=2),
        player_points={1: 2, 2: 10, 3: 2, 9: 6, 11: 1},
        evaluation_dir=tmp_path / "evaluation",
    )
    assert summary is not None
    assert "Bruno" in summary.what_could_have_been_better
    assert "Haaland" in summary.what_could_have_been_better
