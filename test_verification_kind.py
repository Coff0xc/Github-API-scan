"""Honest verification_kind and relay-vs-official pairing."""

import asyncio
import inspect
import os
import queue
import tempfile
import threading
import time

from database import Database, KeyStatus
from findings_feed import build_document
from run_artifacts import render_run_markdown
from scanner import extract_keys, ScanResult
from config import COMPILED_KEY_PATTERNS
from validator.kinds import (
    KIND_GENERIC_HTTP,
    KIND_MATCH_ONLY,
    KIND_PROTOCOL,
    verification_kind,
)


KEY = "sk-proj-Qw9Rt8Yu7Ip6Lk5Jh4Gf3Ds2Az1Xc0Vb"
RELAY_PAIR = "https://relay.example.invalid/v1"
RELAY_CHECK = "https://93.184.216.34/v1"
OFFICIAL = "https://api.openai.com/v1"
LOCATION = "https://github.com/acme/app/blob/abc/.env"


def test_kind_table():
    assert verification_kind("openai") == KIND_PROTOCOL
    assert verification_kind("relay") == KIND_PROTOCOL
    assert verification_kind("anthropic") == KIND_PROTOCOL
    assert verification_kind("gemini") == KIND_PROTOCOL
    assert verification_kind("azure") == KIND_PROTOCOL
    assert verification_kind("groq") == KIND_PROTOCOL
    assert verification_kind("stripe") == KIND_GENERIC_HTTP
    assert verification_kind("github_token") == KIND_GENERIC_HTTP
    assert verification_kind("discord") == KIND_MATCH_ONLY
    assert verification_kind("future_platform") == KIND_MATCH_ONLY


def test_extract_pairs_relay_not_official():
    content = f"OPENAI_BASE_URL={RELAY_PAIR}\n{KEY}\n"
    rows = extract_keys(COMPILED_KEY_PATTERNS, content, LOCATION)
    assert len(rows) == 1
    assert rows[0].api_key == KEY
    assert "relay.example.invalid" in rows[0].base_url
    assert "api.openai.com" not in (rows[0].base_url or "")


def test_worker_uses_single_validate_result():
    from validator_optimized import optimized_validator_worker

    source = inspect.getsource(optimized_validator_worker)
    assert "validate_key_async" not in source
    assert "validate_result" in source
    assert "from validator import start_validators" not in source


def test_relay_live_official_dead_report_uses_relay(monkeypatch):
    from async_database import AsyncDatabase
    from validator import ValidationResult
    from validator_optimized import OptimizedAsyncValidator, start_validators

    async def fake_openai(self, api_key, base_url):
        if "93.184.216.34" in (base_url or ""):
            return ValidationResult(KeyStatus.VALID, "relay ok")
        return ValidationResult(KeyStatus.INVALID, "official dead")

    monkeypatch.setattr(OptimizedAsyncValidator, "validate_openai", fake_openai)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as root:
        path = os.path.join(root, "keys.db")
        async_db = AsyncDatabase(path, run_id="run-relay")
        asyncio.run(async_db.init())
        pending = queue.Queue()
        stop = threading.Event()
        threads = start_validators(
            pending, async_db, stop, num_workers=1, cache_config=None,
        )
        pending.put(ScanResult(
            platform="openai",
            api_key=KEY,
            base_url=RELAY_CHECK,
            source_url=LOCATION,
        ))
        deadline = time.time() + 8
        rows = []
        while time.time() < deadline:
            db = Database(path)
            rows = db.get_keys_by_status(KeyStatus.VALID)
            if rows:
                break
            time.sleep(0.05)
        stop.set()
        for thread in threads:
            thread.join(timeout=3)
        asyncio.run(async_db.close())

        assert len(rows) == 1
        assert rows[0].checked_host == "93.184.216.34"
        assert rows[0].verification_kind == KIND_PROTOCOL
        assert rows[0].base_url == RELAY_CHECK

        document = build_document(path)
        finding = document["findings"][0]
        assert finding["checked_host"] == "93.184.216.34"
        assert finding["status"] == "live"
        assert finding["verification_kind"] == KIND_PROTOCOL
        markdown = render_run_markdown(document, "run-relay")
        assert KEY not in markdown
        assert "93.184.216.34" in markdown
        assert OFFICIAL not in markdown
        assert "api.openai.com" not in finding["checked_host"]


def test_match_only_skips_http(monkeypatch):
    from async_database import AsyncDatabase
    from validator import ValidationResult
    from validator_optimized import OptimizedAsyncValidator, start_validators

    called = []

    async def fake_openai(self, api_key, base_url):
        called.append(base_url)
        return ValidationResult(KeyStatus.INVALID, "should not run")

    monkeypatch.setattr(OptimizedAsyncValidator, "validate_openai", fake_openai)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as root:
        path = os.path.join(root, "keys.db")
        async_db = AsyncDatabase(path, run_id="run-match")
        asyncio.run(async_db.init())
        pending = queue.Queue()
        stop = threading.Event()
        threads = start_validators(
            pending, async_db, stop, num_workers=1, cache_config=None,
        )
        pending.put(ScanResult(
            platform="discord",
            api_key="N" + "a" * 23 + ".aaaaaa." + "b" * 27,
            base_url="",
            source_url=LOCATION,
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

        assert called == []
        assert len(rows) == 1
        assert rows[0].verification_kind == KIND_MATCH_ONLY
        finding = build_document(path)["findings"][0]
        assert finding["status"] == "unknown"
        assert finding["verification_kind"] == KIND_MATCH_ONLY
