"""
通知系统 v2.0 - 企业级多渠道通知
=================================

新增功能:
- Discord Webhook 支持
- Slack Webhook 支持
- 飞书机器人支持
- Server酱 (ServerChan) 支持
- Bark (iOS) 支持
- 严重性分级 (Critical/High/Medium/Low)
- 通知去重 (避免重复推送)
- 静默时段配置
- 每日汇总报告
- 富文本消息格式 (Markdown/HTML)
- 通知速率限制 (防刷屏)
"""

import os
import json
import asyncio
import hashlib
import smtplib
from abc import ABC, abstractmethod
from enum import Enum
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, time, timedelta
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Set, Any, Callable
from collections import deque
from pathlib import Path

import aiohttp
from loguru import logger


# ============================================================================
#                              严重性分级系统
# ============================================================================

class Severity(Enum):
    """通知严重性级别"""
    CRITICAL = "critical"  # GPT-4/Claude-3-Opus + 余额 > $100
    HIGH = "high"          # GPT-4/Claude-3 或 余额 > $10
    MEDIUM = "medium"      # GPT-3.5/普通 Key 有效
    LOW = "low"            # 配额耗尽但有效
    INFO = "info"          # 信息通知 (汇总等)

    @property
    def emoji(self) -> str:
        return {
            Severity.CRITICAL: "🚨",
            Severity.HIGH: "🔥",
            Severity.MEDIUM: "✅",
            Severity.LOW: "⚠️",
            Severity.INFO: "ℹ️",
        }[self]

    @property
    def color(self) -> int:
        """Discord embed 颜色"""
        return {
            Severity.CRITICAL: 0xFF0000,  # 红色
            Severity.HIGH: 0xFF6B00,      # 橙色
            Severity.MEDIUM: 0x00FF00,    # 绿色
            Severity.LOW: 0xFFFF00,       # 黄色
            Severity.INFO: 0x0099FF,      # 蓝色
        }[self]


@dataclass
class KeyInfo:
    """密钥信息数据类"""
    platform: str
    api_key: str
    base_url: str = ""
    model_tier: str = ""        # GPT-4, GPT-3.5, Claude-3, etc.
    balance: str = ""           # $100.00, unlimited, etc.
    rpm: int = 0                # Rate limit
    source_url: str = ""        # GitHub 来源链接
    is_high_value: bool = False
    found_time: datetime = field(default_factory=datetime.now)

    @property
    def masked_key(self) -> str:
        """脱敏后的 Key"""
        if len(self.api_key) <= 12:
            return self.api_key[:4] + "****"
        return self.api_key[:8] + "****" + self.api_key[-4:]

    @property
    def severity(self) -> Severity:
        """自动计算严重性级别"""
        # 解析余额
        balance_value = 0.0
        if self.balance:
            import re
            match = re.search(r'\$?([\d,]+(?:\.\d+)?)', self.balance)
            if match:
                balance_value = float(match.group(1).replace(',', ''))

        # Critical: 高端模型 + 高余额
        if self.model_tier in ['GPT-4', 'GPT-4-Turbo', 'GPT-4o', 'Claude-3-Opus', 'Claude-3.5-Sonnet']:
            if balance_value >= 100 or 'unlimited' in self.balance.lower():
                return Severity.CRITICAL
            return Severity.HIGH

        # High: 高端模型或有余额
        if balance_value >= 10 or self.is_high_value:
            return Severity.HIGH

        # Medium: 普通有效 Key
        if self.model_tier and 'quota' not in self.balance.lower():
            return Severity.MEDIUM

        # Low: 配额耗尽
        return Severity.LOW


# ============================================================================
#                              通知渠道基类
# ============================================================================

class NotificationChannel(ABC):
    """通知渠道抽象基类"""

    def __init__(self, name: str, enabled: bool = True):
        self.name = name
        self.enabled = enabled
        self.min_severity = Severity.LOW  # 最低通知级别

    @abstractmethod
    async def send(self, key_info: KeyInfo, message: str) -> bool:
        """发送通知"""
        pass

    @abstractmethod
    async def send_report(self, title: str, content: str) -> bool:
        """发送汇总报告"""
        pass

    def should_notify(self, severity: Severity) -> bool:
        """是否应该通知此级别"""
        severity_order = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
        return severity_order.index(severity) >= severity_order.index(self.min_severity)


# ============================================================================
#                              Discord 通知
# ============================================================================

