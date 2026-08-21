# FPL Expert

WIP. Recommends transfers, hits, lineup, captain, bench, and chips. **You** make every FPL change. It never logs into FPL.

<!-- recent-runs:start -->
## Latest results

**Price watch** (GitHub, ~21:00 Zagreb)
- [20 Aug 21:36 CEST](reports/prices-gw1-20260820T193618Z.md) · GW1 · **NO ACTION** — No price action tonight.
- [19 Aug 21:31 CEST](reports/prices-gw1-20260819T193120Z.md) · GW1 · **NO ACTION** — No price action tonight.
- [18 Aug 21:32 CEST](reports/prices-gw1-20260818T193222Z.md) · GW1 · **NO ACTION** — No price action tonight.
- [18 Aug 17:20 CEST](run-log.md) · GW1 · **NO ACTION** — No price action tonight.

**Squad news** (pre-deadline)
- [21 Aug 19:19 CEST](reports/predeadline-gw1-20260821T171955Z.md) · GW1 · **REVISE** — Use the free transfer on Tzolis to Wilson, keep Bruno Fernandes captain, and switch the v…
- [21 Aug 19:10 CEST](reports/predeadline-gw1-20260821T171009Z.md) · GW1 · **REVISE** — Consider Tzolis to Wilson with the free transfer, while keeping Bruno Fernandes captain a…
- [21 Aug 19:06 CEST](reports/predeadline-gw1-20260821T170604Z.md) · GW1 · **WATCH** — Hold the free transfer, keep Bruno Fernandes captain and Raya vice, and leave low-start-p…
<!-- recent-runs:end -->

## From your phone (Cursor)

**Prices** run overnight on GitHub. Watch the repo (or issue **FPL price alerts**) for email only when you should act. Reports land in the list above.

**Squad news** — about a day before the GW deadline:

1. Cursor mobile → **Cloud Agent** on this repo (not a local session on a sleeping laptop).
2. Cloud secrets: `OPENAI_API_KEY` and `FPL_PRIVATE_STATE_B64`. Python 3.12 + `uv`.
3. Prompt: `Run the pre-deadline review.`
4. The agent lists the saved squad and waits. Reply **unchanged**, or send an FPL screenshot if the team changed. A pitch or transfers screenshot is enough — it maps **printed name + opponent line under the name** (`Raya|COV|H|6.0`), not kits or last-season clubs.
5. Leave Cursor’s model on **Auto**. OpenAI inside `predeadline` uses the **`gpt-5.6`** alias (current GPT-5.6 Sol), not a dated snapshot.
6. Read the report (chat + GitHub link above): **TLDR** first, then why, then every page OpenAI actually returned. You still transfer in the FPL app.

The agent saves `reports/predeadline-*.md`, refreshes the list above, commits, pushes, and **merges to `main`** in the same run so the links here work from your phone. An open PR is not enough.

## After you change your squad

Re-encode private state and update GitHub secret `FPL_PRIVATE_STATE_B64` (and the Cloud Agent secret):

```bash
uv run fpl-agent team-state encode-for-github PATH
```

## Laptop

```bash
uv sync
uv run fpl-agent prices                 # overnight-style price watch (no OpenAI)
uv run fpl-agent predeadline --live-ai  # squad news; add --force outside the ~24h window
uv run pytest
```

Reports: `reports/prices-gw*.md` and `reports/predeadline-gw*.md`. JSON next to them stays local.

## What is here

- CLI `fpl-agent` — rules, projections, price watch, pre-deadline news, `team-state lookup` for screenshot names
- GitHub Action `fpl-prices.yml` — 21:00 Europe/Zagreb (GitHub cron can skip or run late)
- Cursor rule `.cursor/rules/predeadline.mdc` — phone Cloud Agent flow
- Never mutates your FPL team
