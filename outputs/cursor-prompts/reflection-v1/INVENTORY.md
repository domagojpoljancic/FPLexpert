# reflection-v1 M0 — Inventory (what already exists vs what's missing)

Read-only gate for M1–M6. Re-run this inspection before trusting it — code moves fast in this
repo (see `run-log.md` / recent `horizon-v1`, `stability-v1` commits). Sources checked:
`src/fpl_agent/**`, `tests/unit/**`, a real report pair
(`reports/predeadline-gw3-20260904T181140Z.md` + its `.json`), and `docs/evaluation-plan.md`.

## What's already computed (do not rebuild, reuse)

| Capability | Where | Notes |
| --- | --- | --- |
| Official-result finality policy (provisional until 09:00 UK next day + `data_checked`) | `src/fpl_agent/evaluation/finality.py:11-19` (`provisional_until`, `is_final`); policy text also documented at `src/fpl_agent/rules/season.py:143-146` | **Defined but unused** — nothing in the codebase calls `is_final` today. This is exactly the gate M1 needs to wire in. |
| Per-player official GW points from the live feed | `src/fpl_agent/evaluation/scorecard.py:51-63` (`points_from_live_payload`), fetch helper `fetch_live_points` (`scorecard.py:164-173`) | Reuse directly; do not re-implement. |
| Loading the last saved predeadline plan for a GW | `src/fpl_agent/evaluation/scorecard.py:151-162` (`load_latest_predeadline_plan`) | Reads `reports/predeadline-gw{N}-*.json`, picks the most recent with `weekly_plan.ok`. Reuse directly. |
| XI/captain/transfer scorecard for one GW | `src/fpl_agent/evaluation/scorecard.py:65-148` (`scorecard_from_plan`), `build_previous_scorecard:175-188` | Computes `model_xi_points`, captain comparison, transfer OUT/IN delta, `process_quality`/`outcome_quality` via `replay.grade_process_outcome`. **Only reachable via the standalone `fpl-agent scorecard` CLI command** (`cli.py:520-547`) — never wired into the predeadline report, and the CLI command only prints JSON to stdout; it does not save a file (contrast with `prices_scorecard_cmd` at `cli.py:549-577`, which does save `.json`/`.md`). |
| Deterministic replay + process/outcome/root-cause grading | `src/fpl_agent/evaluation/replay.py` — `ProcessQuality`, `OutcomeQuality`, `RootCause` enums (lines 12-36), `grade_process_outcome` (88-118), `build_replay_result` (121-168) | Root-cause enum already matches the closed set specified in `outputs/cursor-prompts/07_decision_ledger_and_retrospectives.md`. Reuse the enum values verbatim. |
| Recorded, non-hindsight alternative transfer candidates | `src/fpl_agent/daily.py:629,684-704` (`weekly_plan["also_considered"]`, built in `apply_transfer_pick_to_weekly_plan`); rendered today at `daily.py:1254-1268` ("Compared with other affordable …") | Each row is a `TransferCandidate.as_payload()` with `in_id`, `in_name`, `out_id`, `out_name`, `picked: bool`, `reason`, plus `xp`/horizon fields. **This is the only legitimate source for "what could've been done better" — never substitute a live re-rank.** |
| Immutable pre-deadline decision record scaffold | `src/fpl_agent/evaluation/ledger.py` (`DecisionRecord`, `write_decision_record` — refuses to overwrite, `ledger.py:44-52`); written every non-skipped run via `daily.py:1427-1459` (`_write_decision_ledger`) | **Thin today**: `rules_hash`, `catalog_hash`, `projection_hash`, `config_hash`, `code_version` are all written as empty strings; `roll={}`; `primary` only carries `{"plan_action": ...}` — not the actual OUT/IN ids, not `also_considered`, not the horizon window. `data/decision-ledger/` on disk is empty except `.gitkeep`, so no real records exist yet from past GW3 runs even though the code path ran. M5 needs this record enriched (see M5). |
| Mermaid chart helpers / style | `src/fpl_agent/reporting/plan_doc.py` — e.g. `_mermaid_horizon_xp`, `_mermaid_timeline` (search for `_mermaid_` in that file); produces `reports/plan-gw{N}.md` via `write_plan_doc`, called from `daily.py:1421-1423` | Reuse the `xychart-beta` / `flowchart` conventions verbatim for visual consistency; do not invent a new chart library. |
| Predeadline report section order | `src/fpl_agent/daily.py:1348-1411` (`render_daily_text`) | Order today: header lines (`Plan:`, `AI:`, optional `Price:`) → `## Do this` → `## This week` (from `_weekly_plan_section`, ~1185-1345) → `## Why` → `## Watch` → `## Sources` → closing disclaimer line. New reflection content slots in after the header lines (short line) and after `## Watch` / before `## Sources` (detailed section) — see M2 for the exact splice points. |
| GW / deadline resolution already available at report-build time | `src/fpl_agent/daily.py:166-167` (`bootstrap, fixtures = load_public_data(...)`; `gw, deadline = next_deadline(bootstrap)`) inside `run_predeadline` | `bootstrap` and `fixtures` are already in scope where the gate needs to run — no extra network round-trip required for M1's gate itself (only the live-points fetch for the actual reflection numbers needs one more call, already provided by `fetch_live_points`). |

