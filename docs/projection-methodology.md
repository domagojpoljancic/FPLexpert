# Projection Methodology (baseline-v1)

## Units

- Prices: integer tenths of £1m.
- Minutes: float minutes.
- Points: FPL points (float internally; round only for display).
- Probabilities: [0,1], with `p_start + p_sub + p_none = 1`.

## Sources

- Public FPL history fields (minutes, points) when available.
- Team attack/defence proxies from recent scoring/conceding rates (v1 placeholders).
- Availability overrides from validated evidence scenarios (never raw web text).
- Defensive-contribution potential from SeasonRules thresholds × estimated contribution rate.

## Method (implemented)

1. Shrink recent minutes toward position prior (`k=5`).
2. Map expected minutes to start/sub/none probabilities.
3. Form from shrunk recent points × home/away × matchup multipliers.
4. Scale by expected minutes/90 and fixture count (0 for blanks, 2+ for doubles).
5. Add expected defensive-contribution points without double-counting official historic totals in replay.
6. Emit uncalibrated lower/central/upper as ±35% around central.

## Explicitly not used in base xP

- Ownership / EO.

## Preseason / in-season variant (`xp-v2`)

`projections/preseason.py` is used for both preseason and the live pre-deadline path.

**Preseason** (`finished` events = 0):

1. Points per 90 from `total_points / (minutes / 90)`, shrunk toward a price-based prior
   with strength 12 nineties.
2. Start probability from `starts / 38`, shrunk toward a price prior; goalkeepers are
   near-binary (clear number one vs backup).
3. Fixture difficulty from each fixture's `team_h_difficulty` / `team_a_difficulty`.
4. Home/away multipliers of 1.05 / 0.95.
5. FPL `ep_next` blended into the next gameweek at weight 0.35.
6. Availability from `status` and `chance_of_playing_next_round`.
7. **DEFCON (optional, `projections.enable_defcon`):** expected +2 when positional CBIT/CBIRT threshold is likely hit; prior-only when minutes are thin (`defcon_prior_only` warning). Capped at +2/match.

**In-season** (`finished` events ≥ 1):

1. Start probability uses `starts / finished_gameweeks`, not `/ 38`. A GK who started
   every finished GW is 0.95; a GK with 0 minutes after two GWs is treated as a backup.
   Outfielders with 0 minutes after two GWs are capped at 0.10.
2. xG/xA from bootstrap shift pp90 toward underlying chance (capped), so finishing
   droughts are not treated as true skill. `penalties_order == 1` adds a small prior
   when minutes are missing.
3. `ep_next` blend weight is 0.45.

Blank and double gameweeks fall out of the fixture list naturally.

### Known limitations

Premium attackers can still be compressed versus a full Poisson/xG chain. Treat
"premium not selected" as a model property to challenge, not as proven advice.
Ownership is still unused in base xP.

## Validation status

- Implemented and deterministic.
- Empirically validated on the checked-in `holdout_min` fixture only (`n=4`); **xp-v2.1 does not beat `ep_next` on that sample** — DEFCON term is **gated off** (`projections.enable_defcon: false`) until a larger holdout shows improvement.
- Intervals are **uncalibrated**.
