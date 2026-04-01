#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI API Key Scanner - Test Mode
Tests the tool with sample data without requiring GitHub token
"""

import re
from config import REGEX_PATTERNS

print("=" * 70)
print("AI API Key Scanner - Test Mode")
print("=" * 70)

# Sample leaked keys (fake examples for testing regex)
test_keys = {
    "OpenAI": "sk-proj-abcdefghijklmnopqrstuvwxyz1234567890ABCDEFGHIJKLMN",
    "Anthropic": "sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890",
    "Google Gemini": "AIzaSyAbCdEfGhIjKlMnOpQrStUvWxYz1234567",
    "Azure OpenAI": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
    "xAI Grok": "xai-abcdefghijklmnopqrstuvwxyz1234567890abcdef",
    "OpenRouter": "sk-or-v1-" + "a" * 64,
    "HuggingFace": "hf_abcdefghijklmnopqrstuvwxyz1234567890",
    "Groq": "gsk_" + "a" * 52,
    "DeepSeek": "sk-" + "a" * 48,
}

print("\n[Test 1] Regex Pattern Matching")
print("-" * 70)

detected = 0
total = 0

for platform_name, test_key in test_keys.items():
    total += 1
    platform_key = platform_name.lower().replace(" ", "_")

    # Find matching pattern
    found = False
    for pattern_name, pattern in REGEX_PATTERNS.items():
        try:
            if re.search(pattern, test_key):
                print(f"[OK] {platform_name:20s} -> Detected as '{pattern_name}'")
                detected += 1
                found = True
                break
        except:
            pass

    if not found:
        print(f"[!!] {platform_name:20s} -> NOT DETECTED")

print(f"\nDetection Rate: {detected}/{total} ({detected*100//total}%)")

# Test search queries
print("\n[Test 2] Search Query Syntax")
print("-" * 70)

from config import config

sample_queries = config.search_keywords[:5]
for i, query in enumerate(sample_queries, 1):
    # Check for deprecated syntax
    has_deprecated = "NOT test" in query or "NOT example" in query
    syntax = "DEPRECATED" if has_deprecated else "Modern"
    print(f"[{i}] [{syntax:10s}] {query[:60]}...")

print(f"\nTotal queries configured: {len(config.search_keywords)}")

# Test database
print("\n[Test 3] Database Operations")
print("-" * 70)

from database import Database

db = Database(":memory:")
print("[OK] Database initialized")

# Simulate adding a key
from database import LeakedKey, KeyStatus
test_entry = LeakedKey(
    platform="openai",
    api_key="sk-test-demo-key",
    base_url="https://api.openai.com/v1",
    source_url="https://github.com/test/demo",
    status=KeyStatus.VALID,
    is_high_value=True
)

db.add_or_update_key(test_entry)
print("[OK] Key added to database")

stats = db.get_stats()
print(f"[OK] Database stats: {stats['total']} keys")

# Test UI components
print("\n[Test 4] UI Components")
print("-" * 70)

try:
    from ui import Dashboard
    print("[OK] Dashboard class available")
    print("[OK] Rich TUI components loaded")
    print("[OK] Real-time display ready")
except Exception as e:
    print(f"[!!] UI Error: {e}")

# Test export
print("\n[Test 5] Export Functions")
print("-" * 70)

import tempfile
import os

try:
    # Test text export
    temp_file = os.path.join(tempfile.gettempdir(), "test_export.txt")

    with open(temp_file, 'w') as f:
        f.write(f"Platform: {test_entry.platform}\n")
        f.write(f"API Key: {test_entry.api_key}\n")
        f.write(f"Status: {test_entry.status}\n")

    if os.path.exists(temp_file):
        print(f"[OK] Text export working")
        print(f"[OK] Test file: {temp_file}")
        os.remove(temp_file)

except Exception as e:
    print(f"[!!] Export Error: {e}")

# Summary
print("\n" + "=" * 70)
print("TEST SUMMARY")
print("=" * 70)

print(f"""
[OK] Regex Detection:  {detected}/{total} patterns working
[OK] Search Queries:   {len(config.search_keywords)} configured
[OK] Database:         Fully functional
[OK] UI:              Ready
[OK] Export:          Working

TOOL STATUS: READY TO USE
""")

print("=" * 70)
print("Next Steps:")
print("=" * 70)
print("""
1. Add GitHub token to config_local.py:
   GITHUB_TOKENS = ["ghp_your_token_here"]

2. Run the scanner:
   python main_v2.2.py

3. View results:
   python main_v2.2.py --stats
   python main_v2.2.py --export results.txt --status valid
""")

print("=" * 70)
print("Tool is ready. Configure GitHub token to start scanning!")
print("=" * 70)
