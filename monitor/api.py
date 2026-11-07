"""Keyless GET client for pumpdata.fun. This module never sends a transaction."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE = "https://pumpdata.fun"
USER_AGENT = "cabal-watch-monitor/1.0 (read-only; no transactions)"


class ApiError(RuntimeError):
    def __init__(self, status, message, retry_after=None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


class Client:
    def __init__(self, base=DEFAULT_BASE, opener=None, sleep=None, min_interval=1.1, clock=None, max_retries=4):
        self.base = base.rstrip("/")
        self.opener = opener or urllib.request.build_opener()
        self.sleep = sleep or time.sleep
        self.min_interval = min_interval
        self.clock = clock or time.monotonic
        self.max_retries = max_retries
        self._last = 0.0

    def _wait(self):
        elapsed = self.clock() - self._last
        if elapsed < self.min_interval:
            self.sleep(self.min_interval - elapsed)
        self._last = self.clock()

    def get_json(self, path, params=None):
        query = urllib.parse.urlencode({key: value for key, value in (params or {}).items() if value is not None})
        url = self.base + path + (("?" + query) if query else "")
        attempt = 0
        while True:
            attempt += 1
            self._wait()
            request = urllib.request.Request(url, method="GET", headers={"Accept": "application/json", "User-Agent": USER_AGENT})
            if request.get_method() != "GET":
                raise RuntimeError("refusing non-GET request")
            try:
                with self.opener.open(request, timeout=30) as response:
                    status = getattr(response, "status", 200)
                    body = response.read()
                    headers = getattr(response, "headers", {})
            except urllib.error.HTTPError as exc:
                status = exc.code
                body = exc.read()
                headers = exc.headers or {}
                if status in (429, 503) and attempt < self.max_retries:
                    self.sleep(_retry_after(headers))
                    continue
                raise ApiError(status, f"{path} returned {status}") from exc
            except urllib.error.URLError as exc:
                if attempt < self.max_retries:
                    self.sleep(min(2 ** attempt, 30))
                    continue
                raise ApiError(0, f"{path} failed: {exc.reason}") from exc
            if status in (429, 503) and attempt < self.max_retries:
                self.sleep(_retry_after(headers))
                continue
            if status >= 400:
                raise ApiError(status, f"{path} returned {status}")
            try:
                return json.loads(body.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise ApiError(status, f"{path} was not JSON") from exc

    def trades(self, wallets, since=None, limit=2000):
        params = {"wallets": ",".join(wallets), "limit": str(limit)}
        if since is not None:
            params["since"] = str(int(since))
        return self.get_json("/trades/since.json", params)

    def launches(self, deployer, cursor=None, limit=500):
        params = {"deployer": deployer, "limit": str(limit)}
        if cursor is not None:
            params["t"] = str(int(cursor))
        return self.get_json("/launches/since.json", params)

    def prices(self, mints):
        unique = list(dict.fromkeys(mint for mint in mints if mint))
        if not unique:
            return {"prices": []}
        if len(unique) > 50:
            unique = unique[:50]
        return self.get_json("/price.json", {"mints": ",".join(unique)})

    def holders(self, mint):
        return self.get_json(f"/holders/{urllib.parse.quote(mint, safe='')}.json")


def _retry_after(headers):
    raw = None
    if headers is not None:
        getter = getattr(headers, "get", None)
        raw = getter("Retry-After") if getter else None
    try:
        seconds = float(raw)
    except (TypeError, ValueError):
        seconds = 5
    return max(1.0, min(seconds, 120.0))


def price_map(payload):
    found = {}
    for row in (payload or {}).get("prices") or []:
        if isinstance(row, dict) and row.get("mint"):
            row = dict(row)
            if payload and payload.get("as_of") and "as_of" not in row:
                row["as_of"] = payload.get("as_of")
            found[row["mint"]] = row
    return found


def launch_rows(payload):
    columns = (payload or {}).get("columns") or []
    rows = []
    for raw in (payload or {}).get("launches") or []:
        if isinstance(raw, dict):
            rows.append(raw)
        elif isinstance(raw, list):
            rows.append(dict(zip(columns, raw)))
    return rows
