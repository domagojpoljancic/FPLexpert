# ADR 0001 — Packaging with uv + hatchling

## Decision

Use uv for environment/lockfile management and hatchling as the build backend.

## Consequences

- `uv sync` reproduces the environment from `uv.lock`.
- Requires Python 3.12+.
- CLI exposed as `fpl-agent`.
