"""威胁报告按发现时间排列，不按余额或高价值。"""

import os
import tempfile
from datetime import datetime

from database import Database, KeyStatus, LeakedKey
from threat_report import generate_report


OLD = "sk-proj-OLDKEY0123456789abcdefghijklmnop"
NEW = "sk-proj-NEWKEY0123456789abcdefghijklmnop"


def test_report_orders_by_time_and_skips_value_columns():
    with tempfile.TemporaryDirectory() as root:
        db_path = os.path.join(root, "keys.db")
        db = Database(db_path)
        db.insert_key(LeakedKey(
            platform="openai",
            api_key=OLD,
            base_url="https://api.openai.com/v1",
            source_url="https://github.com/acme-labs/old/blob/aaa/.env",
            found_time=datetime(2026, 11, 1, 8, 0),
        ))
        db.update_key_status(
            OLD, KeyStatus.VALID, balance="$999", model_tier="GPT-4",
            rpm=10000, is_high_value=True, balance_usd=999,
        )
        db.insert_key(LeakedKey(
            platform="anthropic",
            api_key=NEW,
            base_url="https://api.anthropic.com",
            source_url="https://github.com/acme-labs/new/blob/bbb/app.yaml",
            found_time=datetime(2026, 11, 10, 9, 0),
            status=KeyStatus.QUOTA_EXCEEDED.value,
        ))

        out = os.path.join(root, "threat.md")
        summary = generate_report(db_path, out, reveal=False)
        text = open(out, encoding="utf-8").read()

        assert "高价值" not in text
        assert "余额" not in text
        assert "$999" not in text
        assert OLD not in text
        assert NEW not in text
        assert text.index("acme-labs/new") < text.index("acme-labs/old")
        assert "quota_exceeded" in text
        assert "GPT-4" in text
        assert "10000" in text
        assert "脱敏" in summary


if __name__ == "__main__":
    test_report_orders_by_time_and_skips_value_columns()
    print("threat report ok")
