"""
扩展验证器模块 - 参考 KeyHacks 添加 30+ 平台验证
=====================================================

支持的平台分类：
1. 通信/消息平台: Slack, Discord, Telegram, Twilio, SendGrid, Mailgun, Mailchimp
2. 云服务商: AWS, GCP, Azure, DigitalOcean, Heroku, Cloudflare, Vercel
3. 开发工具: GitHub, GitLab, Bitbucket, CircleCI, Travis CI, NPM, Docker Hub
4. 监控/APM: Datadog, Sentry, New Relic, PagerDuty
5. 协作工具: Notion, Linear, Asana, Airtable, Jira, Confluence
6. 分析平台: Segment, Mixpanel, Amplitude, Algolia
7. 客服/CRM: Zendesk, Intercom, Freshdesk
8. 地图服务: Mapbox, Google Maps, HERE

参考文档: https://github.com/streaak/keyhacks
"""

import asyncio
import hmac
import hashlib
import base64
import time
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum

import aiohttp
from aiohttp import ClientTimeout
from loguru import logger


# ============================================================================
#                              配置常量
# ============================================================================

REQUEST_TIMEOUT = ClientTimeout(total=15, connect=10)


# ============================================================================
#                              验证结果
# ============================================================================

class ExtendedKeyStatus(Enum):
    """扩展的 Key 状态"""
    VALID = "valid"                    # 有效
    INVALID = "invalid"                # 无效
    QUOTA_EXCEEDED = "quota_exceeded"  # 配额耗尽
    PARTIAL = "partial"                # 部分有效（权限受限）
    CONNECTION_ERROR = "connection_error"  # 连接错误
    UNVERIFIED = "unverified"          # 无法验证


@dataclass
class ExtendedValidationResult:
    """扩展验证结果"""
    status: ExtendedKeyStatus
    message: str
    platform: str = ""
    extra_info: Dict[str, Any] = None
    is_high_value: bool = False

    def __post_init__(self):
        if self.extra_info is None:
            self.extra_info = {}


# ============================================================================
#                              扩展验证器
# ============================================================================

