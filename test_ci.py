"""CI surface: baseline fingerprints, since-ref, log redact."""

import json
import os
import queue
import tempfile
import threading
from pathlib import Path

from database import Database, KeyStatus, LeakedKey
from key_vault import vault
from local_scanner import LocalScanner
from run_artifacts import (
    EXIT_LIVE,
    EXIT_OK,
    load_baseline_fingerprints,
    write_scan_artifacts,
)
from utils import redact_message, set_redact

from test_local_scan import BODY, KEY, _git

SECRET = "sk-proj-" + "c" * 40
LOCATION = "https://github.com/acme/api/blob/abc123/.env"


def test_load_baseline_from_findings_and_list():
    with tempfile.TemporaryDirectory() as tmp:
        fp = "a" * 64
        findings = Path(tmp) / "findings.json"
        findings.write_text(json.dumps({
            "schema": "findings.v1",
            "findings": [{"fingerprint": fp, "status": "live"}],
        }), encoding="utf-8")
        assert fp in load_baseline_fingerprints(str(findings))
        listed = Path(tmp) / "fps.json"
        listed.write_text(json.dumps([fp, "not-a-fingerprint"]), encoding="utf-8")
        assert load_baseline_fingerprints(str(listed)) == {fp}
        lines = Path(tmp) / "fps.txt"
        lines.write_text(fp + "\n# comment\n", encoding="utf-8")
        assert load_baseline_fingerprints(str(lines)) == {fp}


def test_baseline_hides_known_live_from_exit_code():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "keys.db")
        db = Database(db_path)
        run_id = db.create_run("local:/tmp")
        assert db.insert_key(LeakedKey(
            platform="openai",
            api_key=SECRET,
            base_url="https://api.openai.com/v1",
            status=KeyStatus.VALID.value,
            source_url=LOCATION,
            run_id=run_id,
        ))
        fp = vault.hash_key(SECRET)
        baseline = Path(tmp) / "baseline.json"
        baseline.write_text(json.dumps({"fingerprints": [fp]}), encoding="utf-8")
        runs_root = Path(tmp) / "runs"
        _, code = write_scan_artifacts(
            db_path, run_id,
            findings_json=str(Path(tmp) / "findings.json"),
            fmt="json",
            runs_root=runs_root,
            baseline_path=str(baseline),
        )
        assert code == EXIT_OK
        document = json.loads((Path(tmp) / "findings.json").read_text(encoding="utf-8"))
        assert document["findings"] == []

        _, code_new = write_scan_artifacts(
            db_path, run_id,
            findings_json=str(Path(tmp) / "all.json"),
            fmt="json",
            runs_root=runs_root,
        )
        assert code_new == EXIT_LIVE


def test_redact_strips_key_shapes():
    set_redact(True)
    blob = redact_message(f"found {KEY} in file")
    assert KEY not in blob
    assert "..." in blob
    set_redact(False)
    assert KEY in redact_message(f"found {KEY} in file")
    set_redact(True)


def test_since_ref_only_reads_new_commit():
    with tempfile.TemporaryDirectory() as root:
        repo = os.path.join(root, "repo")
        os.makedirs(repo)
        _git(repo, "init")
        readme = os.path.join(repo, "README.md")
        with open(readme, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("safe\n")
        _git(repo, "add", "README.md")
        _git(repo, "commit", "-m", "init")
        base = _git(repo, "rev-parse", "HEAD").stdout.strip()
        app = os.path.join(repo, "app")
        os.makedirs(app)
        with open(os.path.join(app, "settings.py"), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(BODY)
        _git(repo, "add", "app/settings.py")
        _git(repo, "commit", "-m", "leak")
        db = Database(os.path.join(root, "keys.db"))
        found = queue.Queue()
        scanner = LocalScanner(
            repo, found, threading.Event(), db=db, since_ref=base,
        )
        scanner.run()
        rows = []
        while not found.empty():
            rows.append(found.get_nowait())
        assert scanner.stats.get("error") is None
        assert len(rows) == 1
        assert rows[0].api_key == KEY


def test_since_ref_skips_unchanged_old_key():
    with tempfile.TemporaryDirectory() as root:
        repo = os.path.join(root, "repo")
        os.makedirs(repo)
        _git(repo, "init")
        app = os.path.join(repo, "app")
        os.makedirs(app)
        with open(os.path.join(app, "settings.py"), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(BODY)
        _git(repo, "add", "app/settings.py")
        _git(repo, "commit", "-m", "leak")
        base = _git(repo, "rev-parse", "HEAD").stdout.strip()
        with open(os.path.join(repo, "README.md"), "w", encoding="utf-8", newline="\n") as handle:
            handle.write("later\n")
        _git(repo, "add", "README.md")
        _git(repo, "commit", "-m", "docs")
        db = Database(os.path.join(root, "keys.db"))
        found = queue.Queue()
        scanner = LocalScanner(
            repo, found, threading.Event(), db=db, since_ref=base,
        )
        scanner.run()
        rows = []
        while not found.empty():
            rows.append(found.get_nowait())
        assert rows == []


def test_since_ref_missing_sets_error():
    with tempfile.TemporaryDirectory() as root:
        repo = os.path.join(root, "repo")
        os.makedirs(repo)
        _git(repo, "init")
        with open(os.path.join(repo, "README.md"), "w", encoding="utf-8") as handle:
            handle.write("x\n")
        _git(repo, "add", "README.md")
        _git(repo, "commit", "-m", "init")
        db = Database(os.path.join(root, "keys.db"))
        scanner = LocalScanner(
            repo, queue.Queue(), threading.Event(), db=db, since_ref="no-such-ref",
        )
        scanner.run()
        assert scanner.stats.get("error") == "since-ref"


def test_action_yaml_is_composite():
    text = Path("action.yml").read_text(encoding="utf-8")
    assert "aikeyscan --authorized" in text
    assert "--since-ref" in text
    assert "--baseline" in text
    assert "upload-sarif" in text
