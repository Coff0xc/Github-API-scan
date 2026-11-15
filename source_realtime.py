"""
GitHub 实时事件监控 - 监控新提交中的 API Key 泄露

特点:
- 使用 GitHub Events API 实时监控
- 监控 PushEvent 中的新提交
- 发现即验证，抢占先机
"""

import re
import time
import asyncio
import threading
import queue
from typing import List, Optional, Set
from dataclasses import dataclass

import aiohttp
from aiohttp import ClientTimeout

from config import config, COMPILED_KEY_PATTERNS
from scanner import ScanResult, extract_source_keys


GITHUB_EVENTS_API = "https://api.github.com/events"
ASYNC_TIMEOUT = ClientTimeout(total=15, connect=10)

# 高价值关键词 - 快速过滤
HIGH_VALUE_KEYWORDS = [
    'sk-proj-', 'sk-ant-', 'AIzaSy', 'OPENAI_API_KEY',
    'ANTHROPIC_API_KEY', 'GEMINI_API_KEY', '.env'
]


@dataclass
class CommitFile:
    """提交文件信息"""
    filename: str
    raw_url: str
    repo: str
    sha: str


class RealtimeScanner:
    """实时事件扫描器"""

    def __init__(
        self,
        result_queue: queue.Queue,
        stop_event: threading.Event,
        dashboard=None,
        db=None,
    ):
        self.result_queue = result_queue
        self.stop_event = stop_event
        self.dashboard = dashboard
        self.db = db

        self._processed_shas: Set[str] = set()
        self._processed_lock = threading.Lock()

        self._key_patterns = {
            name: pattern
            for name, pattern in COMPILED_KEY_PATTERNS.items()
            if name != "aws_secret_key"
        }

        self.stats = {"events_checked": 0, "commits_scanned": 0, "keys_found": 0}
        self._session: Optional[aiohttp.ClientSession] = None
        self._last_etag: Optional[str] = None

    def _log(self, message: str, level: str = "INFO"):
        if self.dashboard:
            self.dashboard.add_log(f"[Realtime] {message}", level)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=ASYNC_TIMEOUT, trust_env=True)
        return self._session

    async def _close_session(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _fetch_events(self) -> List[dict]:
        """获取最新公开事件"""
        try:
            session = await self._get_session()
            headers = {"Accept": "application/vnd.github.v3+json"}

            # 使用 token 提高限额
            token = config.get_random_token()
            if token:
                headers["Authorization"] = f"token {token}"

            # 使用 ETag 避免重复
            if self._last_etag:
                headers["If-None-Match"] = self._last_etag

            proxy = config.proxy_url if config.proxy_url else None

            async with session.get(GITHUB_EVENTS_API, headers=headers, proxy=proxy) as resp:
                if resp.status == 304:  # Not Modified
                    return []
                if resp.status != 200:
                    return []

                self._last_etag = resp.headers.get("ETag")
                return await resp.json()

        except Exception as e:
            self._log(f"获取事件异常: {type(e).__name__}", "ERROR")
            return []

    async def _fetch_commit_content(self, repo: str, sha: str) -> Optional[str]:
        """获取提交的 patch 内容"""
        try:
            session = await self._get_session()
            url = f"https://api.github.com/repos/{repo}/commits/{sha}"
            headers = {
                "Accept": "application/vnd.github.v3+json"
            }

            token = config.get_random_token()
            if token:
                headers["Authorization"] = f"token {token}"

            proxy = config.proxy_url if config.proxy_url else None

            async with session.get(url, headers=headers, proxy=proxy) as resp:
                if resp.status != 200:
                    return None

                data = await resp.json()
                # 提取所有文件的 patch
                patches = []
                for file in data.get("files", []):
                    patch = file.get("patch", "")
                    filename = file.get("filename", "")
                    if patch:
                        patches.append(f"# {filename}\n{patch}")

                return "\n".join(patches)

        except Exception:
            return None

    def _quick_filter(self, content: str) -> bool:
        """快速过滤 - 检查是否包含高价值关键词"""
        content_lower = content.lower()
        return any(kw.lower() in content_lower for kw in HIGH_VALUE_KEYWORDS)

    def _extract_keys(self, content: str, source_url: str) -> List[ScanResult]:
        """提取 Key"""
        return extract_source_keys(
            self._key_patterns, content, source_url, context_pad=100, db=self.db,
        )

    async def _process_push_event(self, event: dict) -> int:
        """处理 PushEvent"""
        found = 0
        repo = event.get("repo", {}).get("name", "")
        payload = event.get("payload", {})
        commits = payload.get("commits", [])

        for commit in commits:
            sha = commit.get("sha", "")
            message = commit.get("message", "")

            with self._processed_lock:
                if sha in self._processed_shas:
                    continue
                self._processed_shas.add(sha)

            # 快速过滤 commit message
            if not self._quick_filter(message):
                # 获取完整 patch
                content = await self._fetch_commit_content(repo, sha)
                if not content:
                    continue
                if not self._quick_filter(content):
                    continue
            else:
                content = await self._fetch_commit_content(repo, sha)
                if not content:
                    continue

            self.stats["commits_scanned"] += 1
            source_url = f"https://github.com/{repo}/commit/{sha}"
            results = self._extract_keys(content, source_url)

            for result in results:
                try:
                    # 使用优先队列 - 新发现的放在前面
                    self.result_queue.put(result, timeout=1)
                    found += 1
                    self.stats["keys_found"] += 1
                    self._log(f"🔥 实时发现 {result.platform.upper()}: {result.api_key[:20]}...", "FOUND")
                except queue.Full:
                    pass

        return found

    async def _scan_cycle(self) -> int:
        """单次扫描循环"""
        events = await self._fetch_events()
        if not events:
            return 0

        self.stats["events_checked"] += len(events)
        found = 0

        # 只处理 PushEvent
        push_events = [e for e in events if e.get("type") == "PushEvent"]

        for event in push_events:
            if self.stop_event.is_set():
                break
            found += await self._process_push_event(event)

        return found

    def run(self):
        """运行扫描器"""
        self._log("实时监控启动 - 监控 GitHub 新提交", "INFO")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            while not self.stop_event.is_set():
                found = loop.run_until_complete(self._scan_cycle())

                if found > 0:
                    self._log(f"本轮发现 {found} 个 Key", "INFO")

                # 快速轮询 - 每 10 秒检查一次
                for _ in range(10):
                    if self.stop_event.is_set():
                        break
                    time.sleep(1)

        finally:
            loop.run_until_complete(self._close_session())
            loop.close()

        self._log("实时监控停止", "INFO")


def start_realtime_scanner(
    result_queue: queue.Queue,
    stop_event: threading.Event,
    dashboard=None,
    db=None,
) -> threading.Thread:
    """启动实时扫描器"""
    scanner = RealtimeScanner(result_queue, stop_event, dashboard, db=db)
    thread = threading.Thread(target=scanner.run, name="RealtimeScanner", daemon=True)
    thread.start()
    return thread
