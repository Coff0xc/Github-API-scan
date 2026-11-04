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


def test_legacy_entry_points_delegate():
    for script in ("main.py", "main_v2.1.py", "main_optimized.py"):
        text = (ROOT / script).read_text(encoding="utf-8")
        assert "runpy" in text
        assert "class " not in text
        result = _run_entry(script, "--help")
        combined = result.stdout + result.stderr
        assert "allow-public-sources" in combined
        assert "deprecated" in combined


if __name__ == "__main__":
    test_remote_scope_rules()
    test_search_scope_never_passes_raw_query()
    test_plaintext_export_is_masked()
    test_unscoped_remote_scan_stops()
    test_public_source_without_opt_in_stops()
    test_scoped_scan_still_requires_encryption()
    test_legacy_entry_points_delegate()
    print("boundary fixes ok")
