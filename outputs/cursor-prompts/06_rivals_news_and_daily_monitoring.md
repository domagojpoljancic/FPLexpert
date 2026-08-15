# Cursor Prompt 06 — Rival Context, News Evidence, and Daily Change Detection

Continue from Prompts 01–05. Do not use or refer to any old PRD.

This phase adds deterministic rival analysis, normalized news/evidence contracts, and low-noise daily monitoring. Do not yet implement the OpenAI Responses API; Prompt 08 will connect web search and synthesis.

## First action

Run the existing tests and inspect the data adapters, projections, and scenario contracts. Reuse source/provenance types. Do not let raw web text flow directly into configuration, code execution, numeric projections, or decision records.

## Mini-league analysis

When configured classic league standings are publicly available:

- page through standings safely;
- locate the configured manager;
- select a configurable set of nearest rivals above and below, default five each;
- obtain rival picks only for gameweeks and fields that are publicly visible;
- calculate squad overlap, observed captain overlap, player threats, chip use already visible, recent transfer behavior where observed, and differential opportunities;
- separate observed ownership/picks from inferred future behavior;
- record retrieval time, source, pagination coverage, and unavailable rivals.

Do not claim true “effective ownership” unless its denominator, captain multipliers, chip effects, and population are explicitly defined. Label a calculation based only on sampled mini-league rivals as sampled rival exposure, not global ownership.

Rival strategy must never make an illegal or clearly inferior scenario preferable merely for novelty. Expose rival metrics to the strategy layer through a bounded, documented modifier or tie-breaker. Preserve base expected points separately.

If league data is private, missing, paginated beyond the configured budget, or schema-invalid, continue without rival analysis and emit a non-fatal warning.

## News and evidence model

Create typed contracts for:

- a targeted search request tied to specific players, clubs, fixtures, or unresolved assumptions;
- source record and source tier;
- normalized claim;
- affected player/team/fixture IDs;
- claim category: injury, suspension, availability, predicted minutes, rotation, press-conference statement, postponement, confirmed fixture change, or other;
- publication/event time, retrieval time, corroboration count, confidence, and expiry;
- contradictions and superseded claims;
- decision impact and the assumption/projection override proposed.

Source preference:

1. Premier League, FPL, FA, club, or direct manager press-conference source;
2. established sports outlet or named specialist reporter;
3. community or aggregator, explicitly marked lower confidence.

Implement deterministic confidence-policy inputs, not fake precision. A source tier alone must not prove a claim. Conflicting reports must remain visible. Define freshness limits by claim type and require stronger corroboration for large projection or recommendation changes.

External titles, snippets, bodies, URLs, issue text, and player fields are untrusted data. Keep them in data-only fields. Reject non-HTTP(S) URLs, constrain redirects in future fetchers, limit lengths, and ensure embedded instructions cannot modify configuration or system policies.

## Projection override boundary

News never directly writes expected points. It creates a versioned proposed availability/minutes scenario. Deterministic code validates the target player, allowed field, value range, source freshness, and confidence policy before producing a new projection version.

Preserve the original and adjusted projections with an audit record. A contradiction should trigger sensitivity paths rather than a silently chosen fact.

## Daily monitoring

Implement deterministic snapshot comparison for:

- player availability flags and status;
- price movement and official price-predictor state when a supported source exists;
- fixture addition, removal, time change, postponement, blank, or double;
- red cards/suspension-related structured changes present in FPL data;
- team-state freshness/validity;
- material projection, scenario, captaincy, or chip-plan changes;
- source claims added, contradicted, expired, or superseded.

Define a material-change classifier. Timestamps alone must not create a material change. No-change runs should generate a deterministic heartbeat/state record without creating report or Issue noise.

Add a `monitor --offline` path over frozen snapshots and a dry-run summary suitable for later scheduled workflows.

## Tests and acceptance criteria

Test:

- league pagination and manager/rival selection;
- unavailable/private league degradation;
- sampled exposure labeling;
- observed fact versus inferred behavior;
- conflicting injury claims and expiring claims;
- malicious prompt-like text in titles, bodies, and URLs remaining inert data;
- stale news not changing projections;
- validated news scenario creating a new projection version without overwriting the old one;
- fixture postponement, price movement, flag change, and no-change comparisons;
- timestamps alone not causing material output;
- identical snapshots producing one stable no-change result.

This phase is accepted only when rival data fails non-fatally, every material news claim has provenance and freshness, untrusted text cannot reach a control field, and daily monitoring distinguishes meaningful changes from noise deterministically. Finish with the standard checkpoint and stop.
