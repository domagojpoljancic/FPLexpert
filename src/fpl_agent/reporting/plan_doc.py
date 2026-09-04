"""Deterministic season-horizon plan explainer (Mermaid + prose) for GitHub/phone."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fpl_agent.daily import DailyReport

# Locked primary = weekly_plan.best_affordable / after_transfer (stability contract).
_SECRET_MARKERS = (
    "FPL_PRIVATE_STATE_B64",
    "data/private-state",
    "private-state/current",
    "sk-",
    "BEGIN PRIVATE KEY",
)


def locked_primary(plan: dict[str, Any]) -> dict[str, Any]:
    """Headline OUT/IN from the locked pick — never a second ranking authority."""
    after = plan.get("after_transfer") or {}
    best = plan.get("best_affordable") or {}
    if after.get("out_name") and after.get("in_name"):
        return {
            "out_id": after.get("out_id", best.get("out_id")),
            "in_id": after.get("in_id", best.get("in_id")),
            "out_name": after.get("out_name"),
            "in_name": after.get("in_name"),
            "bank_after_tenths": best.get("bank_after_tenths"),
            "sell_tenths": best.get("sell_tenths"),
            "buy_tenths": best.get("buy_tenths"),
            "delta_weighted_xp": best.get("delta_weighted_xp"),
            "delta_gw_xp": best.get("delta_gw_xp"),
            "reason": best.get("reason"),
        }
    if best.get("out_name") and best.get("in_name"):
        return {
            "out_id": best.get("out_id"),
            "in_id": best.get("in_id"),
            "out_name": best.get("out_name"),
            "in_name": best.get("in_name"),
            "bank_after_tenths": best.get("bank_after_tenths"),
            "sell_tenths": best.get("sell_tenths"),
            "buy_tenths": best.get("buy_tenths"),
            "delta_weighted_xp": best.get("delta_weighted_xp"),
            "delta_gw_xp": best.get("delta_gw_xp"),
            "reason": best.get("reason"),
        }
    return {}


def render_plan_doc(report: DailyReport) -> str:
    """Build `reports/plan-gw{N}.md` body from an existing DailyReport (no new ranking)."""
    plan = report.weekly_plan or {}
    primary = locked_primary(plan)
    impact = plan.get("horizon_impact") or {}
    by_gw = _sorted_gw_rows(list(impact.get("by_gw") or []))
    decision = plan.get("transfer_decision") or {}
    chips = sorted(
        [c for c in (plan.get("chips") or []) if isinstance(c, dict)],
        key=lambda c: str(c.get("kind") or ""),
    )
    calendar = _sorted_calendar(list(plan.get("fixture_calendar") or []))

    lines: list[str] = [
        f"# Season plan — Gameweek {report.gameweek}",
        "",
        _headline(report, primary),
        "",
        "## Why this move over the next weeks",
        "",
        _para_horizon(primary, impact, by_gw),
        "",
        _mermaid_horizon_xp(by_gw, primary),
        "",
        "## Spend now vs bank the free transfer",
        "",
        _para_bank_vs_spend(decision, primary),
        "",
        _mermaid_timeline(report.gameweek, primary, decision, chips, calendar),
        "",
        "## Bank and value after the move",
        "",
        _para_bank_value(primary, decision),
        "",
        _mermaid_bank_ft(primary, decision),
        "",
        "## Confirmed DGW / BGW in the horizon",
        "",
        _para_calendar(calendar),
        "",
        _mermaid_calendar(calendar),
        "",
        "## Chip timing",
        "",
        _para_chips(chips),
        "",
        "_Recommend only — you make all FPL changes. Numbers from the locked weekly primary; no second ranking._",
        "",
    ]
    text = "\n".join(lines)
    _assert_no_secrets(text)
    return text


def write_plan_doc(report: DailyReport, root: Path = Path("reports")) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"plan-gw{report.gameweek}.md"
    path.write_text(render_plan_doc(report), encoding="utf-8")
    return path


def _headline(report: DailyReport, primary: dict[str, Any]) -> str:
    if primary.get("out_name") and primary.get("in_name"):
        return (
            f"Locked move: **{primary['out_name']} → {primary['in_name']}** "
            f"(plan **{report.plan_action.upper()}**)."
        )
    return f"Locked move: **hold** (plan **{report.plan_action.upper()}**)."


def _para_horizon(
    primary: dict[str, Any],
    impact: dict[str, Any],
    by_gw: list[dict[str, Any]],
) -> str:
    reason = str(impact.get("reason") or "").strip()
    weighted = impact.get("weighted_delta")
    if primary.get("out_name") and primary.get("in_name") and by_gw:
        bits = ", ".join(
            f"GW{row['gw']} {float(row.get('delta_xp') or 0):+.1f}" for row in by_gw
        )
        base = (
            f"Selling **{primary['out_name']}** for **{primary['in_name']}** changes the XI "
            f"projection across the planning horizon ({bits}"
        )
        if weighted is not None:
            base += f"; {float(weighted):+.1f} weighted overall"
        base += ")."
        if reason:
            return f"{base} {reason}"
        return base
    if reason:
        return reason
    return "No horizon impact rows on this report — hold or missing transfer pick."


def _para_bank_vs_spend(decision: dict[str, Any], primary: dict[str, Any]) -> str:
    action = str(decision.get("action") or "").lower()
    reason = str(decision.get("reason") or "").strip()
    ft_now = decision.get("free_transfers_now")
    ft_roll = decision.get("free_transfers_if_roll")
    ft_xfer = decision.get("free_transfers_if_transfer")
    penalty = decision.get("ft_banking_penalty")
    deferred = decision.get("deferred_upside")
    net = decision.get("net_value_after_ft_penalty")
    seq_rec = decision.get("sequence_recommendation")
    seq_act = decision.get("sequence_act_now_ev")
    seq_roll = decision.get("sequence_roll_to_2ft_ev")
    seq_hit = decision.get("sequence_hit_ev")
    verdict = "Spend the FT now" if action == "transfer" else "Bank the FT"
    parts = [f"**Bank vs spend verdict: {verdict}.**"]
    if reason:
        parts.append(reason)
    detail: list[str] = []
    if ft_now is not None and ft_roll is not None and ft_xfer is not None:
        detail.append(f"FT now {ft_now} → {ft_xfer} if you transfer, {ft_roll} if you roll")
    if seq_rec is not None:
        detail.append(
            f"sequence {seq_rec} (act-now {seq_act}, roll-to-2FT {seq_roll}, hit {seq_hit})"
        )
    elif penalty is not None:
        detail.append(f"flat FT-bank option cost ~{float(penalty):.2f}")
    if deferred is not None:
        detail.append(f"deferred dual-move upside {float(deferred):+.2f}")
    if net is not None:
        detail.append(f"net after FT penalty {float(net):+.2f}")
    if primary.get("out_name") and primary.get("in_name"):
        detail.append(f"locked pick {primary['out_name']}→{primary['in_name']}")
    if detail:
        parts.append("(" + "; ".join(detail) + ".)")
    return " ".join(parts)


def _para_bank_value(primary: dict[str, Any], decision: dict[str, Any]) -> str:
    bank_after = primary.get("bank_after_tenths")
    sell = primary.get("sell_tenths")
    buy = primary.get("buy_tenths")
    ft_xfer = decision.get("free_transfers_if_transfer")
    ft_roll = decision.get("free_transfers_if_roll")
    parts: list[str] = []
    if sell is not None and buy is not None:
        parts.append(
            f"The locked swap sells at £{float(sell) / 10:.1f}m and buys at £{float(buy) / 10:.1f}m"
        )
    if bank_after is not None:
        parts.append(f"leaving **£{float(bank_after) / 10:.1f}m** in the bank")
    if not parts:
        return (
            "Bank and sell/buy tenths are not on this report for the locked pick; "
            "no invented team-value path across future price rises."
        )
    sentence = ", ".join(parts) + "."
    if ft_xfer is not None or ft_roll is not None:
        sentence += (
            f" Free transfers after acting: {ft_xfer}; after rolling: {ft_roll}."
        )
    sentence += (
        " Future affordability is this residual bank plus selling prices — "
        "not a forecast of price changes."
    )
    return sentence


def _para_calendar(calendar: list[dict[str, Any]]) -> str:
    if not calendar:
        return (
            "No confirmed DGW/BGW strip was attached to this report "
            "(fixtures-feed calendar is surfaced when present). "
            "Any unscheduled windows must be labelled priors — never shown as confirmed."
        )
    doubles = [c for c in calendar if c.get("is_double_gw")]
    blanks = [c for c in calendar if c.get("is_blank_gw")]
    if not doubles and not blanks:
        gws = ", ".join(f"GW{c['gameweek']}" for c in calendar)
        return f"Confirmed fixtures in horizon ({gws}): no DGW/BGW flags from the feed."
    bits: list[str] = []
    if doubles:
        bits.append("DGW " + ", ".join(f"GW{c['gameweek']}" for c in doubles))
    if blanks:
        bits.append("BGW " + ", ".join(f"GW{c['gameweek']}" for c in blanks))
    return "Confirmed from fixtures feed: " + "; ".join(bits) + "."


def _para_chips(chips: list[dict[str, Any]]) -> str:
    if not chips:
        return "No chip advice on this report."
    parts: list[str] = []
    for chip in chips:
        kind = chip.get("kind") or "?"
        action = chip.get("action") or "hold"
        reason = str(chip.get("reason") or "").strip()
        avail = "available" if chip.get("available") else "unavailable"
        line = f"**{kind}**: {action} ({avail})"
        if reason:
            line += f" — {reason}"
        parts.append(line)
    return " ".join(parts)


def _mermaid_horizon_xp(by_gw: list[dict[str, Any]], primary: dict[str, Any]) -> str:
    if not by_gw:
        return "_No horizon xP series to chart._"
    labels = ", ".join(f"GW{row['gw']}" for row in by_gw)
    hold = ", ".join(f"{float(row.get('hold_xi_xp') or 0):.1f}" for row in by_gw)
    after = ", ".join(f"{float(row.get('after_xi_xp') or 0):.1f}" for row in by_gw)
    y_vals = [float(row.get("hold_xi_xp") or 0) for row in by_gw] + [
        float(row.get("after_xi_xp") or 0) for row in by_gw
    ]
    y_min = max(0, int(min(y_vals) - 2))
    y_max = int(max(y_vals) + 2)
    title = "XI xP hold vs after transfer"
    if primary.get("out_name") and primary.get("in_name"):
        title = f"XI xP: hold vs {primary['out_name']} to {primary['in_name']}"
    # Table first (always readable on phone), then Mermaid xychart for GitHub.
    table = [
        "| GW | Hold XI xP | After XI xP | Delta |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in by_gw:
        table.append(
            f"| {row['gw']} | {float(row.get('hold_xi_xp') or 0):.2f} | "
            f"{float(row.get('after_xi_xp') or 0):.2f} | "
            f"{float(row.get('delta_xp') or 0):+.2f} |"
        )
    chart = "\n".join(
        [
            "```mermaid",
            "xychart-beta",
            f'    title "{title}"',
            f"    x-axis [{labels}]",
            f'    y-axis "XI xP" {y_min} --> {y_max}',
            f"    line [{hold}]",
            f"    line [{after}]",
            "```",
        ]
    )
    return "\n".join(table) + "\n\n" + chart


def _mermaid_timeline(
    gameweek: int,
    primary: dict[str, Any],
    decision: dict[str, Any],
    chips: list[dict[str, Any]],
    calendar: list[dict[str, Any]],
) -> str:
    action = str(decision.get("action") or "hold").lower()
    move = (
        f"{primary.get('out_name')} to {primary.get('in_name')}"
        if primary.get("out_name") and primary.get("in_name")
        else "hold"
    )
    nodes: list[str] = [
        "flowchart LR",
        f'    A["GW{gameweek} locked: {move}"]',
    ]
    edges: list[str] = []
    if action == "transfer":
        nodes.append(f'    B["Spend FT now"]')
        edges.append("    A --> B")
        prev = "B"
    else:
        nodes.append(f'    B["Bank FT"]')
        edges.append("    A --> B")
        prev = "B"
    ft_roll = decision.get("free_transfers_if_roll")
    if ft_roll is not None:
        nodes.append(f'    C["Next GW: {ft_roll} FT if rolled"]')
        edges.append(f"    {prev} --> C")
        prev = "C"
    play_chips = [c for c in chips if c.get("action") == "play" and c.get("available")]
    hold_note = "hold chips" if not play_chips else "play " + ", ".join(
        str(c.get("kind")) for c in play_chips
    )
    nodes.append(f'    D["Chips: {hold_note}"]')
    edges.append(f"    {prev} --> D")
    prev = "D"
    flagged = [c for c in calendar if c.get("is_double_gw") or c.get("is_blank_gw")]
    if flagged:
        label = ", ".join(
            f"GW{c['gameweek']}{' DGW' if c.get('is_double_gw') else ''}{' BGW' if c.get('is_blank_gw') else ''}".strip()
            for c in flagged
        )
        nodes.append(f'    E["Confirmed windows: {label}"]')
        edges.append(f"    {prev} --> E")
    return "```mermaid\n" + "\n".join(nodes + edges) + "\n```"


def _mermaid_bank_ft(primary: dict[str, Any], decision: dict[str, Any]) -> str:
    bank_after = primary.get("bank_after_tenths")
    ft_now = decision.get("free_transfers_now")
    ft_xfer = decision.get("free_transfers_if_transfer")
    ft_roll = decision.get("free_transfers_if_roll")
    if bank_after is None and ft_now is None:
        return "_No bank/FT trajectory fields on this report._"
    bank_label = (
        f"£{float(bank_after) / 10:.1f}m after move"
        if bank_after is not None
        else "bank n/a"
    )
    lines = [
        "```mermaid",
        "flowchart TD",
        f'    N0["FT now: {ft_now if ft_now is not None else "n/a"}"]',
        f'    N1["If transfer: FT {ft_xfer if ft_xfer is not None else "n/a"} / {bank_label}"]',
        f'    N2["If roll: FT {ft_roll if ft_roll is not None else "n/a"}"]',
        "    N0 --> N1",
        "    N0 --> N2",
        "```",
    ]
    return "\n".join(lines)


def _mermaid_calendar(calendar: list[dict[str, Any]]) -> str:
    if not calendar:
        return "_No confirmed fixture-calendar rows to chart._"
    # Fixed left-to-right GW order.
    nodes = ["flowchart LR"]
    ids: list[str] = []
    for idx, row in enumerate(calendar):
        gw = row["gameweek"]
        nid = f"G{idx}"
        ids.append(nid)
        flags: list[str] = []
        if row.get("is_double_gw"):
            flags.append("DGW")
        if row.get("is_blank_gw"):
            flags.append("BGW")
        tag = " ".join(flags) if flags else "SGW"
        nodes.append(f'    {nid}["GW{gw} {tag}"]')
    for a, b in zip(ids, ids[1:], strict=False):
        nodes.append(f"    {a} --> {b}")
    return "```mermaid\n" + "\n".join(nodes) + "\n```"


def _sorted_gw_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [r for r in rows if r.get("gw") is not None],
        key=lambda r: int(r["gw"]),
    )


def _sorted_calendar(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [r for r in rows if r.get("gameweek") is not None],
        key=lambda r: int(r["gameweek"]),
    )


def _assert_no_secrets(text: str) -> None:
    lower = text.lower()
    for marker in _SECRET_MARKERS:
        if marker.lower() in lower:
            raise ValueError(f"plan doc must not contain secret marker: {marker}")
