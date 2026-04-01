"""
通知集成模块 - 将 notifier_v2 集成到验证流程中
=================================================

使用方法:
    from notify_integration import NotifyIntegration

    # 初始化
    integration = NotifyIntegration(config_path="notify_config.yaml")

    # 在验证成功后调用
    await integration.on_key_validated(
        platform="openai",
        api_key="sk-xxx",
        base_url="https://api.openai.com",
        model_tier="GPT-4",
        balance="$50.00",
        rpm=3000,
        source_url="https://github.com/...",
        is_high_value=True
    )
"""

import asyncio
from datetime import datetime
from typing import Optional
from pathlib import Path

from loguru import logger

from notifier_v2 import (
    NotifierV2,
    KeyInfo,
    Severity,
    DiscordChannel,
    SlackChannel,
    TelegramChannel,
    FeishuChannel,
    DingtalkChannel,
    ServerChanChannel,
    BarkChannel,
    FileChannel,
    SoundChannel,
    create_notifier_from_env,
    init_notifier,
)


class NotifyIntegration:
    """
    通知系统集成类

    将 notifier_v2 与现有的 validator.py 对接
    """

    def __init__(self, config_path: str = None):
        """
        初始化通知集成

        Args:
            config_path: YAML 配置文件路径，如果为 None 则从环境变量加载
        """
        self.notifier: Optional[NotifierV2] = None
        self.enabled = True

        # 尝试加载配置
        try:
            if config_path and Path(config_path).exists():
                self.notifier = init_notifier(config_path)
                logger.info(f"通知系统已从配置文件初始化: {config_path}")
            else:
                # 检查是否有环境变量配置
                import os
                has_env_config = any([
                    os.getenv('DISCORD_WEBHOOK'),
                    os.getenv('SLACK_WEBHOOK'),
                    os.getenv('TELEGRAM_BOT_TOKEN'),
                    os.getenv('FEISHU_WEBHOOK'),
                    os.getenv('DINGTALK_WEBHOOK'),
                    os.getenv('SERVERCHAN_KEY'),
                    os.getenv('BARK_DEVICE_KEY'),
                ])

                if has_env_config:
                    self.notifier = create_notifier_from_env()
                    logger.info("通知系统已从环境变量初始化")
                else:
                    # 最小配置: 仅文件和声音
                    self.notifier = NotifierV2()
                    self.notifier.add_channel(FileChannel())
                    self.notifier.add_channel(SoundChannel())
                    logger.info("通知系统已使用最小配置初始化 (文件+声音)")

        except Exception as e:
            logger.error(f"通知系统初始化失败: {e}")
            self.enabled = False

    async def on_key_validated(
        self,
        platform: str,
        api_key: str,
        base_url: str = "",
        model_tier: str = "",
        balance: str = "",
        rpm: int = 0,
        source_url: str = "",
        is_high_value: bool = False,
        status: str = "valid"
    ) -> dict:
        """
        密钥验证成功时的回调

        此方法应在 validator.py 的 process_result 方法中调用

        Args:
            platform: 平台名称 (openai, anthropic, etc.)
            api_key: API 密钥
            base_url: Base URL
            model_tier: 模型阶梯 (GPT-4, Claude-3, etc.)
            balance: 余额信息
            rpm: 速率限制
            source_url: GitHub 来源 URL
            is_high_value: 是否为高价值 Key
            status: 状态 (valid, quota_exceeded)

        Returns:
            通知发送结果字典
        """
        if not self.enabled or not self.notifier:
            return {"skipped": True, "reason": "notifier_disabled"}

        # 只对 valid 和 quota_exceeded 状态发送通知
        if status not in ["valid", "quota_exceeded"]:
            return {"skipped": True, "reason": "status_not_notifiable"}

        # 创建 KeyInfo 对象
        key_info = KeyInfo(
            platform=platform,
            api_key=api_key,
            base_url=base_url,
            model_tier=model_tier,
            balance=balance,
            rpm=rpm,
            source_url=source_url,
            is_high_value=is_high_value,
            found_time=datetime.now()
        )

        # 发送通知
        try:
            results = await self.notifier.notify(key_info)
            return results
        except Exception as e:
            logger.error(f"发送通知失败: {e}")
            return {"error": str(e)}

    async def send_daily_report(self) -> dict:
        """发送每日汇总报告"""
        if not self.enabled or not self.notifier:
            return {"skipped": True, "reason": "notifier_disabled"}

        try:
            return await self.notifier.send_daily_report()
        except Exception as e:
            logger.error(f"发送每日报告失败: {e}")
            return {"error": str(e)}

    def get_stats(self) -> dict:
        """获取通知统计"""
        if not self.enabled or not self.notifier:
            return {"enabled": False}

        return {
            "enabled": True,
            **self.notifier.get_stats()
        }


