"""Run price snapshot → score → smart-to-act → report. No OpenAI."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fpl_agent.cadence import hours_until, next_deadline, parse_deadline
from fpl_agent.config import Settings, load_settings
from fpl_agent.domain.models import SeasonId
from fpl_agent.domain.run_state import stable_json_hash
from fpl_agent.errors import AgentError, AgentErrorCode, ExitCode
from fpl_agent.prices.actions import PlanView, classify_all
from fpl_agent.prices.alerts import (
    issue_comment_ops,
    maybe_post_webhook,
    notify_payload,
    select_new_notifications,
)
from fpl_agent.prices.model import score_player
from fpl_agent.prices.outcomes import append_outcomes, outcomes_from_snapshots
from fpl_agent.prices.report import render_prices_markdown, report_status, status_headline
from fpl_agent.prices.snapshot import (
    DEFAULT_ROOT,
    append_snapshot,
    gw_dir,
    load_snapshots,
    row_map,
    snapshot_from_bootstrap,
)
from fpl_agent.prices.types import (
    PriceAction,
    PricePrediction,
    ReportStatus,
)
from fpl_agent.rules.season import load_season_rules_2026_27
from fpl_agent.strategy.engine import TransferMove, generate_scenarios
from fpl_agent.suggest import load_public_data
from fpl_agent.team_state.private import load_and_validate_private_state
from fpl_agent.team_state.resolve import resolve_team_state

Universe = Literal["squad", "plan", "watchlist", "all-relevant", "catalog"]


@dataclass
class PricesReport:
    gameweek: int
    status: ReportStatus
    headline: str
    predictions: list[PricePrediction]
    actions: list[PriceAction]
    markdown: str
    warnings: list[str]
    executability: str
    notified: list[dict[str, Any]]
    model_version: str
    snapshot_hashes: list[str]
    report_hash: str


def load_plan_view(
    *,
    reports_dir: Path,
    gameweek: int,
    team: Any,
    rules: Any,
    settings: Settings,
    catalog: dict[int, dict[str, Any]],
) -> PlanView:
    artifacts = sorted(
        list(reports_dir.glob(f"predeadline-gw{gameweek}-*.json"))
        + list(reports_dir.glob(f"daily-gw{gameweek}-*.json"))
        + list(reports_dir.glob(f"analyze-gw{gameweek}-*.json")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    transfers: list[TransferMove] = []
    scenario_id: str | None = None
    gain = 0.0
    hit = 0
    legal = False
    beats = False
    for path in artifacts[:3]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for sc in data.get("scenarios") or []:
            raw_t = sc.get("transfers") or []
            parsed: list[TransferMove] = []
            for t in raw_t:
                try:
                    parsed.append(
                        TransferMove(
                            out_id=int(t["out_id"]),
                            in_id=int(t["in_id"]),
                            sell_tenths=int(t.get("sell_tenths") or 0),
                            buy_tenths=int(t.get("buy_tenths") or 0),
                        )
                    )
                except (KeyError, TypeError, ValueError):
                    continue
            if parsed:
                transfers = parsed
                scenario_id = sc.get("scenario_id")
                gain = float(sc.get("gain_vs_roll") or 0)
                hit = int(sc.get("hit_cost") or 0)
                legal = bool(sc.get("legality_ok"))
                beats = gain > 0 and legal
                break
        if transfers:
            break
        for move in data.get("suggested_moves") or []:
            if move.get("move_type") != "transfer":
                continue
            ids = [int(x) for x in (move.get("player_ids") or []) if x]
            owned = {p.player_id for p in (team.squad.value or [])}
            outs = [i for i in ids if i in owned]
            ins = [i for i in ids if i not in owned]
            if outs and ins:
                transfers.append(
                    TransferMove(out_id=outs[0], in_id=ins[0], sell_tenths=0, buy_tenths=0)
                )
                legal = team.executability.value == "EXECUTABLE"
                beats = True
                scenario_id = scenario_id or "artifact-transfer"
    if transfers:
        return PlanView(
            transfers=transfers,
            scenario_id=scenario_id,
            gain_vs_roll=gain,
            hit_cost=hit,
            legality_ok=legal,
            football_beats_roll=beats,
        )

    squad_dicts = []
    xp: dict[int, list[float]] = {}
    horizon = len(settings.planning.weights)
    for p in team.squad.value or []:
        squad_dicts.append(
            {
                "player_id": p.player_id,
                "position": p.position.value,
                "club_id": p.club_id,
                "purchase_price_tenths": p.purchase_price_tenths,
                "current_price_tenths": p.current_price_tenths,
            }
        )
        xp[p.player_id] = [1.0] * horizon
    scenarios, _ = generate_scenarios(
        rules=rules,
        executability=team.executability,
        bank_tenths=team.bank_tenths.value,
        free_transfers=team.free_transfers.value,
        squad=squad_dicts,
        xp_by_player=xp,
        weights=settings.planning.weights,
        max_hit=settings.planning.max_hit,
        hits_enabled=settings.planning.hits_enabled,
        risk_profile=settings.manager.risk_profile,
    )
    best = next((s for s in scenarios if s.transfers and s.gain_vs_roll > 0 and s.legality_ok), None)
    if best is None:
        return PlanView()
    real = [t for t in best.transfers if t.in_id and t.out_id]
    return PlanView(
        transfers=real,
        scenario_id=best.scenario_id,
        gain_vs_roll=best.gain_vs_roll,
        hit_cost=best.hit_cost,
        legality_ok=best.legality_ok and bool(real),
        football_beats_roll=best.gain_vs_roll > 0 and bool(real),
    )


def resolve_universe(
    kind: Universe,
    *,
    owned: set[int],
    plan: PlanView,
    watchlist: set[int],
    catalog: set[int],
) -> set[int]:
    if kind == "catalog":
        return set(catalog)
    if kind == "squad":
        return set(owned)
    if kind == "plan":
        return set(plan.in_ids | plan.out_ids)
    if kind == "watchlist":
        return set(watchlist)
    return set(owned) | set(plan.in_ids) | set(plan.out_ids) | set(watchlist)


def run_prices(
    *,
    settings: Settings | None = None,
    offline: bool = False,
    universe: Universe = "all-relevant",
    notify: bool | None = None,
    save: bool = True,
    private_path: Path = Path("data/private-state/current.json"),
    snapshot_root: Path = DEFAULT_ROOT,
    reports_dir: Path = Path("reports"),
    outcomes_path: Path = Path("data/outcomes/prices.jsonl"),
    now: datetime | None = None,
    plan: PlanView | None = None,
    bootstrap: dict[str, Any] | None = None,
) -> PricesReport:
    settings = settings or load_settings()
    now = now or datetime.now(UTC)
    warnings: list[str] = []

    if not settings.prices.enabled:
        raise AgentError(
            "prices.enabled is false",
            code=AgentErrorCode.INVALID_CONFIGURATION,
            exit_code=ExitCode.INVALID_CONFIG,
        )
    if not private_path.exists():
        raise AgentError(
            f"private squad missing: {private_path}. Save your squad first.",
            code=AgentErrorCode.INSUFFICIENT_TEAM_STATE,
            exit_code=ExitCode.INSUFFICIENT_OR_STALE_TEAM_STATE,
        )

    if bootstrap is None:
        bootstrap, _fixtures = load_public_data(offline=offline)
    catalog = {int(e["id"]): e for e in bootstrap.get("elements") or [] if "id" in e}
    gw, deadline = next_deadline(bootstrap)
    hours = hours_until(deadline, now=now)

    private = load_and_validate_private_state(
        private_path,
        catalog_player_ids=set(catalog) or None,
    )
    team = resolve_team_state(
        settings=settings,
        season=SeasonId.S2026_27,
        gameweek=gw,
        now=now,
        private=private,
        catalog=catalog,
    )
    rules = load_season_rules_2026_27()
    plan_view = plan if plan is not None else load_plan_view(
        reports_dir=reports_dir,
        gameweek=gw,
        team=team,
        rules=rules,
        settings=settings,
        catalog=catalog,
    )

    snap = snapshot_from_bootstrap(
        bootstrap,
        event_id=gw,
        season=SeasonId.S2026_27.value,
        retrieved_at=now,
    )
    append_snapshot(snap, root=snapshot_root, max_per_gw=settings.prices.snapshot_max_per_gw)
    snapshots = load_snapshots(snapshot_root, SeasonId.S2026_27.value, gw)
    if not snapshots:
        snapshots = [snap]

    if len(snapshots) >= 2:
        prev, cur = snapshots[-2], snapshots[-1]
        changed_ids = [
            pid
            for pid, old in row_map(prev).items()
            if (new := row_map(cur).get(pid)) is not None and new.now_cost != old.now_cost
        ]
        scored_for_outcome = [
            score_player(
                snapshots=snapshots[:-1] or [prev],
                player_id=pid,
                web_name=str((catalog.get(pid) or {}).get("web_name") or pid),
                settings=settings.prices,
                now=now,
                public_max_age=timedelta(minutes=settings.freshness.public_fpl_max_age_minutes),
            )
            for pid in changed_ids
        ]
        recs = outcomes_from_snapshots(
            previous=prev,
            current=cur,
            predictions=scored_for_outcome,
            gameweek=gw,
            now=now,
        )
        append_outcomes(recs, outcomes_path)

    owned = set(private.player_ids)
    watchlist = set(private.watchlist_player_ids)
    target_ids = resolve_universe(
        universe,
        owned=owned,
        plan=plan_view,
        watchlist=watchlist,
        catalog=set(catalog),
    )
    if universe == "catalog":
        warnings.append("universe_catalog_diagnostic_no_notify")

    max_age = timedelta(minutes=settings.freshness.public_fpl_max_age_minutes)
    event_started = None
    events = list(bootstrap.get("events") or [])
    current = next((e for e in events if int(e.get("id") or 0) == gw), None)
    if current is not None:
        prev = next((e for e in events if int(e.get("id") or 0) == gw - 1), None)
        event_started = parse_deadline(prev.get("deadline_time") if prev else None)

    predictions: list[PricePrediction] = []
    for pid in sorted(target_ids):
        el = catalog.get(pid) or {}
        predictions.append(
            score_player(
                snapshots=snapshots,
                player_id=pid,
                web_name=str(el.get("web_name") or pid),
                settings=settings.prices,
                now=now,
                public_max_age=max_age,
                event_started_at=event_started,
                catalog_status=str(el["status"]) if el.get("status") is not None else None,
                catalog_chance=(
                    float(el["chance_of_playing_next_round"])
                    if el.get("chance_of_playing_next_round") is not None
                    else None
                ),
            )
        )

    actions = classify_all(
        predictions=predictions,
        team=team,
        rules=rules,
        plan=plan_view,
        watchlist=watchlist,
        settings=settings.prices,
        alerts=settings.alerts,
        hours_to_deadline=hours,
        now=now,
    )
    warnings.extend(team.warnings)
    status = report_status(actions)
    tz = ZoneInfo(settings.manager.timezone)
    local_now = now.astimezone(tz).strftime("%Y-%m-%d %H:%M %Z")
    markdown = render_prices_markdown(
        gameweek=gw,
        status=status,
        actions=actions,
        predictions=predictions,
        snapshot_times=[s.retrieved_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%MZ") for s in snapshots],
        model_version=settings.prices.model_version,
        timezone_label=local_now,
        warnings=warnings,
        executability=team.executability.value,
    )
    report_hash = stable_json_hash(markdown)

    notify_enabled = settings.publishing.issue_publishing if notify is None else notify
    dry = settings.publishing.dry_run or not notify_enabled
    notified: list[dict[str, Any]] = []
    if universe != "catalog":
        directions = {p.player_id: p.direction.value for p in predictions}
        state_path = gw_dir(snapshot_root, SeasonId.S2026_27.value, gw) / "notify-state.json"
        fresh, _fps = select_new_notifications(
            actions,
            season=SeasonId.S2026_27.value,
            gameweek=gw,
            directions=directions,
            state_path=state_path,
        )
        for action in fresh:
            payload = notify_payload(action, gameweek=gw, report_hash=report_hash)
            hook = maybe_post_webhook(
                url=settings.prices.webhook_url,
                dry_run=dry,
                payload=payload,
            )
            payload["webhook"] = hook
            notified.append(payload)
        notified.extend(
            issue_comment_ops(
                publishing=settings.publishing,
                actions=fresh,
                gameweek=gw,
                body=markdown,
            )
        )
        if dry and fresh:
            warnings.append("notify_dry_run")

    headline = status_headline(status)

    report = PricesReport(
        gameweek=gw,
        status=status,
        headline=headline,
        predictions=predictions,
        actions=actions,
        markdown=markdown,
        warnings=warnings,
        executability=team.executability.value,
        notified=notified,
        model_version=settings.prices.model_version,
        snapshot_hashes=[s.content_hash for s in snapshots],
        report_hash=report_hash,
    )
    if save:
        write_prices_artifact(report, reports_dir)
    return report


def write_prices_artifact(report: PricesReport, root: Path = Path("reports")) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = root / f"prices-gw{report.gameweek}-{stamp}.md"
    path.write_text(report.markdown, encoding="utf-8")
    payload = {
        "gameweek": report.gameweek,
        "status": report.status.value,
        "headline": report.headline,
        "executability": report.executability,
        "model_version": report.model_version,
        "warnings": report.warnings,
        "snapshot_hashes": report.snapshot_hashes,
        "report_hash": report.report_hash,
        "predictions": [p.model_dump(mode="json") for p in report.predictions],
        "actions": [a.model_dump(mode="json") for a in report.actions],
        "notified": report.notified,
    }
    path.with_suffix(".json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def prices_payload_for_llm(report: PricesReport) -> dict[str, Any]:
    return {
        "price_predictions": [
            {
                "player_id": p.player_id,
                "web_name": p.web_name,
                "direction": p.direction.value,
                "likelihood": p.likelihood.value,
                "progress_uncalibrated": p.progress_uncalibrated,
                "warnings": p.warnings,
            }
            for p in report.predictions
        ],
        "price_actions": [a.model_dump(mode="json") for a in report.actions],
        "price_status": report.status.value,
        "policy": {
            "do_not_invent_likelihood": True,
            "do_not_upgrade_ignore_or_watch": True,
            "do_not_transfer_just_because_ran": True,
        },
    }
