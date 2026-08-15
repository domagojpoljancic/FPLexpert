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

## Preseason variant (`preseason-v1`)

Before a season starts there is no current-season form, so `projections/preseason.py`
uses different inputs:

1. Points per 90 from last season's `total_points / (minutes / 90)`, shrunk toward a
   price-based prior with strength 12 nineties.
2. Start probability from last season's `starts / 38`, shrunk toward a price prior;
   goalkeepers are treated as near-binary (clear number one vs backup).
3. Fixture difficulty from each fixture's `team_h_difficulty` / `team_a_difficulty`,
   applied separately to attacking and defensive point shares by position.
4. Home/away multipliers of 1.05 / 0.95.
5. FPL's published `ep_next` blended into gameweek 1 only, at weight 0.35.
6. Availability from `status` and `chance_of_playing_next_round`.

Blank and double gameweeks fall out of the fixture list naturally, since each
fixture contributes its own term.

### Known limitations

Premium attackers are systematically compressed: the model has no explicit
penalty-taker, set-piece, or shot-quality term, so it tends to prefer mid-priced
value over £13m+ forwards. Treat "premium not selected" as a model property to
challenge, not as proven advice.

## Validation status

- Implemented and deterministic.
- Empirically **unvalidated** until leakage-free holdout backtests land with adequate sample size.
- Intervals are **uncalibrated**.
