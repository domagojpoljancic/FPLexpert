# FPL Expert

Read-only Fantasy Premier League co-pilot. It recommends transfers, captain, bench, and price moves from your squad, fixtures, and news. **You** make every change in the official FPL app.

## Quick start

| | |
| --- | --- |
| **From your phone** | Cursor → Cloud Agent → `Run the pre-deadline review` |
| **Squad unchanged?** | Reply **unchanged** when the agent lists your team |
| **Squad changed?** | Send an FPL pitch or transfers screenshot |
| **From a laptop** | `uv run fpl-agent predeadline --live-ai` |
| **Too early / late?** | Add `--force` |
| **FPL API down?** | Add `--offline` |

Overnight **price watch** runs on GitHub (20:00 Zagreb). **Squad news** runs when you trigger the agent ~24h before the deadline. Reports are linked below.

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
- [02 Sep 21:49 CEST](reports/predeadline-gw3-20260902T194928Z.md) · GW3 · **REVISE** — Consider Virgil to De Cuyper, keep Bruno Fernandes captain, and do not spend a chip.
- [02 Sep 21:48 CEST](reports/predeadline-gw3-20260902T194829Z.md) · GW3 · **REVISE** — Consider Virgil to De Cuyper, captain Bruno Fernandes, and confirm the move only after th…
- [02 Sep 21:20 CEST](reports/predeadline-gw3-20260902T192018Z.md) · GW3 · **REVISE** — Consider Virgil to Ajayi with the free transfer, keep Bruno Fernandes captain, and wait f…
- [02 Sep 19:44 CEST](reports/predeadline-gw3-20260902T174456Z.md) · GW3 · **REVISE** — Consider Virgil to Ajayi, start Ajayi, and captain Bruno Fernandes, but check late team n…
- [02 Sep 14:55 CEST](reports/predeadline-gw3-20260902T125520Z.md) · GW3 · **REVISE** — Consider Virgil to Ajayi with the free transfer, subject to a final availability check ne…
- [02 Sep 14:34 CEST](reports/predeadline-gw3-20260902T123407Z.md) · GW3 · **REVISE** — Consider O'Nien to Egan with the free transfer: it fixes the clearest start-risk slot and…
- [02 Sep 12:03 CEST](reports/predeadline-gw3-20260902T100329Z.md) · GW3 · **REVISE** — Use the free transfer on O'Nien to Egan, retain Bruno Fernandes as captain, and recheck T…
<!-- recent-runs:end -->

---

## Details

### What you get

- **Pre-deadline review** — TLDR, XI / captain / bench, transfer options (including when to spend vs bank a free transfer), chip hints, and a **Why** section from news the run actually opened.
- **Overnight price watch** — whether to lock a move before a likely rise or fall (plan-gated; it won't chase random template moves).
- **After the deadline** (optional) — `uv run fpl-agent scorecard -g N` compares the last plan to official points.

Numbers (xP, prices, legality) are computed in code. The LLM only explains **legal candidates we already generated** — it cannot invent players, prices, or injuries.

### From your phone

1. Cursor mobile → **Cloud Agent** on this repo.
2. Prompt: `Run the pre-deadline review.`
3. Confirm **unchanged** or send an FPL screenshot if the team changed.
4. Read the report in chat and in the list above. You still transfer in the FPL app.

Cloud needs `OPENAI_API_KEY` and `FPL_PRIVATE_STATE_B64`. The agent publishes reports to `main` so the links above work from your phone.

For **price alerts**, watch the repo or enable issue **FPL price alerts** — email only when you should act.

### After you change your squad

Re-encode private state for GitHub / Cloud Agent:

```bash
uv run fpl-agent team-state encode-for-github data/private-state/current.json
```

Screenshot mapping (printed name + opponent line under the name, not kits):

```bash
uv run fpl-agent team-state lookup -- "Raya|CHE|H|6.0|GKP" "Virgil|IPS|A|6.5|DEF"
```

### On a laptop

```bash
uv sync
uv run fpl-agent team-state names          # saved squad (no secrets printed)
uv run fpl-agent predeadline --live-ai     # full review
uv run fpl-agent scorecard -g 3            # plan vs official points
uv run fpl-agent prices                    # price watch (no OpenAI)
uv run fpl-agent prices-scorecard          # prediction accuracy (optional)
uv run fpl-agent prices-watchdog           # alert if overnight job skipped
uv run pytest
```

Reports live in `reports/`. Private squad files stay in `data/private-state/` (gitignored). The assistant never logs into FPL or mutates your team.

### Automation

- **Prices:** GitHub Actions `fpl-prices.yml` at 20:00 Zagreb daily.
- **Watchdog:** `fpl-prices-watchdog.yml` comments if the price job is more than 26 hours late.
