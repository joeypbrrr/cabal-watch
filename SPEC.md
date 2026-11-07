# Cabal Watch spec

This is the permanent spec for the read-only dashboard and monitor. The JSON shapes live in [SCHEMA.md](SCHEMA.md). The committed files in `data/` are a saved research snapshot. They are not a claim that a monitor is running.

## Safety

Cabal Watch reads public Solana data and writes JSON. It does not hold keys, sign transactions, or send transactions. Paper results are simulated market-cap changes, not orders.

## What we are tracking

From the owner's screenshot `IMG_4522.png` (Bubblemaps Cluster 1), the working claim is:

- The cabal is one entity controlling about 63 linked wallets.
- Those wallets hold about 44.65% of COGE supply.
- The wallets hold nearly identical amounts, about 0.60–0.65 SOL each.
- They enter early, around a $200K market cap, on tokens such as Democrat / Democat and Coach.
- Those tokens get pushed toward about a $1M market cap.
- Watch the wallets 24/7 and trace them back to a main funding wallet.
- Watch their transactions for new token launches.
- When any cluster wallet buys a new token that is not Coach or another already-known cabal token, flag it as a **possible next cabal play** and record the market cap at detection.
- Refresh the bubble cluster map and the new-token / early-buy list every 30 minutes.
- Show a new-coin detection section.
- Paper-track result before any real money.

Those bullets are the brief. They are not, by themselves, measurements in `data/`.

## What the saved snapshot actually shows

`research/summary.json` and `data/*.json` were written with `status: "snapshot_only_monitor_not_running"`. Read them as a snapshot:

- COGE mint: `8UQdy5sHMVWUWSHeA5B3ZuuAVNumjSLPXdf19MXcpump`.
- Five of eight screenshot wallets were resolved to full addresses. Three stayed partial (`EjG4k8…wVeN`, `GkDuii…a9C2`, `H4emhJ…aUrY`). The other wallets in a 63-wallet cluster were not reconstructed.
- No ownership cluster was independently verified. `cluster_membership_verified` is false. `cluster_id` is null. `reported_cluster_id: "coge-screenshot-1"` means a screenshot match only.
- Other COGE or Democat holders are not silently treated as monitored cabal wallets.
- Funding walks for the resolved wallets stop at exchange or service hot wallets (Binance, Bybit, Gate, Kraken, SideShift, Relay) or at an unlabeled busy wallet. A shared Gate hot wallet funded two of them. That does not prove one owner. No private common funder was found. The site must say so, and must not present a shared exchange wallet as the cabal funder.
- Democat candidate mint `9Y1F6dZ6HpjZDYZdYuUGwMbkUiPsyU7WPTqTQU4Tpump` is not confirmed.
- Coach is unresolved. Do not treat a name-only Coach coin as the cabal's Coach.
- The 0.60–0.65 SOL size, the $200K entry, and the $1M push were not independently verified in this snapshot. Do not display them as measurements.
- `transactions`, `alerts`, `paper`, and `early_buys` are empty. Empty means this snapshot has no rows. It does not mean the wallets were idle outside the window.

## Detection rule

Flag `possible_next_play` when a screenshot-matched cluster wallet buys a mint that is not already known.

- Screenshot-matched means `role` is `screenshot_matched_coge_holder` or `reported_cluster_id` is `coge-screenshot-1`. A deployer, an early buyer, or any other holder does not trip the flag by itself.
- Already-known mints excluded today: COGE `8UQdy5sHMVWUWSHeA5B3ZuuAVNumjSLPXdf19MXcpump`, and the Democat candidate `9Y1F6dZ6HpjZDYZdYuUGwMbkUiPsyU7WPTqTQU4Tpump`.
- Coach is an already-known name in this brief, but no Coach mint is confirmed. Do not skip an alert only because a token's name or ticker is Coach. Exclude a Coach mint only after one is confirmed and written into `excluded_mints`.
- Record market cap at detection from the price source. If that source has no figure, store null. Do not invent a market cap.
- A new buy is not proof the token just launched and is not proof the wallet was an early buyer. When a launch record is known, store `created_at` and `token_age_s`. Leave them null when they are not known.

The alerts section on the site uses this wording.

## Cadence

| Work | Interval |
| --- | --- |
| Wallet trade poll (watched wallets only) | About every 3 minutes, inside a 2–5 minute range |
| Bubble map (`bubbles.json`) | Every 30 minutes |
| New-token / early-buy list (`early_buys.json`) | Every 30 minutes |
| Publish JSON to GitHub Pages | Every 30 minutes |
| Page re-read of the JSON files | Every 60 seconds |

`bubbles.json` and `early_buys.json` carry `requested_refresh_seconds: 1800`. The site labels those sections as updated every 30 minutes and shows the file time in America/New_York with an ET label.

## Paper tracking

Paper rows are a simulated market-cap return, not a fill and not dollars.

`pnl_pct = (checkpoint_mcap / entry_mcap - 1) * 100` at +15 minutes, +1 hour, and +6 hours. Fees and slippage are not included. A checkpoint stays null until it is due and a live quote is observed. The observed time and how late it is are kept. Missing prices stay null. No backfilled entry is invented for an alert that was not seen live.

## Pages

The static site is published on the `gh-pages` branch and served at `https://joeypbrrr.github.io/cabal-watch/`. `publish_data.py` copies monitor JSON from a local directory (default `/workspace/cabal-watch/out`) onto that branch. Sample files in `data/sample/` are fictional and stay out of that live path.
