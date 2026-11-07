# Cabal Watch

Read-only research page for a suspected Solana bundle. It reads public JSON and draws it. It does not hold keys, sign transactions, or send transactions.

Live page: https://joeypbrrr.github.io/cabal-watch/

The tracking brief is [SPEC.md](SPEC.md). The JSON contract is [SCHEMA.md](SCHEMA.md).

## What the page shows

A summary strip, then the sections below it:

1. Wallets, with plain-language roles, percent of supply, and links to [Solscan](https://solscan.io) and [GMGN](https://gmgn.ai).
2. The funding trail. Exchange and busy service wallets are labeled as such. A shared exchange wallet is not shown as the cabal funder.
3. A bubble map for COGE, Democat, Coach, and new launches. Size is percent of supply. The map and the new-launch list are rebuilt every 30 minutes. The page shows that time in Eastern Time.
4. Recent trades, with times in America/New_York labeled ET.
5. Possible next cabal plays: a screenshot-matched wallet buys a token that is not COGE or the Democat candidate. Coach has no confirmed mint, so a name alone does not skip the flag. Market cap at detection is shown when the price source had one.
6. New launches the matched wallets bought, with mint, DexScreener link, first seen time, market cap, wallet count, combined SOL, and current market cap.
7. Paper tracking. Simulated market-cap change at +15 minutes, +1 hour, and +6 hours. Not an order.

The page re-reads the JSON files every 60 seconds. The bubble map and the new-launch list themselves are refreshed every 30 minutes by the monitor.

`data/*.json` in this repo is a saved snapshot (`status: "snapshot_only_monitor_not_running"`). Empty alerts, trades, paper rows, and early buys are empty on purpose. `data/sample/*.json` is fictional example data. The page shows an example-data banner only when it had to fall back to those samples.

COGE mint: `8UQdy5sHMVWUWSHeA5B3ZuuAVNumjSLPXdf19MXcpump`. The Democat candidate `9Y1F6dZ6HpjZDYZdYuUGwMbkUiPsyU7WPTqTQU4Tpump` is not confirmed. Coach is unresolved.

## Publish

GitHub Pages serves the `gh-pages` branch at `/`. `publish_data.py` copies live JSON from a directory on the machine that runs the monitor. The default directory is `/workspace/cabal-watch/out`. Example files are refused.

```bash
python3 publish_data.py
python3 publish_data.py /workspace/cabal-watch/out
python3 publish_data.py --dry-run
python3 publish_data.py --site-only
```

`--site-only` updates the HTML, CSS, and JavaScript and leaves live JSON already on `gh-pages` in place. If a live file is missing, it is seeded from `data/` in this repo. A push to `main` runs that step in `.github/workflows/pages.yml`.

The monitor calls `publish_data.py` every 30 minutes. One manual Pages setting is required if it is not already on: Settings → Pages → Deploy from branch → `gh-pages` → `/ (root)`. `.nojekyll` is included so the JSON is served as files.

## Monitor

The monitor is a Python 3 program in `monitor/`. It uses only the standard library and the keyless [pumpdata.fun](https://pumpdata.fun/openapi.json) API:

- `GET /trades/since.json` for watched wallets (`watch: true`), about every 3 minutes
- `GET /launches/since.json` for watched deployers
- `GET /price.json` for market caps
- `GET /holders/<mint>.json` when rebuilding bubbles

It writes `transactions.json`, `alerts.json`, and `paper.json` from what those calls return. It rebuilds `bubbles.json` and `early_buys.json` every 30 minutes. It does not invent signatures, prices, or a common owner. Exchange wallets stay `watch: false`.

Start it on the machine that should publish:

```bash
chmod +x run_monitor.sh
./run_monitor.sh
```

`run_monitor.sh` restarts the process if it exits. The output directory defaults to `/workspace/cabal-watch/out`. Override it with `CABAL_WATCH_OUT`.

One cycle, without publishing:

```bash
python3 -m monitor --out /workspace/cabal-watch/out --once --no-publish
```

State is kept in `monitor_state.json` in that output directory and is not one of the seven published files.

## Tests

```bash
python3 -m unittest tests.test_logic tests.test_monitor tests.test_publish tests.test_contract
```

## Schema

Each of the seven files is a JSON object with `schema_version`, `updated_at` (Eastern offset), `timezone`, and `status`. Percents are 0–100. Unknown is null.

| File | Rows |
| --- | --- |
| `wallets.json` | `wallets[]`: address, label, role, watch, token percents, Solscan URL, verified flag |
| `funding.json` | `edges[]` first inbound SOL, `common_funders[]` with `same_owner_proven` |
| `transactions.json` | trades; `signature` is null when the free API has none; `idx` keeps the identity |
| `alerts.json` | `flag: "possible_next_play"`, mint, detection time, market cap, matched wallets |
| `paper.json` | checkpoints `15m`, `1h`, `6h`; pnl is `(mcap / entry_mcap - 1) * 100` |
| `bubbles.json` | holders and first-SOL links; `requested_refresh_seconds: 1800` |
| `early_buys.json` | new tokens the matched wallets bought; same 30-minute refresh |

Field-level detail is in [SCHEMA.md](SCHEMA.md).
