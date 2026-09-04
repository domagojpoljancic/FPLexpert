"""Daily smart-assistant loop for a locked squad."""

from __future__ import annotations

import json
import re
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
    DailyMove,
    MoveType,
    apply_news_fail_closed,
    build_client,
    validate_daily_advice,
)
from fpl_agent.projections.preseason import PlayerProjection, project_all
from fpl_agent.rules.season import SeasonRules
from fpl_agent.suggest import load_public_data
from fpl_agent.strategy.transfers import POSITION_LABEL, TransferCandidate, explain_xi_choice
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
        gw_xp = row.get("gw1_xp")
        if gw_xp is not None and float(gw_xp) < 1.0 and row.get("position") not in {1}:
            # Low projected points matters more than start% for outfield squad holes.
            triggers.append(f"{name}: only {float(gw_xp):.1f} projected points this week")
        elif row.get("p_start") is not None and float(row["p_start"]) < 0.35:
            triggers.append(f"{name}: unlikely to start ({row['p_start']:.0%} projected)")
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
    from fpl_agent.projections.preseason import configure_from_settings

    configure_from_settings(settings)

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
    from fpl_agent.evidence.overrides import apply_official_overrides

    override_result = apply_official_overrides(
        claims=fpl_claims,
        projections=proj_by_id,
        allowed_player_ids=set(private.player_ids),
    )
    proj_by_id = override_result.projections
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

    from fpl_agent.rules.season import load_season_rules_2026_27
    from fpl_agent.strategy.chips import recommend_chips
    from fpl_agent.strategy.plan import build_weekly_plan
    from fpl_agent.strategy.transfers import (
        compare_roll_vs_transfer,
        deferred_double_transfer_upside,
        hit_horizon_margin,
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
        risk_profile=settings.manager.risk_profile,
        gameweek=gw,
        early_season_gws=settings.planning.early_season_gws,
        early_season_hit_margin_boost=settings.planning.early_season_hit_margin_boost,
    )
    chip_advice = recommend_chips(
        gameweek=gw,
        weekly_plan=weekly_plan,
        chip_instances=private.chip_instances,
    )
    this_week = this_week_upgrade(affordable_transfers)
    weekly_plan["best_stretch"] = stretch_transfers[0].as_payload() if stretch_transfers else None
    season_rules = load_season_rules_2026_27()
    apply_transfer_pick_to_weekly_plan(
        weekly_plan,
        this_week,
        owned_ids=private.player_ids,
        captain_id=private.captain_id,
        vice_id=private.vice_id,
        projections=proj_by_id,
        gameweeks=gameweeks,
        weights=weights,
        season_rules=season_rules,
        affordable_transfers=affordable_transfers,
    )
    weekly_plan["best_plan"] = transfer_plans[0].as_payload() if transfer_plans else None
    hit_plans = [p for p in transfer_plans if p.hit_cost > 0]
    weekly_plan["best_hit"] = hit_plans[0].as_payload() if hit_plans else None

    free_hit_plans = [p for p in transfer_plans if p.hit_cost == 0]
    best_plan_obj = free_hit_plans[0] if free_hit_plans else None
    hit_margin = hit_horizon_margin(
        risk_profile=settings.manager.risk_profile,
        gameweek=gw,
        early_season_gws=settings.planning.early_season_gws,
        early_season_boost=settings.planning.early_season_hit_margin_boost,
    )
    deferred_upside = deferred_double_transfer_upside(
        owned_ids=private.player_ids,
        bank_tenths=private.bank_tenths,
        purchase_prices_tenths=private.purchase_prices_tenths,
        catalog=catalog,
        projections=proj_by_id,
        rules=season_rules,
        best_single=best_plan_obj,
        risk_profile=settings.manager.risk_profile,
        gameweek=gw,
    )
    transfer_decision = compare_roll_vs_transfer(
        free_transfers=int(private.free_transfers),
        best_plan=best_plan_obj,
        margin=hit_margin,
        rules=season_rules,
        ft_bank_option_value=settings.planning.ft_bank_option_value,
        min_horizon_delta_to_spend_ft=settings.planning.min_horizon_delta_to_spend_ft,
        deferred_upside=deferred_upside,
    )
    weekly_plan["transfer_decision"] = transfer_decision.as_payload()
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
    advice = reconcile_transfer_advice(
        advice,
        weekly_plan,
        affordable_transfers=affordable_transfers,
        owned_ids=private.player_ids,
        captain_id=private.captain_id,
        vice_id=private.vice_id,
        projections=proj_by_id,
        gameweeks=gameweeks,
        weights=weights,
        season_rules=season_rules,
    )
    advice = align_advice_to_after_transfer(advice, weekly_plan)

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
    if override_result.warnings:
        extra_warnings = _unique_texts(extra_warnings + list(override_result.warnings))
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
        "also_considered",
        "chips",
        "after_transfer",
        "transfer_decision",
        "horizon_impact",
        "best_plan",
    )
    out = {key: plan[key] for key in keys if key in plan}
    out["horizon"] = list(plan.get("horizon") or [])[:3]
    return out


