"""
Key 存储加密模块（可选静态加密）
================================

通过环境变量 DB_ENCRYPTION_KEY 启用后：

- api_key 列存 Fernet 密文（前缀 enc:v1:），明文永不落盘
- 去重使用 key_hash 列（SHA-256，单向，不可还原）
- 导出/展示时通过 decrypt() 透明还原

未设置 DB_ENCRYPTION_KEY 时保持明文兼容模式（向后兼容旧数据库），
仅建议在自有授权数据上使用明文模式。

密钥派生：PBKDF2-HMAC-SHA256(secret, 静态盐, 200_000 轮) -> Fernet key。
更换 DB_ENCRYPTION_KEY 会使已有密文不可解密（解密返回空串），请妥善保管。
"""

import os
import base64
import hashlib
from typing import Optional

from loguru import logger

_CIPHER_PREFIX = "enc:v1:"
_KDF_SALT = b"github-api-scan/key-vault/v1"
_KDF_ITERATIONS = 200_000


class KeyVault:
    """透明加解密 + 指纹去重的存储保险库"""

    def __init__(self, secret: Optional[str] = None):
        self.enabled = False
        self._fernet = None

        if secret is None:
            secret = os.getenv("DB_ENCRYPTION_KEY", "").strip()

        if secret:
            try:
                from cryptography.fernet import Fernet
                derived = hashlib.pbkdf2_hmac(
                    "sha256", secret.encode("utf-8"), _KDF_SALT, _KDF_ITERATIONS
                )
                self._fernet = Fernet(base64.urlsafe_b64encode(derived))
                self.enabled = True
                logger.info("数据库静态加密已启用 (DB_ENCRYPTION_KEY)")
            except Exception as e:
                logger.error(f"加密初始化失败，回退明文模式: {e}")
        else:
            logger.warning(
                "未设置 DB_ENCRYPTION_KEY，api_key 将明文入库"
                "（仅建议在自有授权扫描数据上使用）"
            )

    # ------------------------------------------------------------------
    def encrypt(self, plaintext: str) -> str:
        """明文 -> 密文（未启用时原样返回；失败时原样返回，绝不丢数据）"""
        if not self.enabled or not plaintext:
            return plaintext
        try:
            return _CIPHER_PREFIX + self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")
        except Exception as e:
            logger.error(f"加密失败（以明文写入，请检查 DB_ENCRYPTION_KEY）: {e}")
            return plaintext

    def decrypt(self, stored: str) -> str:
        """
        密文/明文 -> 明文。

        - 无前缀视为旧明文数据，原样返回（兼容历史库）
        - 有前缀但本进程无密钥或密钥不匹配：返回空串（拒绝泄出）
        """
        if not stored:
            return stored or ""
        if not stored.startswith(_CIPHER_PREFIX):
            return stored
        if not self.enabled:
            logger.warning("检测到密文数据但未设置 DB_ENCRYPTION_KEY，无法解密")
            return ""
        try:
            return self._fernet.decrypt(stored[len(_CIPHER_PREFIX):].encode("ascii")).decode("utf-8")
        except Exception:
            logger.error("解密失败：DB_ENCRYPTION_KEY 与加密时不一致，或数据损坏")
            return ""

    @staticmethod
    def hash_key(api_key: str) -> str:
        """不可逆指纹，用于唯一索引去重"""
        return hashlib.sha256((api_key or "").encode("utf-8")).hexdigest()

    def mask(self, stored: str, reveal: bool = False) -> str:
        """脱敏展示：sk-proj-abc...wxyz。reveal=True 且可解密时返回明文"""
        plain = self.decrypt(stored)
        if reveal:
            return plain
        if len(plain) <= 10:
            return (plain[:3] + "***") if plain else "***"
        return f"{plain[:6]}...{plain[-4:]}"


# 全局单例：database / async_database / web_dashboard 共用
vault = KeyVault()