# ============================================================================
#                         全局单例
# ============================================================================

_notify_integration: Optional[NotifyIntegration] = None


def get_notify_integration(config_path: str = None) -> NotifyIntegration:
    """获取全局通知集成实例"""
    global _notify_integration

    if _notify_integration is None:
        _notify_integration = NotifyIntegration(config_path)

    return _notify_integration


def init_notify_integration(config_path: str = None) -> NotifyIntegration:
    """初始化全局通知集成实例"""
    global _notify_integration
    _notify_integration = NotifyIntegration(config_path)
    return _notify_integration


# ============================================================================
#                         Validator 集成补丁
# ============================================================================

def patch_validator_for_notifications(validator_class, config_path: str = None):
    """
    为 AsyncValidator 类添加通知功能的补丁

    使用方法:
        from validator import AsyncValidator
        from notify_integration import patch_validator_for_notifications

        patch_validator_for_notifications(AsyncValidator, "notify_config.yaml")

        # 之后所有 AsyncValidator 实例都会自动发送通知
    """
    original_init = validator_class.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._notify_integration = get_notify_integration(config_path)

    # 保存原始 process_result 方法的引用
    if hasattr(validator_class, 'process_result'):
        original_process = validator_class.process_result

        async def patched_process(self, result, *args, **kwargs):
            # 调用原始方法
            ret = await original_process(self, result, *args, **kwargs)

            # 如果有通知集成，检查是否需要发送通知
            if hasattr(self, '_notify_integration') and self._notify_integration:
                # 获取验证结果（需要从原方法返回值或状态获取）
                # 这里假设验证后 Key 已更新到数据库
                try:
                    if hasattr(result, 'api_key') and hasattr(result, 'platform'):
                        key = self.db.get_key_by_api_key(result.api_key) if hasattr(self.db, 'get_key_by_api_key') else None
                        if key and key.status in ['valid', 'quota_exceeded']:
                            await self._notify_integration.on_key_validated(
                                platform=key.platform,
                                api_key=key.api_key,
                                base_url=key.base_url,
                                model_tier=key.model_tier,
                                balance=key.balance,
                                rpm=key.rpm,
                                source_url=key.source_url,
                                is_high_value=key.is_high_value,
                                status=key.status
                            )
                except Exception as e:
                    logger.debug(f"通知发送异常: {e}")

            return ret

        validator_class.process_result = patched_process

    validator_class.__init__ = patched_init
    logger.info("已为 Validator 添加通知功能补丁")


# ============================================================================
#                         便捷函数
# ============================================================================

async def notify_key_found(
    platform: str,
    api_key: str,
    base_url: str = "",
    model_tier: str = "",
    balance: str = "",
    rpm: int = 0,
    source_url: str = "",
    is_high_value: bool = False
) -> dict:
    """
    便捷函数：发现有效 Key 时调用

    可在任何地方直接调用：
        from notify_integration import notify_key_found

        await notify_key_found(
            platform="openai",
            api_key="sk-xxx",
            model_tier="GPT-4",
            is_high_value=True
        )
    """
    integration = get_notify_integration()
    return await integration.on_key_validated(
        platform=platform,
        api_key=api_key,
        base_url=base_url,
        model_tier=model_tier,
        balance=balance,
        rpm=rpm,
        source_url=source_url,
        is_high_value=is_high_value
    )


# ============================================================================
#                         测试代码
# ============================================================================

async def _test():
    """测试通知集成"""
    print("测试通知集成...")

    integration = NotifyIntegration()

    # 测试高价值 Key 通知
    result = await integration.on_key_validated(
        platform="openai",
        api_key="sk-proj-test1234567890abcdef",
        base_url="https://api.openai.com",
        model_tier="GPT-4-Turbo",
        balance="$100.00 remaining",
        rpm=10000,
        source_url="https://github.com/test/repo",
        is_high_value=True
    )

    print(f"通知结果: {result}")
    print(f"统计: {integration.get_stats()}")


if __name__ == "__main__":
    asyncio.run(_test())
