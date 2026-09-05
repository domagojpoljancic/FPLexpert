"""Tests for proposal-only calibration lessons."""

from __future__ import annotations

import hashlib
from pathlib import Path

from fpl_agent.config import ReflectionSettings
from fpl_agent.evaluation.lessons import (
    MIN_DISTINCT_GWS,
    MIN_SAMPLE,
    Lesson,
    SegmentStats,
    aggregate_calibration,
    append_lesson,
    backtest_adjustment,
    eligible_for_proposal,
    format_lessons_section,
    load_lessons,
    propose_adjustment,
)
from fpl_agent.evaluation.reflection import (
    AlternativeReviewed,
    GwFinality,
    PlayerCalibrationRow,
    REFLECTION_SCHEMA_VERSION,
    ReflectionSummary,
)


def _cal_row(
    pid: int,
    *,
    position: str = "FWD",
    tier: str = "mid",
    predicted: float = 6.0,
    actual: int = 4,
) -> PlayerCalibrationRow:
    return PlayerCalibrationRow(
        player_id=pid,
        web_name=f"P{pid}",
        position=position,
        price_tier=tier,
        predicted_xp=predicted,
        actual_points=actual,
    )


def _summary(
    gw: int,
    rows: list[PlayerCalibrationRow],
    *,
    alts: tuple[AlternativeReviewed, ...] = (),
    transfer_predicted_delta: float | None = 1.0,
) -> ReflectionSummary:
    return ReflectionSummary(
        schema_version=REFLECTION_SCHEMA_VERSION,
        gameweek=gw,
        computed_at="2026-09-01T00:00:00+00:00",
        finality=GwFinality.FINAL.value,
        report_path=None,
        predicted_xi_xp=40.0,
        actual_xi_points=38,
        model_captain_name="Cap",
        model_captain_points=10,
        predicted_captain_xp=8.0,
        saved_captain_name=None,
        saved_captain_points=None,
        transfer_out_name="Out",
        transfer_in_name="In",
        transfer_out_points=2,
        transfer_in_points=4,
        transfer_predicted_delta=transfer_predicted_delta,
        transfer_actual_delta=2,
        process_quality="good",
        outcome_quality="positive",
        root_cause="sound_process_normal_variance",
        alternatives_reviewed=alts,
        short_summary=f"GW{gw}",
        detail_summary=f"GW{gw} detail",
        what_could_have_been_better="No recorded alternative would have done better.",
        player_calibration=tuple(rows),
    )


def test_aggregate_calibration_grouping_and_means() -> None:
    history = [
        _summary(1, [_cal_row(1, predicted=6.0, actual=4), _cal_row(2, position="MID", predicted=5.0, actual=5)]),
        _summary(2, [_cal_row(3, predicted=7.0, actual=5), _cal_row(4, position="MID", tier="premium", predicted=8.0, actual=9)]),
    ]
    stats = aggregate_calibration(history)
    assert "FWD:mid" in stats
    assert stats["FWD:mid"].sample_size == 2
    assert stats["FWD:mid"].distinct_gameweeks == 2
    # biases: (6-4)=2, (7-5)=2 → mean 2
    assert stats["FWD:mid"].mean_bias == 2.0
    assert "MID:mid" in stats
    assert "MID:premium" in stats


def test_eligible_for_proposal_boundaries() -> None:
    below = SegmentStats(
        segment="FWD:mid",
        position="FWD",
        price_tier="mid",
        sample_size=MIN_SAMPLE - 1,
        distinct_gameweeks=MIN_DISTINCT_GWS,
        mean_bias=1.0,
        mean_abs_error=1.0,
        gameweeks=tuple(range(1, MIN_DISTINCT_GWS + 1)),
    )
    assert eligible_for_proposal(below) is False
    edge = SegmentStats(
        segment="FWD:mid",
        position="FWD",
        price_tier="mid",
        sample_size=MIN_SAMPLE,
        distinct_gameweeks=MIN_DISTINCT_GWS,
        mean_bias=1.0,
        mean_abs_error=1.0,
        gameweeks=tuple(range(1, MIN_DISTINCT_GWS + 1)),
    )
    assert eligible_for_proposal(edge) is True


