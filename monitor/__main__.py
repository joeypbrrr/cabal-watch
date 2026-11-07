"""Start the read-only monitor: python3 -m monitor --out /workspace/cabal-watch/out"""
from __future__ import annotations

import argparse
import sys

from monitor.service import Monitor


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only Cabal Watch monitor. Never sends a transaction.")
    parser.add_argument("--out", default="/workspace/cabal-watch/out", help="Directory for JSON output")
    parser.add_argument("--seed", default=None, help="Directory of seed JSON (default: repo data/)")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    parser.add_argument("--no-publish", action="store_true", help="Do not call publish_data.py")
    parser.add_argument("--trade-seconds", type=int, default=180, help="Pause between trade polls (120–300)")
    parser.add_argument("--slow-seconds", type=int, default=1800, help="Bubble and early-buy rebuild interval")
    args = parser.parse_args(argv)
    trade_seconds = min(300, max(120, args.trade_seconds))
    monitor = Monitor(
        out=args.out,
        seed_dir=args.seed,
        publish=not args.no_publish,
        trade_poll_s=trade_seconds,
        slow_s=args.slow_seconds,
        publish_s=args.slow_seconds,
        once=args.once,
    )
    try:
        return monitor.run()
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
