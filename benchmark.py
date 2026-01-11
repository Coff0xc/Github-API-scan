#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
性能对比测试脚本

对比原版和优化版的性能差异
"""

import time
import asyncio
import sqlite3
from datetime import datetime
from typing import List
from dataclasses import dataclass

from database import Database, LeakedKey, KeyStatus
from async_database import AsyncDatabase


@dataclass
class BenchmarkResult:
    """性能测试结果"""
    name: str
    duration: float
    operations: int
    ops_per_second: float


def generate_test_keys(count: int = 1000) -> List[LeakedKey]:
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


def benchmark_sync_db(keys: List[LeakedKey], db_path: str = "benchmark_sync.db") -> BenchmarkResult:
    """测试同步数据库性能"""
    # 清理旧数据库
    import os
    if os.path.exists(db_path):
        os.remove(db_path)

    db = Database(db_path)

    start_time = time.time()

    # 插入测试
    for key in keys:
        db.insert_key(key)

    duration = time.time() - start_time
    ops_per_second = len(keys) / duration if duration > 0 else 0

    # 清理
    if os.path.exists(db_path):
        os.remove(db_path)

    return BenchmarkResult(
        name="同步数据库 (原版)",
        duration=duration,
        operations=len(keys),
        ops_per_second=ops_per_second
    )


async def benchmark_async_db(keys: List[LeakedKey], db_path: str = "benchmark_async.db") -> BenchmarkResult:
    """测试异步数据库性能"""
    # 清理旧数据库
    import os
    if os.path.exists(db_path):
        os.remove(db_path)

    db = AsyncDatabase(db_path)
    await db.init()

    start_time = time.time()

    # 插入测试
    for key in keys:
        await db.queue_insert(key)

    # 强制刷新
    await db._flush_queue()

    duration = time.time() - start_time
    ops_per_second = len(keys) / duration if duration > 0 else 0

    # 清理
    await db.close()
    if os.path.exists(db_path):
        os.remove(db_path)

    return BenchmarkResult(
        name="异步数据库 (优化版)",
        duration=duration,
        operations=len(keys),
        ops_per_second=ops_per_second
    )


def print_result(result: BenchmarkResult):
    """打印测试结果"""
    print(f"\n{'='*60}")
    print(f"测试: {result.name}")
    print(f"{'='*60}")
    print(f"操作数量: {result.operations}")
    print(f"总耗时: {result.duration:.2f} 秒")
    print(f"吞吐量: {result.ops_per_second:.2f} ops/s")
    print(f"{'='*60}")


def compare_results(sync_result: BenchmarkResult, async_result: BenchmarkResult):
    """对比结果"""
    speedup = sync_result.duration / async_result.duration if async_result.duration > 0 else 0
    throughput_improvement = (async_result.ops_per_second / sync_result.ops_per_second - 1) * 100 if sync_result.ops_per_second > 0 else 0

    print(f"\n{'='*60}")
    print(f"性能对比")
    print(f"{'='*60}")
    print(f"加速比: {speedup:.2f}x")
    print(f"吞吐量提升: {throughput_improvement:.1f}%")

    if speedup >= 3:
        print(f"\n[OK] 优化版性能提升显著! (目标: 3-5x)")
    elif speedup >= 2:
        print(f"\n[WARN] 优化版有提升,但未达到预期 (目标: 3-5x)")
    else:
        print(f"\n[FAIL] 优化版性能提升不明显")

    print(f"{'='*60}")


def main():
    """主函数"""
    print("="*60)
    print("GitHub Secret Scanner Pro - 性能对比测试")
    print("="*60)

    # 生成测试数据
    print("\n生成测试数据...")
    test_sizes = [100, 500, 1000]

    for size in test_sizes:
        print(f"\n\n{'#'*60}")
        print(f"测试规模: {size} 条记录")
        print(f"{'#'*60}")

        keys = generate_test_keys(size)

        # 测试同步数据库
        print("\n[1/2] 测试同步数据库...")
        sync_result = benchmark_sync_db(keys)
        print_result(sync_result)

        # 测试异步数据库
        print("\n[2/2] 测试异步数据库...")
        async_result = asyncio.run(benchmark_async_db(keys))
        print_result(async_result)

        # 对比结果
        compare_results(sync_result, async_result)

    print("\n\n" + "="*60)
    print("测试完成!")
    print("="*60)
    print("\n建议:")
    print("- 如果性能提升 >= 3x, 可以放心使用优化版")
    print("- 如果性能提升 < 2x, 请检查系统配置")
    print("- 在生产环境中,性能提升可能更明显")


if __name__ == "__main__":
    main()
