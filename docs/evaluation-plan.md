# Evaluation Plan

## Hard safety gates (100%)

Legality, replay exactness, model cannot alter deterministic values, no executable stale finance, immutable ledger, single canonical publish result, secrets absent, no FPL auth/mutation.

## Projection evidence

Compare MAE/bias vs naive baselines on leakage-free holdout before claiming decision value. Thresholds recorded before final eval. Currently: **unproven**.

## Release stages

| Stage | Status |
| --- | --- |
| Private offline pilot | Provisional — core gates tested in unit/integration |
| Scheduled dry-run | Price snapshots scheduled; Issue email on act-now. Watchdog ping TBD |
| Full-season unattended | Prices on GitHub cron (may skip). Pre-deadline is manual. External ping not configured yet |

## Ownership

Repository owner maintains gates; do not weaken a gate to go green.
