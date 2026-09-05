"""Cross-GW calibration lessons — proposal-only, never auto-applied.

Lessons are append-only JSONL under ``data/evaluation/lessons.jsonl``.
Nothing in this module imports or writes into ``projections/preseason`` or
``strategy/transfers``; adjustment factors stay proposals until a future,
explicitly signed-off plan wires them in.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from fpl_agent.config import ReflectionSettings
from fpl_agent.domain.run_state import stable_json_hash, utc_now
from fpl_agent.evaluation.reflection import ReflectionSummary

DEFAULT_LESSONS_PATH = Path("data/evaluation/lessons.jsonl")

# Defaults mirror ReflectionSettings; kept as module aliases for tests that
# import MIN_SAMPLE / MIN_DISTINCT_GWS by name.
MIN_SAMPLE = 20
MIN_DISTINCT_GWS = 4


@dataclass(frozen=True)
class SegmentStats:
    segment: str
    position: str
    price_tier: str
    sample_size: int
    distinct_gameweeks: int
    mean_bias: float
    mean_abs_error: float
    gameweeks: tuple[int, ...]


@dataclass(frozen=True)
class Lesson:
    lesson_id: str
    created_at: str
    as_of_gameweek: int
    segment: str
    sample_size: int
    distinct_gameweeks: int
    observed_bias: float
    proposed_adjustment: dict[str, Any]
    backtest_status: str
    backtest_detail: str
    status: str
    review_after_gw: int
    expires_after_gw: int

    def as_payload(self) -> dict[str, Any]:
        return asdict(self)


def aggregate_calibration(history: list[ReflectionSummary]) -> dict[str, SegmentStats]:
    """Group PlayerCalibrationRow entries by (position, price_tier)."""
    buckets: dict[str, list[tuple[int, float, float]]] = {}
    for summary in history:
        for row in summary.player_calibration:
            key = f"{row.position}:{row.price_tier}"
            buckets.setdefault(key, []).append(
                (summary.gameweek, float(row.predicted_xp), float(row.actual_points))
            )
    out: dict[str, SegmentStats] = {}
    for key, rows in buckets.items():
        if not rows:
            continue
        position, price_tier = key.split(":", 1)
        biases = [pred - actual for _, pred, actual in rows]
        abs_err = [abs(b) for b in biases]
        gws = tuple(sorted({gw for gw, _, _ in rows}))
        out[key] = SegmentStats(
            segment=key,
            position=position,
            price_tier=price_tier,
            sample_size=len(rows),
            distinct_gameweeks=len(gws),
            mean_bias=sum(biases) / len(biases),
            mean_abs_error=sum(abs_err) / len(abs_err),
            gameweeks=gws,
        )
    return out


def eligible_for_proposal(
    stats: SegmentStats,
    *,
    settings: ReflectionSettings | None = None,
) -> bool:
    cfg = settings or ReflectionSettings()
    return stats.sample_size >= cfg.min_sample and stats.distinct_gameweeks >= cfg.min_distinct_gws


def propose_adjustment(
    stats: SegmentStats,
    *,
    as_of_gameweek: int,
    settings: ReflectionSettings | None = None,
) -> Lesson | None:
    """Return a bounded proposal when the sample gate passes; else None."""
    cfg = settings or ReflectionSettings()
    if not eligible_for_proposal(stats, settings=cfg):
        return None
    # Shrink when bias > 0 (predictions run high); boost when bias < 0.
    # factor ≈ 1 - bias / mean_predicted_scale; use a gentle bias fraction.
    raw = 1.0 - (stats.mean_bias * 0.1)
    factor = max(cfg.min_adjustment_factor, min(cfg.max_adjustment_factor, raw))
    # Avoid proposing a no-op.
    if abs(factor - 1.0) < 0.01:
        return None
    proposal = {
        "target": "xp_multiplier",
        "segment": stats.segment,
        "factor": round(factor, 4),
    }
    created = utc_now().isoformat()
    lesson_id = stable_json_hash(
        {
            "segment": stats.segment,
            "proposal": proposal,
            "as_of_gameweek": as_of_gameweek,
        }
    )[:24]
    return Lesson(
        lesson_id=lesson_id,
        created_at=created,
        as_of_gameweek=as_of_gameweek,
        segment=stats.segment,
        sample_size=stats.sample_size,
        distinct_gameweeks=stats.distinct_gameweeks,
        observed_bias=round(stats.mean_bias, 4),
        proposed_adjustment=proposal,
        backtest_status="pending",
        backtest_detail="",
        status="proposed",
        review_after_gw=as_of_gameweek + cfg.review_after_gws,
        expires_after_gw=as_of_gameweek + cfg.expires_after_gws,
    )


def backtest_adjustment(
    lesson: Lesson,
    history: list[ReflectionSummary],
) -> Lesson:
    """Leakage-free prior-GW MAE check + recorded-pick flip guard."""
    factor = float(lesson.proposed_adjustment.get("factor") or 1.0)
    position, price_tier = lesson.segment.split(":", 1)
    prior_rows: list[tuple[float, float]] = []
    for summary in history:
        if summary.gameweek >= lesson.as_of_gameweek:
            continue
        for row in summary.player_calibration:
            if row.position != position or row.price_tier != price_tier:
                continue
            prior_rows.append((float(row.predicted_xp), float(row.actual_points)))

    if len(prior_rows) < 2:
        return _with_backtest(
            lesson,
            status="backtested_fail",
            detail="insufficient prior-GW rows for leakage-free backtest",
        )

    base_mae = sum(abs(p - a) for p, a in prior_rows) / len(prior_rows)
    adj_mae = sum(abs(p * factor - a) for p, a in prior_rows) / len(prior_rows)
    if adj_mae >= base_mae:
        return _with_backtest(
            lesson,
            status="backtested_fail",
            detail=(
                f"adjusted MAE {adj_mae:.3f} not strictly lower than baseline {base_mae:.3f}"
            ),
        )

    flip_reason = _flip_reason(lesson, history, factor=factor)
    if flip_reason:
        return _with_backtest(lesson, status="backtested_fail", detail=flip_reason)

    return _with_backtest(
        lesson,
        status="backtested_pass",
        detail=(
            f"adjusted MAE {adj_mae:.3f} < baseline {base_mae:.3f}; "
            "no recorded also_considered pick flipped"
        ),
    )


def append_lesson(path: Path, lesson: Lesson) -> None:
    """Append one lesson line; never rewrite prior lines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(lesson.as_payload(), sort_keys=True) + "\n")


