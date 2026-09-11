"""Pre-publish invariants for pre-deadline advice.

Catches report classes that LLM review historically missed: free-looking hits,
roll/transfer contradictions, and Wildcard triggers that are start-chance only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AdviceLintIssue:
    code: str
    message: str
    severity: str = "error"  # error | warning


_HIT_MARK = re.compile(r"(?:−|-|–)\s*(?:4|8)\b|\bhit\b|\bnet\b", re.IGNORECASE)
_ROLL_HOLD = re.compile(
    r"\b(?:roll|bank)\b.*\b(?:ft|free transfer|transfer)\b|"
    r"\b(?:bank|roll)\b.*\b(?:the\s+)?(?:ft|transfer)\b|"
    r"\bhold\s+the\s+transfer\b|"
    r"\bdo\s+not\s+transfer\b",
    re.IGNORECASE,
)
_START_ONLY_WC = re.compile(r"start\s+chance|p_start|below\s+\d+%\s+start", re.IGNORECASE)
_WC_SECOND_SIGNAL = re.compile(
    r"fixture|horizon|transfer[\s-]plan|rebuild|transfer plan|nets?\s+\+|targeted transfers",
    re.IGNORECASE,
)
_FREE_TRANSFER_CLAIM = re.compile(
    r"\bfree\s+transfer\b(?!\s+in\s+the\s+supplied)|"
    r"\bwithout\s+(?:a\s+)?hit\b|"
    r"\bno\s+hit\b",
    re.IGNORECASE,
)


def lint_predeadline_advice(
    *,
    weekly_plan: dict[str, Any] | None,
    suggested_moves: list[Any] | None = None,
    report_text: str | None = None,
    free_transfers: int | None = None,
) -> list[AdviceLintIssue]:
    """Return invariant violations for structured moves and/or rendered report text."""
    plan = weekly_plan or {}
    decision = plan.get("transfer_decision") or {}
    action = str(decision.get("action") or "").lower()
    hit = int(decision.get("hit_points_if_transfer") or 0)
    ft_now = decision.get("free_transfers_now")
    if ft_now is None:
        ft_now = free_transfers
    try:
        ft_now_i = int(ft_now) if ft_now is not None else None
    except (TypeError, ValueError):
        ft_now_i = None

    moves = list(suggested_moves or [])
    text = report_text or ""
    issues: list[AdviceLintIssue] = []

    def _move_type(move: Any) -> str:
        if isinstance(move, dict):
            return str(move.get("move_type") or move.get("type") or "").lower()
        raw = getattr(move, "move_type", "")
        return str(getattr(raw, "value", raw) or "").lower()

    def _move_blob(move: Any) -> str:
        if isinstance(move, dict):
            return f"{move.get('summary') or ''} {move.get('why') or ''}"
        return f"{getattr(move, 'summary', '')} {getattr(move, 'why', '')}"

    transfer_moves = [m for m in moves if _move_type(m) == "transfer"]
    hold_moves = [m for m in moves if _move_type(m) == "hold"]

    if action == "roll":
        if transfer_moves:
            issues.append(
                AdviceLintIssue(
                    code="roll_with_transfer_move",
                    message="transfer_decision is roll but suggested_moves still includes a transfer",
                )
            )
        if hit > 0 and hold_moves:
            blob = " ".join(_move_blob(m) for m in hold_moves)
            if not _HIT_MARK.search(blob):
                issues.append(
                    AdviceLintIssue(
                        code="roll_hold_missing_hit",
                        message=f"roll/hold text must disclose the −{hit} hit and net when FT is exhausted",
                    )
                )
        if hit > 0 and text:
            if not _HIT_MARK.search(text):
                issues.append(
                    AdviceLintIssue(
                        code="report_missing_hit_on_roll",
                        message="rendered report must mention the hit/net when rolling with 0 FT",
                    )
                )
            if re.search(r"\bsell\b", text, re.I) and not _HIT_MARK.search(text):
                issues.append(
                    AdviceLintIssue(
                        code="report_sell_without_hit",
                        message="report sells a player while rolling a hit without stating −N / net",
                    )
                )

    if action == "transfer" and hit > 0:
        if transfer_moves:
            blob = " ".join(_move_blob(m) for m in transfer_moves)
            if not _HIT_MARK.search(blob):
                issues.append(
                    AdviceLintIssue(
                        code="transfer_missing_hit_disclosure",
                        message=f"transfer move must disclose the −{hit} hit (and preferably net)",
                    )
                )
        if text and not _HIT_MARK.search(text):
            issues.append(
                AdviceLintIssue(
                    code="report_transfer_missing_hit",
                    message="rendered transfer advice must disclose the hit cost",
                )
            )

    if action == "transfer" and hold_moves:
        for move in hold_moves:
            if _ROLL_HOLD.search(_move_blob(move)):
                issues.append(
                    AdviceLintIssue(
                        code="transfer_with_competing_roll_hold",
                        message="transfer decision still has a hold move that banks/rolls the FT",
                    )
                )
                break

    if ft_now_i is not None and ft_now_i <= 0 and hit > 0 and text:
        if re.search(r"\b(?:both|either)\b.*\b(?:leave|left)\b.*\b(?:1|one)\b.*\bft\b", text, re.I):
            if not re.search(r"(?:−|-|–)\s*4|costs?\s+−|hit", text, re.I):
                issues.append(
                    AdviceLintIssue(
                        code="ft_after_implies_free_today",
                        message="FT-after wording implies a free move today when FT is 0 and a hit applies",
                    )
                )
        if _FREE_TRANSFER_CLAIM.search(text) and not _HIT_MARK.search(text):
            issues.append(
                AdviceLintIssue(
                    code="free_transfer_claim_with_hit",
                    message="report claims a free/no-hit transfer while hit_points_if_transfer > 0",
                )
            )

    for chip in plan.get("chips") or []:
        if not isinstance(chip, dict):
            continue
        if str(chip.get("kind") or "").lower() not in {"wildcard", "wc"}:
            continue
        if str(chip.get("action") or "").lower() != "play":
            continue
        reason = str(chip.get("reason") or "")
        if _START_ONLY_WC.search(reason) and not _WC_SECOND_SIGNAL.search(reason):
            issues.append(
                AdviceLintIssue(
                    code="wildcard_start_chance_only",
                    message="Wildcard play reason is start-chance only; needs fixtures and/or transfer-plan signal",
                )
            )

    return issues


def format_lint_warnings(issues: list[AdviceLintIssue]) -> list[str]:
    return [f"advice_lint:{issue.severity}:{issue.code}:{issue.message}" for issue in issues]
