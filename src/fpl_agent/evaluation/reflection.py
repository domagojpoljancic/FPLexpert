"""Deterministic GW reflection gate and summary builder.

The ``data/evaluation/reflection-gw{N}.json`` cache written here is a derived,
safely recomputable artifact (official points can be corrected later per
``finality.py``; when that happens the cache is simply overwritten with a fresh
``computed_at``). It is **not** the immutable decision ledger — do not confuse
it with ``ledger.py``'s write-once contract.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from fpl_agent.cadence import parse_deadline
from fpl_agent.domain.run_state import utc_now
from fpl_agent.evaluation.finality import is_final
from fpl_agent.evaluation.replay import RootCause, grade_process_outcome
from fpl_agent.evaluation.scorecard import (
    fetch_live_points,
    load_latest_predeadline_plan,
    scorecard_from_plan,
)
from fpl_agent.ingestion.client import FplClient
from fpl_agent.suggest import next_gameweek

REFLECTION_SCHEMA_VERSION = "1.0.0"

_ROOT_CAUSE_PLAIN: dict[str, str] = {
    RootCause.SOUND_PROCESS_NORMAL_VARIANCE.value: (
        "the process was sound; this is normal week-to-week variance, not a mistake"
    ),
    RootCause.PROJECTION_OR_MINUTES_MISS.value: (
        "projections or minutes assumptions missed how the week played out"
    ),
    RootCause.NEWS_OR_DATA_FRESHNESS_MISS.value: (
        "news or data freshness lagged behind what happened"
    ),
    RootCause.SCENARIO_GENERATION_GAP.value: (
        "a relevant scenario was missing from the shortlist"
    ),
    RootCause.RANKING_OR_REASONING_MISS.value: (
        "ranking or reasoning ranked the wrong option among recorded choices"
    ),
    RootCause.RULES_OR_CALCULATION_BUG.value: (
        "a rules or calculation bug affected the numbers"
    ),
    RootCause.USER_EXECUTION_DIFFERENCE.value: (
        "the squad on pitch differed from the model's recommendation"
    ),
    RootCause.UNAVOIDABLE_LATE_EVENT.value: (
        "a late event after the decision lock made the outcome unavoidable"
    ),
    RootCause.INSUFFICIENT_EVIDENCE.value: (
        "there is not enough recorded evidence to grade the process yet"
    ),
}


class GwFinality(StrEnum):
    FINAL = "final"
    IN_PROGRESS = "in_progress"
    PROVISIONAL = "provisional"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class AlternativeReviewed:
    in_name: str
    in_id: int
    predicted_delta: float | None
    actual_delta: int | None
    beat_the_pick: bool | None
    position: str | None = None
    price_tier: str | None = None


@dataclass(frozen=True)
class PlayerCalibrationRow:
    """Per-XI-player predicted vs actual for segment calibration (M4).

    Price tiers (documented breakpoints, £m):
    - budget: < 5.0
    - mid: 5.0 inclusive through 8.0 inclusive
    - premium: > 8.0
    """

    player_id: int
    web_name: str
    position: str
    price_tier: str
    predicted_xp: float
    actual_points: int


@dataclass(frozen=True)
class ReflectionSummary:
    schema_version: str
    gameweek: int
    computed_at: str
    finality: str
    report_path: str | None
    predicted_xi_xp: float | None
    actual_xi_points: int | None
    model_captain_name: str
    model_captain_points: int
    predicted_captain_xp: float | None
    saved_captain_name: str | None
    saved_captain_points: int | None
    transfer_out_name: str | None
    transfer_in_name: str | None
    transfer_out_points: int | None
    transfer_in_points: int | None
    transfer_predicted_delta: float | None
    transfer_actual_delta: int | None
    process_quality: str
    outcome_quality: str
    root_cause: str
    alternatives_reviewed: tuple[AlternativeReviewed, ...]
    short_summary: str
    detail_summary: str
    what_could_have_been_better: str
    player_calibration: tuple[PlayerCalibrationRow, ...] = ()

    def as_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["alternatives_reviewed"] = [asdict(a) for a in self.alternatives_reviewed]
        payload["player_calibration"] = [asdict(r) for r in self.player_calibration]
        return payload


def price_tier_from_millions(price_m: float | None) -> str:
    """Map listed price (£m) to budget / mid / premium.

    Breakpoints: budget < 5.0; mid 5.0–8.0 inclusive; premium > 8.0.
    """
    if price_m is None:
        return "mid"
    if price_m < 5.0:
        return "budget"
    if price_m <= 8.0:
        return "mid"
    return "premium"


def gw_finality_status(
    *,
    bootstrap: dict[str, Any],
    fixtures: list[dict[str, Any]],
    gameweek: int,
    now: datetime | None = None,
) -> GwFinality:
    """Classify whether ``gameweek`` is safe to treat as an official result."""
    if gameweek <= 0:
        return GwFinality.NOT_APPLICABLE

    event = next(
        (e for e in (bootstrap.get("events") or []) if int(e.get("id") or 0) == gameweek),
        None,
    )
    if event is None:
        return GwFinality.UNKNOWN

    gw_fixtures = [f for f in fixtures if int(f.get("event") or 0) == gameweek]
    if not gw_fixtures:
        return GwFinality.UNKNOWN
    if any(not bool(f.get("finished")) for f in gw_fixtures):
        return GwFinality.IN_PROGRESS

    kickoffs: list[datetime] = []
    for row in gw_fixtures:
        parsed = parse_deadline(row.get("kickoff_time"))
        if parsed is None:
            return GwFinality.UNKNOWN
        kickoffs.append(parsed)

    final_match_end = max(kickoffs)
    checked = bool(event.get("data_checked"))
    when = now if now is not None else utc_now()
    if is_final(now=when, final_match_end=final_match_end, data_checked=checked):
        return GwFinality.FINAL
    return GwFinality.PROVISIONAL


def reflection_gate(
    bootstrap: dict[str, Any],
    fixtures: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> tuple[int, GwFinality]:
    """Return (subject_gw, status) for the GW immediately before next_gameweek."""
    subject_gw = next_gameweek(bootstrap) - 1
    status = gw_finality_status(
        bootstrap=bootstrap,
        fixtures=fixtures,
        gameweek=subject_gw,
        now=now,
    )
    return subject_gw, status


def reflection_cache_path(evaluation_dir: Path, gameweek: int) -> Path:
    return evaluation_dir / f"reflection-gw{gameweek}.json"


def load_reflection_summary(path: Path) -> ReflectionSummary:
    """Deserialize a persisted reflection cache into ``ReflectionSummary``."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    alts_raw = payload.get("alternatives_reviewed") or []
    alts = tuple(
        AlternativeReviewed(
            in_name=str(row.get("in_name") or ""),
            in_id=int(row.get("in_id") or 0),
            predicted_delta=_optional_float(row.get("predicted_delta")),
            actual_delta=_optional_int(row.get("actual_delta")),
            beat_the_pick=row.get("beat_the_pick") if isinstance(row.get("beat_the_pick"), bool) else None,
            position=str(row["position"]) if row.get("position") else None,
            price_tier=str(row["price_tier"]) if row.get("price_tier") else None,
        )
        for row in alts_raw
        if isinstance(row, dict)
    )
    cal_raw = payload.get("player_calibration") or []
    calibration = tuple(
        PlayerCalibrationRow(
            player_id=int(row.get("player_id") or 0),
            web_name=str(row.get("web_name") or ""),
            position=str(row.get("position") or "?"),
            price_tier=str(row.get("price_tier") or "mid"),
            predicted_xp=float(row.get("predicted_xp") or 0),
            actual_points=int(row.get("actual_points") or 0),
        )
        for row in cal_raw
        if isinstance(row, dict) and int(row.get("player_id") or 0)
    )
    return ReflectionSummary(
        schema_version=str(payload.get("schema_version") or REFLECTION_SCHEMA_VERSION),
        gameweek=int(payload["gameweek"]),
        computed_at=str(payload.get("computed_at") or ""),
        finality=str(payload.get("finality") or GwFinality.FINAL.value),
        report_path=payload.get("report_path"),
        predicted_xi_xp=_optional_float(payload.get("predicted_xi_xp")),
        actual_xi_points=_optional_int(payload.get("actual_xi_points")),
        model_captain_name=str(payload.get("model_captain_name") or ""),
        model_captain_points=int(payload.get("model_captain_points") or 0),
        predicted_captain_xp=_optional_float(payload.get("predicted_captain_xp")),
        saved_captain_name=payload.get("saved_captain_name"),
        saved_captain_points=_optional_int(payload.get("saved_captain_points")),
        transfer_out_name=payload.get("transfer_out_name"),
        transfer_in_name=payload.get("transfer_in_name"),
        transfer_out_points=_optional_int(payload.get("transfer_out_points")),
        transfer_in_points=_optional_int(payload.get("transfer_in_points")),
        transfer_predicted_delta=_optional_float(payload.get("transfer_predicted_delta")),
        transfer_actual_delta=_optional_int(payload.get("transfer_actual_delta")),
        process_quality=str(payload.get("process_quality") or ""),
        outcome_quality=str(payload.get("outcome_quality") or ""),
        root_cause=str(payload.get("root_cause") or ""),
        alternatives_reviewed=alts,
        short_summary=str(payload.get("short_summary") or ""),
        detail_summary=str(payload.get("detail_summary") or ""),
        what_could_have_been_better=str(payload.get("what_could_have_been_better") or ""),
        player_calibration=calibration,
    )


