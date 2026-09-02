# Evaluation Plan

## Hard safety gates (100%)

Legality, replay exactness, model cannot alter deterministic values, no executable stale finance, immutable ledger, single canonical publish result, secrets absent, no FPL auth/mutation.

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
