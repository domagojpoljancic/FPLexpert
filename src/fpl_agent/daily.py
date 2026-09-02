"""Daily smart-assistant loop for a locked squad."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fpl_agent.cadence import hours_until, next_deadline, predeadline_gate
from fpl_agent.config import Settings, load_settings
from fpl_agent.domain.models import SeasonId
from fpl_agent.errors import AgentError, AgentErrorCode, ExitCode
from fpl_agent.evidence.news import (
    SUGGESTED_SOURCE_HUBS,
    build_squad_search_request,
    claims_from_bootstrap_news,
    claims_from_search_sources,
)
from fpl_agent.llm.client import (
    DailyAdvice,
    apply_news_fail_closed,
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
    tldr: list[str] = field(default_factory=list)
    detail: str = ""
    search_queries: list[str] = field(default_factory=list)
    suggested_hubs: list[dict[str, str]] = field(default_factory=list)
    weekly_plan: dict[str, Any] = field(default_factory=dict)


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

    from fpl_agent.strategy.chips import recommend_chips
    from fpl_agent.strategy.plan import build_weekly_plan
    from fpl_agent.strategy.transfers import (
        rank_transfer_candidates,
        rank_transfer_plans,
        this_week_upgrade,
    )

    weekly_plan = build_weekly_plan(
        owned_ids=private.player_ids,
        projections=proj_by_id,
        gameweeks=gameweeks,
        captain_id=private.captain_id,
        vice_id=private.vice_id,
    )

    affordable_transfers, stretch_transfers = rank_transfer_candidates(
        owned_ids=private.player_ids,
        bank_tenths=private.bank_tenths,
        purchase_prices_tenths=private.purchase_prices_tenths,
        catalog=catalog,
        projections=proj_by_id,
    )
    transfer_plans = rank_transfer_plans(
        owned_ids=private.player_ids,
        bank_tenths=private.bank_tenths,
        free_transfers=int(private.free_transfers),
        purchase_prices_tenths=private.purchase_prices_tenths,
        catalog=catalog,
        projections=proj_by_id,
        hits_enabled=True,
    )
    chip_advice = recommend_chips(
        gameweek=gw,
        weekly_plan=weekly_plan,
        chip_instances=private.chip_instances,
    )
    this_week = this_week_upgrade(affordable_transfers)
    weekly_plan["best_affordable"] = this_week.as_payload() if this_week else None
    weekly_plan["best_stretch"] = stretch_transfers[0].as_payload() if stretch_transfers else None
    weekly_plan["after_transfer"] = None
    if this_week is not None:
        after_ids = [
            this_week.in_id if pid == this_week.out_id else pid for pid in private.player_ids
        ]
        after_plan = build_weekly_plan(
            owned_ids=after_ids,
            projections=proj_by_id,
            gameweeks=gameweeks,
            captain_id=(
                private.captain_id
                if private.captain_id != this_week.out_id
                else this_week.in_id
            ),
            vice_id=private.vice_id if private.vice_id != this_week.out_id else None,
        )
        if after_plan.get("ok"):
            weekly_plan["after_transfer"] = {
                "out_id": this_week.out_id,
                "in_id": this_week.in_id,
                "out_name": this_week.out_name,
                "in_name": this_week.in_name,
                "xi_drop_name": this_week.xi_drop_name,
                "formation": after_plan.get("formation"),
                "xi": after_plan.get("xi"),
                "bench": after_plan.get("bench"),
                "model_captain": after_plan.get("model_captain"),
                "model_vice": after_plan.get("model_vice"),
            }
    weekly_plan["best_plan"] = transfer_plans[0].as_payload() if transfer_plans else None
    hit_plans = [p for p in transfer_plans if p.hit_cost > 0]
    weekly_plan["best_hit"] = hit_plans[0].as_payload() if hit_plans else None
    weekly_plan["chips"] = [c.as_payload() for c in chip_advice]
    try:
        from fpl_agent.evaluation.scorecard import build_previous_scorecard

        prev = build_previous_scorecard(
            previous_gameweek=gw - 1,
            reports_dir=reports_dir,
        )
        weekly_plan["previous_scorecard"] = prev.as_payload() if prev else None
    except Exception:  # noqa: BLE001
        weekly_plan["previous_scorecard"] = None
    transfer_note = (
        "No legal improving 1-FT upgrade fits the current bank; stretch targets need more funds."
        if not affordable_transfers and stretch_transfers
        else (
            "No this-week FT: affordable upgrades do not start in the modelled XI."
            if affordable_transfers and this_week is None
            else (
                "Legal improving 1-FT upgrades that start this GW are listed in transfer_candidates."
                if this_week
                else "No improving same-position 1-FT upgrades found in the projection set."
            )
        )
    )

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
        "suggested_source_hubs": [dict(h) for h in SUGGESTED_SOURCE_HUBS],
        "weekly_plan": _llm_weekly_plan(weekly_plan),
        "transfer_candidates": [
            c.as_payload() for c in affordable_transfers if c.in_starts
        ][:8],
        "stretch_transfer_candidates": [c.as_payload() for c in stretch_transfers[:4]],
        "transfer_plans": [p.as_payload() for p in transfer_plans[:4]],
        "chip_advice": [c.as_payload() for c in chip_advice],
        "transfer_market_note": transfer_note,
        "policy": {
            "do_not_transfer_just_because_ran": True,
            "recommend_only": True,
            "reddit_is_community_tier": True,
            "do_not_invent_price_likelihood": True,
            "do_not_upgrade_ignore_or_watch_price_actions": True,
            "only_recommend_transfers_from_supplied_candidates": True,
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
    for cand in affordable_transfers + stretch_transfers:
        extra_ids.add(cand.out_id)
        extra_ids.add(cand.in_id)
    for plan in transfer_plans:
        for move in plan.moves:
            extra_ids.add(move.out_id)
            extra_ids.add(move.in_id)
    advice = validate_daily_advice(
        advice if isinstance(advice, DailyAdvice) else DailyAdvice.model_validate(advice),
        allowed_player_ids=set(private.player_ids) | extra_ids,
        allowed_source_ids=allowed_sources or {c.claim_id for c in fpl_claims},
        price_actions=price_block.get("price_actions") if isinstance(price_block.get("price_actions"), list) else None,
        owned_player_ids=set(private.player_ids),
    )
    advice = apply_news_fail_closed(
        advice,
        used_live=used_live and not meta.fallback,
        web_search_calls=int(meta.web_search_calls),
        page_count=len(meta.sources),
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
            "title": c.text[:200],
            "text": c.text[:200],
            "player_ids": c.player_ids,
        }
        for c in all_claims
    ]

    extra_warnings = _unique_texts(list(team.warnings))
    if price_report is not None:
        extra_warnings = _unique_texts(extra_warnings + list(price_report.warnings))

    tldr = [item.strip() for item in advice.tldr if item.strip()]
    if not tldr and advice.headline:
        tldr = [advice.headline]

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
        tldr=tldr,
        detail=advice.detail.strip(),
        search_queries=list(meta.search_queries),
        suggested_hubs=[dict(h) for h in SUGGESTED_SOURCE_HUBS],
        weekly_plan=weekly_plan,
    )


def _llm_weekly_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Smaller weekly_plan for the model so after_transfer is not truncated."""
    keys = (
        "ok",
        "formation",
        "xi",
        "bench",
        "model_captain",
        "model_vice",
        "best_affordable",
        "best_stretch",
        "chips",
        "after_transfer",
    )
    out = {key: plan[key] for key in keys if key in plan}
    out["horizon"] = list(plan.get("horizon") or [])[:3]
    return out


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


