"""Scan run artifacts: checked_host, public status, SARIF, exit codes."""

import json
import tempfile
from pathlib import Path

from database import Database, KeyStatus, LeakedKey
from findings_feed import _FINDING_FIELDS, build_document
from run_artifacts import (
    EXIT_LIVE,
    EXIT_OK,
    checked_host_from_url,
    persist_status,
    public_status,
    write_scan_artifacts,
)

SECRET = "sk-proj-" + "c" * 40
LOCATION = "https://github.com/acme/api/blob/abc123/.env"


def test_checked_host_and_public_status():
    assert checked_host_from_url("https://api.openai.com/v1") == "api.openai.com"
    assert checked_host_from_url("http://localhost:8080/v1") == "localhost"
    assert checked_host_from_url("") == ""
    assert public_status("valid") == "live"
    assert public_status("quota_exceeded") == "quota"
    assert public_status("invalid") == "dead"
    assert public_status("connection_error") == "unknown"
    assert public_status("unknown") == "unknown"
    assert persist_status(KeyStatus.CONNECTION_ERROR) == "unknown"
    assert persist_status(KeyStatus.VALID) == "valid"
    assert persist_status(KeyStatus.INVALID) == "invalid"


def test_write_scan_artifacts_live_exit_and_no_secret():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "keys.db")
        db = Database(db_path)
        run_id = db.create_run("repo:acme/api")
        assert db.insert_key(LeakedKey(
            platform="openai",
            api_key=SECRET,
            base_url="https://relay.example.invalid/v1",
            status=KeyStatus.VALID.value,
            source_url=LOCATION,
            run_id=run_id,
            checked_host="relay.example.invalid",
        ))
        runs_root = Path(tmp) / "runs"
        cwd_json = Path(tmp) / "findings.json"
        summary, code = write_scan_artifacts(
            db_path,
            run_id,
            findings_json=str(cwd_json),
            fmt="all",
            runs_root=runs_root,
        )
        assert code == EXIT_LIVE
        run_dir = runs_root / run_id
        assert (run_dir / "findings.json").is_file()
        assert (run_dir / "report.md").is_file()
        assert (run_dir / "results.sarif").is_file()
        text = cwd_json.read_text(encoding="utf-8")
        assert SECRET not in text
        document = json.loads(text)
        assert document["schema"] == "findings.v1"
        assert document["run_id"] == run_id
        finding = document["findings"][0]
        assert set(finding) == set(_FINDING_FIELDS)
        assert finding["status"] == "live"
        assert finding["checked_host"] == "relay.example.invalid"
        assert finding["run_id"] == run_id
        markdown = (run_dir / "report.md").read_text(encoding="utf-8")
        assert SECRET not in markdown
        assert "relay.example.invalid" in markdown
        sarif = json.loads((run_dir / "results.sarif").read_text(encoding="utf-8"))
        blob = json.dumps(sarif)
        assert SECRET not in blob
        assert sarif["version"] == "2.1.0"
        assert finding["fingerprint"] in blob
        assert str(run_dir) in summary or run_id in summary


def test_live_only_drops_dead_and_empty_is_ok():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "keys.db")
        db = Database(db_path)
        run_id = db.create_run("local:/tmp/x")
        db.insert_key(LeakedKey(
            platform="openai",
            api_key=SECRET,
            base_url="https://api.openai.com/v1",
            status=KeyStatus.INVALID.value,
            source_url=LOCATION,
            run_id=run_id,
        ))
        runs_root = Path(tmp) / "runs"
        summary, code = write_scan_artifacts(
            db_path,
            run_id,
            findings_json=str(Path(tmp) / "findings.json"),
            live_only=True,
            fmt="json",
            runs_root=runs_root,
        )
        assert code == EXIT_OK
        document = json.loads((Path(tmp) / "findings.json").read_text(encoding="utf-8"))
        assert document["findings"] == []
        assert "0 条发现" in summary


def test_connection_error_exports_as_unknown():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "keys.db")
        db = Database(db_path)
        db.insert_key(LeakedKey(
            platform="openai",
            api_key=SECRET,
            base_url="https://api.openai.com/v1",
            status=KeyStatus.UNKNOWN.value,
            source_url=LOCATION,
            checked_host="api.openai.com",
        ))
        finding = build_document(db_path)["findings"][0]
        assert finding["status"] == "unknown"
        assert finding["checked_host"] == "api.openai.com"
