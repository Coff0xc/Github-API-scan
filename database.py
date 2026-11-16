"""
数据库模块 - SQLite 数据持久化与去重

表结构：
1. leaked_keys - 泄露密钥表
   - api_key: 唯一索引
   - status: 验证状态 (valid/invalid/quota_exceeded/connection_error)
   
2. scanned_blobs - 已扫描文件 SHA 表 (持久化去重)
   - file_sha: Git Blob SHA (跨仓库去重)
   - scan_time: 扫描时间
"""

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Set, Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum

from loguru import logger

from key_vault import vault


class KeyStatus(Enum):
    """API Key 状态枚举"""
    PENDING = "pending"              # 待验证
    VALID = "valid"                  # 有效
    INVALID = "invalid"              # 无效（认证失败）
    QUOTA_EXCEEDED = "quota_exceeded"  # 有效但配额耗尽
    CONNECTION_ERROR = "connection_error"  # 连接失败（中转站挂了）；产物里归为 unknown
    UNVERIFIED = "unverified"        # 无法验证（如 Azure 缺少完整 endpoint）
    UNKNOWN = "unknown"              # 验证未完成：网络/超时/不确定


@dataclass
class LeakedKey:
    """
    泄露密钥数据模型

    核心字段：
    - api_key: API 密钥（唯一索引）
    - base_url: 绑定的 API 地址（解决 401 的关键）
    - status: 验证状态
    - model_tier: 模型阶梯 (GPT-4/GPT-3.5)
    - rpm: 速率限制
    """
    platform: str           # openai, azure, gemini, anthropic
    api_key: str            # API Key
    base_url: str           # 绑定的 Base URL
    status: str = KeyStatus.PENDING.value
    source_url: str = ""    # GitHub 来源链接
    model_tier: str = ""    # 模型阶梯: GPT-4, GPT-3.5, Gemini-Pro 等
    rpm: int = 0            # Rate Per Minute
    found_time: datetime = None
    id: int = None
    run_id: str = ""
    checked_host: str = ""
    verification_kind: str = ""

    def __post_init__(self):
        if self.found_time is None:
            self.found_time = datetime.now()


