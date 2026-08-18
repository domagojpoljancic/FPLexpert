# Price-change prediction (prices-v1.0.0)

Uncalibrated, deterministic heuristic. It does **not** claim to match FPL’s unpublished threshold. Bands only — never a percentage chance. A predicted rise/fall is **not** a transfer recommendation.

## What FPL gives us

Official public `bootstrap-static` `elements` fields used when present:

- `id`, `now_cost` (tenths of £1m)
- `cost_change_event`, `cost_change_event_fall`
- `transfers_in_event`, `transfers_out_event`
- `selected_by_percent` (string or number)
- `status`, `news`, `chance_of_playing_next_round`

There is **no** official “% to next rise” endpoint. If a field is missing, that input is `unavailable`; we do not invent it.

Prediction quality comes from **deltas between our snapshots** of those public fields, stored under `data/snapshots/prices/{season}/gw-{NN}/`.

## Overnight window (assumption)

Recorded as `unverified` / `observed_undocumented` unless an official timestamp appears:

- Prices often move in a **nightly** UK window. FPL does not advertise the minute.
- GitHub cron cannot be assumed to hit that window.
- Transfer counters may lag, reset at event boundaries, or jump.

Reports speak in **likelihood bands for the next expected window**, never “will rise at 01:32”. Wall-clock “tonight / this morning” uses `manager.timezone` (default `Europe/Zagreb`); storage is UTC.

## Player universe (alerts)

Score for alerts:

1. Owned squad
2. Planned transfer in/out ids from the latest strategy/pre-deadline artifact
3. Optional `watchlist_player_ids` on private state

`--universe catalog` may score everyone for evaluation and **must not notify**.

## Constants (model version bump if changed)

| Key | v1.0.0 value | Role |
| --- | --- | --- |
| `rise_base_net` | 40000 | Net in-event transfers for progress=1.0 at 0% ownership (rises) |
| `fall_base_net` | 50000 | Same for falls (slightly harder) |
| `ownership_scale_k` | 3.0 | `threshold = base * (1 + k * ownership_pct/100)` |
| `watch_progress` | 0.55 | Below → `unlikely` |
| `likely_progress` | 0.85 | At/above + non-reversing velocity → `likely_next_window` |
| `hysteresis` | 0.05 | Avoids flip-flopping bands |
| `min_snapshots_for_likely` | 2 | One snapshot cannot emit `likely_next_window` |
| `event_early_cap` | `watch` | First 24h of an event unless progress ≥ 0.95 with ≥2 snapshots |

Missing ownership → do not emit `likely_next_window` (cap `watch`); warn `ownership_missing`.

Missing `transfers_in_event` / `transfers_out_event` → predictor `unavailable` for that player; no crash.

## Progress and bands

```
net = transfers_in_event - transfers_out_event
threshold = base(direction) * (1 + ownership_scale_k * ownership_pct/100)
progress = min(1.0, abs(net) / threshold)   # null if net/threshold unavailable
```

Direction: `rise` if net>0, `fall` if net<0, `none` if net==0.

Velocity = Δnet / hours between the last two snapshots (`retrieved_at`). If velocity strongly reverses vs overall net (opposite sign and |Δnet| > 20% of |net|), **downgrade one band** and warn `velocity_reversed`.

Hysteresis: leaving `likely_next_window` requires progress < `likely_progress - hysteresis`.

`already_moved`: `now_cost` changed vs previous snapshot, or `cost_change_event` increased in that direction since the previous snapshot. Do not also emit `likely_next_window` for a second tick unless new net/velocity independently supports it.

Stale public data (`retrieved_at` older than `freshness.public_fpl_max_age_minutes`): cannot emit `likely_next_window`.

## Smart-to-act (the product)

Counterfactual `now_cost` ±1 and ±2 tenths are labeled `counterfactual` and **never** written as observed prices. Selling proceeds use `rules.selling_price_tenths`. Affordability uses `rules.budget_after_transfers`.

Action classes (first matching **ignore** rule wins; `act_now_recommended` requires every listed condition):

| Class | Meaning |
| --- | --- |
| `ignore` | No ping. Includes: not in plan; owned rise with no planned sell (team-value vanity); hit-only-for-price; long-term hold |
| `watch` | Interesting but do not spend a transfer solely for £0.1m |
| `act_now_conditional` | Planned affordability/sell-value at risk, but a condition is missing (stale state, last FT protected, weak band) |
| `act_now_recommended` | Fresh data, executable state, legal plan already +EV vs roll **or** already chosen, material £ change, not injured **buy**, outside safety floor |

Price timing may only **bring forward** a football move the strategy already supports, or **block delay** when waiting loses the move. It must not recommend a transfer merely because the price job ran.

With sell-on fee 0.5, a +0.1 rise often **does not** increase selling price; a +0.2 rise often does. Encode that with `selling_price_tenths`, do not hand-wave.

## Cadence (this repo)

- **Daily** (`fpl-agent daily` / `fpl-agent prices`): snapshot + predict + smart-to-act. **No** OpenAI, **no** web/Reddit search.
- **Pre-deadline** (`fpl-agent predeadline`): full injury/news/lineup/transfer review, about **one day before** the official GW deadline. May use OpenAI if `OPENAI_API_KEY` is set. Consumes price actions as structured evidence and must not invent likelihoods.

Recommended local windows (manager tz), not guarantees:

- GitHub Actions: 21:00 Europe/Zagreb in summer (`0 19 * * *` UTC). Persist snapshots in git. Email via GitHub Issue on act-now only. Run log: Actions Summary + `run-log.md` at repo root.
- Evening: after transfer activity, before the uncertain overnight window (e.g. 21:30–23:30 Europe/Zagreb)
- Morning: confirm `now_cost` vs last night’s predictions
- ~24h before deadline: full pre-deadline check (you start this from Cursor on your phone)

GitHub cron is **not** claimed to beat FPL’s overnight job.

## Outcomes

When a later snapshot shows `now_cost` moved, append a `PriceOutcome` (predicted band/direction vs actual delta). **Do not** auto-tune thresholds in this version.

## Explicitly not used

- Scraping Fantasy Football Hub or any third-party HTML/JS predictor
- LLM-estimated likelihood or action class
- Ownership as a reason to churn a hold for team value
