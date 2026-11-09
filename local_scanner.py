"""
本地资产扫描模块
================

授权渗透/自有资产审计场景：直接扫描本地目录与全量 Git 历史，
发现泄露凭据后走统一验证管线。

历史扫描按 blob 去重：同一份内容无论出现在多少次提交里，只解析一次。
已经扫过的 blob 记在 scanned_blobs，下一次不再读。已经入库的密钥不再送去验证。

用法（main_v2.2.py / main.py）：
    python main_v2.2.py --authorized --scan-local /path/to/repo
    python main_v2.2.py --authorized --scan-local . --no-git-history
    python main_v2.2.py --authorized --report threat.md --reveal-report

仅扫描你拥有或获得书面授权的目录（见 AUTHORIZED_USE.md）。
"""

import os
import re
import queue
import subprocess
import threading
import time
from typing import List, Optional, Set

from loguru import logger

from config import config, REGEX_PATTERNS, BASE_URL_PATTERNS
from database import Database
from scanner import (
    ScanResult, content_variants, select_key_matches, should_skip_file,
    TEST_KEY_PATTERNS, ENTROPY_THRESHOLD, mask_key,
)
from utils import calculate_entropy


class LocalScanner:
    """本地目录 + Git 历史泄露扫描器（产出 ScanResult 进入统一验证管线）"""

    # 单个内容块上限，避免超大 diff/文件拖垮管线
    MAX_CHUNK_CHARS = 200_000

    def __init__(
        self,
        root: str,
        result_queue: queue.Queue,
        stop_event: threading.Event,
        dashboard=None,
        scan_git_history: bool = True,
        db: Optional[Database] = None,
    ):
        self.root = os.path.abspath(root)
        self.result_queue = result_queue
        self.stop_event = stop_event
        self.dashboard = dashboard
        self.scan_git_history = scan_git_history
        self.db = db if db is not None else Database(config.db_path)

        self._patterns = {
            name: re.compile(pattern)
            for name, pattern in REGEX_PATTERNS.items()
            if name != "azure"  # azure 走上下文识别，正则太宽
        }
        self._base_url_patterns = [
            re.compile(pattern, re.IGNORECASE) for pattern in BASE_URL_PATTERNS
        ]
        self._processed: Set[str] = set()
        self._seen_blobs: Set[str] = set()
        self._pending_blobs: List[str] = []
        self._lock = threading.Lock()
        self._file_limit = config.max_file_size_kb * 1024

        self.stats = {
            "files_scanned": 0,
            "commits_scanned": 0,
            "blobs_scanned": 0,
            "found": 0,
            "skipped": 0,
        }

    # ------------------------------------------------------------------
    def run(self):
        if not os.path.exists(self.root):
            self._log(f"路径不存在: {self.root}", "ERROR")
            return

        is_git = self._is_git_repo()
        self._log(f"本地扫描开始: {self.root} "
                  f"({'git 仓库: 当前文件 + ' + ('全量历史' if self.scan_git_history else '不含历史') if is_git else '普通目录'})",
                  "SCAN")

        if is_git and self.scan_git_history:
            self._scan_git_history()

        self._scan_worktree()

        self._log(
            f"本地扫描完成: 文件 {self.stats['files_scanned']}, "
            f"blob {self.stats['blobs_scanned']}, "
            f"提交 {self.stats['commits_scanned']}, "
            f"发现 {self.stats['found']}, 跳过 {self.stats['skipped']}",
            "INFO",
        )

    # ------------------------------------------------------------------
    # 公开目录扫描（历史扫描在内部单独读取 .git，不重复走此路径）
    # ------------------------------------------------------------------
    def _scan_worktree(self):
        skip_dirs = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', 'dist', 'build'}
        tracked = self._tracked_blob_shas()
        for dirpath, dirnames, filenames in os.walk(self.root):
            if self.stop_event.is_set():
                return
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            for fn in filenames:
                if self.stop_event.is_set():
                    return
                path = os.path.join(dirpath, fn)
                rel = os.path.relpath(path, self.root).replace(os.sep, '/')
                blob_sha = tracked.get(rel)
                if blob_sha and blob_sha in self._seen_blobs:
                    self.stats["skipped"] += 1
                    continue
                try:
                    size = os.path.getsize(path)
                    skip, _reason = should_skip_file(rel, size)
                    if skip or size > self._file_limit:
                        self.stats["skipped"] += 1
                        continue
                    with open(path, 'r', encoding='utf-8', errors='replace') as handle:
                        content = handle.read()
                    self.stats["files_scanned"] += 1
                    self._extract(content, f"local://{rel}")
                except (OSError, PermissionError):
                    continue

    # ------------------------------------------------------------------
    # 全量 Git 历史：git log --all -p 逐行流式解析
    # ------------------------------------------------------------------
    def _is_git_repo(self) -> bool:
        try:
            subprocess.run(["git", "-C", self.root, "rev-parse", "--git-dir"],
                           capture_output=True, timeout=10, check=True)
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def _scan_git_history(self):
        """每个 blob 读一次。提交说明单独扫，避免和文件内容混在同一段 diff 里。"""
        try:
            self._seen_blobs.update(self.db.load_scanned_blob_shas())
        except Exception as exc:
            self._log(f"读取已扫描 blob 失败: {exc}", "WARN")

        blobs = self._list_blobs()
        self.stats["commits_scanned"] = self._commit_count()
        pending = [(sha, path) for sha, path in blobs if sha not in self._seen_blobs]
        self.stats["skipped"] += len(blobs) - len(pending)
        self._cat_blobs(pending)
        self._flush_blobs()
        self._scan_commit_messages()

    def _list_blobs(self):
        try:
            proc = subprocess.run(
                ["git", "-C", self.root, "rev-list", "--all", "--objects"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                check=True,
            )
        except FileNotFoundError:
            self._log("git 命令不可用，跳过历史扫描", "WARN")
            return []
        except subprocess.SubprocessError as exc:
            self._log(f"列举 Git 对象失败: {exc}", "WARN")
            return []

        blobs = {}
        for line in proc.stdout.splitlines():
            sha, _, path = line.partition(" ")
            if len(sha) != 40 or not path:
                continue
            path = path.strip().replace("\\", "/")
            if sha in blobs or sha in self._seen_blobs:
                continue
            skip, _reason = should_skip_file(path, 0)
            if skip:
                continue
            blobs[sha] = path
        return list(blobs.items())

    def _commit_count(self) -> int:
        try:
            proc = subprocess.run(
                ["git", "-C", self.root, "rev-list", "--all", "--count"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                check=True,
            )
            return int(proc.stdout.strip() or "0")
        except (subprocess.SubprocessError, FileNotFoundError, ValueError):
            return 0

    def _cat_blobs(self, blobs: List[tuple]):
        if not blobs:
            return
        try:
            proc = subprocess.Popen(
                ["git", "-C", self.root, "cat-file", "--batch"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            self._log("git 命令不可用，跳过历史扫描", "WARN")
            return

        try:
            proc.stdin.write("".join(f"{sha}\n" for sha, _path in blobs).encode())
            proc.stdin.close()
            for sha, path in blobs:
                if self.stop_event.is_set():
                    break
                kind, data = _read_batch_object(proc.stdout)
                if kind != "blob" or data is None:
                    continue
                self._remember_blob(sha)
                if len(data) > self._file_limit or b"\x00" in data[:8192]:
                    self.stats["skipped"] += 1
                    continue
                text = data.decode("utf-8", errors="replace")
                if len(text) > self.MAX_CHUNK_CHARS:
                    text = text[:self.MAX_CHUNK_CHARS]
                self.stats["blobs_scanned"] += 1
                self._extract(text, f"local://git@{sha[:10]}:{path}")
        finally:
            proc.kill()
            proc.wait()

    def _remember_blob(self, sha: str):
        self._seen_blobs.add(sha)
        self._pending_blobs.append(sha)
        if len(self._pending_blobs) >= 100:
            self._flush_blobs()

    def _flush_blobs(self):
        if not self._pending_blobs:
            return
        try:
            self.db.mark_blobs_scanned(self._pending_blobs)
        except Exception as exc:
            self._log(f"写入已扫描 blob 失败: {exc}", "WARN")
        self._pending_blobs = []

    def _scan_commit_messages(self):
        try:
            proc = subprocess.run(
                ["git", "-C", self.root, "log", "--all", "--pretty=format:%x1e%H%n%B"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                check=True,
            )
        except (subprocess.SubprocessError, FileNotFoundError):
            return
        for block in proc.stdout.split("\x1e"):
            if self.stop_event.is_set():
                return
            block = block.strip()
            if not block:
                continue
            sha, _, body = block.partition("\n")
            if body.strip():
                self._extract(body, f"local://git@{sha[:10]}:commit-message")

    def _tracked_blob_shas(self) -> dict:
        try:
            proc = subprocess.run(
                ["git", "-C", self.root, "ls-files", "-s"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                check=True,
            )
        except (subprocess.SubprocessError, FileNotFoundError):
            return {}
        tracked = {}
        for line in proc.stdout.splitlines():
            meta, _, path = line.partition("\t")
            parts = meta.split()
            if len(parts) >= 2 and path:
                tracked[path.replace("\\", "/")] = parts[1]
        return tracked

    # ------------------------------------------------------------------
    # 提取逻辑（与 scanner.py 管线同源：BPE 解码 + 正则 + 熵/测试词过滤）
    # ------------------------------------------------------------------
    def _extract(self, content: str, source_url: str):
        for variant in content_variants(content):
            for start, end, platform, api_key in select_key_matches(self._patterns, variant):
                if self.stop_event.is_set():
                    return

                with self._lock:
                    if api_key in self._processed:
                        continue
                    self._processed.add(api_key)

                if self._looks_like_test_key(api_key):
                    self.stats["skipped"] += 1
                    continue

                if self.db.key_exists(api_key):
                    self.stats["skipped"] += 1
                    continue

                context = variant[max(0, start - 300):end + 300]
                base_url = self._extract_base_url(context)

                result = ScanResult(
                    platform=platform,
                    api_key=api_key,
                    base_url=base_url,
                    source_url=source_url,
                    is_relay=bool(base_url and base_url not in config.default_base_urls.values()),
                    context=context,
                )
                self.stats["found"] += 1
                self._log(f"[LOCAL] {platform} {mask_key(api_key)} @ {source_url}", "FOUND")
                try:
                    self.result_queue.put(result, timeout=5)
                except queue.Full:
                    self._log("结果队列已满，本地结果被丢弃", "WARN")

    def _looks_like_test_key(self, api_key: str) -> bool:
        """熵 + 测试词过滤（与 scanner 管线同标准）"""
        key_lower = api_key.lower()
        if any(w in key_lower for w in TEST_KEY_PATTERNS):
            return True
        stripped = re.sub(r'^(sk-proj-|sk-svcacct-|sk-ant-api\d+-|sk-ant-|sk-|AIza|hf_|gsk_|xai-|llama-|moonshot-|zhipu-|glm-|baichuan-|minimax-|co-|volc-|r8_|pplx-|fw_|wr-|ff-|yi-|step-|sensetime-|xf-|tiangong-|modal-|pk-|sk-or-v1-|sk_live_|rk_live_|ghp_|gho_|ghu_|ghs_|ghr_|xox[bpars]-|dop_v1_|shpat_|lin_api_|secret_|glpat-)', '', api_key)
        try:
            if calculate_entropy(stripped) < ENTROPY_THRESHOLD:
                return True
        except Exception:
            pass
        return False

    def _extract_base_url(self, context: str) -> str:
        """从上下文提取 base_url。赋值形式的模式排在通用 URL 前面。"""
        for pattern in self._base_url_patterns:
            match = pattern.search(context)
            if not match:
                continue
            url = match.group(1) if match.groups() else match.group(0)
            if url.startswith("http"):
                return url.rstrip("/")
        return ""

    def _log(self, message: str, level: str = "INFO"):
        if self.dashboard:
            try:
                self.dashboard.add_log(message, level)
            except Exception:
                pass
        logger.debug(f"[LocalScanner] {message}")


def _read_batch_object(stdout):
    """读取 git cat-file --batch 的一个对象。缺失时没有正文。"""
    header = stdout.readline()
    if not header:
        return "", None
    parts = header.decode("utf-8", errors="replace").strip().split()
    if len(parts) < 3 or parts[1] == "missing":
        return parts[1] if len(parts) > 1 else "", None
    size = int(parts[2])
    data = stdout.read(size)
    stdout.read(1)
    return parts[1], data


# ============================================================================
#                              启动函数
# ============================================================================

def start_local_scanner(
    root: str,
    result_queue: queue.Queue,
    stop_event: threading.Event,
    dashboard=None,
    scan_git_history: bool = True,
    db: Optional[Database] = None,
) -> threading.Thread:
    """启动本地扫描线程"""
    scanner = LocalScanner(
        root, result_queue, stop_event, dashboard, scan_git_history, db=db,
    )
    thread = threading.Thread(target=scanner.run, name="LocalScanner", daemon=True)
    thread.start()
    return thread


def run_local_scan(
    root: str,
    db_path: str = "",
    scan_git_history: bool = True,
    num_validators: int = 1,
):
    """
    本地扫描完整流程（含 TUI 与验证管线），供 main 入口直接调用。

    扫描结束（Ctrl+C 中断亦可）后返回数据库统计。
    """
    import time as _time
    from ui import Dashboard
    from validator import start_validators

    db = Database(db_path or config.db_path)
    result_queue = queue.Queue(maxsize=10000)
    stop_event = threading.Event()
    dashboard = Dashboard()

    dashboard.update_stats(total_tokens=0, is_running=True)

    validator_threads = start_validators(
        result_queue, db, stop_event, dashboard=dashboard, num_workers=num_validators
    )
    scanner_thread = start_local_scanner(
        root, result_queue, stop_event, dashboard=dashboard,
        scan_git_history=scan_git_history, db=db,
    )

    try:
        with dashboard.start():
            while scanner_thread.is_alive() or any(t.is_alive() for t in validator_threads):
                dashboard.update_stats(queue_size=result_queue.qsize())
                dashboard.refresh()
                _time.sleep(0.25)
    except KeyboardInterrupt:
        dashboard.add_log("收到中断信号，正在停止...", "WARN")
    finally:
        stop_event.set()
        # 给验证器 30s 清空队列余量
        deadline = _time.time() + 30
        while not result_queue.empty() and _time.time() < deadline:
            _time.sleep(0.5)

    return db.get_stats()
