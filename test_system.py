#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
组件自检脚本。同时可被 pytest 收集：

- 直接运行 `python test_system.py`：打印每步结果，末尾给汇总和退出码。
- pytest 收集：断言失败即测试失败；GitHub token 未配置时跳过而非失败
  （token 是环境条件，不是代码缺陷）。
"""

import sys


def test_imports():
    """Test that all required modules can be imported"""
    print("[1/5] Testing module imports...")
    try:
        import aiohttp  # noqa: F401
        import rich  # noqa: F401
        from github import Github  # noqa: F401
        import loguru  # noqa: F401
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Run: pip install -r requirements.txt")
        raise AssertionError(f"module import failed: {e}") from e
    print("✅ All required modules imported successfully")


def test_config():
    """Test configuration loading"""
    print("\n[2/5] Testing configuration...")
    try:
        from config import config, REGEX_PATTERNS
        print("✅ Configuration loaded successfully")
        print(f"   - Platforms: {len(config.default_base_urls)}")
        print(f"   - Regex patterns: {len(REGEX_PATTERNS)}")
        print(f"   - Search queries: {len(config.search_keywords)}")
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        raise AssertionError(f"config load failed: {e}") from e


def test_regex():
    """Test regex pattern compilation"""
    print("\n[3/5] Testing regex patterns...")
    import re
    from config import REGEX_PATTERNS
    errors = []
    for name, pattern in REGEX_PATTERNS.items():
        try:
            re.compile(pattern)
        except Exception as e:
            errors.append(f"{name}: {e}")

    if errors:
        print(f"❌ Regex errors found:")
        for err in errors:
            print(f"   - {err}")
        raise AssertionError(f"invalid regex patterns: {errors}")
    print(f"✅ All {len(REGEX_PATTERNS)} regex patterns valid")


def test_github_token():
    """Test GitHub token configuration. 未配置时 pytest 跳过（环境条件）。"""
    print("\n[4/5] Testing GitHub token...")
    from config import config
    token = ""
    if config.github_tokens:
        token = config.github_tokens[0] or ""
    configured = bool(token) and not token.startswith("#")
    if not configured:
        print("⚠️  GitHub token not configured")
        print("   Add your token to config_local.py")
        print("   Get token: https://github.com/settings/tokens")
        import pytest
        pytest.skip("GitHub token not configured")
    print("✅ GitHub token configured")


def test_database():
    """Test database connection"""
    print("\n[5/5] Testing database...")
    try:
        from database import Database
        db = Database(":memory:")  # Use in-memory database for testing
        stats = db.get_stats()
        print("✅ Database working correctly")
        print(f"   - Current records: {stats.get('total', 0)}")
    except Exception as e:
        print(f"❌ Database error: {e}")
        raise AssertionError(f"database init failed: {e}") from e


def main():
    """Run all tests"""
    print("=" * 50)
    print("AI API Key Scanner - Component Test")
    print("=" * 50)

    checks = [test_imports, test_config, test_regex, test_github_token, test_database]
    passed = 0
    for check in checks:
        try:
            check()
            passed += 1
        except KeyboardInterrupt:
            raise
        except BaseException as exc:
            # AssertionError（断言失败）与 pytest.skip 的 Skipped（继承 BaseException）都走这里
            print(f"   -> {type(exc).__name__}: {exc}")

    print("\n" + "=" * 50)

    if passed == len(checks):
        print(f"✅ All tests passed ({passed}/{len(checks)})")
        print("\n🚀 Ready to scan! Run: python main_v2.2.py")
        return 0
    elif passed >= 3:
        print(f"⚠️  Mostly working ({passed}/{len(checks)} passed)")
        print("\n📝 Configure GitHub token to start scanning")
        return 1
    else:
        print(f"❌ System not ready ({passed}/{len(checks)} passed)")
        print("\n📦 Install dependencies: pip install -r requirements.txt")
        return 2


if __name__ == "__main__":
    sys.exit(main())
