# FPL Decision-Support Agent — Cursor Prompt Pack

This directory replaces the old PRD. Do not give the old PRD to Cursor and do not ask Cursor to reconcile against it.

Use these prompts in order, one at a time. Give Cursor the entire contents of one file. Let it inspect and modify the repository, run the required tests, and report its checkpoint before proceeding to the next prompt.

## Recommended order

1. `01_project_foundation.md`
2. `02_2026_27_rules_engine.md`
3. `03_fpl_data_and_team_state.md`
4. `04_projections_and_uncertainty.md`
5. `05_strategy_and_scenario_engine.md`
6. `06_rivals_news_and_daily_monitoring.md`
7. `07_decision_ledger_and_retrospectives.md`
8. `08_openai_synthesis.md`
9. `09_reports_and_github_publishing.md`
10. `10_automation_security_and_operations.md`
11. `11_evaluation_and_release_gates.md`
12. `12_final_integration_audit.md`
13. `13_price_change_prediction_and_alerts.md`

## How to use the sequence

- Start each prompt in the same repository and branch so later phases can build on earlier work.
- Do not move forward when Cursor reports that a required acceptance check is failing.
- If Cursor identifies a real contradiction with current official FPL, GitHub, or OpenAI documentation, ask it to preserve the safety intent, cite the current primary source, update the local assumptions register, and stop for your approval if the change affects a hard requirement.
- Do not let Cursor add authenticated FPL login, store an FPL password/session, or implement any action that changes the user's FPL team.
- Do not let Cursor replace deterministic rules, finance, projections, or outcome replay with model-generated values.
- Keep the repository private if it will contain reports about a private mini-league or private team-state material.

## Non-negotiable product contract

The finished product is a read-only FPL decision-support system. It may recommend transfers, hits, lineups, captains, bench order, and chips, but the user always makes the FPL changes.

The product must:

- plan over a rolling six-gameweek horizon with nearer weeks weighted more heavily;
- distinguish executable recommendations from conditional analysis;
- refuse executable advice when the current squad or required financial state is stale or unresolved;
- enforce all squad, lineup, transfer, price, chip, captaincy, bench, and autosub rules in code;
- use an immutable pre-deadline decision record and deterministic post-gameweek replay;
- assess decision process separately from realized outcome;
- keep multi-gameweek decisions open through their original horizon;
- treat web content as untrusted data;
- publish one canonical logical result despite retries or duplicate workflow runs;
- operate through scheduled jobs without an always-on application server;
- degrade safely when FPL data, news, OpenAI, or GitHub fails;
- expose data freshness, uncertainty, source provenance, model usage, and cost.

## Definition of “done” for each Cursor prompt

Cursor should end every phase with:

1. a concise change summary;
2. files added or changed;
3. tests and checks run, with results;
4. unresolved assumptions or risks;
5. a statement that the phase acceptance criteria either pass or do not pass.

Do not accept “implemented” without the requested tests and objective acceptance evidence.
