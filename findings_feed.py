"""
给 Grok Bot / Muse 读的发现管道。

输出只有位置、平台、指纹、脱敏预览和处置状态。
没有明文 Key，没有余额，没有验证接口。

代理把处置写进另一份 JSON，本机再用 --apply-dispositions 写回数据库。
代理不拿数据库文件，也不拿 DASHBOARD_TOKEN。
"""

import json
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import urlparse

from database import Database

SCHEMA = "findings.v1"
DISPOSITIONS = ("open", "notified", "rotated", "false_positive")
_FINDING_FIELDS = (
    "fingerprint",
    "platform",
    "preview",
    "repo",
    "path",
    "commit",
    "location",
    "disposition",
    "found_time",
)


def parse_location(url: str) -> dict:
    """从 GitHub / Gist 链接拆出仓库、路径、提交或分支。拆不开时留空。"""
    repo = ""
    path = ""
    commit = ""
    if not url:
        return {"repo": repo, "path": path, "commit": commit}
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    parts = [part for part in parsed.path.split("/") if part]
    if host.endswith("github.com") and not host.startswith("gist.") and len(parts) >= 2:
        repo = f"{parts[0]}/{parts[1]}"
        if len(parts) >= 4 and parts[2] in ("blob", "commit"):
            commit = parts[3]
            if parts[2] == "blob":
                path = "/".join(parts[4:])
    elif "gist.github.com" in host and parts:
        repo = f"gist:{parts[0]}"
        path = parts[1] if len(parts) > 1 else ""
    return {"repo": repo, "path": path, "commit": commit}


def _finding_from_row(row: dict) -> dict:
    place = parse_location(row.get("location") or "")
    disposition = row.get("disposition") or "open"
    if disposition not in DISPOSITIONS:
        disposition = "open"
    return {
        "fingerprint": row.get("fingerprint") or "",
        "platform": row.get("platform") or "",
        "preview": row.get("preview") or "",
        "repo": place["repo"],
        "path": place["path"],
        "commit": place["commit"],
        "location": row.get("location") or "",
        "disposition": disposition,
        "found_time": row.get("found_time") or "",
    }


def build_document(db_path: str) -> dict:
    db = Database(db_path)
    findings = [_finding_from_row(row) for row in db.list_finding_sources()]
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "findings": findings,
    }


def write_findings(db_path: str, out_path: str) -> str:
    document = build_document(db_path)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return (
        f"已写出 {len(document['findings'])} 条发现: {out_path}\n"
        "  文件不含明文 Key。把处置状态写回时用 --apply-dispositions。"
    )


def _updates_from_payload(payload) -> Iterable[dict]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("updates", "findings"):
            if isinstance(payload.get(key), list):
                return payload[key]
    raise ValueError("处置文件必须是数组，或含 updates / findings 数组的对象")


def apply_dispositions(db_path: str, path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    updates = list(_updates_from_payload(payload))
    db = Database(db_path)
    applied = 0
    skipped = 0
    for item in updates:
        if not isinstance(item, dict):
            skipped += 1
            continue
        disposition = (item.get("disposition") or "").strip()
        fingerprint = item.get("fingerprint") or ""
        if disposition not in DISPOSITIONS or not db.set_disposition(fingerprint, disposition):
            skipped += 1
            continue
        applied += 1
    return f"处置已写回 {applied} 条，跳过 {skipped} 条。"


def set_one_disposition(db_path: str, fingerprint: str, disposition: str) -> str:
    if disposition not in DISPOSITIONS:
        allowed = ", ".join(DISPOSITIONS)
        return f"[ABORT] 处置状态必须是其中之一: {allowed}"
    db = Database(db_path)
    if not db.set_disposition(fingerprint, disposition):
        return "[ABORT] 没有匹配的指纹，或指纹不是 64 位十六进制。"
    return f"已把 {fingerprint} 标为 {disposition}。"
