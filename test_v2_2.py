#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v2.2 功能测试 - 验证缓存

测试内容：
1. 缓存管理器 - L1/L2/L3 缓存功能
2. 优化验证器不带死掉的批量路径
3. 优化验证器 - 集成测试（network）
"""

import asyncio
import time
from datetime import datetime

import pytest

from database import Database, LeakedKey, KeyStatus
from async_database import AsyncDatabase
from cache_manager import CacheManager, CacheConfig, DomainHealth
from validator_optimized import OptimizedAsyncValidator

from loguru import logger


# ============================================================================
#                          测试 1: 缓存管理器
# ============================================================================

async def test_cache_manager():
    """测试缓存管理器"""
    print("\n" + "=" * 60)
    print("测试 1: 缓存管理器")
    print("=" * 60)

    cache = CacheManager(CacheConfig(
        validation_ttl=10.0,
        domain_health_ttl=10.0,
        key_fingerprint_ttl=10.0
    ))
    await cache.start()

    # 测试 L1: 验证结果缓存
    print("\n[L1] 验证结果缓存测试")
    api_key = "sk-test-123456"
    base_url = "https://api.openai.com"

    # 第一次获取（应该未命中）
    result = await cache.get_validation_result(api_key, base_url)
    assert result is None, "首次获取应该返回 None"
    print("  [OK] 缓存未命中（预期）")

    # 设置缓存
    await cache.set_validation_result(api_key, base_url, {
        'status': 'valid',
        'info': '3模型',
        'model_tier': 'GPT-4',
        'rpm': 10000
    })
    print("  [OK] 缓存已设置")

    # 第二次获取（应该命中）
    result = await cache.get_validation_result(api_key, base_url)
    assert result is not None, "第二次获取应该命中缓存"
    assert result['status'] == 'valid'
    assert result['info'] == '3模型'
    assert 'balance' not in result
    print("  [OK] 缓存命中")

    # 测试 L2: 域名健康度缓存
    print("\n[L2] 域名健康度缓存测试")
    test_url = "https://test.example.com"

    # 记录成功
    await cache.record_domain_success(test_url)
    health = await cache.get_domain_health(test_url)
    assert health == DomainHealth.HEALTHY
    print("  [OK] 域名健康度: HEALTHY")

    # 记录多次失败
    for _ in range(5):
        await cache.record_domain_failure(test_url)
    health = await cache.get_domain_health(test_url)
    assert health == DomainHealth.UNHEALTHY
    print("  [OK] 域名健康度: UNHEALTHY")

    # 记录更多失败，变为 DEAD
    for _ in range(6):
        await cache.record_domain_failure(test_url)
    health = await cache.get_domain_health(test_url)
    assert health == DomainHealth.DEAD
    is_dead = await cache.is_domain_dead(test_url)
    assert is_dead
    print("  [OK] 域名健康度: DEAD")

    # 测试 L3: Key 指纹缓存
    print("\n[L3] Key 指纹缓存测试")
    test_key = "sk-fingerprint-test"

    # 首次检查
    exists = await cache.has_key_fingerprint(test_key)
    assert not exists
    print("  [OK] 指纹不存在（预期）")

    # 添加指纹
    await cache.add_key_fingerprint(test_key)
    exists = await cache.has_key_fingerprint(test_key)
    assert exists
    print("  [OK] 指纹已添加")

    # 获取统计
    stats = cache.get_stats()
    print(f"\n[统计] 缓存统计:")
    print(f"  验证缓存: {stats['validation']['size']} 条")
    print(f"  域名健康: {stats['domain_health']['size']} 个")
    print(f"  指纹缓存: {stats['fingerprints']['size']} 个")
    print(f"  命中率: {stats['validation']['hit_rate']:.1f}%")

    await cache.stop()
    print("\n[OK] 缓存管理器测试通过")


def test_optimized_validator_has_no_batch_path():
    """worker 按条 claim→validate→upsert，不走按域名攒批。"""
    validator = OptimizedAsyncValidator(Database(":memory:"))
    assert not hasattr(validator, "validate_batch")
    assert not hasattr(validator, "_batch_validator")
    stats = validator.get_stats()
    assert "batch" not in stats
    assert "batch_validations" not in stats


async def test_openai_cache_hit_uses_info_not_balance():
    class FakeCache:
        async def get_validation_result(self, api_key, base_url):
            return {
                "status": "valid",
                "info": "3模型",
                "model_tier": "GPT-4",
                "rpm": 8000,
                "balance": "should-be-ignored",
            }

        async def is_domain_dead(self, base_url):
            raise AssertionError("cache hit must not check domain")

    validator = OptimizedAsyncValidator(Database(":memory:"))
    validator._cache_manager = FakeCache()
    result = await validator.validate_openai(
        "sk-test-cache", "https://93.184.216.34/v1",
    )
    assert result.status == KeyStatus.VALID
    assert result.info == "3模型"
    assert result.model_tier == "GPT-4"
    assert result.rpm == 8000
    assert validator._stats["cache_hits"] == 1


# ============================================================================
#                          测试 3: 优化验证器集成
# ============================================================================

@pytest.mark.network
async def test_optimized_validator():
    """测试优化验证器（集成缓存）。

    会向 api.openai.com 发真实请求，标记为 network，默认套件不运行。
    """
    print("\n" + "=" * 60)
    print("测试 3: 优化验证器集成")
    print("=" * 60)

    # 初始化数据库
    db = AsyncDatabase("test_v2_2.db")
    await db.init()

    # 创建验证器
    validator = OptimizedAsyncValidator(
        db,
        dashboard=None,
        cache_config=CacheConfig(validation_ttl=60.0),
    )
    await validator.init_cache()

    print("\n[单个验证] 测试缓存功能")
    api_key = "sk-test-cache-123"
    base_url = "https://api.openai.com"

    # 第一次验证（缓存未命中）
    start = time.time()
    result1 = await validator.validate_openai(api_key, base_url)
    time1 = time.time() - start
    print(f"  第一次验证: {time1*1000:.1f}ms (缓存未命中)")

    # 第二次验证（缓存命中）
    start = time.time()
    result2 = await validator.validate_openai(api_key, base_url)
    time2 = time.time() - start
    print(f"  第二次验证: {time2*1000:.1f}ms (缓存命中)")

    if time2 < time1:
        speedup = time1 / time2
        print(f"  [OK] 缓存加速: {speedup:.1f}x")

    stats = validator.get_stats()
    print(f"\n[统计] 验证器统计:")
    print(f"  总验证: {stats['total_validations']}")
    print(f"  缓存命中: {stats['cache_hits']}")
    print(f"  缓存未命中: {stats['cache_misses']}")
    print(f"  死域名跳过: {stats['dead_domain_skipped']}")

    if stats['cache_hits'] + stats['cache_misses'] > 0:
        hit_rate = stats['cache_hits'] / (stats['cache_hits'] + stats['cache_misses']) * 100
        print(f"  缓存命中率: {hit_rate:.1f}%")

    # 清理
    await validator.close()
    await db.close()

    # 删除测试数据库
    import os
    if os.path.exists("test_v2_2.db"):
        os.remove("test_v2_2.db")

    print("\n[OK] 优化验证器集成测试通过")


# ============================================================================
#                          主测试函数
# ============================================================================

async def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("v2.2 功能测试套件")
    print("=" * 60)

    try:
        # 测试 1: 缓存管理器
        await test_cache_manager()
        test_optimized_validator_has_no_batch_path()
        await test_optimized_validator()

        print("\n" + "=" * 60)
        print("所有测试通过!")
        print("=" * 60)

        print("\nv2.2 功能验证:")
        print("  [OK] L1 验证结果缓存")
        print("  [OK] L2 域名健康度追踪")
        print("  [OK] L3 Key 指纹去重")
        print("  [OK] 缓存集成到验证器")

        return 0

    except Exception as e:
        print(f"\n[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
