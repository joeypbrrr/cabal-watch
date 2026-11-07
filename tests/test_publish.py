"""gh-pages publish keeps the publisher's JSON and refuses example files."""
from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from publish_data import commit, publish


def git(cwd, *args, check=True):
    proc = subprocess.run(
        ["git", "-c", "user.name=Cabal Watch Test", "-c", "user.email=test@example.com", *args],
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
    )
    if check and proc.returncode != 0:
        raise AssertionError(proc.stderr or proc.stdout)
    return proc


def live(name="wallets.json", example=False, body=None):
    payload = body or {
        "schema_version": 1,
        "updated_at": "2026-11-07T12:00:00-05:00",
        "timezone": "America/New_York",
        "status": "example" if example else "monitor_running",
        "wallets": [{"address": "wallet", "watch": True}],
    }
    if example:
        payload["example"] = True
    return name, json.dumps(payload) + "\n"


class Publish(unittest.TestCase):
    def test_example_file_is_refused(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "out"
            source.mkdir()
            name, text = live(example=True)
            (source / name).write_text(text)
            bare = root / "bare.git"
            git(None, "init", "--bare", "-b", "gh-pages", str(bare))
            with self.assertRaises(RuntimeError):
                publish(root=root, source=source, remote=str(bare), work=root / "work", branch="gh-pages")
            heads = git(None, "ls-remote", "--heads", str(bare)).stdout
            self.assertNotIn("gh-pages", heads)

    def test_data_publish_and_site_only_preserves_live_json(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.html").write_text("<p>v1</p>\n")
            (root / "data").mkdir()
            source = root / "out"
            source.mkdir()
            _name, text = live(body={
                "schema_version": 1,
                "updated_at": "2026-11-07T12:00:00-05:00",
                "timezone": "America/New_York",
                "status": "monitor_running",
                "wallets": [{"address": "live-wallet"}],
            })
            (source / "wallets.json").write_text(text)
            (root / "data" / "wallets.json").write_text(json.dumps({
                "schema_version": 1, "status": "snapshot_only_monitor_not_running", "wallets": [{"address": "repo-wallet"}],
            }) + "\n")
            bare = root / "bare.git"
            work = root / "work"
            git(None, "init", "--bare", "-b", "gh-pages", str(bare))
            first = publish(root=root, source=source, remote=str(bare), work=work, branch="gh-pages")
            self.assertTrue(first["published"])
            (root / "index.html").write_text("<p>v2</p>\n")
            second = publish(root=root, source=source, remote=str(bare), work=work, branch="gh-pages", site_only=True)
            self.assertTrue(second["published"])
            check = root / "check"
            git(None, "clone", str(bare), str(check))
            self.assertIn("v2", (check / "index.html").read_text())
            saved = json.loads((check / "data" / "wallets.json").read_text())
            self.assertEqual(saved["wallets"][0]["address"], "live-wallet")

    def test_retry_keeps_remote_note_and_new_json(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.html").write_text("site\n")
            source = root / "out"
            source.mkdir()
            (source / "wallets.json").write_text(json.dumps({
                "schema_version": 1, "status": "monitor_running", "wallets": [{"address": "v1"}],
            }) + "\n")
            bare = root / "bare.git"
            work = root / "work"
            git(None, "init", "--bare", "-b", "gh-pages", str(bare))
            publish(root=root, source=source, remote=str(bare), work=work, branch="gh-pages")
            other = root / "other"
            git(None, "clone", str(bare), str(other))
            (other / "NOTE").write_text("from the other side\n")
            git(other, "add", "NOTE")
            git(other, "commit", "-m", "remote moved")
            git(other, "push", "origin", "HEAD:gh-pages")
            (source / "wallets.json").write_text(json.dumps({
                "schema_version": 1, "status": "monitor_running", "wallets": [{"address": "v2"}],
            }) + "\n")
            publish(root=root, source=source, remote=str(bare), work=work, branch="gh-pages")
            check = root / "check"
            git(None, "clone", str(bare), str(check))
            self.assertEqual(json.loads((check / "data" / "wallets.json").read_text())["wallets"][0]["address"], "v2")
            self.assertIn("other side", (check / "NOTE").read_text())

    def test_forbidden_key_is_refused(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "out"
            source.mkdir()
            (source / "wallets.json").write_text(json.dumps({
                "schema_version": 1, "wallets": [], "private_key": "nope",
            }) + "\n")
            with self.assertRaises(RuntimeError):
                publish(root=root, source=source, dry_run=True)

    def test_commit_helper_is_quiet_when_clean(self):
        with TemporaryDirectory() as tmp:
            repo = Path(tmp)
            git(None, "init", "-b", "main", str(repo))
            (repo / "a.txt").write_text("a\n")
            self.assertTrue(commit(repo, "first"))
            self.assertFalse(commit(repo, "second"))


if __name__ == "__main__":
    unittest.main()
