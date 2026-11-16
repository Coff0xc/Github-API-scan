"""本地历史扫描：同一 blob 只解析一次，并能从相邻行配对 base_url。"""

import asyncio
import inspect
import os
import queue
import subprocess
import tempfile
import threading
import time

from database import Database, KeyStatus
from local_scanner import LocalScanner, run_local_scan
from scanner import ScanResult, content_variants


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


def test_run_local_scan_uses_optimized_validator():
    source = inspect.getsource(run_local_scan)
    assert "validator_optimized" in source
    assert "from validator import start_validators" not in source
    assert "AsyncDatabase" in source


def test_worker_source_has_no_second_engine():
    from validator_optimized import optimized_validator_worker

    source = inspect.getsource(optimized_validator_worker)
    assert "validate_key_async" not in source
    assert "validate_result(" in source


def test_take_queued_result_from_sync_queue():
    from validator_optimized import take_queued_result

    pending = queue.Queue()
    item = ScanResult(
        platform="openai",
        api_key=KEY,
        base_url="https://api.openai.com/v1",
        source_url="local",
    )

    async def run():
        pending.put(item)
        got = await take_queued_result(pending, timeout=1.0)
        assert got is item
        try:
            await take_queued_result(pending, timeout=0.05)
        except asyncio.TimeoutError:
            return
        raise AssertionError("empty sync queue should time out")

    asyncio.run(run())


def test_optimized_worker_drains_sync_queue_and_upserts(monkeypatch):
    from async_database import AsyncDatabase
    from validator import ValidationResult
    from validator_optimized import OptimizedAsyncValidator, start_validators

    async def fake_openai(self, api_key, base_url):
        return ValidationResult(KeyStatus.INVALID, "auth failed")

    monkeypatch.setattr(OptimizedAsyncValidator, "validate_openai", fake_openai)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as root:
        path = os.path.join(root, "keys.db")
        async_db = AsyncDatabase(path)
        asyncio.run(async_db.init())
        pending = queue.Queue()
        stop = threading.Event()
        threads = start_validators(
            pending, async_db, stop, num_workers=1, cache_config=None,
        )
        pending.put(ScanResult(
            platform="openai",
            api_key=KEY,
            base_url="https://api.openai.com/v1",
            source_url="https://example.test/settings.py",
        ))
        deadline = time.time() + 8
        rows = []
        while time.time() < deadline:
            db = Database(path)
            rows = db.get_keys_by_status(KeyStatus.INVALID)
            if rows:
                break
            time.sleep(0.05)
        stop.set()
        for thread in threads:
            thread.join(timeout=3)
        asyncio.run(async_db.close())
        assert len(rows) == 1
        assert rows[0].api_key == KEY
        assert rows[0].status == KeyStatus.INVALID.value
        assert rows[0].checked_host == "api.openai.com"


def test_connection_error_persists_as_unknown(monkeypatch):
    from async_database import AsyncDatabase
    from validator import ValidationResult
    from validator_optimized import OptimizedAsyncValidator, start_validators

    async def fake_openai(self, api_key, base_url):
        return ValidationResult(KeyStatus.CONNECTION_ERROR, "timeout")

    monkeypatch.setattr(OptimizedAsyncValidator, "validate_openai", fake_openai)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as root:
        path = os.path.join(root, "keys.db")
        async_db = AsyncDatabase(path, run_id="run-test")
        asyncio.run(async_db.init())
        pending = queue.Queue()
        stop = threading.Event()
        threads = start_validators(
            pending, async_db, stop, num_workers=1, cache_config=None,
        )
        pending.put(ScanResult(
            platform="openai",
            api_key=KEY,
            base_url="https://93.184.216.34/v1",
            source_url="https://example.test/settings.py",
        ))
        deadline = time.time() + 8
        rows = []
        while time.time() < deadline:
            db = Database(path)
            rows = db.get_keys_by_status(KeyStatus.UNKNOWN)
            if rows:
                break
            time.sleep(0.05)
        stop.set()
        for thread in threads:
            thread.join(timeout=3)
        asyncio.run(async_db.close())
        assert len(rows) == 1
        assert rows[0].status == KeyStatus.UNKNOWN.value
        assert rows[0].checked_host == "93.184.216.34"
        assert rows[0].run_id == "run-test"


if __name__ == "__main__":
    test_content_variants_skip_identical_decode()
    test_history_reads_each_blob_once_and_pairs_base_url()
    test_run_local_scan_uses_optimized_validator()
    test_take_queued_result_from_sync_queue()
    print("local scan ok")
