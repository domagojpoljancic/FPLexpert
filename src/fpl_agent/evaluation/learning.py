"""Apply prior-GW reflection outcomes and backtested lessons to live projections.

Two layers:

1. **Segment lessons** — ``backtested_pass`` proposals from ``lessons.py`` become
   xP multipliers by ``position:price_tier`` (bounded by ReflectionSettings).
2. **Prior-transfer outcomes** — if last week's recommended IN underperformed
   recorded ``also_considered`` alternatives that beat it, boost those player
   ids (and gently dampen the missed pick) so this week's transfer ranking
   actually feels the miss.

Both layers are opt-in via ``ReflectionSettings`` and are described in
``weekly_plan["learning"]`` for the report.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from fpl_agent.config import ReflectionSettings
from fpl_agent.evaluation.lessons import DEFAULT_LESSONS_PATH, current_lessons
from fpl_agent.evaluation.plan_store import DEFAULT_PLANS_DIR, load_weekly_plan
from fpl_agent.evaluation.reflection import price_tier_from_millions
from fpl_agent.projections.preseason import PlayerProjection

_ELEMENT_TYPE_POS = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}

# Prior-transfer player multipliers stay inside a tighter band than segment lessons.
_PRIOR_PLAYER_MIN = 0.90
_PRIOR_PLAYER_MAX = 1.12
_PRIOR_BEAT_STEP = 0.04
_PRIOR_MISS_DAMPEN = 0.96


@dataclass
class LearningApplication:
    notes: list[str] = field(default_factory=list)
    segment_factors: dict[str, float] = field(default_factory=dict)
    player_factors: dict[int, float] = field(default_factory=dict)
    applied: bool = False

    def as_payload(self) -> dict[str, Any]:
        return {
            "applied": self.applied,
            "notes": list(self.notes),
            "segment_factors": dict(self.segment_factors),
            "player_factors": {str(k): v for k, v in sorted(self.player_factors.items())},
        }


def _segment_for_player(
    player_id: int,
    catalog: dict[int, dict[str, Any]],
) -> str | None:
    el = catalog.get(player_id) or {}
    et = el.get("element_type")
    if et is None:
        return None
    pos = _ELEMENT_TYPE_POS.get(int(et))
    if not pos:
        return None
    cost = el.get("now_cost")
    price_m = float(cost) / 10.0 if cost is not None else None
    tier = price_tier_from_millions(price_m)
    return f"{pos}:{tier}"


def active_segment_factors(
    *,
    as_of_gameweek: int,
    lessons_path: Path = DEFAULT_LESSONS_PATH,
    settings: ReflectionSettings | None = None,
) -> tuple[dict[str, float], list[str]]:
    """Return segment -> factor for live, unexpired, backtested_pass lessons."""
    cfg = settings or ReflectionSettings()
    best: dict[str, tuple[int, float, str]] = {}
    for lesson in current_lessons(lessons_path).values():
        if lesson.status != "proposed":
            continue
        if lesson.backtest_status != "backtested_pass":
            continue
        if int(lesson.as_of_gameweek) >= int(as_of_gameweek):
            continue
        if int(as_of_gameweek) > int(lesson.expires_after_gw):
            continue
        adj = lesson.proposed_adjustment or {}
        if adj.get("target") != "xp_multiplier":
            continue
        try:
            factor = float(adj.get("factor") or 1.0)
        except (TypeError, ValueError):
            continue
        factor = max(cfg.min_adjustment_factor, min(cfg.max_adjustment_factor, factor))
        if abs(factor - 1.0) < 0.01:
            continue
        segment = str(adj.get("segment") or lesson.segment)
        prev = best.get(segment)
        if prev is not None and prev[0] >= int(lesson.as_of_gameweek):
            continue
        direction = "shrink" if factor < 1.0 else "boost"
        note = (
            f"Applied lesson on {segment}: {direction} projections by "
            f"{abs(1.0 - factor) * 100:.0f}% (backtested_pass from GW{lesson.as_of_gameweek})."
        )
        best[segment] = (int(lesson.as_of_gameweek), factor, note)

    factors = {seg: tup[1] for seg, tup in best.items()}
    notes = [tup[2] for _, tup in sorted(best.items())]
    return factors, notes


def prior_transfer_player_factors(
    reflection: dict[str, Any] | None,
    *,
    plans_dir: Path = DEFAULT_PLANS_DIR,
) -> tuple[dict[int, float], list[str]]:
    """Boost also_considered INs that beat last week's pick; dampen a clear miss."""
    if not reflection:
        return {}, []
    try:
        subject_gw = int(reflection.get("gameweek") or 0)
    except (TypeError, ValueError):
        return {}, []
    if subject_gw < 1:
        return {}, []

    factors: dict[int, float] = {}
    notes: list[str] = []

    alts = reflection.get("alternatives_reviewed") or []
    beaters: list[dict[str, Any]] = []
    for row in alts:
        if not isinstance(row, dict):
            continue
        if row.get("beat_the_pick") is True and int(row.get("in_id") or 0) > 0:
            beaters.append(row)

    pick_actual = reflection.get("transfer_actual_delta")
    for row in beaters:
        in_id = int(row["in_id"])
        actual = row.get("actual_delta")
        bump = _PRIOR_BEAT_STEP
        if isinstance(actual, (int, float)) and isinstance(pick_actual, (int, float)):
            bump = min(
                0.10,
                _PRIOR_BEAT_STEP + 0.01 * max(0.0, float(actual) - float(pick_actual)),
            )
        factor = min(_PRIOR_PLAYER_MAX, 1.0 + bump)
        factors[in_id] = max(factors.get(in_id, 1.0), factor)
        name = str(row.get("in_name") or in_id)
        notes.append(
            f"Prior GW{subject_gw}: {name} beat the recommended transfer on actual points "
            f"— boosting their projection by {(factor - 1.0) * 100:.0f}% this week."
        )

    plan = load_weekly_plan(subject_gw, plans_dir=plans_dir)
    best = (plan or {}).get("best_affordable") if isinstance(plan, dict) else None
    pick_in_id = int(best.get("in_id") or 0) if isinstance(best, dict) else 0
    transfer_out = reflection.get("transfer_out_name")
    transfer_in = reflection.get("transfer_in_name")
    should_dampen = bool(beaters) or (
        isinstance(pick_actual, (int, float)) and float(pick_actual) < 0
    )
    if pick_in_id and should_dampen:
        dampened = max(_PRIOR_PLAYER_MIN, min(factors.get(pick_in_id, 1.0), _PRIOR_MISS_DAMPEN))
        factors[pick_in_id] = dampened
        label = str(transfer_in or pick_in_id)
        notes.append(
            f"Prior GW{subject_gw}: recommended {transfer_out} → {label} underperformed "
            f"recorded alternatives (or lost points) — dampening {label} by "
            f"{(1.0 - dampened) * 100:.0f}% this week."
        )

    better = str(reflection.get("what_could_have_been_better") or "").strip()
    if better:
        notes.append(f"Prior GW{subject_gw} takeaway: {better}")

    return factors, notes