class DiscordChannel(NotificationChannel):
    """Discord Webhook 通知"""

    def __init__(self, webhook_url: str, enabled: bool = True):
        super().__init__("Discord", enabled)
        self.webhook_url = webhook_url

    async def send(self, key_info: KeyInfo, message: str = "") -> bool:
        if not self.enabled or not self.webhook_url:
            return False

        severity = key_info.severity

        # Discord Embed 格式
        embed = {
            "title": f"{severity.emoji} 发现 {key_info.platform.upper()} Key!",
            "color": severity.color,
            "fields": [
                {"name": "平台", "value": key_info.platform.upper(), "inline": True},
                {"name": "级别", "value": severity.value.upper(), "inline": True},
                {"name": "Key", "value": f"`{key_info.masked_key}`", "inline": False},
            ],
            "timestamp": key_info.found_time.isoformat(),
            "footer": {"text": "GitHub Secret Scanner Pro"}
        }

        # 可选字段
        if key_info.model_tier:
            embed["fields"].append({"name": "模型", "value": key_info.model_tier, "inline": True})
        if key_info.balance:
            embed["fields"].append({"name": "余额/状态", "value": key_info.balance, "inline": True})
        if key_info.rpm:
            embed["fields"].append({"name": "RPM", "value": str(key_info.rpm), "inline": True})
        if key_info.base_url:
            embed["fields"].append({"name": "Base URL", "value": key_info.base_url, "inline": False})
        if key_info.source_url:
            embed["fields"].append({"name": "来源", "value": f"[GitHub Link]({key_info.source_url})", "inline": False})

        payload = {"embeds": [embed]}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    success = resp.status in [200, 204]
                    if not success:
                        logger.warning(f"Discord 通知失败: {resp.status}")
                    return success
        except Exception as e:
            logger.error(f"Discord 通知异常: {e}")
            return False

    async def send_report(self, title: str, content: str) -> bool:
        if not self.enabled or not self.webhook_url:
            return False

        embed = {
            "title": f"📊 {title}",
            "description": content[:4096],  # Discord 限制
            "color": Severity.INFO.color,
            "timestamp": datetime.now().isoformat(),
            "footer": {"text": "GitHub Secret Scanner Pro - Daily Report"}
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json={"embeds": [embed]},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    return resp.status in [200, 204]
        except Exception as e:
            logger.error(f"Discord 报告发送异常: {e}")
            return False


# ============================================================================
#                              Slack 通知
# ============================================================================

class SlackChannel(NotificationChannel):
    """Slack Webhook 通知"""

    def __init__(self, webhook_url: str, enabled: bool = True):
        super().__init__("Slack", enabled)
        self.webhook_url = webhook_url

    async def send(self, key_info: KeyInfo, message: str = "") -> bool:
        if not self.enabled or not self.webhook_url:
            return False

        severity = key_info.severity

        # Slack Block Kit 格式
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"{severity.emoji} 发现 {key_info.platform.upper()} Key!"}
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*平台:*\n{key_info.platform.upper()}"},
                    {"type": "mrkdwn", "text": f"*级别:*\n{severity.value.upper()}"},
                    {"type": "mrkdwn", "text": f"*Key:*\n`{key_info.masked_key}`"},
                ]
            }
        ]

        # 添加详细信息
        details = []
        if key_info.model_tier:
            details.append(f"*模型:* {key_info.model_tier}")
        if key_info.balance:
            details.append(f"*余额:* {key_info.balance}")
        if key_info.base_url:
            details.append(f"*Base URL:* {key_info.base_url}")

        if details:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": "\n".join(details)}
            })

        if key_info.source_url:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"<{key_info.source_url}|查看来源>"}
            })

        blocks.append({"type": "divider"})
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"GitHub Secret Scanner Pro | {key_info.found_time.strftime('%Y-%m-%d %H:%M:%S')}"}]
        })

        payload = {"blocks": blocks}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    success = resp.status == 200
                    if not success:
                        text = await resp.text()
                        logger.warning(f"Slack 通知失败: {resp.status} - {text}")
                    return success
        except Exception as e:
            logger.error(f"Slack 通知异常: {e}")
            return False

    async def send_report(self, title: str, content: str) -> bool:
        if not self.enabled or not self.webhook_url:
            return False

        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": f"📊 {title}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": content[:3000]}},
            {"type": "divider"},
            {"type": "context", "elements": [{"type": "mrkdwn", "text": f"Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}]}
        ]

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json={"blocks": blocks}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    return resp.status == 200
        except Exception as e:
            logger.error(f"Slack 报告发送异常: {e}")
            return False


# ============================================================================
#                              Telegram 通知
# ============================================================================

class TelegramChannel(NotificationChannel):
    """Telegram Bot 通知"""

    def __init__(self, bot_token: str, chat_id: str, enabled: bool = True):
        super().__init__("Telegram", enabled)
        self.bot_token = bot_token
        self.chat_id = chat_id

    async def send(self, key_info: KeyInfo, message: str = "") -> bool:
        if not self.enabled or not self.bot_token or not self.chat_id:
            return False

        severity = key_info.severity

        # Telegram Markdown 格式
        text = f"""{severity.emoji} *发现 {key_info.platform.upper()} Key\\!*

*平台:* `{key_info.platform}`
*级别:* `{severity.value.upper()}`
*Key:* `{key_info.masked_key}`"""

        if key_info.model_tier:
            text += f"\n*模型:* `{key_info.model_tier}`"
        if key_info.balance:
            # 转义 Markdown 特殊字符
            balance_escaped = key_info.balance.replace('.', '\\.').replace('-', '\\-').replace('$', '\\$')
            text += f"\n*余额:* `{balance_escaped}`"
        if key_info.rpm:
            text += f"\n*RPM:* `{key_info.rpm}`"
        if key_info.base_url:
            text += f"\n*Base URL:* `{key_info.base_url}`"
        if key_info.source_url:
            text += f"\n\n[查看来源]({key_info.source_url})"

        text += f"\n\n_GitHub Secret Scanner Pro_"

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": True
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        # 如果 Markdown 解析失败，尝试纯文本
                        payload["parse_mode"] = None
                        payload["text"] = text.replace('*', '').replace('`', '').replace('\\', '')
                        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp2:
                            return resp2.status == 200
                    return True
        except Exception as e:
            logger.error(f"Telegram 通知异常: {e}")
            return False

    async def send_report(self, title: str, content: str) -> bool:
        if not self.enabled or not self.bot_token or not self.chat_id:
            return False

        text = f"📊 *{title}*\n\n{content[:4000]}"
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json={"chat_id": self.chat_id, "text": text}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    return resp.status == 200
        except Exception as e:
            logger.error(f"Telegram 报告发送异常: {e}")
            return False


# ============================================================================
#                              飞书通知
# ============================================================================

class FeishuChannel(NotificationChannel):
    """飞书机器人通知"""

    def __init__(self, webhook_url: str, enabled: bool = True):
        super().__init__("Feishu", enabled)
        self.webhook_url = webhook_url

    async def send(self, key_info: KeyInfo, message: str = "") -> bool:
        if not self.enabled or not self.webhook_url:
            return False

        severity = key_info.severity

        # 飞书卡片消息
        card = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": f"{severity.emoji} 发现 {key_info.platform.upper()} Key!"},
                    "template": "red" if severity in [Severity.CRITICAL, Severity.HIGH] else "green"
                },
                "elements": [
                    {
                        "tag": "div",
                        "fields": [
                            {"is_short": True, "text": {"tag": "lark_md", "content": f"**平台**\n{key_info.platform.upper()}"}},
                            {"is_short": True, "text": {"tag": "lark_md", "content": f"**级别**\n{severity.value.upper()}"}},
                            {"is_short": False, "text": {"tag": "lark_md", "content": f"**Key**\n`{key_info.masked_key}`"}},
                        ]
                    }
                ]
            }
        }

        # 添加可选字段
        extra_fields = []
        if key_info.model_tier:
            extra_fields.append({"is_short": True, "text": {"tag": "lark_md", "content": f"**模型**\n{key_info.model_tier}"}})
        if key_info.balance:
            extra_fields.append({"is_short": True, "text": {"tag": "lark_md", "content": f"**余额**\n{key_info.balance}"}})

        if extra_fields:
            card["card"]["elements"].append({"tag": "div", "fields": extra_fields})

        if key_info.source_url:
            card["card"]["elements"].append({
                "tag": "action",
                "actions": [{"tag": "button", "text": {"tag": "plain_text", "content": "查看来源"}, "url": key_info.source_url, "type": "primary"}]
            })

        card["card"]["elements"].append({"tag": "hr"})
        card["card"]["elements"].append({
            "tag": "note",
            "elements": [{"tag": "plain_text", "content": f"GitHub Secret Scanner Pro | {key_info.found_time.strftime('%Y-%m-%d %H:%M:%S')}"}]
        })

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=card, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    return resp.status == 200
        except Exception as e:
            logger.error(f"飞书通知异常: {e}")
            return False

    async def send_report(self, title: str, content: str) -> bool:
        if not self.enabled or not self.webhook_url:
            return False

        card = {
            "msg_type": "interactive",
            "card": {
                "header": {"title": {"tag": "plain_text", "content": f"📊 {title}"}, "template": "blue"},
                "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": content[:2000]}}]
            }
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=card, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    return resp.status == 200
        except Exception as e:
            logger.error(f"飞书报告发送异常: {e}")
            return False


