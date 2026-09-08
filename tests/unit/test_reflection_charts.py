"""Tests for reflection Mermaid chart helpers."""

from __future__ import annotations

import json
from pathlib import Path

from fpl_agent.evaluation.reflection import (
    AlternativeReviewed,
    GwFinality,
    REFLECTION_SCHEMA_VERSION,
    ReflectionSummary,
)
from fpl_agent.reporting.reflection_charts import (
    load_reflection_history,
    mermaid_calibration_trend,
    mermaid_transfer_payoff_trend,
    parse_mermaid_line_series,
)


def _summary(
    gw: int,
    *,
    predicted: float | None = 40.0,
    actual: int | None = 38,
    transfer_delta: int | None = 2,
    with_transfer: bool = True,
) -> ReflectionSummary:
    return ReflectionSummary(
        schema_version=REFLECTION_SCHEMA_VERSION,
        gameweek=gw,
        computed_at="2026-09-01T00:00:00+00:00",
        finality=GwFinality.FINAL.value,
        report_path=None,
        predicted_xi_xp=predicted,
        actual_xi_points=actual,
        model_captain_name="Haaland",
        model_captain_points=12,
        predicted_captain_xp=10.0,
        saved_captain_name=None,
        saved_captain_points=None,
        transfer_out_name="Out" if with_transfer else None,
        transfer_in_name="In" if with_transfer else None,
        transfer_out_points=2 if with_transfer else None,
        transfer_in_points=(2 + (transfer_delta or 0)) if with_transfer else None,
        transfer_predicted_delta=1.0 if with_transfer else None,
        transfer_actual_delta=transfer_delta if with_transfer else None,
        process_quality="good",
        outcome_quality="positive",
        root_cause="sound_process_normal_variance",
        alternatives_reviewed=tuple(),
        short_summary=f"GW{gw} short",
        detail_summary=f"GW{gw} detail",
        what_could_have_been_better="No recorded alternative would have done better.",
    )


def _write(root: Path, summary: ReflectionSummary) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"reflection-gw{summary.gameweek}.json").write_text(
        json.dumps(summary.as_payload()),
        encoding="utf-8",
    )


def test_load_reflection_history_ordering_and_gaps(tmp_path: Path) -> None:
    root = tmp_path / "evaluation"
    _write(root, _summary(1, predicted=30.0, actual=28, transfer_delta=1))
    _write(root, _summary(3, predicted=35.0, actual=40, transfer_delta=3))
    _write(root, _summary(4, predicted=36.0, actual=34, transfer_delta=-1))
    # GW2 missing — skipped
    history = load_reflection_history(root, through_gameweek=4, max_gws=6)
    assert [h.gameweek for h in history] == [1, 3, 4]
    assert load_reflection_history(tmp_path / "empty", through_gameweek=4) == []


def test_load_reflection_history_window_size(tmp_path: Path) -> None:
    root = tmp_path / "evaluation"
    for gw in range(1, 8):
        _write(root, _summary(gw, predicted=30.0 + gw, actual=30 + gw, transfer_delta=gw))
    history = load_reflection_history(root, through_gameweek=7, max_gws=3)
    assert [h.gameweek for h in history] == [5, 6, 7]


def test_mermaid_calibration_requires_two_points() -> None:
    assert mermaid_calibration_trend([]) is None
    assert mermaid_calibration_trend([_summary(1)]) is None
    chart = mermaid_calibration_trend(
        [
            _summary(1, predicted=30.5, actual=28),
            _summary(2, predicted=41.0, actual=44),
        ]
    )
    assert chart is not None
    assert "```mermaid" in chart
    assert "xychart-beta" in chart
    series = parse_mermaid_line_series(chart)
    assert series == [[30.5, 41.0], [28.0, 44.0]]


def test_mermaid_transfer_payoff_omits_holds() -> None:
    history = [
        _summary(1, transfer_delta=2),
        _summary(2, with_transfer=False),  # hold — omitted
        _summary(3, transfer_delta=-1),
    ]
    chart = mermaid_transfer_payoff_trend(history)
    assert chart is not None
    assert "```mermaid" in chart
    assert "xychart-beta" in chart
    series = parse_mermaid_line_series(chart)
    assert series == [[2.0, -1.0]]
    assert "GW2" not in chart
    assert mermaid_transfer_payoff_trend([_summary(1, transfer_delta=2)]) is None