def test_propose_adjustment_none_below_gate_and_bounded_above() -> None:
    thin = SegmentStats(
        segment="FWD:mid",
        position="FWD",
        price_tier="mid",
        sample_size=5,
        distinct_gameweeks=2,
        mean_bias=2.0,
        mean_abs_error=2.0,
        gameweeks=(1, 2),
    )
    assert propose_adjustment(thin, as_of_gameweek=5) is None

    fat = SegmentStats(
        segment="FWD:mid",
        position="FWD",
        price_tier="mid",
        sample_size=24,
        distinct_gameweeks=5,
        mean_bias=2.0,  # high → shrink
        mean_abs_error=2.0,
        gameweeks=(1, 2, 3, 4, 5),
    )
    lesson = propose_adjustment(fat, as_of_gameweek=5)
    assert lesson is not None
    factor = float(lesson.proposed_adjustment["factor"])
    assert 0.85 <= factor <= 1.15
    assert factor < 1.0  # shrink when bias positive

    low = SegmentStats(
        segment="DEF:budget",
        position="DEF",
        price_tier="budget",
        sample_size=24,
        distinct_gameweeks=5,
        mean_bias=-2.0,  # low → boost
        mean_abs_error=2.0,
        gameweeks=(1, 2, 3, 4, 5),
    )
    lesson2 = propose_adjustment(low, as_of_gameweek=5)
    assert lesson2 is not None
    assert float(lesson2.proposed_adjustment["factor"]) > 1.0


def _fat_history_for_pass(
    *,
    with_flip_alt: bool = False,
    predicted: float = 6.0,
    actual: int = 4,
) -> list[ReflectionSummary]:
    """Build ≥4 GWs / ≥20 FWD:mid rows for gate + backtest fixtures."""
    history: list[ReflectionSummary] = []
    pid = 1
    for gw in range(1, 6):
        rows = []
        for _ in range(5):  # 5 rows * 5 gws = 25
            rows.append(_cal_row(pid, predicted=predicted, actual=actual))
            pid += 1
        alts: tuple[AlternativeReviewed, ...] = ()
        pick_delta = 1.0
        if with_flip_alt and gw == 2:
            alts = (
                AlternativeReviewed(
                    in_name="NearMiss",
                    in_id=900,
                    predicted_delta=0.99,
                    actual_delta=None,
                    beat_the_pick=False,
                    position="FWD",
                    price_tier="mid",
                ),
            )
        history.append(
            _summary(gw, rows, alts=alts, transfer_predicted_delta=pick_delta)
        )
    return history


def test_backtest_adjustment_pass() -> None:
    history = _fat_history_for_pass(with_flip_alt=False)
    stats = aggregate_calibration(history)["FWD:mid"]
    lesson = propose_adjustment(stats, as_of_gameweek=5)
    assert lesson is not None
    # Force a shrink factor known to reduce MAE on pred=6/actual=4.
    forced = Lesson(
        lesson_id=lesson.lesson_id,
        created_at=lesson.created_at,
        as_of_gameweek=5,
        segment=lesson.segment,
        sample_size=lesson.sample_size,
        distinct_gameweeks=lesson.distinct_gameweeks,
        observed_bias=lesson.observed_bias,
        proposed_adjustment={"target": "xp_multiplier", "segment": "FWD:mid", "factor": 0.9},
        backtest_status="pending",
        backtest_detail="",
        status="proposed",
        review_after_gw=lesson.review_after_gw,
        expires_after_gw=lesson.expires_after_gw,
    )
    result = backtest_adjustment(forced, history)
    assert result.backtest_status == "backtested_pass"


def test_backtest_adjustment_fail_on_flip() -> None:
    # Under-prediction → boost helps MAE; alt-only boost can flip a near-tie pick.
    history = _fat_history_for_pass(with_flip_alt=True, predicted=4.0, actual=6)
    stats = aggregate_calibration(history)["FWD:mid"]
    lesson = propose_adjustment(stats, as_of_gameweek=5)
    assert lesson is not None
    forced = Lesson(
        lesson_id=lesson.lesson_id,
        created_at=lesson.created_at,
        as_of_gameweek=5,
        segment=lesson.segment,
        sample_size=lesson.sample_size,
        distinct_gameweeks=lesson.distinct_gameweeks,
        observed_bias=lesson.observed_bias,
        proposed_adjustment={"target": "xp_multiplier", "segment": "FWD:mid", "factor": 1.15},
        backtest_status="pending",
        backtest_detail="",
        status="proposed",
        review_after_gw=lesson.review_after_gw,
        expires_after_gw=lesson.expires_after_gw,
    )
    result = backtest_adjustment(forced, history)
    assert result.backtest_status == "backtested_fail"
    assert "flip" in result.backtest_detail.lower()


