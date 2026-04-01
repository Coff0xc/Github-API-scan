#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
性能监控模块 - 实时性能指标收集

特性：
1. 请求延迟统计（P50/P95/P99）
2. 成功率和错误率追踪
3. 吞吐量监控
4. 资源使用监控
5. 实时性能报告
"""

import time
import asyncio
import psutil
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime
import statistics

from loguru import logger


@dataclass
class LatencyStats:
    """延迟统计"""
    count: int = 0
    total: float = 0.0
    min: float = float('inf')
    max: float = 0.0
    p50: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    samples: deque = field(default_factory=lambda: deque(maxlen=1000))

    def add_sample(self, latency: float):
        """添加延迟样本"""
        self.count += 1
        self.total += latency
        self.min = min(self.min, latency)
        self.max = max(self.max, latency)
        self.samples.append(latency)

        # 计算百分位数
        if len(self.samples) > 0:
            sorted_samples = sorted(self.samples)
            self.p50 = statistics.median(sorted_samples)
            self.p95 = sorted_samples[int(len(sorted_samples) * 0.95)]
            self.p99 = sorted_samples[int(len(sorted_samples) * 0.99)]

    @property
    def avg(self) -> float:
        """平均延迟"""
        return self.total / self.count if self.count > 0 else 0.0


@dataclass
class ThroughputStats:
    """吞吐量统计"""
    total_operations: int = 0
    start_time: float = field(default_factory=time.time)
    window_operations: deque = field(default_factory=lambda: deque(maxlen=60))  # 60秒窗口

    def record_operation(self):
        """记录一次操作"""
        self.total_operations += 1
        self.window_operations.append(time.time())

    @property
    def ops_per_second(self) -> float:
        """每秒操作数（基于窗口）"""
        if len(self.window_operations) < 2:
            return 0.0

        window_duration = self.window_operations[-1] - self.window_operations[0]
        if window_duration > 0:
            return len(self.window_operations) / window_duration
        return 0.0

    @property
    def total_ops_per_second(self) -> float:
        """总体每秒操作数"""
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            return self.total_operations / elapsed
        return 0.0


@dataclass
class ErrorStats:
    """错误统计"""
    total_errors: int = 0
    error_by_type: Dict[str, int] = field(default_factory=dict)
    recent_errors: deque = field(default_factory=lambda: deque(maxlen=100))

    def record_error(self, error_type: str, error_msg: str = ""):
        """记录错误"""
        self.total_errors += 1
        self.error_by_type[error_type] = self.error_by_type.get(error_type, 0) + 1
        self.recent_errors.append({
            'type': error_type,
            'message': error_msg,
            'timestamp': time.time()
        })


class PerformanceMonitor:
    """
    性能监控器

    收集和分析各种性能指标
    """

    def __init__(self):
        # 延迟统计
        self.validation_latency = LatencyStats()
        self.db_write_latency = LatencyStats()
        self.http_request_latency = LatencyStats()

        # 吞吐量统计
        self.validation_throughput = ThroughputStats()
        self.scan_throughput = ThroughputStats()

        # 错误统计
        self.validation_errors = ErrorStats()
        self.connection_errors = ErrorStats()

        # 成功率统计
        self.total_validations = 0
        self.successful_validations = 0
        self.failed_validations = 0

        # 资源使用
        self.peak_memory_mb = 0.0
        self.peak_cpu_percent = 0.0

        # 监控任务
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """启动监控"""
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_resources())
        logger.info("性能监控已启动")

    async def stop(self):
        """停止监控"""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

    async def _monitor_resources(self):
        """监控系统资源"""
        while self._running:
            try:
                await asyncio.sleep(1)

                # 内存使用
                memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
                self.peak_memory_mb = max(self.peak_memory_mb, memory_mb)

                # CPU 使用
                cpu_percent = psutil.Process().cpu_percent()
                self.peak_cpu_percent = max(self.peak_cpu_percent, cpu_percent)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"资源监控异常: {e}")

    # ========================================================================
    #                           记录方法
    # ========================================================================

    def record_validation(self, latency: float, success: bool, error_type: str = ""):
        """记录验证操作"""
        self.validation_latency.add_sample(latency)
        self.validation_throughput.record_operation()
        self.total_validations += 1

        if success:
            self.successful_validations += 1
        else:
            self.failed_validations += 1
            if error_type:
                self.validation_errors.record_error(error_type)

    def record_db_write(self, latency: float):
        """记录数据库写入"""
        self.db_write_latency.add_sample(latency)

    def record_http_request(self, latency: float, success: bool = True):
        """记录 HTTP 请求"""
        self.http_request_latency.add_sample(latency)
        if not success:
            self.connection_errors.record_error("http_error")

    def record_scan(self):
        """记录扫描操作"""
        self.scan_throughput.record_operation()

    def record_error(self, error_type: str, error_msg: str = ""):
        """记录通用错误"""
        self.validation_errors.record_error(error_type, error_msg)

    # ========================================================================
    #                           统计方法
    # ========================================================================

    def get_success_rate(self) -> float:
        """获取成功率（百分比）"""
        if self.total_validations == 0:
            return 0.0
        return (self.successful_validations / self.total_validations) * 100

    def get_error_rate(self) -> float:
        """获取错误率（百分比）"""
        return 100.0 - self.get_success_rate()

    def get_validation_stats(self) -> dict:
        """获取验证统计"""
        return {
            'total': self.total_validations,
            'successful': self.successful_validations,
            'failed': self.failed_validations,
            'success_rate': self.get_success_rate(),
            'error_rate': self.get_error_rate(),
            'latency': {
                'avg_ms': self.validation_latency.avg * 1000,
                'min_ms': self.validation_latency.min * 1000,
                'max_ms': self.validation_latency.max * 1000,
                'p50_ms': self.validation_latency.p50 * 1000,
                'p95_ms': self.validation_latency.p95 * 1000,
                'p99_ms': self.validation_latency.p99 * 1000,
            },
            'throughput': {
                'current_ops': self.validation_throughput.ops_per_second,
                'total_ops': self.validation_throughput.total_ops_per_second,
            }
        }

    def get_resource_stats(self) -> dict:
        """获取资源统计"""
        try:
            process = psutil.Process()
            return {
                'memory_mb': process.memory_info().rss / 1024 / 1024,
                'peak_memory_mb': self.peak_memory_mb,
                'cpu_percent': process.cpu_percent(),
                'peak_cpu_percent': self.peak_cpu_percent,
                'threads': process.num_threads(),
            }
        except Exception:
            return {}

    def get_error_stats(self) -> dict:
        """获取错误统计"""
        return {
            'total_errors': self.validation_errors.total_errors,
            'by_type': dict(self.validation_errors.error_by_type),
            'connection_errors': self.connection_errors.total_errors,
        }

    def get_full_stats(self) -> dict:
        """获取完整统计"""
        return {
            'validation': self.get_validation_stats(),
            'resources': self.get_resource_stats(),
            'errors': self.get_error_stats(),
            'database': {
                'write_latency_ms': self.db_write_latency.avg * 1000,
                'write_p95_ms': self.db_write_latency.p95 * 1000,
            },
            'http': {
                'request_latency_ms': self.http_request_latency.avg * 1000,
                'request_p95_ms': self.http_request_latency.p95 * 1000,
            },
            'scan': {
                'throughput_ops': self.scan_throughput.ops_per_second,
            }
        }

    def print_report(self):
        """打印性能报告"""
        stats = self.get_full_stats()

        print("\n" + "=" * 60)
        print("性能监控报告")
        print("=" * 60)

        # 验证统计
        val_stats = stats['validation']
        print(f"\n验证统计:")
        print(f"  总数: {val_stats['total']}")
        print(f"  成功: {val_stats['successful']} ({val_stats['success_rate']:.1f}%)")
        print(f"  失败: {val_stats['failed']} ({val_stats['error_rate']:.1f}%)")
        print(f"  吞吐量: {val_stats['throughput']['current_ops']:.2f} ops/s")

        # 延迟统计
        latency = val_stats['latency']
        print(f"\n延迟统计:")
        print(f"  平均: {latency['avg_ms']:.2f} ms")
        print(f"  P50: {latency['p50_ms']:.2f} ms")
        print(f"  P95: {latency['p95_ms']:.2f} ms")
        print(f"  P99: {latency['p99_ms']:.2f} ms")

        # 资源使用
        resources = stats['resources']
        if resources:
            print(f"\n资源使用:")
            print(f"  内存: {resources['memory_mb']:.1f} MB (峰值: {resources['peak_memory_mb']:.1f} MB)")
            print(f"  CPU: {resources['cpu_percent']:.1f}% (峰值: {resources['peak_cpu_percent']:.1f}%)")

        # 错误统计
        errors = stats['errors']
        if errors['total_errors'] > 0:
            print(f"\n错误统计:")
            print(f"  总错误: {errors['total_errors']}")
            for error_type, count in errors['by_type'].items():
                print(f"  {error_type}: {count}")

        print("=" * 60 + "\n")


# 全局监控器实例
_global_monitor: Optional[PerformanceMonitor] = None


def get_monitor() -> PerformanceMonitor:
    """获取全局监控器"""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = PerformanceMonitor()
    return _global_monitor


# 装饰器：自动记录函数执行时间
def monitor_latency(operation_type: str = "validation"):
    """
    延迟监控装饰器

    用法:
        @monitor_latency("validation")
        async def validate_key(...):
            ...
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            monitor = get_monitor()
            start_time = time.time()
            success = True
            error_type = ""

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                error_type = type(e).__name__
                raise
            finally:
                latency = time.time() - start_time

                if operation_type == "validation":
                    monitor.record_validation(latency, success, error_type)
                elif operation_type == "db_write":
                    monitor.record_db_write(latency)
                elif operation_type == "http":
                    monitor.record_http_request(latency, success)

        return wrapper
    return decorator