# ============================================================================
#                              钉钉通知
# ============================================================================

class DingtalkChannel(NotificationChannel):
    """钉钉机器人通知"""

    def __init__(self, webhook_url: str, secret: str = "", enabled: bool = True):
        super().__init__("Dingtalk", enabled)
        self.webhook_url = webhook_url
        self.secret = secret  # 加签密钥 (可选)

    def _get_signed_url(self) -> str:
        """获取加签后的 URL"""
        if not self.secret:
            return self.webhook_url

        import hmac
        import base64
        import urllib.parse

        timestamp = str(round(datetime.now().timestamp() * 1000))
        secret_enc = self.secret.encode('utf-8')
        string_to_sign = f'{timestamp}\n{self.secret}'
        string_to_sign_enc = string_to_sign.encode('utf-8')
        hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod='sha256').digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))

        return f"{self.webhook_url}&timestamp={timestamp}&sign={sign}"

    async def send(self, key_info: KeyInfo, message: str = "") -> bool:
        if not self.enabled or not self.webhook_url:
            return False

        severity = key_info.severity

        # 钉钉 Markdown 格式
        text = f"""### {severity.emoji} 发现 {key_info.platform.upper()} Key!

- **平台:** {key_info.platform.upper()}
- **级别:** {severity.value.upper()}
- **Key:** `{key_info.masked_key}`"""

        if key_info.model_tier:
            text += f"\n- **模型:** {key_info.model_tier}"
        if key_info.balance:
            text += f"\n- **余额:** {key_info.balance}"
        if key_info.rpm:
            text += f"\n- **RPM:** {key_info.rpm}"
        if key_info.base_url:
            text += f"\n- **Base URL:** {key_info.base_url}"
        if key_info.source_url:
            text += f"\n\n[查看来源]({key_info.source_url})"

        text += f"\n\n---\n*GitHub Secret Scanner Pro | {key_info.found_time.strftime('%H:%M:%S')}*"

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": f"发现 {key_info.platform.upper()} Key!",
                "text": text
            }
        }

        try:
            url = self._get_signed_url()
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    result = await resp.json()
                    success = result.get("errcode") == 0
                    if not success:
                        logger.warning(f"钉钉通知失败: {result}")
                    return success
        except Exception as e:
            logger.error(f"钉钉通知异常: {e}")
            return False

    async def send_report(self, title: str, content: str) -> bool:
        if not self.enabled or not self.webhook_url:
            return False

        payload = {
            "msgtype": "markdown",
            "markdown": {"title": title, "text": f"### 📊 {title}\n\n{content[:2000]}"}
        }

        try:
            url = self._get_signed_url()
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    result = await resp.json()
                    return result.get("errcode") == 0
        except Exception as e:
            logger.error(f"钉钉报告发送异常: {e}")
            return False


