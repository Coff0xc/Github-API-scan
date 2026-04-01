#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
重试处理器 - 智能重试机制

特性：
1. 指数退避重试策略
2. 区分临时错误和永久错误
3. 与断路器集成
4. 重试统计和监控
"""

import asyncio
import time
from typing import Callable, Optional, Any, TypeVar, Awaitable
from dataclasses import dataclass
from enum import Enum

from loguru import logger
import aiohttp


class ErrorType(Enum):
    """错误类型分类"""
    RETRYABLE = "retryable"  # 可重试错误（临时性）
    PERMANENT = "permanent"  # 永久错误（不可重试）
    RATE_LIMIT = "rate_limit"  # 速率限制


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3
    initial_delay: float = 1.0  # 初始延迟（秒）
    max_delay: float = 30.0  # 最大延迟（秒）
    exponential_base: float = 2.0  # 指数基数
    jitter: bool = True  # 是否添加随机抖动


@dataclass
class RetryStats:
    """重试统计"""
    total_attempts: int = 0
    successful_retries: int = 0
    failed_retries: int = 0
    permanent_failures: int = 0
    rate_limit_hits: int = 0


T = TypeVar('T')


class RetryHandler:
    """重试处理器"""

    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()
        self.stats = RetryStats()

        # 可重试的 HTTP 状态码
        self.retryable_status_codes = {
            408,  # Request Timeout
            429,  # Too Many Requests
            500,  # Internal Server Error
            502,  # Bad Gateway
            503,  # Service Unavailable
            504,  # Gateway Timeout
        }

        # 永久失败的状态码
        self.permanent_status_codes = {
            400,  # Bad Request
            401,  # Unauthorized
            403,  # Forbidden
            404,  # Not Found
            405,  # Method Not Allowed
        }

    def classify_error(self, error: Exception) -> ErrorType:
        """
        分类错误类型

        Args:
            error: 异常对象

        Returns:
            ErrorType: 错误类型
        """
        # HTTP 响应错误
        if isinstance(error, aiohttp.ClientResponseError):
            if error.status == 429:
                return ErrorType.RATE_LIMIT
            elif error.status in self.retryable_status_codes:
                return ErrorType.RETRYABLE
            elif error.status in self.permanent_status_codes:
                return ErrorType.PERMANENT
            else:
                # 未知状态码，默认可重试
                return ErrorType.RETRYABLE

        # 连接错误（可重试）
        if isinstance(error, (
            aiohttp.ClientConnectionError,
            aiohttp.ServerTimeoutError,
            asyncio.TimeoutError,
            ConnectionError,
        )):
            return ErrorType.RETRYABLE

        # SSL 错误（永久）
        if isinstance(error, aiohttp.ClientSSLError):
            return ErrorType.PERMANENT

        # 其他错误默认为永久
        return ErrorType.PERMANENT

    def calculate_delay(self, attempt: int) -> float:
        """
        计算重试延迟（指数退避）

        Args:
            attempt: 当前重试次数（从 0 开始）

        Returns:
            float: 延迟秒数
        """
        delay = min(
            self.config.initial_delay * (self.config.exponential_base ** attempt),
            self.config.max_delay
        )

        # 添加随机抖动（避免雷鸣群效应）
        if self.config.jitter:
            import random
            delay = delay * (0.5 + random.random())

        return delay

    async def execute_with_retry(
        self,
        func: Callable[..., Awaitable[T]],
        *args,
        **kwargs
    ) -> T:
        """
        执行函数并在失败时重试

        Args:
            func: 异步函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            函数返回值

        Raises:
            最后一次尝试的异常
        """
        last_error: Optional[Exception] = None

        for attempt in range(self.config.max_retries + 1):
            self.stats.total_attempts += 1

            try:
                result = await func(*args, **kwargs)

                # 成功
                if attempt > 0:
                    self.stats.successful_retries += 1
                    logger.debug(f"重试成功 (尝试 {attempt + 1}/{self.config.max_retries + 1})")

                return result

            except Exception as e:
                last_error = e
                error_type = self.classify_error(e)

                # 永久错误，不重试
                if error_type == ErrorType.PERMANENT:
                    self.stats.permanent_failures += 1
                    logger.debug(f"永久错误，不重试: {e}")
                    raise

                # 速率限制
                if error_type == ErrorType.RATE_LIMIT:
                    self.stats.rate_limit_hits += 1
                    logger.warning(f"触发速率限制: {e}")

                # 最后一次尝试失败
                if attempt >= self.config.max_retries:
                    self.stats.failed_retries += 1
                    logger.warning(f"重试失败，已达最大次数 ({self.config.max_retries}): {e}")
                    raise

                # 计算延迟并重试
                delay = self.calculate_delay(attempt)
                logger.debug(
                    f"临时错误，{delay:.2f}秒后重试 "
                    f"(尝试 {attempt + 1}/{self.config.max_retries + 1}): {e}"
                )
                await asyncio.sleep(delay)

        # 理论上不会到达这里
        if last_error:
            raise last_error
        raise RuntimeError("重试逻辑异常")

    def get_stats(self) -> dict:
        """获取重试统计"""
        total = self.stats.total_attempts
        if total == 0:
            return {
                "total_attempts": 0,
                "success_rate": 0.0,
                "retry_rate": 0.0,
            }

        successful = total - self.stats.failed_retries - self.stats.permanent_failures
        return {
            "total_attempts": total,
            "successful_retries": self.stats.successful_retries,
            "failed_retries": self.stats.failed_retries,
            "permanent_failures": self.stats.permanent_failures,
            "rate_limit_hits": self.stats.rate_limit_hits,
            "success_rate": successful / total * 100,
            "retry_rate": self.stats.successful_retries / total * 100 if total > 0 else 0,
        }

    def reset_stats(self):
        """重置统计"""
        self.stats = RetryStats()


# 全局重试处理器实例
_global_retry_handler: Optional[RetryHandler] = None


def get_retry_handler(config: Optional[RetryConfig] = None) -> RetryHandler:
    """获取全局重试处理器"""
    global _global_retry_handler
    if _global_retry_handler is None:
        _global_retry_handler = RetryHandler(config)
    return _global_retry_handler


# 装饰器版本
def with_retry(config: Optional[RetryConfig] = None):
    """
    重试装饰器

    用法:
        @with_retry(RetryConfig(max_retries=5))
        async def my_function():
            ...
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        async def wrapper(*args, **kwargs) -> T:
            handler = get_retry_handler(config)
            return await handler.execute_with_retry(func, *args, **kwargs)
        return wrapper
    return decorator