def test_append_only_lessons_ledger(tmp_path: Path) -> None:
    path = tmp_path / "lessons.jsonl"
    first = Lesson(
        lesson_id="abc123",
        created_at="t1",
        as_of_gameweek=4,
        segment="FWD:mid",
        sample_size=20,
        distinct_gameweeks=4,
        observed_bias=1.0,
        proposed_adjustment={"factor": 0.94},
        backtest_status="backtested_pass",
        backtest_detail="ok",
        status="proposed",
        review_after_gw=7,
        expires_after_gw=12,
    )
    append_lesson(path, first)
    before = path.read_bytes()
    digest = hashlib.sha256(before).hexdigest()
    second = Lesson(
        lesson_id="abc123",
        created_at="t2",
        as_of_gameweek=5,
        segment="FWD:mid",
        sample_size=25,
        distinct_gameweeks=5,
        observed_bias=0.8,
        proposed_adjustment={"factor": 0.95},
        backtest_status="backtested_pass",
        backtest_detail="ok2",
        status="proposed",
        review_after_gw=8,
        expires_after_gw=13,
    )
    append_lesson(path, second)
    after = path.read_bytes()
    assert after.startswith(before)
    assert hashlib.sha256(before).hexdigest() == digest
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2
    loaded = load_lessons(path)
    assert loaded[0].created_at == "t1"
    assert loaded[1].created_at == "t2"


def test_format_lessons_section_labels_not_applied() -> None:
    lesson = Lesson(
        lesson_id="x",
        created_at="t",
        as_of_gameweek=5,
        segment="FWD:mid",
        sample_size=24,
        distinct_gameweeks=5,
        observed_bias=0.6,
        proposed_adjustment={"target": "xp_multiplier", "segment": "FWD:mid", "factor": 0.94},
        backtest_status="backtested_pass",
        backtest_detail="would have cut mean error",
        status="proposed",
        review_after_gw=8,
        expires_after_gw=13,
    )
    obs = [
        SegmentStats(
            segment="MID:budget",
            position="MID",
            price_tier="budget",
            sample_size=3,
            distinct_gameweeks=2,
            mean_bias=0.6,
            mean_abs_error=0.6,
            gameweeks=(4, 5),
        )
    ]
    lines = format_lessons_section([lesson], obs, as_of_gameweek=5)
    text = "\n".join(lines)
    assert "not applied automatically" in text
    assert "Not yet applied" in text
    assert "applied" in text.lower()
    assert "Observation only" in text
    assert "false" not in text  # sanity
    # Never claim applied:
    assert "has been applied" not in text.lower()
    assert "now applied" not in text.lower()


def test_render_reflection_includes_lessons_section(tmp_path: Path) -> None:
    import json

    from fpl_agent.daily import DailyReport, render_daily_text

    evaluation = tmp_path / "evaluation"
    evaluation.mkdir()
    history = _fat_history_for_pass(with_flip_alt=False)
    for summary in history:
        (evaluation / f"reflection-gw{summary.gameweek}.json").write_text(
            json.dumps(summary.as_payload()), encoding="utf-8"
        )

    reflection = history[-1].as_payload()
    report = DailyReport(
        gameweek=6,
        plan_action="keep",
        headline="Hold",
        what_changed=[],
        attention_triggers=[],
        suggested_moves=[],
        uncertainty=[],
        warnings=[],
        sources=[],
        model_meta={"fallback": True},
        executability="EXECUTABLE",
        used_live_ai=False,
        detail="Why text",
        reflection=reflection,
    )
    text = render_daily_text(report, evaluation_dir=evaluation)
    assert "Suggested adjustments for future reports (not applied automatically)" in text
    assert "Not yet applied" in text
    assert "has been applied" not in text.lower()
