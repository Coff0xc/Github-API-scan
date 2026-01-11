"""
验证器模块 - 优化版 v2.1

新增优化：
1. 连接池管理 - 复用 HTTP 连接
2. 智能重试机制 - 指数退避
3. 改进的错误分类
4. 性能监控增强
"""

import asyncio
import ssl
from typing import Tuple, Optional, Dict, Any
from datetime import datetime
from dataclasses import dataclass

import aiohttp
from aiohttp import ClientTimeout
from loguru import logger

from config import (
    config,
    PROTECTED_DOMAINS,
    SAFE_HTTP_STATUS_CODES,
    CIRCUIT_BREAKER_HTTP_CODES,
    CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
    CIRCUIT_BREAKER_HALF_OPEN_REQUESTS
)
from database import Database, LeakedKey, KeyStatus
from connection_pool import get_connection_pool
from retry_handler import RetryHandler, RetryConfig, ErrorType

# 导入原有的熔断器和工具函数
from validator import (
    CircuitBreaker,
    circuit_breaker,
    mask_key,
    ValidationResult,
    MAX_CONCURRENCY,
    REQUEST_TIMEOUT,
    HIGH_VALUE_MODELS,
    RPM_ENTERPRISE_THRESHOLD,
    RPM_FREE_TRIAL_THRESHOLD
)


