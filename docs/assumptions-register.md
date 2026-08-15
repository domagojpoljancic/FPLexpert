# Assumptions Register

| claim | type | source | last_checked | owner | expiry / recheck | safe fallback |
| --- | --- | --- | --- | --- | --- | --- |
| 2026/27 chips: two instances each of WC/FH/BB/TC; first set expires at GW19 deadline; only one chip per GW | documented | https://www.premierleague.com/en/news/4679879/whats-happening-with-fpl-chips-in-202627 | 2026-08-15 | rules | recheck on season announcement / bootstrap chip drift | fail-closed exit 8 |
| Free Hit unavailable GW1; FH in GW19 blocks FH in GW20 | documented | same chip article | 2026-08-15 | rules | same | refuse illegal chip scenarios |
| Bootstrap chip windows: WC/FH start_event=2 first half; BB/TC start_event=1 | observed_undocumented | https://fantasy.premierleague.com/api/bootstrap-static/ | 2026-08-15 | rules | `fpl-agent rules diff` each run | material drift → exit 8 |
| Initial budget 100.0m, squad 15, club limit 3, sell-on fee 0.5, max FT 5 (1+4 extra) | observed_undocumented | bootstrap `game_settings` | 2026-08-15 | rules | rules diff | fail-closed |
| Defensive contribution: DEF 10 CBIT → 2 pts; MID/FWD 12 CBIRT → 2 pts | documented | https://www.premierleague.com/en/news/4361991/whats-happening-with-defensive-contribution-points-in-202627-fantasy | 2026-08-15 | rules/projections | if PL republishes thresholds | keep thresholds in SeasonRules |
| GW scores provisional until 09:00 UK day after final match | documented | https://www.premierleague.com/en/news/4679873/all-you-need-to-know-about-changes-to-fpl-for-202627 | 2026-08-15 | evaluation | if lockdown guidance changes | require `data_checked` + time gate |
| Public picks do not prove unsubmitted pre-deadline squad | documented | product contract + FPL privacy model | 2026-08-15 | team_state | continuous | require private sync for EXECUTABLE |
| Selling-price article URL in prompt pack 404s; use bootstrap sell-on fee 0.5 + classic retain floor(rise/2) | unverified | prompt cited https://www.premierleague.com/en/news/2174907/1000 (404 on 2026-08-15); bootstrap `transfers_sell_on_fee` | 2026-08-15 | rules | find current official transfers article | property tests on 0.1–0.4 rises |
| FT preserved across Wildcard and Free Hit | documented | chip article wording + longstanding FPL behavior | 2026-08-15 | rules | re-verify if FPL changes chip FAQ | encode in SeasonRules flag |
| Projection v1 coefficients are transparent defaults, not validated football truth | unverified | methodology doc | 2026-08-15 | projections | after holdout backtest | label uncalibrated |
| OpenAI model IDs/prices in settings are placeholders pending live project proof | unverified | settings.yaml + https://developers.openai.com/api/docs/guides/tools-web-search | 2026-08-15 | llm | before pilot with real key | deterministic daily fallback without key |
| Responses API `web_search` with domain filters (incl. reddit.com as community tier) | documented | https://developers.openai.com/api/docs/guides/tools-web-search | 2026-08-15 | llm | if tool schema changes | skip live search / fallback |

| GitHub schedules can delay/drop; public inactivity can disable schedules | documented | GitHub Actions docs | 2026-08-15 | ops | before claiming unattended readiness | external watchdog required |
