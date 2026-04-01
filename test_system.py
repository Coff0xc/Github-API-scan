#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to verify all components work correctly
"""

import sys

def test_imports():
    """Test that all required modules can be imported"""
    print("[1/5] Testing module imports...")
    try:
        import aiohttp
        import rich
        from github import Github
        import loguru
        print("✅ All required modules imported successfully")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Run: pip install -r requirements.txt")
        return False

def test_config():
    """Test configuration loading"""
    print("\n[2/5] Testing configuration...")
    try:
        from config import config, REGEX_PATTERNS
        print(f"✅ Configuration loaded successfully")
        print(f"   - Platforms: {len(config.default_base_urls)}")
        print(f"   - Regex patterns: {len(REGEX_PATTERNS)}")
        print(f"   - Search queries: {len(config.search_keywords)}")
        return True
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        return False

def test_regex():
    """Test regex pattern compilation"""
    print("\n[3/5] Testing regex patterns...")
    try:
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
            return False
        else:
            print(f"✅ All {len(REGEX_PATTERNS)} regex patterns valid")
            return True
    except Exception as e:
        print(f"❌ Regex test error: {e}")
        return False

def test_github_token():
    """Test GitHub token configuration"""
    print("\n[4/5] Testing GitHub token...")
    try:
        from config import config
        if config.github_tokens and config.github_tokens[0] and not config.github_tokens[0].startswith("#"):
            print("✅ GitHub token configured")
            return True
        else:
            print("⚠️  GitHub token not configured")
            print("   Add your token to config_local.py")
            print("   Get token: https://github.com/settings/tokens")
            return False
    except Exception as e:
        print(f"❌ Token test error: {e}")
        return False

def test_database():
    """Test database connection"""
    print("\n[5/5] Testing database...")
    try:
        from database import Database
        db = Database(":memory:")  # Use in-memory database for testing
        stats = db.get_stats()
        print(f"✅ Database working correctly")
        print(f"   - Current records: {stats.get('total', 0)}")
        return True
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

def main():
    """Run all tests"""
    print("=" * 50)
    print("AI API Key Scanner - Component Test")
    print("=" * 50)

    results = [
        test_imports(),
        test_config(),
        test_regex(),
        test_github_token(),
        test_database(),
    ]

    print("\n" + "=" * 50)
    passed = sum(results)
    total = len(results)

    if passed == total:
        print(f"✅ All tests passed ({passed}/{total})")
        print("\n🚀 Ready to scan! Run: python main_v2.2.py")
        return 0
    elif passed >= 3:
        print(f"⚠️  Mostly working ({passed}/{total} passed)")
        print("\n📝 Configure GitHub token to start scanning")
        return 1
    else:
        print(f"❌ System not ready ({passed}/{total} passed)")
        print("\n📦 Install dependencies: pip install -r requirements.txt")
        return 2

if __name__ == "__main__":
    sys.exit(main())
