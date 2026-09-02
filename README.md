# FPL Expert

**A read-only Fantasy Premier League co-pilot.** It reads your squad, fixtures, prices, and news, then recommends transfers, captain, bench, and overnight price moves. **You** make every change in the official FPL app — it never logs into FPL.

## Cheat sheet

| When | What to run |
| --- | --- |
| **~24h before deadline** | `uv run fpl-agent predeadline --live-ai` |
| **Squad changed?** | Send an FPL screenshot in Cursor, or update `data/private-state/current.json` |
| **After a deadline** (optional) | `uv run fpl-agent scorecard -g N` — compare last plan vs real points |
| **Price accuracy** (optional, later in season) | `uv run fpl-agent prices-scorecard` |
| **Too early/late for predeadline?** | add `--force` |
| **FPL API down?** | add `--offline` |

**On your phone:** Cursor → Cloud Agent on this repo → prompt: `Run the pre-deadline review.` The agent lists your saved squad, waits for **unchanged** or a screenshot, then runs the review and publishes the report below.

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
- [02 Sep 21:20 CEST](reports/predeadline-gw3-20260902T192018Z.md) · GW3 · **REVISE** — Consider Virgil to Ajayi with the free transfer, keep Bruno Fernandes captain, and wait f…
- [02 Sep 19:44 CEST](reports/predeadline-gw3-20260902T174456Z.md) · GW3 · **REVISE** — Consider Virgil to Ajayi, start Ajayi, and captain Bruno Fernandes, but check late team n…
- [02 Sep 14:55 CEST](reports/predeadline-gw3-20260902T125520Z.md) · GW3 · **REVISE** — Consider Virgil to Ajayi with the free transfer, subject to a final availability check ne…
- [02 Sep 14:34 CEST](reports/predeadline-gw3-20260902T123407Z.md) · GW3 · **REVISE** — Consider O'Nien to Egan with the free transfer: it fixes the clearest start-risk slot and…
- [02 Sep 12:03 CEST](reports/predeadline-gw3-20260902T100329Z.md) · GW3 · **REVISE** — Use the free transfer on O'Nien to Egan, retain Bruno Fernandes as captain, and recheck T…
- [28 Aug 06:55 CEST](reports/predeadline-gw2-20260828T045547Z.md) · GW2 · **REVISE** — Consider Gibbs-White to Cherki, then start João Pedro over Shaw and keep Bruno Fernandes…
<!-- recent-runs:end -->

## What you get

- **Pre-deadline review** — TLDR, recommended XI / captain / bench, transfer options (including cross-position restructures when sensible), hit advice with a moderate risk bar, chip hints, and a **Why** section with only news pages the review actually opened.
- **Overnight price watch** — automated report on whether to lock a move before a likely rise/fall (plan-gated: it won't chase random template rises).
- **After the deadline** — optional scorecard comparing what we recommended vs official points for that gameweek.

Numbers (xP, prices, legality) are computed in code. An LLM only ranks and explains **legal candidates we already generated** — it cannot invent players, prices, or injuries.

## From your phone

**Prices** run overnight on GitHub. Watch the repo (or issue **FPL price alerts**) for email only when you should act. Reports appear in the list above.

**Squad news** — about a day before the gameweek deadline:

1. Cursor mobile → **Cloud Agent** on this repo (not a local session on a sleeping laptop).
2. Cloud secrets: `OPENAI_API_KEY` and `FPL_PRIVATE_STATE_B64`. Python 3.12 + `uv`.
3. Prompt: `Run the pre-deadline review.`
4. The agent lists the saved squad and waits. Reply **unchanged**, or send an FPL screenshot if the team changed. A pitch or transfers screenshot is enough — it maps **printed name + opponent line under the name** (`Raya|COV|H|6.0`), not kits or last-season clubs.
5. Leave Cursor's model on **Auto**. OpenAI inside `predeadline` uses the **`gpt-5.6`** alias (current GPT-5.6 Sol), not a dated snapshot.
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
uv run fpl-agent team-state names          # show saved squad (no secrets printed)
uv run fpl-agent predeadline --live-ai     # full review; add --force outside ~24h window
uv run fpl-agent scorecard -g 3             # last week's plan vs official points
uv run fpl-agent prices                    # overnight-style price watch (no OpenAI)
uv run fpl-agent prices-scorecard          # price prediction accuracy (optional)
uv run fpl-agent prices-watchdog           # alert if overnight price job looks skipped
uv run pytest
```

Reports: `reports/prices-gw*.md` and `reports/predeadline-gw*.md`. JSON next to them stays local.

Private squad files stay on your machine (`data/private-state/`). They are gitignored and never committed. The assistant never mutates your FPL team.

Overnight price watch runs on GitHub (`fpl-prices.yml`, 20:00 Zagreb). GitHub cron can still fire late; the job skips ticks before 20:00 local and skips if it already succeeded that day. A second workflow (`fpl-prices-watchdog.yml`) comments if that job is more than 26 hours late.
