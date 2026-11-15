#!/usr/bin/env python3
"""范围闸门、脱敏导出、入口合并的回归测试。不访问网络。"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def test_remote_scope_rules():
    from use_boundary import require_remote_scope

    assert require_remote_scope("acme", "") is True
    assert require_remote_scope("", "acme/api") is True
    assert require_remote_scope("acme", "acme/api") is True
    assert require_remote_scope("", "") is False
    assert require_remote_scope("", "noslash") is False
    assert require_remote_scope("org/name", "") is False


def test_search_scope_never_passes_raw_query():
    from scanner import apply_search_scope, mask_key
    from utils import mask_key as utils_mask

    assert apply_search_scope("sk-secret", "", "") is None
    assert apply_search_scope("sk-secret", "", "noslash") is None
    assert apply_search_scope("sk-secret", "acme", "").endswith("org:acme")
    scoped = apply_search_scope("sk-secret", "ignored", "acme/api")
    assert scoped is not None and scoped.endswith("repo:acme/api")
    assert "org:" not in scoped
    assert mask_key is utils_mask
    assert "..." in mask_key("sk-proj-" + "a" * 40)


def test_plaintext_export_is_masked():
    from database import Database, LeakedKey, KeyStatus
    from export_io import export_keys

    secret = "sk-proj-" + "a" * 40
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "keys.db")
        out = str(Path(tmp) / "out.txt")
        db = Database(db_path)
        assert db.insert_key(LeakedKey(
            platform="openai",
            api_key=secret,
            base_url="https://api.openai.com/v1",
            status=KeyStatus.VALID.value,
            source_url="https://example.invalid/file",
        ))
        export_keys(db_path, out, status_filter="valid", reveal=False)
        text = Path(out).read_text(encoding="utf-8")
        assert secret not in text
        assert "..." in text

        revealed = str(Path(tmp) / "full.txt")
        export_keys(db_path, revealed, status_filter="valid", reveal=True)
        assert secret in Path(revealed).read_text(encoding="utf-8")


def _run_entry(script: str, *args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["SCANNER_AUTHORIZED"] = "1"
    env.pop("DB_ENCRYPTION_KEY", None)
    return subprocess.run(
        [sys.executable, script, *args],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_unscoped_remote_scan_stops():
    result = _run_entry("main_v2.2.py", "--authorized")
    combined = result.stdout + result.stderr
    assert "target-org" in combined
    assert result.returncode == 0


def test_public_source_without_opt_in_stops():
    result = _run_entry("main_v2.2.py", "--authorized", "--target-org", "acme", "--gist")
    combined = result.stdout + result.stderr
    assert "allow-public-sources" in combined


def test_scoped_scan_still_requires_encryption():
    result = _run_entry("main_v2.2.py", "--authorized", "--target-org", "acme")
    combined = result.stdout + result.stderr
    assert "DB_ENCRYPTION_KEY" in combined


def test_single_entry_point():
    for script in ("main.py", "main_v2.1.py", "main_optimized.py"):
        assert not (ROOT / script).exists()
    result = _run_entry("main_v2.2.py", "--help")
    combined = result.stdout + result.stderr
    assert "allow-public-sources" in combined
    assert "findings-json" in combined


def test_private_targets_are_blocked():
    from utils import host_is_safe_to_contact

    assert host_is_safe_to_contact("127.0.0.1") is True
    assert host_is_safe_to_contact("localhost") is True
    assert host_is_safe_to_contact("10.1.2.3") is False
    assert host_is_safe_to_contact("169.254.169.254") is False
    assert host_is_safe_to_contact("8.8.8.8") is True
    assert host_is_safe_to_contact("") is False


def test_relay_url_policy_matches_host_rules():
    from utils import relay_url_is_allowed

    assert relay_url_is_allowed("") is True
    assert relay_url_is_allowed("https://api.openai.com/v1") is True
    assert relay_url_is_allowed("http://127.0.0.1:1/v1") is True
    assert relay_url_is_allowed("http://localhost:8000/v1") is True
    assert relay_url_is_allowed("http://192.168.1.1/v1") is False
    assert relay_url_is_allowed("https://10.1.2.3/v1") is False
    assert relay_url_is_allowed("http://internal.corp/api") is False
    assert relay_url_is_allowed("https://docs.python.org/howto") is False

    from database import Database
    from validator import AsyncValidator
    from validator_optimized import OptimizedAsyncValidator

    sync_v = AsyncValidator(Database(":memory:"))
    opt_v = OptimizedAsyncValidator(Database(":memory:"))
    assert sync_v._is_likely_valid_relay("http://127.0.0.1:1/v1") is True
    assert opt_v._is_likely_valid_relay("http://127.0.0.1:1/v1") is True
    assert sync_v._is_likely_valid_relay("http://192.168.1.1/v1") is False
    assert opt_v._is_likely_valid_relay("http://192.168.1.1/v1") is False


def test_key_patterns_compiled_once_without_azure():
    from config import COMPILED_KEY_PATTERNS, REGEX_PATTERNS

    assert "azure" in REGEX_PATTERNS
    assert "azure" not in COMPILED_KEY_PATTERNS
    assert "openai" in COMPILED_KEY_PATTERNS
    from scanner import GitHubScanner
    import queue
    import threading
    from database import Database

    scanner = GitHubScanner(queue.Queue(), Database(":memory:"), threading.Event())
    assert scanner._key_patterns is COMPILED_KEY_PATTERNS


def test_github_scanner_requires_sync_database():
    from async_database import AsyncDatabase
    from scanner import GitHubScanner
    import queue
    import threading

    try:
        GitHubScanner(queue.Queue(), AsyncDatabase(":memory:"), threading.Event())
    except TypeError as exc:
        assert "Database" in str(exc)
        return
    raise AssertionError("GitHubScanner must reject AsyncDatabase")


def test_github_scanner_preloads_scanned_blob_shas():
    from scanner import GitHubScanner
    import queue
    import threading
    from database import Database

    sha = "a" * 40
    db = Database(":memory:")
    assert db.mark_blob_scanned(sha)
    scanner = GitHubScanner(queue.Queue(), db, threading.Event())
    assert sha in scanner._processed_shas

    original = scanner.db.is_blob_scanned

    def boom(file_sha):
        if file_sha == sha:
            raise AssertionError("preloaded SHA must not hit the database")
        return original(file_sha)

    scanner.db.is_blob_scanned = boom
    assert scanner._is_sha_processed(sha) is True
    assert scanner._is_sha_processed("b" * 40) is False


def test_github_extract_keeps_new_key_with_sync_database():
    from scanner import GitHubScanner
    import queue
    import threading
    from database import Database

    key = "sk-proj-Qw9Rt8Yu7Ip6Lk5Jh4Gf3Ds2Az1Xc0Vb"
    scanner = GitHubScanner(queue.Queue(), Database(":memory:"), threading.Event())
    found = scanner._extract_keys_from_content(
        f"API_KEY={key}", "https://github.com/acme/app/blob/main/.env",
    )
    assert [item.api_key for item in found] == [key]


if __name__ == "__main__":
    test_remote_scope_rules()
    test_search_scope_never_passes_raw_query()
    test_plaintext_export_is_masked()
    test_unscoped_remote_scan_stops()
    test_public_source_without_opt_in_stops()
    test_scoped_scan_still_requires_encryption()
    test_single_entry_point()
    test_private_targets_are_blocked()
    test_relay_url_policy_matches_host_rules()
    test_key_patterns_compiled_once_without_azure()
    test_github_scanner_requires_sync_database()
    test_github_scanner_preloads_scanned_blob_shas()
    test_github_extract_keeps_new_key_with_sync_database()
    print("boundary fixes ok")
