"""Human price report. Lead with market movers, then plan-gated actions."""

from __future__ import annotations

from fpl_agent.prices.external import MarketMover
from fpl_agent.prices.types import (
    ActionClass,
    LikelihoodBand,
    PriceAction,
    PriceDirection,
    PricePrediction,
    ReportStatus,
)

_STATUS_HEADLINE = {
    ReportStatus.NO_ACTION: "No price action tonight.",
    ReportStatus.WATCH: "Watch list only — do not churn for £0.1m.",
    ReportStatus.ACT_TONIGHT_CONDITIONAL: "Price timing may matter if a listed condition still holds.",
    ReportStatus.ACT_TONIGHT: "Act in FPL yourself tonight if you still want the planned move.",
}

PREDICTOR_HINT = (
    "Do **not** transfer solely for a predicted £0.1m tick. If a riser looks useful, "
    "run the GW predictor / pre-deadline review first: "
    "`uv run fpl-agent predeadline --live-ai` "
    '(phone: Cloud Agent → "Run the pre-deadline review") '
    "and only buy if next-GW projected points beat your current options."
)


def status_headline(status: ReportStatus) -> str:
    return _STATUS_HEADLINE[status]


def escape_md(text: str) -> str:
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("<", "&lt;").replace("`", "'")


def report_status(
    actions: list[PriceAction],
    *,
    market: list[MarketMover] | None = None,
) -> ReportStatus:
    classes = {a.action_class for a in actions}
    if ActionClass.ACT_NOW_RECOMMENDED in classes:
        return ReportStatus.ACT_TONIGHT
    if ActionClass.ACT_NOW_CONDITIONAL in classes:
        return ReportStatus.ACT_TONIGHT_CONDITIONAL
    if ActionClass.WATCH in classes:
        return ReportStatus.WATCH
    if market and any(m.band != LikelihoodBand.UNLIKELY for m in market):
        return ReportStatus.WATCH
    return ReportStatus.NO_ACTION


def _fmt_mover(m: MarketMover) -> str:
    cost = f"£{m.cost_millions:.1f}m" if m.cost_millions is not None else "?"
    flags: list[str] = []
    if m.owned:
        flags.append("owned")
    if m.in_plan:
        flags.append("in plan")
    flag_s = f" [{', '.join(flags)}]" if flags else ""
    band = "likely" if m.band == LikelihoodBand.LIKELY_NEXT_WINDOW else "watch"
    return (
        f"{escape_md(m.web_name)} ({cost}){flag_s} — "
        f"{m.direction.value}, {band}, "
        f"LiveFPL progress_tonight={m.external_progress:+.2f}"
    )


def _transfer_advice_lines(market: list[MarketMover], actions: list[PriceAction]) -> list[str]:
    lines: list[str] = []
    unowned_likely_rises = [
        m
        for m in market
        if m.direction == PriceDirection.RISE
        and m.band == LikelihoodBand.LIKELY_NEXT_WINDOW
        and not m.owned
    ]
    owned_likely_falls = [
        m
        for m in market
        if m.direction == PriceDirection.FALL
        and m.band == LikelihoodBand.LIKELY_NEXT_WINDOW
        and m.owned
    ]
    act = [
        a
        for a in actions
        if a.action_class in {ActionClass.ACT_NOW_RECOMMENDED, ActionClass.ACT_NOW_CONDITIONAL}
    ]
    if act:
        lines.append(
            "- Plan-gated act-now items are listed under **Act tonight** — those are the only "
            "price-timing moves this job may recommend."
        )
    if unowned_likely_rises:
        names = ", ".join(escape_md(m.web_name) for m in unowned_likely_rises[:8])
        lines.append(
            f"- Likely **rises** not in your squad ({names}): interesting for *who* may tick up, "
            "not an automatic buy."
        )
        lines.append(f"- {PREDICTOR_HINT}")
    elif any(m.direction == PriceDirection.RISE and not m.owned for m in market):
        lines.append(f"- {PREDICTOR_HINT}")
    if owned_likely_falls:
        names = ", ".join(escape_md(m.web_name) for m in owned_likely_falls[:8])
        lines.append(
            f"- Owned players likely to **fall** ({names}): only sell if you already want them "
            "out for football reasons (or a planned transfer). Re-check with the GW predictor "
            "before spending a free transfer just to protect £0.1m."
        )
    if not lines:
        lines.append(
            "- No market-driven transfer check tonight. Keep free transfers for football moves."
        )
    return lines


