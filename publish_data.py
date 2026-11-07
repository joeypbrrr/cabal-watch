#!/usr/bin/env python3
"""Copy cabal-watch JSON onto the gh-pages branch and push it.

The static site is served from gh-pages at
https://joeypbrrr.github.io/cabal-watch/. Hourly is not the cadence:
bubbles, early buys, and this publish step run every 30 minutes.

Live JSON is read from a local directory (default /workspace/cabal-watch/out).
Files marked example=true are refused, so sample data cannot land on the
live path. Tokens are never accepted as arguments.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = Path("/workspace/cabal-watch/out")
DEFAULT_WORK = Path("/tmp/cabal-watch-gh-pages")
BRANCH_DEFAULT = "gh-pages"
LIVE_FILES = (
    "wallets.json",
    "funding.json",
    "transactions.json",
    "alerts.json",
    "paper.json",
    "bubbles.json",
    "early_buys.json",
)
SITE_FILES = (
    "index.html",
    "favicon.svg",
    "manifest.webmanifest",
    ".nojekyll",
    "README.md",
    "SPEC.md",
    "SCHEMA.md",
)
SITE_DIRS = ("css", "js", "vendor")
FORBIDDEN_KEYS = {
    "private_key",
    "privatekey",
    "secret_key",
    "secretkey",
    "seed_phrase",
    "mnemonic",
    "keypair",
    "secret",
}
MAX_BYTES = 5_000_000
TOKEN_RE = re.compile(r"(https?://)([^/\s@]+)@")
ET = ZoneInfo("America/New_York")


def redact(text):
    return TOKEN_RE.sub(r"\1", text or "")


def git(cwd, *args, timeout=120, check=False):
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        timeout=timeout,
        env=env,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(redact((proc.stderr or proc.stdout or "git failed").strip()))
    return proc


def commit(cwd, message):
    git(cwd, "add", "-A")
    if git(cwd, "diff", "--cached", "--quiet").returncode == 0:
        return False
    proc = git(
        cwd,
        "-c", "user.name=joeypbrrr",
        "-c", "user.email=joeypbrrr@users.noreply.github.com",
        "commit", "-m", message,
    )
    if proc.returncode != 0:
        raise RuntimeError(redact(proc.stderr or proc.stdout or "commit failed"))
    return True


def remote_has_branch(remote, branch):
    proc = git(None, "ls-remote", "--heads", remote, f"refs/heads/{branch}", timeout=60)
    if proc.returncode != 0:
        raise RuntimeError("cannot read remote: " + redact(proc.stderr or proc.stdout))
    return bool(proc.stdout.strip())


def find_forbidden(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                return str(key)
            found = find_forbidden(value)
            if found:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = find_forbidden(value)
            if found:
                return found
    return None


def validate_live(path):
    if path.stat().st_size > MAX_BYTES:
        raise RuntimeError(f"{path.name} is larger than 5MB")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{path.name} is not valid JSON") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"{path.name} must be a JSON object")
    if data.get("example") is True or data.get("status") == "example":
        raise RuntimeError(f"{path.name} is example data and cannot be published as live data")
    if data.get("schema_version") not in (None, 1):
        raise RuntimeError(f"{path.name} has an unsupported schema_version")
    forbidden = find_forbidden(data)
    if forbidden:
        raise RuntimeError(f"{path.name} contains forbidden key {forbidden}")
    return data


def copy_tree_files(src_root, dest_root, relative):
    copied = []
    base = src_root / relative
    if not base.exists():
        return copied
    for src in base.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(src_root).as_posix()
        target = dest_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        copied.append(rel)
    return copied


def copy_site(root, dest):
    copied = []
    for rel in SITE_FILES:
        src = root / rel
        if not src.exists():
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        copied.append(rel)
    for folder in SITE_DIRS:
        copied.extend(copy_tree_files(root, dest, folder))
    copied.extend(copy_tree_files(root, dest, "data/sample"))
    marker = dest / ".nojekyll"
    if not marker.exists():
        marker.write_text("")
        copied.append(".nojekyll")
    return copied


def fill_missing_live(root, dest):
    """Seed gh-pages with the repo snapshot only when a live file is absent."""
    copied = []
    for name in LIVE_FILES:
        dest_path = dest / "data" / name
        src = root / "data" / name
        if dest_path.exists() or not src.exists():
            continue
        validate_live(src)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest_path)
        copied.append(f"data/{name}")
    return copied


def copy_live(source, dest):
    source = Path(source)
    if not source.is_dir():
        raise RuntimeError(f"source directory not found: {source}")
    copied = []
    found = False
    for name in LIVE_FILES:
        src = source / name
        if not src.exists():
            continue
        found = True
        validate_live(src)
        target = dest / "data" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        copied.append(f"data/{name}")
    if not found:
        raise RuntimeError(f"no live JSON files in {source}")
    return copied


def ensure_clone(work, remote, branch):
    if (work / ".git").exists():
        return "existing"
    if work.exists() and any(work.iterdir()):
        raise RuntimeError(f"{work} exists and is not a git checkout")
    if remote_has_branch(remote, branch):
        work.parent.mkdir(parents=True, exist_ok=True)
        proc = git(None, "clone", "--branch", branch, "--single-branch", remote, str(work), timeout=180)
        if proc.returncode != 0:
            raise RuntimeError("clone failed: " + redact(proc.stderr or proc.stdout))
        return "cloned"
    work.mkdir(parents=True, exist_ok=True)
    proc = git(None, "init", "-b", branch, str(work))
    if proc.returncode != 0:
        raise RuntimeError(redact(proc.stderr or proc.stdout))
    git(work, "remote", "add", "origin", remote, check=True)
    return "created"


def ensure_linked_worktree(root, work, branch):
    if (work / ".git").exists():
        return "existing"
    if work.exists() and any(work.iterdir()):
        raise RuntimeError(f"{work} exists and is not a git worktree")
    work.parent.mkdir(parents=True, exist_ok=True)
    fetched = git(root, "fetch", "origin", branch, timeout=120)
    if fetched.returncode != 0 and "couldn't find remote ref" not in (fetched.stderr or "").lower():
        # A missing branch is fine; other fetch errors are not.
        missing = "not found" in (fetched.stderr or "").lower() or "couldn't find remote ref" in (fetched.stderr or "").lower()
        if not missing:
            raise RuntimeError("fetch failed: " + redact(fetched.stderr or fetched.stdout))
    remote = git(root, "remote", "get-url", "origin", check=True).stdout.strip()
    if remote_has_branch(remote, branch):
        proc = git(root, "worktree", "add", "--force", "-B", branch, str(work), f"origin/{branch}")
        if proc.returncode != 0:
            raise RuntimeError(redact(proc.stderr or proc.stdout))
        return "worktree"
    proc = git(root, "worktree", "add", "--orphan", "-b", branch, str(work))
    if proc.returncode != 0:
        raise RuntimeError(redact(proc.stderr or proc.stdout))
    return "orphan"


def reset_to_origin(work, branch):
    fetched = git(work, "fetch", "origin", branch, timeout=120)
    if fetched.returncode != 0:
        text = (fetched.stderr or "").lower()
        if "couldn't find remote ref" in text or "not found" in text:
            return False
        raise RuntimeError("fetch failed: " + redact(fetched.stderr or fetched.stdout))
    if git(work, "rev-parse", "--verify", f"origin/{branch}").returncode != 0:
        return False
    git(work, "reset", "--hard", f"origin/{branch}", check=True)
    git(work, "clean", "-fd", check=True)
    return True


def push_with_retry(work, branch, recopy, retries=4):
    last = ""
    for attempt in range(retries):
        if attempt:
            reset_to_origin(work, branch)
            recopy()
            if not commit(work, _message("retry")):
                raise RuntimeError("retry had nothing to commit")
        proc = git(work, "push", "origin", f"HEAD:{branch}", timeout=180)
        if proc.returncode == 0:
            return
        last = redact(proc.stderr or proc.stdout)
        lowered = last.lower()
        if any(word in lowered for word in ("authentication", "permission", "403", "could not read")):
            raise RuntimeError(last)
    raise RuntimeError("push failed after retries: " + last)


def _message(kind):
    stamp = datetime.now(ET).strftime("%Y-%m-%d %H:%M %Z")
    label = "ET" if stamp.endswith(("EST", "EDT")) else stamp.split()[-1]
    # Always append the ET label the site uses, even when the abbreviation is EST/EDT.
    pretty = datetime.now(ET).strftime("%Y-%m-%d %H:%M")
    return f"{kind} {pretty} ET"


def _lock(work):
    import fcntl
    path = Path(str(work) + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("w")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise RuntimeError("another publish is already running") from exc
    return handle


def publish(root=None, source=None, site_only=False, remote=None, branch=BRANCH_DEFAULT, work=None, dry_run=False):
    root = Path(root or ROOT)
    source = Path(source or DEFAULT_SOURCE)
    work = Path(work or DEFAULT_WORK)
    if dry_run:
        files = [rel for rel in SITE_FILES if (root / rel).exists()] if site_only or not (source / "wallets.json").exists() else []
        if site_only:
            files = [rel for rel in SITE_FILES if (root / rel).exists()]
            files += [f"data/{name}" for name in LIVE_FILES if (root / "data" / name).exists()]
        else:
            files = []
            if not source.is_dir():
                raise RuntimeError(f"source directory not found: {source}")
            for name in LIVE_FILES:
                src = source / name
                if src.exists():
                    validate_live(src)
                    files.append(f"data/{name}")
            if not files:
                raise RuntimeError(f"no live JSON files in {source}")
        print("dry-run", "site" if site_only else "data", len(files), "files")
        return {"ok": True, "dry_run": True, "files": files}

    handle = _lock(work)
    try:
        if remote is None and (root / ".git").exists():
            remote = git(root, "remote", "get-url", "origin", check=True).stdout.strip()
            ensure_linked_worktree(root, work, branch)
        else:
            if remote is None:
                raise RuntimeError("no git remote")
            ensure_clone(work, remote, branch)
        if git(work, "rev-parse", "--verify", "HEAD").returncode == 0:
            reset_to_origin(work, branch)

        def recopy():
            copied = []
            if site_only or not (work / "index.html").exists():
                copied.extend(copy_site(root, work))
                copied.extend(fill_missing_live(root, work))
            if not site_only:
                copied.extend(copy_live(source, work))
            return copied

        copied = recopy()
        kind = "Site publish" if site_only else "Data publish"
        if not commit(work, _message(kind)):
            print("no changes")
            return {"ok": True, "published": None, "detail": "no changes", "files": copied}
        push_with_retry(work, branch, recopy)
        stamp = _message(kind)
        print("published", stamp, flush=True)
        return {"ok": True, "published": stamp, "files": copied}
    finally:
        handle.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Publish cabal-watch JSON to gh-pages")
    parser.add_argument("source", nargs="?", default=None, help="Directory of live JSON (default /workspace/cabal-watch/out)")
    parser.add_argument("--source", dest="source_opt", default=None)
    parser.add_argument("--site-only", action="store_true", help="Update the static site and keep live JSON already on gh-pages")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--branch", default=BRANCH_DEFAULT)
    parser.add_argument("--remote", default=None)
    parser.add_argument("--work", default=None)
    parser.add_argument("--root", default=None)
    args = parser.parse_args(argv)
    source = args.source_opt or args.source or DEFAULT_SOURCE
    try:
        result = publish(
            root=args.root,
            source=source,
            site_only=args.site_only,
            remote=args.remote,
            branch=args.branch,
            work=args.work,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print("publish failed:", redact(str(exc))[:500], file=sys.stderr, flush=True)
        return 1
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