def build_learning_application(
    *,
    gameweek: int,
    reflection: dict[str, Any] | None,
    settings: ReflectionSettings | None = None,
    lessons_path: Path = DEFAULT_LESSONS_PATH,
    plans_dir: Path = DEFAULT_PLANS_DIR,
) -> LearningApplication:
    """Compose segment + prior-transfer factors for this predeadline run."""
    cfg = settings or ReflectionSettings()
    app = LearningApplication()
    if cfg.apply_backtested_lessons:
        seg, seg_notes = active_segment_factors(
            as_of_gameweek=gameweek,
            lessons_path=lessons_path,
            settings=cfg,
        )
        app.segment_factors.update(seg)
        app.notes.extend(seg_notes)
    if cfg.apply_prior_transfer_outcomes:
        players, prior_notes = prior_transfer_player_factors(
            reflection, plans_dir=plans_dir
        )
        app.player_factors.update(players)
        app.notes.extend(prior_notes)
    app.applied = bool(app.segment_factors or app.player_factors)
    if not app.notes and reflection:
        gw = reflection.get("gameweek")
        app.notes.append(
            f"Checked GW{gw} reflection for learning signals; no projection adjustments needed."
        )
    return app


def scale_projection(proj: PlayerProjection, factor: float) -> PlayerProjection:
    if abs(factor - 1.0) < 1e-9:
        return proj
    xp = tuple(round(x * factor, 6) for x in proj.xp_by_gw)
    weighted = round(float(proj.weighted_xp) * factor, 6)
    return replace(proj, xp_by_gw=xp, weighted_xp=weighted)


def apply_learning_to_projections(
    projections: dict[int, PlayerProjection],
    catalog: dict[int, dict[str, Any]],
    learning: LearningApplication,
) -> dict[int, PlayerProjection]:
    """Return a new mapping with segment and per-player multipliers applied."""
    if not learning.segment_factors and not learning.player_factors:
        return projections
    out: dict[int, PlayerProjection] = {}
    for pid, proj in projections.items():
        factor = 1.0
        segment = _segment_for_player(pid, catalog)
        if segment and segment in learning.segment_factors:
            factor *= learning.segment_factors[segment]
        if pid in learning.player_factors:
            factor *= learning.player_factors[pid]
        out[pid] = scale_projection(proj, factor)
    return out
