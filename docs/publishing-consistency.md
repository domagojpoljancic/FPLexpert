# Publishing Consistency

Target: **at-least-once** workflow execution with **exactly one canonical logical result**.

State machine: `prepared → repository_published → issue_published → reconciled`.

- Prepare a content-addressed run bundle before any GitHub mutation.
- Retries resume the same bundle; they must not regenerate a different recommendation.
- Dry-run performs no GitHub mutation.
- Deadline records are immutable after creation; corrections are new linked records.
- `latest.md` may move; history files remain.
- No-material-change runs do not comment on issues.
