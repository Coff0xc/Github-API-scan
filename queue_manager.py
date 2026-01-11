#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
动态队列管理器 - 智能内存管理

特性：
1. 动态调整队列大小
2. 内存压力监控
3. 背压控制（Backpressure）
4. 队列统计和监控
"""

import asyncio
import psutil
from typing import TypeVar, Generic, Optional
from dataclasses import dataclass
from loguru import logger

T = TypeVar('T')


@dataclass
class QueueConfig:
    """队列配置"""
    initial_size: int = 1000
    min_size: int = 100
    max_size: int = 10000
    memory_threshold_percent: float = 80.0  # 内存使用阈值
    auto_adjust: bool = True  # 是否自动调整大小


@dataclass
class QueueStats:
    """队列统计"""
    current_size: int = 0
    max_size: int = 0
    total_put: int = 0
    total_get: int = 0
    total_dropped: int = 0
    backpressure_events: int = 0


class DynamicQueue(Generic[T]):
    """
    动态队列 - 根据内存压力自动调整大小

    特性：
    - 内存压力大时缩小队列
    - 内存充足时扩大队列
    - 背压控制防止内存溢出
    """

    def __init__(self, config: Optional[QueueConfig] = None):
        self.config = config or QueueConfig()
        self._queue: asyncio.Queue[T] = asyncio.Queue(maxsize=self.config.initial_size)
        self._stats = QueueStats(max_size=self.config.initial_size)

        # 监控任务
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """启动队列监控"""
        self._running = True
        if self.config.auto_adjust:
            self._monitor_task = asyncio.create_task(self._monitor_memory())
            logger.info(f"动态队列已启动 (初始大小: {self.config.initial_size})")

    async def stop(self):
        """停止队列监控"""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

    def _get_memory_usage(self) -> float:
        """获取当前内存使用率（百分比）"""
        try:
            return psutil.virtual_memory().percent
        except Exception:
            return 0.0

    async def _monitor_memory(self):
        """监控内存使用并动态调整队列大小"""
        while self._running:
            try:
                await asyncio.sleep(5)  # 每 5 秒检查一次

                memory_percent = self._get_memory_usage()
                current_max = self._queue.maxsize

                # 内存压力大，缩小队列
                if memory_percent > self.config.memory_threshold_percent:
                    new_size = max(
                        self.config.min_size,
                        int(current_max * 0.7)  # 缩小 30%
                    )
                    if new_size < current_max:
                        await self._resize_queue(new_size)
                        logger.warning(
                            f"内存压力大 ({memory_percent:.1f}%), "
                            f"队列缩小: {current_max} -> {new_size}"
                        )

                # 内存充足，扩大队列
                elif memory_percent < self.config.memory_threshold_percent - 20:
                    new_size = min(
                        self.config.max_size,
                        int(current_max * 1.3)  # 扩大 30%
                    )
                    if new_size > current_max:
                        await self._resize_queue(new_size)
                        logger.info(
                            f"内存充足 ({memory_percent:.1f}%), "
                            f"队列扩大: {current_max} -> {new_size}"
                        )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"内存监控异常: {e}")

    async def _resize_queue(self, new_size: int):
        """
        调整队列大小

        注意：asyncio.Queue 不支持动态调整大小，
        这里通过创建新队列并迁移数据实现
        """
        old_queue = self._queue
        new_queue = asyncio.Queue(maxsize=new_size)

        # 迁移现有数据
        migrated = 0
        while not old_queue.empty():
            try:
                item = old_queue.get_nowait()
                try:
                    new_queue.put_nowait(item)
                    migrated += 1
                except asyncio.QueueFull:
                    # 新队列已满，丢弃剩余数据
                    self._stats.total_dropped += 1
                    logger.warning("队列缩小时丢弃数据")
                    break
            except asyncio.QueueEmpty:
                break

        self._queue = new_queue
        self._stats.max_size = new_size
        logger.debug(f"队列调整完成，迁移 {migrated} 条数据")

    async def put(self, item: T, timeout: Optional[float] = None) -> bool:
        """
        放入数据（带超时）

        Returns:
            bool: 是否成功放入
        """
        self._stats.total_put += 1

        try:
            if timeout:
                await asyncio.wait_for(
                    self._queue.put(item),
                    timeout=timeout
                )
            else:
                await self._queue.put(item)
            return True

        except asyncio.TimeoutError:
            # 背压：队列满且超时
            self._stats.backpressure_events += 1
            logger.warning("队列背压：放入超时")
            return False

        except Exception as e:
            logger.error(f"放入队列失败: {e}")
            return False

    def put_nowait(self, item: T) -> bool:
        """
        非阻塞放入

        Returns:
            bool: 是否成功放入
        """
        self._stats.total_put += 1

        try:
            self._queue.put_nowait(item)
            return True
        except asyncio.QueueFull:
            self._stats.backpressure_events += 1
            return False

    async def get(self, timeout: Optional[float] = None) -> Optional[T]:
        """
        获取数据（带超时）

        Returns:
            Optional[T]: 数据项，超时返回 None
        """
        try:
            if timeout:
                item = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=timeout
                )
            else:
                item = await self._queue.get()

            self._stats.total_get += 1
            return item

        except asyncio.TimeoutError:
            return None

        except Exception as e:
            logger.error(f"从队列获取失败: {e}")
            return None

    def get_nowait(self) -> Optional[T]:
        """非阻塞获取"""
        try:
            item = self._queue.get_nowait()
            self._stats.total_get += 1
            return item
        except asyncio.QueueEmpty:
            return None

    def qsize(self) -> int:
        """当前队列大小"""
        return self._queue.qsize()

    def empty(self) -> bool:
        """队列是否为空"""
        return self._queue.empty()

    def full(self) -> bool:
        """队列是否已满"""
        return self._queue.full()

    def maxsize(self) -> int:
        """队列最大容量"""
        return self._queue.maxsize

    def get_stats(self) -> dict:
        """获取队列统计"""
        return {
            "current_size": self.qsize(),
            "max_size": self._stats.max_size,
            "total_put": self._stats.total_put,
            "total_get": self._stats.total_get,
            "total_dropped": self._stats.total_dropped,
            "backpressure_events": self._stats.backpressure_events,
            "memory_usage_percent": self._get_memory_usage(),
            "utilization_percent": (self.qsize() / self._stats.max_size * 100) if self._stats.max_size > 0 else 0,
        }

    def reset_stats(self):
        """重置统计"""
        self._stats = QueueStats(max_size=self._stats.max_size)


class PriorityDynamicQueue(DynamicQueue[T]):
    """
    优先级动态队列

    支持按优先级排序的动态队列
    """

    def __init__(self, config: Optional[QueueConfig] = None):
        super().__init__(config)
        # 使用 PriorityQueue 替代普通 Queue
        self._queue = asyncio.PriorityQueue(maxsize=self.config.initial_size)

    async def put_with_priority(
        self,
        priority: int,
        item: T,
        timeout: Optional[float] = None
    ) -> bool:
        """
        按优先级放入数据

        Args:
            priority: 优先级（数字越小优先级越高）
            item: 数据项
            timeout: 超时时间

        Returns:
            bool: 是否成功放入
        """
        return await self.put((priority, item), timeout)


# 便捷函数
def create_queue(
    initial_size: int = 1000,
    auto_adjust: bool = True,
    memory_threshold: float = 80.0
) -> DynamicQueue:
    """
    创建动态队列

    Args:
        initial_size: 初始大小
        auto_adjust: 是否自动调整
        memory_threshold: 内存阈值（百分比）

    Returns:
        DynamicQueue: 队列实例
    """
    config = QueueConfig(
        initial_size=initial_size,
        auto_adjust=auto_adjust,
        memory_threshold_percent=memory_threshold
    )
    return DynamicQueue(config)
