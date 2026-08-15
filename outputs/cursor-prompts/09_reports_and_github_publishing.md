# Cursor Prompt 09 — Reports, Canonical State, and Race-Safe GitHub Publishing

Continue from Prompts 01–08. Do not use or refer to any old PRD.

Implement actionable Markdown and GitHub Issue publishing. The consistency target is at-least-once workflow execution with exactly one canonical logical result—not a false claim that GitHub Actions guarantees exactly-once execution.

## First action

Run all tests. Review run manifests, immutable decision records, outcome corrections, material-change classification, executability, and deterministic fallback. Design the publishing state machine in `docs/publishing-consistency.md` before implementing mutations.

## Reports

Use a structure equivalent to:

```text
reports/{season}/gw-{NN}/{run_id}-{mode}.md
reports/{season}/gw-{NN}/latest.md
reports/{season}/gw-{NN}/review.md
reports/{season}/reviews/rolling-{lookback}-gw.md
reports/{season}/index.md
```

Deadline reports must put a one-screen decision summary first:

- executable, conditional-only, or insufficient-state status;
- primary transfer plan or explicit “no executable recommendation”;
- hit, bank after, freshness time, and affordability check time;
- starting XI, bench, captain, and vice;
- chip instance advice;
- roll plus safer/aggressive alternatives;
- six-gameweek table;
- material news, contradictions, rival context, assumptions, triggers, and warnings;
- sources, data/model/prompt versions, usage, estimated/actual cost, and run ID.

Do not display more precision than the projection method supports. Label uncalibrated intervals and conditional scenarios clearly. Every current material claim must have a visible clickable source.

Daily reports should emphasize only material changes and decision triggers. No-change runs should not create report noise unless a configured heartbeat artifact is due.

Review reports must include:

- recommended versus actual action when observable;
- exact points for actual, recommendation, roll, and recorded alternatives;
- attribution for transfer/hit, captain, lineup/bench/autosub, and chip only where valid;
- process and outcome grades separately;
- projection calibration and open multi-gameweek decision status;
- what worked, failed, was variance, and remains unresolved;
- evidence-linked lesson proposals;
- original decision hash and outcome/review version.

Escape Markdown and hostile HTML. Never render secrets, raw headers, cookies, full private-state payloads, or unbounded raw source content.

## Canonical run bundle

Before GitHub mutation, create a content-addressed run bundle containing:

- manifest;
- immutable machine-readable decision or outcome record;
- rendered Markdown;
- desired Issue body/comment operations;
- input and output hashes.

Use a state machine such as `prepared → repository_published → issue_published → reconciled`, with recoverable transitions. A partial failure must be resumable from the bundle without regenerating the recommendation.

Never change the original deadline recommendation during a retrospective or correction. `latest.md` may point to a newer canonical record, but history remains intact.

## GitHub Issue behavior

Maintain one issue per gameweek with stable hidden markers in addition to a human title. Suggested presentation:

- title: `FPL Agent — GW {N}`;
- labels: `fpl-agent`, `gameweek-{N}`;
- body: latest canonical recommendation plus link to repository report;
- comments: timestamped material changes;
- one retrospective comment per review version;
- one deduplicated failure warning per failure fingerprint when publishing is safe.

Upsert by stable marker/label and verify the existing issue belongs to the same season/gameweek. Do not rely only on title text. Do not comment on a no-material-change run.

## Concurrency and Git consistency

GitHub concurrency groups reduce overlap but do not prove exactly-once processing or ordering. Implement application-level idempotency keys and reconciliation.

- Use one canonical publisher path/job for all repository and Issue mutations.
- Serialize publisher work across daily, deadline, review, and manual workflows using a shared concurrency group.
- Derive idempotency from season, gameweek, mode, logical event/version, and content hash—not wall-clock time.
- Before pushing, verify the current default-branch head and rebase/reapply the prepared bundle on conflict.
- Retry a bounded number of times; never force-push.
- When the repository write succeeds but the Issue mutation fails, preserve the bundle and resume only the missing transition.
- Reconcile repository manifest, issue marker, comments, and content hashes on every publisher run.
- Never let an older delayed run replace a newer canonical run without an explicit ordering policy.

Document unavoidable non-atomicity between Git and GitHub Issues and show how reconciliation repairs it.

## Permissions and dry run

Use the workflow-provided `GITHUB_TOKEN`, not a personal access token. The future publishing job requires explicit `contents: write` and `issues: write`; all other permissions should be `none` or the minimum required read scope.

Provide a full local/dry-run publisher that writes the intended operations without calling GitHub. No publish command may default to mutating GitHub.

## Tests and acceptance criteria

Use a fake Git repository/GitHub API or isolated test repository for mutation tests. Cover:

- first issue creation and subsequent update;
- repeated identical runs producing no duplicate report/comment/commit;
- twenty duplicate or overlapping prepared bundles converging on one canonical logical state;
- old delayed run refusing to replace a newer run;
- repository success plus Issue failure and successful reconciliation;
- Issue success plus local crash and idempotent recovery;
- branch conflict and bounded retry without force-push;
- official correction producing a new review version without rewriting the old one;
- Markdown/HTML injection and secret redaction;
- no-change daily run producing no Issue noise;
- dry-run performing zero network mutations.

This phase is accepted only when duplicate/retried/partial runs converge, the history is immutable, one publisher owns all mutations, and a deterministic fallback report is publishable without OpenAI. Finish with the standard checkpoint and stop.
