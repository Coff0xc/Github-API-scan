"""AsyncValidator session, dispatch, legacy thread loop."""

import asyncio
import queue as sync_queue
import ssl
import threading
from datetime import datetime
from typing import Optional, Tuple

import aiohttp
from aiohttp import TCPConnector
from loguru import logger

from config import config
from database import Database, KeyStatus, LeakedKey
from utils import mask_key, relay_url_is_allowed
from validator.circuit import CircuitBreaker, circuit_breaker
from validator.platforms import PLATFORM_METHODS, bind_platform_methods
from validator.types import MAX_CONCURRENCY, REQUEST_TIMEOUT, ValidationResult


class AsyncValidator:
    """异步 API Key 验证器 - 集成熍断器保护"""

    def __init__(self, db: Database, dashboard=None):
        self.db = db
        self.dashboard = dashboard
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
        self._session: Optional[aiohttp.ClientSession] = None
        self._circuit_breaker = circuit_breaker

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = TCPConnector(
                limit=MAX_CONCURRENCY,
                ssl=ssl.create_default_context(),
                force_close=True
            )
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=REQUEST_TIMEOUT,
                trust_env=True
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _get_proxy(self) -> Optional[str]:
        return config.proxy_url if config.proxy_url else None

    def _log(self, message: str, level: str = "INFO"):
        if self.dashboard:
            self.dashboard.add_log(message, level)

    def _try_url_variants(self, base_url: str, path: str) -> list:
        base_url = base_url.rstrip('/')
        path = path.lstrip('/')

        variants = [f"{base_url}/{path}"]

        if '/v1' not in base_url:
            variants.append(f"{base_url}/v1/{path}")

        if '/v1' in base_url:
            base_without_v1 = base_url.replace('/v1', '')
            variants.append(f"{base_without_v1}/v1/{path}")

        return variants

    async def _check_circuit_breaker(self, base_url: str) -> Optional[ValidationResult]:
        if not config.circuit_breaker_enabled:
            return None

        if not await self._circuit_breaker.is_allowed(base_url):
            self._log(f"熍断中: {base_url[:30]}...", "WARN")
            return ValidationResult(KeyStatus.CONNECTION_ERROR, "域名熍断中")

        return None

    async def _record_circuit_result(
        self,
        url: str,
        success: bool = False,
        error: Exception = None,
        http_status: int = None
    ):
        if not config.circuit_breaker_enabled:
            return

        if success:
            await self._circuit_breaker.record_success(url)
        else:
            await self._circuit_breaker.record_failure(url, error, http_status)

    def _is_likely_valid_relay(self, base_url: str) -> bool:
        return relay_url_is_allowed(base_url)

    async def validate_single(self, result: 'ScanResult') -> ValidationResult:
        """验证单个结果（统一入口）"""
        platform = result.platform.lower()

        if result.base_url and not self._is_likely_valid_relay(result.base_url):
            return ValidationResult(KeyStatus.INVALID, "base_url 无效")

        if platform == "azure" or result.is_azure:
            return await self.validate_azure(result.api_key, result.base_url)

        method_name = f"validate_{platform}"
        if method_name not in PLATFORM_METHODS:
            return await self.validate_openai(result.api_key, result.base_url)
        return await getattr(self, method_name)(result.api_key, result.base_url)

    async def process_result(self, result: 'ScanResult'):
        """
        异步处理单个结果。

        入库前按密钥去重。验证结果只回写状态、模型档位和 RPM。
        """
        async with self.semaphore:
            masked = mask_key(result.api_key)

            if self.db.key_exists(result.api_key):
                self._log(f"[SKIP] Key 已在数据库中: {masked}", "SKIP")
                if self.dashboard:
                    self.dashboard.increment_stat("skipped_duplicate")
                return

            leaked_key = LeakedKey(
                platform=result.platform,
                api_key=result.api_key,
                base_url=result.base_url,
                status=KeyStatus.PENDING.value,
                source_url=result.source_url,
                found_time=datetime.now()
            )

            if not self.db.insert_key(leaked_key):
                self._log(f"[SKIP] Key 插入冲突: {masked}", "SKIP")
                return

            self._log(f"验证 {masked}...", "INFO")
            vr = await self.validate_single(result)

            self.db.update_key_status(
                result.api_key,
                vr.status,
                model_tier=vr.model_tier,
                rpm=vr.rpm,
            )

            if self.dashboard:
                source_short = result.source_url.split('/')[-1] if '/' in result.source_url else result.source_url

                if vr.status == KeyStatus.VALID:
                    self.dashboard.add_valid_key(
                        platform=result.platform,
                        masked_key=masked,
                        source=source_short,
                        status="valid",
                    )
                    self._log(f"✓ 有效! {vr.model_tier or result.platform.upper()} {masked}", "VALID")

                elif vr.status == KeyStatus.QUOTA_EXCEEDED:
                    self.dashboard.add_valid_key(
                        platform=result.platform,
                        masked_key=masked,
                        source=source_short,
                        status="quota_exceeded",
                    )
                    self.dashboard.increment_stat("quota_exceeded")
                    self._log(f"⚠ 配额耗尽 {masked}", "WARN")

                elif vr.status == KeyStatus.CONNECTION_ERROR:
                    self.dashboard.increment_stat("connection_errors")
                    self._log(f"✗ 连接失败 {masked}", "ERROR")

                else:
                    self.dashboard.increment_stat("invalid_keys")

    async def run_batch(self, results: list):
        tasks = [self.process_result(r) for r in results]
        await asyncio.gather(*tasks, return_exceptions=True)


