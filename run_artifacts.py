"""Scan run artifacts: findings.json, report.md, optional SARIF, exit codes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from aikeyscan import __version__

EXIT_OK = 0
EXIT_CONFIG = 1
EXIT_LIVE = 2

STATUS_LIVE = "live"
STATUS_DEAD = "dead"
STATUS_QUOTA = "quota"
STATUS_UNKNOWN = "unknown"

_LIVE_PUBLIC = frozenset({STATUS_LIVE, STATUS_QUOTA})


def checked_host_from_url(base_url: str) -> str:
    text = (base_url or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = "https://" + text
    host = urlparse(text).hostname
    return (host or "").lower()


def public_status(status: str) -> str:
    raw = (status or "").strip().lower()
    if raw == "valid":
        return STATUS_LIVE
    if raw == "quota_exceeded":
        return STATUS_QUOTA
    if raw == "invalid":
        return STATUS_DEAD
    return STATUS_UNKNOWN


def persist_status(status) -> str:
    """Map a validator status onto stored values. Network/indeterminate -> unknown."""
    from database import KeyStatus

    if isinstance(status, KeyStatus):
        value = status.value
    else:
        value = str(status or "").strip().lower()
    if value in (
        KeyStatus.VALID.value,
        KeyStatus.INVALID.value,
        KeyStatus.QUOTA_EXCEEDED.value,
        KeyStatus.UNKNOWN.value,
    ):
        return value
    return KeyStatus.UNKNOWN.value


def live_count(findings: list) -> int:
    return sum(1 for item in findings if item.get("status") in _LIVE_PUBLIC)


def exit_code_for_findings(findings: list) -> int:
    return EXIT_LIVE if live_count(findings) else EXIT_OK


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render_run_markdown(document: dict, run_id: str = "") -> str:
    findings = document.get("findings") or []
    generated = document.get("generated_at") or ""
    live = live_count(findings)
    lines = [
        "# Scan report",
        "",
        f"- run_id: `{run_id or document.get('run_id') or ''}`",
        f"- generated_at: {generated}",
        f"- findings: {len(findings)}",
        f"- live or quota: {live}",
        "",
        "| Platform | Status | Preview | Checked host | Location |",
        "|---|---|---|---|---|",
    ]
    if not findings:
        lines.append("| — | — | — | — | — |")
    else:
        for item in findings:
            lines.append(
                "| {platform} | {status} | `{preview}` | {host} | {location} |".format(
                    platform=_cell(item.get("platform")),
                    status=_cell(item.get("status")),
                    preview=_cell(item.get("preview")),
                    host=_cell(item.get("checked_host")),
                    location=_cell(item.get("location")),
                )
            )
    lines.append("")
    lines.append("This file has no raw keys. Mark rotated with `--set-disposition <fingerprint> rotated`.")
    lines.append("")
    return "\n".join(lines)


def _cell(value) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def build_sarif(document: dict) -> dict:
    results = []
    for item in document.get("findings") or []:
        status = item.get("status") or STATUS_UNKNOWN
        if status in _LIVE_PUBLIC:
            level = "error"
        elif status == STATUS_UNKNOWN:
            level = "warning"
        else:
            level = "note"
        path = item.get("path") or item.get("location") or "unknown"
        message = "{platform} {status} at {host} ({preview})".format(
            platform=item.get("platform") or "unknown",
            status=status,
            host=item.get("checked_host") or "unknown-host",
            preview=item.get("preview") or "",
        )
        result = {
            "ruleId": "ai-key-pair",
            "level": level,
            "message": {"text": message},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": path},
                }
            }],
            "partialFingerprints": {
                "aikeyscan/fingerprint": item.get("fingerprint") or "",
            },
        }
        results.append(result)
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "aikeyscan",
                    "version": __version__,
                    "informationUri": "https://github.com/Coff0xc/Github-API-scan",
                    "rules": [{
                        "id": "ai-key-pair",
                        "shortDescription": {"text": "AI API key paired with the host that was checked"},
                    }],
                }
            },
            "results": results,
        }],
    }


def write_scan_artifacts(
    db_path: str,
    run_id: str = "",
    *,
    findings_json: str = "findings.json",
    live_only: bool = False,
    fmt: str = "json",
    report_path: str = "",
    runs_root: Optional[Path] = None,
) -> tuple[str, int]:
    """Write findings.json + report.md (and SARIF when requested). Return summary and exit code."""
    from findings_feed import build_document

    full = build_document(db_path, run_id=run_id or None, live_only=False)
    document = build_document(db_path, run_id=run_id or None, live_only=live_only) if live_only else full
    if run_id:
        document = dict(document)
        document["run_id"] = run_id

    root = Path(runs_root) if runs_root else Path(".aikeyscan") / "runs"
    run_dir = root / (run_id or "adhoc")
    run_dir.mkdir(parents=True, exist_ok=True)

    findings_file = run_dir / "findings.json"
    _write_json(findings_file, document)
    cwd_json = Path(findings_json)
    if cwd_json.resolve() != findings_file.resolve():
        cwd_json.parent.mkdir(parents=True, exist_ok=True)
        cwd_json.write_text(findings_file.read_text(encoding="utf-8"), encoding="utf-8")

    markdown = render_run_markdown(document, run_id)
    (run_dir / "report.md").write_text(markdown, encoding="utf-8")
    if report_path:
        extra = Path(report_path)
        extra.parent.mkdir(parents=True, exist_ok=True)
        extra.write_text(markdown, encoding="utf-8")

    formats = {part.strip().lower() for part in (fmt or "json").split(",") if part.strip()}
    if "all" in formats:
        formats.update({"json", "sarif"})
    sarif_path = None
    if "sarif" in formats:
        sarif_path = run_dir / "results.sarif"
        _write_json(sarif_path, build_sarif(document))

    code = exit_code_for_findings(full.get("findings") or [])
    lines = [
        f"已写出 {len(document.get('findings') or [])} 条发现: {cwd_json}",
        f"  运行目录: {run_dir}",
        "  文件不含明文 Key。",
    ]
    if sarif_path:
        lines.append(f"  SARIF: {sarif_path}")
    return "\n".join(lines), code
