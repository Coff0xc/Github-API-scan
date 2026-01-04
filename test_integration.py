#!/usr/bin/env python3
"""
集成测试 - 验证器新平台支持
"""

import sys
sys.path.insert(0, '.')

def test_validators():
    """测试新平台验证器"""
    from validator import AsyncValidator, CircuitBreaker
    from database import Database
    import threading

    print("\n[集成测试] 验证器新平台支持")
    print("=" * 50)

    # 创建内存数据库
    db = Database(":memory:")

    # 创建验证器
    validator = AsyncValidator(db)

    # 测试 1: 验证方法存在
    print("\n1. 检查新平台验证方法...")
    assert hasattr(validator, 'validate_huggingface'), "缺少 validate_huggingface"
    assert hasattr(validator, 'validate_groq'), "缺少 validate_groq"
    assert hasattr(validator, 'validate_deepseek'), "缺少 validate_deepseek"
    print("   ✓ 所有新平台验证方法存在")

    # 测试 2: SSRF 防护
    print("\n2. 测试 SSRF 防护...")

    # 应该被阻止的 URL
    blocked_urls = [
        ("http://192.168.1.1/api", "私有 IP"),
        ("http://10.0.0.1/api", "私有 IP"),
        ("http://internal.corp/api", "危险后缀"),
        ("http://api.local/v1", "危险后缀"),
    ]

    all_blocked = True
    for url, reason in blocked_urls:
        result = validator._is_likely_valid_relay(url)
        if result:
            print(f"   ✗ 未阻止 ({reason}): {url}")
            all_blocked = False
        else:
            print(f"   ✓ 已阻止 ({reason}): {url}")

    # 应该允许的 URL
    allowed_urls = [
        "https://api.openai.com/v1",
        "https://api.groq.com/openai/v1",
        "https://api.deepseek.com/v1",
    ]

    print("\n   允许的 URL:")
    all_allowed = True
    for url in allowed_urls:
        result = validator._is_likely_valid_relay(url)
        if result:
            print(f"   ✓ 已允许: {url}")
        else:
            print(f"   ✗ 被阻止: {url}")
            all_allowed = False

    # 测试 3: 熔断器线程安全
    print("\n3. 检查熔断器线程安全...")
    cb = CircuitBreaker()
    lock_type = type(cb._lock).__name__
    is_thread_safe = 'lock' in lock_type.lower()
    if is_thread_safe:
        print(f"   ✓ 熔断器使用 {lock_type}")
    else:
        print(f"   ✗ 熔断器锁类型: {lock_type}")

    print("\n" + "=" * 50)
    if all_blocked and all_allowed and is_thread_safe:
        print("集成测试完成: 全部通过 ✓")
    else:
        print("集成测试完成: 部分失败")
    print("=" * 50)


if __name__ == "__main__":
    test_validators()