def load_lessons(path: Path) -> list[Lesson]:
    if not path.exists():
        return []
    out: list[Lesson] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        payload = json.loads(line)
        out.append(_lesson_from_payload(payload))
    return out


def current_lessons(path: Path) -> dict[str, Lesson]:
    """Most recent line per lesson_id wins."""
    current: dict[str, Lesson] = {}
    for lesson in load_lessons(path):
        current[lesson.lesson_id] = lesson
    return current


def build_lessons_for_history(
    history: list[ReflectionSummary],
    *,
    as_of_gameweek: int,
    settings: ReflectionSettings | None = None,
    lessons_path: Path = DEFAULT_LESSONS_PATH,
    persist: bool = True,
) -> tuple[list[Lesson], list[SegmentStats]]:
    """Aggregate, propose, backtest, and optionally persist lessons for this cycle.

    Returns (lessons_to_surface, below_gate_observations).
    v1 surfaces only ``backtested_pass`` proposals plus below-gate observations.
    """
    cfg = settings or ReflectionSettings()
    stats_map = aggregate_calibration(history)
    observations = [s for s in stats_map.values() if not eligible_for_proposal(s, settings=cfg)]
    lessons: list[Lesson] = []
    for stats in stats_map.values():
        proposal = propose_adjustment(stats, as_of_gameweek=as_of_gameweek, settings=cfg)
        if proposal is None:
            continue
        tested = backtest_adjustment(proposal, history)
        if persist:
            append_lesson(lessons_path, tested)
        if tested.backtest_status == "backtested_pass" and tested.status == "proposed":
            lessons.append(tested)
    return lessons, observations


def format_lessons_section(
    lessons: list[Lesson],
    observations: list[SegmentStats],
    *,
    as_of_gameweek: int,
) -> list[str]:
    """Markdown lines for the reflection report (proposal-only labeling)."""
    # Prefer newest lesson per segment among those matching this as_of GW.
    by_segment: dict[str, Lesson] = {}
    for lesson in lessons:
        if lesson.as_of_gameweek != as_of_gameweek:
            continue
        if lesson.backtest_status != "backtested_pass":
            continue
        if lesson.status != "proposed":
            continue
        by_segment[lesson.segment] = lesson

    if not by_segment and not observations:
        return []

    lines = [
        "### Suggested adjustments for future reports (not applied automatically)",
        "",
    ]
    for segment, lesson in sorted(by_segment.items()):
        factor = float(lesson.proposed_adjustment.get("factor") or 1.0)
        pct = abs(1.0 - factor) * 100
        direction = "shrink" if factor < 1.0 else "boost"
        pos, tier = segment.split(":", 1)
        lines.append(
            f"- **{pos} ({tier}-price)**: projections have run ~{abs(lesson.observed_bias):.1f} pts "
            f"{'high' if lesson.observed_bias > 0 else 'low'} over {lesson.distinct_gameweeks} weeks "
            f"(n={lesson.sample_size}). Proposed: {direction} {pos} {tier}-price xP by "
            f"{pct:.0f}% for upcoming reports. Backtest: **pass** — {lesson.backtest_detail}. "
            "Not yet applied — needs an explicit config change and human sign-off."
        )
    for stats in sorted(observations, key=lambda s: s.segment):
        if stats.sample_size < 1:
            continue
        pos, tier = stats.segment.split(":", 1)
        lines.append(
            f"- Observation only — **{pos} ({tier}-price)** projections have run "
            f"~{abs(stats.mean_bias):.1f} pts {'high' if stats.mean_bias > 0 else 'low'} "
            f"across the {stats.distinct_gameweeks} weeks measured so far (n={stats.sample_size}) — "
            "too little history yet to propose an adjustment."
        )
    return lines


