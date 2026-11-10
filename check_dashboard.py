#!/usr/bin/env python3
"""
Web Dashboard 冒烟脚本

用真实 Database 类造一个带样例数据的库，供人工打开 dashboard 查看。
表结构由 database.py 自己初始化，不会随手工 CREATE TABLE 漂移。
"""

import random

from database import Database, LeakedKey, KeyStatus

PLATFORMS = ['openai', 'anthropic', 'gemini', 'moonshot', 'zhipu', 'openrouter']
STATUSES = [KeyStatus.VALID, KeyStatus.INVALID, KeyStatus.QUOTA_EXCEEDED]
MODEL_TIERS = {'openai': 'GPT-4', 'anthropic': 'Claude Opus', 'gemini': 'Gemini-Pro'}


def create_test_database(db_path='check_dashboard.db'):
    """通过真实 Database 类写入样例数据，schema 与线上一致。"""
    db = Database(db_path)

    print("Generating sample data...")
    for i in range(200):
        platform = random.choice(PLATFORMS)
        api_key = (
            f"sk-test-{platform}-{i:04d}-"
            f"{''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=20))}"
        )
        key = LeakedKey(
            platform=platform,
            api_key=api_key,
            base_url="https://api.example.com/v1",
            status=KeyStatus.PENDING.value,
            source_url=f"https://github.com/test/repo-{i}/blob/main/config.py",
        )
        if db.insert_key(key):
            db.update_key_status(
                api_key,
                status=random.choice(STATUSES),
                model_tier=MODEL_TIERS.get(platform, ''),
                rpm=random.choice([0, 60, 3500]),
            )

    stats = db.get_stats()
    print(f"\n✅ Test database created: {db_path}")
    print(f"   Total keys: {stats.get('total', 0)}")
    print(f"   Valid keys: {stats.get('valid', 0)}")

    return db_path


def main():
    print("=" * 60)
    print("Web Dashboard Smoke Data")
    print("=" * 60)

    db_path = create_test_database()

    print(f"\n📊 To view this sample data:")
    print(f"   DB_PATH={db_path} python web_dashboard.py")
    print(f"   Then open http://127.0.0.1:5000")
    print("\n" + "=" * 60)


if __name__ == '__main__':
    main()
