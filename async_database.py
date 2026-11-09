"""
异步数据库模块 - 基于 aiosqlite 的高性能实现

特性：
- 全异步操作，消除 IO 阻塞
- 批量写入优化
- 连接池管理
"""

import asyncio
import aiosqlite
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from contextlib import asynccontextmanager
from loguru import logger

from database import LeakedKey, KeyStatus
from key_vault import vault
from config import config as app_config


class AsyncDatabase:
    """异步数据库管理类"""

    def __init__(self, db_path: str = "leaked_keys.db"):
        self.db_path = db_path
        self._write_queue: List[LeakedKey] = []
        self._queue_lock = asyncio.Lock()
        # 批量写入参数可通过 config.yaml database.batch_size / flush_interval 调整
        self._batch_size = app_config.db_batch_size
        self._flush_interval = app_config.db_flush_interval  # 秒
        self._flush_task: Optional[asyncio.Task] = None

    async def init(self):
        """初始化数据库"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS leaked_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    api_key TEXT NOT NULL UNIQUE,
                    key_hash TEXT,
                    base_url TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    source_url TEXT DEFAULT '',
                    model_tier TEXT DEFAULT '',
                    rpm INTEGER DEFAULT 0,
                    found_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                    verified_time DATETIME
                )
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_status ON leaked_keys(status)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_platform ON leaked_keys(platform)")

            # key_hash 列迁移 + 旧数据回填（兼容历史数据库）
            try:
                await db.execute("ALTER TABLE leaked_keys ADD COLUMN key_hash TEXT")
            except Exception:
                pass  # 字段已存在
            async with db.execute(
                "SELECT id, api_key FROM leaked_keys WHERE key_hash IS NULL"
            ) as cursor:
                rows = await cursor.fetchall()
            for row_id, stored_key in rows:
                await db.execute(
                    "UPDATE leaked_keys SET key_hash = ? WHERE id = ?",
                    (vault.hash_key(vault.decrypt(stored_key)), row_id),
                )
            try:
                await db.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_key_hash ON leaked_keys(key_hash)"
                )
            except Exception as e:
                logger.warning(f"key_hash 唯一索引创建失败（旧数据可能存在重复）: {e}")

            try:
                await db.execute(
                    "ALTER TABLE leaked_keys ADD COLUMN disposition TEXT DEFAULT 'open'"
                )
            except Exception:
                pass
            async with db.execute("PRAGMA table_info(leaked_keys)") as cursor:
                columns = {row[1] for row in await cursor.fetchall()}
            for retired in ("is_high_value", "balance", "balance_usd", "value_score"):
                if retired in columns:
                    await db.execute(f"ALTER TABLE leaked_keys DROP COLUMN {retired}")

            await db.execute("""
                CREATE TABLE IF NOT EXISTS scanned_blobs (
                    file_sha TEXT PRIMARY KEY,
                    scan_time DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()

        # 启动批量写入任务
        self._flush_task = asyncio.create_task(self._periodic_flush())
        logger.info(f"异步数据库初始化完成: {self.db_path}")

    async def close(self):
        """关闭数据库"""
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        await self._flush_queue()

    async def _periodic_flush(self):
        """定期刷新写入队列"""
        while True:
            await asyncio.sleep(self._flush_interval)
            await self._flush_queue()

    async def _flush_queue(self):
        """批量写入队列中的数据"""
        async with self._queue_lock:
            if not self._write_queue:
                return

            keys_to_write = self._write_queue[:]
            self._write_queue.clear()

        if not keys_to_write:
            return

        async with aiosqlite.connect(self.db_path) as db:
            for key in keys_to_write:
                try:
                    await db.execute("""
                        INSERT OR IGNORE INTO leaked_keys
                        (platform, api_key, key_hash, base_url, status, source_url, model_tier, rpm, found_time)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        key.platform, vault.encrypt(key.api_key), vault.hash_key(key.api_key),
                        key.base_url, key.status,
                        key.source_url, key.model_tier, key.rpm,
                        key.found_time.isoformat() if key.found_time else datetime.now().isoformat()
                    ))
                except Exception as e:
                    logger.debug(f"批量写入异常: {e}")
            await db.commit()

        logger.debug(f"批量写入 {len(keys_to_write)} 条记录")

    async def queue_insert(self, key: LeakedKey):
        """将 Key 加入写入队列"""
        async with self._queue_lock:
            self._write_queue.append(key)
            if len(self._write_queue) >= self._batch_size:
                asyncio.create_task(self._flush_queue())

    async def key_exists(self, api_key: str) -> bool:
        """检查 Key 是否存在（按 key_hash 指纹查询）"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT 1 FROM leaked_keys WHERE key_hash = ? LIMIT 1",
                (vault.hash_key(api_key),)
            ) as cursor:
                return await cursor.fetchone() is not None

    async def is_blob_scanned(self, file_sha: str) -> bool:
        """检查文件是否已扫描"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT 1 FROM scanned_blobs WHERE file_sha = ? LIMIT 1",
                (file_sha,)
            ) as cursor:
                return await cursor.fetchone() is not None

    async def mark_blob_scanned(self, file_sha: str) -> bool:
        """标记文件为已扫描"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute(
                    "INSERT OR IGNORE INTO scanned_blobs (file_sha) VALUES (?)",
                    (file_sha,)
                )
                await db.commit()
                return True
            except Exception:
                return False

    async def update_key_status(
        self,
        api_key: str,
        status: KeyStatus,
        balance: str = "",
        model_tier: str = "",
        rpm: int = 0,
        is_high_value: bool = False
    ):
        """更新状态、模型档位和 RPM。余额参数仍可传入，不再写入。"""
        del balance, is_high_value
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE leaked_keys
                SET status = ?, model_tier = ?, rpm = ?, verified_time = ?
                WHERE key_hash = ?
            """, (
                status.value, model_tier, rpm,
                datetime.now().isoformat(), vault.hash_key(api_key)
            ))
            await db.commit()

    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM leaked_keys") as cursor:
                total = (await cursor.fetchone())[0]

            async with db.execute(
                "SELECT status, COUNT(*) FROM leaked_keys GROUP BY status"
            ) as cursor:
                statuses = {row[0]: row[1] async for row in cursor}

            async with db.execute(
                "SELECT platform, COUNT(*) FROM leaked_keys GROUP BY platform"
            ) as cursor:
                platforms = {row[0]: row[1] async for row in cursor}

        return {
            "total": total,
            "valid": statuses.get('valid', 0) + statuses.get('quota_exceeded', 0),
            "statuses": statuses,
            "platforms": platforms
        }


def try_enable_uvloop():
    """尝试启用 uvloop 以提升性能"""
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        logger.info("uvloop 已启用")
        return True
    except ImportError:
        logger.debug("uvloop 未安装，使用默认事件循环")
        return False