def _with_backtest(lesson: Lesson, *, status: str, detail: str) -> Lesson:
    return Lesson(
        lesson_id=lesson.lesson_id,
        created_at=lesson.created_at,
        as_of_gameweek=lesson.as_of_gameweek,
        segment=lesson.segment,
        sample_size=lesson.sample_size,
        distinct_gameweeks=lesson.distinct_gameweeks,
        observed_bias=lesson.observed_bias,
        proposed_adjustment=dict(lesson.proposed_adjustment),
        backtest_status=status,
        backtest_detail=detail,
        status=lesson.status,
        review_after_gw=lesson.review_after_gw,
        expires_after_gw=lesson.expires_after_gw,
    )


def _flip_reason(lesson: Lesson, history: list[ReflectionSummary], *, factor: float) -> str | None:
    """Fail if adjusting segment predicted deltas would flip a recorded pick."""
    position, price_tier = lesson.segment.split(":", 1)
    for summary in history:
        if summary.gameweek >= lesson.as_of_gameweek:
            continue
        pick_delta = summary.transfer_predicted_delta
        if pick_delta is None:
            continue
        # Tag pick IN with segment via alternatives' siblings or calibration.
        pick_in_segment = False
        if summary.transfer_in_name:
            for row in summary.player_calibration:
                # pick IN is rarely still on the pre-transfer XI; use alternatives tags
                pass
        # Use alternatives' position/tier tags; also treat pick delta as baseline.
        adjusted_pick = pick_delta
        # If any alternative in the same segment would beat the pick after factoring.
        for alt in summary.alternatives_reviewed:
            if alt.predicted_delta is None:
                continue
            alt_delta = float(alt.predicted_delta)
            pick_adj = float(pick_delta)
            if alt.position == position and alt.price_tier == price_tier:
                alt_delta *= factor
            # If the pick's IN is also in-segment, shrink/boost pick too.
            # Conservatively: when any alt is in-segment, also apply factor to pick
            # only if pick's transfer_in shares the segment — approximated when
            # all same-position shortlist rows share position; tier may differ.
            if summary.transfer_in_name and alt.position == position:
                # Apply factor to pick only when we know pick is same tier.
                # Without pick tier on the summary, apply when every alt shares tier
                # with the segment (same-position shortlist) AND pick delta is the
                # baseline — use alternatives only for the flip of ranking.
                pass
            # Ranking among shortlist: pick wins if pick_adj >= all alt_adj
            if alt.position == position and alt.price_tier == price_tier:
                # Compare unadjusted pick vs adjusted alt (pick not in segment)
                # or both adjusted when pick also in segment — detect via name match
                # against calibration is unreliable for IN. Use: if original ranking
                # had pick >= alt and after factor alt > pick, that's a flip when
                # only the alt is adjusted OR both are.
                original_pick_wins = float(pick_delta) >= float(alt.predicted_delta)
                # Assume pick IN is in same segment when position matches and we
                # have no contrary tier — apply factor to both when alt is in segment
                # and position matches the pick's position (same_position_shortlist).
                both_adj_pick = float(pick_delta) * factor
                both_adj_alt = float(alt.predicted_delta) * factor
                after_both = both_adj_pick >= both_adj_alt
                after_alt_only = float(pick_delta) >= alt_delta
                # Flip if either framing changes the winner.
                if original_pick_wins and (not after_both or not after_alt_only):
                    return (
                        f"would flip recorded also_considered ranking in GW{summary.gameweek}: "
                        f"{alt.in_name} would beat the pick after factor {factor}"
                    )
                if (not original_pick_wins) and after_both and after_alt_only:
                    return (
                        f"would flip recorded also_considered ranking in GW{summary.gameweek}: "
                        f"pick would newly beat {alt.in_name} after factor {factor}"
                    )
            _ = adjusted_pick
            _ = pick_in_segment
    return None


def _lesson_from_payload(payload: dict[str, Any]) -> Lesson:
    return Lesson(
        lesson_id=str(payload["lesson_id"]),
        created_at=str(payload.get("created_at") or ""),
        as_of_gameweek=int(payload["as_of_gameweek"]),
        segment=str(payload["segment"]),
        sample_size=int(payload.get("sample_size") or 0),
        distinct_gameweeks=int(payload.get("distinct_gameweeks") or 0),
        observed_bias=float(payload.get("observed_bias") or 0),
        proposed_adjustment=dict(payload.get("proposed_adjustment") or {}),
        backtest_status=str(payload.get("backtest_status") or "pending"),
        backtest_detail=str(payload.get("backtest_detail") or ""),
        status=str(payload.get("status") or "proposed"),
        review_after_gw=int(payload.get("review_after_gw") or 0),
        expires_after_gw=int(payload.get("expires_after_gw") or 0),
    )
