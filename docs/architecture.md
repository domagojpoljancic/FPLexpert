# Architecture

## Packaging choice

We use **uv** + **hatchling** with a `src/` layout and `uv.lock`.

- uv provides fast, reproducible installs and a first-class lockfile.
- hatchling is a lightweight PEP 517 backend without Poetry's heavier workflow.
- Python **3.12+** is required (matches modern typing and the prompt-pack contract).

## Deterministic vs model boundary

| Concern | Owner |
| --- | --- |
| Season rules, prices, FT/hits, chips, autosubs, replay totals | Deterministic code (`rules`, `evaluation`) |
| Expected points / uncertainty baseline | Deterministic code (`projections`) |
| Scenario construction & legality | Deterministic code (`strategy`) |
| Team-state provenance & executability | Deterministic code (`team_state`) |
| Ranking/explanation of supplied candidates | Optional LLM (`llm`) — cannot invent IDs or override numbers |
| Publishing | Deterministic state machine (`publishing`) |

## Runtime shape

No always-on app server. **Price watch** is scheduled GitHub Actions (`fpl-prices.yml`). **Pre-deadline** is a manual Cloud Agent / local CLI run. Laptop is required only for Cursor implementation work.

## Modules

- `config` — validated settings
- `ingestion` — read-only FPL HTTP adapters
- `team_state` — private sync + field resolver
- `rules` — versioned `SeasonRules`
- `projections` — baseline xP
- `strategy` — multi-GW scenarios
- `prices` — snapshot history, uncalibrated rise/fall bands, smart-to-act (daily cadence)
- `evidence` / `rivals` / `monitoring` — context layers
- `evaluation` — ledger + replay
- `llm` — bounded synthesis
- `reporting` / `publishing` — Markdown + GitHub consistency
