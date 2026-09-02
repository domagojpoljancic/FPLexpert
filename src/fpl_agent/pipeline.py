"""Offline-capable analysis pipeline wiring deterministic layers."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from fpl_agent import __version__
from fpl_agent.config import load_settings
from fpl_agent.domain.models import SeasonId
from fpl_agent.domain.run_state import new_run_id, stable_json_hash, utc_now
from fpl_agent.evaluation.ledger import DecisionRecord, build_decision_id
from fpl_agent.llm.client import FakeOpenAIClient, validate_synthesis
from fpl_agent.projections.model import project_horizon
from fpl_agent.publishing.state import advance, prepare_bundle
from fpl_agent.reporting.render import render_deadline_report
from fpl_agent.rules.season import load_season_rules
from fpl_agent.strategy.engine import generate_scenarios
from fpl_agent.team_state.private import load_and_validate_private_state
from fpl_agent.team_state.resolve import resolve_team_state


def _to_dict(obj: Any) -> dict[str, Any]:
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    if hasattr(obj, "model_dump"):
        dumped = obj.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {"value": dumped}
    if isinstance(obj, dict):
        return obj
    return {"value": obj}


def run_pipeline(
    *,
    mode: str = "dry_run",
    offline: bool = True,
    settings_path: Path | None = None,
) -> dict[str, Any]:
    settings = load_settings(settings_path)
    from fpl_agent.projections.preseason import configure_from_settings

    configure_from_settings(settings)
    rules = load_season_rules(SeasonId.S2026_27)
    run_id = new_run_id()
    now = utc_now()

    private = None
    private_path = Path("data/private-state/current.json")
    catalog: dict[int, dict[str, Any]] = {}
    gw = 1
    for candidate in (
        Path("data/cache/bootstrap-static.json"),
        Path("tests/fixtures/bootstrap_static_reduced.json"),
    ):
        if not candidate.exists():
            continue
        boot = json.loads(candidate.read_text(encoding="utf-8"))
        catalog = {int(e["id"]): e for e in boot.get("elements") or []}
        events = boot.get("events") or []
        gw = next((int(e["id"]) for e in events if e.get("is_next")), 1)
        break

    if private_path.exists():
        private = load_and_validate_private_state(
            private_path,
            catalog_player_ids=set(catalog) or None,
        )

    team = resolve_team_state(
        settings=settings,
        season=SeasonId.S2026_27,
        gameweek=int(gw),
        now=now,
        private=private,
        catalog=catalog,
    )

    weights = settings.planning.weights
    gameweeks = list(range(int(gw), int(gw) + len(weights)))
    xp_by_player: dict[int, list[float]] = {}
    squad_dicts: list[dict[str, Any]] = []
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
        hz = project_horizon(
            player_id=p.player_id,
            gameweeks=gameweeks,
            weights=weights,
            per_gw_kwargs=[
                {
                    "recent_minutes": [70, 75, 80],
                    "recent_points": [2, 5, 3],
                    "position_prior_minutes": 70.0,
                    "team_attack": 0.1,
                    "team_defence": 0.0,
                    "opp_attack": 0.0,
                    "opp_defence": 0.0,
                    "is_home": True,
                    "fixtures_in_gw": 1,
                }
                for _ in gameweeks
            ],
        )
        xp_by_player[p.player_id] = hz.unweighted_by_gw

    scenarios, diag = generate_scenarios(
        rules=rules,
        executability=team.executability,
        bank_tenths=team.bank_tenths.value,
        free_transfers=team.free_transfers.value,
        squad=squad_dicts,
        xp_by_player=xp_by_player,
        weights=weights,
        max_hit=settings.planning.max_hit,
        hits_enabled=settings.planning.hits_enabled,
        risk_profile=settings.manager.risk_profile,
    )

    allowed = {s.scenario_id for s in scenarios}
    executable_ids = {
        s.scenario_id
        for s in scenarios
        if s.executability.value == "EXECUTABLE" and s.legality_ok
    }
    client = FakeOpenAIClient()
    synthesis = client.synthesize_deadline(
        {
            "candidates": [
                {
                    "scenario_id": s.scenario_id,
                    "executability": s.executability.value,
                    "weighted_net": s.weighted_net,
                }
                for s in scenarios
            ],
            "sources": [],
        }
    )
    synthesis = validate_synthesis(
        synthesis,
        allowed_scenario_ids=allowed,
        allowed_source_ids=set(),
        executable_ids=executable_ids,
    )

    primary = next((s for s in scenarios if s.scenario_id == synthesis.chosen_scenario_id), None)
    roll = next((s for s in scenarios if not s.transfers and s.hit_cost == 0), scenarios[0] if scenarios else None)

    report_warnings = team.warnings + list(synthesis.warnings)
    report_payload = {
        "gameweek": gw,
        "executability": team.executability.value,
        "freshness": team.as_of.isoformat(),
        "run_id": run_id,
        "warnings": report_warnings,
        "primary": {
            "summary": (
                "roll"
                if primary and not primary.transfers
                else (primary.notes[0] if primary and primary.notes else "none")
            ),
            "hit_cost": primary.hit_cost if primary else 0,
            "bank_after": primary.bank_after if primary else None,
            "captain_id": primary.captain_id if primary else None,
            "vice_id": primary.vice_id if primary else None,
            "chip": primary.chip if primary else None,
        },
        "horizon_table": (
            [
                {"gw": gameweeks[i], "xp": base.projected_by_gw[i]}
                for i in range(len(weights))
            ]
            if (base := (primary or roll)) is not None
            else []
        ),
    }
    markdown = render_deadline_report(report_payload)

    decision_payload = {
        "season": SeasonId.S2026_27.value,
        "gameweek": gw,
        "team": team.model_dump(mode="json"),
        "scenarios": [_to_dict(s) for s in scenarios],
        "synthesis": synthesis.model_dump(),
    }
    decision_id = build_decision_id(decision_payload)
    record = DecisionRecord(
        decision_id=decision_id,
        season=SeasonId.S2026_27.value,
        gameweek=int(gw),
        generated_at=now.isoformat(),
        data_cutoff=now.isoformat(),
        team_state=team.model_dump(mode="json"),
        executability=team.executability.value,
        rules_hash=stable_json_hash(rules.model_dump(mode="json")),
        catalog_hash=stable_json_hash(sorted(catalog)),
        projection_hash=stable_json_hash(xp_by_player),
        config_hash=stable_json_hash(settings.model_dump(mode="json")),
        code_version=__version__,
        roll=_to_dict(roll) if roll else {},
        primary=_to_dict(primary) if primary else None,
        alternatives=[_to_dict(s) for s in scenarios[:5]],
        warnings=report_warnings,
        report_hash=stable_json_hash(markdown),
    )

    bundle = prepare_bundle(
        manifest={"run_id": run_id, "mode": mode, "offline": offline},
        decision_record=record.model_dump(mode="json"),
        markdown=markdown,
    )
    dry = settings.publishing.dry_run or mode in {"dry_run", "manual"}
    if not dry:
        bundle = advance(bundle, bundle.state.__class__.REPOSITORY_PUBLISHED, dry_run=False)
    else:
        bundle = advance(bundle, bundle.state.__class__.RECONCILED, dry_run=True)

    return {
        "run_id": run_id,
        "mode": mode,
        "offline": offline,
        "executability": team.executability.value,
        "scenario_count": len(scenarios),
        "diagnostics": _to_dict(diag),
        "chosen_scenario_id": synthesis.chosen_scenario_id,
        "bundle_id": bundle.bundle_id,
        "publish_state": bundle.state.value,
        "markdown_preview": markdown[:500],
        "code_version": __version__,
    }
