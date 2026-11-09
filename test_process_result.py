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
            validator.probe_gpt4 = _fail("probe_gpt4")
            validator.probe_billing = _fail("probe_billing")
            validator.probe_quota_by_request = _fail("probe_quota")

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
                    "SELECT balance, balance_usd, is_high_value FROM leaked_keys"
                ).fetchone()
            assert row[0] in ("", None)
            assert row[1] == 0
            assert row[2] == 0

    asyncio.run(run())


def _fail(name):
    async def _inner(*_args, **_kwargs):
        raise AssertionError(name)

    return _inner


if __name__ == "__main__":
    test_process_result_does_not_score_or_store_value()
    print("process result ok")
