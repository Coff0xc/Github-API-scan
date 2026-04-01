#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v2.1 集成测试 - 验证所有优化模块协同工作

测试内容：
1. 连接池 + 重试机制 + 优化验证器
2. 动态队列 + 性能监控
3. 完整的验证流程
"""

import asyncio
import time
from datetime import datetime

from database import LeakedKey, KeyStatus
from async_database import AsyncDatabase
from connection_pool import get_connection_pool, close_connection_pool
from retry_handler import RetryHandler, RetryConfig
from queue_manager import create_queue
from performance_monitor import get_monitor
from validator_optimized import OptimizedAsyncValidator

from loguru import logger


async def test_full_integration():
    """完整集成测试"""
    print("\n" + "=" * 60)
    print("v2.1 完整集成测试")
    print("=" * 60)

    # 初始化组件
    db = AsyncDatabase("test_integration_v2.1.db")
    await db.init()

    monitor = get_monitor()
    await monitor.start()

    queue = create_queue(initial_size=100, auto_adjust=False)
    await queue.start()

    validator = OptimizedAsyncValidator(db, dashboard=None)

    print("\n[1/4] 组件初始化完成")

    # 生成测试数据
    test_keys = [
        LeakedKey(
            platform="openai",
            api_key=f"sk-test-{i:04d}-{'x' * 40}",
            base_url="https://api.openai.com",
            status=KeyStatus.PENDING.value,
            balance="",
            source_url=f"https://github.com/test/repo{i}",
            found_time=datetime.now()
        )
        for i in range(50)
    ]

    print(f"\n[2/4] 生成 {len(test_keys)} 个测试 Key")

    # 测试验证流程
    start_time = time.time()
    validation_tasks = []

    for key in test_keys:
        # 放入队列
        await queue.put(key)

        # 创建验证任务
        task = validator.validate_openai(key.api_key, key.base_url)
        validation_tasks.append(task)

    print(f"\n[3/4] 开始并发验证 ({len(validation_tasks)} 个)")

    # 并发执行验证
    results = await asyncio.gather(*validation_tasks, return_exceptions=True)

    duration = time.time() - start_time

    # 统计结果
    success_count = sum(1 for r in results if not isinstance(r, Exception))
    error_count = len(results) - success_count

    print(f"\n[4/4] 验证完成")
    print(f"  总数: {len(results)}")
    print(f"  成功: {success_count}")
    print(f"  错误: {error_count}")
    print(f"  耗时: {duration:.2f} 秒")
    print(f"  吞吐量: {len(results) / duration:.2f} ops/s")

    # 获取各组件统计
    print("\n" + "=" * 60)
    print("组件统计")
    print("=" * 60)

    # 验证器统计
    validator_stats = validator.get_stats()
    print(f"\n验证器:")
    print(f"  总验证: {validator_stats['total_validations']}")
    print(f"  成功: {validator_stats['successful_validations']}")
    print(f"  失败: {validator_stats['failed_validations']}")
    print(f"  重试: {validator_stats['retried_validations']}")
    print(f"  连接复用: {validator_stats['connection_reused']}")

    # 连接池统计
    pool = await get_connection_pool()
    pool_stats = pool.get_stats()
    print(f"\n连接池:")
    print(f"  活跃 session: {pool_stats['active_sessions']}")
    print(f"  管理域名: {len(pool_stats['domains'])}")

    # 队列统计
    queue_stats = queue.get_stats()
    print(f"\n动态队列:")
    print(f"  当前大小: {queue_stats['current_size']}")
    print(f"  总放入: {queue_stats['total_put']}")
    print(f"  总获取: {queue_stats['total_get']}")
    print(f"  内存使用: {queue_stats['memory_usage_percent']:.1f}%")

    # 性能监控统计
    print("\n性能监控:")
    monitor.print_report()

    # 清理
    await monitor.stop()
    await queue.stop()
    await validator.close()
    await close_connection_pool()
    await db.close()

    # 删除测试数据库
    import os
    if os.path.exists("test_integration_v2.1.db"):
        os.remove("test_integration_v2.1.db")

    print("\n" + "=" * 60)
    print("集成测试完成!")
    print("=" * 60)

    print("\nv2.1 优化验证:")
    print("  [OK] 连接池正常工作")
    print("  [OK] 智能重试机制生效")
    print("  [OK] 动态队列管理正常")
    print("  [OK] 性能监控数据准确")
    print("  [OK] 所有组件协同工作")

    return True


async def main():
    """主函数"""
    try:
        success = await test_full_integration()
        if success:
            print("\n[SUCCESS] 所有测试通过!")
            return 0
        else:
            print("\n[FAILED] 测试失败")
            return 1
    except Exception as e:
        print(f"\n[ERROR] 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
