"""
本地资产扫描模块
================

授权渗透/自有资产审计场景：直接扫描本地目录与**全量 Git 历史**，
发现泄露凭据后走统一验证管线（验证真伪 → 余额/权限评估 → 入库）。

泄露最常藏在历史提交里（文件后来被删但 .git 里还在），因此 git
历史扫描默认开启，这也是 gitleaks / TruffleHog 的核心工作方式。

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
    ScanResult, decode_bpe_variants, should_skip_file,
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
    ):
        self.root = os.path.abspath(root)
        self.result_queue = result_queue
        self.stop_event = stop_event
        self.dashboard = dashboard
        self.scan_git_history = scan_git_history

        self._patterns = {
            name: re.compile(pattern)
            for name, pattern in REGEX_PATTERNS.items()
            if name != "azure"  # azure 走上下文识别，正则太宽
        }
        self._processed: Set[str] = set()
        self._lock = threading.Lock()

        self.stats = {"files_scanned": 0, "commits_scanned": 0, "found": 0, "skipped": 0}

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

        self._log(f"本地扫描完成: 文件 {self.stats['files_scanned']}, "
                  f"提交 {self.stats['commits_scanned']}, "
                  f"发现 {self.stats['found']}, 跳过 {self.stats['skipped']}", "INFO")

    # ------------------------------------------------------------------
    # 公开目录扫描（历史扫描在内部单独读取 .git，不重复走此路径）
    # ------------------------------------------------------------------
    def _scan_worktree(self):
        skip_dirs = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', 'dist', 'build'}
        for dirpath, dirnames, filenames in os.walk(self.root):
            if self.stop_event.is_set():
                return
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            for fn in filenames:
                if self.stop_event.is_set():
                    return
                path = os.path.join(dirpath, fn)
                rel = os.path.relpath(path, self.root).replace(os.sep, '/')
                try:
                    size = os.path.getsize(path)
                    skip, reason = should_skip_file(rel, size)
                    if skip:
                        self.stats["skipped"] += 1
                        continue
                    if size > config.max_file_size_kb * 1024:
                        continue
                    with open(path, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read()
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
        cmd = ["git", "-C", self.root, "log", "--all", "-p", "-U0",
               "--no-color", "--full-history"]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    text=True, encoding='utf-8', errors='replace')
        except FileNotFoundError:
            self._log("git 命令不可用，跳过历史扫描", "WARN")
            return

        current_commit = ""
        current_file = ""
        buf: List[str] = []
        buf_len = 0

        def flush():
            nonlocal buf, buf_len
            if buf and current_file:
                content = "".join(buf)[:self.MAX_CHUNK_CHARS]
                self._extract(content,
                              f"local://git@{current_commit or 'worktree'}:{current_file}")
            buf = []
            buf_len = 0

        try:
            for line in proc.stdout:
                if self.stop_event.is_set():
                    break
                if line.startswith("commit "):
                    flush()
                    current_commit = line.split()[1][:10]
                    self.stats["commits_scanned"] += 1
                elif line.startswith("+++ b/"):
                    flush()
                    current_file = line[6:].strip()
                elif line.startswith("diff --git"):
                    flush()
                else:
                    buf.append(line)
                    buf_len += len(line)
                    if buf_len > self.MAX_CHUNK_CHARS:
                        flush()
        finally:
            flush()
            proc.terminate()

    # ------------------------------------------------------------------
    # 提取逻辑（与 scanner.py 管线同源：BPE 解码 + 正则 + 熵/测试词过滤）
    # ------------------------------------------------------------------
    def _extract(self, content: str, source_url: str):
        decoded = decode_bpe_variants(content)
        for platform, pattern in self._patterns.items():
            for variant in (content, decoded):
                for match in pattern.finditer(variant):
                    if self.stop_event.is_set():
                        return
                    api_key = match.group(0)

                    with self._lock:
                        if api_key in self._processed:
                            continue
                        self._processed.add(api_key)

                    if self._looks_like_test_key(api_key):
                        self.stats["skipped"] += 1
                        continue

                    context = content[max(0, match.start() - 300):match.end() + 300]
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

    @staticmethod
    def _extract_base_url(context: str) -> str:
        """从上下文提取 base_url（优先变量赋值形态，回退首个 http URL）"""
        for pattern in BASE_URL_PATTERNS:
            m = re.search(pattern, context)
            if m:
                url = m.group(1) if m.groups() else m.group(0)
                if url.startswith("http"):
                    return url.rstrip('/')
        return ""

    def _log(self, message: str, level: str = "INFO"):
        if self.dashboard:
            try:
                self.dashboard.add_log(message, level)
            except Exception:
                pass
        logger.debug(f"[LocalScanner] {message}")


# ============================================================================
#                              启动函数
# ============================================================================

def start_local_scanner(
    root: str,
    result_queue: queue.Queue,
    stop_event: threading.Event,
    dashboard=None,
    scan_git_history: bool = True,
) -> threading.Thread:
    """启动本地扫描线程"""
    scanner = LocalScanner(root, result_queue, stop_event, dashboard, scan_git_history)
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
        scan_git_history=scan_git_history
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
