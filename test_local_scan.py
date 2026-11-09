"""本地历史扫描：同一 blob 只解析一次，并能从相邻行配对 base_url。"""

import os
import queue
import subprocess
import tempfile
import threading

from database import Database
from local_scanner import LocalScanner
from scanner import content_variants


KEY = "sk-proj-Qw9Rt8Yu7Ip6Lk5Jh4Gf3Ds2Az1Xc0Vb"
BODY = (
    "OPENAI_BASE_URL=https://api.internal-relay.invalid/v1\n"
    f"{KEY}\n"
)


def _git(root, *args, check=True):
    env = os.environ.copy()
    env.update({
        "GIT_AUTHOR_NAME": "scan-test",
        "GIT_AUTHOR_EMAIL": "scan-test@example.com",
        "GIT_COMMITTER_NAME": "scan-test",
        "GIT_COMMITTER_EMAIL": "scan-test@example.com",
    })
    return subprocess.run(
        ["git", "-C", root, *args],
        check=check,
        capture_output=True,
        text=True,
        env=env,
    )


def _commit_repo(root):
    _git(root, "init")
    settings = os.path.join(root, "app")
    os.makedirs(settings)
    with open(os.path.join(settings, "settings.py"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(BODY)
    copied = os.path.join(root, "copy")
    os.makedirs(copied)
    with open(os.path.join(copied, "settings.py"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(BODY)
    _git(root, "add", "app/settings.py", "copy/settings.py")
    _git(root, "commit", "-m", "add settings")
    os.remove(os.path.join(settings, "settings.py"))
    os.remove(os.path.join(copied, "settings.py"))
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "remove settings")


def _collect(root, db):
    found = queue.Queue()
    scanner = LocalScanner(root, found, threading.Event(), db=db, scan_git_history=True)
    scanner.run()
    rows = []
    while not found.empty():
        rows.append(found.get_nowait())
    return scanner.stats, rows


def test_content_variants_skip_identical_decode():
    assert list(content_variants("plain-text")) == ["plain-text"]
    variants = list(content_variants("sk-proj-abc%2Fdef"))
    assert variants[0] == "sk-proj-abc%2Fdef"
    assert variants[1] == "sk-proj-abc/def"


def test_history_reads_each_blob_once_and_pairs_base_url():
    with tempfile.TemporaryDirectory() as root:
        repo = os.path.join(root, "repo")
        os.makedirs(repo)
        _commit_repo(repo)
        db = Database(os.path.join(root, "keys.db"))
        stats, rows = _collect(repo, db)
        assert len(rows) == 1
        assert rows[0].platform == "openai"
        assert rows[0].api_key == KEY
        assert rows[0].base_url == "https://api.internal-relay.invalid/v1"
        assert "settings.py" in rows[0].source_url
        assert stats["blobs_scanned"] == 1
        assert stats["commits_scanned"] == 2

        again_stats, again_rows = _collect(repo, db)
        assert again_rows == []
        assert again_stats["blobs_scanned"] == 0


if __name__ == "__main__":
    test_content_variants_skip_identical_decode()
    test_history_reads_each_blob_once_and_pairs_base_url()
    print("local scan ok")