bind_platform_methods(AsyncValidator)


async def validate_key_async(
    platform: str,
    api_key: str,
    base_url: str = "",
    circuit_breaker: Optional[CircuitBreaker] = None,
) -> Tuple[KeyStatus, str, str, int, bool]:
    """
    按平台分发验证，返回 (status, balance, model_tier, rpm, is_high_value)。

    validator_optimized 的验证 worker 对非 openai/relay 平台调用本函数；
    openai/relay 走 OptimizedAsyncValidator 的缓存路径，不经这里。
    每次调用使用独立的临时验证器，session 用毕即关，不做跨调用缓存。
    """
    from scanner import ScanResult

    platform = (platform or "openai").lower()
    validator = AsyncValidator(Database(":memory:"))
    if circuit_breaker is not None:
        validator._circuit_breaker = circuit_breaker
    try:
        result = await validator.validate_single(ScanResult(
            platform=platform,
            api_key=api_key,
            base_url=base_url or "",
            source_url="",
            is_azure=(platform == "azure"),
            is_relay=bool(base_url),
        ))
        return result.status, "", result.model_tier or "", result.rpm or 0, False
    finally:
        await validator.close()


def get_scan_result_class():
    from scanner import ScanResult
    return ScanResult


async def run_validator_loop(
    result_queue: 'asyncio.Queue',
    db: Database,
    stop_event: 'asyncio.Event',
    dashboard=None
):
    """运行异步验证循环"""
    validator = AsyncValidator(db, dashboard)

    try:
        while not stop_event.is_set():
            try:
                batch = []
                try:
                    while len(batch) < 50:
                        result = result_queue.get_nowait()
                        batch.append(result)
                except asyncio.QueueEmpty:
                    pass

                if batch:
                    if dashboard:
                        dashboard.update_stats(queue_size=result_queue.qsize())
                    await validator.run_batch(batch)
                else:
                    await asyncio.sleep(0.5)

            except Exception as e:
                if dashboard:
                    dashboard.add_log(f"验证错误: {str(e)[:30]}", "ERROR")
                await asyncio.sleep(1)
    finally:
        await validator.close()


def _validator_thread_worker(
    result_queue: sync_queue.Queue,
    db: Database,
    stop_event: threading.Event,
    dashboard=None
):
    """在线程中运行 asyncio 事件循环。"""

    async def async_worker():
        validator = AsyncValidator(db, dashboard)
        try:
            while not stop_event.is_set():
                try:
                    batch = []
                    try:
                        while len(batch) < 50:
                            result = result_queue.get_nowait()
                            batch.append(result)
                    except sync_queue.Empty:
                        pass

                    if batch:
                        if dashboard:
                            dashboard.update_stats(queue_size=result_queue.qsize())
                        await validator.run_batch(batch)
                    else:
                        await asyncio.sleep(0.3)

                except Exception as e:
                    if dashboard:
                        dashboard.add_log(f"验证错误: {str(e)[:30]}", "ERROR")
                    await asyncio.sleep(1)
        finally:
            await validator.close()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(async_worker())
    finally:
        loop.close()


def start_validators(
    result_queue: sync_queue.Queue,
    db: Database,
    stop_event: threading.Event,
    dashboard=None,
    num_workers: int = 1
) -> list:
    """
    启动验证器线程。遗留入口；新进程用 validator_optimized.start_validators。
    """
    logger.warning(
        "validator.start_validators 是遗留入口。新的扫描进程应使用 "
        "validator_optimized.start_validators（main_v2.2）。"
    )
    threads = []
    actual_workers = min(num_workers, 2)

    for i in range(actual_workers):
        thread = threading.Thread(
            target=_validator_thread_worker,
            args=(result_queue, db, stop_event, dashboard),
            name=f"AsyncValidator-{i}",
            daemon=True
        )
        thread.start()
        threads.append(thread)

    if dashboard:
        dashboard.add_log(f"启动 {actual_workers} 个异步验证器 (100 并发/个)", "INFO")

    return threads