## What's missing (build in M1–M6)

| Gap | Verdict |
| --- | --- |
| Nothing gates "is the prior GW actually official/final" before showing any retrospective content. `finality.is_final` exists but is dangling/unused. | **build (M1)** |
| `predeadline_ev_positive`, `recommendation_net`, `roll_net` are **read** by `scorecard.py:117-124` / `replay.py` but are **never set** anywhere in `strategy/plan.py`, `strategy/transfers.py`, or `daily.py` for a real weekly plan (only `cli.py:607` hardcodes `predeadline_ev_positive=True` for its own synthetic `replay` demo). Confirmed by grep — a real saved report today would score `process_quality=insufficient_evidence` if run through `scorecard_from_plan` as-is. | **build (M1)** — derive process quality from fields that *are* populated on a real plan (`weekly_plan.transfer_decision`, `best_affordable.delta_weighted_xp` sign, `after_transfer` presence) rather than depending on the dead fields. Optionally backfill the dead fields too for consistency with the existing `evaluation/replay` machinery, but do not block M1 on that. |
| No reflection content anywhere in the predeadline markdown/JSON report. `## Reflection`-style section does not exist. | **build (M2)** |
| No charts comparing predicted vs actual over time, or transfer payoff over time. | **build (M3)** |
| No cross-GW aggregation of scorecards; no calibration-bias tracking by segment (position/price tier); no adjustment-proposal mechanism; no backtest gate. | **build (M4)** |
| No concept of a transfer "thesis" that stays open across its original multi-GW horizon and closes only when that horizon elapses (or the player leaves the squad) — the decision ledger has no `latest_gw_delta` / `cumulative_horizon_delta` fields described in `07_decision_ledger_and_retrospectives.md` §"Multi-gameweek decisions and lessons". | **build (M5)** |
| `data/decision-ledger/`, `data/evaluation/`, `data/outcomes/` exist as empty directories (`.gitkeep` only) — no real historical records to learn from yet. | Expected — M1 starts populating `data/evaluation/reflection-gw*.json`; M5 starts populating `data/decision-ledger/**` with real content (today's writes are near-empty payloads, see above) and `data/evaluation/transfer-theses.jsonl`. |

## Do not build

- A second ranking authority. Reflection only explains and grades the one locked pick
  (`weekly_plan.best_affordable` / `after_transfer`) and its recorded `also_considered` — it
  never re-ranks with hindsight.
- An auto-applying adjustment mechanism. M4 stops at "proposed" / "backtested_pass" — nothing in
  this plan flips a production weight automatically.
- A rewrite of the immutable decision ledger's overwrite protection (`ledger.py:47-49`). Any
  correction is a new, linked record, exactly as `07_decision_ledger_and_retrospectives.md`
  requires — M5 must respect this.
- Historical backtesting of the *projection ranking itself* against past seasons — that is
  explicitly out of scope per `docs/evaluation-plan.md` ("we do not run historical backtests in
  this repo"). M4's backtest is narrow: it only validates a proposed *calibration* adjustment
  against this app's own accumulated in-season track record, and only ever produces a proposal.
