"""
Pastebin 扫描源 - 从 Pastebin 公开 Paste 中扫描 API Key

数据源:
1. Pastebin Scraping API (需要 Pro 账户)
2. PastebinScraper 公开列表 (免费)
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


# Pastebin 配置
PASTEBIN_SCRAPE_URL = "https://scrape.pastebin.com/api_scraping.php"
PASTEBIN_RAW_URL = "https://scrape.pastebin.com/api_scrape_item.php?i="
PASTEBIN_PUBLIC_URL = "https://pastebin.com/raw/"

# 并发配置
ASYNC_CONCURRENCY = 30
ASYNC_TIMEOUT = ClientTimeout(total=15, connect=8)


@dataclass
class PasteMetadata:
    """Paste 元数据"""
    key: str
    title: str
    syntax: str
    size: int
    date: str
    url: str


class PastebinScanner:
    """
    Pastebin 扫描器

    支持两种模式:
    1. Scraping API (需要 Pro 账户 API Key)
    2. 公开 Paste 列表爬取 (免费但速度慢)
    """

    def __init__(
        self,
        result_queue: queue.Queue,
        stop_event: threading.Event,
        dashboard=None,
        api_key: str = ""
    ):
        self.result_queue = result_queue
        self.stop_event = stop_event
        self.dashboard = dashboard
        self.api_key = api_key  # Pastebin Pro API Key

        # 已处理的 Paste Key
        self._processed_pastes: Set[str] = set()
        self._processed_lock = threading.Lock()

        # 编译正则
        self._key_patterns = {
            platform: re.compile(pattern)
            for platform, pattern in REGEX_PATTERNS.items()
            if platform != "azure"  # Azure 需要特殊处理
        }

        # 统计
        self.stats = {
            "pastes_scanned": 0,
            "keys_found": 0,
        }

        # aiohttp session
        self._session: Optional[aiohttp.ClientSession] = None

    def _log(self, message: str, level: str = "INFO"):
        """输出日志"""
        if self.dashboard:
            self.dashboard.add_log(f"[Pastebin] {message}", level)

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取 aiohttp session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=ASYNC_TIMEOUT,
                trust_env=True
            )
        return self._session

    async def _close_session(self):
        """关闭 session"""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _fetch_recent_pastes(self, limit: int = 100) -> List[PasteMetadata]:
        """
        获取最近的公开 Paste 列表

        需要 Pastebin Pro API Key
        """
        if not self.api_key:
            self._log("未配置 Pastebin API Key，跳过 Scraping API", "WARN")
            return []

        try:
            session = await self._get_session()
            url = f"{PASTEBIN_SCRAPE_URL}?limit={limit}"
            proxy = config.proxy_url if config.proxy_url else None

            async with session.get(url, proxy=proxy) as resp:
                if resp.status != 200:
                    self._log(f"获取 Paste 列表失败: HTTP {resp.status}", "ERROR")
                    return []

                data = await resp.json()
                pastes = []
                for item in data:
                    pastes.append(PasteMetadata(
                        key=item.get("key", ""),
                        title=item.get("title", ""),
                        syntax=item.get("syntax", ""),
                        size=int(item.get("size", 0)),
                        date=item.get("date", ""),
                        url=f"https://pastebin.com/{item.get('key', '')}"
                    ))
                return pastes
        except Exception as e:
            self._log(f"获取 Paste 列表异常: {type(e).__name__}", "ERROR")
            return []

    async def _fetch_paste_content(self, paste_key: str) -> Optional[str]:
        """获取 Paste 内容"""
        try:
            session = await self._get_session()

            # 优先使用 Scraping API
            if self.api_key:
                url = f"{PASTEBIN_RAW_URL}{paste_key}"
            else:
                url = f"{PASTEBIN_PUBLIC_URL}{paste_key}"

            proxy = config.proxy_url if config.proxy_url else None

            async with session.get(url, proxy=proxy) as resp:
                if resp.status == 200:
                    return await resp.text(errors='ignore')
                return None
        except Exception:
            return None

    def _extract_keys(self, content: str, source_url: str) -> List[ScanResult]:
        """从内容中提取 API Key"""
        results = []

        for platform, pattern in self._key_patterns.items():
            for match in pattern.finditer(content):
                api_key = match.group(0)

                # 测试 Key 检测
                if is_test_key(api_key):
                    continue

                # 熵值过滤
                key_body = api_key
                prefixes = ['sk-proj-', 'sk-ant-', 'sk-', 'AIza', 'hf_', 'gsk_']
                for prefix in prefixes:
                    if api_key.startswith(prefix):
                        key_body = api_key[len(prefix):]
                        break

                if calculate_entropy(key_body) < ENTROPY_THRESHOLD:
                    continue

                # 提取上下文
                start = max(0, match.start() - 200)
                end = min(len(content), match.end() + 200)
                context = content[start:end]

                results.append(ScanResult(
                    platform=platform,
                    api_key=api_key,
                    base_url=config.default_base_urls.get(platform, ""),
                    source_url=source_url,
                    context=context
                ))

        return results

    async def _scan_paste(self, paste: PasteMetadata) -> int:
        """扫描单个 Paste"""
        # 检查是否已处理
        with self._processed_lock:
            if paste.key in self._processed_pastes:
                return 0
            self._processed_pastes.add(paste.key)

        # 获取内容
        content = await self._fetch_paste_content(paste.key)
        if not content:
            return 0

        self.stats["pastes_scanned"] += 1

        # 提取 Key
        results = self._extract_keys(content, paste.url)

        for result in results:
            try:
                self.result_queue.put(result, timeout=5)
                self.stats["keys_found"] += 1
                self._log(f"发现 {result.platform.upper()} Key: {result.api_key[:12]}...", "FOUND")
            except queue.Full:
                pass

        return len(results)

    async def _scan_batch(self, pastes: List[PasteMetadata]) -> int:
        """批量扫描 Paste"""
        semaphore = asyncio.Semaphore(ASYNC_CONCURRENCY)

        async def scan_one(paste):
            async with semaphore:
                return await self._scan_paste(paste)

        tasks = [scan_one(p) for p in pastes]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return sum(r for r in results if isinstance(r, int))

    def run(self):
        """运行扫描器主循环"""
        self._log("Pastebin 扫描器启动", "INFO")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            while not self.stop_event.is_set():
                # 获取最近的 Paste
                pastes = loop.run_until_complete(self._fetch_recent_pastes(100))

                if pastes:
                    self._log(f"获取到 {len(pastes)} 个 Paste", "SCAN")
                    found = loop.run_until_complete(self._scan_batch(pastes))
                    if found > 0:
                        self._log(f"本轮发现 {found} 个 Key", "INFO")

                # 等待下一轮
                for _ in range(30):  # 30秒间隔
                    if self.stop_event.is_set():
                        break
                    time.sleep(1)
        finally:
            loop.run_until_complete(self._close_session())
            loop.close()

        self._log("Pastebin 扫描器停止", "INFO")


def start_pastebin_scanner(
    result_queue: queue.Queue,
    stop_event: threading.Event,
    dashboard=None,
    api_key: str = ""
) -> threading.Thread:
    """启动 Pastebin 扫描器线程"""
    scanner = PastebinScanner(result_queue, stop_event, dashboard, api_key)
    thread = threading.Thread(
        target=scanner.run,
        name="PastebinScanner",
        daemon=True
    )
    thread.start()
    return thread
