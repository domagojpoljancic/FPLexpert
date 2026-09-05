"""Tests for multi-GW transfer thesis tracking."""

from __future__ import annotations

import json
from pathlib import Path

from fpl_agent.evaluation.ledger import DecisionRecord, build_decision_id, write_decision_record
from fpl_agent.evaluation.transfer_pertinence import (
    TransferThesis,
    format_theses_section,
    load_latest_theses,
    open_theses_from_ledger,
    persist_theses,
    update_theses_for_gameweek,
)


def _write_transfer_record(
    root: Path,
    *,
    season: str,
    gameweek: int,
    out_id: int,
    in_id: int,
    out_name: str,
    in_name: str,
    horizon: list[int],
    predicted: dict[int, float],
    alternatives: list[dict] | None = None,
) -> str:
    primary = {
        "plan_action": "revise",
        "out_id": out_id,
        "out_name": out_name,
        "in_id": in_id,
        "in_name": in_name,
        "horizon_gameweeks": horizon,
        "predicted_delta_by_gw": {str(k): v for k, v in predicted.items()},
    }
    alts = alternatives or [
        {"in_id": in_id, "in_name": in_name, "out_id": out_id, "out_name": out_name, "picked": True},
        {"in_id": 999, "in_name": "AltPlayer", "out_id": out_id, "out_name": out_name, "picked": False},
    ]
    payload = {"gameweek": gameweek, "primary": primary}
    decision_id = build_decision_id(payload)
    record = DecisionRecord(
        decision_id=decision_id,
        season=season,
        gameweek=gameweek,
        generated_at="2026-09-01T00:00:00+00:00",
        data_cutoff="2026-09-01T00:00:00+00:00",
        team_state={},
        executability="EXECUTABLE",
        rules_hash="",
        catalog_hash="",
        projection_hash="",
        config_hash="",
        code_version="",
        roll={},
        primary=primary,
        alternatives=alts,
    )
    write_decision_record(root, record)
    return decision_id


