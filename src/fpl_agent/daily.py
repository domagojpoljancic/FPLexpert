"""Daily smart-assistant loop for a locked squad."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fpl_agent.cadence import hours_until, next_deadline, predeadline_gate
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
from fpl_agent.suggest import load_public_data
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
    skipped: bool = False
    skip_reason: str | None = None
    price_status: str | None = None
    price_actions: list[dict[str, Any]] | None = None
    squad_as_of: datetime | None = None
    squad_max_age_hours: float = 24.0
    timezone: str = "Europe/Zagreb"


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
    private_path: Path = Path("data/private-state/current.json"),
    snapshot_root: Path | None = None,
    reports_dir: Path = Path("reports"),
    save: bool = False,
):
    """Daily cadence: price watch + smart-to-act. No OpenAI."""
    from fpl_agent.prices.run import DEFAULT_ROOT, run_prices

    return run_prices(
        settings=settings,
        offline=offline,
        private_path=private_path,
        snapshot_root=snapshot_root or DEFAULT_ROOT,
        reports_dir=reports_dir,
        save=save,
        notify=False,
    )


def run_predeadline(
    *,
    settings: Settings | None = None,
    offline: bool = False,
    require_live_ai: bool = False,
    force: bool = False,
    private_path: Path = Path("data/private-state/current.json"),
    snapshot_root: Path | None = None,
    reports_dir: Path = Path("reports"),
) -> DailyReport:
    settings = settings or load_settings()

    bootstrap, fixtures = load_public_data(offline=offline)
    gw, deadline = next_deadline(bootstrap)
    hours = hours_until(deadline)
    allowed, gate = predeadline_gate(hours, settings.cadence, force=force)
    if not allowed:
        return DailyReport(
            gameweek=gw,
            plan_action="keep",
            headline="Pre-deadline full check skipped — more than a day before the deadline.",
            what_changed=[],
            attention_triggers=[],
            suggested_moves=[],
            uncertainty=[],
            warnings=[
                f"predeadline_gate={gate.value}; run `fpl-agent daily` for the price watch, "
                "or pass --force to run the full news/squad review now."
            ],
            sources=[],
            model_meta={"fallback": True, "gate": gate.value},
            executability="CONDITIONAL_ONLY",
            used_live_ai=False,
            skipped=True,
            skip_reason=gate.value,
        )

    if not private_path.exists():
        raise AgentError(
            f"private squad missing: {private_path}. Save your squad first.",
            code=AgentErrorCode.INSUFFICIENT_TEAM_STATE,
            exit_code=ExitCode.INSUFFICIENT_OR_STALE_TEAM_STATE,
        )

    catalog = {int(e["id"]): e for e in bootstrap.get("elements") or []}
    teams = {int(t["id"]): str(t["short_name"]) for t in bootstrap.get("teams") or []}
    private = load_and_validate_private_state(
        private_path,
        catalog_player_ids=set(catalog) or None,
    )
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

    price_report = None
    price_block: dict[str, Any] = {}
    try:
        from fpl_agent.prices.run import DEFAULT_ROOT, prices_payload_for_llm, run_prices

        price_report = run_prices(
            settings=settings,
            offline=offline,
            private_path=private_path,
            snapshot_root=snapshot_root or DEFAULT_ROOT,
            reports_dir=reports_dir,
            save=False,
            notify=False,
            bootstrap=bootstrap,
        )
        price_block = prices_payload_for_llm(price_report)
    except AgentError as exc:
        price_block = {"price_error": str(exc)}

    payload = {
        "mode": "predeadline",
        "manager_team_id": settings.manager.team_id,
        "gameweek": gw,
        "hours_to_deadline": hours,
        "predeadline_gate": gate.value,
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
            "do_not_invent_price_likelihood": True,
            "do_not_upgrade_ignore_or_watch_price_actions": True,
        },
        **price_block,
    }

    client = build_client(
        model=settings.models.deadline_model,
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

    extra_ids: set[int] = set()
    for action in price_block.get("price_actions") or []:
        if isinstance(action, dict):
            extra_ids.update(int(x) for x in (action.get("player_ids") or []) if x)
    advice = validate_daily_advice(
        advice if isinstance(advice, DailyAdvice) else DailyAdvice.model_validate(advice),
        allowed_player_ids=set(private.player_ids) | extra_ids,
        allowed_source_ids=allowed_sources or {c.claim_id for c in fpl_claims},
        price_actions=price_block.get("price_actions") if isinstance(price_block.get("price_actions"), list) else None,
    )

    if private.applies_before_gameweek != gw:
        advice.warnings.append(
            f"private state applies_before_gameweek={private.applies_before_gameweek} but next GW is {gw}"
        )
    if not used_live:
        advice.warnings.append("OPENAI_API_KEY not set — used deterministic fallback (no live news search)")
    if gate.value == "closer_than_intended":
        advice.warnings.append("inside the late pre-deadline window; prefer the deadline command if the deadline is imminent")
    if gate.value == "deadline_unknown":
        advice.warnings.append("official deadline_time missing; ran full check anyway")

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

    extra_warnings = _unique_texts(list(team.warnings))
    if price_report is not None:
        extra_warnings = _unique_texts(extra_warnings + list(price_report.warnings))

    return DailyReport(
        gameweek=gw,
        plan_action=advice.plan_action.value,
        headline=advice.headline,
        what_changed=advice.what_changed or what_changed,
        attention_triggers=advice.attention_triggers or triggers,
        suggested_moves=[m.model_dump(mode="json") for m in advice.suggested_moves],
        uncertainty=advice.uncertainty,
        warnings=advice.warnings + extra_warnings,
        sources=sources_out,
        model_meta={
            "response_id": meta.response_id,
            "model": meta.model,
            "latency_ms": meta.latency_ms,
            "usage": meta.usage,
            "web_search_calls": meta.web_search_calls,
            "fallback": meta.fallback,
            "prompt_version": meta.prompt_version,
            "gate": gate.value,
        },
        executability=team.executability.value,
        used_live_ai=used_live and not meta.fallback,
        skipped=False,
        skip_reason=None,
        price_status=price_report.status.value if price_report is not None else None,
        price_actions=price_block.get("price_actions") if isinstance(price_block.get("price_actions"), list) else None,
        squad_as_of=private.as_of,
        squad_max_age_hours=float(settings.freshness.private_squad_max_age_hours),
        timezone=settings.manager.timezone,
    )


def _unique_texts(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _format_squad_age(report: DailyReport, *, now: datetime | None = None) -> tuple[str, float] | None:
    if report.squad_as_of is None:
        return None
    now = now or datetime.now(UTC)
    as_of = report.squad_as_of
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=UTC)
    age_hours = (now - as_of.astimezone(UTC)).total_seconds() / 3600
    try:
        from zoneinfo import ZoneInfo

        local = as_of.astimezone(ZoneInfo(report.timezone)).strftime("%d %b %Y %H:%M %Z")
    except Exception:  # noqa: BLE001
        local = as_of.astimezone(UTC).strftime("%d %b %Y %H:%M UTC")
    return local, age_hours


def _can_act_lines(report: DailyReport) -> list[str]:
    lines = ["## Can you act on transfer advice?", ""]
    if report.executability == "EXECUTABLE":
        lines.append(
            "**Yes.** The squad file is fresh enough (15 players, bank, free transfers)."
        )
        return lines
    if report.executability == "CONDITIONAL_ONLY":
        lines.append(
            "**Only with caveats.** Some bank, free-transfer, or chip data is missing or old."
        )
        return lines
    lines.append(
        "**No — not as executable transfers.** "
        "We do not have a fresh enough picture of your team to say “do this transfer now.”"
    )
    aged = _format_squad_age(report)
    if aged:
        local, age_hours = aged
        lines.append(
            f"Your squad file was last saved **{local}** ({age_hours:.0f} hours ago). "
            f"We only trust it for **{report.squad_max_age_hours:.0f} hours**."
        )
    lines.append(
        "News and lineup notes below can still be useful. "
        "Update `data/private-state/current.json` from the FPL app, then run again. "
        "For the GitHub evening price job, also run "
        "`uv run fpl-agent team-state encode-for-github data/private-state/current.json`."
    )
    return lines


def _ai_line(report: DailyReport) -> str:
    if not report.used_live_ai:
        return "AI: not used (deterministic fallback; no API key or skipped)."
    model = str(report.model_meta.get("model") or "OpenAI")
    searches = report.model_meta.get("web_search_calls")
    extra = f" Web searches actually made: {searches}." if searches is not None else ""
    return f"AI: **{model}** (live OpenAI).{extra}"


def render_daily_text(report: DailyReport) -> str:
    if report.skipped:
        lines = [
            f"# Pre-deadline FPL review — Gameweek {report.gameweek}",
            "",
            f"**Skipped** ({report.skip_reason or 'outside the usual window'}).",
            "",
            report.headline,
            "",
        ]
        lines.extend(f"- {w}" for w in _unique_texts(report.warnings))
        lines += [
            "",
            "Use `fpl-agent daily` for the price watch, or `--force` to run this review anyway.",
            "",
            "_Recommend only — you make all FPL changes._",
        ]
        return "\n".join(lines)

    hide = {"private squad stale"}
    warnings = [w for w in _unique_texts(report.warnings) if w not in hide]
    lines = [
        f"# Pre-deadline FPL review — Gameweek {report.gameweek}",
        "",
        f"Plan: **{report.plan_action.upper()}**",
        _ai_line(report),
    ]
    if report.price_status:
        lines.append(f"Price watch: **{report.price_status}** (overnight rises/falls — not news).")
    lines += ["", *_can_act_lines(report), "", f"## {report.headline}", "", "## What changed"]
    if report.what_changed:
        lines.extend(f"- {x}" for x in report.what_changed)
    else:
        lines.append("- Nothing material from FPL status fields.")
    lines += ["", "## Attention"]
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
    if warnings:
        lines += ["", "## Other warnings"]
        lines.extend(f"- {x}" for x in warnings)
    if report.sources:
        lines += ["", "## Sources"]
        for src in report.sources[:12]:
            lines.append(f"- `{src['claim_id']}` ({src['tier']}) {src['url']}")
    lines += ["", "_Recommend only — you make all FPL changes._"]
    return "\n".join(lines)


def write_daily_artifact(report: DailyReport, root: Path = Path("reports")) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = root / f"predeadline-gw{report.gameweek}-{stamp}.md"
    path.write_text(render_daily_text(report), encoding="utf-8")
    json_path = path.with_suffix(".json")
    json_path.write_text(json.dumps(asdict(report), indent=2, default=str), encoding="utf-8")
    return path
