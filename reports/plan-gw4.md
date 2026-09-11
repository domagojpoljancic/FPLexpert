# Season plan — Gameweek 4

Locked move: **Senesi → Egan** (plan **REVISE**).

## Why this move over the next weeks

Selling **Senesi** for **Egan** changes the XI projection across the planning horizon (GW4 +3.8, GW5 +1.1, GW6 +1.5, GW7 +1.0, GW8 +1.5, GW9 +1.6; +8.2 weighted overall). Adds +3.8 pts to the XI this GW and keeps paying later (GW5 +1.1, GW6 +1.5, GW7 +1.0; +8.2 weighted overall).

| GW | Hold XI xP | After XI xP | Delta |
| --- | ---: | ---: | ---: |
| 4 | 32.61 | 36.44 | +3.83 |
| 5 | 25.53 | 26.65 | +1.11 |
| 6 | 24.29 | 25.82 | +1.52 |
| 7 | 25.07 | 26.07 | +1.00 |
| 8 | 24.70 | 26.22 | +1.52 |
| 9 | 24.06 | 25.68 | +1.62 |

```mermaid
xychart-beta
    title "XI xP: hold vs Senesi to Egan"
    x-axis [GW4, GW5, GW6, GW7, GW8, GW9]
    y-axis "XI xP" 22 --> 38
    line [32.6, 25.5, 24.3, 25.1, 24.7, 24.1]
    line [36.4, 26.6, 25.8, 26.1, 26.2, 25.7]
```

## Spend now vs bank the free transfer

**Bank vs spend verdict: Bank the FT.** Bank the FT (1→2 next GW). Bank for 2 FT: dual-move horizon EV 11.2 beats act-now 8.2 (delta +2.9). (FT now 1 → 1 if you transfer, 2 if you roll; sequence bank_for_2ft (act-now 8.245, roll-to-2FT 11.19, hit 6.321); deferred dual-move upside +2.94; net after FT penalty +7.89; locked pick Senesi→Egan.)

```mermaid
flowchart LR
    A["GW4 locked: Senesi to Egan"]
    B["Bank FT"]
    C["Next GW: 2 FT if rolled"]
    D["Chips: play wildcard"]
    A --> B
    B --> C
    C --> D
```

## Bank and value after the move

The locked swap sells at £5.9m and buys at £4.1m, leaving **£1.8m** in the bank. Free transfers after acting: 1; after rolling: 2. Future affordability is this residual bank plus selling prices — not a forecast of price changes.

```mermaid
flowchart TD
    N0["FT now: 1"]
    N1["If transfer: FT 1 / £1.8m after move"]
    N2["If roll: FT 2"]
    N0 --> N1
    N0 --> N2
```

## Confirmed DGW / BGW in the horizon

Confirmed fixtures in horizon (GW4, GW5, GW6, GW7, GW8, GW9): no DGW/BGW flags from the feed.

```mermaid
flowchart LR
    G0["GW4 SGW"]
    G1["GW5 SGW"]
    G2["GW6 SGW"]
    G3["GW7 SGW"]
    G4["GW8 SGW"]
    G5["GW9 SGW"]
    G0 --> G1
    G1 --> G2
    G2 --> G3
    G3 --> G4
    G4 --> G5
```

## DGW / BGW priors (not confirmed)

No labelled DGW/BGW priors on this report (none invented by default).

## Chip timing

**3xc**: hold (available) — Captain mean xP 3.89 lacks ceiling for TC (haul proxy 0.00, need ≥0.25); hold until a genuine haul week (DGW detection pending). **bboost**: hold (available) — Bench xP 0.67 (need ≥8) or outfield start risk (min 0%) is not enough to spend Bench Boost. **freehit**: hold (available) — This week's XI xP 32.6 is close enough to the horizon median 24.7; hold Free Hit. **wildcard**: play (available) — even the best 2-transfer plan still nets +6.3 horizon pts after hits. That combination points to a rebuild, not a one-week Free Hit.

_Recommend only — you make all FPL changes. Numbers from the locked weekly primary; no second ranking._
