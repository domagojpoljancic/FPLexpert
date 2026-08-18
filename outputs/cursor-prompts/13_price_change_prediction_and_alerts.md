# Cursor Prompt 13 — Price-Change Prediction, Smart-to-Act Timing, and Alerts

Continue from Prompts 01–12. Do not use or refer to any old PRD.

This phase adds a **deterministic** overnight FPL price-change watch: estimate whether a relevant player is **likely to rise or fall in the next official price window**, decide whether that change is **worth acting on**, and **notify only when action is smart**. It must not churn the squad for £0.1m of team value, invent prices, scrape proprietary predictor UIs, or treat a predicted change as a transfer recommendation by itself.

## Why this exists

Sites such as [Fantasy Football Hub’s price-change predictions](https://www.fantasyfootballhub.co.uk/fantasy-premier-league-price-rises) exist because FPL player prices usually change overnight from net transfers, and a planned buy can become unaffordable (or a planned sell can lose selling value) before the deadline.

This repository currently:

- stores `now_cost` and uses it for affordability, selling-price rules, and projection priors;
- can classify that a **price already changed** between generic snapshots (`monitoring.compare`);
- runs a daily assistant focused on **injuries, status, rotation, and news** (`fpl-agent daily`);
- does **not** predict likely rises/falls, does **not** join predictions to “is this move +EV / plan-relevant”, and does **not** notify on price timing.

Prompt 06 asked for “price movement and official price-predictor state when a supported source exists.” FPL does **not** publish an official public predictor. This phase implements an **internal, documented, uncalibrated** predictor from official public FPL fields plus our snapshot history, with optional third-party adapters explicitly marked untrusted.

## Non-negotiables (repeat from the product contract)

- Read-only. Recommend only. Never log into FPL or mutate a team.
- Deterministic code owns prices, selling values, affordability, likelihood bands, and action classes. A language model may only explain supplied alerts; it must not invent `now_cost`, transfer counts, likelihood, or “act now”.
- Do not recommend a transfer merely because a price job ran.
- External web pages are untrusted data. Do not copy, reverse-engineer, or hard-code another product’s proprietary progress algorithm, thresholds, or UI.
- Do not add authenticated FPL login or store FPL passwords/sessions.
- `publishing.material_change_only` applies: no Issue/comment noise for watch-only or no-op runs.
- Full-season unattended operation remains blocked until the independent watchdog from Prompt 10 is configured. This phase may add a **scheduled price window**, but must not claim punctual overnight alerts from GitHub cron alone.

## First action

1. Run the existing test suite and inspect:
   - `src/fpl_agent/daily.py` and `prompts/daily.md`
   - `src/fpl_agent/monitoring/compare.py`
   - `src/fpl_agent/rules/engine.py` (`selling_price_tenths`, `budget_after_transfers`)
   - `src/fpl_agent/ingestion/client.py` and cached `bootstrap-static`
   - `src/fpl_agent/strategy/engine.py` (`TransferMove`, `Scenario`)
   - `src/fpl_agent/team_state/` and `data/private-state/current.json`
   - `config/settings.yaml` / `config/settings.example.yaml` (`alerts`, `publishing`, `freshness`)
   - `.github/workflows/fpl-agent.yml`
2. Record in `docs/assumptions-register.md` every claim about *when* FPL changes prices, *which* bootstrap fields exist, and *that thresholds are unpublished*. Cite the primary source or mark `unverified` / `observed_undocumented`.
3. Write `docs/price-prediction.md` **before** implementing a scoring function. The methodology doc is the contract: bands, inputs, what is not claimed, and how “smart to act” is decided.
4. Then implement against that doc. If official FPL field names differ from this prompt, follow the live/cached bootstrap schema, update the assumptions register, and do not invent fields.

Stop and ask for approval if you discover that implementing this requires FPL authentication, scraping a third-party HTML app, or replacing selling-price rules with model output.

## Product outcome

After this phase, a manager with a locked squad can run (locally, and later on a schedule):

```bash
uv run fpl-agent prices
uv run fpl-agent daily
```

and get:

1. **Predictions** for a bounded player universe (squad + transfer targets + optional watchlist), not the entire 700-player catalog as alerts.
2. **Action class** per alert: `ignore` | `watch` | `act_now_conditional` | `act_now_recommended`.
3. A human report that answers: *who might move, which direction, how confident, whether to do anything tonight, and why*.
4. A notification **only** for `act_now_*` (and for a predicted change that would **invalidate a recorded plan’s affordability**), deduplicated per gameweek/player/direction.
5. A morning/post-window **outcome check**: did `now_cost` actually move as predicted? Logged for later calibration. Never auto-tune thresholds in this phase.

The daily assistant must consume these alerts as structured evidence. It must not search the web for “price rises” as a substitute for this module.

---

## Part A — Domain: what FPL actually gives us

### Official public fields (bootstrap `elements`)

Use only fields present in `bootstrap-static` (and, if already fetched, element summary). Typical 2026/27 public fields relevant here — **verify against cache/live schema**:

- `id`, `now_cost` (tenths)
- `cost_change_event`, `cost_change_event_fall`
- `cost_change_start`, `cost_change_start_fall`
- `transfers_in`, `transfers_out`
- `transfers_in_event`, `transfers_out_event`
- `selected_by_percent` (string percent; parse safely)
- `status`, `news`, `chance_of_playing_next_round` (for “don’t buy a rising injured player”)

If a field is missing, degrade: mark predictor `unavailable` for that input, do not guess.

There is **no** official FPL endpoint that returns “% to next rise”. Do not pretend one exists.

### Snapshot history is the real signal

A single `transfers_in_event` total is weak. Prediction quality comes from **deltas between our own snapshots** over the current event.

Implement a durable, content-addressed (or timestamped) **price snapshot store**, for example:

```text
data/snapshots/prices/{season}/gw-{NN}/{utc_timestamp}.json
data/snapshots/prices/{season}/gw-{NN}/latest.json
```

Each snapshot must include:

- `retrieved_at` (UTC)
- `event_id` / gameweek
- `schema_version`, `adapter_version`, content hash
- per-player: `player_id`, `now_cost`, `transfers_in_event`, `transfers_out_event`, `selected_by_percent`, `cost_change_event`, `status`

Reuse ingestion: whenever public bootstrap is fetched successfully, **also** append a price snapshot (bounded size). Offline mode must read frozen snapshots only.

Retention: keep at least 48 hours of snapshots for the current GW, plus the last snapshot of the previous GW. Cap files so the repo cannot grow without bound (configurable max snapshots per GW; older files may be gitignored if they contain nothing private — these are public FPL stats).

Do not commit secrets. Public transfer counts are not private; still redact manager-specific watchlist material from published Issue bodies if the user configured a private watchlist.

### Typical overnight window (assumption, not a guarantee)

Record as `unverified` / `observed_undocumented` unless you find a current official statement:

- FPL price changes usually occur in a **nightly window** (historically around 01:30–02:30 UK), not at an API-advertised timestamp.
- GitHub cron cannot be assumed to hit that window.
- Transfer counters may lag, reset around event boundaries, or jump.

The product must speak in **likelihood bands for the next expected window**, never “will rise at 01:32”.

Manager timezone is already configured (`manager.timezone`, currently `Europe/Zagreb`). Schedule suggestions and report copy must use that timezone for “tonight / this morning”, while storing UTC.

---

## Part B — Predictor (deterministic, uncalibrated)

Create a package such as `src/fpl_agent/prices/` with:

- `snapshot.py` — append/load snapshots
- `model.py` — score players
- `actions.py` — smart-to-act policy
- `alerts.py` — materiality, fingerprints, report payload
- `README.md` — module boundary

### Player universe

Score only:

1. **Owned**: private squad `player_ids`.
2. **Plan targets**: `in_id` / `out_id` from the latest strategy scenarios for this GW (if an analysis artifact exists); plus `suggested_moves.player_ids` from the latest daily report if present.
3. **Watchlist**: optional `watchlist_player_ids` on private team state (default empty). Validate IDs against the catalog.

Never emit hundreds of “Haaland might rise” rows for players with no relationship to this manager.

A separate **diagnostic** mode (`--universe catalog`, default off) may score everyone for evaluation, but must not notify.

### Output contract (typed, extra=forbid)

Each `PricePrediction` must include at least:

- `player_id`, `web_name` (from catalog; do not invent)
- `now_cost_tenths`
- `direction`: `rise` | `fall` | `none`
- `likelihood`: `unlikely` | `watch` | `likely_next_window` | `already_moved`
- `progress_uncalibrated`: float in `[0, 1]` **or null** if insufficient snapshots
- `net_transfers_event`: `transfers_in_event - transfers_out_event`
- `net_transfers_since_prev_snapshot` (may be null)
- `snapshot_count_used`
- `model_version`
- `as_of`
- `warnings` (stale data, GW1/preseason, missing history, status flag, event just started)
- `provenance`: source = `fpl_public_snapshot` (and optional adapter id)

`already_moved` means `now_cost` changed vs the previous snapshot or `cost_change_event` increased in the expected direction **today**. Do not also scream “likely to rise” for a player who just rose unless a **second** rise is independently supported.

### Scoring rules (v1 heuristic — document every constant)

FPL’s exact threshold function is unpublished. v1 must be **transparent and conservative**:

1. Require at least **two** snapshots in the current event, or one snapshot plus non-zero `transfers_*_event` with an explicit `single_snapshot_weak` warning and cap likelihood at `watch`.
2. Compute net transfers and recent velocity (net per hour between last two snapshots, using `retrieved_at`).
3. Scale a **placeholder threshold** by ownership. Example shape (constants belong in settings + methodology doc, not magic numbers in three files):

   - higher `selected_by_percent` → larger net-transfer volume needed;
   - rises and falls may use different constants;
   - never claim these match FPL.

4. Map progress to bands with hysteresis (avoid flip-flopping `watch`/`likely` every run):

   - `unlikely`: progress below `watch_threshold`
   - `watch`: between watch and likely
   - `likely_next_window`: at/above `likely_threshold` **and** velocity not reversing
   - If velocity reversed strongly, downgrade one band and warn

5. If public data is older than `freshness.public_fpl_max_age_minutes`, do not emit `likely_next_window`. Downgrade and warn `stale_public_data`.
6. Preseason / GW1 / first 24h of an event: default to `watch` max unless evidence is overwhelming; warn `event_early`.
7. Injured/suspended/unavailable (`status` in `i,s,u,n` or chance 0): still predict price (dead money is transferred) but the **action policy** must refuse “buy before rise”.

**Forbidden:** fake precision (“87% chance of a rise”). Bands + uncalibrated progress only until a later evaluation phase proves calibration.

**Forbidden:** LLM-estimated likelihood.

### Optional third-party adapter (off by default)

Config may later allow a **read-only JSON** source the user operates (for example a self-hosted export). Requirements:

- disabled by default;
- HTTPS only, size-limited, schema-validated;
- labeled `community` / untrusted;
- **cannot** override `now_cost` or selling prices;
- may only attach `external_progress` as an extra field;
- if it disagrees with the internal band, keep both and prefer **inaction** (do not escalate to `act_now_recommended` solely on the external source);
- do **not** scrape `fantasyfootballhub.co.uk` or similar HTML/JS apps in this phase.

If no such source is configured, do not mention Hub (or any vendor) in user-facing reports as if it were consulted.

---

## Part C — Smart-to-act policy (this is the feature)

A predicted rise/fall is **not** a recommendation. `actions.py` must join predictions to finance, plan, and opportunity cost.

### Inputs

- Predictions for the universe
- Resolved team state: squad, bank, free transfers, purchase prices, current prices, selling prices, chips, executability
- Season rules (`selling_price_tenths`, hit cost, FT rollover)
- Latest **roll** vs **best legal transfer scenario(s)** if already computed this run; if not, compute a **bounded** reuse of the existing strategy engine (do not invent a second optimiser)
- Current GW deadline from bootstrap events
- `alerts` / new `prices` settings (below)

### Simulations (deterministic)

For each relevant player, simulate **hypothetical** `now_cost` shifts of `±1` tenth and `±2` tenths **without** writing them into the catalog:

- **Owned player fall:** new selling price vs current selling price. Flag `sell_value_at_risk` if selling price would drop.
- **Owned player rise:** new selling price vs current. Flag `wait_for_rise` only if the manager already has a **planned sell** of that player *and* selling price would increase (remember: with sell-on fee 0.5, a +0.1 rise often does **not** increase selling price; a +0.2 rise often does). Use `selling_price_tenths`; do not hand-wave.
- **Unowned target rise:** re-run `budget_after_transfers` for the planned buy (or cheapest legal plan containing that `in_id`). Flag `affordability_risk` if the plan becomes illegal/unaffordable, or bank-after falls below a configured floor (default 0).
- **Unowned target fall:** usually `ignore` (cheaper later). Do not ping.

Hypothetical prices must be labeled `counterfactual`. They must never be stored as observed `now_cost`.

### Action class rules

Apply in order. First match wins. Encode as data-driven tests.

**`ignore`** when any of:

- likelihood is `unlikely` or `none`;
- player is owned, likely to **rise**, and is **not** a planned sell (team-value gain is not an action);
- player is unowned, likely to **rise** or **fall**, and is **not** in plan targets / watchlist;
- player is owned, likely to **fall**, and is a **long-term hold** (not a planned sell this GW or next, and no replacement scenario beats roll after the fall);
- the only benefit is +0.1 team value with no points plan attached;
- a hit would be required **solely** to beat a price change, and `prices.allow_hit_for_price` is false (default **false**);
- this would spend the **last** free transfer **solely** for price, and `prices.allow_last_ft_for_price` is false (default **false**);
- deadline is inside `alerts.safety_floor_minutes` (too late to trust/act in-app; warn instead);
- team state is not `EXECUTABLE` — then the maximum class is `act_now_conditional` (never `act_now_recommended`).

**`watch`** when:

- likelihood is `watch` or `likely_next_window`, but policy forbids acting (last FT, hold, not in plan, weak snapshots);
- owned + likely fall + unclear whether they will be sold this horizon;
- predicted rise on a target that remains affordable even after +0.1 (no urgency).

**`act_now_conditional`** when:

- `affordability_risk` or `sell_value_at_risk` is true for a **planned** move, but team state is stale/incomplete, or the transfer is not yet legal, or evidence is only `watch` band, or OpenAI/strategy did not confirm the underlying football move;
- report must list the missing condition (“sync bank/FT”, “confirm you still want X → Y”).

**`act_now_recommended`** only when **all** are true:

1. likelihood is `likely_next_window` (not merely `watch`);
2. public data is fresh;
3. team state is `EXECUTABLE`;
4. the underlying transfer (or explicit wait/sell) is already a **legal** candidate vs roll, **or** is the already-chosen plan for this GW;
5. the price move would **materially** change affordability or selling proceeds (at least `alerts.material_change_price_tenths`, default 1 tenth of **selling price or buy cost**, not vanity TV);
6. acting does not require a hit unless that hit is already justified by the strategy gain vs roll (price is not the sole reason);
7. the player is not unavailable for a **buy**;
8. we are outside the safety floor and not so far before the deadline that burning a FT is obviously dominated by waiting (configurable: if `hours_to_deadline` > `prices.max_hours_ahead_to_spend_ft`, cap at `watch` unless affordability_risk is already true at **current** prices too).

If the planned football transfer is **not** +EV vs roll, **do not** recommend doing it early just to bank 0.1m. Price timing may only **bring forward** a move the strategy already supports, or **block delay** when waiting loses the move.

### Copy / explanation fields (deterministic)

Each `PriceAction` must have:

- `action_class`
- `move_type`: `none` | `buy_before_rise` | `sell_before_fall` | `wait_for_rise_then_sell` | `hold`
- `summary` (short, no invented points)
- `rationale_codes` (stable enums, e.g. `affordability_risk`, `sell_value_at_risk`, `not_in_plan`, `last_ft_protected`, `hit_not_justified`, `long_term_hold`, `counterfactual_plus_one_still_affordable`)
- `player_ids`
- `related_scenario_id` if any
- `valid_until` (next snapshot freshness bound or expected window date — labeled uncertain)

The LLM, if used in `daily`, may rephrase `summary` but must keep `action_class` and codes from this module.

---

## Part D — Daily, monitor, CLI, and reports

### CLI

Add `fpl-agent prices` with flags:

- `--offline`
- `--save/--no-save`
- `--notify/--no-notify` (default: follow publishing settings)
- `--universe squad|plan|watchlist|all-relevant` (default `all-relevant`)

It must print a concise Markdown-like summary and write:

```text
reports/prices-gw{N}-{utc}.md
reports/prices-gw{N}-{utc}.json
```

Exit 0 on successful computation including “nothing to do”. Use existing `ExitCode` values for config/upstream failures. Do not add a new exit code unless truly required.

### Daily integration

Extend `run_daily` payload with `price_predictions` and `price_actions` (already validated objects). Update `prompts/daily.md`:

- You may use supplied price actions.
- You must not invent price likelihoods.
- You must not upgrade `ignore`/`watch` to a transfer.
- You may mention `act_now_*` in `suggested_moves` only if the player IDs are supplied.

Deterministic fallback (no API key) must still surface `act_now_*` from the prices module.

### Monitor integration

Replace the placeholder “price key changed” behaviour with explicit change types:

- `now_cost` change (observed)
- likelihood band change
- action_class escalation to `act_now_*`
- prediction outcome hit/miss after a window

Timestamps alone still must not be material. Identical predictions → heartbeat hash only.

### Report shape

Lead with the decision, not a table of 40 watch names:

1. Status: `NO ACTION` | `WATCH` | `ACT TONIGHT (conditional)` | `ACT TONIGHT`
2. At most a few `act_now_*` bullets (who, direction, what to do in FPL, bank/FT after if executable)
3. Watch list (short)
4. What was ignored and why (collapsed / last)
5. Freshness, snapshot times, model version, uncalibrated disclaimer
6. Sources: FPL bootstrap URL + snapshot hashes — not scraped third parties

Escape Markdown. No secrets. Recommend-only footer.

---

## Part E — Notifications (low noise)

### What may notify

Notify only if `publishing.material_change_only` would consider it material:

- new or escalated `act_now_recommended` or `act_now_conditional`
- observed `now_cost` change that **invalidates** a recorded plan’s affordability
- prediction **miss/hit** is **not** a user notification unless it changes action class (log it)

Do not notify on:

- `ignore`
- `watch` (unless a configured `--verbose-watch` that still does not create GitHub Issues)
- repeated identical fingerprints in the same GW

### Fingerprint

`season | gw | player_id | direction | action_class | related_scenario_id`

Store last-notified fingerprints in canonical publishing state or `data/snapshots/prices/.../notify-state.json` so retries do not spam.

### Channels (this phase)

1. **Always:** CLI stdout + saved report (local).
2. **If** `publishing.issue_publishing` is true and not dry-run: one GitHub Issue comment on the current GW issue (Prompt 09 markers). Do not open a new issue per player.
3. **Optional webhook:** `prices.webhook_url` empty by default. If set, POST a small JSON allowlisted payload (action class, player ids, gw, summary, report hash). Timeouts, no secret echo, HTTPS only.

No SMS/email/push vendors in this phase. Do not require a new SaaS.

### Schedule (do not over-claim)

Document recommended windows in README and `docs/price-prediction.md`:

- **Evening (manager tz):** after typical transfer activity, before the uncertain overnight window — e.g. 21:30–23:30 in `Europe/Zagreb`.
- **Morning:** confirm observed `now_cost` vs last night’s predictions.

You may add a workflow_dispatch mode `prices` and an extra cron **suggestion** in comments or a **disabled** job until watchdog exists. Do not silently enable a noisy Issue publisher. Do not claim the cron will beat FPL’s overnight job.

If you add a schedule, keep it staggered (not top-of-hour), cheap (no OpenAI in the prices preflight), and concurrency-safe with existing workflows.

---

## Part F — Configuration

Extend `config/settings.example.yaml` and `config/settings.yaml` with a validated `prices:` block (Pydantic, env overlay `FPL_PRICES__...`). Suggested defaults:

```yaml
prices:
  enabled: true
  snapshot_max_per_gw: 48
  watch_progress: 0.55
  likely_progress: 0.85
  min_snapshots_for_likely: 2
  hysteresis: 0.05
  allow_hit_for_price: false
  allow_last_ft_for_price: false
  max_hours_ahead_to_spend_ft: 36
  bank_floor_tenths_after: 0
  webhook_url: ""
  external_predictor_url: ""  # disabled unless set
```

Ownership-scaling threshold constants belong here or in a versioned `prices_model` table with `checked_at` in the assumptions register. Changing them is a model-version bump.

Add freshness if needed: `prices_snapshot_max_age_minutes` (can reuse public FPL freshness).

---

## Part G — Evaluation hooks (no auto-learning)

When a later snapshot shows `now_cost` changed:

- append a `PriceOutcome` record: predicted direction/band vs actual delta, hours since prediction, gw, player, ownership band;
- keep it under `data/outcomes/` or the decision-ledger adjacent path;
- do **not** auto-adjust thresholds (Prompt 07: `min_evidence_before_param_change`);
- unit-test the recorder with synthetic before/after snapshots.

This phase does not need a full MAE dashboard. It needs a replayable log so a later prompt can calibrate.

---

## Tests and acceptance criteria

Add unit tests (synthetic bootstrap slices, no network) covering:

**Predictor**

- two snapshots with accelerating net ins → `likely_next_window` rise for a mid-owned player given the documented constants;
- reversing velocity downgrades the band;
- one snapshot cannot emit `likely_next_window`;
- stale public data cannot emit `likely_next_window`;
- `now_cost` already +1 vs previous snapshot → `already_moved`, not a second rise without new evidence;
- missing `transfers_in_event` → unavailable/degraded, no crash;
- universe filter excludes unrelated catalog players from alerts.

**Selling price / affordability**

- owned player, purchase 50, current 52, predicted fall to 51: selling price change matches `selling_price_tenths`;
- owned player, purchase 50, current 50, predicted rise +1: selling price **unchanged** (0.5 retain) → `wait_for_rise_then_sell` is **not** recommended;
- planned buy unaffordable after +1 tenth → `affordability_risk`;
- planned buy still affordable after +1 → not `act_now_recommended`.

**Policy**

- Haaland-like rise, not in plan → `ignore`;
- planned transfer-in about to rise and unaffordable after → `act_now_recommended` if FT available, legal, executable;
- same but only last FT and `allow_last_ft_for_price: false` → `watch` or `act_now_conditional`, never silent `act_now_recommended`;
- hit-only-for-price → not recommended;
- injured target → no `buy_before_rise`;
- non-executable team state → cannot emit `act_now_recommended`;
- identical second run → same fingerprint, notify once.

**Integration**

- `fpl-agent prices --offline` uses fixtures and writes a report;
- `daily` payload includes price actions; fake LLM cannot invent a rise;
- monitor: timestamp-only snapshot is non-material; `now_cost` change is material;
- webhook/Issue paths dry-run by default;
- malicious `news` text cannot change action_class.

**Docs / config**

- `docs/price-prediction.md` exists and matches the code constants;
- assumptions register updated;
- `00_READ_ME_FIRST.md` lists this prompt;
- README status table: prices predictor **working (uncalibrated)**; notifications **local report + optional Issue**; Hub scrape **not used**;
- traceability matrix row added.

This phase is accepted only when:

1. No third-party HTML scrape exists in the tree.
2. Likelihood is never model-invented.
3. `act_now_recommended` cannot fire solely because a daily/price job ran or because team value might tick up on a hold.
4. Selling-price and affordability counterfactuals use `rules` code.
5. Tests above pass.
6. Offline CLI path works without `OPENAI_API_KEY`.

Finish with the standard checkpoint (change summary, files, tests, assumptions, pass/fail) and stop. Do not start Prompt 10-style unattended claims, and do not “calibrate” thresholds from a handful of players.
