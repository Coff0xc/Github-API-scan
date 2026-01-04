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

import sqlite3
import threading
from datetime import datetime
from typing import Optional, List
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum

from loguru import logger


class KeyStatus(Enum):
    """API Key 状态枚举"""
    PENDING = "pending"              # 待验证
    VALID = "valid"                  # 有效
    INVALID = "invalid"              # 无效（认证失败）
    QUOTA_EXCEEDED = "quota_exceeded"  # 有效但配额耗尽
    CONNECTION_ERROR = "connection_error"  # 连接失败（中转站挂了）
    UNVERIFIED = "unverified"        # 无法验证（如 Azure 缺少完整 endpoint）


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
    - is_high_value: 是否高价值 Key
    """
    platform: str           # openai, azure, gemini, anthropic
    api_key: str            # API Key
    base_url: str           # 绑定的 Base URL
    status: str = KeyStatus.PENDING.value
    balance: str = ""       # 余额/模型信息
    source_url: str = ""    # GitHub 来源链接
    model_tier: str = ""    # 模型阶梯: GPT-4, GPT-3.5, Gemini-Pro 等
    rpm: int = 0            # Rate Per Minute
    is_high_value: bool = False  # 是否高价值 Key
    found_time: datetime = None
    id: int = None
    
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
        self._init_db()
    
    @contextmanager
    def _get_connection(self):
        """获取数据库连接的上下文管理器"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # 启用 WAL 模式 - 提升并发读写性能
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-64000")  # 64MB 缓存
        try:
            yield conn
        finally:
            conn.close()
    
    def _init_db(self):
        """初始化数据库表结构"""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 创建主表（优化后的结构）
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS leaked_keys (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        platform TEXT NOT NULL,
                        api_key TEXT NOT NULL UNIQUE,
                        base_url TEXT NOT NULL,
                        status TEXT DEFAULT 'pending',
                        balance TEXT DEFAULT '',
                        source_url TEXT DEFAULT '',
                        model_tier TEXT DEFAULT '',
                        rpm INTEGER DEFAULT 0,
                        is_high_value BOOLEAN DEFAULT 0,
                        found_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                        verified_time DATETIME
                    )
                """)
                
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
                    cursor.execute("ALTER TABLE leaked_keys ADD COLUMN is_high_value BOOLEAN DEFAULT 0")
                except sqlite3.OperationalError:
                    pass
                
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
    
    # ========================================================================
    #                           Key 去重 (第二层防御)
    # ========================================================================
    
    def key_exists(self, api_key: str) -> bool:
        """
        检查 Key 是否已存在
        
        用于验证前检查，避免重复验证已入库的 Key
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT 1 FROM leaked_keys WHERE api_key = ? LIMIT 1",
                    (api_key,)
                )
                return cursor.fetchone() is not None
    
    def insert_key(self, key: LeakedKey) -> bool:
        """
        插入新的泄露密钥
        
        Returns:
            插入是否成功（已存在返回 False）
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute("""
                        INSERT INTO leaked_keys 
                        (platform, api_key, base_url, status, balance, source_url, model_tier, rpm, is_high_value, found_time)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        key.platform,
                        key.api_key,
                        key.base_url,
                        key.status,
                        key.balance,
                        key.source_url,
                        key.model_tier,
                        key.rpm,
                        1 if key.is_high_value else 0,
                        key.found_time.isoformat() if key.found_time else datetime.now().isoformat()
                    ))
                    conn.commit()
                    return True
                except sqlite3.IntegrityError:
                    return False
    
    def update_key_status(
        self, 
        api_key: str, 
        status: KeyStatus,
        balance: str = "",
        model_tier: str = "",
        rpm: int = 0,
        is_high_value: bool = False
    ) -> bool:
        """
        更新 Key 的验证状态
        
        Args:
            api_key: API Key
            status: 新状态
            balance: 余额/附加信息
            model_tier: 模型阶梯
            rpm: RPM 限制
            is_high_value: 是否高价值
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE leaked_keys 
                    SET status = ?, balance = ?, model_tier = ?, rpm = ?, is_high_value = ?, verified_time = ?
                    WHERE api_key = ?
                """, (
                    status.value, balance, model_tier, rpm, 
                    1 if is_high_value else 0, 
                    datetime.now().isoformat(), api_key
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
    
    @staticmethod
    def _row_to_key(row: sqlite3.Row) -> LeakedKey:
        """将数据库行转换为 LeakedKey 对象"""
        # 兼容旧数据库（无新字段）
        row_dict = dict(row)
        return LeakedKey(
            id=row_dict.get("id"),
            platform=row_dict.get("platform", ""),
            api_key=row_dict.get("api_key", ""),
            base_url=row_dict.get("base_url", ""),
            status=row_dict.get("status", "pending"),
            balance=row_dict.get("balance") or "",
            source_url=row_dict.get("source_url") or "",
            model_tier=row_dict.get("model_tier") or "",
            rpm=row_dict.get("rpm") or 0,
            is_high_value=bool(row_dict.get("is_high_value", 0)),
            found_time=datetime.fromisoformat(row_dict["found_time"]) if row_dict.get("found_time") else None
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
