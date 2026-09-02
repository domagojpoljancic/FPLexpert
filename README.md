# FPL Expert

A read-only Fantasy Premier League assistant. It recommends transfers, captain, lineup, bench, and overnight price moves. **You** make every change in the official FPL app. It never logs into FPL.

<!-- recent-runs:start -->
## Latest results

**Price watch** (GitHub, 20:00 Zagreb — last 7 days)
- [01 Sep 23:40 CEST](reports/prices-gw3-20260901T214030Z.md) · GW3 · **NO ACTION** — No price action tonight.
- [01 Sep 01:09 CEST](reports/prices-gw3-20260831T230954Z.md) · GW3 · **NO ACTION** — No price action tonight.
- [30 Aug 23:52 CEST](reports/prices-gw3-20260830T215242Z.md) · GW3 · **NO ACTION** — No price action tonight.
- [29 Aug 23:36 CEST](reports/prices-gw3-20260829T213616Z.md) · GW3 · **NO ACTION** — No price action tonight.
- [29 Aug 04:02 CEST](reports/prices-gw3-20260829T020207Z.md) · GW3 · **NO ACTION** — No price action tonight.
- [28 Aug 05:31 CEST](reports/prices-gw2-20260828T033149Z.md) · GW2 · **NO ACTION** — No price action tonight.
- [26 Aug 23:44 CEST](reports/prices-gw2-20260826T214423Z.md) · GW2 · **NO ACTION** — No price action tonight.

**Squad news** (pre-deadline — last 7 days)
- [02 Sep 14:55 CEST](reports/predeadline-gw3-20260902T125520Z.md) · GW3 · **REVISE** — Consider Virgil to Ajayi with the free transfer, subject to a final availability check ne…
- [02 Sep 14:34 CEST](reports/predeadline-gw3-20260902T123407Z.md) · GW3 · **REVISE** — Consider O'Nien to Egan with the free transfer: it fixes the clearest start-risk slot and…
- [02 Sep 12:03 CEST](reports/predeadline-gw3-20260902T100329Z.md) · GW3 · **REVISE** — Use the free transfer on O'Nien to Egan, retain Bruno Fernandes as captain, and recheck T…
- [28 Aug 06:55 CEST](reports/predeadline-gw2-20260828T045547Z.md) · GW2 · **REVISE** — Consider Gibbs-White to Cherki, then start João Pedro over Shaw and keep Bruno Fernandes…
<!-- recent-runs:end -->

## How it works

Overnight, a GitHub Action watches FPL prices and writes a short report. About a day before each gameweek deadline, you run a squad review from your phone. You get a TLDR, the model’s XI / captain / bench, and only the news pages the review actually opened.

## From your phone

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

## On a laptop

```bash
uv sync
uv run fpl-agent prices                 # overnight-style price watch (no OpenAI)
uv run fpl-agent predeadline --live-ai  # squad news; add --force outside the ~24h window
uv run fpl-agent scorecard -g 2         # last week's plan vs official points
uv run fpl-agent prices-watchdog        # alert if overnight price job looks skipped
uv run pytest
```

Reports: `reports/prices-gw*.md` and `reports/predeadline-gw*.md`. JSON next to them stays local.

Private squad files stay on your machine (`data/private-state/`). They are gitignored and never committed. The assistant never mutates your FPL team.

Overnight price watch runs on GitHub (`fpl-prices.yml`, 20:00 Zagreb). GitHub cron can still fire late; the job skips ticks before 20:00 local and skips if it already succeeded that day. A second workflow (`fpl-prices-watchdog.yml`) comments if that job is more than 26 hours late.
