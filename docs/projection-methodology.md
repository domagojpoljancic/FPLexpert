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

## Validation status

- Implemented and deterministic.
- Empirically **unvalidated** until leakage-free holdout backtests land with adequate sample size.
- Intervals are **uncalibrated**.
