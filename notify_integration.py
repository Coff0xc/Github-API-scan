"""
通知集成模块 - 验证后的处置通知
================================

活路径只有一条：validator_optimized 的验证 worker 在密钥仍可用时调用
disclose_finding()。它只在用户配置了通知渠道（notify_config.yaml 或
环境变量）时发送，内容只有平台、脱敏预览和位置；渠道接受后把该行
标为 notified。没有配置就不发，也不写任何桌面密钥文件。
"""

import os
from pathlib import Path

from loguru import logger

from notifier_v2 import (
    KeyInfo,
    create_notifier_from_env,
    init_notifier,
)


def configured_notifier():
    """只在用户写了通知配置或环境变量时才建渠道。没有配置就不发，也不写桌面密钥文件。"""
    config_path = os.getenv("NOTIFY_CONFIG", "notify_config.yaml")
    if Path(config_path).exists():
        return init_notifier(config_path)
    has_env = any(os.getenv(name) for name in (
        "DISCORD_WEBHOOK",
        "SLACK_WEBHOOK",
        "TELEGRAM_BOT_TOKEN",
        "FEISHU_WEBHOOK",
        "DINGTALK_WEBHOOK",
        "SERVERCHAN_KEY",
        "BARK_DEVICE_KEY",
    ))
    if has_env:
        return create_notifier_from_env()
    return None


async def disclose_finding(db_path: str, platform: str, api_key: str, source_url: str) -> dict:
    """验证表明该授权资产上的密钥仍然可用时，通知位置和预览，并标为 notified。"""
    notifier = configured_notifier()
    if notifier is None or not notifier.channels:
        return {"skipped": True, "reason": "notifier_not_configured"}

    from key_vault import vault
    from database import Database

    fingerprint = vault.hash_key(api_key)
    key_info = KeyInfo(
        platform=platform or "",
        api_key=api_key,
        source_url=source_url or "",
        fingerprint=fingerprint,
    )
    try:
        results = await notifier.notify(key_info)
    except Exception as exc:
        logger.error(f"发送处置通知失败: {exc}")
        return {"error": str(exc)}

    sent = any(name != "skipped" and value is True for name, value in results.items())
    if sent and not Database(db_path).set_disposition(fingerprint, "notified"):
        logger.warning("通知已发出，但没有把指纹标为 notified")
    return results
