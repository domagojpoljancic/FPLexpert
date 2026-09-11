# Package: prices

Deterministic overnight price-change watch:

- snapshots of official public FPL fields
- uncalibrated rise/fall bands
- smart-to-act policy (ignore / watch / act tonight)
- squad-relative upgrade check for market movers (same-position ΔxP vs owned players)

A language model must not invent `now_cost`, likelihood, or action class.
Do not scrape third-party predictor UIs.
See `docs/price-prediction.md`.
