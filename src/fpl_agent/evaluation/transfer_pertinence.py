"""Multi-GW transfer thesis tracking (append-only versions).

``horizon_gameweeks`` and ``predicted_delta_by_gw`` are fixed at version 1.
Later versions only grow ``actual_delta_by_gw`` / cumulatives / ``status``.
Decision-ledger records remain immutable — progress lives only here.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_THESES_JSONL = Path("data/evaluation/transfer-theses.jsonl")
DEFAULT_THESES_LATEST = Path("data/evaluation/transfer-theses-latest.json")
DEFAULT_LEDGER_ROOT = Path("data/decision-ledger")


@dataclass(frozen=True)
class TransferThesis:
    decision_id: str
    version: int
    out_id: int
    out_name: str
    in_id: int
    in_name: str
    gameweek_made: int
    horizon_gameweeks: tuple[int, ...]
    predicted_delta_by_gw: dict[int, float]
    actual_delta_by_gw: dict[int, int]
    cumulative_predicted_delta: float
    cumulative_actual_delta: int
    status: str
    alternatives: tuple[dict[str, Any], ...] = ()

    def as_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        # JSON keys for gw maps must be strings
        payload["predicted_delta_by_gw"] = {
            str(k): v for k, v in self.predicted_delta_by_gw.items()
        }
        payload["actual_delta_by_gw"] = {
            str(k): v for k, v in self.actual_delta_by_gw.items()
        }
        payload["horizon_gameweeks"] = list(self.horizon_gameweeks)
        payload["alternatives"] = list(self.alternatives)
        return payload


def thesis_from_payload(payload: dict[str, Any]) -> TransferThesis:
    pred = {
        int(k): float(v) for k, v in (payload.get("predicted_delta_by_gw") or {}).items()
    }
    actual = {
        int(k): int(v) for k, v in (payload.get("actual_delta_by_gw") or {}).items()
    }
    alts = tuple(
        row for row in (payload.get("alternatives") or []) if isinstance(row, dict)
    )
    return TransferThesis(
        decision_id=str(payload["decision_id"]),
        version=int(payload.get("version") or 1),
        out_id=int(payload["out_id"]),
        out_name=str(payload.get("out_name") or ""),
        in_id=int(payload["in_id"]),
        in_name=str(payload.get("in_name") or ""),
        gameweek_made=int(payload["gameweek_made"]),
        horizon_gameweeks=tuple(int(g) for g in (payload.get("horizon_gameweeks") or [])),
        predicted_delta_by_gw=pred,
        actual_delta_by_gw=actual,
        cumulative_predicted_delta=float(payload.get("cumulative_predicted_delta") or 0),
        cumulative_actual_delta=int(payload.get("cumulative_actual_delta") or 0),
        status=str(payload.get("status") or "open"),
        alternatives=alts,
    )


def open_theses_from_ledger(
    root: Path,
    season: str,
    *,
    existing: dict[str, TransferThesis] | None = None,
) -> list[TransferThesis]:
    """Open version-1 theses from enriched decision-ledger transfer records.

    Skips decision_ids that already have a thesis in ``existing`` (latest map).
    """
    existing = existing or {}
    season_root = root / season
    if not season_root.exists():
        return []
    opened: list[TransferThesis] = []
    for gw_dir in sorted(season_root.glob("gw-*")):
        canonical = gw_dir / "canonical.json"
        if not canonical.exists():
            continue
        try:
            pointer = json.loads(canonical.read_text(encoding="utf-8"))
            decision_id = str(pointer.get("decision_id") or "")
            path = gw_dir / f"{decision_id}.json"
            if not path.exists():
                continue
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
        if decision_id in existing:
            continue
        primary = record.get("primary") or {}
        out_id = primary.get("out_id")
        in_id = primary.get("in_id")
        if not out_id or not in_id:
            continue
        horizon_gws = [
            int(g)
            for g in (primary.get("horizon_gameweeks") or [])
            if g is not None
        ]
        pred_map_raw = primary.get("predicted_delta_by_gw") or {}
        pred_map = {int(k): float(v) for k, v in pred_map_raw.items()}
        if not pred_map and primary.get("horizon_impact_by_gw"):
            for row in primary["horizon_impact_by_gw"]:
                gw = row.get("gw") or row.get("gameweek")
                if gw is None:
                    continue
                pred_map[int(gw)] = float(row.get("delta_xp") or 0)
                if int(gw) not in horizon_gws:
                    horizon_gws.append(int(gw))
        if not horizon_gws and pred_map:
            horizon_gws = sorted(pred_map)
        alts = tuple(
            row for row in (record.get("alternatives") or []) if isinstance(row, dict)
        )
        thesis = TransferThesis(
            decision_id=decision_id,
            version=1,
            out_id=int(out_id),
            out_name=str(primary.get("out_name") or out_id),
            in_id=int(in_id),
            in_name=str(primary.get("in_name") or in_id),
            gameweek_made=int(record.get("gameweek") or 0),
            horizon_gameweeks=tuple(horizon_gws),
            predicted_delta_by_gw=pred_map,
            actual_delta_by_gw={},
            cumulative_predicted_delta=round(sum(pred_map.values()), 3),
            cumulative_actual_delta=0,
            status="open",
            alternatives=alts,
        )
        opened.append(thesis)
    return opened


def update_theses_for_gameweek(
    theses: list[TransferThesis],
    *,
    gameweek: int,
    player_points: dict[int, int],
    current_squad_ids: set[int],
) -> list[TransferThesis]:
    """Return new versions only when state actually changes (idempotent)."""
    updated: list[TransferThesis] = []
    for thesis in theses:
        if thesis.status != "open":
            updated.append(thesis)
            continue

        # Player sold after the move week — close without inventing further GWs.
        if gameweek > thesis.gameweek_made and thesis.in_id not in current_squad_ids:
            if thesis.status == "closed_player_sold":
                updated.append(thesis)
                continue
            closed = _replace_thesis(
                thesis,
                version=thesis.version + 1,
                status="closed_player_sold",
            )
            updated.append(closed)
            continue

        if gameweek not in thesis.horizon_gameweeks:
            updated.append(thesis)
            continue
        if gameweek in thesis.actual_delta_by_gw:
            # Already filled — idempotent no-op (same version).
            updated.append(thesis)
            continue
        if thesis.in_id not in player_points or thesis.out_id not in player_points:
            updated.append(thesis)
            continue

        delta = int(player_points[thesis.in_id]) - int(player_points[thesis.out_id])
        new_actual = dict(thesis.actual_delta_by_gw)
        new_actual[gameweek] = delta
        filled = set(new_actual)
        horizon = set(thesis.horizon_gameweeks)
        status = "closed_horizon_complete" if horizon and horizon <= filled else "open"
        # Cumulative predicted over filled weeks only ("so far").
        pred_so_far = sum(
            float(thesis.predicted_delta_by_gw.get(gw, 0)) for gw in sorted(filled)
        )
        new_thesis = _replace_thesis(
            thesis,
            version=thesis.version + 1,
            actual_delta_by_gw=new_actual,
            cumulative_predicted_delta=round(pred_so_far, 3),
            cumulative_actual_delta=sum(new_actual.values()),
            status=status,
        )
        updated.append(new_thesis)
    return updated


def persist_theses(
    theses: list[TransferThesis],
    *,
    jsonl_path: Path = DEFAULT_THESES_JSONL,
    latest_path: Path = DEFAULT_THESES_LATEST,
    previous_latest: dict[str, TransferThesis] | None = None,
) -> None:
    """Append only theses whose version advanced; rebuild latest pointer."""
    previous_latest = previous_latest or load_latest_theses(latest_path)
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    latest: dict[str, TransferThesis] = dict(previous_latest)
    with jsonl_path.open("a", encoding="utf-8") as fh:
        for thesis in theses:
            prev = previous_latest.get(thesis.decision_id)
            if prev is not None and prev.version == thesis.version and prev.status == thesis.status:
                # Same version — skip append (idempotent re-run).
                latest[thesis.decision_id] = thesis
                continue
            if prev is not None and prev.version == thesis.version:
                latest[thesis.decision_id] = thesis
                continue
            # New open (v1) or advanced version.
            if prev is None or thesis.version > prev.version:
                fh.write(json.dumps(thesis.as_payload(), sort_keys=True) + "\n")
            latest[thesis.decision_id] = thesis
    latest_path.write_text(
        json.dumps(
            {did: t.as_payload() for did, t in latest.items()},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def load_latest_theses(path: Path = DEFAULT_THESES_LATEST) -> dict[str, TransferThesis]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    out: dict[str, TransferThesis] = {}
    for did, row in payload.items():
        if isinstance(row, dict):
            out[str(did)] = thesis_from_payload(row)
    return out


def sync_theses_for_reflection(
    *,
    gameweek: int,
    player_points: dict[int, int],
    current_squad_ids: set[int],
    season: str = "2026-27",
    ledger_root: Path = DEFAULT_LEDGER_ROOT,
    jsonl_path: Path = DEFAULT_THESES_JSONL,
    latest_path: Path = DEFAULT_THESES_LATEST,
) -> list[TransferThesis]:
    """Open new theses from the ledger, update for ``gameweek``, persist versions."""
    latest = load_latest_theses(latest_path)
    newly_opened = open_theses_from_ledger(ledger_root, season, existing=latest)
    combined = list(latest.values()) + newly_opened
    updated = update_theses_for_gameweek(
        combined,
        gameweek=gameweek,
        player_points=player_points,
        current_squad_ids=current_squad_ids,
    )
    persist_theses(
        updated,
        jsonl_path=jsonl_path,
        latest_path=latest_path,
        previous_latest=latest,
    )
    return list(load_latest_theses(latest_path).values())


def format_theses_section(
    theses: list[TransferThesis],
    *,
    current_gameweek: int,
    max_rows: int = 6,
) -> list[str]:
    """Markdown table for aged transfer calls (recorded alternatives only)."""
    relevant: list[TransferThesis] = []
    for thesis in theses:
        if thesis.status == "open":
            relevant.append(thesis)
        elif thesis.status.startswith("closed"):
            # Show closed theses from roughly the last few weeks of horizon end.
            last_gw = max(thesis.horizon_gameweeks) if thesis.horizon_gameweeks else thesis.gameweek_made
            if current_gameweek - last_gw <= 3:
                relevant.append(thesis)
    relevant.sort(key=lambda t: (-t.gameweek_made, t.decision_id))
    relevant = relevant[:max_rows]
    if not relevant:
        return []

    lines = [
        "### How past transfer calls have aged",
        "",
        "| Move | Made | Weeks tracked | Predicted (so far) | Actual (so far) | Verdict |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for thesis in relevant:
        tracked = len(thesis.actual_delta_by_gw)
        horizon_n = len(thesis.horizon_gameweeks) or tracked
        pred = thesis.cumulative_predicted_delta
        act = thesis.cumulative_actual_delta
        remaining = max(0, horizon_n - tracked)
        if thesis.status == "open":
            if act > pred:
                verdict = f"Paying off — ahead of plan, {remaining} GWs left in its horizon"
            elif act < pred:
                verdict = f"Behind plan — {remaining} GWs left in its horizon"
            else:
                verdict = f"On plan — {remaining} GWs left in its horizon"
        elif thesis.status == "closed_horizon_complete":
            verdict = f"Closed — net {act:+d} pt over its {horizon_n}-GW horizon"
        elif thesis.status == "closed_player_sold":
            verdict = "Closed — player left the squad before the horizon ended"
        else:
            verdict = f"Closed ({thesis.status})"
        lines.append(
            f"| {thesis.out_name} → {thesis.in_name} | GW{thesis.gameweek_made} | "
            f"{tracked} / {horizon_n} | {pred:+.1f} | {act:+d} | {verdict} |"
        )

        # Optional better-line from recorded alternatives only.
        better = _better_from_recorded_alts(thesis)
        if better:
            lines.append("")
            lines.append(better)
    return lines


def _better_from_recorded_alts(thesis: TransferThesis) -> str | None:
    names = []
    for row in thesis.alternatives:
        if row.get("picked"):
            continue
        name = row.get("in_name")
        if name:
            names.append(str(name))
    if not names:
        return None
    # Informational only — do not invent outcomes for alts without actuals.
    return (
        f"_Recorded alternatives for {thesis.out_name} → {thesis.in_name}: "
        + ", ".join(names)
        + "._"
    )


def _replace_thesis(thesis: TransferThesis, **changes: Any) -> TransferThesis:
    data = asdict(thesis)
    data.update(changes)
    data["horizon_gameweeks"] = tuple(data["horizon_gameweeks"])
    data["alternatives"] = tuple(data.get("alternatives") or ())
    return TransferThesis(**data)
