# Traceability matrix (WIP)

| Requirement | Module | Owner | Tests | Degradation | Gate |
| --- | --- | --- | --- | --- | --- |
| Private team sync | team_state.private | det | test_team_state | INSUFFICIENT | hard |
| Public FPL adapters | ingestion.client | det | contract + live opt-in | cached TTL / stop | hard |
| Season rules 2026/27 | rules.* | det | test_rules | exit 8 | hard |
| Projections | projections.* | det | test_projections_strategy | uncalibrated labels | evidence |
| Scenarios | strategy.engine | det | test_projections_strategy | conditional/insufficient | hard |
| Rivals/news/monitor | rivals, evidence, monitoring | det | test_context_layers | non-fatal rivals | soft |
| Ledger/replay | evaluation.* | det | unit + integration | provisional preview | hard |
| LLM synthesis | llm.client | model | validation tests | deterministic fallback | hard |
| Reports/publish | reporting, publishing | det | test_context_layers | dry-run | hard |
| Actions | .github/workflows | ops | workflow present | watchdog required | blocked unattended |
