"""
SearchCode 扫描源 - 从 searchcode.com 搜索 API Key

特点:
- 免费 API，无需认证
- 搜索多个代码托管平台
- 支持正则搜索
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

from config import config, REGEX_PATTERNS
from scanner import ScanResult, calculate_entropy, is_test_key, ENTROPY_THRESHOLD


# SearchCode API
SEARCHCODE_API = "https://searchcode.com/api/codesearch_I/"
ASYNC_CONCURRENCY = 20
ASYNC_TIMEOUT = ClientTimeout(total=20, connect=10)

# 搜索关键词
SEARCHCODE_KEYWORDS = [
    "OPENAI_API_KEY",
    "sk-proj-",
    "ANTHROPIC_API_KEY",
    "sk-ant-api",
    "GEMINI_API_KEY",
    "AIzaSy",
    "HUGGINGFACE_TOKEN",
    "hf_",
    "GROQ_API_KEY",
    "gsk_",
    "DEEPSEEK_API_KEY",
    "AWS_SECRET_ACCESS_KEY",
    "STRIPE_SECRET_KEY",
    "sk_live_",
]


@dataclass
class CodeResult:
    """搜索结果"""
    id: str
    filename: str
    repo: str
    url: str
    lines: dict


class SearchCodeScanner:
    """SearchCode 扫描器"""

    def __init__(
        self,
        result_queue: queue.Queue,
        stop_event: threading.Event,
        dashboard=None
    ):
        self.result_queue = result_queue
        self.stop_event = stop_event
        self.dashboard = dashboard

        self._processed_ids: Set[str] = set()
        self._processed_lock = threading.Lock()

        self._key_patterns = {
            platform: re.compile(pattern)
            for platform, pattern in REGEX_PATTERNS.items()
            if platform != "azure"
        }

        self.stats = {"searched": 0, "keys_found": 0}
        self._session: Optional[aiohttp.ClientSession] = None

    def _log(self, message: str, level: str = "INFO"):
        if self.dashboard:
            self.dashboard.add_log(f"[SearchCode] {message}", level)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=ASYNC_TIMEOUT, trust_env=True)
        return self._session

    async def _close_session(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _search(self, keyword: str, page: int = 0) -> List[CodeResult]:
        """搜索代码"""
        results = []
        try:
            session = await self._get_session()
            params = {"q": keyword, "p": page, "per_page": 100}
            proxy = config.proxy_url if config.proxy_url else None

            async with session.get(SEARCHCODE_API, params=params, proxy=proxy) as resp:
                if resp.status != 200:
                    return []

                data = await resp.json()
                for item in data.get("results", []):
                    results.append(CodeResult(
                        id=str(item.get("id", "")),
                        filename=item.get("filename", ""),
                        repo=item.get("repo", ""),
                        url=item.get("url", ""),
                        lines=item.get("lines", {})
                    ))
        except Exception as e:
            self._log(f"搜索异常: {type(e).__name__}", "ERROR")

        return results

    def _extract_keys(self, code_result: CodeResult) -> List[ScanResult]:
        """从搜索结果提取 Key"""
        results = []
        content = "\n".join(code_result.lines.values())

        for platform, pattern in self._key_patterns.items():
            for match in pattern.finditer(content):
                api_key = match.group(0)

                if is_test_key(api_key):
                    continue

                key_body = api_key
                for prefix in ['sk-proj-', 'sk-ant-', 'sk-', 'AIza', 'hf_', 'gsk_']:
                    if api_key.startswith(prefix):
                        key_body = api_key[len(prefix):]
                        break

                if calculate_entropy(key_body) < ENTROPY_THRESHOLD:
                    continue

                results.append(ScanResult(
                    platform=platform,
                    api_key=api_key,
                    base_url=config.default_base_urls.get(platform, ""),
                    source_url=code_result.url,
                    context=content[:500]
                ))

        return results

    async def _scan_keyword(self, keyword: str) -> int:
        """扫描单个关键词"""
        found = 0
        self._log(f"搜索: {keyword}", "SCAN")

        for page in range(3):  # 最多 3 页
            if self.stop_event.is_set():
                break

            results = await self._search(keyword, page)
            if not results:
                break

            for code_result in results:
                with self._processed_lock:
                    if code_result.id in self._processed_ids:
                        continue
                    self._processed_ids.add(code_result.id)

                self.stats["searched"] += 1
                keys = self._extract_keys(code_result)

                for key_result in keys:
                    try:
                        self.result_queue.put(key_result, timeout=5)
                        found += 1
                        self.stats["keys_found"] += 1
                        self._log(f"发现 {key_result.platform.upper()}: {key_result.api_key[:15]}...", "FOUND")
                    except queue.Full:
                        pass

            await asyncio.sleep(1)  # 避免请求过快

        return found

    def run(self):
        """运行扫描器"""
        self._log("SearchCode 扫描器启动", "INFO")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            while not self.stop_event.is_set():
                total_found = 0

                for keyword in SEARCHCODE_KEYWORDS:
                    if self.stop_event.is_set():
                        break

                    found = loop.run_until_complete(self._scan_keyword(keyword))
                    total_found += found
                    time.sleep(2)

                if total_found > 0:
                    self._log(f"本轮发现 {total_found} 个 Key", "INFO")

                self._log("等待 5 分钟...", "INFO")
                for _ in range(300):
                    if self.stop_event.is_set():
                        break
                    time.sleep(1)

        finally:
            loop.run_until_complete(self._close_session())
            loop.close()

        self._log("SearchCode 扫描器停止", "INFO")


def start_searchcode_scanner(
    result_queue: queue.Queue,
    stop_event: threading.Event,
    dashboard=None
) -> threading.Thread:
    """启动 SearchCode 扫描器"""
    scanner = SearchCodeScanner(result_queue, stop_event, dashboard)
    thread = threading.Thread(target=scanner.run, name="SearchCodeScanner", daemon=True)
    thread.start()
    return thread
