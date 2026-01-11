#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
连接池管理器 - 优化 HTTP 连接复用

特性：
1. 连接池复用，减少连接开销
2. 自动清理过期连接
3. 连接健康检查
4. 支持多个域名的独立连接池
"""

import asyncio
import ssl
import time
from typing import Dict, Optional
from urllib.parse import urlparse

import aiohttp
from aiohttp import ClientTimeout, TCPConnector
from loguru import logger

from config import config


class ConnectionPool:
    """HTTP 连接池管理器"""

    def __init__(
        self,
        max_connections: int = 100,
        max_connections_per_host: int = 30,
        ttl_dns_cache: int = 300,
        timeout: int = 15
    ):
        self.max_connections = max_connections
        self.max_connections_per_host = max_connections_per_host
        self.ttl_dns_cache = ttl_dns_cache
        self.timeout = ClientTimeout(total=timeout, connect=10)

        # 域名 -> session 映射
        self._sessions: Dict[str, aiohttp.ClientSession] = {}
        self._session_create_times: Dict[str, float] = {}
        self._lock = asyncio.Lock()

        # 连接池配置
        self._ssl_context = ssl.create_default_context()
        self._ssl_context.check_hostname = True
        self._ssl_context.verify_mode = ssl.CERT_REQUIRED

        # 清理任务
        self._cleanup_task: Optional[asyncio.Task] = None
        self._session_ttl = 3600  # session 存活时间 1 小时

    async def start(self):
        """启动连接池"""
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        logger.info(f"连接池已启动 (最大连接: {self.max_connections})")

    async def stop(self):
        """停止连接池"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        await self.close_all()

    def _extract_domain(self, url: str) -> str:
        """从 URL 提取域名"""
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower()
        except Exception:
            return "default"

    async def get_session(self, url: str) -> aiohttp.ClientSession:
        """
        获取或创建 session

        为不同域名维护独立的 session，提高连接复用率
        """
        domain = self._extract_domain(url)

        async with self._lock:
            # 检查是否存在有效 session
            if domain in self._sessions:
                session = self._sessions[domain]
                if not session.closed:
                    # 检查 session 是否过期
                    create_time = self._session_create_times.get(domain, 0)
                    if time.time() - create_time < self._session_ttl:
                        return session
                    else:
                        # session 过期，关闭并重建
                        await session.close()
                        del self._sessions[domain]
                        del self._session_create_times[domain]

            # 创建新 session
            connector = TCPConnector(
                limit=self.max_connections,
                limit_per_host=self.max_connections_per_host,
                ttl_dns_cache=self.ttl_dns_cache,
                ssl=self._ssl_context,
                force_close=False,  # 启用连接复用
                enable_cleanup_closed=True
            )

            session = aiohttp.ClientSession(
                connector=connector,
                timeout=self.timeout,
                trust_env=True,
                connector_owner=True
            )

            self._sessions[domain] = session
            self._session_create_times[domain] = time.time()

            logger.debug(f"为域名 {domain} 创建新 session")
            return session

    async def _periodic_cleanup(self):
        """定期清理过期 session"""
        while True:
            try:
                await asyncio.sleep(600)  # 每 10 分钟清理一次
                await self._cleanup_expired_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"清理 session 异常: {e}")

    async def _cleanup_expired_sessions(self):
        """清理过期的 session"""
        async with self._lock:
            now = time.time()
            expired_domains = []

            for domain, create_time in self._session_create_times.items():
                if now - create_time >= self._session_ttl:
                    expired_domains.append(domain)

            for domain in expired_domains:
                session = self._sessions.get(domain)
                if session and not session.closed:
                    await session.close()
                del self._sessions[domain]
                del self._session_create_times[domain]
                logger.debug(f"清理过期 session: {domain}")

    async def close_all(self):
        """关闭所有 session"""
        async with self._lock:
            for session in self._sessions.values():
                if not session.closed:
                    await session.close()
            self._sessions.clear()
            self._session_create_times.clear()
        logger.info("所有连接已关闭")

    def get_stats(self) -> dict:
        """获取连接池统计信息"""
        return {
            "active_sessions": len(self._sessions),
            "domains": list(self._sessions.keys())
        }


# 全局连接池实例
_global_pool: Optional[ConnectionPool] = None


async def get_connection_pool() -> ConnectionPool:
    """获取全局连接池"""
    global _global_pool
    if _global_pool is None:
        _global_pool = ConnectionPool()
        await _global_pool.start()
    return _global_pool


async def close_connection_pool():
    """关闭全局连接池"""
    global _global_pool
    if _global_pool:
        await _global_pool.stop()
        _global_pool = None