def apply_transfer_pick_to_weekly_plan(
    weekly_plan: dict[str, Any],
    pick: TransferCandidate | None,
    *,
    owned_ids: list[int],
    captain_id: int | None,
    vice_id: int | None,
    projections: dict[int, PlayerProjection],
    gameweeks: list[int],
    weights: list[float],
    season_rules: SeasonRules,
    affordable_transfers: list[TransferCandidate],
) -> None:
    """Attach best_affordable / also_considered / after_transfer / horizon_impact for one pick."""
    from dataclasses import replace

    from fpl_agent.strategy.plan import build_weekly_plan
    from fpl_agent.strategy.transfers import (
        explain_vs_pick,
        horizon_transfer_impact,
        same_position_shortlist,
        xi_drop_for_swap,
    )

    weekly_plan["best_affordable"] = pick.as_payload() if pick is not None else None
    weekly_plan["also_considered"] = []
    weekly_plan["after_transfer"] = None
    weekly_plan["horizon_impact"] = None
    if pick is None:
        return

    after_ids = [pick.in_id if pid == pick.out_id else pid for pid in owned_ids]
    hold_plan = build_weekly_plan(
        owned_ids=owned_ids,
        projections=projections,
        gameweeks=gameweeks,
        captain_id=captain_id,
        vice_id=vice_id,
    )
    after_plan = build_weekly_plan(
        owned_ids=after_ids,
        projections=projections,
        gameweeks=gameweeks,
        captain_id=(captain_id if captain_id != pick.out_id else pick.in_id),
        vice_id=vice_id if vice_id != pick.out_id else None,
    )
    # Source of truth for "who drops" is the GW0 after XI, not horizon-weighted ranking.
    drop_id, gw0_drop = xi_drop_for_swap(
        owned_ids=owned_ids,
        out_id=pick.out_id,
        in_id=pick.in_id,
        projections=projections,
        rules=season_rules,
        gameweek_index=0,
    )
    if hold_plan.get("ok") and after_plan.get("ok"):
        hold_xi = {
            int(row["player_id"]): str(row["web_name"])
            for row in (hold_plan.get("xi") or [])
            if row.get("player_id") is not None
        }
        after_xi_ids = {
            int(row["player_id"]) for row in (after_plan.get("xi") or []) if row.get("player_id") is not None
        }
        for pid, name in hold_xi.items():
            if pid not in after_xi_ids and pid != pick.out_id:
                drop_id, gw0_drop = pid, name
                break
        else:
            if pick.out_id in hold_xi and pick.out_id not in after_xi_ids:
                drop_id, gw0_drop = pick.out_id, hold_xi[pick.out_id]

    drop_proj = projections.get(drop_id) if drop_id is not None else None
    drop_xp = float(drop_proj.xp_by_gw[0]) if drop_proj and drop_proj.xp_by_gw else None
    aligned_pick = pick
    if gw0_drop != pick.xi_drop_name or drop_xp != pick.xi_drop_xp_next:
        aligned_pick = replace(pick, xi_drop_name=gw0_drop, xi_drop_xp_next=drop_xp)
    weekly_plan["best_affordable"] = aligned_pick.as_payload()

    considered: list[dict[str, Any]] = []
    for cand in same_position_shortlist(aligned_pick, affordable_transfers, limit=3):
        if cand.in_id == aligned_pick.in_id and cand.out_id == aligned_pick.out_id:
            row_cand = aligned_pick
        else:
            alt_drop_id, alt_drop = xi_drop_for_swap(
                owned_ids=owned_ids,
                out_id=cand.out_id,
                in_id=cand.in_id,
                projections=projections,
                rules=season_rules,
                gameweek_index=0,
            )
            alt_proj = projections.get(alt_drop_id) if alt_drop_id is not None else None
            alt_xp = float(alt_proj.xp_by_gw[0]) if alt_proj and alt_proj.xp_by_gw else None
            row_cand = replace(cand, xi_drop_name=alt_drop, xi_drop_xp_next=alt_xp)
        row = row_cand.as_payload()
        row["picked"] = cand.in_id == aligned_pick.in_id and cand.out_id == aligned_pick.out_id
        if not row["picked"]:
            row["reason"] = explain_vs_pick(row_cand, aligned_pick)
        considered.append(row)
    weekly_plan["also_considered"] = considered

    if after_plan.get("ok"):
        weekly_plan["after_transfer"] = {
            "out_id": aligned_pick.out_id,
            "in_id": aligned_pick.in_id,
            "out_name": aligned_pick.out_name,
            "in_name": aligned_pick.in_name,
            "xi_drop_name": aligned_pick.xi_drop_name,
            "formation": after_plan.get("formation"),
            "xi": after_plan.get("xi"),
            "bench": after_plan.get("bench"),
            "model_captain": after_plan.get("model_captain"),
            "model_vice": after_plan.get("model_vice"),
        }
    weekly_plan["horizon_impact"] = horizon_transfer_impact(
        owned_ids=owned_ids,
        after_ids=after_ids,
        projections=projections,
        rules=season_rules,
        gameweeks=gameweeks,
        weights=weights,
    )


