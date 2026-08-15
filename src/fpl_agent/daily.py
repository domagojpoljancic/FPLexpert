"""Daily smart-assistant loop for a locked squad."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fpl_agent.config import Settings, load_settings
from fpl_agent.domain.models import SeasonId
from fpl_agent.errors import AgentError, AgentErrorCode, ExitCode
from fpl_agent.evidence.news import (
    build_squad_search_request,
    claims_from_bootstrap_news,
    claims_from_search_sources,
)
from fpl_agent.llm.client import (
    DailyAdvice,
    build_client,
    validate_daily_advice,
)
from fpl_agent.projections.preseason import project_all
from fpl_agent.suggest import load_public_data, next_gameweek
from fpl_agent.team_state.private import load_and_validate_private_state
from fpl_agent.team_state.resolve import resolve_team_state


@dataclass
class DailyReport:
    gameweek: int
    plan_action: str
    headline: str
    what_changed: list[str]
    attention_triggers: list[str]
    suggested_moves: list[dict[str, Any]]
    uncertainty: list[str]
    warnings: list[str]
    sources: list[dict[str, Any]]
    model_meta: dict[str, Any]
    executability: str
    used_live_ai: bool


def _squad_rows(
    *,
    private_players: list[int],
    catalog: dict[int, dict[str, Any]],
    teams: dict[int, str],
    projections: dict[int, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pid in private_players:
        el = catalog.get(pid, {})
        proj = projections.get(pid)
        rows.append(
            {
                "player_id": pid,
                "web_name": el.get("web_name"),
                "team": teams.get(int(el.get("team") or 0), "?"),
                "position": el.get("element_type"),
                "price": (el.get("now_cost") or 0) / 10,
                "status": el.get("status"),
                "chance_of_playing_next_round": el.get("chance_of_playing_next_round"),
                "news": (el.get("news") or "")[:240] or None,
                "gw1_xp": proj.xp_by_gw[0] if proj and proj.xp_by_gw else None,
                "weighted_6gw": proj.weighted_xp if proj else None,
                "p_start": proj.p_start if proj else None,
            }
        )
    return rows


def _deterministic_triggers(rows: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    changed: list[str] = []
    triggers: list[str] = []
    for row in rows:
        name = row.get("web_name") or row["player_id"]
        status = row.get("status") or "a"
        chance = row.get("chance_of_playing_next_round")
        news = row.get("news")
        if status in {"i", "d", "s", "u", "n"}:
            triggers.append(f"{name}: FPL status={status}")
        if chance is not None and float(chance) < 100:
            triggers.append(f"{name}: {chance}% chance of playing")
        if news:
            changed.append(f"{name}: {news}")
        if row.get("p_start") is not None and float(row["p_start"]) < 0.35:
            triggers.append(f"{name}: low projected start probability ({row['p_start']:.0%})")
    # de-dupe preserve order
    def uniq(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            if item not in seen:
                seen.add(item)
                out.append(item)
        return out

    return uniq(changed), uniq(triggers)


def run_daily(
    *,
    settings: Settings | None = None,
    offline: bool = False,
    require_live_ai: bool = False,
    private_path: Path = Path("data/private-state/current.json"),
) -> DailyReport:
    settings = settings or load_settings()
    if not private_path.exists():
        raise AgentError(
            f"private squad missing: {private_path}. Save your squad first.",
            code=AgentErrorCode.INSUFFICIENT_TEAM_STATE,
            exit_code=ExitCode.INSUFFICIENT_OR_STALE_TEAM_STATE,
        )

    bootstrap, fixtures = load_public_data(offline=offline)
    catalog = {int(e["id"]): e for e in bootstrap.get("elements") or []}
    teams = {int(t["id"]): str(t["short_name"]) for t in bootstrap.get("teams") or []}
    private = load_and_validate_private_state(
        private_path,
        catalog_player_ids=set(catalog) or None,
    )
    gw = next_gameweek(bootstrap)
    if private.applies_before_gameweek != gw:
        # still allow; warn in report
        pass

    team = resolve_team_state(
        settings=settings,
        season=SeasonId.S2026_27,
        gameweek=gw,
        private=private,
        catalog=catalog,
    )

    weights = settings.planning.weights
    gameweeks = list(range(gw, gw + len(weights)))
    all_proj = project_all(
        bootstrap=bootstrap,
        fixtures=fixtures,
        gameweeks=gameweeks,
        weights=weights,
    )
    proj_by_id = {p.player_id: p for p in all_proj}

    rows = _squad_rows(
        private_players=private.player_ids,
        catalog=catalog,
        teams=teams,
        projections=proj_by_id,
    )
    what_changed, triggers = _deterministic_triggers(rows)

    fpl_claims = claims_from_bootstrap_news(
        elements=list(bootstrap.get("elements") or []),
        player_ids=set(private.player_ids),
    )
    search_req = build_squad_search_request(
        player_ids=private.player_ids,
        club_ids=sorted({int(catalog[p]["team"]) for p in private.player_ids if p in catalog}),
        player_names=[str(r.get("web_name") or r["player_id"]) for r in rows],
        budget=settings.models.web_search_budget,
    )

    payload = {
        "mode": "daily",
        "manager_team_id": settings.manager.team_id,
        "gameweek": gw,
        "executability": team.executability.value,
        "bank_tenths": private.bank_tenths,
        "free_transfers": private.free_transfers,
        "captain_id": private.captain_id,
        "vice_id": private.vice_id,
        "starters": private.starters,
        "bench_order": private.bench_order,
        "squad": rows,
        "what_changed": what_changed,
        "attention_triggers": triggers,
        "search_request": search_req.model_dump(mode="json"),
        "sources": [c.model_dump(mode="json") for c in fpl_claims],
        "policy": {
            "do_not_transfer_just_because_ran": True,
            "recommend_only": True,
            "reddit_is_community_tier": True,
        },
    }

    client = build_client(
        model=settings.models.daily_model,
        max_output_tokens=settings.models.max_output_tokens,
        web_search_budget=settings.models.web_search_budget,
        require_live=require_live_ai,
    )
    used_live = type(client).__name__ == "ResponsesOpenAIClient"
    advice, meta = client.synthesize_daily(payload)

    web_claims = claims_from_search_sources(
        meta.sources,
        player_ids=private.player_ids,
    )
    all_claims = fpl_claims + web_claims
    allowed_sources = {c.claim_id for c in all_claims}
    payload_sources = payload.get("sources")
    if isinstance(payload_sources, list):
        for src in payload_sources:
            if isinstance(src, dict) and "claim_id" in src:
                allowed_sources.add(str(src["claim_id"]))

    advice = validate_daily_advice(
        advice if isinstance(advice, DailyAdvice) else DailyAdvice.model_validate(advice),
        allowed_player_ids=set(private.player_ids),
        allowed_source_ids=allowed_sources or {c.claim_id for c in fpl_claims},
    )

    if private.applies_before_gameweek != gw:
        advice.warnings.append(
            f"private state applies_before_gameweek={private.applies_before_gameweek} but next GW is {gw}"
        )
    if not used_live:
        advice.warnings.append("OPENAI_API_KEY not set — used deterministic fallback (no live news search)")

    sources_out = [
        {
            "claim_id": c.claim_id,
            "tier": c.source_tier,
            "category": c.category.value,
            "url": c.source_url,
            "text": c.text[:200],
            "player_ids": c.player_ids,
        }
        for c in all_claims
    ]

    return DailyReport(
        gameweek=gw,
        plan_action=advice.plan_action.value,
        headline=advice.headline,
        what_changed=advice.what_changed or what_changed,
        attention_triggers=advice.attention_triggers or triggers,
        suggested_moves=[m.model_dump(mode="json") for m in advice.suggested_moves],
        uncertainty=advice.uncertainty,
        warnings=advice.warnings + team.warnings,
        sources=sources_out,
        model_meta={
            "response_id": meta.response_id,
            "model": meta.model,
            "latency_ms": meta.latency_ms,
            "usage": meta.usage,
            "web_search_calls": meta.web_search_calls,
            "fallback": meta.fallback,
            "prompt_version": meta.prompt_version,
        },
        executability=team.executability.value,
        used_live_ai=used_live and not meta.fallback,
    )


def render_daily_text(report: DailyReport) -> str:
    lines = [
        f"# Daily FPL assistant — GW{report.gameweek}",
        f"Status: **{report.plan_action.upper()}** | Executability: {report.executability}",
        f"AI: {'live OpenAI + web search' if report.used_live_ai else 'deterministic fallback (no API key)'}",
        "",
        f"## {report.headline}",
        "",
        "## What changed",
    ]
    if report.what_changed:
        lines.extend(f"- {x}" for x in report.what_changed)
    else:
        lines.append("- Nothing material from FPL status fields.")
    lines += ["", "## Attention triggers"]
    if report.attention_triggers:
        lines.extend(f"- {x}" for x in report.attention_triggers)
    else:
        lines.append("- None.")
    lines += ["", "## Suggested moves"]
    if report.suggested_moves:
        for move in report.suggested_moves:
            lines.append(
                f"- [{move.get('urgency', 'low')}] {move.get('move_type')}: {move.get('summary')}"
            )
    else:
        lines.append("- Hold.")
    if report.uncertainty:
        lines += ["", "## Uncertainty"]
        lines.extend(f"- {x}" for x in report.uncertainty)
    if report.warnings:
        lines += ["", "## Warnings"]
        lines.extend(f"- {x}" for x in report.warnings)
    if report.sources:
        lines += ["", "## Sources"]
        for src in report.sources[:12]:
            lines.append(f"- `{src['claim_id']}` ({src['tier']}) {src['url']}")
    lines += ["", "_Recommend only — you make all FPL changes._"]
    return "\n".join(lines)


def write_daily_artifact(report: DailyReport, root: Path = Path("reports")) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = root / f"daily-gw{report.gameweek}-{stamp}.md"
    path.write_text(render_daily_text(report), encoding="utf-8")
    json_path = path.with_suffix(".json")
    json_path.write_text(json.dumps(asdict(report), indent=2, default=str), encoding="utf-8")
    return path
