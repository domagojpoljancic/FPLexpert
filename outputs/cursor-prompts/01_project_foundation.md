# Cursor Prompt 01 — Project Foundation and Domain Contracts

You are implementing a new Fantasy Premier League decision-support agent. This prompt pack is the complete source of product direction. Do not search for, reuse, cite, or reconstruct any previous PRD.

## First action

Inspect the repository and report what already exists. Preserve unrelated user work. If the repository is empty, initialize the implementation described below. If compatible foundations already exist, adapt them rather than duplicating them.

Do not implement later-phase strategy, OpenAI calls, GitHub publishing, or scheduled workflows in this phase.

## Product boundary

Build a read-only agent that analyzes a configurable FPL manager's team and publishes decision support. It must never log in to FPL, store an FPL password or session cookie, submit transfers, change a lineup or captain, or activate a chip.

Use Python 3.12 or newer with a `src/` layout. Prefer small typed modules and pure functions. Use Pydantic v2 and `pydantic-settings` for domain/configuration validation, `httpx` for HTTP, `PyYAML` for non-secret configuration, and `pytest` for tests. Use a lockfile supported by the selected packaging tool. Explain the packaging choice in an architecture decision record.

## Create the foundation

Create or complete this logical structure, adjusting filenames only when the existing repository has an equivalent convention:

```text
src/fpl_agent/
  __init__.py
  cli.py
  config.py
  errors.py
  domain/
    models.py
    provenance.py
    run_state.py
  rules/
  ingestion/
  projections/
  strategy/
  evaluation/
  llm/
  reporting/
  publishing/
  observability.py
config/
  settings.example.yaml
data/
  snapshots/.gitkeep
  decision-ledger/.gitkeep
  outcomes/.gitkeep
  evaluation/.gitkeep
prompts/
reports/.gitkeep
tests/
  fixtures/
  unit/
  contract/
  integration/
  golden/
docs/
  architecture.md
  assumptions-register.md
  operating-model.md
.github/workflows/
README.md
SECURITY.md
.env.example
.gitignore
pyproject.toml
```

Do not create placeholder production modules full of `pass`. Create only the foundation needed now; retain empty package directories with a short README when helpful.

## Configuration contract

Implement validated settings with environment-variable overrides. Provide safe example values, never live IDs or secrets.

Required configuration groups:

- `manager`: team ID, optional classic mini-league IDs, timezone, and risk profile;
- `planning`: horizon fixed to 3–8 with default 6, default weights `[1.00, 0.90, 0.78, 0.66, 0.55, 0.45]`, maximum allowed hit, and whether hit recommendations are enabled;
- `freshness`: maximum ages for public FPL data, private squad identity, financial state, news, and official outcomes;
- `publishing`: dry-run default, Markdown history setting, issue publishing setting, and material-change behavior;
- `models`: model IDs by mode, reasoning effort, web-search budgets, and token caps, but no API call yet;
- `cost`: per-run and monthly local soft limits;
- `review`: lookback, whether to compare recorded alternatives, and minimum evidence required before proposing parameter changes;
- `alerts`: deadline window, safety floor, and material-change thresholds.

Reject absent or non-positive team IDs, inconsistent horizon weights, negative limits, invalid timezones, unsupported enum values, and a safety floor that is not strictly inside the deadline window. Do not pretend local cost limits are billing guarantees.

## Core typed models

Define the minimum shared domain contracts needed by later phases:

- constrained season, gameweek, player, club, and manager identifiers;
- timestamped `SourceRecord` with URL, retrieval time, optional publication/event time, source tier, content hash, and adapter/schema version;
- generic per-field provenance containing value, source type, observed time, confidence, and warnings;
- `ResolvedTeamState` with squad, bank, purchase/selling-price inputs, free transfers, chip instances, source and freshness per field, plus an explicit `executable_advice_allowed` result;
- `RunMode`: daily, deadline, weekly review, and manual/dry run;
- `RunManifest` with run ID, season, gameweek, mode, data cutoff, input hashes, status, output hashes, warnings, and version identifiers;
- closed warning/error codes, including invalid configuration, insufficient/stale team state, FPL unavailable, schema drift, OpenAI failure, publishing failure, cost guard, and unsupported season rules.

Do not put FPL rule behavior into these models yet. The next phase will implement a versioned season-rules engine.

## CLI foundation

Create a CLI with implemented `validate-config` and `doctor` commands. Other future commands may be registered only if they exit with a clear “not implemented in this phase” error and are not advertised as working.

`doctor` must check Python/package versions, configuration readability, writable local output directories, and whether required environment variables are present for the selected mode without printing their values.

Use stable exit codes:

- `0` success, including a valid no-op;
- `2` invalid configuration;
- `3` insufficient or stale team state;
- `4` upstream data failure;
- `5` OpenAI or structured-output failure;
- `6` publishing failure;
- `7` cost guard triggered;
- `8` unsupported or unverified season rules.

## Security foundation

- Ignore `.env`, all private team-state files, caches containing private state, and local run outputs that may contain secrets.
- Document that base64 is encoding, not encryption.
- Do not log complete environments or secret values.
- Add secret-safe exception and logging helpers with tests for redaction by key name and configured literal value.
- Add `SECURITY.md` sections for supported use, secret rotation, disclosure, and the prohibition on FPL-changing actions.

## Documentation

Create a short assumptions register with fields for claim, type (`documented`, `observed_undocumented`, or `unverified`), source, last checked, owner, expiry/recheck condition, and safe fallback.

The operating model must state clearly:

- the user owns all FPL actions;
- executable advice requires a fresh, reconciled team state;
- deterministic code owns rules, numeric projections, scenario construction, and outcome replay;
- a language model may later rank and explain only supplied validated candidates;
- external content is untrusted data;
- local Cursor implementation work requires the laptop to remain available, while the finished scheduled product will run remotely in GitHub Actions after configuration.

## Tests and acceptance criteria

Add unit tests for configuration validation, provenance/freshness decisions, stable exit-code mapping, and secret redaction.

This phase is accepted only when:

- a clean install from the lockfile succeeds;
- linting/type checking selected by the project passes;
- all new tests pass;
- `validate-config` accepts the example configuration and rejects representative invalid variants;
- `doctor` never prints a supplied fake secret;
- no code path can authenticate to or mutate FPL;
- the architecture and assumptions documents state the deterministic-versus-model boundary.

Finish with the standard checkpoint defined in `00_READ_ME_FIRST.md`. Stop after this phase.