def _starter_candidate(
    candidates: list[TransferCandidate],
    *,
    out_id: int,
    in_id: int,
) -> TransferCandidate | None:
    for cand in candidates:
        if cand.out_id == out_id and cand.in_id == in_id and cand.affordable and cand.in_starts:
            return cand
    return None


def _advice_transfer_pair(
    advice: DailyAdvice,
    candidates: list[TransferCandidate] | None = None,
) -> tuple[int, int] | None:
    """Return out/in ids for the advised transfer.

    Live models sometimes mis-label the transfer as hold while still citing the
    candidate player_ids — treat those as transfers when they match a starter buy.
    """
    for move in advice.suggested_moves:
        if move.move_type == MoveType.TRANSFER and len(move.player_ids) >= 2:
            return int(move.player_ids[0]), int(move.player_ids[1])
    if not candidates:
        return None
    for move in advice.suggested_moves:
        if len(move.player_ids) < 2:
            continue
        out_id, in_id = int(move.player_ids[0]), int(move.player_ids[1])
        if _starter_candidate(candidates, out_id=out_id, in_id=in_id) is not None:
            return out_id, in_id
    return None


def _coerce_mislabeled_transfer_moves(
    advice: DailyAdvice,
    *,
    out_id: int,
    in_id: int,
) -> DailyAdvice:
    """Force matching moves to move_type=transfer so Do this cannot say hold for a swap."""
    from fpl_agent.llm.client import PlanAction

    changed = False
    new_moves: list[DailyMove] = []
    for move in advice.suggested_moves:
        ids = [int(x) for x in move.player_ids]
        if (
            len(ids) >= 2
            and ids[0] == out_id
            and ids[1] == in_id
            and move.move_type != MoveType.TRANSFER
        ):
            new_moves.append(move.model_copy(update={"move_type": MoveType.TRANSFER}))
            changed = True
        else:
            new_moves.append(move)
    if not changed:
        return advice
    updates: dict[str, Any] = {"suggested_moves": new_moves}
    if advice.plan_action == PlanAction.KEEP:
        updates["plan_action"] = PlanAction.REVISE
    warnings = list(advice.warnings)
    warnings.append("coerced_hold_move_to_transfer")
    updates["warnings"] = warnings
    return advice.model_copy(update=updates)


