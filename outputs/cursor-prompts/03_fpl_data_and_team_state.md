# Cursor Prompt 03 — FPL Data Adapters and Trustworthy Current-Team State

Continue from Prompts 01–02. Do not use or refer to any old PRD.

The purpose of this phase is to solve the largest feasibility risk: public FPL picks do not reliably reveal a manager's live, unsubmitted pre-deadline team, and public data cannot be assumed to reveal current bank, free transfers, purchase/selling prices, or remaining chip instances.

## First action

Run all existing tests. Inspect the live FPL endpoints listed below using read-only requests. Store small sanitized fixtures and update the assumptions register. Treat the routes as observed website interfaces, not a documented/versioned public developer API.

Expected adapter routes:

- `/api/bootstrap-static/`
- `/api/fixtures/`
- `/api/entry/{manager_id}/`
- `/api/entry/{manager_id}/history/`
- `/api/entry/{manager_id}/event/{gw}/picks/`
- `/api/entry/{manager_id}/transfers/`
- `/api/leagues-classic/{league_id}/standings/`
- `/api/element-summary/{player_id}/`
- `/api/event/{gw}/live/`

Do not invent behavior when a route returns 401, 403, 404, partial data, or a changed schema.

## FPL client and adapters

Implement an `FplClient` and focused adapters with:

- connect/read/total timeouts;
- bounded retry with exponential backoff and jitter for retryable failures only;
- response-size and content-type limits;
- Pydantic validation and explicit compatibility versions;
- conditional requests/cache headers when available;
- per-route request budgets and cache TTLs;
- pagination for league standings where needed;
- sanitized raw-response artifacts with short retention for diagnostics;
- normalized snapshots containing source URL, retrieval time, HTTP status, adapter/schema version, and SHA-256 content hash;
- fail-closed behavior when required fields disappear;
- tolerant handling of new optional fields.

Determine the current and next gameweek from event metadata. Do not use date arithmetic to guess the event.

Add contract fixtures and an opt-in live smoke command. Live contract failure should alert but must not make ordinary offline unit tests flaky.

## Explicit current-team source model

Resolve each field separately and record which source won. Supported sources, in priority order, are:

1. a fresh, validated user-synchronized private state;
2. public post-deadline picks/history/entry data for fields it actually proves;
3. the most recent local canonical snapshot within a configured TTL;
4. unknown.

Never claim that public picks reveal unsubmitted pre-deadline changes. Never assume that a public transfer route exposes private current-gameweek transfers before the deadline. Such behavior may only be used if it is explicitly revalidated and recorded as observed, and there must still be a safe fallback.

The resolver must output per-field provenance and freshness for:

- the exact 15-player squad;
- bank;
- free transfers;
- purchase prices or directly observed selling prices;
- both instances/windows/status of every chip;
- current captain, vice-captain, lineup, and bench when relevant;
- as-of time and the gameweek to which the state applies.

## User-controlled private state synchronization

Implement a usable local synchronization workflow without FPL authentication.

Create a schema along these lines:

```json
{
  "schema_version": "1.0.0",
  "season": "2026-27",
  "applies_before_gameweek": 1,
  "as_of": "2026-08-13T08:00:00+02:00",
  "player_ids": [1],
  "bank_tenths": 15,
  "free_transfers": 1,
  "purchase_prices_tenths": {"1": 55},
  "chip_instances": []
}
```

The real schema must require all 15 players, reconcile IDs against the current catalog, validate financial values and chip instances against `SeasonRules`, and reject an event/season mismatch.

Add CLI commands equivalent to:

- `team-state validate PATH`;
- `team-state status`;
- `team-state encode-for-github PATH` or a safer `gh secret set` helper.

If using a GitHub Actions secret payload, state clearly that GitHub encrypts stored secrets but base64 itself is not encryption. Never print the payload. The recommended secret name may be `FPL_PRIVATE_STATE_B64`, but decoding must happen only inside the narrow step/job that requires it. Local state files must be gitignored.

Do not add FPL credentials, browser login, session-token capture, or authenticated “my team” endpoints.

## Executability and staleness gate

Implement a deterministic decision returning one of:

- `EXECUTABLE`: exact current squad and all required financial/chip fields are fresh and reconciled;
- `CONDITIONAL_ONLY`: analysis is possible but affordability, hit, or chip availability depends on stated unknowns;
- `INSUFFICIENT`: squad identity or another non-negotiable field is missing/stale, so no recommendation may be ranked.

An executable transfer recommendation must never rely on stale squad identity, guessed bank, guessed free transfers, or guessed selling values. The report layer will later expose this status prominently.

## Failure and schema-drift behavior

- Public FPL unavailable: use a cached source only inside its TTL and label it stale; otherwise stop before recommendation.
- Picks unavailable before GW1 or another deadline: require the user-synchronized squad.
- Conflicting field values: retain both provenance records, select only by explicit precedence, and add a warning.
- Material schema drift: stop analysis with an actionable, deduplicatable error.
- Private state malformed or stale: do not fall through to a falsely “high confidence” public reconstruction.

## Tests and acceptance criteria

Add unit, contract, and integration tests for:

- every route normalizer and required-field drift;
- 401/403/404, timeout, invalid content type, oversized body, retry exhaustion, and stale cache;
- field-level source precedence;
- GW1 picks returning 404;
- private-state schema and 15-player reconciliation;
- mismatched season/gameweek and stale timestamps;
- conflicting public/private fields;
- unknown bank, free transfers, selling prices, and chips producing `CONDITIONAL_ONLY`;
- stale/unknown squad identity producing `INSUFFICIENT`;
- secret payload and private state never appearing in logs or artifacts.

This phase is accepted only when a frozen offline run can reconstruct a fully proven team state, deliberately incomplete finance produces conditional-only output, a stale squad blocks advice, and the user has a documented end-to-end command for updating the private state without exposing it. Finish with the standard checkpoint and stop.