class Database:
    """
    SQLite 数据库管理类
    
    特性：
    - 线程安全（使用锁）
    - 唯一索引防重复
    - 支持多状态查询
    """
    
    def __init__(self, db_path: str = "leaked_keys.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        # :memory: 库必须共享同一连接：sqlite 的每个新连接都是独立的空内存库
        self._memory_conn = None
        if db_path == ":memory:":
            self._memory_conn = self._new_connection(db_path)
        self._init_db()

    @staticmethod
    def _new_connection(db_path: str) -> sqlite3.Connection:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # 启用 WAL 模式 - 提升并发读写性能
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-64000")  # 64MB 缓存
        return conn

    @contextmanager
    def _get_connection(self):
        """获取数据库连接的上下文管理器"""
        if self._memory_conn is not None:
            yield self._memory_conn
            return
        conn = self._new_connection(self.db_path)
        try:
            yield conn
        finally:
            conn.close()
    
    def _init_db(self):
        """初始化数据库表结构"""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # api_key 列: 启用 DB_ENCRYPTION_KEY 时存 Fernet 密文（enc:v1: 前缀）
                # key_hash 列: SHA-256 指纹，用于唯一去重（不随加密开关变化）
                cursor.execute("""
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

                # key_hash 列迁移 + 旧数据回填（兼容历史数据库）
                try:
                    cursor.execute("ALTER TABLE leaked_keys ADD COLUMN key_hash TEXT")
                except sqlite3.OperationalError:
                    pass  # 字段已存在
                cursor.execute(
                    "SELECT id, api_key FROM leaked_keys WHERE key_hash IS NULL"
                )
                for row_id, stored_key in cursor.fetchall():
                    cursor.execute(
                        "UPDATE leaked_keys SET key_hash = ? WHERE id = ?",
                        (vault.hash_key(vault.decrypt(stored_key)), row_id),
                    )
                try:
                    cursor.execute(
                        "CREATE UNIQUE INDEX IF NOT EXISTS idx_key_hash ON leaked_keys(key_hash)"
                    )
                except sqlite3.OperationalError as e:
                    logger.warning(f"key_hash 唯一索引创建失败（旧数据可能存在重复）: {e}")
                
                # 尝试添加新字段（兼容旧数据库）
                try:
                    cursor.execute("ALTER TABLE leaked_keys ADD COLUMN model_tier TEXT DEFAULT ''")
                except sqlite3.OperationalError:
                    pass
                try:
                    cursor.execute("ALTER TABLE leaked_keys ADD COLUMN rpm INTEGER DEFAULT 0")
                except sqlite3.OperationalError:
                    pass

                try:
                    cursor.execute(
                        "ALTER TABLE leaked_keys ADD COLUMN disposition TEXT DEFAULT 'open'"
                    )
                except sqlite3.OperationalError:
                    pass
                cursor.execute(
                    "UPDATE leaked_keys SET disposition = 'open' "
                    "WHERE disposition IS NULL OR disposition = ''"
                )

                columns = {row[1] for row in cursor.execute("PRAGMA table_info(leaked_keys)")}
                for retired in (
                    "is_high_value", "balance", "balance_usd", "value_score",
                    "used_quota_usd", "total_quota_usd", "tpm", "rpd",
                    "has_gpt4", "has_gpt5", "has_claude_opus",
                    "organization", "account_name", "expiration_date", "key_type",
                ):
                    if retired in columns:
                        cursor.execute(f"ALTER TABLE leaked_keys DROP COLUMN {retired}")

                # 创建索引
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_platform ON leaked_keys(platform)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_status ON leaked_keys(status)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_base_url ON leaked_keys(base_url)
                """)
                
                # ========== 创建已扫描文件 SHA 表 (持久化去重) ==========
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS scanned_blobs (
                        file_sha TEXT PRIMARY KEY,
                        scan_time DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                for column, ddl in (
                    ("run_id", "ALTER TABLE leaked_keys ADD COLUMN run_id TEXT DEFAULT ''"),
                    ("checked_host", "ALTER TABLE leaked_keys ADD COLUMN checked_host TEXT DEFAULT ''"),
                    ("verification_kind", "ALTER TABLE leaked_keys ADD COLUMN verification_kind TEXT DEFAULT ''"),
                ):
                    try:
                        cursor.execute(ddl)
                    except sqlite3.OperationalError:
                        pass
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS scan_runs (
                        id TEXT PRIMARY KEY,
                        scope TEXT NOT NULL DEFAULT '',
                        started_at TEXT NOT NULL,
                        finished_at TEXT,
                        stats TEXT DEFAULT ''
                    )
                """)
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_run_id ON leaked_keys(run_id)"
                )
                
                conn.commit()
                
                # 统计已扫描文件数
                cursor.execute("SELECT COUNT(*) FROM scanned_blobs")
                blob_count = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM leaked_keys")
                key_count = cursor.fetchone()[0]
                
                logger.info(f"数据库初始化完成: {self.db_path} (已扫描文件: {blob_count}, 已入库 Key: {key_count})")
    
    # ========================================================================
    #                           文件 SHA 去重 (第一层防御)
    # ========================================================================
    
    def is_blob_scanned(self, file_sha: str) -> bool:
        """
        检查文件 SHA 是否已扫描过
        
        Args:
            file_sha: Git Blob SHA (跨仓库去重)
            
        Returns:
            是否已扫描
        """
        if not file_sha:
            return False
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT 1 FROM scanned_blobs WHERE file_sha = ? LIMIT 1",
                    (file_sha,)
                )
                return cursor.fetchone() is not None
    
    def mark_blob_scanned(self, file_sha: str) -> bool:
        """
        标记文件 SHA 为已扫描
        
        Args:
            file_sha: Git Blob SHA
            
        Returns:
            插入是否成功
        """
        if not file_sha:
            return False
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(
                        "INSERT OR IGNORE INTO scanned_blobs (file_sha, scan_time) VALUES (?, ?)",
                        (file_sha, datetime.now().isoformat())
                    )
                    conn.commit()
                    return cursor.rowcount > 0
                except sqlite3.IntegrityError:
                    return False
    
    def get_scanned_blob_count(self) -> int:
        """获取已扫描文件数量"""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM scanned_blobs")
                return cursor.fetchone()[0]

    def load_scanned_blob_shas(self) -> Set[str]:
        """一次读出已扫描 blob，避免逐个文件查库。"""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT file_sha FROM scanned_blobs")
                return {row[0] for row in cursor.fetchall() if row[0]}

    def mark_blobs_scanned(self, file_shas: Iterable[str]) -> None:
        """批量标记已扫描 blob。"""
        rows = [(sha, datetime.now().isoformat()) for sha in file_shas if sha]
        if not rows:
            return
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany(
                    "INSERT OR IGNORE INTO scanned_blobs (file_sha, scan_time) VALUES (?, ?)",
                    rows,
                )
                conn.commit()
    
    # ========================================================================
    #                           Key 去重 (第二层防御)
    # ========================================================================
    
    def key_exists(self, api_key: str) -> bool:
        """
        检查 Key 是否已存在（按 key_hash 指纹查询，明文/密文模式均适用）

        用于验证前检查，避免重复验证已入库的 Key
        """
        return bool(self.existing_api_keys((api_key,)))

    def existing_api_keys(self, api_keys: Iterable[str]) -> Set[str]:
        """一次查出已入库的明文 key。"""
        hashed = {}
        for api_key in api_keys:
            if not api_key:
                continue
            hashed[vault.hash_key(api_key)] = api_key
        if not hashed:
            return set()
        hashes = tuple(hashed.keys())
        found = set()
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                for offset in range(0, len(hashes), 400):
                    chunk = hashes[offset:offset + 400]
                    placeholders = ",".join("?" * len(chunk))
                    cursor.execute(
                        f"SELECT key_hash FROM leaked_keys WHERE key_hash IN ({placeholders})",
                        chunk,
                    )
                    found.update(row[0] for row in cursor.fetchall())
        return {hashed[key_hash] for key_hash in found if key_hash in hashed}
    
    def insert_key(self, key: LeakedKey) -> bool:
        """插入新的泄露密钥。已存在返回 False。"""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute("""
                        INSERT INTO leaked_keys
                        (platform, api_key, key_hash, base_url, status, source_url, model_tier, rpm, found_time, run_id, checked_host, verification_kind)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        key.platform,
                        vault.encrypt(key.api_key),
                        vault.hash_key(key.api_key),
                        key.base_url,
                        key.status,
                        key.source_url,
                        key.model_tier,
                        key.rpm,
                        key.found_time.isoformat() if key.found_time else datetime.now().isoformat(),
                        key.run_id or "",
                        key.checked_host or "",
                        key.verification_kind or "",
                    ))
                    conn.commit()
                    return True
                except sqlite3.IntegrityError:
                    return False
    
    def update_key_status(
        self,
        api_key: str,
        status: KeyStatus,
        model_tier: str = "",
        rpm: int = 0,
    ) -> bool:
        """回写状态、模型档位和 RPM。"""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE leaked_keys
                    SET status = ?, model_tier = ?, rpm = ?, verified_time = ?
                    WHERE key_hash = ?
                """, (
                    status.value, model_tier, rpm,
                    datetime.now().isoformat(),
                    vault.hash_key(api_key)
                ))
                conn.commit()
                return cursor.rowcount > 0
    
    def get_keys_by_status(self, status: KeyStatus) -> List[LeakedKey]:
        """获取指定状态的所有 Key"""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM leaked_keys WHERE status = ?",
                    (status.value,)
                )
                return [self._row_to_key(row) for row in cursor.fetchall()]
    
    def get_valid_keys(self, platform: Optional[str] = None) -> List[LeakedKey]:
        """获取所有有效的 Key（包括 quota_exceeded，因为它们技术上是有效的）"""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                valid_statuses = (KeyStatus.VALID.value, KeyStatus.QUOTA_EXCEEDED.value)
                
                if platform:
                    cursor.execute("""
                        SELECT * FROM leaked_keys 
                        WHERE status IN (?, ?) AND platform = ?
                    """, (*valid_statuses, platform))
                else:
                    cursor.execute("""
                        SELECT * FROM leaked_keys WHERE status IN (?, ?)
                    """, valid_statuses)
                
                return [self._row_to_key(row) for row in cursor.fetchall()]
    
    def get_all_keys(self) -> List[LeakedKey]:
        """获取所有 Key"""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM leaked_keys ORDER BY found_time DESC")
                return [self._row_to_key(row) for row in cursor.fetchall()]
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 总数
                cursor.execute("SELECT COUNT(*) FROM leaked_keys")
                total = cursor.fetchone()[0]
                
                # 各状态数量
                cursor.execute("""
                    SELECT status, COUNT(*) as count 
                    FROM leaked_keys GROUP BY status
                """)
                statuses = {row[0]: row[1] for row in cursor.fetchall()}
                
                # 各平台数量
                cursor.execute("""
                    SELECT platform, COUNT(*) as count 
                    FROM leaked_keys GROUP BY platform
                """)
                platforms = {row[0]: row[1] for row in cursor.fetchall()}
                
                # 有效数（valid + quota_exceeded）
                valid_count = statuses.get('valid', 0) + statuses.get('quota_exceeded', 0)
                
                return {
                    "total": total,
                    "valid": valid_count,
                    "statuses": statuses,
                    "platforms": platforms
                }

    def list_finding_sources(self, run_id: str = "") -> List[dict]:
        """
        代理管道用的行。只返回指纹、脱敏预览和位置，不返回明文 Key。
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                sql = """
                    SELECT platform, key_hash, api_key, source_url, found_time, disposition,
                           status, base_url, run_id, checked_host, verification_kind
                    FROM leaked_keys
                """
                params = []
                if run_id:
                    sql += " WHERE run_id = ?"
                    params.append(run_id)
                sql += " ORDER BY found_time DESC"
                cursor.execute(sql, params)
                rows = []
                for row in cursor.fetchall():
                    stored = row["api_key"] or ""
                    fingerprint = (row["key_hash"] or "").strip()
                    if not fingerprint:
                        plain = vault.decrypt(stored)
                        fingerprint = vault.hash_key(plain) if plain else ""
                    if not fingerprint:
                        continue
                    rows.append({
                        "fingerprint": fingerprint,
                        "platform": row["platform"] or "",
                        "preview": vault.mask(stored),
                        "location": row["source_url"] or "",
                        "disposition": row["disposition"] or "open",
                        "found_time": row["found_time"] or "",
                        "status": row["status"] or "",
                        "base_url": row["base_url"] or "",
                        "run_id": row["run_id"] or "",
                        "checked_host": row["checked_host"] or "",
                        "verification_kind": row["verification_kind"] or "",
                    })
                return rows

    def create_run(self, scope: str) -> str:
        """Start a scan run and return its id."""
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"{stamp}-{uuid.uuid4().hex[:6]}"
        started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO scan_runs (id, scope, started_at) VALUES (?, ?, ?)",
                    (run_id, scope or "", started),
                )
                conn.commit()
        return run_id

    def latest_run_id(self) -> str:
        """Most recently started scan run, or empty."""
        with self._lock:
            with self._get_connection() as conn:
                try:
                    row = conn.execute(
                        "SELECT id FROM scan_runs ORDER BY rowid DESC LIMIT 1"
                    ).fetchone()
                except sqlite3.OperationalError:
                    return ""
                return (row[0] if row else "") or ""

    def finish_run(self, run_id: str, stats: Optional[dict] = None) -> None:
        if not run_id:
            return
        finished = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        payload = json.dumps(stats or {}, ensure_ascii=False)
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    "UPDATE scan_runs SET finished_at = ?, stats = ? WHERE id = ?",
                    (finished, payload, run_id),
                )
                conn.commit()

    def attach_run(self, api_key: str, run_id: str) -> None:
        if not api_key or not run_id:
            return
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    "UPDATE leaked_keys SET run_id = ? WHERE key_hash = ?",
                    (run_id, vault.hash_key(api_key)),
                )
                conn.commit()

    def set_disposition(self, fingerprint: str, disposition: str) -> bool:
        """按指纹更新处置状态。指纹必须是 64 位十六进制。"""
        fp = (fingerprint or "").strip().lower()
        if disposition not in ("open", "notified", "rotated", "false_positive"):
            return False
        if len(fp) != 64 or any(c not in "0123456789abcdef" for c in fp):
            return False
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE leaked_keys SET disposition = ? WHERE key_hash = ?",
                    (disposition, fp),
                )
                conn.commit()
                return cursor.rowcount == 1
    
    @staticmethod
    def _row_to_key(row: sqlite3.Row) -> LeakedKey:
        """将数据库行转换为 LeakedKey 对象（api_key 透明解密）"""
        # 兼容旧数据库（无新字段）
        row_dict = dict(row)
        return LeakedKey(
            id=row_dict.get("id"),
            platform=row_dict.get("platform", ""),
            api_key=vault.decrypt(row_dict.get("api_key", "")),
            base_url=row_dict.get("base_url", ""),
            status=row_dict.get("status", "pending"),
            source_url=row_dict.get("source_url") or "",
            model_tier=row_dict.get("model_tier") or "",
            rpm=row_dict.get("rpm") or 0,
            found_time=datetime.fromisoformat(row_dict["found_time"]) if row_dict.get("found_time") else None,
            run_id=row_dict.get("run_id") or "",
            checked_host=row_dict.get("checked_host") or "",
            verification_kind=row_dict.get("verification_kind") or "",
        )

    # ========================================================================
    #                           扫描进度持久化 (断点续传)
    # ========================================================================

    def save_progress(self, current_index: int, total: int, is_completed: bool = False):
        """保存扫描进度"""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS scan_progress (
                        id INTEGER PRIMARY KEY, current_index INTEGER,
                        total INTEGER, is_completed BOOLEAN, update_time DATETIME
                    )
                """)
                cursor.execute("""
                    INSERT OR REPLACE INTO scan_progress (id, current_index, total, is_completed, update_time)
                    VALUES (1, ?, ?, ?, ?)
                """, (current_index, total, 1 if is_completed else 0, datetime.now().isoformat()))
                conn.commit()

    def load_progress(self) -> dict:
        """加载扫描进度"""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS scan_progress (
                        id INTEGER PRIMARY KEY, current_index INTEGER,
                        total INTEGER, is_completed BOOLEAN, update_time DATETIME
                    )
                """)
                conn.commit()
                cursor.execute("SELECT current_index, total, is_completed FROM scan_progress WHERE id = 1")
                row = cursor.fetchone()
                if row:
                    return {"current_index": row[0], "total": row[1], "is_completed": bool(row[2])}
                return {"current_index": 0, "total": 0, "is_completed": False}

    def reset_progress(self):
        """重置扫描进度"""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS scan_progress (
                        id INTEGER PRIMARY KEY, current_index INTEGER,
                        total INTEGER, is_completed BOOLEAN, update_time DATETIME
                    )
                """)
                cursor.execute("DELETE FROM scan_progress WHERE id = 1")
                conn.commit()
