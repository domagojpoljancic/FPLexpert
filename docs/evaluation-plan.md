# Evaluation Plan

## Hard safety gates (100%)

Legality, replay exactness, model cannot alter deterministic values, no executable stale finance, immutable ledger, single canonical publish result, secrets absent, no FPL auth/mutation.

## Projection evidence

Compare MAE/bias vs naive baselines on leakage-free holdout before claiming decision value. Thresholds recorded before final eval. Currently: **unproven**.

## Release stages

| Stage | Status |
| --- | --- |
| Private offline pilot | Provisional — core gates tested in unit/integration |
| Scheduled dry-run | Blocked on GitHub secret/config + watchdog |
| Full-season unattended | Blocked pending external liveness monitor |

## Ownership

Repository owner maintains gates; do not weaken a gate to go green.