class OptimizedAsyncValidator:
    """
    优化版异步验证器

    v2.1 新特性：
    - 使用连接池复用 HTTP 连接
    - 智能重试机制（指数退避）
    - 改进的性能监控
    """

    def __init__(self, db: Database, dashboard=None):
        self.db = db
        self.dashboard = dashboard
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
        self._circuit_breaker = circuit_breaker

        # 新增：连接池和重试处理器
        self._connection_pool = None
        self._retry_handler = RetryHandler(RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            max_delay=10.0,
            exponential_base=2.0,
            jitter=True
        ))

        # 性能统计
        self._stats = {
            'total_validations': 0,
            'successful_validations': 0,
            'failed_validations': 0,
            'retried_validations': 0,
            'connection_reused': 0,
        }

    async def _get_session(self, url: str) -> aiohttp.ClientSession:
        """
        获取 session（使用连接池）

        优化：为不同域名维护独立的 session，提高连接复用率
        """
        if self._connection_pool is None:
            self._connection_pool = await get_connection_pool()

        session = await self._connection_pool.get_session(url)
        self._stats['connection_reused'] += 1
        return session

    async def close(self):
        """关闭资源"""
        # 连接池由全局管理，不需要在这里关闭
        pass

    def _get_proxy(self) -> Optional[str]:
        """获取代理 URL"""
        return config.proxy_url if config.proxy_url else None

    def _log(self, message: str, level: str = "INFO"):
        """输出日志"""
        if self.dashboard:
            self.dashboard.add_log(message, level)

    def _try_url_variants(self, base_url: str, path: str) -> list:
        """生成 URL 变体"""
        base_url = base_url.rstrip('/')
        path = path.lstrip('/')

        variants = [f"{base_url}/{path}"]

        if '/v1' not in base_url:
            variants.append(f"{base_url}/v1/{path}")

        if '/v1' in base_url:
            base_without_v1 = base_url.replace('/v1', '')
            variants.append(f"{base_without_v1}/v1/{path}")

        return variants

    # ========================================================================
    #                           熔断器集成方法
    # ========================================================================

    async def _check_circuit_breaker(self, base_url: str) -> Optional[ValidationResult]:
        """检查熔断器状态"""
        if not config.circuit_breaker_enabled:
            return None

        if not await self._circuit_breaker.is_allowed(base_url):
            self._log(f"熔断中: {base_url[:30]}...", "WARN")
            return ValidationResult(KeyStatus.CONNECTION_ERROR, "域名熔断中")

        return None

    async def _record_circuit_result(
        self,
        url: str,
        success: bool = False,
        error: Exception = None,
        http_status: int = None
    ):
        """记录请求结果到熔断器"""
        if not config.circuit_breaker_enabled:
            return

        if success:
            await self._circuit_breaker.record_success(url)
        else:
            await self._circuit_breaker.record_failure(url, error, http_status)

    def _is_likely_valid_relay(self, base_url: str) -> bool:
        """检查 URL 是否可能是有效的中转站 + SSRF 防护"""
        if not base_url:
            return True

        url_lower = base_url.lower()

        # SSRF 防护: 强制 HTTPS
        if not url_lower.startswith('https://'):
            if not (url_lower.startswith('http://localhost') or url_lower.startswith('http://127.0.0.1')):
                if url_lower.startswith('http://'):
                    return False

        # SSRF 防护: 阻止私有 IP
        try:
            from urllib.parse import urlparse
            import ipaddress
            parsed = urlparse(base_url)
            host = parsed.hostname or ''
            try:
                ip = ipaddress.ip_address(host)
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                    return False
            except ValueError:
                pass
            for suffix in ['.local', '.internal', '.corp', '.lan', '.home']:
                if host.endswith(suffix):
                    return False
        except Exception:
            return False

        # 无效域名黑名单
        invalid_domains = [
            'docs.djangoproject.com',
            'docs.python.org',
            'developer.mozilla.org',
            'stackoverflow.com',
            'themoviedb.org',
            'prisma.io',
            'pris.ly',
            'every.to',
            'makersuite.google.com',
            '/settings',
            '/ref/',
            '/docs/',
            '/guide',
        ]

        for invalid in invalid_domains:
            if invalid in url_lower:
                return False

        return True

    # ========================================================================
    #                           优化的验证方法
    # ========================================================================

    async def _make_request_with_retry(
        self,
        method: str,
        url: str,
        headers: dict,
        proxy: Optional[str] = None,
        json_data: Optional[dict] = None
    ) -> aiohttp.ClientResponse:
        """
        发送 HTTP 请求（带重试）

        新增：使用重试处理器自动重试临时错误
        """
        session = await self._get_session(url)

        async def _do_request():
            if method.upper() == 'GET':
                return await session.get(url, headers=headers, proxy=proxy)
            elif method.upper() == 'POST':
                return await session.post(url, headers=headers, json=json_data, proxy=proxy)
            else:
                raise ValueError(f"不支持的 HTTP 方法: {method}")

        # 使用重试处理器
        try:
            response = await self._retry_handler.execute_with_retry(_do_request)
            return response
        except Exception as e:
            # 记录重试统计
            error_type = self._retry_handler.classify_error(e)
            if error_type == ErrorType.RETRYABLE:
                self._stats['retried_validations'] += 1
            raise

    async def validate_openai(self, api_key: str, base_url: str) -> ValidationResult:
        """
        异步验证 OpenAI / 中转站

        优化：
        1. 使用连接池复用连接
        2. 智能重试临时错误
        3. 改进的错误处理
        """
        self._stats['total_validations'] += 1

        # 预检查 base_url 有效性
        if not self._is_likely_valid_relay(base_url):
            self._stats['failed_validations'] += 1
            return ValidationResult(KeyStatus.INVALID, "base_url 无效")

        if not base_url:
            base_url = config.default_base_urls["openai"]

        # 熔断器检查
        circuit_result = await self._check_circuit_breaker(base_url)
        if circuit_result:
            self._stats['failed_validations'] += 1
            return circuit_result

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        proxy = self._get_proxy()

        model_tier = "GPT-3.5"
        rpm = 0
        models_list = []

        # Step 1: GET /models（带重试）
        for url in self._try_url_variants(base_url, "models"):
            try:
                async with await self._make_request_with_retry('GET', url, headers, proxy) as resp:
                    # 提取 RPM
                    rpm = int(resp.headers.get('x-ratelimit-limit-requests', 0))

                    if resp.status == 200:
                        # 记录成功
                        await self._record_circuit_result(url, success=True)
                        self._stats['successful_validations'] += 1

                        data = await resp.json()
                        models_list = [m.get("id", "") for m in data.get("data", [])]

                        # 检测高价值模型
                        for m in models_list:
                            if any(hv in m.lower() for hv in ['gpt-4', 'gpt-4o']):
                                model_tier = "GPT-4"
                                break

                        model_names = [m[:15] for m in models_list[:3]]
                        info = f"{len(models_list)}模型: {', '.join(model_names)}"

                        # RPM 透视标记
                        rpm_tier = ""
                        if rpm >= RPM_ENTERPRISE_THRESHOLD:
                            rpm_tier = "Enterprise"
                        elif rpm > 0 and rpm <= RPM_FREE_TRIAL_THRESHOLD:
                            rpm_tier = "Free Trial"

                        if rpm_tier:
                            info = f"{info} [{rpm_tier}]"

                        is_high = model_tier == "GPT-4" or rpm >= RPM_ENTERPRISE_THRESHOLD

                        return ValidationResult(KeyStatus.VALID, info, model_tier, rpm, 0.0, is_high)

                    elif resp.status == 429:
                        await self._record_circuit_result(url, http_status=429)
                        self._stats['failed_validations'] += 1
                        return ValidationResult(KeyStatus.QUOTA_EXCEEDED, "配额耗尽")

                    elif resp.status in CIRCUIT_BREAKER_HTTP_CODES:
                        await self._record_circuit_result(url, http_status=resp.status)
                        self._stats['failed_validations'] += 1
                        return ValidationResult(KeyStatus.CONNECTION_ERROR, f"网关错误 {resp.status}")

                    elif resp.status == 401:
                        self._stats['failed_validations'] += 1
                        return ValidationResult(KeyStatus.INVALID, "认证失败")

                    else:
                        continue

            except asyncio.TimeoutError:
                await self._record_circuit_result(url, error=asyncio.TimeoutError())
                continue

            except aiohttp.ClientError as e:
                await self._record_circuit_result(url, error=e)
                continue

            except Exception as e:
                logger.debug(f"验证异常: {e}")
                continue

        # 所有 URL 变体都失败
        self._stats['failed_validations'] += 1
        return ValidationResult(KeyStatus.CONNECTION_ERROR, "连接失败")

    def get_stats(self) -> dict:
        """获取性能统计"""
        stats = self._stats.copy()

        # 添加重试处理器统计
        retry_stats = self._retry_handler.get_stats()
        stats.update({
            'retry_success_rate': retry_stats.get('success_rate', 0),
            'retry_attempts': retry_stats.get('total_attempts', 0),
        })

        # 添加连接池统计
        if self._connection_pool:
            pool_stats = self._connection_pool.get_stats()
            stats.update({
                'active_sessions': pool_stats.get('active_sessions', 0),
                'domains': pool_stats.get('domains', []),
            })

        return stats
