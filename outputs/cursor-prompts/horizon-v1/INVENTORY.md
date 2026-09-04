# horizon-v1 M0 — Inventory (what is already computed)

Read-only gate for M1–M4. Sources: `src/fpl_agent/**` + latest report JSON `reports/predeadline-gw3-20260904T163607Z.json`.

**Locked primary note:** `select_primary_move` is specified under `outputs/cursor-prompts/stability-v1/` but is **not yet in product code**. The live locked headline transfer is `weekly_plan.best_affordable` (fed by `this_week_upgrade` / report-honesty snap to that pick). Horizon-v1 must read **that** IN/OUT and must not invent a second ranking authority.

| Manager question | Value already computed? (`file:line`) | In JSON report? (field) | In markdown report? | Verdict: surface / explain / build |
| --- | --- | --- | --- | --- |
| Effect on next N GWs (OUT vs IN) | Yes — XI hold vs after per GW: `horizon_transfer_impact` `transfers.py:734–766`; this-GW OUT/IN pts on candidate `out_xp_next`/`in_xp_next` (`TransferCandidate` ~153–155). Per-player `xp_by_gw` exists on projections at runtime but is **not** persisted as OUT vs IN series. | Yes — `weekly_plan.horizon_impact.by_gw[]` (`hold_xi_xp`, `after_xi_xp`, `delta_xp`), `weighted_delta`, `reason`; also `best_affordable.delta_weighted_xp` / `delta_gw_xp` | Partially — “Transfer vs hold (XI pts)” + “Future weeks” (`daily.py` `_weekly_plan_section` ~1256–1265); no chart | **explain** (visualize XI hold→after from existing `horizon_impact`; do not rebuild ranking) |
| Effect on DGW/BGW in horizon | Confirmed from fixtures feed: `fixture_counts_by_club_gw` / `summarize_gameweek` / `calendar_for_horizon` `fixtures_calendar.py:19–70`; used inside `recommend_chips` (`chips.py:64–66`) then discarded. **No** labelled priors beyond the feed. | No calendar / DGW fields on `weekly_plan` | No (chip copy may say “DGW detection pending”) | **surface** confirmed calendar onto report + plan doc; **build** only for labelled **priors** beyond the feed (M4b) |
| Skip now → bank 2/3 FTs later | Partially — `compare_roll_vs_transfer` `transfers.py:834–921` uses flat `FT_BANK_OPTION_VALUE` (0.35) as banking cost; `deferred_double_transfer_upside` `transfers.py:769–803` compares best no-hit dual vs single and can force roll when upside dominates. Not a full “0 this week → 2 FT next week” sequence EV. | Yes — `weekly_plan.transfer_decision` (`action`, `reason`, `free_transfers_*`, `horizon_delta`, `ft_banking_penalty`, `net_value_after_ft_penalty`, `deferred_upside`, `min_horizon_to_spend`) | Partially — “FT timing (…)” reason line (`daily.py` ~1266–1271) | **surface/explain** existing decision fields in plan doc; **build** true act-now vs roll-to-2 sequence EV to replace reliance on flat option value (M4a) |
| Effect on bank | Yes — `bank_after_tenths` on `TransferCandidate` / plans (`transfers.py:144`, `194`, set ~529–583) | Yes — `best_affordable.bank_after_tenths` (and plan payloads) | Buried inside transfer reason (“Bank left: £…”) — no dedicated bank-after / FT-after line | **surface** |
| Effect on team value / future affordability | Partial — `sell_tenths` / `buy_tenths` / `bank_after_tenths` on the pick; selling via `selling_price_tenths` (`rules/engine.py:107`). Price watch has `sell_value_at_risk` on `price_actions`. No multi-GW team-value path (would invent price rises). | Yes — sell/buy/bank on `best_affordable`; price actions separate | Bank left in reason only; no affordability runway chart | **surface/explain** sell→buy→bank-after for the locked pick (no invented TV trajectory) |
| When to play each chip | Yes — this-week play/hold: `recommend_chips` `chips.py:43–97` (+ use-or-lose near GW19). Not a season chip optimiser. | Yes — `weekly_plan.chips[]` (`kind`, `action`, `available`, `reason`, `metric`) | Minimal — “Chips: hold” or play list (`daily.py` ~1246–1251); fuller reasons in Do-this hold move | **surface/explain** per-chip reasons + window notes (no new chip optimiser) |

## Verdict summary (binds M1–M4)

| Verdict | Items |
| --- | --- |
| **surface / explain** (M1–M2) | Horizon XI impact chart + prose; bank-after / FT-after; sell/buy/affordability of locked pick; chip reasons; confirmed DGW/BGW calendar strip from feed |
| **build** (M4 only) | **M4a** — sequence EV for act-now vs bank-to-2-FT (replace flat `FT_BANK_OPTION_VALUE` as the sole banking cost). **M4b** — labelled DGW/BGW **priors** beyond fixtures feed (confidence; never as confirmed). |

Do **not** build: longer horizon, chip auto-play, second ranking authority, invented fixtures/prices/IDs, or per-player OUT/IN `xp_by_gw` series not already on the report (chart XI hold vs after instead).