# ============================================================================
#                              Server酱 (微信) 通知
# ============================================================================

class ServerChanChannel(NotificationChannel):
    """Server酱 (微信推送)"""

    def __init__(self, send_key: str, enabled: bool = True):
        super().__init__("ServerChan", enabled)
        self.send_key = send_key

    async def send(self, key_info: KeyInfo, message: str = "") -> bool:
        if not self.enabled or not self.send_key:
            return False

        severity = key_info.severity
        title = f"{severity.emoji} 发现 {key_info.platform.upper()} Key!"

        content = f"""## {title}

| 字段 | 值 |
|------|-----|
| 平台 | {key_info.platform.upper()} |
| 级别 | {severity.value.upper()} |
| Key | `{key_info.masked_key}` |"""

        if key_info.model_tier:
            content += f"\n| 模型 | {key_info.model_tier} |"
        if key_info.balance:
            content += f"\n| 余额 | {key_info.balance} |"
        if key_info.source_url:
            content += f"\n\n[查看来源]({key_info.source_url})"

        url = f"https://sctapi.ftqq.com/{self.send_key}.send"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data={"title": title, "desp": content}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    result = await resp.json()
                    return result.get("code") == 0
        except Exception as e:
            logger.error(f"Server酱通知异常: {e}")
            return False

    async def send_report(self, title: str, content: str) -> bool:
        if not self.enabled or not self.send_key:
            return False

        url = f"https://sctapi.ftqq.com/{self.send_key}.send"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data={"title": f"📊 {title}", "desp": content[:5000]}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    result = await resp.json()
                    return result.get("code") == 0
        except Exception as e:
            logger.error(f"Server酱报告发送异常: {e}")
            return False


