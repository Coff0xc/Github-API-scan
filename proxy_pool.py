"""
代理池模块 - 多代理轮换与健康检查

特性：
- 多代理自动轮换
- 代理健康检查
- 失败自动剔除
- 支持 HTTP/SOCKS5
"""

import asyncio
import aiohttp
import random
from typing import List, Optional, Dict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from loguru import logger


@dataclass
class ProxyInfo:
    """代理信息"""
    url: str
    protocol: str = "http"  # http, socks5
    fail_count: int = 0
    success_count: int = 0
    last_check: Optional[datetime] = None
    is_healthy: bool = True


class ProxyPool:
    """代理池管理器"""

    def __init__(
        self,
        proxies: List[str] = None,
        max_fail_count: int = 3,
        health_check_interval: int = 300
    ):
        self.proxies: List[ProxyInfo] = []
        self.max_fail_count = max_fail_count
        self.health_check_interval = health_check_interval
        self._index = 0
        self._lock = asyncio.Lock()

        if proxies:
            for p in proxies:
                self.add_proxy(p)

    def add_proxy(self, proxy_url: str):
        """添加代理"""
        protocol = "socks5" if proxy_url.startswith("socks") else "http"
        self.proxies.append(ProxyInfo(url=proxy_url, protocol=protocol))
        logger.info(f"添加代理: {proxy_url[:30]}...")

    def remove_proxy(self, proxy_url: str):
        """移除代理"""
        self.proxies = [p for p in self.proxies if p.url != proxy_url]

    async def get_proxy(self) -> Optional[str]:
        """获取下一个可用代理（轮询）"""
        async with self._lock:
            healthy = [p for p in self.proxies if p.is_healthy]
            if not healthy:
                return None

            # 轮询选择
            self._index = (self._index + 1) % len(healthy)
            return healthy[self._index].url

    async def get_random_proxy(self) -> Optional[str]:
        """随机获取可用代理"""
        healthy = [p for p in self.proxies if p.is_healthy]
        if not healthy:
            return None
        return random.choice(healthy).url

    async def report_success(self, proxy_url: str):
        """报告代理成功"""
        for p in self.proxies:
            if p.url == proxy_url:
                p.success_count += 1
                p.fail_count = 0
                p.is_healthy = True
                break

    async def report_failure(self, proxy_url: str):
        """报告代理失败"""
        for p in self.proxies:
            if p.url == proxy_url:
                p.fail_count += 1
                if p.fail_count >= self.max_fail_count:
                    p.is_healthy = False
                    logger.warning(f"代理标记为不健康: {proxy_url[:30]}...")
                break

    async def health_check(self, test_url: str = "https://api.openai.com"):
        """健康检查所有代理"""
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            for proxy in self.proxies:
                try:
                    async with session.get(test_url, proxy=proxy.url) as resp:
                        if resp.status < 500:
                            proxy.is_healthy = True
                            proxy.fail_count = 0
                        else:
                            proxy.fail_count += 1
                except Exception:
                    proxy.fail_count += 1

                if proxy.fail_count >= self.max_fail_count:
                    proxy.is_healthy = False

                proxy.last_check = datetime.now()

    def get_stats(self) -> Dict:
        """获取代理池统计"""
        healthy = sum(1 for p in self.proxies if p.is_healthy)
        return {
            "total": len(self.proxies),
            "healthy": healthy,
            "unhealthy": len(self.proxies) - healthy,
            "proxies": [
                {
                    "url": p.url[:30] + "...",
                    "healthy": p.is_healthy,
                    "success": p.success_count,
                    "fail": p.fail_count
                }
                for p in self.proxies
            ]
        }

    @property
    def has_healthy_proxy(self) -> bool:
        """是否有可用代理"""
        return any(p.is_healthy for p in self.proxies)


# 全局代理池
_proxy_pool: Optional[ProxyPool] = None


def init_proxy_pool(proxies: List[str]) -> ProxyPool:
    """初始化全局代理池"""
    global _proxy_pool
    _proxy_pool = ProxyPool(proxies)
    return _proxy_pool


def get_proxy_pool() -> Optional[ProxyPool]:
    """获取全局代理池"""
    return _proxy_pool


async def get_next_proxy() -> Optional[str]:
    """获取下一个代理"""
    if _proxy_pool:
        return await _proxy_pool.get_proxy()
    return None
