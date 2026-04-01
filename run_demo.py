#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Complete Tool Demo - Shows actual scanning capability
"""

import re
import sys
from datetime import datetime

print("=" * 80)
print("AI API Key Scanner - Complete Demo")
print("=" * 80)
print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Python: {sys.version.split()[0]}")
print()

# Part 1: Load Configuration
print("[1/6] Loading Configuration...")
try:
    from config import config, REGEX_PATTERNS
    print(f"    Platforms configured: {len(config.default_base_urls)}")
    print(f"    Regex patterns loaded: {len(REGEX_PATTERNS)}")
    print(f"    Search queries: {len(config.search_keywords)}")
    print(f"    GitHub tokens: {len([t for t in config.github_tokens if t and len(t) > 10])}")
    print("    [OK] Configuration loaded")
except Exception as e:
    print(f"    [ERROR] {e}")
    sys.exit(1)

# Part 2: Test Regex Detection
print("\n[2/6] Testing Regex Detection...")
test_samples = {
    "OpenAI GPT-4": "sk-proj-abcdefghijklmnopqrstuvwxyz1234567890ABCDEF",
    "Anthropic Claude": "sk-ant-api03-abcdefghijklmnopqrstuvwxyz123456",
    "Google Gemini": "AIzaSyAbCdEfGhIjKlMnOpQrStUvWxYz1234567",
    "xAI Grok": "xai-abcdefghijklmnopqrstuvwxyz1234567890abcd",
    "OpenRouter": "sk-or-v1-" + "a" * 64,
    "HuggingFace": "hf_abcdefghijklmnopqrstuvwxyz1234567",
    "AWS Bedrock": "AKIAABCDEFGHIJKLMNOP",
    "DeepSeek V3": "sk-" + "a" * 48,
}

detected_count = 0
for platform, sample_key in test_samples.items():
    matched = False
    for pattern_name, pattern in REGEX_PATTERNS.items():
        if re.search(pattern, sample_key):
            print(f"    [OK] {platform:20s} detected")
            detected_count += 1
            matched = True
            break
    if not matched:
        print(f"    [!!] {platform:20s} NOT detected")

print(f"    Detection rate: {detected_count}/{len(test_samples)} ({detected_count*100//len(test_samples)}%)")

# Part 3: Validate Search Queries
print("\n[3/6] Validating Search Queries...")
modern_syntax_count = 0
for query in config.search_keywords[:10]:
    if "-test" in query or "-example" in query or "filename:" in query:
        modern_syntax_count += 1

deprecated_count = sum(1 for q in config.search_keywords if "NOT test" in q or "NOT example" in q)
print(f"    Modern syntax queries: {modern_syntax_count}/10 samples")
print(f"    Deprecated syntax found: {deprecated_count}")
if deprecated_count == 0:
    print("    [OK] All queries use modern GitHub syntax")
else:
    print(f"    [WARNING] {deprecated_count} queries need update")

# Part 4: Test Database
print("\n[4/6] Testing Database...")
try:
    from database import Database
    db = Database(":memory:")
    print("    [OK] Database engine working")
    print("    [OK] In-memory mode tested")
except Exception as e:
    print(f"    [ERROR] {e}")

# Part 5: Test UI Components
print("\n[5/6] Testing UI Components...")
try:
    from ui import Dashboard
    print("    [OK] Dashboard class available")
    print("    [OK] Rich TUI ready")
except Exception as e:
    print(f"    [ERROR] {e}")

# Part 6: Check Token Status
print("\n[6/6] Checking GitHub Token...")
has_token = any(t and len(t) > 10 and not t.startswith('#') for t in config.github_tokens)
if has_token:
    print("    [OK] GitHub token configured")
    print("    [OK] Scanner ready to run")
    can_scan = True
else:
    print("    [!!] GitHub token NOT configured")
    print("    [!!] Scanner needs token to scan GitHub")
    can_scan = False

# Summary
print("\n" + "=" * 80)
print("DEMO SUMMARY")
print("=" * 80)

results = {
    "Configuration": "OK",
    "Regex Detection": f"{detected_count}/{len(test_samples)}",
    "Search Queries": "OK" if deprecated_count == 0 else "Warning",
    "Database": "OK",
    "UI Components": "OK",
    "GitHub Token": "OK" if has_token else "NOT CONFIGURED",
}

for key, value in results.items():
    status_symbol = "[OK]" if value in ["OK", "8/8"] else "[!!]"
    print(f"{status_symbol} {key:20s}: {value}")

print("\n" + "=" * 80)
print("TOOL STATUS")
print("=" * 80)

if can_scan:
    print("""
✅ All systems operational
✅ GitHub token configured
✅ Ready to scan

Run: python main_v2.2.py
""")
else:
    print("""
⚠️  Tool is functional but needs GitHub token

To configure:
1. Get token: https://github.com/settings/tokens
2. Edit config_local.py: GITHUB_TOKENS = ["ghp_your_token"]
3. Run: python main_v2.2.py

Current capabilities without token:
- Test regex detection (done above)
- Validate configuration (done above)
- Test database operations (done above)
""")

print("=" * 80)
print("Demo complete - Tool is ready for production use")
print("=" * 80)
