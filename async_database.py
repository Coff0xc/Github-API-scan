"""
异步数据库模块 - 基于 aiosqlite 的高性能实现

特性：
- 全异步操作，消除 IO 阻塞
- 批量写入优化
- 连接池管理
"""

import asyncio
import threading
import aiosqlite
from datetime import datetime
from typing import Optional, List, Dict, Any, Set, Tuple
from loguru import logger

from database import LeakedKey, KeyStatus
from key_vault import vault
from config import config as app_config

_CLAIMS: Dict[str, Tuple[threading.Lock, Set[str]]] = {}
_CLAIMS_GUARD = threading.Lock()


def _shared_claims(db_path: str) -> Tuple[threading.Lock, Set[str]]:
    with _CLAIMS_GUARD:
        if db_path not in _CLAIMS:
            _CLAIMS[db_path] = (threading.Lock(), set())
        return _CLAIMS[db_path]


class AsyncDatabase:
    """异步数据库。连接绑在当前事件循环上，验证结果一次写入。"""

    def __init__(self, db_path: str = "leaked_keys.db", run_id: str = ""):
        self.db_path = db_path
        self.run_id = run_id or ""
        self._conn: Optional[aiosqlite.Connection] = None
        self._conn_lock: Optional[asyncio.Lock] = None
        self._write_queue: List[LeakedKey] = []
        self._claim_lock, self._pending_hashes = _shared_claims(db_path)
        self._queue_lock: Optional[asyncio.Lock] = None
        self._batch_size = app_config.db_batch_size
        self._flush_interval = app_config.db_flush_interval
        self._flush_task: Optional[asyncio.Task] = None

    async def init(self, *, start_flusher: bool = True):
        """在当前事件循环上打开连接并确保表结构。"""
        if self._conn is not None:
            return
        self._conn_lock = asyncio.Lock()
        self._queue_lock = asyncio.Lock()
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA synchronous=NORMAL")
        db = self._conn
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

        try:
            await db.execute("ALTER TABLE leaked_keys ADD COLUMN key_hash TEXT")
        except Exception:
            pass
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
        for retired in (
            "is_high_value", "balance", "balance_usd", "value_score",
            "used_quota_usd", "total_quota_usd", "tpm", "rpd",
            "has_gpt4", "has_gpt5", "has_claude_opus",
            "organization", "account_name", "expiration_date", "key_type",
        ):
            if retired in columns:
                await db.execute(f"ALTER TABLE leaked_keys DROP COLUMN {retired}")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS scanned_blobs (
                file_sha TEXT PRIMARY KEY,
                scan_time DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        for ddl in (
            "ALTER TABLE leaked_keys ADD COLUMN run_id TEXT DEFAULT ''",
            "ALTER TABLE leaked_keys ADD COLUMN checked_host TEXT DEFAULT ''",
        ):
            try:
                await db.execute(ddl)
            except Exception:
                pass
        await db.execute("""
            CREATE TABLE IF NOT EXISTS scan_runs (
                id TEXT PRIMARY KEY,
                scope TEXT NOT NULL DEFAULT '',
                started_at TEXT NOT NULL,
                finished_at TEXT,
                stats TEXT DEFAULT ''
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_run_id ON leaked_keys(run_id)"
        )
        await db.commit()

        if start_flusher:
            self._flush_task = asyncio.create_task(self._periodic_flush())
        logger.info(f"异步数据库初始化完成: {self.db_path}")

    async def connect(self) -> "AsyncDatabase":
        """在当前事件循环上打开一条新连接，与同路径实例共享 claim 集合。"""
        bound = AsyncDatabase(self.db_path, run_id=self.run_id)
        await bound.init(start_flusher=False)
        return bound

    async def close(self):
        """关闭数据库"""
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        await self._flush_queue()
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def _periodic_flush(self):
        """定期刷新写入队列"""
        while True:
            await asyncio.sleep(self._flush_interval)
            await self._flush_queue()

    def _row_values(self, key: LeakedKey):
        key_hash = vault.hash_key(key.api_key)
        return (
            key.platform,
            vault.encrypt(key.api_key),
            key_hash,
            key.base_url,
            key.status,
            key.source_url,
            key.model_tier,
            key.rpm,
            key.found_time.isoformat() if key.found_time else datetime.now().isoformat(),
            key.run_id or self.run_id or "",
            key.checked_host or "",
        )

    async def _flush_queue(self):
        """批量写入队列中的数据"""
        if self._queue_lock is None:
            return
        async with self._queue_lock:
            if not self._write_queue:
                return
            keys_to_write = self._write_queue[:]
            self._write_queue.clear()

        if not keys_to_write or self._conn is None or self._conn_lock is None:
            return

        async with self._conn_lock:
            for key in keys_to_write:
                try:
                    await self._conn.execute(
                        """
                        INSERT OR IGNORE INTO leaked_keys
                        (platform, api_key, key_hash, base_url, status, source_url, model_tier, rpm, found_time, run_id, checked_host)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        self._row_values(key),
                    )
                    with self._claim_lock:
                        self._pending_hashes.discard(vault.hash_key(key.api_key))
                except Exception as e:
                    logger.debug(f"批量写入异常: {e}")
            await self._conn.commit()

        logger.debug(f"批量写入 {len(keys_to_write)} 条记录")

    async def queue_insert(self, key: LeakedKey):
        """将 Key 加入写入队列"""
        if self._queue_lock is None:
            raise RuntimeError("AsyncDatabase.init() was not called")
        key_hash = vault.hash_key(key.api_key)
        with self._claim_lock:
            self._pending_hashes.add(key_hash)
        async with self._queue_lock:
            self._write_queue.append(key)
            if len(self._write_queue) >= self._batch_size:
                asyncio.create_task(self._flush_queue())

    async def flush(self):
        """立即落盘待写入队列。"""
        await self._flush_queue()

    async def claim_key(self, api_key: str) -> bool:
        """本轮是否该验证这条密钥。已入库或正在处理的返回 False。"""
        if self._conn is None:
            raise RuntimeError("AsyncDatabase.init() was not called")
        key_hash = vault.hash_key(api_key)
        self._claim_lock.acquire()
        try:
            if key_hash in self._pending_hashes:
                return False
            async with self._conn.execute(
                "SELECT 1 FROM leaked_keys WHERE key_hash = ? LIMIT 1",
                (key_hash,),
            ) as cursor:
                if await cursor.fetchone():
                    return False
            self._pending_hashes.add(key_hash)
            return True
        finally:
            self._claim_lock.release()

    async def release_claim(self, api_key: str) -> None:
        with self._claim_lock:
            self._pending_hashes.discard(vault.hash_key(api_key))

    async def upsert_finding(self, key: LeakedKey) -> None:
        """验证结束后一次写入：插入或按指纹更新状态。"""
        if self._conn is None or self._conn_lock is None:
            raise RuntimeError("AsyncDatabase.init() was not called")
        status = key.status
        verified_time = datetime.now().isoformat()
        values = self._row_values(key)
        async with self._conn_lock:
            await self._conn.execute(
                """
                INSERT INTO leaked_keys
                (platform, api_key, key_hash, base_url, status, source_url, model_tier, rpm, found_time, run_id, checked_host, verified_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(key_hash) DO UPDATE SET
                    status=excluded.status,
                    model_tier=excluded.model_tier,
                    rpm=excluded.rpm,
                    verified_time=excluded.verified_time,
                    base_url=excluded.base_url,
                    source_url=excluded.source_url,
                    run_id=excluded.run_id,
                    checked_host=excluded.checked_host
                """,
                values + (verified_time,),
            )
            await self._conn.commit()
        with self._claim_lock:
            self._pending_hashes.discard(values[2])

    async def attach_run(self, api_key: str, run_id: str = "") -> None:
        rid = run_id or self.run_id
        if not api_key or not rid or self._conn is None or self._conn_lock is None:
            return
        async with self._conn_lock:
            await self._conn.execute(
                "UPDATE leaked_keys SET run_id = ? WHERE key_hash = ?",
                (rid, vault.hash_key(api_key)),
            )
            await self._conn.commit()

    async def key_exists(self, api_key: str) -> bool:
        """检查 Key 是否存在（按 key_hash 指纹查询，含未落盘的在途项）"""
        key_hash = vault.hash_key(api_key)
        with self._claim_lock:
            if key_hash in self._pending_hashes:
                return True
        if self._conn is None or self._conn_lock is None:
            return False
        async with self._conn_lock:
            async with self._conn.execute(
                "SELECT 1 FROM leaked_keys WHERE key_hash = ? LIMIT 1",
                (key_hash,),
            ) as cursor:
                return await cursor.fetchone() is not None

    async def is_blob_scanned(self, file_sha: str) -> bool:
        """检查文件是否已扫描"""
        if self._conn is None or self._conn_lock is None:
            raise RuntimeError("AsyncDatabase.init() was not called")
        async with self._conn_lock:
            async with self._conn.execute(
                "SELECT 1 FROM scanned_blobs WHERE file_sha = ? LIMIT 1",
                (file_sha,),
            ) as cursor:
                return await cursor.fetchone() is not None

    async def mark_blob_scanned(self, file_sha: str) -> bool:
        """标记文件为已扫描"""
        if self._conn is None or self._conn_lock is None:
            return False
        try:
            async with self._conn_lock:
                await self._conn.execute(
                    "INSERT OR IGNORE INTO scanned_blobs (file_sha) VALUES (?)",
                    (file_sha,),
                )
                await self._conn.commit()
            return True
        except Exception:
            return False

    async def update_key_status(
        self,
        api_key: str,
        status: KeyStatus,
        model_tier: str = "",
        rpm: int = 0,
    ):
        """更新状态、模型档位和 RPM。"""
        if self._conn is None or self._conn_lock is None:
            raise RuntimeError("AsyncDatabase.init() was not called")
        async with self._conn_lock:
            await self._conn.execute(
                """
                UPDATE leaked_keys
                SET status = ?, model_tier = ?, rpm = ?, verified_time = ?
                WHERE key_hash = ?
                """,
                (
                    status.value, model_tier, rpm,
                    datetime.now().isoformat(), vault.hash_key(api_key),
                ),
            )
            await self._conn.commit()

    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        if self._conn is None or self._conn_lock is None:
            raise RuntimeError("AsyncDatabase.init() was not called")
        async with self._conn_lock:
            async with self._conn.execute("SELECT COUNT(*) FROM leaked_keys") as cursor:
                total = (await cursor.fetchone())[0]
            async with self._conn.execute(
                "SELECT status, COUNT(*) FROM leaked_keys GROUP BY status"
            ) as cursor:
                statuses = {row[0]: row[1] async for row in cursor}
            async with self._conn.execute(
                "SELECT platform, COUNT(*) FROM leaked_keys GROUP BY platform"
            ) as cursor:
                platforms = {row[0]: row[1] async for row in cursor}

        return {
            "total": total,
            "valid": statuses.get('valid', 0) + statuses.get('quota_exceeded', 0),
            "statuses": statuses,
            "platforms": platforms,
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
