#!/usr/bin/env python3
"""代理管道：发现 JSON 不含明文 Key，处置状态可以按指纹写回。"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SECRET = "sk-proj-" + "b" * 40
LOCATION = "https://github.com/acme/api-server/blob/abc123def4567890/.env"


def test_parse_github_blob_and_gist():
    from findings_feed import parse_location

    place = parse_location(LOCATION)
    assert place == {
        "repo": "acme/api-server",
        "path": ".env",
        "commit": "abc123def4567890",
    }
    gist = parse_location("https://gist.github.com/octocat/0123456789abcdef")
    assert gist["repo"] == "gist:octocat"
    assert gist["path"] == "0123456789abcdef"
    assert parse_location("") == {"repo": "", "path": "", "commit": ""}


def _seed(db_path: str):
    from database import Database, KeyStatus, LeakedKey

    db = Database(db_path)
    assert db.insert_key(LeakedKey(
        platform="openai",
        api_key=SECRET,
        base_url="https://api.openai.com/v1",
        status=KeyStatus.VALID.value,
        source_url=LOCATION,
    ))


def test_export_has_no_secret_and_round_trips_disposition():
    from findings_feed import DISPOSITIONS, _FINDING_FIELDS, apply_dispositions, write_findings
    from key_vault import vault

    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "keys.db")
        out = str(Path(tmp) / "findings.json")
        _seed(db_path)
        summary = write_findings(db_path, out)
        text = Path(out).read_text(encoding="utf-8")
        document = json.loads(text)

        assert SECRET not in text
        assert "api_key" not in text
        assert "balance" not in text
        assert document["schema"] == "findings.v1"
        assert len(document["findings"]) == 1
        finding = document["findings"][0]
        assert set(finding) == set(_FINDING_FIELDS)
        assert finding["fingerprint"] == vault.hash_key(SECRET)
        assert finding["repo"] == "acme/api-server"
        assert finding["path"] == ".env"
        assert finding["commit"] == "abc123def4567890"
        assert finding["disposition"] == "open"
        assert "..." in finding["preview"]
        assert "不含明文" in summary

        updates = str(Path(tmp) / "updates.json")
        Path(updates).write_text(json.dumps({
            "updates": [
                {"fingerprint": finding["fingerprint"], "disposition": "notified"},
                {"fingerprint": "a" * 64, "disposition": "rotated"},
                {"fingerprint": finding["fingerprint"], "disposition": "use-it"},
            ]
        }), encoding="utf-8")
        result = apply_dispositions(db_path, updates)
        assert result.startswith("处置已写回 1 条，跳过 2 条")

        write_findings(db_path, out)
        again = json.loads(Path(out).read_text(encoding="utf-8"))
        assert again["findings"][0]["disposition"] == "notified"
        assert "notified" in DISPOSITIONS


def test_http_findings_ignore_reveal():
    os.environ.pop("DB_ENCRYPTION_KEY", None)
    import web_dashboard
    from findings_feed import _FINDING_FIELDS

    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "keys.db")
        _seed(db_path)
        web_dashboard.db_reader.db_path = db_path
        client = web_dashboard.app.test_client()
        response = client.get("/api/findings?reveal=1")
        assert response.status_code == 200
        body = response.get_json()
        encoded = json.dumps(body)
        assert SECRET not in encoded
        assert "api_key" not in encoded
        assert set(body["findings"][0]) == set(_FINDING_FIELDS)


def test_cli_writes_findings():
    env = os.environ.copy()
    env["SCANNER_AUTHORIZED"] = "1"
    env.pop("DB_ENCRYPTION_KEY", None)
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "keys.db")
        out = str(Path(tmp) / "findings.json")
        _seed(db_path)
        result = subprocess.run(
            [sys.executable, "main_v2.2.py", "--authorized", "--db", db_path, "--findings-json", out],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        combined = result.stdout + result.stderr
        assert result.returncode == 0, combined
        text = Path(out).read_text(encoding="utf-8")
        assert SECRET not in text
        assert "findings.v1" in text


def test_notice_and_channel_omit_secret():
    import asyncio
    from findings_feed import disclosure_notice
    from notifier_v2 import KeyInfo, NotificationChannel, NotifierV2

    text = disclosure_notice("openai", "sk-pro...cret", LOCATION)
    assert SECRET not in text
    assert LOCATION in text
    assert "没有完整密钥" in text

    class Capture(NotificationChannel):
        def __init__(self):
            super().__init__("capture")
            self.sent = []

        async def send(self, key_info, message=""):
            self.sent.append(key_info.api_key + message)
            return True

        async def send_report(self, title, content):
            self.sent.append(title + "\n" + content)
            return True

    notifier = NotifierV2()
    channel = Capture()
    notifier.channels.append(channel)
    asyncio.run(notifier.notify(KeyInfo(
        platform="openai",
        api_key=SECRET,
        source_url=LOCATION,
        balance="$100",
        is_high_value=True,
    )))
    blob = "\n".join(channel.sent)
    assert SECRET not in blob
    assert "$100" not in blob
    assert LOCATION in blob


def test_disposition_post_uses_fingerprint_only():
    import web_dashboard
    from key_vault import vault

    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "keys.db")
        _seed(db_path)
        fingerprint = vault.hash_key(SECRET)
        web_dashboard.db_reader.db_path = db_path
        web_dashboard.DASHBOARD_TOKEN = "panel-token"
        web_dashboard.AUTH_ENABLED = True
        client = web_dashboard.app.test_client()

        missing = client.post(
            "/api/findings/disposition",
            json={"fingerprint": fingerprint, "disposition": "rotated"},
        )
        assert missing.status_code == 401

        response = client.post(
            "/api/findings/disposition",
            headers={"X-API-Token": "panel-token"},
            json={
                "fingerprint": fingerprint,
                "disposition": "rotated",
                "api_key": SECRET,
            },
        )
        body = response.get_json()
        encoded = json.dumps(body)
        assert response.status_code == 200
        assert body == {
            "ok": True,
            "fingerprint": fingerprint,
            "disposition": "rotated",
        }
        assert SECRET not in encoded
        assert "api_key" not in body
        from findings_feed import build_document
        assert build_document(db_path)["findings"][0]["disposition"] == "rotated"

        rejected = client.post(
            "/api/findings/disposition",
            headers={"X-API-Token": "panel-token"},
            json={"fingerprint": fingerprint, "disposition": "use-it"},
        )
        assert rejected.status_code == 400


def test_dashboard_home_lists_findings():
    import web_dashboard

    client = web_dashboard.app.test_client()
    html = client.get("/").get_data(as_text=True)
    script = client.get("/static/js/dashboard.js").get_data(as_text=True)
    assert "发现记录" in html
    assert "指纹" in html
    assert "预览" in html
    assert "处置" in html
    assert "High Value" not in html
    assert ">API Key<" not in html
    assert "export-btn" not in html
    assert "/api/findings" in script
    assert "/api/keys" not in script


if __name__ == "__main__":
    test_parse_github_blob_and_gist()
    test_export_has_no_secret_and_round_trips_disposition()
    test_http_findings_ignore_reveal()
    test_cli_writes_findings()
    test_notice_and_channel_omit_secret()
    test_dashboard_home_lists_findings()
    test_disposition_post_uses_fingerprint_only()
    print("findings feed ok")