# ============================================================================
#                              Bark (iOS) 通知
# ============================================================================

class BarkChannel(NotificationChannel):
    """Bark iOS 推送"""

    def __init__(self, server_url: str, device_key: str, enabled: bool = True):
        super().__init__("Bark", enabled)
        self.server_url = server_url.rstrip('/')
        self.device_key = device_key

    async def send(self, key_info: KeyInfo, message: str = "") -> bool:
        if not self.enabled or not self.server_url or not self.device_key:
            return False

        severity = key_info.severity
        title = f"{severity.emoji} {key_info.platform.upper()} Key"
        body = f"级别: {severity.value.upper()}\nKey: {key_info.masked_key}"

        if key_info.model_tier:
            body += f"\n模型: {key_info.model_tier}"
        if key_info.balance:
            body += f"\n余额: {key_info.balance}"

        # Bark API
        url = f"{self.server_url}/{self.device_key}/{title}/{body}"
        params = {"sound": "alarm" if severity in [Severity.CRITICAL, Severity.HIGH] else "default"}

        if key_info.source_url:
            params["url"] = key_info.source_url

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    result = await resp.json()
                    return result.get("code") == 200
        except Exception as e:
            logger.error(f"Bark 通知异常: {e}")
            return False

    async def send_report(self, title: str, content: str) -> bool:
        if not self.enabled or not self.server_url or not self.device_key:
            return False

        url = f"{self.server_url}/{self.device_key}/{title}/{content[:200]}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    result = await resp.json()
                    return result.get("code") == 200
        except Exception as e:
            logger.error(f"Bark 报告发送异常: {e}")
            return False


# ============================================================================
#                              文件通知 (始终启用)
# ============================================================================

class FileChannel(NotificationChannel):
    """文件记录通知"""

    def __init__(self, output_path: str = None, enabled: bool = True):
        super().__init__("File", enabled)
        self.output_path = Path(output_path or os.path.expanduser("~/Desktop/found_keys.txt"))
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

    async def send(self, key_info: KeyInfo, message: str = "") -> bool:
        if not self.enabled:
            return False

        from findings_feed import disclosure_notice

        content = disclosure_notice(
            key_info.platform, key_info.masked_key, key_info.source_url,
        ) + "\n"

        try:
            with open(self.output_path, "a", encoding="utf-8") as f:
                f.write(content)
            return True
        except Exception as e:
            logger.error(f"文件写入异常: {e}")
            return False

    async def send_report(self, title: str, content: str) -> bool:
        report_path = self.output_path.parent / f"report_{datetime.now().strftime('%Y%m%d')}.txt"
        try:
            with open(report_path, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*70}\n{title}\n{'='*70}\n{content}\n")
            return True
        except Exception as e:
            logger.error(f"报告文件写入异常: {e}")
            return False


# ============================================================================
#                              声音通知 (仅 Windows)
# ============================================================================

class SoundChannel(NotificationChannel):
    """声音提醒通知"""

    def __init__(self, enabled: bool = True):
        super().__init__("Sound", enabled)

    async def send(self, key_info: KeyInfo, message: str = "") -> bool:
        if not self.enabled:
            return False

        try:
            import platform
            if platform.system() == "Windows":
                import winsound
                severity = key_info.severity

                if severity == Severity.CRITICAL:
                    # 紧急警报音
                    for _ in range(3):
                        winsound.Beep(2000, 200)
                        winsound.Beep(1500, 200)
                elif severity == Severity.HIGH:
                    winsound.Beep(1500, 300)
                    winsound.Beep(2000, 300)
                else:
                    winsound.Beep(1000, 200)
                    winsound.Beep(1200, 200)
                return True
            else:
                # Linux/Mac: 使用终端响铃
                print('\a', end='', flush=True)
                return True
        except Exception:
            return False

    async def send_report(self, title: str, content: str) -> bool:
        # 报告不播放声音
        return True


