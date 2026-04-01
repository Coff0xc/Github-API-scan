#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v2.1 优化效果测试脚本

测试内容：
1. 连接池性能对比
2. 重试机制效果验证
3. 动态队列内存管理
4. 性能监控准确性
"""

import asyncio
import time
from datetime import datetime
from typing import List

from database import LeakedKey, KeyStatus
from async_database import AsyncDatabase
from connection_pool import get_connection_pool, close_connection_pool
from retry_handler import RetryHandler, RetryConfig
from queue_manager import create_queue
from performance_monitor import get_monitor

# 测试数据生成
def generate_test_keys(count: int = 100) -> List[LeakedKey]:
    """生成测试数据"""
    keys = []
    for i in range(count):
        key = LeakedKey(
            platform="openai",
            api_key=f"sk-test-{i:06d}-{'x' * 40}",
            base_url="https://api.openai.com",
            status=KeyStatus.PENDING.value,
            balance="",
            source_url=f"https://github.com/test/repo/blob/main/test{i}.py",
            found_time=datetime.now()
        )
        keys.append(key)
    return keys


async def test_connection_pool():
    """测试连接池性能"""
    print("\n" + "=" * 60)
    print("测试 1: 连接池性能")
    print("=" * 60)

    pool = await get_connection_pool()

    # 测试多次获取同一域名的 session
    test_url = "https://api.openai.com/v1/models"

    start_time = time.time()
    for i in range(100):
        session = await pool.get_session(test_url)
    duration = time.time() - start_time

    stats = pool.get_stats()

    print(f"\n获取 100 次 session 耗时: {duration:.3f} 秒")
    print(f"活跃 session 数: {stats['active_sessions']}")
    print(f"管理的域名: {stats['domains']}")
    print(f"平均耗时: {duration / 100 * 1000:.2f} ms/次")

    print("\n[OK] 连接池测试完成")


async def test_retry_handler():
    """测试重试机制"""
    print("\n" + "=" * 60)
    print("测试 2: 重试机制")
    print("=" * 60)

    handler = RetryHandler(RetryConfig(
        max_retries=3,
        initial_delay=0.1,
        max_delay=1.0
    ))

    # 模拟临时失败后成功的场景
    attempt_count = 0

    async def flaky_function():
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count < 3:
            raise ConnectionError("临时连接错误")
        return "成功"

    start_time = time.time()
    result = await handler.execute_with_retry(flaky_function)
    duration = time.time() - start_time

    stats = handler.get_stats()

    print(f"\n函数执行结果: {result}")
    print(f"总尝试次数: {attempt_count}")
    print(f"总耗时: {duration:.3f} 秒")
    print(f"重试统计:")
    print(f"  成功重试: {stats['successful_retries']}")
    print(f"  失败重试: {stats['failed_retries']}")
    print(f"  成功率: {stats['success_rate']:.1f}%")

    print("\n[OK] 重试机制测试完成")


async def test_dynamic_queue():
    """测试动态队列"""
    print("\n" + "=" * 60)
    print("测试 3: 动态队列管理")
    print("=" * 60)

    queue = create_queue(
        initial_size=100,
        auto_adjust=False,
        memory_threshold=80.0
    )

    await queue.start()

    # 测试放入和获取
    test_data = list(range(50))

    start_time = time.time()
    for item in test_data:
        await queue.put(item)
    put_duration = time.time() - start_time

    start_time = time.time()
    retrieved = []
    for _ in range(50):
        item = await queue.get()
        if item is not None:
            retrieved.append(item)
    get_duration = time.time() - start_time

    stats = queue.get_stats()

    print(f"\n放入 50 条数据耗时: {put_duration:.3f} 秒")
    print(f"获取 50 条数据耗时: {get_duration:.3f} 秒")
    print(f"队列统计:")
    print(f"  当前大小: {stats['current_size']}")
    print(f"  最大容量: {stats['max_size']}")
    print(f"  总放入: {stats['total_put']}")
    print(f"  总获取: {stats['total_get']}")
    print(f"  利用率: {stats['utilization_percent']:.1f}%")
    print(f"  内存使用: {stats['memory_usage_percent']:.1f}%")

    await queue.stop()

    print("\n[OK] 动态队列测试完成")


async def test_performance_monitor():
    """测试性能监控"""
    print("\n" + "=" * 60)
    print("测试 4: 性能监控")
    print("=" * 60)

    monitor = get_monitor()
    await monitor.start()

    # 模拟一些操作
    for i in range(100):
        latency = 0.01 + (i % 10) * 0.001
        success = i % 10 != 0
        error_type = "" if success else "connection_error"

        monitor.record_validation(latency, success, error_type)
        await asyncio.sleep(0.001)

    stats = monitor.get_full_stats()

    print(f"\n验证统计:")
    val_stats = stats['validation']
    print(f"  总数: {val_stats['total']}")
    print(f"  成功: {val_stats['successful']}")
    print(f"  失败: {val_stats['failed']}")
    print(f"  成功率: {val_stats['success_rate']:.1f}%")
    print(f"  吞吐量: {val_stats['throughput']['current_ops']:.2f} ops/s")

    print(f"\n延迟统计:")
    latency = val_stats['latency']
    print(f"  平均: {latency['avg_ms']:.2f} ms")
    print(f"  P50: {latency['p50_ms']:.2f} ms")
    print(f"  P95: {latency['p95_ms']:.2f} ms")
    print(f"  P99: {latency['p99_ms']:.2f} ms")

    print(f"\n资源使用:")
    resources = stats['resources']
    print(f"  内存: {resources['memory_mb']:.1f} MB")
    print(f"  CPU: {resources['cpu_percent']:.1f}%")

    await monitor.stop()

    print("\n[OK] 性能监控测试完成")


async def test_integrated_performance():
    """集成性能测试"""
    print("\n" + "=" * 60)
    print("测试 5: 集成性能测试")
    print("=" * 60)

    keys = generate_test_keys(500)

    db = AsyncDatabase("test_integrated.db")
    await db.init()

    monitor = get_monitor()

    start_time = time.time()
    for key in keys:
        write_start = time.time()
        await db.queue_insert(key)
        write_latency = time.time() - write_start
        monitor.record_db_write(write_latency)

    await db._flush_queue()
    duration = time.time() - start_time

    print(f"\n写入 {len(keys)} 条记录:")
    print(f"  总耗时: {duration:.3f} 秒")
    print(f"  吞吐量: {len(keys) / duration:.2f} ops/s")
    print(f"  平均延迟: {duration / len(keys) * 1000:.2f} ms")

    await db.close()
    import os
    if os.path.exists("test_integrated.db"):
        os.remove("test_integrated.db")

    print("\n[OK] 集成性能测试完成")


async def main():
    """主测试函数"""
    print("=" * 60)
    print("GitHub Secret Scanner Pro - v2.1 优化测试")
    print("=" * 60)
    print(f"\n开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        await test_connection_pool()
        await test_retry_handler()
        await test_dynamic_queue()
        await test_performance_monitor()
        await test_integrated_performance()

        await close_connection_pool()

        print("\n" + "=" * 60)
        print("所有测试完成!")
        print("=" * 60)

        print("\nv2.1 新增优化:")
        print("  1. HTTP 连接池 - 复用连接，减少开销")
        print("  2. 智能重试机制 - 指数退避，提高成功率")
        print("  3. 动态队列管理 - 根据内存压力自动调整")
        print("  4. 性能监控系统 - 实时统计延迟和吞吐量")

        print("\n建议:")
        print("  - 在生产环境中启用所有优化")
        print("  - 根据实际负载调整配置参数")
        print("  - 定期查看性能监控报告")

    except Exception as e:
        print(f"\n[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
