"""Web Dashboard 的 hermetic 安全面测试。

覆盖面板对外的信任边界：
- 无令牌读取永远是脱敏的（reveal 参数被忽略）
- 改处置 / 导出 / 统计推送需要 X-API-Token 头
- 错误令牌按 IP 限速：10 次失败后续请求 429
- 导出默认 Fernet 加密且可用派生密钥解开；mask=1 返回脱敏 JSON
- 安全响应头

DB 指向临时文件，模块常量用 monkeypatch 改写，不打网络。
"""

import json

import pytest

import web_dashboard
from database import Database, LeakedKey, KeyStatus
from key_vault import vault

SECRET = "sk-proj-A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
TOKEN = "dashboard-test-token"


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "keys.db")
    db = Database(db_path)
    assert db.insert_key(LeakedKey(
        platform="openai",
        api_key=SECRET,
        base_url="https://api.openai.com/v1",
        status=KeyStatus.VALID.value,
        source_url="https://github.com/acme/billing/blob/abc/.env",
    ))

    monkeypatch.setattr(web_dashboard.db_reader, "db_path", db_path)
    monkeypatch.setattr(web_dashboard, "current_run_id", "")
    monkeypatch.setattr(web_dashboard, "DASHBOARD_TOKEN", TOKEN)
    monkeypatch.setattr(web_dashboard, "AUTH_ENABLED", True)
    monkeypatch.setattr(web_dashboard, "EXPORT_KEY_SECRET", "")
    web_dashboard._auth_failures.clear()

    return web_dashboard.app.test_client()


def test_findings_are_masked_without_token(client):
    resp = client.get("/api/findings")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert SECRET not in body
    assert "..." in body


def test_reveal_flag_is_ignored_on_findings(client):
    resp = client.get("/api/findings?reveal=1&reveal=true")
    assert resp.status_code == 200
    assert SECRET not in resp.get_data(as_text=True)


def test_disposition_requires_token(client):
    fingerprint = vault.hash_key(SECRET)
    resp = client.post("/api/findings/disposition", json={
        "fingerprint": fingerprint,
        "disposition": "rotated",
    })
    assert resp.status_code == 401


def test_disposition_rejects_wrong_token(client):
    fingerprint = vault.hash_key(SECRET)
    resp = client.post(
        "/api/findings/disposition",
        json={"fingerprint": fingerprint, "disposition": "rotated"},
        headers={"X-API-Token": "wrong"},
    )
    assert resp.status_code == 401


def test_disposition_updates_row_with_token(client, tmp_path):
    fingerprint = vault.hash_key(SECRET)
    resp = client.post(
        "/api/findings/disposition",
        json={"fingerprint": fingerprint, "disposition": "rotated"},
        headers={"X-API-Token": TOKEN},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    assert payload["fingerprint"] == fingerprint
    assert payload["disposition"] == "rotated"

    db = Database(str(tmp_path / "keys.db"))
    rows = db.list_finding_sources()
    assert rows[0]["disposition"] == "rotated"


def test_disposition_rejects_bad_status(client):
    fingerprint = vault.hash_key(SECRET)
    resp = client.post(
        "/api/findings/disposition",
        json={"fingerprint": fingerprint, "disposition": "compromised"},
        headers={"X-API-Token": TOKEN},
    )
    assert resp.status_code == 400


def test_rate_limit_kicks_in_after_ten_bad_tokens(client):
    fingerprint = vault.hash_key(SECRET)
    last = None
    for _ in range(11):
        last = client.post(
            "/api/findings/disposition",
            json={"fingerprint": fingerprint, "disposition": "rotated"},
            headers={"X-API-Token": "wrong"},
        )
    assert last.status_code == 429


def test_missing_token_does_not_count_toward_rate_limit(client):
    fingerprint = vault.hash_key(SECRET)
    for _ in range(12):
        resp = client.post(
            "/api/findings/disposition",
            json={"fingerprint": fingerprint, "disposition": "rotated"},
        )
    assert resp.status_code == 401  # 永远 401，不累计限速


def test_export_disabled_when_token_not_configured(client, monkeypatch):
    monkeypatch.setattr(web_dashboard, "AUTH_ENABLED", False)
    resp = client.get("/api/export")
    assert resp.status_code == 403


def test_export_encrypted_roundtrip_contains_keys(client):
    resp = client.get("/api/export", headers={"X-API-Token": TOKEN})
    assert resp.status_code == 200
    blob = resp.get_data()
    assert SECRET not in blob.decode("utf-8", errors="ignore")

    from cryptography.fernet import Fernet
    decrypted = Fernet(web_dashboard._derive_export_key()).decrypt(blob)
    assert SECRET in decrypted.decode("utf-8")


def test_export_masked_variant_has_no_secret(client):
    resp = client.get("/api/export?mask=1", headers={"X-API-Token": TOKEN})
    assert resp.status_code == 200
    assert SECRET not in resp.get_data(as_text=True)


def test_stats_push_requires_token(client):
    resp = client.post("/api/stats/update", json={"total_scanned": 5})
    assert resp.status_code == 401

    resp = client.post(
        "/api/stats/update",
        json={"total_scanned": 5},
        headers={"X-API-Token": TOKEN},
    )
    assert resp.status_code == 200


def test_security_headers_present(client):
    resp = client.get("/api/findings")
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("Cache-Control") == "no-store"
