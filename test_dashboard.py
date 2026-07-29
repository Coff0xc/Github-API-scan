#!/usr/bin/env python3
"""
Web Dashboard Test Script

Tests the web dashboard functionality without running the full scanner.
"""

import sqlite3
from datetime import datetime
import random

# Sample platforms and data
PLATFORMS = ['openai', 'anthropic', 'gemini', 'moonshot', 'zhipu', 'openrouter']
STATUSES = ['valid', 'invalid', 'quota_exceeded']

def create_test_database(db_path='test_dashboard.db'):
    """Create a test database with sample data"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leaked_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            api_key TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            info TEXT,
            source_url TEXT NOT NULL,
            base_url TEXT,
            model_tier TEXT,
            rpm INTEGER DEFAULT 0,
            balance REAL DEFAULT 0.0,
            is_high_value INTEGER DEFAULT 0,
            found_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Generate sample data
    print("Generating sample data...")

    for i in range(200):
        platform = random.choice(PLATFORMS)
        status = random.choice(STATUSES)
        is_high_value = 1 if random.random() > 0.7 else 0

        api_key = f"sk-test-{platform}-{i:04d}-{''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=20))}"
        info = "Valid key" if status == 'valid' else "Invalid" if status == 'invalid' else "Quota exceeded"
        source_url = f"https://github.com/test/repo-{i}/blob/main/config.py"

        cursor.execute('''
            INSERT OR IGNORE INTO leaked_keys
            (platform, api_key, status, info, source_url, is_high_value)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (platform, api_key, status, info, source_url, is_high_value))

    conn.commit()

    # Print stats
    cursor.execute('SELECT COUNT(*) FROM leaked_keys')
    total = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM leaked_keys WHERE status = "valid"')
    valid = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM leaked_keys WHERE is_high_value = 1')
    high_value = cursor.fetchone()[0]

    print(f"\n✅ Test database created: {db_path}")
    print(f"   Total keys: {total}")
    print(f"   Valid keys: {valid}")
    print(f"   High-value keys: {high_value}")

    conn.close()
    return db_path

def test_dashboard():
    """Test dashboard with sample data"""
    print("=" * 60)
    print("Web Dashboard Test")
    print("=" * 60)

    # Create test database
    db_path = create_test_database()

    print(f"\n📊 Starting Web Dashboard...")
    print(f"   Database: {db_path}")
    print(f"   URL: http://127.0.0.1:5000")
    print(f"\n⚠️  To use this test database, run:")
    print(f"   python web_dashboard.py")
    print(f"\n   Then modify web_dashboard.py line:")
    print(f"   db_reader = DatabaseReader(db_path='{db_path}')")
    print("\n" + "=" * 60)

if __name__ == '__main__':
    test_dashboard()