def render_prices_markdown(
    *,
    gameweek: int,
    status: ReportStatus,
    actions: list[PriceAction],
    predictions: list[PricePrediction],
    snapshot_times: list[str],
    model_version: str,
    timezone_label: str,
    warnings: list[str],
    executability: str,
    market: list[MarketMover] | None = None,
    external_source: str | None = None,
) -> str:
    pred_by_id = {p.player_id: p for p in predictions}
    market = market or []
    act_now = [
        a
        for a in actions
        if a.action_class in {ActionClass.ACT_NOW_RECOMMENDED, ActionClass.ACT_NOW_CONDITIONAL}
    ]
    watches = [a for a in actions if a.action_class == ActionClass.WATCH]
    ignored = [a for a in actions if a.action_class == ActionClass.IGNORE]

    rises = [m for m in market if m.direction == PriceDirection.RISE]
    falls = [m for m in market if m.direction == PriceDirection.FALL]

    lines = [
        f"# Price watch — GW{gameweek}",
        f"Status: **{status.value}** | Executability: {executability}",
        f"Headline: {escape_md(status_headline(status))}",
        f"Clock: {escape_md(timezone_label)} (storage UTC)",
        "",
        "## Market tonight (who may rise / fall)",
    ]
    if not market:
        lines.append("- No external market movers in band (or feed unavailable).")
    else:
        lines.append("### Likely / watch rises")
        if rises:
            for m in rises:
                lines.append(f"- {_fmt_mover(m)}")
        else:
            lines.append("- None in band.")
        lines.append("")
        lines.append("### Likely / watch falls")
        if falls:
            for m in falls:
                lines.append(f"- {_fmt_mover(m)}")
        else:
            lines.append("- None in band.")
        lines.append("")
        lines.append(
            "_External progress is untrusted community data (LiveFPL JSON). "
            "It never overrides official `now_cost` and never alone triggers act-now._"
        )

    lines += ["", "## Should you transfer?", *_transfer_advice_lines(market, actions)]

    lines += ["", "## Act tonight (plan-gated)"]
    if act_now:
        for action in act_now[:6]:
            lines.append(f"- {escape_md(action.summary)}")
    else:
        lines.append("- None. Do not transfer just because this job ran.")

    lines += ["", "## Your squad / plan watch"]
    if watches:
        for action in watches[:12]:
            lines.append(f"- {escape_md(action.summary)}")
    else:
        lines.append("- None.")

    lines += ["", "## Ignored (your universe, why)"]
    if ignored:
        for action in ignored[:8]:
            why = ", ".join(action.rationale_codes[:4]) or "not material"
            name = escape_md(action.summary.split(":")[0])
            lines.append(f"- {name}: {escape_md(why)}")
        if len(ignored) > 8:
            lines.append(f"- … {len(ignored) - 8} more ignored")
    else:
        lines.append("- Nothing scored in squad/plan/watchlist universe.")

    lines += ["", "## Freshness"]
    if snapshot_times:
        lines.append("- Snapshots (UTC): " + ", ".join(escape_md(t) for t in snapshot_times[-4:]))
    else:
        lines.append("- No stored snapshots yet (single bootstrap pull).")
    lines.append(
        f"- Model: `{escape_md(model_version)}` — uncalibrated heuristic, not FPL’s unpublished formula."
    )
    lines.append("- Likelihood is never a percentage and is never produced by a language model.")
    if external_source:
        lines.append(f"- External feed: `{escape_md(external_source)}`")

    if warnings:
        lines += ["", "## Warnings"]
        lines.extend(f"- {escape_md(w)}" for w in warnings[:12])

    lines += [
        "",
        "## Sources",
        "- Official public bootstrap `https://fantasy.premierleague.com/api/bootstrap-static/`",
        "- Local snapshot hashes for the internal heuristic",
        "- Optional LiveFPL JSON `https://livefpl.us/api/prices.json` (untrusted; mirrors livefpl.net/prices)",
        "",
        "_Recommend only — you make all FPL changes._",
    ]
    _ = pred_by_id
    return "\n".join(lines)
