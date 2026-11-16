"""Installable CLI: scan, dashboard, report, findings, disposition."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional, Sequence

COMMANDS = ("scan", "dashboard", "report", "findings", "disposition")

_ROOT_HELP = """usage: aikeyscan <command> [options]

Commands:
  scan          Scan an organization, repository, or local git tree
  dashboard     Open the local findings page for a run
  report        Write markdown / SARIF for a run
  findings      Write findings.v1 JSON
  disposition   Set open/notified/rotated/false_positive by fingerprint

Examples:
  aikeyscan scan --authorized --scan-local ./repo
  aikeyscan dashboard
  aikeyscan disposition <fingerprint> rotated

Run `aikeyscan scan --help` or `aikeyscan dashboard --help` for flags.
Bare flags (without a command) still run scan, for compatibility.
"""


def _normalize(argv: list[str]) -> list[str]:
    if not argv:
        return ["--help"]
    if argv[0] in COMMANDS or argv[0] in ("-h", "--help"):
        return argv
    return ["scan", *argv]


def _cmd_dashboard(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="aikeyscan dashboard")
    parser.add_argument("--db", default=os.getenv("DB_PATH", "leaked_keys.db"))
    parser.add_argument("--run", default="", help="run id (default: latest scan)")
    parser.add_argument("--all-runs", action="store_true", help="show every finding, not one run")
    parser.add_argument("--host", default="", help="bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args(argv)
    from web_dashboard import serve
    serve(
        db_path=args.db,
        run_id=args.run,
        host=args.host or None,
        port=args.port,
        all_runs=bool(args.all_runs),
    )
    return 0


def _cmd_findings(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="aikeyscan findings")
    parser.add_argument("--db", default=os.getenv("DB_PATH", "leaked_keys.db"))
    parser.add_argument("--run", default="", help="run id (default: all findings)")
    parser.add_argument("--out", default="findings.json")
    parser.add_argument("--live-only", action="store_true")
    args = parser.parse_args(argv)
    from findings_feed import build_document
    import json
    from pathlib import Path
    document = build_document(args.db, run_id=args.run or None, live_only=args.live_only)
    Path(args.out).write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(f"已写出 {len(document.get('findings') or [])} 条发现: {args.out}")
    return 0


def _cmd_report(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="aikeyscan report")
    parser.add_argument("--db", default=os.getenv("DB_PATH", "leaked_keys.db"))
    parser.add_argument("--run", default="", help="run id (default: latest)")
    parser.add_argument("--out", default="", help="markdown path")
    parser.add_argument("--format", default="json", help="json, sarif, or all")
    parser.add_argument("--live-only", action="store_true")
    args = parser.parse_args(argv)
    from database import Database
    from run_artifacts import write_scan_artifacts
    run_id = args.run or Database(args.db).latest_run_id()
    summary, code = write_scan_artifacts(
        args.db,
        run_id,
        findings_json="findings.json",
        live_only=args.live_only,
        fmt=args.format,
        report_path=args.out,
    )
    print(summary)
    return code


def _cmd_disposition(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="aikeyscan disposition")
    parser.add_argument("fingerprint", nargs="?", help="64-hex fingerprint")
    parser.add_argument("status", nargs="?", help="open/notified/rotated/false_positive")
    parser.add_argument("--apply", metavar="FILE", help="JSON with updates[]")
    parser.add_argument("--db", default=os.getenv("DB_PATH", "leaked_keys.db"))
    args = parser.parse_args(argv)
    from findings_feed import apply_dispositions, set_one_disposition
    if args.apply:
        print(apply_dispositions(args.db, args.apply))
        return 0
    if not args.fingerprint or not args.status:
        parser.error("need FINGERPRINT STATUS, or --apply FILE")
    text = set_one_disposition(args.db, args.fingerprint, args.status)
    print(text)
    return 1 if text.startswith("[ABORT]") else 0


def main(argv: Optional[Sequence[str]] = None) -> None:
    raw = list(argv) if argv is not None else sys.argv[1:]
    raw = _normalize(raw)
    if not raw or raw[0] in ("-h", "--help"):
        print(_ROOT_HELP.strip())
        raise SystemExit(0)
    cmd, *rest = raw
    if cmd == "scan":
        sys.argv = [sys.argv[0], *rest]
        from scanner_main import main as scan_main
        raise SystemExit(scan_main() or 0)
    if cmd == "dashboard":
        raise SystemExit(_cmd_dashboard(rest) or 0)
    if cmd == "findings":
        raise SystemExit(_cmd_findings(rest) or 0)
    if cmd == "report":
        raise SystemExit(_cmd_report(rest) or 0)
    if cmd == "disposition":
        raise SystemExit(_cmd_disposition(rest) or 0)
    print(_ROOT_HELP.strip())
    raise SystemExit(2)


if __name__ == "__main__":
    main()