def build_reflection(
    *,
    gameweek: int,
    reports_dir: Path = Path("reports"),
    bootstrap: dict[str, Any],
    client: FplClient | None = None,
    player_points: dict[int, int] | None = None,
    evaluation_dir: Path = Path("data/evaluation"),
    persist: bool = True,
) -> ReflectionSummary | None:
    """Build a ``ReflectionSummary`` for a final gameweek, or ``None`` on soft failure.

    ``bootstrap`` supplies catalog prices/positions for per-player calibration rows.
    """
    plan = load_latest_predeadline_plan(reports_dir, gameweek)
    if plan is None:
        return None
    report_path = _latest_ok_report_path(reports_dir, gameweek)
    catalog = {
        int(el["id"]): el
        for el in (bootstrap.get("elements") or [])
        if isinstance(el, dict) and el.get("id") is not None
    }

    try:
        points = (
            player_points
            if player_points is not None
            else fetch_live_points(gameweek, client=client)
        )
    except Exception:
        return None

    plan_for_score = dict(plan)
    _backfill_process_fields(plan_for_score, points)

    card = scorecard_from_plan(
        gameweek=gameweek,
        weekly_plan=plan_for_score,
        player_points=points,
    )

    process, outcome, root = grade_process_outcome(
        recommendation_net=_optional_int(plan_for_score.get("recommendation_net")),
        roll_net=_optional_int(plan_for_score.get("roll_net")),
        actual_net=_grade_actual_net(plan_for_score, card),
        predeadline_ev_positive=(
            plan_for_score.get("predeadline_ev_positive")
            if isinstance(plan_for_score.get("predeadline_ev_positive"), bool)
            else None
        ),
    )

    best = plan.get("best_affordable") or {}
    transfer_out_name = str(best["out_name"]) if best.get("out_name") else None
    transfer_in_name = str(best["in_name"]) if best.get("in_name") else None
    transfer_predicted = _optional_float(best.get("delta_weighted_xp")) if best else None

    pick_actual = card.transfer_delta
    alternatives = _review_alternatives(
        plan=plan,
        player_points=points,
        pick_actual_delta=pick_actual,
        catalog=catalog,
    )
    calibration = _player_calibration_rows(
        plan=plan,
        player_points=points,
        catalog=catalog,
    )

    short = _build_short_summary(
        gameweek=gameweek,
        process=process.value,
        outcome=outcome.value,
        transfer_out_name=transfer_out_name,
        transfer_in_name=transfer_in_name,
        transfer_actual_delta=card.transfer_delta,
    )
    detail = _build_detail_summary(
        gameweek=gameweek,
        predicted_xi_xp=card.predicted_xi_xp,
        actual_xi_points=card.model_xi_points,
        model_captain_name=card.model_captain_name,
        model_captain_points=card.model_captain_points,
        saved_captain_name=card.saved_captain_name,
        saved_captain_points=card.saved_captain_points,
        transfer_out_name=transfer_out_name,
        transfer_in_name=transfer_in_name,
        transfer_actual_delta=card.transfer_delta,
        process=process.value,
        outcome=outcome.value,
        root_cause=root.value,
    )
    better = _what_could_have_been_better(
        alternatives=alternatives,
        pick_actual_delta=pick_actual,
        model_captain_name=card.model_captain_name,
        model_captain_points=card.model_captain_points,
        saved_captain_name=card.saved_captain_name,
        saved_captain_points=card.saved_captain_points,
        saved_captain_id=plan.get("saved_captain_id"),
    )

    summary = ReflectionSummary(
        schema_version=REFLECTION_SCHEMA_VERSION,
        gameweek=gameweek,
        computed_at=utc_now().isoformat(),
        finality=GwFinality.FINAL.value,
        report_path=str(report_path) if report_path is not None else None,
        predicted_xi_xp=card.predicted_xi_xp,
        actual_xi_points=card.model_xi_points,
        model_captain_name=card.model_captain_name,
        model_captain_points=card.model_captain_points,
        predicted_captain_xp=card.predicted_captain_xp,
        saved_captain_name=card.saved_captain_name,
        saved_captain_points=card.saved_captain_points,
        transfer_out_name=transfer_out_name,
        transfer_in_name=transfer_in_name,
        transfer_out_points=card.transfer_out_points,
        transfer_in_points=card.transfer_in_points,
        transfer_predicted_delta=transfer_predicted,
        transfer_actual_delta=card.transfer_delta,
        process_quality=process.value,
        outcome_quality=outcome.value,
        root_cause=root.value,
        alternatives_reviewed=alternatives,
        short_summary=short,
        detail_summary=detail,
        what_could_have_been_better=better,
        player_calibration=calibration,
    )

    if persist:
        evaluation_dir.mkdir(parents=True, exist_ok=True)
        path = reflection_cache_path(evaluation_dir, gameweek)
        path.write_text(
            json.dumps(summary.as_payload(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return summary


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _latest_ok_report_path(reports_dir: Path, gameweek: int) -> Path | None:
    paths = sorted(reports_dir.glob(f"predeadline-gw{gameweek}-*.json"), reverse=True)
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        plan = payload.get("weekly_plan")
        if isinstance(plan, dict) and plan.get("ok"):
            return path
    return None


def _backfill_process_fields(plan: dict[str, Any], player_points: dict[int, int]) -> None:
    """Fill dead process fields from populated plan data so grading can run.

    Lives here (not in ``scorecard.py``) so the standalone scorecard CLI contract
    stays unchanged.
    """
    has_ev = isinstance(plan.get("predeadline_ev_positive"), bool)
    has_rec = plan.get("recommendation_net") is not None
    has_roll = plan.get("roll_net") is not None
    if has_ev and has_rec and has_roll:
        return

    after = plan.get("after_transfer")
    best = plan.get("best_affordable") or {}
    if not after or not best:
        # Hold recommendation: no transfer thesis to grade this way.
        return

    if not has_ev:
        plan["predeadline_ev_positive"] = bool(float(best.get("delta_weighted_xp") or 0) > 0)

    out_id = int(best.get("out_id") or 0)
    in_id = int(best.get("in_id") or 0)
    if out_id and in_id and out_id in player_points and in_id in player_points:
        if not has_rec:
            plan["recommendation_net"] = int(player_points[in_id])
        if not has_roll:
            plan["roll_net"] = int(player_points[out_id])


def _grade_actual_net(plan: dict[str, Any], card: Any) -> int | None:
    """Prefer transfer-centric actual net when backfilled; else XI total."""
    rec = plan.get("recommendation_net")
    roll = plan.get("roll_net")
    if rec is not None and roll is not None:
        # Grade the transfer itself: recommended IN points vs holding OUT.
        return int(rec)
    # Mirror scorecard's XI-with-captain adjustment when no transfer nets exist.
    return int(card.model_xi_points)


def _review_alternatives(
    *,
    plan: dict[str, Any],
    player_points: dict[int, int],
    pick_actual_delta: int | None,
    catalog: dict[int, dict[str, Any]] | None = None,
) -> tuple[AlternativeReviewed, ...]:
    """Build alternative reviews from recorded ``also_considered`` only.

    Note: ``also_considered`` is same-*position* (see ``same_position_shortlist``),
    not necessarily same-OUT — each row's own ``out_id`` is used for actual delta.
    """
    catalog = catalog or {}
    rows = [r for r in (plan.get("also_considered") or []) if isinstance(r, dict)]
    out: list[AlternativeReviewed] = []
    for row in rows:
        if row.get("picked"):
            continue
        in_id = int(row.get("in_id") or 0)
        out_id = int(row.get("out_id") or 0)
        in_name = str(row.get("in_name") or in_id or "?")
        if not in_id:
            continue
        predicted = _optional_float(row.get("delta_weighted_xp"))
        if predicted is None:
            predicted = _optional_float(row.get("delta_gw_xp"))
        actual: int | None = None
        if in_id in player_points and out_id and out_id in player_points:
            actual = int(player_points[in_id]) - int(player_points[out_id])
        beat: bool | None = None
        if actual is not None and pick_actual_delta is not None:
            beat = actual > pick_actual_delta
        pos, tier = _position_and_tier(in_id, catalog, fallback_pos=row.get("position"))
        out.append(
            AlternativeReviewed(
                in_name=in_name,
                in_id=in_id,
                predicted_delta=predicted,
                actual_delta=actual,
                beat_the_pick=beat,
                position=pos,
                price_tier=tier,
            )
        )
    return tuple(out)


_ELEMENT_TYPE_POS = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


def _position_and_tier(
    player_id: int,
    catalog: dict[int, dict[str, Any]],
    *,
    fallback_pos: object = None,
) -> tuple[str | None, str | None]:
    el = catalog.get(player_id) or {}
    pos = None
    if fallback_pos:
        pos = str(fallback_pos)
    et = el.get("element_type")
    if et is not None:
        pos = _ELEMENT_TYPE_POS.get(int(et), pos)
    price_m = None
    if el.get("now_cost") is not None:
        price_m = float(el["now_cost"]) / 10.0
    tier = price_tier_from_millions(price_m) if price_m is not None else None
    return pos, tier


def _player_calibration_rows(
    *,
    plan: dict[str, Any],
    player_points: dict[int, int],
    catalog: dict[int, dict[str, Any]],
) -> tuple[PlayerCalibrationRow, ...]:
    rows: list[PlayerCalibrationRow] = []
    for row in plan.get("xi") or []:
        if not isinstance(row, dict):
            continue
        pid = int(row.get("player_id") or 0)
        if not pid:
            continue
        predicted = float(row.get("xp_next") or 0)
        actual = int(player_points.get(pid, 0))
        pos = str(row.get("position") or "") or None
        cat_pos, tier = _position_and_tier(pid, catalog, fallback_pos=pos)
        position = cat_pos or pos or "?"
        price_tier = tier or "mid"
        rows.append(
            PlayerCalibrationRow(
                player_id=pid,
                web_name=str(row.get("web_name") or pid),
                position=position,
                price_tier=price_tier,
                predicted_xp=predicted,
                actual_points=actual,
            )
        )
    return tuple(rows)


def _process_word(process: str) -> str:
    return {
        "good": "good",
        "mixed": "mixed",
        "poor": "poor",
        "insufficient_evidence": "unproven",
    }.get(process, process.replace("_", " "))


def _outcome_word(outcome: str) -> str:
    return {
        "positive": "positive",
        "neutral": "neutral",
        "negative": "negative",
    }.get(outcome, outcome.replace("_", " "))


def _build_short_summary(
    *,
    gameweek: int,
    process: str,
    outcome: str,
    transfer_out_name: str | None,
    transfer_in_name: str | None,
    transfer_actual_delta: int | None,
) -> str:
    process_word = _process_word(process)
    outcome_word = _outcome_word(outcome)
    if transfer_out_name and transfer_in_name and transfer_actual_delta is not None:
        sign = "+" if transfer_actual_delta >= 0 else ""
        return (
            f"Last week (GW{gameweek}): {process_word} process, {outcome_word} outcome — "
            f"{transfer_out_name} → {transfer_in_name} was {sign}{transfer_actual_delta} pts."
        )
    return (
        f"Last week (GW{gameweek}): {process_word} process, {outcome_word} outcome "
        f"(no transfer recommended)."
    )


def _build_detail_summary(
    *,
    gameweek: int,
    predicted_xi_xp: float | None,
    actual_xi_points: int | None,
    model_captain_name: str,
    model_captain_points: int,
    saved_captain_name: str | None,
    saved_captain_points: int | None,
    transfer_out_name: str | None,
    transfer_in_name: str | None,
    transfer_actual_delta: int | None,
    process: str,
    outcome: str,
    root_cause: str,
) -> str:
    parts: list[str] = []
    if predicted_xi_xp is not None and actual_xi_points is not None:
        parts.append(
            f"GW{gameweek} model XI predicted {predicted_xi_xp:.1f} xp and scored "
            f"{actual_xi_points} official points."
        )
    elif actual_xi_points is not None:
        parts.append(f"GW{gameweek} model XI scored {actual_xi_points} official points.")

    cap_line = (
        f"Model captain {model_captain_name} scored {model_captain_points} "
        f"(captain points, doubled)."
    )
    if (
        saved_captain_name
        and saved_captain_points is not None
        and saved_captain_name != model_captain_name
    ):
        cap_line += (
            f" Saved captain {saved_captain_name} scored {saved_captain_points}."
        )
    parts.append(cap_line)

    if transfer_out_name and transfer_in_name and transfer_actual_delta is not None:
        sign = "+" if transfer_actual_delta >= 0 else ""
        parts.append(
            f"Transfer {transfer_out_name} → {transfer_in_name} finished "
            f"{sign}{transfer_actual_delta} pts vs the sold player."
        )
    else:
        parts.append("No transfer was recommended for that week.")

    root_plain = _ROOT_CAUSE_PLAIN.get(root_cause, root_cause.replace("_", " "))
    parts.append(
        f"Process graded {process.replace('_', ' ')}; outcome "
        f"{outcome.replace('_', ' ')} — {root_plain}."
    )
    return " ".join(parts)


def _what_could_have_been_better(
    *,
    alternatives: tuple[AlternativeReviewed, ...],
    pick_actual_delta: int | None,
    model_captain_name: str,
    model_captain_points: int,
    saved_captain_name: str | None,
    saved_captain_points: int | None,
    saved_captain_id: object,
) -> str:
    beaters = [a for a in alternatives if a.beat_the_pick is True and a.actual_delta is not None]
    if beaters and pick_actual_delta is not None:
        best = max(beaters, key=lambda a: int(a.actual_delta or 0))
        edge = int(best.actual_delta or 0) - pick_actual_delta
        return (
            f"{best.in_name} was in the shortlist and would have scored more "
            f"(+{edge} pts actual delta vs the pick)."
        )

    if (
        saved_captain_id is not None
        and saved_captain_name
        and saved_captain_name != model_captain_name
        and saved_captain_points is not None
        and saved_captain_points > model_captain_points
    ):
        return (
            f"Saved captain {saved_captain_name} outscored model captain "
            f"{model_captain_name} ({saved_captain_points} vs {model_captain_points})."
        )

    return "No recorded alternative would have done better."


def root_cause_plain(root_cause: str) -> str:
    """Spell a root-cause enum value in plain language for report prose."""
    return _ROOT_CAUSE_PLAIN.get(root_cause, root_cause.replace("_", " "))