def _snap_advice_to_pick(advice: DailyAdvice, pick: TransferCandidate) -> DailyAdvice:
    """Rewrite the first transfer move onto the engine pick so Do this matches This week."""
    payload = pick.as_payload()
    summary = f"{pick.out_name} to {pick.in_name}"
    why = str(payload.get("reason") or "").strip() or (
        f"{pick.in_name} is the supplied this-week upgrade over {pick.out_name} "
        f"({pick.delta_gw_xp:+.1f} pts this GW)."
    )
    headline = (
        f"Sell {pick.out_name} for {pick.in_name}, keep the rest of the plan, "
        "and recheck late team news."
    )
    new_moves: list[DailyMove] = []
    replaced = False
    for move in advice.suggested_moves:
        if move.move_type == MoveType.TRANSFER and not replaced:
            new_moves.append(
                move.model_copy(
                    update={
                        "summary": summary,
                        "why": why,
                        "player_ids": [pick.out_id, pick.in_id],
                    }
                )
            )
            replaced = True
            continue
        new_moves.append(move)
    if not replaced:
        new_moves.insert(
            0,
            DailyMove(
                move_type=MoveType.TRANSFER,
                summary=summary,
                why=why,
                player_ids=[pick.out_id, pick.in_id],
                urgency="high",
            ),
        )
    warnings = list(advice.warnings)
    warnings.append(f"aligned_transfer_to_best_affordable:{pick.out_name}->{pick.in_name}")
    return advice.model_copy(
        update={
            "suggested_moves": new_moves,
            "headline": headline if advice.plan_action.value == "revise" else advice.headline,
            "warnings": warnings,
        }
    )


def reconcile_transfer_advice(
    advice: DailyAdvice,
    weekly_plan: dict[str, Any],
    *,
    affordable_transfers: list[TransferCandidate],
    owned_ids: list[int],
    captain_id: int | None,
    vice_id: int | None,
    projections: dict[int, PlayerProjection],
    gameweeks: list[int],
    weights: list[float],
    season_rules: SeasonRules,
) -> DailyAdvice:
    """Keep Do this and This week on the engine 1-FT pick.

    Near-tied defender upgrades (Ajayi / Egan / De Cuyper) previously flipped
    whenever the model preferred a different legal starter buy. The named
    transfer is now always ``weekly_plan.best_affordable``; the model may only
    explain it, not replace it.
    """
    engine_raw = weekly_plan.get("best_affordable") or {}
    engine_pick: TransferCandidate | None = None
    if engine_raw.get("out_id") is not None and engine_raw.get("in_id") is not None:
        engine_pick = _starter_candidate(
            affordable_transfers,
            out_id=int(engine_raw["out_id"]),
            in_id=int(engine_raw["in_id"]),
        )

    pair = _advice_transfer_pair(advice, affordable_transfers)
    if engine_pick is None:
        return advice

    if pair is not None:
        out_id, in_id = pair
        advice = _coerce_mislabeled_transfer_moves(advice, out_id=out_id, in_id=in_id)

    if pair is not None and pair[0] == engine_pick.out_id and pair[1] == engine_pick.in_id:
        return advice

    advice = _snap_advice_to_pick(advice, engine_pick)
    apply_transfer_pick_to_weekly_plan(
        weekly_plan,
        engine_pick,
        owned_ids=owned_ids,
        captain_id=captain_id,
        vice_id=vice_id,
        projections=projections,
        gameweeks=gameweeks,
        weights=weights,
        season_rules=season_rules,
        affordable_transfers=affordable_transfers,
    )
    return advice


