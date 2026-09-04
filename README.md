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
- [03 Sep 23:36 CEST](reports/prices-gw3-20260903T213651Z.md) · GW3 · **WATCH** — Watch list only — do not churn for £0.1m.
- [02 Sep 23:41 CEST](reports/prices-gw3-20260902T214102Z.md) · GW3 · **WATCH** — Watch list only — do not churn for £0.1m.
- [01 Sep 23:40 CEST](reports/prices-gw3-20260901T214030Z.md) · GW3 · **NO ACTION** — No price action tonight.
- [01 Sep 01:09 CEST](reports/prices-gw3-20260831T230954Z.md) · GW3 · **NO ACTION** — No price action tonight.
- [30 Aug 23:52 CEST](reports/prices-gw3-20260830T215242Z.md) · GW3 · **NO ACTION** — No price action tonight.
- [29 Aug 23:36 CEST](reports/prices-gw3-20260829T213616Z.md) · GW3 · **NO ACTION** — No price action tonight.
- [29 Aug 04:02 CEST](reports/prices-gw3-20260829T020207Z.md) · GW3 · **NO ACTION** — No price action tonight.

**Squad news** (pre-deadline — last 7 days)
- [04 Sep 17:25 CEST](reports/predeadline-gw3-20260904T152555Z.md) · GW3 · **REVISE** — Sell Shaw for De Cuyper, start De Cuyper (bench Virgil), and captain B.Fernandes.
- [04 Sep 17:08 CEST](reports/predeadline-gw3-20260904T150826Z.md) · GW3 · **REVISE** — Sell O'Nien for Ajayi, start Ajayi (bench Virgil), and captain B.Fernandes.
- [04 Sep 16:55 CEST](reports/predeadline-gw3-20260904T145522Z.md) · GW3 · **REVISE** — Sell O'Nien for Egan, start Egan (bench Virgil), and captain B.Fernandes.
- [04 Sep 16:13 CEST](reports/predeadline-gw3-20260904T141311Z.md) · GW3 · **REVISE** — Sell O'Nien for Egan, start Egan (bench Virgil), and captain B.Fernandes.
<!-- recent-runs:end -->

---

## Details

### What you get

- **Pre-deadline review** — TLDR, XI / captain / bench, transfer options (including when to spend vs bank a free transfer), chip hints, and a **Why** section from news the run actually opened.
- **Overnight price watch** — whether to lock a move before a likely rise or fall (plan-gated; it won't chase random template moves).
- **After the deadline** (optional) — `uv run fpl-agent scorecard -g N` compares the last plan to official points.

Numbers (xP, prices, legality) are computed in code. The LLM only explains **legal candidates we already generated** — it cannot invent players, prices, or injuries.

**How to read the advice**

1. **Projected points decide the XI and transfers** — not “who has the easier fixture” and not start%. The model picks the 11 highest projected scores that fit a legal formation (e.g. only 3 defenders start in a 3-5-2).
2. **Start% is a footnote** — used when someone is unlikely to play (rotation / injury risk). It is not why a high-start% player gets benched.
3. **Easier club ≠ more points** — clean sheets and attacking returns are already baked into the points projection. Example: after buying Ajayi/Egan (~5 pts), Virgil (~2 pts) can sit even vs an easier opponent because there are only three defender slots and the new buy outscores him.

Fixtures still matter as colour in the Why text; they do not override the points ranking. When two buys for the same sale are within ~0.5 pts this week, ranking prefers the better next-few-GW outlook. The named free transfer is always the engine pick — the model cannot swap it for another near-tied defender between reruns.

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
