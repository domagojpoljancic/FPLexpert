# Evaluation Plan

## Hard safety gates (100%)

Legality, replay exactness, model cannot alter deterministic values, no executable stale finance, immutable ledger, single canonical publish result, secrets absent, no FPL auth/mutation.

## Recommendation stability

Deterministic layer (CI): `tests/unit/test_stability.py` — repeated runs on a frozen payload must emit **identical** `primary_move` out/in IDs, captain, and vice (100%). Near-ties inside `PRIMARY_EPSILON_WEIGHTED_XP` must not oscillate. Official-tier veto → consistent alternative; without veto → snap-back to primary.

Live model (opt-in, not CI): set `FPL_LIVE_STABILITY=1`. Target ≥90% identical primary when one scenario has a material deterministic advantage (prompt 11). Snap-back validation is the contract; decoding temperature is not the fix.

Record for live evals: model id, `PROMPT_VERSION` / schema version, repetitions, divergence count, pass/fail.

## Projection evidence

The agent optimises **forward-looking** expected points (xP) for upcoming gameweeks. We do not run historical backtests in this repo — advice is judged on whether the next GW plan is sensible given fixtures, minutes, and your squad, not on replaying past seasons.

After each deadline, use `fpl-agent scorecard` and `fpl-agent replay` to compare what we recommended vs what actually happened (process vs luck), one gameweek at a time.

## Release stages

| Stage | Status |
| --- | --- |
| Private offline pilot | Provisional — core gates tested in unit/integration |
| Scheduled dry-run | Price snapshots scheduled; Issue email on act-now; watchdog comments if last-success > 26h |
| Full-season unattended | Prices on GitHub cron (may skip). Pre-deadline is manual. External ping not configured yet |

## Ownership

Repository owner maintains gates; do not weaken a gate to go green.
