"""Append/load content-addressed public price snapshots. No secrets."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fpl_agent.domain.run_state import stable_json_hash
from fpl_agent.prices.types import PlayerPriceRow, PriceSnapshot

SCHEMA_VERSION = "prices-snapshot-1.0.0"
ADAPTER_VERSION = "1.0.0"
DEFAULT_ROOT = Path("data/snapshots/prices")


def parse_ownership(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().rstrip("%")
    try:
        return float(text)
    except ValueError:
        return None


def parse_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def player_row_from_element(el: dict[str, Any]) -> PlayerPriceRow | None:
    pid = parse_optional_int(el.get("id"))
    cost = parse_optional_int(el.get("now_cost"))
    if pid is None or cost is None:
        return None
    return PlayerPriceRow(
        player_id=pid,
        now_cost=cost,
        transfers_in_event=parse_optional_int(el.get("transfers_in_event")),
        transfers_out_event=parse_optional_int(el.get("transfers_out_event")),
        selected_by_percent=parse_ownership(el.get("selected_by_percent")),
        cost_change_event=parse_optional_int(el.get("cost_change_event")),
        cost_change_event_fall=parse_optional_int(el.get("cost_change_event_fall")),
        status=str(el["status"]) if el.get("status") is not None else None,
        chance_of_playing_next_round=parse_optional_float(el.get("chance_of_playing_next_round")),
        web_name=str(el["web_name"]) if el.get("web_name") is not None else None,
    )


def snapshot_from_bootstrap(
    bootstrap: dict[str, Any],
    *,
    event_id: int,
    season: str,
    retrieved_at: datetime | None = None,
) -> PriceSnapshot:
    retrieved_at = retrieved_at or datetime.now(UTC)
    rows: list[PlayerPriceRow] = []
    for el in bootstrap.get("elements") or []:
        if isinstance(el, dict):
            row = player_row_from_element(el)
            if row is not None:
                rows.append(row)
    payload = [r.model_dump(mode="json") for r in rows]
    return PriceSnapshot(
        retrieved_at=retrieved_at,
        event_id=event_id,
        season=season,
        schema_version=SCHEMA_VERSION,
        adapter_version=ADAPTER_VERSION,
        content_hash=stable_json_hash(payload),
        players=rows,
    )


def gw_dir(root: Path, season: str, event_id: int) -> Path:
    return root / season / f"gw-{event_id:02d}"


def load_snapshots(root: Path, season: str, event_id: int) -> list[PriceSnapshot]:
    folder = gw_dir(root, season, event_id)
    if not folder.exists():
        return []
    out: list[PriceSnapshot] = []
    for path in sorted(folder.glob("*.json")):
        if path.name in {"latest.json", "notify-state.json"}:
            continue
        try:
            out.append(PriceSnapshot.model_validate_json(path.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            continue
    out.sort(key=lambda s: s.retrieved_at)
    return out


def append_snapshot(
    snapshot: PriceSnapshot,
    *,
    root: Path = DEFAULT_ROOT,
    max_per_gw: int = 48,
) -> Path | None:
    folder = gw_dir(root, snapshot.season, snapshot.event_id)
    folder.mkdir(parents=True, exist_ok=True)
    existing = load_snapshots(root, snapshot.season, snapshot.event_id)
    if existing and existing[-1].content_hash == snapshot.content_hash:
        latest = folder / "latest.json"
        latest.write_text(existing[-1].model_dump_json(indent=2), encoding="utf-8")
        return None
    stamp = snapshot.retrieved_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = folder / f"{stamp}.json"
    if path.exists():
        path = folder / f"{stamp}-{snapshot.content_hash[:8]}.json"
    path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
    (folder / "latest.json").write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
    _prune(folder, max_per_gw=max_per_gw)
    _retain_previous_gw_latest(root, snapshot.season, snapshot.event_id)
    return path


def _prune(folder: Path, *, max_per_gw: int) -> None:
    files = sorted(
        [p for p in folder.glob("*.json") if p.name not in {"latest.json", "notify-state.json"}],
        key=lambda p: p.name,
    )
    extra = len(files) - max_per_gw
    for path in files[: max(0, extra)]:
        path.unlink(missing_ok=True)


def _retain_previous_gw_latest(root: Path, season: str, event_id: int) -> None:
    """Drop whole GW folders older than previous, keeping each remaining latest.json."""
    season_dir = root / season
    if not season_dir.exists():
        return
    gws: list[tuple[int, Path]] = []
    for child in season_dir.iterdir():
        if child.is_dir() and child.name.startswith("gw-"):
            try:
                gws.append((int(child.name.split("-", 1)[1]), child))
            except ValueError:
                continue
    keep = {event_id, event_id - 1}
    for gw, folder in gws:
        if gw not in keep:
            for path in folder.glob("*"):
                if path.name != "latest.json":
                    path.unlink(missing_ok=True)


def row_map(snapshot: PriceSnapshot) -> dict[int, PlayerPriceRow]:
    return {p.player_id: p for p in snapshot.players}


def dumps_notify_state(path: Path, fingerprints: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"fingerprints": fingerprints}, indent=2), encoding="utf-8")


def load_notify_state(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    raw = data.get("fingerprints") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw]