def test_thesis_opens_and_closes_across_horizon(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger"
    season = "2026-27"
    horizon = [3, 4, 5]
    predicted = {3: 1.5, 4: 1.0, 5: 0.5}
    decision_id = _write_transfer_record(
        ledger,
        season=season,
        gameweek=3,
        out_id=10,
        in_id=20,
        out_name="Shaw",
        in_name="De Cuyper",
        horizon=horizon,
        predicted=predicted,
    )
    opened = open_theses_from_ledger(ledger, season)
    assert len(opened) == 1
    thesis = opened[0]
    assert thesis.decision_id == decision_id
    assert thesis.version == 1
    assert thesis.horizon_gameweeks == (3, 4, 5)
    assert thesis.predicted_delta_by_gw == predicted
    assert thesis.status == "open"
    assert thesis.actual_delta_by_gw == {}

    squad = {20, 1, 2}
    # GW3 points: in 6, out 2 → +4
    t1 = update_theses_for_gameweek(
        [thesis], gameweek=3, player_points={20: 6, 10: 2}, current_squad_ids=squad
    )[0]
    assert t1.status == "open"
    assert t1.actual_delta_by_gw == {3: 4}
    assert t1.version == 2
    assert t1.horizon_gameweeks == thesis.horizon_gameweeks  # immutable
    assert t1.predicted_delta_by_gw == thesis.predicted_delta_by_gw

    t2 = update_theses_for_gameweek(
        [t1], gameweek=4, player_points={20: 5, 10: 3}, current_squad_ids=squad
    )[0]
    assert t2.actual_delta_by_gw == {3: 4, 4: 2}
    assert t2.status == "open"
    assert t2.version == 3

    t3 = update_theses_for_gameweek(
        [t2], gameweek=5, player_points={20: 2, 10: 4}, current_squad_ids=squad
    )[0]
    assert t3.status == "closed_horizon_complete"
    assert t3.actual_delta_by_gw == {3: 4, 4: 2, 5: -2}
    assert t3.cumulative_actual_delta == 4
    assert t3.version == 4


def test_thesis_closes_when_player_sold(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger"
    _write_transfer_record(
        ledger,
        season="2026-27",
        gameweek=3,
        out_id=10,
        in_id=20,
        out_name="Shaw",
        in_name="De Cuyper",
        horizon=[3, 4, 5],
        predicted={3: 1.0, 4: 1.0, 5: 1.0},
    )
    thesis = open_theses_from_ledger(ledger, "2026-27")[0]
    after_gw3 = update_theses_for_gameweek(
        [thesis], gameweek=3, player_points={20: 5, 10: 2}, current_squad_ids={20}
    )[0]
    assert after_gw3.status == "open"
    # Sold before GW4
    closed = update_theses_for_gameweek(
        [after_gw3], gameweek=4, player_points={20: 8, 10: 1}, current_squad_ids={1, 2}
    )[0]
    assert closed.status == "closed_player_sold"
    assert 4 not in closed.actual_delta_by_gw


def test_update_idempotent_no_duplicate_version(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger"
    evaluation = tmp_path / "evaluation"
    _write_transfer_record(
        ledger,
        season="2026-27",
        gameweek=3,
        out_id=10,
        in_id=20,
        out_name="Shaw",
        in_name="De Cuyper",
        horizon=[3, 4],
        predicted={3: 1.0, 4: 1.0},
    )
    thesis = open_theses_from_ledger(ledger, "2026-27")[0]
    jsonl = evaluation / "transfer-theses.jsonl"
    latest = evaluation / "transfer-theses-latest.json"
    persist_theses([thesis], jsonl_path=jsonl, latest_path=latest, previous_latest={})

    updated = update_theses_for_gameweek(
        [thesis], gameweek=3, player_points={20: 6, 10: 2}, current_squad_ids={20}
    )
    persist_theses(
        updated,
        jsonl_path=jsonl,
        latest_path=latest,
        previous_latest=load_latest_theses(latest),
    )
    lines_after_first = [ln for ln in jsonl.read_text().splitlines() if ln.strip()]
    assert len(lines_after_first) == 2  # v1 open + v2 with GW3

    # Re-run same GW — no new line
    again = update_theses_for_gameweek(
        updated, gameweek=3, player_points={20: 6, 10: 2}, current_squad_ids={20}
    )
    persist_theses(
        again,
        jsonl_path=jsonl,
        latest_path=latest,
        previous_latest=load_latest_theses(latest),
    )
    lines_after_rerun = [ln for ln in jsonl.read_text().splitlines() if ln.strip()]
    assert len(lines_after_rerun) == 2
    assert again[0].version == updated[0].version
    assert again[0].actual_delta_by_gw == updated[0].actual_delta_by_gw


def test_format_theses_only_cites_recorded_alternatives(tmp_path: Path) -> None:
    thesis = TransferThesis(
        decision_id="d1",
        version=2,
        out_id=10,
        out_name="Shaw",
        in_id=20,
        in_name="De Cuyper",
        gameweek_made=3,
        horizon_gameweeks=(3, 4, 5),
        predicted_delta_by_gw={3: 1.5, 4: 1.0, 5: 0.5},
        actual_delta_by_gw={3: 4},
        cumulative_predicted_delta=1.5,
        cumulative_actual_delta=4,
        status="open",
        alternatives=(
            {"in_name": "De Cuyper", "picked": True},
            {"in_name": "AltPlayer", "picked": False},
        ),
    )
    lines = format_theses_section([thesis], current_gameweek=4)
    text = "\n".join(lines)
    assert "Shaw → De Cuyper" in text
    assert "AltPlayer" in text
    assert "Salah" not in text
    assert "Palmer" not in text
    assert "How past transfer calls have aged" in text
