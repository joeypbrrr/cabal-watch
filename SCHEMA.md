# cabal-watch research data contract (v1)

The site reads these seven JSON objects from `data/*.json`. If a live file is missing, it falls back to `data/sample/*.json` and shows an example-data banner. Sample files set `example: true` and `status: "example"`. The files committed in `data/` are the research snapshot (`status: "snapshot_only_monitor_not_running"`). The monitor in `monitor/` can rewrite the output directory later. It had not been started when those snapshot files were saved.

Every file includes:

- `schema_version`: `1`
- `updated_at`: ISO-8601 timestamp with an America/New_York offset
- `timezone`: `"America/New_York"`
- `status`: `"snapshot_only_monitor_not_running"` while the file is still the saved snapshot, `"monitor_running"` after the monitor rewrites it, or `"example"` in `data/sample/`

Percent fields use 0–100, not fractions. Unknown is null, never zero. The monitor must not invent signatures, market caps, balances, or wallet links.

## wallets.json

`wallets[]`: `{address, label, role, watch, tokens:[{mint, symbol, pct_held, as_of}], solscan_url, cluster_membership_verified, reported_cluster_id?, associated_mints?}`.

Exchange and service wallets have `watch: false`. Only the five screenshot-matched COGE holders carry `reported_cluster_id: "coge-screenshot-1"`. No ownership cluster is independently verified. Other COGE or Democat holders must not be turned into monitored cabal wallets.

## funding.json

`edges[]`: `{funder, wallet, amount_sol, time, slot, signature, method, source, tx_url, funder_label, funder_label_source, stop_reason}`.

`common_funders[]`: `{address, wallets_funded_in_sample, label, same_owner_proven}`.

A shared exchange hot wallet does not establish common ownership. `same_owner_proven` stays false for those wallets. The site must not label one as the cabal funder.

## transactions.json

`transactions[]`: `{address, signature, slot, time, type, mint, symbol, side, amount_sol, source}`. The free trades API does not return signatures. Rows from it set `signature` to null and keep `idx` so the stable identity is `(address, slot, idx, mint, side)`. Do not invent a signature.

`coverage`: `{wallets_queried, since, retention_start, pumpfun_and_pumpswap_only, api_returned_count, more}`, plus `as_of`.

## alerts.json

`alerts[]`: `{id, flag: "possible_next_play", mint, symbol, detected_at, mcap_at_detection, cluster_wallet_count, cluster_wallets, source}`.

`rule`: `{flag, trigger, excluded_mints, coach_mint_status}`.

Trigger when any screenshot-matched cluster wallet buys an unknown mint. COGE and the Democat candidate are excluded. Coach stays unresolved, so a name-only Coach coin is not silently excluded. Include `created_at` and `token_age_s` when a launch time is known. A new buy does not by itself mean the token just launched.

## paper.json

`paper[]`: `{alert_id, mint, entry_at, entry_mcap, checkpoints: {"15m": {due_at, observed_at, mcap, pnl_pct, status}, "1h": {...}, "6h": {...}}}`.

`model`: `{basis, formula, horizons_minutes, fees_slippage_included}`.

Basis is a market-cap return proxy: `(checkpoint_mcap / entry_mcap - 1) * 100`. It is not executable PnL. Unknown checkpoints stay null. Do not invent an entry after the fact. Keep the live quote time and how late the checkpoint was (`lateness_s` when observed).

## bubbles.json

`tokens[]`: `{mint, symbol, as_of, holders:[{address, pct_supply, cluster_id, reported_cluster_id}], links:[{source, target, kind: "first_inbound_SOL", amount_sol, time, signature, same_owner_proven}], source, cluster_verified}`.

`cluster_id` stays null until a graph is actually verified. `reported_cluster_id` is only the screenshot match. Exchange or service funding nodes may appear as links and must not become an ownership cluster. Holder coverage is the top token accounts summed to wallets, not all 63 screenshot addresses.

`requested_refresh_seconds`: `1800`.

## early_buys.json

`early_buys[]`: `{mint, symbol, first_buy_at, mcap_at_detection, cluster_wallet_count, total_sol, current_mcap}`.

`requested_refresh_seconds`: `1800`.

A newly seen buy is not proof the wallet was among the first buyers. Add `created_at`, `token_age_s`, `launch_slot`, and `early_buyer_proven` when those are known. `early_buyer_proven` stays false without that evidence.

## Monitor sources

Documented free API: [https://pumpdata.fun/openapi.json](https://pumpdata.fun/openapi.json). No key.

- `GET /trades/since.json?wallets=` up to 50 comma-separated addresses, `since` cursor, `limit` up to 2000. Buys and sells in the trailing three hours. Store `next_since`, follow `more`, dedupe on the stable identity, and honor rate limits.
- `GET /launches/since.json?deployer=` for named deployers' launches, not every token a wallet buys.
- `GET /price.json?mints=` up to 50, for market-cap checkpoints. Keep the observed time and source age.
- `GET /holders/<mint>.json` for the holder refresh. The source cache is about five minutes. `share` is a fraction of supply; store `share * 100` in percent fields.

Funding walks already in `funding.json` are historic first-inbound SOL. The monitor does not reclassify exchange withdrawals as cabal activity and does not send transactions. Bubble and early-buy rebuilds, and GitHub Pages publishes, run every 30 minutes. Trade polling is separate and more frequent.