def _scrub_false_bench_claims(text: str, xi_names: set[str]) -> str:
    """Remove 'X drops to the bench' clauses when X is still in the after XI."""
    out = text
    for name in sorted(xi_names, key=len, reverse=True):
        if not name:
            continue
        escaped = re.escape(name)
        out = re.sub(
            rf";?\s*{escaped}\s+drops(?:\s+out)?\s+(?:of\s+the\s+XI|to\s+the\s+bench)",
            "",
            out,
            flags=re.IGNORECASE,
        )
        out = re.sub(
            rf"(?:,?\s*)?(?:and\s+)?bench\s+{escaped}\b",
            "",
            out,
            flags=re.IGNORECASE,
        )
        out = re.sub(
            rf"\bover\s+{escaped}\b",
            "",
            out,
            flags=re.IGNORECASE,
        )
    out = re.sub(r"\s{2,}", " ", out).strip(" ;,")
    out = re.sub(r"\s+\.", ".", out)
    return out


def align_advice_to_after_transfer(advice: DailyAdvice, weekly_plan: dict[str, Any]) -> DailyAdvice:
    """Force Do this lineup / why / detail to match after_transfer XI and bench."""
    after = weekly_plan.get("after_transfer") or {}
    xi_rows = [row for row in (after.get("xi") or []) if isinstance(row, dict)]
    bench_rows = [row for row in (after.get("bench") or []) if isinstance(row, dict)]
    if not xi_rows:
        return advice

    xi_names = {str(row.get("web_name") or "") for row in xi_rows} - {""}
    bench_names = {str(row.get("web_name") or "") for row in bench_rows} - {""}
    in_name = str(after.get("in_name") or "")
    drop = after.get("xi_drop_name")
    if drop and drop in xi_names:
        drop = None
    if drop and drop not in bench_names:
        # Prefer an actual after-bench player who left the hold path, else omit.
        drop = None

    best_reason = str((weekly_plan.get("best_affordable") or {}).get("reason") or "").strip()
    warnings = list(advice.warnings)
    new_moves: list[DailyMove] = []
    saw_transfer = False
    for move in advice.suggested_moves:
        if move.move_type == MoveType.LINEUP:
            continue
        if move.move_type == MoveType.TRANSFER:
            saw_transfer = True
            why = best_reason or _scrub_false_bench_claims(move.why, xi_names)
            summary = move.summary
            out_n = str(after.get("out_name") or "")
            in_n = str(after.get("in_name") or "")
            if out_n and in_n:
                summary = f"Sell {out_n} for {in_n}"
            new_moves.append(move.model_copy(update={"why": why, "summary": summary}))
            continue
        if move.move_type == MoveType.CAPTAIN:
            cap = after.get("model_captain") or {}
            cap_name = str(cap.get("web_name") or "")
            if cap_name and cap_name not in move.summary:
                new_moves.append(
                    move.model_copy(
                        update={
                            "summary": f"Captain {cap_name}",
                            "why": (
                                f"{cap_name} is the modelled captain after the transfer "
                                f"({float(cap.get('xp_next') or 0):.1f} xP)."
                            ),
                            "player_ids": [int(cap["player_id"])] if cap.get("player_id") else move.player_ids,
                        }
                    )
                )
                continue
        new_moves.append(move)

    if saw_transfer and in_name:
        if in_name in xi_names:
            summary = f"Start {in_name}"
            why = (
                f"Play {in_name}: higher projected points this week than the defender "
                f"they replace in the XI."
            )
            if drop and drop in bench_names:
                summary += f" and bench {drop}"
                in_row = next((r for r in xi_rows if str(r.get("web_name")) == in_name), {})
                drop_row = next((r for r in bench_rows if str(r.get("web_name")) == drop), {})
                in_pts = in_row.get("xp_next")
                drop_pts = drop_row.get("xp_next")
                if in_pts is not None and drop_pts is not None:
                    why = (
                        f"Start {in_name} ({float(in_pts):.1f} pts) and bench {drop} "
                        f"({float(drop_pts):.1f} pts). The XI is ranked by projected points — "
                        f"not by how easy the fixture looks."
                    )
                else:
                    why = (
                        f"Start {in_name} and bench {drop} because {in_name} projects more "
                        f"points this week."
                    )
            new_moves.append(
                DailyMove(
                    move_type=MoveType.LINEUP,
                    summary=summary,
                    why=why,
                    urgency="medium",
                )
            )
        elif in_name in bench_names:
            new_moves.append(
                DailyMove(
                    move_type=MoveType.LINEUP,
                    summary=f"Leave {in_name} on the bench this week",
                    why=(
                        f"{in_name} joins the squad, but other players still project more "
                        f"points this week, so keep them as cover."
                    ),
                    urgency="medium",
                )
            )

    detail = _scrub_false_bench_claims(advice.detail, xi_names)
    headline = _scrub_false_bench_claims(advice.headline, xi_names)
    from fpl_agent.llm.client import PlanAction

    plan_action = advice.plan_action
    if saw_transfer and after.get("out_name") and after.get("in_name"):
        plan_action = PlanAction.REVISE
        drop_bit = f", start {in_name} (bench {drop})" if drop and drop in bench_names else f", start {in_name}"
        cap_name = str((after.get("model_captain") or {}).get("web_name") or "")
        cap_bit = f", and captain {cap_name}" if cap_name else ""
        headline = (
            f"Sell {after.get('out_name')} for {after.get('in_name')}"
            f"{drop_bit}{cap_bit}."
        )
        # Replace truncated-payload WATCH essays with the engine reason.
        if best_reason and (
            "weekly_plan" in detail.lower()
            or "missing" in detail.lower()
            or "cannot safely" in detail.lower()
            or "omits" in detail.lower()
        ):
            detail = best_reason
    tldr = [_scrub_false_bench_claims(item, xi_names) for item in advice.tldr]
    if "aligned_lineup_to_after_transfer" not in warnings:
        warnings.append("aligned_lineup_to_after_transfer")
    return advice.model_copy(
        update={
            "suggested_moves": new_moves,
            "detail": detail,
            "headline": headline,
            "tldr": tldr,
            "warnings": warnings,
            "plan_action": plan_action,
        }
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


def _player_names(rows: list[Any], *, with_points: bool = False) -> str:
    """Format player list; optional projected points so reports do not lead with start%."""
    names: list[str] = []
    for player in rows:
        name = str(player.get("web_name") or player.get("player_id") or "?")
        if with_points and player.get("xp_next") is not None:
            names.append(f"{name} ({float(player['xp_next']):.1f} pts)")
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
    # Prefer after_transfer labels so Do this / This week cannot name different swaps.
    label = after if after.get("out_name") and after.get("in_name") else best
    if after.get("xi") and label:
        drop = after.get("xi_drop_name") or (best or {}).get("xi_drop_name")
        xi_names = {
            str(player.get("web_name") or "")
            for player in (after.get("xi") or [])
            if isinstance(player, dict)
        }
        drop_bit = (
            f"; {drop} drops out of the XI"
            if drop and drop != label.get("out_name") and drop not in xi_names
            else ""
        )
        lines.append(
            f"After **{label.get('out_name')} → {label.get('in_name')}** "
            f"({label.get('in_name')} starts{drop_bit}):"
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
        lines.append(
            f"- XI ({using.get('formation') or plan.get('formation')}): "
            f"{_player_names(xi, with_points=True)}"
        )
    if bench:
        lines.append(f"- Bench: {_player_names(bench, with_points=True)}")
    xi_why = explain_xi_choice(
        xi=[row for row in xi if isinstance(row, dict)],
        bench=[row for row in bench if isinstance(row, dict)],
        formation=str(using.get("formation") or plan.get("formation") or "") or None,
        in_name=str(label.get("in_name") or "") if isinstance(label, dict) else None,
        drop_name=(
            str(after.get("xi_drop_name") or (best or {}).get("xi_drop_name") or "") or None
            if after or best
            else None
        ),
    )
    if xi_why:
        lines.append(f"- {xi_why}")
    if cap:
        lines.append(
            f"- Captain: **{cap.get('web_name')}** ({cap.get('xp_next')} xP) · "
            f"Vice: **{(vice or {}).get('web_name') or '—'}**"
        )
        cap_name = str(cap.get("web_name") or "")
        if cap_name:
            lines.append(
                f"- Why captain: **{cap_name}** has the best projected score among likely starters this week."
            )
    also = [row for row in (plan.get("also_considered") or []) if row.get("in_name")]
    if also:
        pos_n = int(also[0].get("element_type") or 0)
        pos = POSITION_LABEL.get(pos_n, "player")
        if len(also) == 1:
            reason = str(also[0].get("reason") or "").strip()
            if reason:
                lines.append(f"- Why this transfer: {reason}")
        else:
            lines.append(f"- Compared with other affordable {pos}s:")
            for row in also:
                tag = "recommended" if row.get("picked") else "also looked at"
                reason = str(row.get("reason") or "").strip()
                bit = f": {reason}" if reason else ""
                lines.append(f"  - **{row.get('in_name')}** ({tag}){bit}")
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
    impact = plan.get("horizon_impact") or {}
    impact_rows = list(impact.get("by_gw") or [])[:4]
    if impact_rows:
        bits = " · ".join(
            f"GW{row.get('gw')} {float(row.get('delta_xp') or 0):+.1f}" for row in impact_rows
        )
        lines.append(f"- Transfer vs hold (XI pts): {bits}")
        reason = str(impact.get("reason") or "").strip()
        if reason:
            lines.append(f"- Future weeks: {reason}")
    decision = plan.get("transfer_decision") or {}
    decision_reason = str(decision.get("reason") or "").strip()
    if decision_reason:
        action = str(decision.get("action") or "").lower()
        label_ft = "Spend FT now" if action == "transfer" else "Bank FT"
        lines.append(f"- FT timing ({label_ft}): {decision_reason}")
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
    from fpl_agent.reporting.plan_doc import write_plan_doc

    write_plan_doc(report, root=root)
    _write_decision_ledger(report)
    return path


def _write_decision_ledger(report: DailyReport) -> None:
    from fpl_agent.evaluation.ledger import DecisionRecord, build_decision_id, write_decision_record

    if report.skipped:
        return
    payload = {
        "gameweek": report.gameweek,
        "weekly_plan": report.weekly_plan,
        "plan_action": report.plan_action,
    }
    now = datetime.now(UTC).isoformat()
    record = DecisionRecord(
        decision_id=build_decision_id(payload),
        season="2026-27",
        gameweek=report.gameweek,
        generated_at=now,
        data_cutoff=now,
        team_state={"executability": report.executability},
        executability=report.executability,
        rules_hash="",
        catalog_hash="",
        projection_hash="",
        config_hash="",
        code_version="",
        roll={},
        primary={"plan_action": report.plan_action},
        warnings=list(report.warnings),
        report_hash=build_decision_id({"headline": report.headline}),
    )
    try:
        write_decision_record(Path("data/decision-ledger"), record)
    except FileExistsError:
        pass