# ============================================================================
#                              统一通知管理器
# ============================================================================

class NotifierV2:
    """
    统一通知管理器 v2.0

    特性:
    - 多渠道并发通知
    - 严重性分级过滤
    - 通知去重
    - 静默时段
    - 速率限制
    - 每日汇总
    """

    def __init__(self, config_path: str = None):
        self.channels: List[NotificationChannel] = []
        self.notified_keys: Set[str] = set()  # 已通知的 Key (去重)
        self.notification_history: deque = deque(maxlen=1000)  # 通知历史

        # 速率限制
        self.rate_limit_window = 60  # 秒
        self.rate_limit_max = 30     # 每分钟最大通知数
        self.recent_notifications: deque = deque(maxlen=100)

        # 静默时段 (默认关闭)
        self.quiet_hours_enabled = False
        self.quiet_hours_start = time(23, 0)  # 23:00
        self.quiet_hours_end = time(7, 0)     # 07:00

        # 统计数据 (用于每日报告)
        self.daily_stats = {
            "total_found": 0,
            "by_severity": {s.value: 0 for s in Severity},
            "by_platform": {},
            "high_value_keys": []
        }

        # 加载配置
        if config_path and Path(config_path).exists():
            self.load_config(config_path)

    def add_channel(self, channel: NotificationChannel):
        """添加通知渠道"""
        self.channels.append(channel)
        logger.info(f"已添加通知渠道: {channel.name} (enabled={channel.enabled})")

    def load_config(self, config_path: str):
        """从 YAML 配置文件加载"""
        try:
            import yaml
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            # Discord
            if discord_cfg := config.get('discord'):
                self.add_channel(DiscordChannel(
                    webhook_url=discord_cfg.get('webhook_url', ''),
                    enabled=discord_cfg.get('enabled', True)
                ))

            # Slack
            if slack_cfg := config.get('slack'):
                self.add_channel(SlackChannel(
                    webhook_url=slack_cfg.get('webhook_url', ''),
                    enabled=slack_cfg.get('enabled', True)
                ))

            # Telegram
            if tg_cfg := config.get('telegram'):
                self.add_channel(TelegramChannel(
                    bot_token=tg_cfg.get('bot_token', ''),
                    chat_id=tg_cfg.get('chat_id', ''),
                    enabled=tg_cfg.get('enabled', True)
                ))

            # 飞书
            if feishu_cfg := config.get('feishu'):
                self.add_channel(FeishuChannel(
                    webhook_url=feishu_cfg.get('webhook_url', ''),
                    enabled=feishu_cfg.get('enabled', True)
                ))

            # 钉钉
            if dingtalk_cfg := config.get('dingtalk'):
                self.add_channel(DingtalkChannel(
                    webhook_url=dingtalk_cfg.get('webhook_url', ''),
                    secret=dingtalk_cfg.get('secret', ''),
                    enabled=dingtalk_cfg.get('enabled', True)
                ))

            # Server酱
            if serverchan_cfg := config.get('serverchan'):
                self.add_channel(ServerChanChannel(
                    send_key=serverchan_cfg.get('send_key', ''),
                    enabled=serverchan_cfg.get('enabled', True)
                ))

            # Bark
            if bark_cfg := config.get('bark'):
                self.add_channel(BarkChannel(
                    server_url=bark_cfg.get('server_url', 'https://api.day.app'),
                    device_key=bark_cfg.get('device_key', ''),
                    enabled=bark_cfg.get('enabled', True)
                ))

            # 文件
            if file_cfg := config.get('file'):
                self.add_channel(FileChannel(
                    output_path=file_cfg.get('output_path'),
                    enabled=file_cfg.get('enabled', True)
                ))

            # 声音
            if sound_cfg := config.get('sound'):
                self.add_channel(SoundChannel(enabled=sound_cfg.get('enabled', True)))

            # 静默时段
            if quiet_cfg := config.get('quiet_hours'):
                self.quiet_hours_enabled = quiet_cfg.get('enabled', False)
                if start := quiet_cfg.get('start'):
                    h, m = map(int, start.split(':'))
                    self.quiet_hours_start = time(h, m)
                if end := quiet_cfg.get('end'):
                    h, m = map(int, end.split(':'))
                    self.quiet_hours_end = time(h, m)

            logger.info(f"已加载通知配置: {config_path}")

        except Exception as e:
            logger.error(f"加载通知配置失败: {e}")

    def _is_quiet_hours(self) -> bool:
        """检查是否在静默时段"""
        if not self.quiet_hours_enabled:
            return False

        now = datetime.now().time()
        start = self.quiet_hours_start
        end = self.quiet_hours_end

        if start <= end:
            return start <= now <= end
        else:
            # 跨午夜的情况
            return now >= start or now <= end

    def _check_rate_limit(self) -> bool:
        """检查速率限制"""
        now = datetime.now()
        cutoff = now - timedelta(seconds=self.rate_limit_window)

        # 清理过期记录
        while self.recent_notifications and self.recent_notifications[0] < cutoff:
            self.recent_notifications.popleft()

        return len(self.recent_notifications) < self.rate_limit_max

    def _get_key_hash(self, key_info: KeyInfo) -> str:
        """生成 Key 的哈希 (用于去重)"""
        return hashlib.md5(f"{key_info.platform}:{key_info.api_key}".encode()).hexdigest()

    async def notify(self, key_info: KeyInfo, force: bool = False) -> Dict[str, bool]:
        """
        发送通知到所有渠道

        Args:
            key_info: 密钥信息
            force: 是否强制发送 (忽略去重和静默时段)

        Returns:
            各渠道发送结果
        """
        results = {}
        severity = key_info.severity
        key_hash = self._get_key_hash(key_info)

        # 更新统计
        self.daily_stats["total_found"] += 1
        self.daily_stats["by_severity"][severity.value] += 1
        self.daily_stats["by_platform"][key_info.platform] = \
            self.daily_stats["by_platform"].get(key_info.platform, 0) + 1

        if key_info.is_high_value or severity in [Severity.CRITICAL, Severity.HIGH]:
            self.daily_stats["high_value_keys"].append({
                "platform": key_info.platform,
                "key": key_info.masked_key,
                "model": key_info.model_tier,
                "time": key_info.found_time.isoformat()
            })

        # 去重检查
        if not force and key_hash in self.notified_keys:
            logger.debug(f"跳过重复通知: {key_info.masked_key}")
            return {"skipped": True, "reason": "duplicate"}

        # 静默时段检查 (Critical 级别除外)
        if not force and severity != Severity.CRITICAL and self._is_quiet_hours():
            logger.debug(f"静默时段，跳过通知: {key_info.masked_key}")
            return {"skipped": True, "reason": "quiet_hours"}

        # 速率限制检查 (Critical 级别除外)
        if not force and severity != Severity.CRITICAL and not self._check_rate_limit():
            logger.warning(f"速率限制，跳过通知: {key_info.masked_key}")
            return {"skipped": True, "reason": "rate_limit"}

        # 标记为已通知
        self.notified_keys.add(key_hash)
        self.recent_notifications.append(datetime.now())

        # 并发发送到所有渠道
        tasks = []
        for channel in self.channels:
            if channel.enabled and channel.should_notify(severity):
                tasks.append(self._send_to_channel(channel, key_info))

        if tasks:
            channel_results = await asyncio.gather(*tasks, return_exceptions=True)
            for channel, result in zip([c for c in self.channels if c.enabled], channel_results):
                if isinstance(result, Exception):
                    results[channel.name] = False
                    logger.error(f"{channel.name} 通知异常: {result}")
                else:
                    results[channel.name] = result

        # 记录历史
        self.notification_history.append({
            "time": datetime.now().isoformat(),
            "key": key_info.masked_key,
            "platform": key_info.platform,
            "severity": severity.value,
            "results": results
        })

        success_count = sum(1 for v in results.values() if v is True)
        logger.info(f"通知发送完成: {key_info.platform} {key_info.masked_key} -> {success_count}/{len(results)} 成功")

        return results

    async def _send_to_channel(self, channel: NotificationChannel, key_info: KeyInfo) -> bool:
        """只发送平台、脱敏预览和位置。渠道拿不到完整密钥和余额。"""
        from findings_feed import disclosure_notice

        preview = key_info.masked_key
        text = disclosure_notice(key_info.platform, preview, key_info.source_url)
        if key_info.api_key and key_info.api_key in text:
            text = text.replace(key_info.api_key, preview)
        try:
            if isinstance(channel, SoundChannel):
                safe = KeyInfo(
                    platform=key_info.platform,
                    api_key=preview,
                    source_url=key_info.source_url,
                    found_time=key_info.found_time,
                )
                return await channel.send(safe, "")
            return await channel.send_report("泄露处置", text)
        except Exception as e:
            logger.error(f"{channel.name} 发送失败: {e}")
            return False

    async def send_daily_report(self):
        """发送每日汇总报告"""
        stats = self.daily_stats

        title = f"每日扫描报告 - {datetime.now().strftime('%Y-%m-%d')}"

        content = f"""## 📊 扫描统计

- **总发现**: {stats['total_found']} 个 Key
- **Critical**: {stats['by_severity']['critical']} 个
- **High**: {stats['by_severity']['high']} 个
- **Medium**: {stats['by_severity']['medium']} 个
- **Low**: {stats['by_severity']['low']} 个

### 平台分布
"""
        for platform, count in sorted(stats['by_platform'].items(), key=lambda x: -x[1]):
            content += f"- {platform}: {count} 个\n"

        if stats['high_value_keys']:
            content += "\n### 高价值 Key\n"
            for key in stats['high_value_keys'][-10:]:  # 最多显示 10 个
                content += f"- {key['platform']} `{key['key']}` ({key['model']})\n"

        # 发送到所有渠道
        results = {}
        for channel in self.channels:
            if channel.enabled:
                try:
                    results[channel.name] = await channel.send_report(title, content)
                except Exception as e:
                    logger.error(f"{channel.name} 报告发送失败: {e}")
                    results[channel.name] = False

        # 重置统计
        self.daily_stats = {
            "total_found": 0,
            "by_severity": {s.value: 0 for s in Severity},
            "by_platform": {},
            "high_value_keys": []
        }

        return results

    def get_stats(self) -> dict:
        """获取当前统计"""
        return {
            "daily_stats": self.daily_stats,
            "notified_count": len(self.notified_keys),
            "channels": [{"name": c.name, "enabled": c.enabled} for c in self.channels],
            "recent_notifications": list(self.notification_history)[-20:]
        }


