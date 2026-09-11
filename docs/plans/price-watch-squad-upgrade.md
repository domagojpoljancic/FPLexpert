# Build plan: price-watch squad-relative upgrade check

Hand this file to an Auto-model agent. Implement everything below in one go, then merge to `main`. Do not leave an open PR.

You are working in the `FPLexpert` repo. Work on a feature branch, keep the overnight job resilient, and follow the repo's pre-push hygiene and test-coverage rules.

## Background / problem

The `fpl-agent prices` report's "Should you transfer?" section only lists unowned likely risers ("Likely rises not in your squad (…): interesting for who may tick up"). It never compares a riser to the players I own. The useful question is: **is a riser an upgrade on someone in my squad (now or as a future-planning target), and is it affordable?** The repo already has the machinery: `strategy/transfers.py:rank_transfer_candidates()` computes same-position swaps (ΔxP this GW, ΔxP over the horizon, affordability, who drops from the XI) from `projections/preseason.py:project_all()`. The price job just doesn't call it. Wire it in.

## Goal

For each unowned riser in the price watch, show which of my players it would replace, the projected-points delta this GW and over the horizon, and whether it's affordable — so I can decide whether to buy before the rise (including for future plans). Fall back to the current generic wording only when projections can't be computed. Keep all existing guardrails.

## Files to change

- `src/fpl_agent/prices/run.py` — compute projections and squad-relative swap evaluations; pass into the report.
- `src/fpl_agent/prices/transfer_check.py` — **new** pure module producing structured "upgrade verdicts". Keep `report.py` formatting-only.
- `src/fpl_agent/prices/report.py` — rewrite `_transfer_advice_lines` and thread the new data through `render_prices_markdown`.
- `tests/unit/test_prices.py` — update wording assertions + add new tests.
- `src/fpl_agent/prices/README.md` and `docs/price-prediction.md` — document the new check.
- `.github/workflows/fpl-prices.yml` — reschedule (see final section).

## Step 1 — Compute projections in the price run

In `run_prices` (`src/fpl_agent/prices/run.py`), `load_public_data` already returns fixtures but they're discarded (`bootstrap, _fixtures = load_public_data(...)`). Capture fixtures. When `bootstrap` is passed in directly (tests), fixtures may be empty/unavailable — handle gracefully.

- `from fpl_agent.projections.preseason import project_all, configure_from_settings`
- `configure_from_settings(settings)` then `projections = project_all(bootstrap=bootstrap, fixtures=fixtures, gameweeks=<[gw, gw+1, …]>, weights=settings.planning.weights)`.
- Build `gameweeks` for `len(settings.planning.weights)` gameweeks; reuse whatever helper pre-deadline uses for the horizon if one exists.
- Guard: if `fixtures` is empty (offline test path / feed down), skip the upgrade check, keep the current generic text, and append a warning code `market_upgrade_check_skipped_no_fixtures`. Never fail the overnight job.

## Step 2 — New module `src/fpl_agent/prices/transfer_check.py`

Pure, deterministic, no LLM, no invented IDs. Given market movers, projections, and the resolved `team` (owned ids, bank, free transfers, purchase prices, rules), return structured verdicts:

- For unowned risers (band `LIKELY_NEXT_WINDOW`, and optionally `WATCH`), find the best same-position swap where the buy is that riser. Prefer calling `rank_transfer_candidates(...)` and filtering to `in_id in {riser ids}`; if its min-delta/dedupe filtering drops a riser you still want to report, compute that single swap directly with the same primitives (`_xi_objective`, `selling_price_tenths`, `budget_after_transfers`, `xi_drop_for_swap`) so numbers match the pre-deadline report.
- Per riser return a small dataclass: `in_id, in_name, cost, out_name, delta_gw_xp, delta_weighted_xp, affordable, bank_shortfall_tenths, is_upgrade` (upgrade = `delta_weighted_xp` clears a small bar; reuse `MIN_WEIGHTED_DELTA`).
- Also handle owned fallers: is there an affordable same-position replacement that's an upgrade/lateral (so a fall is the nudge to move)?

## Step 3 — Rewrite `_transfer_advice_lines` in `report.py`

Thread the Step 2 verdicts through `render_prices_markdown` as a new optional arg defaulting to `None` (so existing callers/tests still work). Produce lines like:

- Upgrade + affordable: `- **Palmer** (£10.5m, likely rise) would upgrade **Saka** (+1.2 pts this GW, +3.4 over the next 4). Affordable now — buying before the rise saves £0.1m. Confirm in the pre-deadline review.`
- Upgrade but short on cash: same, plus `You'd need £2.0m more in the bank (future-planning target, not tonight).`
- Not an upgrade: `- **Elanga** (likely rise): rising, but not an upgrade on your squad right now (best swap −0.3 pts). No reason to buy.`
- Preserve the existing guardrail sentence and `PREDICTOR_HINT` (still point to `predeadline --live-ai`).
- Fallback: if verdicts is `None`, emit today's generic text unchanged.

## Step 4 — Tests (`tests/unit/test_prices.py`)

- Update `test_prices_offline_cli_path` (~line 548) and `test_livefpl_parse_and_market_movers` (~line 638) wording assertions.
- Add `test_market_upgrade_check_flags_squad_replacement`: unowned riser clearly out-projects a same-position squad player → report names the owned player + positive delta / "upgrade" line.
- Add `test_market_upgrade_check_reports_non_upgrade`: riser that doesn't beat the squad → "not an upgrade" line.
- Add `test_market_upgrade_check_degrades_without_fixtures`: no fixtures → generic fallback text + `market_upgrade_check_skipped_no_fixtures` warning, no crash.
- Keep deterministic; reuse existing `_catalog()`/`_private_file()` fixtures and mirror how `project_all` is used in `tests/unit/test_projections_strategy.py`.

## Guardrails to preserve (do not regress)

- Never override official `now_cost`; LiveFPL progress stays untrusted and never alone triggers act-now.
- Never auto-recommend a buy purely for a £0.1m tick — the new line adds a *points* verdict; the pre-deadline review remains where I commit.
- Degrade silently (keep old text) whenever projections/fixtures aren't available.
- No `PricesSettings` model-version bump needed (heuristic constants unchanged); this is report/logic only.

## Step 5 — Reschedule the GitHub Actions price job (3 hours earlier)

In `.github/workflows/fpl-prices.yml`, change the schedule from `cron: "0 16 * * *"` to `cron: "0 13 * * *"` (3 hours earlier, 16:00 → 13:00 UTC). Update the adjacent comment lines so the timezone note stays accurate (13:00 UTC = 15:00 CEST summer / 14:00 Zagreb winter; adjust the "lands before ~21:00 CEST" wording accordingly). Leave `fpl-prices-watchdog.yml` and `fpl-agent.yml` unchanged.

## Finish

- Run `uv run pytest` (at least `tests/unit/test_prices.py` plus the full unit suite) green.
- Refresh `README.md` if any status wording changed; don't stage secrets, private state, JSON reports, or snapshots.
- Commit on a feature branch, push, open a PR targeting `main`, and **merge it into `main`** in the same run (fast-forward `main` locally and `git push origin main` if the merge API is unavailable). Don't leave the PR open.
