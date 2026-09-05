# Security Policy

## Supported use

This repository is a **private-purpose** project for personal Fantasy Premier League decision support this season — not a public product. It may become a product after a full Premier League season.

It is a **read-only** FPL decision-support agent. Supported deployments:

- local CLI analysis with user-provided private team state files;
- GitHub Actions scheduled **price** workflow (no OpenAI) and manual/test workflows. Never authenticate to Fantasy Premier League.

## Prohibited

- Storing an FPL password or session cookie.
- Authenticating to FPL or calling any endpoint that changes squad, transfers, lineup, captain, or chips.
- Logging secret values, full environments, or private-state payloads.
- Treating base64 as encryption. Base64 is **encoding only**; GitHub encrypts repository secrets at rest, but the local encoding step is not encryption.

## Secret rotation

1. Rotate `OPENAI_API_KEY` in the provider dashboard and update the GitHub Actions secret.
2. Re-encode and replace `FPL_PRIVATE_STATE_B64` after any squad/finance change you want the agent to trust.
3. Revoke `GITHUB_TOKEN`/PATs used for optional external watchdogs when compromised.

## Disclosure

Report suspected secret leakage or security defects privately to the repository owner. Do not open public issues containing secret material.
