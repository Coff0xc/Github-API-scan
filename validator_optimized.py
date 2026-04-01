"""
验证器模块 - 优化版 v2.2

v2.2 新增优化：
1. 智能缓存系统 - 3层缓存架构，减少重复验证
2. 批量验证支持 - 按域名分组，降低网络开销
3. 域名健康度追踪 - 避免验证死域名

v2.1 优化（保留）：
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

# v2.2: 缓存和批量验证
from cache_manager import CacheManager, CacheConfig, get_cache_manager
from batch_validator import BatchValidator, BatchConfig

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

    v2.2 新特性：
    - 智能缓存系统（3层缓存架构）
    - 批量验证支持（按域名分组）
    - 域名健康度追踪

    v2.1 特性（保留）：
    - 使用连接池复用 HTTP 连接
    - 智能重试机制（指数退避）
    - 改进的性能监控
    """

    def __init__(self, db: Database, dashboard=None,
                 cache_config: Optional[CacheConfig] = None,
                 batch_config: Optional[BatchConfig] = None):
        self.db = db
        self.dashboard = dashboard
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
        self._circuit_breaker = circuit_breaker

        # v2.1: 连接池和重试处理器
        self._connection_pool = None
        self._retry_handler = RetryHandler(RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            max_delay=10.0,
            exponential_base=2.0,
            jitter=True
        ))

        # v2.2: 缓存管理器和批量验证器
        self._cache_manager: Optional[CacheManager] = None
        self._cache_config = cache_config
        self._batch_validator = BatchValidator(batch_config)

        # 性能统计
        self._stats = {
            'total_validations': 0,
            'successful_validations': 0,
            'failed_validations': 0,
            'retried_validations': 0,
            'connection_reused': 0,
            # v2.2 新增统计
            'cache_hits': 0,
            'cache_misses': 0,
            'dead_domain_skipped': 0,
            'batch_validations': 0,
        }

    async def init_cache(self):
        """
        初始化缓存管理器（v2.2 新增）

        必须在使用验证器前调用
        """
        if self._cache_manager is None:
            self._cache_manager = await get_cache_manager(self._cache_config)
            logger.info("缓存管理器已初始化")

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
        # 缓存管理器也由全局管理
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

        v2.2 优化：
        1. 智能缓存 - 检查缓存避免重复验证
        2. 域名健康度 - 跳过死域名
        3. 批量验证支持

        v2.1 优化（保留）：
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

        # v2.2: 检查缓存
        if self._cache_manager:
            cached_result = await self._cache_manager.get_validation_result(api_key, base_url)
            if cached_result:
                self._stats['cache_hits'] += 1
                self._log(f"缓存命中: {mask_key(api_key)}", "DEBUG")
                return ValidationResult(
                    KeyStatus(cached_result['status']),
                    cached_result.get('balance', ''),
                    cached_result.get('model_tier', 'GPT-3.5'),
                    cached_result.get('rpm', 0),
                    cached_result.get('latency', 0.0),
                    cached_result.get('is_high_value', False)
                )
            self._stats['cache_misses'] += 1

        # v2.2: 检查域名健康度
        if self._cache_manager:
            is_dead = await self._cache_manager.is_domain_dead(base_url)
            if is_dead:
                self._stats['dead_domain_skipped'] += 1
                self._log(f"跳过死域名: {base_url[:30]}...", "WARN")
                return ValidationResult(KeyStatus.CONNECTION_ERROR, "域名已死")

        # 熔断器检查
        circuit_result = await self._check_circuit_breaker(base_url)
        if circuit_result:
            self._stats['failed_validations'] += 1
            # 记录域名失败
            if self._cache_manager:
                await self._cache_manager.record_domain_failure(base_url)
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

                        # v2.2: 记录域名成功
                        if self._cache_manager:
                            await self._cache_manager.record_domain_success(base_url)

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

                        result = ValidationResult(KeyStatus.VALID, info, model_tier, rpm, 0.0, is_high)

                        # v2.2: 存储到缓存
                        if self._cache_manager:
                            await self._cache_manager.set_validation_result(
                                api_key, base_url,
                                {
                                    'status': result.status.value,
                                    'balance': result.balance,
                                    'model_tier': result.model_tier,
                                    'rpm': result.rpm,
                                    'latency': result.latency,
                                    'is_high_value': result.is_high_value
                                }
                            )

                        return result

                    elif resp.status == 429:
                        await self._record_circuit_result(url, http_status=429)
                        self._stats['failed_validations'] += 1
                        # v2.2: 记录域名失败
                        if self._cache_manager:
                            await self._cache_manager.record_domain_failure(base_url)
                        return ValidationResult(KeyStatus.QUOTA_EXCEEDED, "配额耗尽")

                    elif resp.status in CIRCUIT_BREAKER_HTTP_CODES:
                        await self._record_circuit_result(url, http_status=resp.status)
                        self._stats['failed_validations'] += 1
                        # v2.2: 记录域名失败
                        if self._cache_manager:
                            await self._cache_manager.record_domain_failure(base_url)
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
        # v2.2: 记录域名失败
        if self._cache_manager:
            await self._cache_manager.record_domain_failure(base_url)
        return ValidationResult(KeyStatus.CONNECTION_ERROR, "连接失败")

    # ========================================================================
    #                           v2.2: 批量验证方法
    # ========================================================================

    async def validate_batch(
        self,
        keys: list[tuple[str, str]],
        progress_callback=None
    ) -> list[ValidationResult]:
        """
        批量验证 Key（v2.2 新增）

        按域名分组验证，减少网络开销

        Args:
            keys: [(api_key, base_url), ...]
            progress_callback: 进度回调 def(completed, total)

        Returns:
            [ValidationResult, ...]
        """
        self._stats['batch_validations'] += 1

        async def _validate_single(api_key: str, base_url: str):
            """单个验证的包装函数"""
            return await self.validate_openai(api_key, base_url)

        # 使用批量验证器
        results = await self._batch_validator.validate_batch(
            keys,
            _validate_single,
            progress_callback
        )

        return results

    def get_stats(self) -> dict:
        """获取性能统计"""
        stats = self._stats.copy()

        # v2.1: 添加重试处理器统计
        retry_stats = self._retry_handler.get_stats()
        stats.update({
            'retry_success_rate': retry_stats.get('success_rate', 0),
            'retry_attempts': retry_stats.get('total_attempts', 0),
        })

        # v2.1: 添加连接池统计
        if self._connection_pool:
            pool_stats = self._connection_pool.get_stats()
            stats.update({
                'active_sessions': pool_stats.get('active_sessions', 0),
                'domains': pool_stats.get('domains', []),
            })

        # v2.2: 添加缓存统计
        if self._cache_manager:
            cache_stats = self._cache_manager.get_stats()
            stats['cache'] = cache_stats

            # 计算缓存命中率
            total_cache_requests = self._stats['cache_hits'] + self._stats['cache_misses']
            if total_cache_requests > 0:
                stats['cache_hit_rate'] = (
                    self._stats['cache_hits'] / total_cache_requests * 100
                )
            else:
                stats['cache_hit_rate'] = 0.0

        # v2.2: 添加批量验证统计
        batch_stats = self._batch_validator.get_stats()
        stats['batch'] = batch_stats

        return stats
