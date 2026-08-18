"""Human price report. Lead with the decision. Recommend-only."""

from __future__ import annotations

from fpl_agent.prices.types import ActionClass, PriceAction, PricePrediction, ReportStatus


def escape_md(text: str) -> str:
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("<", "&lt;").replace("`", "'")


def report_status(actions: list[PriceAction]) -> ReportStatus:
    classes = {a.action_class for a in actions}
    if ActionClass.ACT_NOW_RECOMMENDED in classes:
        return ReportStatus.ACT_TONIGHT
    if ActionClass.ACT_NOW_CONDITIONAL in classes:
        return ReportStatus.ACT_TONIGHT_CONDITIONAL
    if ActionClass.WATCH in classes:
        return ReportStatus.WATCH
    return ReportStatus.NO_ACTION


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
) -> str:
    pred_by_id = {p.player_id: p for p in predictions}
    act_now = [a for a in actions if a.action_class in {ActionClass.ACT_NOW_RECOMMENDED, ActionClass.ACT_NOW_CONDITIONAL}]
    watches = [a for a in actions if a.action_class == ActionClass.WATCH]
    ignored = [a for a in actions if a.action_class == ActionClass.IGNORE]

    lines = [
        f"# Price watch — GW{gameweek}",
        f"Status: **{status.value}** | Executability: {executability}",
        f"Clock: {escape_md(timezone_label)} (storage UTC)",
        "",
        "## Act tonight" if act_now else "## Act tonight",
    ]
    if act_now:
        for action in act_now[:6]:
            lines.append(f"- {escape_md(action.summary)}")
    else:
        lines.append("- None. Do not transfer just because this job ran.")

    lines += ["", "## Watch"]
    if watches:
        for action in watches[:12]:
            lines.append(f"- {escape_md(action.summary)}")
    else:
        lines.append("- None.")

    lines += ["", "## Ignored (why)"]
    if ignored:
        for action in ignored[:8]:
            why = ", ".join(action.rationale_codes[:4]) or "not material"
            name = escape_md(action.summary.split(":")[0])
            lines.append(f"- {name}: {escape_md(why)}")
        if len(ignored) > 8:
            lines.append(f"- … {len(ignored) - 8} more ignored")
    else:
        lines.append("- Nothing scored in universe.")

    lines += ["", "## Freshness"]
    if snapshot_times:
        lines.append("- Snapshots (UTC): " + ", ".join(escape_md(t) for t in snapshot_times[-4:]))
    else:
        lines.append("- No stored snapshots yet (single bootstrap pull).")
    lines.append(f"- Model: `{escape_md(model_version)}` — uncalibrated heuristic, not FPL’s unpublished formula.")
    lines.append("- Likelihood is never a percentage and is never produced by a language model.")

    if warnings:
        lines += ["", "## Warnings"]
        lines.extend(f"- {escape_md(w)}" for w in warnings[:12])

    lines += [
        "",
        "## Sources",
        "- Official public bootstrap `https://fantasy.premierleague.com/api/bootstrap-static/`",
        "- Local snapshot hashes only. No third-party HTML scrape.",
        "",
        "_Recommend only — you make all FPL changes._",
    ]
    # keep predictions referenced so reports stay auditable without dumping 40 names up top
    _ = pred_by_id
    return "\n".join(lines)
