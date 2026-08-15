# Cursor Prompt 10 — Unattended GitHub Actions, Security, and Operations

Continue from Prompts 01–09. Do not use or refer to any old PRD.

Implement unattended operation without an always-on application server. After setup, scheduled jobs must run on GitHub-hosted infrastructure while the user's laptop is asleep or turned off. Local Cursor implementation itself is not part of that guarantee.

## First action: verify GitHub behavior

Before writing workflow files, verify and record current primary GitHub documentation for:

- scheduled events, IANA timezones, default-branch behavior, delayed/dropped schedules, and public-repository inactivity disabling;
- concurrency ordering/cancellation semantics;
- `GITHUB_TOKEN` permissions and event-recursion behavior;
- secrets, environments, artifact retention, and dependency pinning.

Start with:

- <https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule>
- <https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax>
- <https://docs.github.com/en/actions/concepts/security/github_token>
- <https://docs.github.com/en/actions/concepts/security/secrets>

Do not claim schedule punctuality or exactly-once execution. Current GitHub documentation warns that scheduled runs can be delayed or dropped under load and that public repositories can have schedules disabled after inactivity.

## Workflow architecture

Create small workflows or reusable workflow components for:

- daily monitoring;
- deadline watching/preflight;
- post-gameweek review preflight;
- manual dispatch;
- one canonical publisher path shared by every mode;
- opt-in live contract/smoke checks.

Scheduled workflows run from the latest default-branch commit. Manual dispatch must default to dry-run/no-publish and expose validated mode, optional gameweek/team override, and explicit publish confirmation.

## Deadline operation

The deadline watcher must:

1. run a cheap deterministic preflight with no OpenAI key in its environment;
2. fetch the official deadline from event metadata;
3. exit successfully when outside the configured analysis window;
4. use several staggered schedule opportunities inside the relevant period rather than relying on one top-of-hour run;
5. consult canonical run manifests and idempotency keys;
6. refresh all required state before recommendation;
7. refuse to call OpenAI or claim timely advice inside the safety floor;
8. publish or signal a stale/missed-analysis warning when still operationally possible.

Avoid schedule times at the top of the hour where practical. Keep preflight inexpensive and do not expose model credentials to it.

A GitHub-only schedule cannot independently alert when all GitHub schedules are disabled. Implement and document an optional `repository_dispatch`/`workflow_dispatch` hook for an external serverless scheduler or uptime monitor. Full-season unattended readiness must remain blocked until an independent liveness monitor is configured and tested. This monitor is not an always-on application server.

## Review operation

Run a cheap review preflight on a schedule and manually. It must use the season-specific official finality rule, not a weekday or fixed “hours after match” guess. It exits successfully until an unreviewed gameweek is final, then performs official ingestion and deterministic replay before the OpenAI key becomes available.

## Secret and permission isolation

Repository/environment secrets may include only what is required, such as:

- `OPENAI_API_KEY`;
- optional private team-state secret payload selected in Prompt 03;
- optional external-watchdog credential if required.

Non-secret manager IDs, league IDs, timezone, model IDs, cost limits, and publishing settings should use validated variables/configuration.

Requirements:

- set top-level permissions to none/read-only and elevate only the canonical publisher job to `contents: write` and `issues: write`;
- pass the OpenAI key only to the exact model-call job/step;
- pass private state only to the exact resolution job/step;
- do not run secret-bearing or write-permission jobs for untrusted pull requests;
- pin every third-party Action to an immutable commit SHA and record the human-readable release in a comment;
- lock Python dependencies and enable automated dependency updates;
- never dump the full environment, request headers, secret payload, or raw exception containing a secret;
- sanitize artifacts before upload and use explicit short retention;
- document key rotation and incident response.

## Persistence and recovery

GitHub-hosted runners are ephemeral. Canonical state must live in committed manifests/reports/ledgers or another explicitly configured durable store. Artifacts are diagnostic, not the sole persistence mechanism.

Use the publisher state/reconciliation design from Prompt 09. Do not use a lone mutable `run-state.json` as an exactly-once lock. Do not force-push. Ensure a workflow-generated repository commit not triggering normal push workflows does not break the operating model.

## Observability and alerting

Emit structured logs and a job summary with:

- run ID, season, gameweek, mode, stage, and outcome;
- scheduled time, actual start time, deadline distance, and lateness;
- data source status/freshness/cache use;
- rules/projection/model/prompt/schema versions;
- OpenAI tokens, search actions, estimated/actual cost, and cost guard;
- publishing transition and reconciliation status;
- redacted warning/error codes.

Create deduplicated operational alerts for schema drift, stale/insufficient team state, missed deadline analysis, repeated OpenAI failure, publishing inconsistency, rule drift, cost-limit breach, and overdue review. Alert delivery must have at least one route independent of the normal report content for pilot use. Document what cannot alert if GitHub itself is unavailable.

## Degradation behavior

Enforce these outcomes:

- public FPL unavailable: use in-TTL cache with a stale label or stop before recommendation;
- private team state incomplete/stale: conditional-only or insufficient, never guessed execution advice;
- rival data unavailable: continue without rival strategy;
- web search unavailable: use FPL flags/cached normalized claims with lower confidence;
- OpenAI unavailable or invalid: publish deterministic candidates/replay plus warning;
- canonical decision record missing: factual limited review only;
- GitHub Issue failure: preserve repository bundle and reconcile later;
- Git conflict: rebase/retry boundedly, never force-push;
- official result correction: append a new version and update aggregates;
- cost guard: skip/downgrade only according to tested configured policy.

## Setup documentation

Update README with exact steps from clone to:

1. local dry run;
2. private team-state validation and safe secret update;
3. repository variables/secrets;
4. enabling scheduled workflows;
5. permission verification;
6. external liveness monitor setup or an explicit statement that full unattended readiness is not yet met;
7. a proof run showing that GitHub executes independently of the laptop.

## Tests and acceptance criteria

Test workflow syntax and permissions statically, plus integration simulations for:

- outside-window preflight making no OpenAI call;
- delayed run inside the safety floor refusing stale analysis;
- duplicate and overlapping schedule/manual runs;
- event not final causing a no-op review;
- secrets unavailable to preflight and pull-request jobs;
- production jobs not running on untrusted PRs;
- publisher conflict and partial recovery;
- sanitized artifact and log redaction;
- disabled/dropped primary schedule detected by the configured independent monitor in a controlled drill;
- laptop-independent GitHub-hosted dry run.

This phase is accepted only when GitHub-hosted scheduled/manual runs work with the laptop off, permissions and secret scopes are minimal, primary schedule failure is detectable for full unattended mode, and every failure mode has a tested safe result. Finish with the standard checkpoint and stop.