def _act_tldr_bullet(report: DailyReport) -> str:
    if report.executability == "EXECUTABLE":
        return "Transfers: **you can act** (squad file is fresh)."
    if report.executability == "CONDITIONAL_ONLY":
        return "Transfers: **caveats** — bank, FT, or chips may be incomplete."
    return "Transfers: **not executable** — squad file missing or stale; news notes still useful."


def _can_act_lines(report: DailyReport) -> list[str]:
    if report.executability == "EXECUTABLE":
        return []
    lines = ["### Squad file", ""]
    if report.executability == "CONDITIONAL_ONLY":
        lines.append(
            "Some bank, free-transfer, or chip data is missing or old. Treat transfer ideas as conditional."
        )
        return lines
    lines.append(
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


def _source_label(src: dict[str, Any]) -> str:
    title = str(src.get("title") or src.get("text") or "").strip()
    url = str(src.get("url") or "")
    if title.startswith("Web source consulted"):
        title = ""
    if title and url:
        return f"[{title}]({url})"
    if url:
        return url
    return title or "(no url)"


def _sources_section(report: DailyReport) -> list[str]:
    searches = report.model_meta.get("web_search_calls")
    web_pages = [s for s in report.sources if not str(s.get("claim_id") or "").startswith("fpl-")]
    lines = ["## Sources", ""]
    if report.used_live_ai:
        lines.append(f"{searches if searches is not None else 0} web searches.")
    else:
        lines.append("No live OpenAI search.")
    if web_pages:
        for src in web_pages[:5]:
            lines.append(f"- {_source_label(src)}")
        extra = len(web_pages) - 5
        if extra > 0:
            lines.append(f"- _{extra} more pages omitted._")
    elif report.used_live_ai:
        lines.append("- No pages returned.")
    return lines


def _player_names(rows: list[Any], *, with_start: bool = False) -> str:
    names: list[str] = []
    for player in rows:
        name = str(player.get("web_name") or player.get("player_id") or "?")
        if with_start:
            names.append(f"{name} ({float(player.get('p_start') or 0):.0%})")
        else:
            names.append(name)
    return ", ".join(names)


def _weekly_plan_section(report: DailyReport) -> list[str]:
    plan = report.weekly_plan or {}
    if not plan.get("ok"):
        return []
    after = plan.get("after_transfer") or {}
    using = after if after.get("xi") else plan
    cap = using.get("model_captain") or plan.get("model_captain") or {}
    vice = using.get("model_vice") or plan.get("model_vice") or {}
    xi = using.get("xi") or []
    bench = using.get("bench") or []
    lines = ["## This week", ""]
    best = plan.get("best_affordable")
    if after.get("xi") and best:
        drop = after.get("xi_drop_name") or best.get("xi_drop_name")
        drop_bit = f"; {drop} drops out of the XI" if drop and drop != best.get("out_name") else ""
        lines.append(
            f"After **{best.get('out_name')} → {best.get('in_name')}** "
            f"({best.get('in_name')} starts{drop_bit}):"
        )
        lines.append("")
    elif best is None and plan.get("best_stretch"):
        stretch = plan["best_stretch"]
        lines.append(
            f"Hold the FT. Best stretch (does not fit the bank): "
            f"**{stretch.get('out_name')} → {stretch.get('in_name')}** "
            f"(needs £{float(stretch.get('bank_shortfall_tenths') or 0) / 10:.1f}m)."
        )
        lines.append("")
    if xi:
        lines.append(f"- XI ({using.get('formation') or plan.get('formation')}): {_player_names(xi)}")
    if bench:
        lines.append(f"- Bench: {_player_names(bench, with_start=True)}")
    if cap:
        lines.append(
            f"- Captain: **{cap.get('web_name')}** ({cap.get('xp_next')} xP) · "
            f"Vice: **{(vice or {}).get('web_name') or '—'}**"
        )
    chips = plan.get("chips") or []
    play = [c for c in chips if c.get("action") == "play" and c.get("available")]
    if play:
        lines.append("- Chips: " + ", ".join(f"**{c.get('kind')}**" for c in play))
    elif chips:
        lines.append("- Chips: hold")
    horizon = list(plan.get("horizon") or [])[:3]
    if horizon:
        bits = " · ".join(f"GW{row.get('gw')} {row.get('xi_xp')}" for row in horizon)
        lines.append(f"- Next GWs (XI xP): {bits}")
    return lines


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

    hide = {"private squad stale", "notify_dry_run", "news_search_empty"}
    warnings = [w for w in _unique_texts(report.warnings) if w not in hide]
    tldr = [item for item in report.tldr if item][:5] or ([report.headline] if report.headline else [])
    lines = [
        f"# Pre-deadline FPL review — Gameweek {report.gameweek}",
        "",
        f"Plan: **{report.plan_action.upper()}** — {report.headline}",
        _ai_line(report),
    ]
    if report.price_status and report.price_status not in {"NO ACTION", "no action"}:
        lines.append(f"Price: **{report.price_status}**")
    lines += ["", "## Do this", ""]
    if report.suggested_moves:
        for move in report.suggested_moves:
            lines.append(f"- {move.get('move_type')}: {move.get('summary')}")
            why = str(move.get("why") or "").strip()
            if why:
                lines.append(f"  - {why}")
    else:
        if tldr:
            lines.extend(f"- {item}" for item in tldr)
        else:
            lines.append("- Hold.")
    if any(w == "news_search_empty" for w in report.warnings):
        lines.append("- News search returned no pages — treat injury claims as unverified.")
    lines.append(f"- {_act_tldr_bullet(report)}")
    plan_lines = _weekly_plan_section(report)
    if plan_lines:
        lines += ["", *plan_lines]
    detail = report.detail.strip() or report.headline
    lines += ["", "## Why", "", detail]
    watch = _unique_texts(
        list(report.attention_triggers[:4])
        + [u for u in report.uncertainty if "weekly_plan" not in u.lower() and "weekly-plan" not in u.lower()][:2]
        + warnings[:3]
    )
    notes = _can_act_lines(report)
    if watch or notes:
        lines += ["", "## Watch", ""]
        if notes:
            lines.extend(x for x in notes if not x.startswith("#") and x)
            lines.append("")
        lines.extend(f"- {x}" for x in watch[:6])
    lines += ["", *_sources_section(report), "", "_Recommend only — you make all FPL changes._"]
    return "\n".join(lines)


def write_daily_artifact(report: DailyReport, root: Path = Path("reports")) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = root / f"predeadline-gw{report.gameweek}-{stamp}.md"
    path.write_text(render_daily_text(report), encoding="utf-8")
    json_path = path.with_suffix(".json")
    json_path.write_text(json.dumps(asdict(report), indent=2, default=str), encoding="utf-8")
    return path
