# reflection-v1 — Development plan overview

Feature: a **reflection/retrospective** section inside the pre-deadline report itself — not a
separate command — that explains how last week's advice actually played out, gated on the
prior gameweek being **fully official/final** (skip entirely while it is still live). Short
explanation at the top of the report, a detailed section further down (mermaid charts
included), and a small cross-gameweek learning loop that proposes (never auto-applies)
calibration adjustments from the accumulated track record.

This directory is a **prompt pack**, in the same spirit as `outputs/cursor-prompts/horizon-v1/`.
Hand one milestone file to Cursor (Auto model is fine) at a time, in order. Let it inspect the
repo, implement, run tests, and report a checkpoint before you give it the next file. Do not
skip `INVENTORY.md` even if it looks already answered below — code may have moved since this
was written; re-verify the cited `file:line` anchors first.

## Why this feature, precisely

From the request that produced this plan:

1. Reflection/retrospective becomes part of the **predeadline** report, not a separate report.
2. Only include it once the **current/most-recently-played gameweek is done** (official, not
   provisional). If predeadline runs mid-gameweek, skip the reflection part entirely — no
   partial section, no heading.
3. Short explanation up top, detailed version further down — matching how the rest of the
   report already works (`Plan:`/`AI:` header lines are short; `## Why` is the detailed prose).
4. Charts where they earn their place (reuse the existing Mermaid convention from
   `reporting/plan_doc.py`).
5. Look at **past reports' suggestions**, check how accurate they were, and use that to adjust
   the algorithm for **future** reports — bounded, reversible, sample-gated, proposal-only in
   v1 (never an automatic weight change).
6. Specifically reflect on **transfer suggestions**: how the players involved actually
   performed, and what could have been done better — using only alternatives that were
   actually recorded pre-deadline, never an invented hindsight pick.

## Non-negotiables (carried over from the existing product contract)

These come from `outputs/cursor-prompts/00_READ_ME_FIRST.md` and
`outputs/cursor-prompts/07_decision_ledger_and_retrospectives.md`, and apply to every milestone
below:

- Never treat a provisional (not-yet-final) gameweek result as canonical. Official FPL guidance
  (already encoded in `src/fpl_agent/evaluation/finality.py` and
  `src/fpl_agent/rules/season.py:143-146`): scores stay provisional until 09:00 UK the day after
  the gameweek's final match, and only once `event.data_checked` is also true.
  If the current guidance has changed, verify against the live FPL API before assuming this file
  is still correct, cite the primary source, and update `docs/assumptions-register.md`.
- Never invent a hindsight "should have bought X" player. Any "what could have been done
  better" line must cite only players present in the recorded `also_considered` shortlist (or
  the recorded `saved_captain_id`) at decision time — never a live re-rank against this week's
  full player pool.
- The LLM (`fpl-agent predeadline --live-ai`) may only phrase prose around numbers the
  deterministic layer already computed. It must not compute or alter the reflection numbers,
  process/outcome grade, or any proposed adjustment.
- Reflection must never change the current week's transfer, lineup, or captain recommendation.
  It is additive and comes after the "Do this" / "Why" logic has already run.
- Adjustment proposals are **proposal-only** in this whole plan (M1–M6). No milestone here wires
  a proposal into the live projection engine. That would need its own future plan, its own
  explicit sign-off, and the leakage-free backtest gate described in M4 passing first.

## Milestones

| # | File | What it delivers |
| --- | --- | --- |
| M0 | `INVENTORY.md` | Read-only gate: what's already computed vs missing, with `file:line` citations. Re-verify before M1. |
| M1 | `M1_finality_gate_and_reflection_builder.md` | Deterministic "is last GW actually final?" gate + a `ReflectionSummary` builder (no report changes yet). |
| M2 | `M2_report_integration.md` | Wires the short header line + the detailed `## Reflection` section into the real predeadline markdown/JSON report, gated by M1. |
| M3 | `M3_charts.md` | Adds the two Mermaid charts to the detailed section (predicted-vs-actual calibration trend, transfer payoff trend). |
| M4 | `M4_learning_ledger_and_adjustments.md` | Cross-GW calibration ledger + bounded, sample-gated, backtested (still proposal-only) adjustment suggestions. |
| M5 | `M5_transfer_pertinence_review.md` | "How did that transfer age?" multi-week attribution per locked transfer thesis, closed only at its original horizon. |
| M6 | `M6_final_integration.md` | Full test pass, docs/README updated to match reality, run-log style note. |

## Definition of "done" for each milestone

Same bar as the original prompt pack:

1. a concise change summary;
2. files added or changed;
3. tests run, with results (`uv run pytest`, plus the specific new test files);
4. unresolved assumptions or risks;
5. an explicit pass/fail statement against that milestone's acceptance criteria.

Do not move to the next milestone file when a required acceptance check is failing.
