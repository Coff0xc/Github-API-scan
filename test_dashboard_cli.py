"""aikeyscan dashboard binds a run; disposition uses the same fingerprint."""

import json
import os
import subprocess
import sys
from pathlib import Path

import web_dashboard
from database import Database, KeyStatus, LeakedKey
from key_vault import vault

SECRET_A = "sk-proj-" + "A" * 40
SECRET_B = "sk-proj-" + "B" * 40
LOCATION = "https://github.com/acme/api/blob/abc/.env"
ROOT = Path(__file__).resolve().parent


def test_latest_run_and_findings_filter(tmp_path, monkeypatch):
    db_path = str(tmp_path / "keys.db")
    db = Database(db_path)
    run_a = db.create_run("local:/a")
    run_b = db.create_run("local:/b")
    assert db.insert_key(LeakedKey(
        platform="openai", api_key=SECRET_A, base_url="https://api.openai.com/v1",
        status=KeyStatus.VALID.value, source_url=LOCATION, run_id=run_a,
    ))
    assert db.insert_key(LeakedKey(
        platform="anthropic", api_key=SECRET_B, base_url="https://api.anthropic.com",
        status=KeyStatus.VALID.value, source_url=LOCATION, run_id=run_b,
    ))
    assert db.latest_run_id() == run_b

    monkeypatch.setattr(web_dashboard.db_reader, "db_path", db_path)
    web_dashboard.configure(db_path=db_path, run_id=run_b)
    client = web_dashboard.app.test_client()
    body = client.get("/api/findings").get_json()
    fps = {item["fingerprint"] for item in body["findings"]}
    assert vault.hash_key(SECRET_B) in fps
    assert vault.hash_key(SECRET_A) not in fps
    assert SECRET_A not in json.dumps(body)
    assert SECRET_B not in json.dumps(body)
    stats = client.get("/api/stats").get_json()
    assert stats.get("run_id") == run_b
    assert stats.get("total_keys") == 1

    web_dashboard.configure(db_path=db_path, run_id="")
    all_body = client.get("/api/findings").get_json()
    assert len(all_body["findings"]) == 2
    web_dashboard.configure(run_id="")


def test_disposition_subcommand_sets_status(tmp_path):
    db_path = str(tmp_path / "keys.db")
    db = Database(db_path)
    assert db.insert_key(LeakedKey(
        platform="openai", api_key=SECRET_A, base_url="https://api.openai.com/v1",
        status=KeyStatus.VALID.value, source_url=LOCATION,
    ))
    fp = vault.hash_key(SECRET_A)
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    result = subprocess.run(
        [sys.executable, "-m", "aikeyscan", "disposition", fp, "rotated", "--db", db_path],
        cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    from findings_feed import build_document
    assert build_document(db_path)["findings"][0]["disposition"] == "rotated"


def test_dashboard_help():
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    result = subprocess.run(
        [sys.executable, "-m", "aikeyscan", "dashboard", "--help"],
        cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "--run" in combined
    assert "--port" in combined
