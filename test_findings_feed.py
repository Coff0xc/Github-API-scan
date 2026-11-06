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


if __name__ == "__main__":
    test_parse_github_blob_and_gist()
    test_export_has_no_secret_and_round_trips_disposition()
    test_http_findings_ignore_reveal()
    test_cli_writes_findings()
    print("findings feed ok")
