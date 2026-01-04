#!/usr/bin/env python3
"""
优化功能测试脚本
"""

import asyncio
import sys
from datetime import datetime

# 测试结果
results = {"passed": 0, "failed": 0, "errors": []}


def test(name):
    """测试装饰器"""
    def decorator(func):
        def wrapper():
            try:
                func()
                results["passed"] += 1
                print(f"  ✓ {name}")
            except AssertionError as e:
                results["failed"] += 1
                results["errors"].append(f"{name}: {e}")
                print(f"  ✗ {name}: {e}")
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(f"{name}: {type(e).__name__}: {e}")
                print(f"  ✗ {name}: {type(e).__name__}: {e}")
        return wrapper
    return decorator


# ============================================================================
#                              测试 1: 配置模块
# ============================================================================
print("\n[1/6] 测试配置模块...")

@test("新平台正则存在")
def test_new_platform_regex():
    from config import REGEX_PATTERNS
    assert "huggingface" in REGEX_PATTERNS, "缺少 huggingface"
    assert "groq" in REGEX_PATTERNS, "缺少 groq"
    assert "deepseek" in REGEX_PATTERNS, "缺少 deepseek"

@test("新平台默认 URL")
def test_new_platform_urls():
    from config import config
    urls = config.default_base_urls
    assert "huggingface" in urls, "缺少 huggingface URL"
    assert "groq" in urls, "缺少 groq URL"
    assert "deepseek" in urls, "缺少 deepseek URL"

@test("新平台搜索关键词")
def test_new_search_keywords():
    from config import config
    keywords = " ".join(config.search_keywords)
    assert "HUGGINGFACE" in keywords or "HF_TOKEN" in keywords, "缺少 HuggingFace 关键词"
    assert "GROQ" in keywords or "gsk_" in keywords, "缺少 Groq 关键词"

test_new_platform_regex()
test_new_platform_urls()
test_new_search_keywords()


# ============================================================================
#                              测试 2: 正则匹配
# ============================================================================
print("\n[2/6] 测试正则匹配...")

@test("HuggingFace Key 匹配")
def test_hf_regex():
    import re
    from config import REGEX_PATTERNS
    pattern = re.compile(REGEX_PATTERNS["huggingface"])
    # 有效 Key
    assert pattern.search("hf_abcdefghijklmnopqrstuvwxyz1234567890"), "应匹配有效 HF Key"
    # 无效 Key (太短)
    assert not pattern.search("hf_short"), "不应匹配太短的 Key"

@test("Groq Key 匹配")
def test_groq_regex():
    import re
    from config import REGEX_PATTERNS
    pattern = re.compile(REGEX_PATTERNS["groq"])
    # 有效 Key (gsk_ + 52字符)
    valid_key = "gsk_" + "a" * 52
    assert pattern.search(valid_key), "应匹配有效 Groq Key"

@test("DeepSeek Key 匹配")
def test_deepseek_regex():
    import re
    from config import REGEX_PATTERNS
    pattern = re.compile(REGEX_PATTERNS["deepseek"])
    # 有效 Key
    valid_key = "sk-" + "a" * 50
    assert pattern.search(valid_key), "应匹配有效 DeepSeek Key"

test_hf_regex()
test_groq_regex()
test_deepseek_regex()


# ============================================================================
#                              测试 3: 通知模块
# ============================================================================
print("\n[3/6] 测试通知模块...")

@test("通知模块导入")
def test_notifier_import():
    from notifier import Notifier, NotifyConfig, init_notifier, get_notifier
    assert Notifier is not None
    assert NotifyConfig is not None

@test("通知配置创建")
def test_notify_config():
    from notifier import NotifyConfig
    config = NotifyConfig(
        telegram_token="test_token",
        telegram_chat_id="123456"
    )
    assert config.telegram_token == "test_token"
    assert config.notify_on_valid == True

@test("通知器初始化")
def test_notifier_init():
    from notifier import Notifier, NotifyConfig
    config = NotifyConfig()
    notifier = Notifier(config)
    assert notifier is not None

test_notifier_import()
test_notify_config()
test_notifier_init()


# ============================================================================
#                              测试 4: 代理池模块
# ============================================================================
print("\n[4/6] 测试代理池模块...")

@test("代理池导入")
def test_proxy_pool_import():
    from proxy_pool import ProxyPool, ProxyInfo, init_proxy_pool, get_proxy_pool
    assert ProxyPool is not None
    assert ProxyInfo is not None

@test("代理池创建")
def test_proxy_pool_create():
    from proxy_pool import ProxyPool
    pool = ProxyPool(["http://proxy1:8080", "http://proxy2:8080"])
    assert len(pool.proxies) == 2
    assert pool.has_healthy_proxy == True

@test("代理池统计")
def test_proxy_pool_stats():
    from proxy_pool import ProxyPool
    pool = ProxyPool(["http://proxy1:8080"])
    stats = pool.get_stats()
    assert stats["total"] == 1
    assert stats["healthy"] == 1

test_proxy_pool_import()
test_proxy_pool_create()
test_proxy_pool_stats()


# ============================================================================
#                              测试 5: 异步数据库模块
# ============================================================================
print("\n[5/6] 测试异步数据库模块...")

@test("异步数据库导入")
def test_async_db_import():
    from async_database import AsyncDatabase, try_enable_uvloop
    assert AsyncDatabase is not None

@test("异步数据库创建")
def test_async_db_create():
    from async_database import AsyncDatabase
    db = AsyncDatabase(":memory:")
    assert db is not None
    assert db._batch_size == 50

test_async_db_import()
test_async_db_create()


# ============================================================================
#                              测试 6: 误报过滤增强
# ============================================================================
print("\n[6/6] 测试误报过滤增强...")

@test("scanner 模块导入")
def test_scanner_import():
    from scanner import GitHubScanner, calculate_entropy
    assert GitHubScanner is not None
    assert calculate_entropy is not None

@test("熵值计算")
def test_entropy():
    from scanner import calculate_entropy
    # 高熵值 (随机字符串)
    high_entropy = calculate_entropy("aB3xY9kL2mN5pQ8r")
    assert high_entropy > 3.0, f"随机字符串熵值应 > 3.0, 实际: {high_entropy}"

    # 低熵值 (重复字符)
    low_entropy = calculate_entropy("aaaaaaaaaa")
    assert low_entropy < 1.0, f"重复字符熵值应 < 1.0, 实际: {low_entropy}"

test_scanner_import()
test_entropy()


# ============================================================================
#                              测试结果汇总
# ============================================================================
print("\n" + "=" * 50)
print(f"测试结果: {results['passed']} 通过, {results['failed']} 失败")
print("=" * 50)

if results["errors"]:
    print("\n失败详情:")
    for err in results["errors"]:
        print(f"  - {err}")

sys.exit(0 if results["failed"] == 0 else 1)