class ExtendedValidator:
    """
    扩展验证器 - 支持 30+ 平台

    参考: https://github.com/streaak/keyhacks
    """

    def __init__(self, proxy_url: str = None):
        self.proxy_url = proxy_url
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=REQUEST_TIMEOUT)
        return self._session

    async def close(self):
        """关闭 session"""
        if self._session and not self._session.closed:
            await self._session.close()

    # ========================================================================
    #                       通信/消息平台
    # ========================================================================

    async def validate_slack_token(self, token: str) -> ExtendedValidationResult:
        """
        验证 Slack Token

        Token 类型:
        - xoxb-* : Bot Token
        - xoxp-* : User Token
        - xoxa-* : App Token
        - xoxr-* : Refresh Token
        """
        session = await self._get_session()
        headers = {"Authorization": f"Bearer {token}"}

        try:
            async with session.get(
                "https://slack.com/api/auth.test",
                headers=headers,
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("ok"):
                        team = data.get("team", "unknown")
                        user = data.get("user", "unknown")
                        return ExtendedValidationResult(
                            ExtendedKeyStatus.VALID,
                            f"Slack 有效 @{user} in {team}",
                            "slack",
                            {"team": team, "user": user},
                            is_high_value=True
                        )
                    else:
                        error = data.get("error", "invalid_auth")
                        if error == "token_expired":
                            return ExtendedValidationResult(
                                ExtendedKeyStatus.QUOTA_EXCEEDED,
                                "Token 已过期",
                                "slack"
                            )
                return ExtendedValidationResult(
                    ExtendedKeyStatus.INVALID,
                    "Slack 认证失败",
                    "slack"
                )
        except Exception as e:
            logger.debug(f"Slack 验证异常: {e}")
            return ExtendedValidationResult(
                ExtendedKeyStatus.CONNECTION_ERROR,
                f"连接失败: {str(e)[:30]}",
                "slack"
            )

    async def validate_discord_bot_token(self, token: str) -> ExtendedValidationResult:
        """验证 Discord Bot Token"""
        session = await self._get_session()
        headers = {"Authorization": f"Bot {token}"}

        try:
            async with session.get(
                "https://discord.com/api/v10/users/@me",
                headers=headers,
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    username = data.get("username", "unknown")
                    bot_id = data.get("id", "unknown")
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.VALID,
                        f"Discord Bot: {username}#{data.get('discriminator', '0000')}",
                        "discord",
                        {"bot_id": bot_id, "username": username},
                        is_high_value=True
                    )
                elif resp.status == 401:
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.INVALID,
                        "Discord Token 无效",
                        "discord"
                    )
        except Exception as e:
            logger.debug(f"Discord 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.CONNECTION_ERROR,
            "连接失败",
            "discord"
        )

    async def validate_telegram_bot_token(self, token: str) -> ExtendedValidationResult:
        """验证 Telegram Bot Token"""
        session = await self._get_session()

        try:
            async with session.get(
                f"https://api.telegram.org/bot{token}/getMe",
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("ok"):
                        bot_info = data.get("result", {})
                        username = bot_info.get("username", "unknown")
                        return ExtendedValidationResult(
                            ExtendedKeyStatus.VALID,
                            f"Telegram Bot: @{username}",
                            "telegram",
                            {"bot_id": bot_info.get("id"), "username": username},
                            is_high_value=True
                        )
        except Exception as e:
            logger.debug(f"Telegram 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.INVALID,
            "Telegram Token 无效",
            "telegram"
        )

    async def validate_twilio(self, account_sid: str, auth_token: str) -> ExtendedValidationResult:
        """验证 Twilio API 凭证"""
        session = await self._get_session()
        auth = aiohttp.BasicAuth(account_sid, auth_token)

        try:
            async with session.get(
                f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}.json",
                auth=auth,
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    status = data.get("status", "unknown")
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.VALID,
                        f"Twilio 有效 (状态: {status})",
                        "twilio",
                        {"account_status": status},
                        is_high_value=True
                    )
                elif resp.status == 401:
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.INVALID,
                        "Twilio 认证失败",
                        "twilio"
                    )
        except Exception as e:
            logger.debug(f"Twilio 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.CONNECTION_ERROR,
            "连接失败",
            "twilio"
        )

    async def validate_sendgrid(self, api_key: str) -> ExtendedValidationResult:
        """验证 SendGrid API Key"""
        session = await self._get_session()
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            async with session.get(
                "https://api.sendgrid.com/v3/user/profile",
                headers=headers,
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    email = data.get("email", "unknown")
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.VALID,
                        f"SendGrid 有效 ({email})",
                        "sendgrid",
                        {"email": email},
                        is_high_value=True
                    )
                elif resp.status == 401:
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.INVALID,
                        "SendGrid 认证失败",
                        "sendgrid"
                    )
        except Exception as e:
            logger.debug(f"SendGrid 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.CONNECTION_ERROR,
            "连接失败",
            "sendgrid"
        )

    async def validate_mailgun(self, api_key: str) -> ExtendedValidationResult:
        """验证 Mailgun API Key"""
        session = await self._get_session()
        auth = aiohttp.BasicAuth("api", api_key)

        try:
            async with session.get(
                "https://api.mailgun.net/v3/domains",
                auth=auth,
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    domains = data.get("items", [])
                    domain_count = len(domains)
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.VALID,
                        f"Mailgun 有效 ({domain_count} 域名)",
                        "mailgun",
                        {"domain_count": domain_count},
                        is_high_value=domain_count > 0
                    )
                elif resp.status == 401:
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.INVALID,
                        "Mailgun 认证失败",
                        "mailgun"
                    )
        except Exception as e:
            logger.debug(f"Mailgun 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.CONNECTION_ERROR,
            "连接失败",
            "mailgun"
        )

    async def validate_mailchimp(self, api_key: str) -> ExtendedValidationResult:
        """
        验证 Mailchimp API Key

        API Key 格式: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx-usX
        其中 usX 是数据中心标识
        """
        # 从 API Key 提取数据中心
        if "-" in api_key:
            dc = api_key.split("-")[-1]
        else:
            dc = "us1"  # 默认

        session = await self._get_session()
        auth = aiohttp.BasicAuth("anystring", api_key)

        try:
            async with session.get(
                f"https://{dc}.api.mailchimp.com/3.0/",
                auth=auth,
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    account_name = data.get("account_name", "unknown")
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.VALID,
                        f"Mailchimp 有效 ({account_name})",
                        "mailchimp",
                        {"account_name": account_name, "dc": dc},
                        is_high_value=True
                    )
                elif resp.status == 401:
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.INVALID,
                        "Mailchimp 认证失败",
                        "mailchimp"
                    )
        except Exception as e:
            logger.debug(f"Mailchimp 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.CONNECTION_ERROR,
            "连接失败",
            "mailchimp"
        )

    # ========================================================================
    #                       云服务商
    # ========================================================================

    async def validate_digitalocean(self, token: str) -> ExtendedValidationResult:
        """验证 DigitalOcean API Token"""
        session = await self._get_session()
        headers = {"Authorization": f"Bearer {token}"}

        try:
            async with session.get(
                "https://api.digitalocean.com/v2/account",
                headers=headers,
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    account = data.get("account", {})
                    email = account.get("email", "unknown")
                    droplet_limit = account.get("droplet_limit", 0)
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.VALID,
                        f"DO 有效 ({email}, 限额: {droplet_limit})",
                        "digitalocean",
                        {"email": email, "droplet_limit": droplet_limit},
                        is_high_value=True
                    )
                elif resp.status == 401:
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.INVALID,
                        "DigitalOcean 认证失败",
                        "digitalocean"
                    )
        except Exception as e:
            logger.debug(f"DigitalOcean 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.CONNECTION_ERROR,
            "连接失败",
            "digitalocean"
        )

    async def validate_heroku(self, api_key: str) -> ExtendedValidationResult:
        """验证 Heroku API Key"""
        session = await self._get_session()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/vnd.heroku+json; version=3"
        }

        try:
            async with session.get(
                "https://api.heroku.com/account",
                headers=headers,
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    email = data.get("email", "unknown")
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.VALID,
                        f"Heroku 有效 ({email})",
                        "heroku",
                        {"email": email},
                        is_high_value=True
                    )
                elif resp.status == 401:
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.INVALID,
                        "Heroku 认证失败",
                        "heroku"
                    )
        except Exception as e:
            logger.debug(f"Heroku 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.CONNECTION_ERROR,
            "连接失败",
            "heroku"
        )

    async def validate_cloudflare(self, api_key: str, email: str = "") -> ExtendedValidationResult:
        """
        验证 Cloudflare API Token / Global API Key

        两种认证方式:
        1. API Token (推荐): Authorization: Bearer <token>
        2. Global API Key: X-Auth-Key + X-Auth-Email
        """
        session = await self._get_session()

        # 尝试 API Token 方式
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            async with session.get(
                "https://api.cloudflare.com/client/v4/user/tokens/verify",
                headers=headers,
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success"):
                        return ExtendedValidationResult(
                            ExtendedKeyStatus.VALID,
                            "Cloudflare API Token 有效",
                            "cloudflare",
                            is_high_value=True
                        )
        except Exception as e:
            logger.debug(f"Cloudflare 验证异常: {e}")

        # 尝试 Global API Key 方式
        if email:
            headers = {
                "X-Auth-Key": api_key,
                "X-Auth-Email": email
            }
            try:
                async with session.get(
                    "https://api.cloudflare.com/client/v4/user",
                    headers=headers,
                    proxy=self.proxy_url
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("success"):
                            return ExtendedValidationResult(
                                ExtendedKeyStatus.VALID,
                                "Cloudflare Global Key 有效",
                                "cloudflare",
                                is_high_value=True
                            )
            except Exception as e:
                logger.debug(f"Cloudflare Global Key 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.INVALID,
            "Cloudflare 认证失败",
            "cloudflare"
        )

    async def validate_vercel(self, token: str) -> ExtendedValidationResult:
        """验证 Vercel API Token"""
        session = await self._get_session()
        headers = {"Authorization": f"Bearer {token}"}

        try:
            async with session.get(
                "https://api.vercel.com/v2/user",
                headers=headers,
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    username = data.get("user", {}).get("username", "unknown")
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.VALID,
                        f"Vercel 有效 (@{username})",
                        "vercel",
                        {"username": username},
                        is_high_value=True
                    )
                elif resp.status == 401:
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.INVALID,
                        "Vercel 认证失败",
                        "vercel"
                    )
        except Exception as e:
            logger.debug(f"Vercel 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.CONNECTION_ERROR,
            "连接失败",
            "vercel"
        )

    # ========================================================================
    #                       开发工具
    # ========================================================================

    async def validate_gitlab_token(self, token: str) -> ExtendedValidationResult:
        """验证 GitLab Personal Access Token"""
        session = await self._get_session()
        headers = {"PRIVATE-TOKEN": token}

        try:
            async with session.get(
                "https://gitlab.com/api/v4/user",
                headers=headers,
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    username = data.get("username", "unknown")
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.VALID,
                        f"GitLab 有效 (@{username})",
                        "gitlab",
                        {"username": username},
                        is_high_value=True
                    )
                elif resp.status == 401:
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.INVALID,
                        "GitLab 认证失败",
                        "gitlab"
                    )
        except Exception as e:
            logger.debug(f"GitLab 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.CONNECTION_ERROR,
            "连接失败",
            "gitlab"
        )

    async def validate_bitbucket(self, username: str, app_password: str) -> ExtendedValidationResult:
        """验证 Bitbucket App Password"""
        session = await self._get_session()
        auth = aiohttp.BasicAuth(username, app_password)

        try:
            async with session.get(
                "https://api.bitbucket.org/2.0/user",
                auth=auth,
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    display_name = data.get("display_name", username)
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.VALID,
                        f"Bitbucket 有效 ({display_name})",
                        "bitbucket",
                        {"username": username},
                        is_high_value=True
                    )
                elif resp.status == 401:
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.INVALID,
                        "Bitbucket 认证失败",
                        "bitbucket"
                    )
        except Exception as e:
            logger.debug(f"Bitbucket 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.CONNECTION_ERROR,
            "连接失败",
            "bitbucket"
        )

    async def validate_circleci(self, token: str) -> ExtendedValidationResult:
        """验证 CircleCI API Token"""
        session = await self._get_session()
        headers = {"Circle-Token": token}

        try:
            async with session.get(
                "https://circleci.com/api/v2/me",
                headers=headers,
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    login = data.get("login", "unknown")
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.VALID,
                        f"CircleCI 有效 ({login})",
                        "circleci",
                        {"login": login},
                        is_high_value=True
                    )
                elif resp.status == 401:
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.INVALID,
                        "CircleCI 认证失败",
                        "circleci"
                    )
        except Exception as e:
            logger.debug(f"CircleCI 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.CONNECTION_ERROR,
            "连接失败",
            "circleci"
        )

    async def validate_travis_ci(self, token: str) -> ExtendedValidationResult:
        """验证 Travis CI API Token"""
        session = await self._get_session()
        headers = {
            "Authorization": f"token {token}",
            "Travis-API-Version": "3"
        }

        try:
            async with session.get(
                "https://api.travis-ci.com/user",
                headers=headers,
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    login = data.get("login", "unknown")
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.VALID,
                        f"Travis CI 有效 ({login})",
                        "travis_ci",
                        {"login": login},
                        is_high_value=True
                    )
                elif resp.status == 401:
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.INVALID,
                        "Travis CI 认证失败",
                        "travis_ci"
                    )
        except Exception as e:
            logger.debug(f"Travis CI 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.CONNECTION_ERROR,
            "连接失败",
            "travis_ci"
        )

    async def validate_npm_token(self, token: str) -> ExtendedValidationResult:
        """验证 NPM Token"""
        session = await self._get_session()
        headers = {"Authorization": f"Bearer {token}"}

        try:
            async with session.get(
                "https://registry.npmjs.org/-/npm/v1/user",
                headers=headers,
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    name = data.get("name", "unknown")
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.VALID,
                        f"NPM 有效 ({name})",
                        "npm",
                        {"name": name},
                        is_high_value=True
                    )
                elif resp.status == 401:
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.INVALID,
                        "NPM 认证失败",
                        "npm"
                    )
        except Exception as e:
            logger.debug(f"NPM 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.CONNECTION_ERROR,
            "连接失败",
            "npm"
        )

    async def validate_docker_hub(self, username: str, password: str) -> ExtendedValidationResult:
        """验证 Docker Hub 凭证"""
        session = await self._get_session()

        try:
            async with session.post(
                "https://hub.docker.com/v2/users/login",
                json={"username": username, "password": password},
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "token" in data:
                        return ExtendedValidationResult(
                            ExtendedKeyStatus.VALID,
                            f"Docker Hub 有效 ({username})",
                            "docker_hub",
                            {"username": username},
                            is_high_value=True
                        )
                elif resp.status == 401:
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.INVALID,
                        "Docker Hub 认证失败",
                        "docker_hub"
                    )
        except Exception as e:
            logger.debug(f"Docker Hub 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.CONNECTION_ERROR,
            "连接失败",
            "docker_hub"
        )

    # ========================================================================
    #                       监控/APM
    # ========================================================================

    async def validate_datadog(self, api_key: str, app_key: str = "") -> ExtendedValidationResult:
        """验证 Datadog API Key"""
        session = await self._get_session()
        headers = {"DD-API-KEY": api_key}
        if app_key:
            headers["DD-APPLICATION-KEY"] = app_key

        try:
            async with session.get(
                "https://api.datadoghq.com/api/v1/validate",
                headers=headers,
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("valid"):
                        return ExtendedValidationResult(
                            ExtendedKeyStatus.VALID,
                            "Datadog API Key 有效",
                            "datadog",
                            is_high_value=True
                        )
                elif resp.status == 403:
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.INVALID,
                        "Datadog 认证失败",
                        "datadog"
                    )
        except Exception as e:
            logger.debug(f"Datadog 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.CONNECTION_ERROR,
            "连接失败",
            "datadog"
        )

    async def validate_sentry(self, auth_token: str) -> ExtendedValidationResult:
        """验证 Sentry Auth Token"""
        session = await self._get_session()
        headers = {"Authorization": f"Bearer {auth_token}"}

        try:
            async with session.get(
                "https://sentry.io/api/0/",
                headers=headers,
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    user = data.get("user", {})
                    username = user.get("username", "unknown")
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.VALID,
                        f"Sentry 有效 ({username})",
                        "sentry",
                        {"username": username},
                        is_high_value=True
                    )
                elif resp.status == 401:
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.INVALID,
                        "Sentry 认证失败",
                        "sentry"
                    )
        except Exception as e:
            logger.debug(f"Sentry 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.CONNECTION_ERROR,
            "连接失败",
            "sentry"
        )

    async def validate_newrelic(self, api_key: str) -> ExtendedValidationResult:
        """验证 New Relic API Key"""
        session = await self._get_session()
        headers = {"Api-Key": api_key}

        try:
            # 使用 GraphQL API
            async with session.post(
                "https://api.newrelic.com/graphql",
                headers=headers,
                json={"query": "{ actor { user { email name } } }"},
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "data" in data and "actor" in data["data"]:
                        user = data["data"]["actor"].get("user", {})
                        name = user.get("name", "unknown")
                        return ExtendedValidationResult(
                            ExtendedKeyStatus.VALID,
                            f"New Relic 有效 ({name})",
                            "newrelic",
                            {"name": name},
                            is_high_value=True
                        )
                elif resp.status == 401:
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.INVALID,
                        "New Relic 认证失败",
                        "newrelic"
                    )
        except Exception as e:
            logger.debug(f"New Relic 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.CONNECTION_ERROR,
            "连接失败",
            "newrelic"
        )

    async def validate_pagerduty(self, api_key: str) -> ExtendedValidationResult:
        """验证 PagerDuty API Key"""
        session = await self._get_session()
        headers = {"Authorization": f"Token token={api_key}"}

        try:
            async with session.get(
                "https://api.pagerduty.com/users/me",
                headers=headers,
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    user = data.get("user", {})
                    name = user.get("name", "unknown")
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.VALID,
                        f"PagerDuty 有效 ({name})",
                        "pagerduty",
                        {"name": name},
                        is_high_value=True
                    )
                elif resp.status == 401:
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.INVALID,
                        "PagerDuty 认证失败",
                        "pagerduty"
                    )
        except Exception as e:
            logger.debug(f"PagerDuty 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.CONNECTION_ERROR,
            "连接失败",
            "pagerduty"
        )

    # ========================================================================
    #                       协作工具
    # ========================================================================

    async def validate_notion(self, token: str) -> ExtendedValidationResult:
        """验证 Notion Integration Token"""
        session = await self._get_session()
        headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": "2022-06-28"
        }

        try:
            async with session.get(
                "https://api.notion.com/v1/users/me",
                headers=headers,
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    name = data.get("name", "unknown")
                    bot_type = data.get("type", "unknown")
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.VALID,
                        f"Notion 有效 ({name}, {bot_type})",
                        "notion",
                        {"name": name, "type": bot_type},
                        is_high_value=True
                    )
                elif resp.status == 401:
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.INVALID,
                        "Notion 认证失败",
                        "notion"
                    )
        except Exception as e:
            logger.debug(f"Notion 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.CONNECTION_ERROR,
            "连接失败",
            "notion"
        )

    async def validate_linear(self, api_key: str) -> ExtendedValidationResult:
        """验证 Linear API Key"""
        session = await self._get_session()
        headers = {"Authorization": api_key}

        try:
            async with session.post(
                "https://api.linear.app/graphql",
                headers=headers,
                json={"query": "{ viewer { id name email } }"},
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "data" in data and "viewer" in data["data"]:
                        viewer = data["data"]["viewer"]
                        name = viewer.get("name", "unknown")
                        return ExtendedValidationResult(
                            ExtendedKeyStatus.VALID,
                            f"Linear 有效 ({name})",
                            "linear",
                            {"name": name},
                            is_high_value=True
                        )
        except Exception as e:
            logger.debug(f"Linear 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.INVALID,
            "Linear 认证失败",
            "linear"
        )

    async def validate_asana(self, token: str) -> ExtendedValidationResult:
        """验证 Asana Personal Access Token"""
        session = await self._get_session()
        headers = {"Authorization": f"Bearer {token}"}

        try:
            async with session.get(
                "https://app.asana.com/api/1.0/users/me",
                headers=headers,
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    user = data.get("data", {})
                    name = user.get("name", "unknown")
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.VALID,
                        f"Asana 有效 ({name})",
                        "asana",
                        {"name": name},
                        is_high_value=True
                    )
                elif resp.status == 401:
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.INVALID,
                        "Asana 认证失败",
                        "asana"
                    )
        except Exception as e:
            logger.debug(f"Asana 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.CONNECTION_ERROR,
            "连接失败",
            "asana"
        )

    async def validate_airtable(self, api_key: str) -> ExtendedValidationResult:
        """验证 Airtable API Key"""
        session = await self._get_session()
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            async with session.get(
                "https://api.airtable.com/v0/meta/whoami",
                headers=headers,
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    user_id = data.get("id", "unknown")
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.VALID,
                        f"Airtable 有效 (ID: {user_id})",
                        "airtable",
                        {"user_id": user_id},
                        is_high_value=True
                    )
                elif resp.status == 401:
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.INVALID,
                        "Airtable 认证失败",
                        "airtable"
                    )
        except Exception as e:
            logger.debug(f"Airtable 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.CONNECTION_ERROR,
            "连接失败",
            "airtable"
        )

    async def validate_jira_atlassian(self, email: str, api_token: str, domain: str) -> ExtendedValidationResult:
        """验证 Jira/Atlassian API Token"""
        session = await self._get_session()
        auth = aiohttp.BasicAuth(email, api_token)

        try:
            async with session.get(
                f"https://{domain}.atlassian.net/rest/api/3/myself",
                auth=auth,
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    display_name = data.get("displayName", "unknown")
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.VALID,
                        f"Atlassian 有效 ({display_name})",
                        "atlassian",
                        {"display_name": display_name, "domain": domain},
                        is_high_value=True
                    )
                elif resp.status == 401:
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.INVALID,
                        "Atlassian 认证失败",
                        "atlassian"
                    )
        except Exception as e:
            logger.debug(f"Atlassian 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.CONNECTION_ERROR,
            "连接失败",
            "atlassian"
        )

    # ========================================================================
    #                       分析平台
    # ========================================================================

    async def validate_segment(self, write_key: str) -> ExtendedValidationResult:
        """验证 Segment Write Key"""
        session = await self._get_session()
        auth = aiohttp.BasicAuth(write_key, "")

        try:
            async with session.post(
                "https://api.segment.io/v1/track",
                auth=auth,
                json={
                    "userId": "test_user",
                    "event": "validation_test",
                    "properties": {}
                },
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.VALID,
                        "Segment Write Key 有效",
                        "segment",
                        is_high_value=True
                    )
                elif resp.status == 401:
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.INVALID,
                        "Segment 认证失败",
                        "segment"
                    )
        except Exception as e:
            logger.debug(f"Segment 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.CONNECTION_ERROR,
            "连接失败",
            "segment"
        )

    async def validate_mixpanel(self, token: str) -> ExtendedValidationResult:
        """验证 Mixpanel Project Token"""
        # Mixpanel Token 只能通过发送 track 请求验证
        session = await self._get_session()

        try:
            async with session.post(
                "https://api.mixpanel.com/track",
                data={
                    "data": base64.b64encode(
                        f'{{"event":"test","properties":{{"token":"{token}"}}}}'.encode()
                    ).decode()
                },
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    result = await resp.text()
                    if result == "1":
                        return ExtendedValidationResult(
                            ExtendedKeyStatus.VALID,
                            "Mixpanel Token 有效",
                            "mixpanel",
                            is_high_value=True
                        )
        except Exception as e:
            logger.debug(f"Mixpanel 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.INVALID,
            "Mixpanel Token 无效",
            "mixpanel"
        )

    async def validate_amplitude(self, api_key: str) -> ExtendedValidationResult:
        """验证 Amplitude API Key"""
        session = await self._get_session()

        try:
            async with session.post(
                "https://api2.amplitude.com/2/httpapi",
                json={
                    "api_key": api_key,
                    "events": [{
                        "user_id": "test_user",
                        "event_type": "validation_test"
                    }]
                },
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("code") == 200:
                        return ExtendedValidationResult(
                            ExtendedKeyStatus.VALID,
                            "Amplitude API Key 有效",
                            "amplitude",
                            is_high_value=True
                        )
        except Exception as e:
            logger.debug(f"Amplitude 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.INVALID,
            "Amplitude API Key 无效",
            "amplitude"
        )

    async def validate_algolia(self, app_id: str, api_key: str) -> ExtendedValidationResult:
        """验证 Algolia API Key"""
        session = await self._get_session()
        headers = {
            "X-Algolia-Application-Id": app_id,
            "X-Algolia-API-Key": api_key
        }

        try:
            async with session.get(
                f"https://{app_id}-dsn.algolia.net/1/keys/{api_key}",
                headers=headers,
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    acl = data.get("acl", [])
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.VALID,
                        f"Algolia 有效 (权限: {len(acl)})",
                        "algolia",
                        {"acl": acl},
                        is_high_value="admin" in str(acl).lower()
                    )
                elif resp.status == 403:
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.INVALID,
                        "Algolia 认证失败",
                        "algolia"
                    )
        except Exception as e:
            logger.debug(f"Algolia 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.CONNECTION_ERROR,
            "连接失败",
            "algolia"
        )

    # ========================================================================
    #                       客服/CRM
    # ========================================================================

    async def validate_zendesk(self, subdomain: str, email: str, api_token: str) -> ExtendedValidationResult:
        """验证 Zendesk API Token"""
        session = await self._get_session()
        auth = aiohttp.BasicAuth(f"{email}/token", api_token)

        try:
            async with session.get(
                f"https://{subdomain}.zendesk.com/api/v2/users/me.json",
                auth=auth,
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    user = data.get("user", {})
                    name = user.get("name", "unknown")
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.VALID,
                        f"Zendesk 有效 ({name})",
                        "zendesk",
                        {"name": name, "subdomain": subdomain},
                        is_high_value=True
                    )
                elif resp.status == 401:
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.INVALID,
                        "Zendesk 认证失败",
                        "zendesk"
                    )
        except Exception as e:
            logger.debug(f"Zendesk 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.CONNECTION_ERROR,
            "连接失败",
            "zendesk"
        )

    async def validate_intercom(self, token: str) -> ExtendedValidationResult:
        """验证 Intercom Access Token"""
        session = await self._get_session()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }

        try:
            async with session.get(
                "https://api.intercom.io/me",
                headers=headers,
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    name = data.get("name", "unknown")
                    app_id = data.get("app", {}).get("id_code", "unknown")
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.VALID,
                        f"Intercom 有效 ({name}, App: {app_id})",
                        "intercom",
                        {"name": name, "app_id": app_id},
                        is_high_value=True
                    )
                elif resp.status == 401:
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.INVALID,
                        "Intercom 认证失败",
                        "intercom"
                    )
        except Exception as e:
            logger.debug(f"Intercom 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.CONNECTION_ERROR,
            "连接失败",
            "intercom"
        )

    async def validate_freshdesk(self, subdomain: str, api_key: str) -> ExtendedValidationResult:
        """验证 Freshdesk API Key"""
        session = await self._get_session()
        auth = aiohttp.BasicAuth(api_key, "X")

        try:
            async with session.get(
                f"https://{subdomain}.freshdesk.com/api/v2/agents/me",
                auth=auth,
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    name = data.get("contact", {}).get("name", "unknown")
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.VALID,
                        f"Freshdesk 有效 ({name})",
                        "freshdesk",
                        {"name": name, "subdomain": subdomain},
                        is_high_value=True
                    )
                elif resp.status == 401:
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.INVALID,
                        "Freshdesk 认证失败",
                        "freshdesk"
                    )
        except Exception as e:
            logger.debug(f"Freshdesk 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.CONNECTION_ERROR,
            "连接失败",
            "freshdesk"
        )

    # ========================================================================
    #                       地图服务
    # ========================================================================

    async def validate_mapbox(self, token: str) -> ExtendedValidationResult:
        """验证 Mapbox Access Token"""
        session = await self._get_session()

        try:
            async with session.get(
                f"https://api.mapbox.com/tokens/v2?access_token={token}",
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    username = data.get("code", "unknown")
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.VALID,
                        f"Mapbox 有效 ({username})",
                        "mapbox",
                        is_high_value=True
                    )
                elif resp.status == 401:
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.INVALID,
                        "Mapbox 认证失败",
                        "mapbox"
                    )
        except Exception as e:
            logger.debug(f"Mapbox 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.CONNECTION_ERROR,
            "连接失败",
            "mapbox"
        )

    async def validate_google_maps(self, api_key: str) -> ExtendedValidationResult:
        """验证 Google Maps API Key"""
        session = await self._get_session()

        try:
            # 使用 Geocoding API 测试
            async with session.get(
                f"https://maps.googleapis.com/maps/api/geocode/json?address=test&key={api_key}",
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    status = data.get("status")
                    if status in ["OK", "ZERO_RESULTS"]:
                        return ExtendedValidationResult(
                            ExtendedKeyStatus.VALID,
                            "Google Maps 有效",
                            "google_maps",
                            is_high_value=True
                        )
                    elif status == "REQUEST_DENIED":
                        error_msg = data.get("error_message", "")
                        if "API key" in error_msg:
                            return ExtendedValidationResult(
                                ExtendedKeyStatus.INVALID,
                                "Google Maps Key 无效",
                                "google_maps"
                            )
        except Exception as e:
            logger.debug(f"Google Maps 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.UNVERIFIED,
            "无法验证",
            "google_maps"
        )

    # ========================================================================
    #                       支付平台
    # ========================================================================

    async def validate_paypal(self, client_id: str, secret: str) -> ExtendedValidationResult:
        """验证 PayPal API 凭证"""
        session = await self._get_session()
        auth = aiohttp.BasicAuth(client_id, secret)

        try:
            async with session.post(
                "https://api-m.paypal.com/v1/oauth2/token",
                auth=auth,
                data={"grant_type": "client_credentials"},
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "access_token" in data:
                        return ExtendedValidationResult(
                            ExtendedKeyStatus.VALID,
                            "PayPal 生产环境 有效",
                            "paypal",
                            is_high_value=True
                        )
        except Exception as e:
            logger.debug(f"PayPal 验证异常: {e}")

        # 尝试 Sandbox
        try:
            async with session.post(
                "https://api-m.sandbox.paypal.com/v1/oauth2/token",
                auth=auth,
                data={"grant_type": "client_credentials"},
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "access_token" in data:
                        return ExtendedValidationResult(
                            ExtendedKeyStatus.VALID,
                            "PayPal Sandbox 有效",
                            "paypal_sandbox",
                            is_high_value=False
                        )
        except Exception as e:
            logger.debug(f"PayPal Sandbox 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.INVALID,
            "PayPal 认证失败",
            "paypal"
        )

    async def validate_square(self, access_token: str) -> ExtendedValidationResult:
        """验证 Square Access Token"""
        session = await self._get_session()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Square-Version": "2024-01-18"
        }

        try:
            async with session.get(
                "https://connect.squareup.com/v2/merchants/me",
                headers=headers,
                proxy=self.proxy_url
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    merchant = data.get("merchant", {})
                    name = merchant.get("business_name", "unknown")
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.VALID,
                        f"Square 有效 ({name})",
                        "square",
                        {"business_name": name},
                        is_high_value=True
                    )
                elif resp.status == 401:
                    return ExtendedValidationResult(
                        ExtendedKeyStatus.INVALID,
                        "Square 认证失败",
                        "square"
                    )
        except Exception as e:
            logger.debug(f"Square 验证异常: {e}")

        return ExtendedValidationResult(
            ExtendedKeyStatus.CONNECTION_ERROR,
            "连接失败",
            "square"
        )

    # ========================================================================
    #                       统一验证入口
    # ========================================================================

    async def validate(
        self,
        platform: str,
        credentials: Dict[str, str]
    ) -> ExtendedValidationResult:
        """
        统一验证入口

        Args:
            platform: 平台名称
            credentials: 凭证字典，键根据平台不同而不同

        Returns:
            验证结果
        """
        platform = platform.lower()

        # 通信/消息平台
        if platform == "slack":
            return await self.validate_slack_token(credentials.get("token", ""))
        elif platform == "discord":
            return await self.validate_discord_bot_token(credentials.get("token", ""))
        elif platform == "telegram":
            return await self.validate_telegram_bot_token(credentials.get("token", ""))
        elif platform == "twilio":
            return await self.validate_twilio(
                credentials.get("account_sid", ""),
                credentials.get("auth_token", "")
            )
        elif platform == "sendgrid":
            return await self.validate_sendgrid(credentials.get("api_key", ""))
        elif platform == "mailgun":
            return await self.validate_mailgun(credentials.get("api_key", ""))
        elif platform == "mailchimp":
            return await self.validate_mailchimp(credentials.get("api_key", ""))

        # 云服务商
        elif platform == "digitalocean":
            return await self.validate_digitalocean(credentials.get("token", ""))
        elif platform == "heroku":
            return await self.validate_heroku(credentials.get("api_key", ""))
        elif platform == "cloudflare":
            return await self.validate_cloudflare(
                credentials.get("api_key", ""),
                credentials.get("email", "")
            )
        elif platform == "vercel":
            return await self.validate_vercel(credentials.get("token", ""))

        # 开发工具
        elif platform == "gitlab":
            return await self.validate_gitlab_token(credentials.get("token", ""))
        elif platform == "bitbucket":
            return await self.validate_bitbucket(
                credentials.get("username", ""),
                credentials.get("app_password", "")
            )
        elif platform == "circleci":
            return await self.validate_circleci(credentials.get("token", ""))
        elif platform == "travis_ci":
            return await self.validate_travis_ci(credentials.get("token", ""))
        elif platform == "npm":
            return await self.validate_npm_token(credentials.get("token", ""))
        elif platform == "docker_hub":
            return await self.validate_docker_hub(
                credentials.get("username", ""),
                credentials.get("password", "")
            )

        # 监控/APM
        elif platform == "datadog":
            return await self.validate_datadog(
                credentials.get("api_key", ""),
                credentials.get("app_key", "")
            )
        elif platform == "sentry":
            return await self.validate_sentry(credentials.get("auth_token", ""))
        elif platform == "newrelic":
            return await self.validate_newrelic(credentials.get("api_key", ""))
        elif platform == "pagerduty":
            return await self.validate_pagerduty(credentials.get("api_key", ""))

        # 协作工具
        elif platform == "notion":
            return await self.validate_notion(credentials.get("token", ""))
        elif platform == "linear":
            return await self.validate_linear(credentials.get("api_key", ""))
        elif platform == "asana":
            return await self.validate_asana(credentials.get("token", ""))
        elif platform == "airtable":
            return await self.validate_airtable(credentials.get("api_key", ""))
        elif platform in ["jira", "atlassian", "confluence"]:
            return await self.validate_jira_atlassian(
                credentials.get("email", ""),
                credentials.get("api_token", ""),
                credentials.get("domain", "")
            )

        # 分析平台
        elif platform == "segment":
            return await self.validate_segment(credentials.get("write_key", ""))
        elif platform == "mixpanel":
            return await self.validate_mixpanel(credentials.get("token", ""))
        elif platform == "amplitude":
            return await self.validate_amplitude(credentials.get("api_key", ""))
        elif platform == "algolia":
            return await self.validate_algolia(
                credentials.get("app_id", ""),
                credentials.get("api_key", "")
            )

        # 客服/CRM
        elif platform == "zendesk":
            return await self.validate_zendesk(
                credentials.get("subdomain", ""),
                credentials.get("email", ""),
                credentials.get("api_token", "")
            )
        elif platform == "intercom":
            return await self.validate_intercom(credentials.get("token", ""))
        elif platform == "freshdesk":
            return await self.validate_freshdesk(
                credentials.get("subdomain", ""),
                credentials.get("api_key", "")
            )

        # 地图服务
        elif platform == "mapbox":
            return await self.validate_mapbox(credentials.get("token", ""))
        elif platform == "google_maps":
            return await self.validate_google_maps(credentials.get("api_key", ""))

        # 支付平台
        elif platform == "paypal":
            return await self.validate_paypal(
                credentials.get("client_id", ""),
                credentials.get("secret", "")
            )
        elif platform == "square":
            return await self.validate_square(credentials.get("access_token", ""))

        # 未知平台
        else:
            return ExtendedValidationResult(
                ExtendedKeyStatus.UNVERIFIED,
                f"不支持的平台: {platform}",
                platform
            )


# ============================================================================
#                              便捷函数
# ============================================================================

_global_validator: Optional[ExtendedValidator] = None


async def get_extended_validator(proxy_url: str = None) -> ExtendedValidator:
    """获取全局扩展验证器实例"""
    global _global_validator

    if _global_validator is None:
        _global_validator = ExtendedValidator(proxy_url)

    return _global_validator


async def validate_extended(
    platform: str,
    credentials: Dict[str, str],
    proxy_url: str = None
) -> ExtendedValidationResult:
    """便捷验证函数"""
    validator = await get_extended_validator(proxy_url)
    return await validator.validate(platform, credentials)


# ============================================================================
#                              平台清单
# ============================================================================

EXTENDED_PLATFORMS = {
    # 通信/消息平台
    "slack": {"required": ["token"], "description": "Slack Bot/User Token"},
    "discord": {"required": ["token"], "description": "Discord Bot Token"},
    "telegram": {"required": ["token"], "description": "Telegram Bot Token"},
    "twilio": {"required": ["account_sid", "auth_token"], "description": "Twilio API"},
    "sendgrid": {"required": ["api_key"], "description": "SendGrid API Key"},
    "mailgun": {"required": ["api_key"], "description": "Mailgun API Key"},
    "mailchimp": {"required": ["api_key"], "description": "Mailchimp API Key"},

    # 云服务商
    "digitalocean": {"required": ["token"], "description": "DigitalOcean API Token"},
    "heroku": {"required": ["api_key"], "description": "Heroku API Key"},
    "cloudflare": {"required": ["api_key"], "optional": ["email"], "description": "Cloudflare API"},
    "vercel": {"required": ["token"], "description": "Vercel API Token"},

    # 开发工具
    "gitlab": {"required": ["token"], "description": "GitLab Personal Access Token"},
    "bitbucket": {"required": ["username", "app_password"], "description": "Bitbucket App Password"},
    "circleci": {"required": ["token"], "description": "CircleCI API Token"},
    "travis_ci": {"required": ["token"], "description": "Travis CI API Token"},
    "npm": {"required": ["token"], "description": "NPM Auth Token"},
    "docker_hub": {"required": ["username", "password"], "description": "Docker Hub 凭证"},

    # 监控/APM
    "datadog": {"required": ["api_key"], "optional": ["app_key"], "description": "Datadog API Key"},
    "sentry": {"required": ["auth_token"], "description": "Sentry Auth Token"},
    "newrelic": {"required": ["api_key"], "description": "New Relic API Key"},
    "pagerduty": {"required": ["api_key"], "description": "PagerDuty API Key"},

    # 协作工具
    "notion": {"required": ["token"], "description": "Notion Integration Token"},
    "linear": {"required": ["api_key"], "description": "Linear API Key"},
    "asana": {"required": ["token"], "description": "Asana Personal Access Token"},
    "airtable": {"required": ["api_key"], "description": "Airtable API Key"},
    "atlassian": {"required": ["email", "api_token", "domain"], "description": "Jira/Confluence API"},

    # 分析平台
    "segment": {"required": ["write_key"], "description": "Segment Write Key"},
    "mixpanel": {"required": ["token"], "description": "Mixpanel Project Token"},
    "amplitude": {"required": ["api_key"], "description": "Amplitude API Key"},
    "algolia": {"required": ["app_id", "api_key"], "description": "Algolia API Key"},

    # 客服/CRM
    "zendesk": {"required": ["subdomain", "email", "api_token"], "description": "Zendesk API"},
    "intercom": {"required": ["token"], "description": "Intercom Access Token"},
    "freshdesk": {"required": ["subdomain", "api_key"], "description": "Freshdesk API Key"},

    # 地图服务
    "mapbox": {"required": ["token"], "description": "Mapbox Access Token"},
    "google_maps": {"required": ["api_key"], "description": "Google Maps API Key"},

    # 支付平台
    "paypal": {"required": ["client_id", "secret"], "description": "PayPal API 凭证"},
    "square": {"required": ["access_token"], "description": "Square Access Token"},
}


def get_supported_platforms() -> Dict[str, dict]:
    """获取支持的平台列表"""
    return EXTENDED_PLATFORMS.copy()


def get_platform_requirements(platform: str) -> dict:
    """获取平台的凭证要求"""
    return EXTENDED_PLATFORMS.get(platform.lower(), {})
