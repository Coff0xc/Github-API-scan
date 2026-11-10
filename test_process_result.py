"""旧验证路径不再为了打分去查余额或探测 GPT-4。"""

import asyncio
import os
import sqlite3
import tempfile

from database import Database
from scanner import ScanResult
from validator import AsyncValidator, KeyStatus, ValidationResult

KEY = "sk-proj-OLDPATH0123456789abcdefghijklmn"


def test_process_result_does_not_score_or_store_value():
    async def run():
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as root:
            db = Database(os.path.join(root, "keys.db"))
            validator = AsyncValidator(db)

            async def fake_validate(_result):
                return ValidationResult(
                    KeyStatus.VALID, "3模型", "GPT-4", 8000, 50.0, True,
                )

            validator.validate_single = fake_validate
            await validator.process_result(ScanResult(
                platform="openai",
                api_key=KEY,
                base_url="https://api.openai.com/v1",
                source_url="https://github.com/acme-labs/app/blob/abc/.env",
            ))
            stored = db.get_valid_keys()
            assert len(stored) == 1
            assert stored[0].status == "valid"
            assert stored[0].model_tier == "GPT-4"
            assert stored[0].rpm == 8000
            with sqlite3.connect(db.db_path) as conn:
                row = conn.execute(
                    "SELECT status, model_tier, rpm FROM leaked_keys"
                ).fetchone()
                columns = {info[1] for info in conn.execute("PRAGMA table_info(leaked_keys)")}
            assert row == ("valid", "GPT-4", 8000)
            for retired in ("is_high_value", "balance", "balance_usd", "value_score"):
                assert retired not in columns
            for name in ("probe_billing", "probe_gpt4", "probe_quota_by_request"):
                assert not hasattr(AsyncValidator, name)

    asyncio.run(run())


def _fail(name):
    async def _inner(*_args, **_kwargs):
        raise AssertionError(name)

    return _inner


def test_platform_checks_do_not_flag_high_value():
    import inspect
    import validator

    source = inspect.getsource(validator.AsyncValidator)
    assert "is_high_value=True" not in source
    assert "is_high_value=balance" not in source
    assert "def probe_billing" not in source
    assert "def probe_gpt4" not in source
    assert "def probe_quota_by_request" not in source
    assert "HIGH_VALUE_MODELS" not in source


def test_queued_insert_must_flush_before_status_update():
    """queue_insert 只是入队，必须先 flush 落盘再 update_key_status。

    验证 worker 的回归：不 flush 直接 update 会命中 0 行，状态静默丢失，
    数据库里永远只剩 pending。
    """
    from async_database import AsyncDatabase

    async def run():
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as root:
            path = os.path.join(root, "keys.db")
            db = AsyncDatabase(path)
            await db.init()
            await db.queue_insert(_leaked_key("gemini", KEY))
            await db.flush()
            await db.update_key_status(KEY, KeyStatus.CONNECTION_ERROR, "", "", 0, False)
            await db.close()
            with sqlite3.connect(path) as conn:
                row = conn.execute("SELECT status FROM leaked_keys").fetchone()
            assert row == ("connection_error",)

    asyncio.run(run())


def _leaked_key(platform, api_key):
    from database import LeakedKey
    from datetime import datetime

    return LeakedKey(
        platform=platform,
        api_key=api_key,
        base_url="http://127.0.0.1:1/v1",
        status=KeyStatus.PENDING.value,
        source_url="https://github.com/acme-labs/app/blob/abc/.env",
        found_time=datetime.now(),
    )


if __name__ == "__main__":
    test_process_result_does_not_score_or_store_value()
    test_platform_checks_do_not_flag_high_value()
    test_queued_insert_must_flush_before_status_update()
    print("process result ok")