# ============================================================================
#                              便捷初始化函数
# ============================================================================

def create_notifier_from_env() -> NotifierV2:
    """从环境变量创建通知器"""
    notifier = NotifierV2()

    # Discord
    if webhook := os.getenv('DISCORD_WEBHOOK'):
        notifier.add_channel(DiscordChannel(webhook))

    # Slack
    if webhook := os.getenv('SLACK_WEBHOOK'):
        notifier.add_channel(SlackChannel(webhook))

    # Telegram
    if token := os.getenv('TELEGRAM_BOT_TOKEN'):
        chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
        notifier.add_channel(TelegramChannel(token, chat_id))

    # 飞书
    if webhook := os.getenv('FEISHU_WEBHOOK'):
        notifier.add_channel(FeishuChannel(webhook))

    # 钉钉
    if webhook := os.getenv('DINGTALK_WEBHOOK'):
        secret = os.getenv('DINGTALK_SECRET', '')
        notifier.add_channel(DingtalkChannel(webhook, secret))

    # Server酱
    if key := os.getenv('SERVERCHAN_KEY'):
        notifier.add_channel(ServerChanChannel(key))

    # Bark
    if device_key := os.getenv('BARK_DEVICE_KEY'):
        server = os.getenv('BARK_SERVER', 'https://api.day.app')
        notifier.add_channel(BarkChannel(server, device_key))

    # 默认启用文件和声音
    notifier.add_channel(FileChannel())
    notifier.add_channel(SoundChannel())

    return notifier


# ============================================================================
#                              全局实例
# ============================================================================

# 默认通知器 (可以替换为配置加载的实例)
notifier_v2: Optional[NotifierV2] = None


def get_notifier() -> NotifierV2:
    """获取全局通知器实例"""
    global notifier_v2
    if notifier_v2 is None:
        notifier_v2 = create_notifier_from_env()
    return notifier_v2


def init_notifier(config_path: str = None) -> NotifierV2:
    """初始化全局通知器"""
    global notifier_v2

    if config_path and Path(config_path).exists():
        notifier_v2 = NotifierV2(config_path)
    else:
        notifier_v2 = create_notifier_from_env()

    return notifier_v2
