"""Anthropic: POST /v1/messages with credit/billing mapping."""

import asyncio

import aiohttp

from config import CIRCUIT_BREAKER_HTTP_CODES, config
from database import KeyStatus
from validator.types import ValidationResult


async def validate_anthropic(self, api_key: str, base_url: str) -> ValidationResult:
    """
    异步验证 Anthropic Claude Key。

    必须用 POST /v1/messages（不支持 GET /models）。
    400 + credit/billing → QUOTA_EXCEEDED。
    """
    if not base_url:
        base_url = config.default_base_urls["anthropic"]

    circuit_result = await self._check_circuit_breaker(base_url)
    if circuit_result:
        return circuit_result

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }

    body = {
        "model": "claude-3-haiku-20240307",
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "Hi"}]
    }

    session = await self._get_session()
    proxy = self._get_proxy()

    try:
        url = f"{base_url.rstrip('/')}/v1/messages"
        async with session.post(url, headers=headers, json=body, proxy=proxy) as resp:
            response_text = await resp.text()

            if resp.status == 200:
                await self._record_circuit_result(url, success=True)
                try:
                    data = await resp.json()
                    model_used = data.get("model", "claude-3").lower()
                    if "opus" in model_used:
                        tier = "Claude-3-Opus"
                    elif "sonnet" in model_used:
                        tier = "Claude-3-Sonnet"
                    else:
                        tier = "Claude-3"
                    return ValidationResult(KeyStatus.VALID, "Claude有效", tier)
                except Exception:
                    return ValidationResult(KeyStatus.VALID, "Claude有效", "Claude-3")

            elif resp.status == 400:
                await self._record_circuit_result(url, http_status=400)
                if "credit" in response_text.lower() and "balance" in response_text.lower():
                    return ValidationResult(KeyStatus.QUOTA_EXCEEDED, "Claude余额不足", "Claude-3", 0)
                elif "billing" in response_text.lower():
                    return ValidationResult(KeyStatus.QUOTA_EXCEEDED, "Claude账单问题", "Claude-3", 0)
                else:
                    return ValidationResult(KeyStatus.VALID, "有效(请求错误)", "Claude", 0)

            elif resp.status == 401:
                await self._record_circuit_result(url, http_status=401)
                return ValidationResult(KeyStatus.INVALID, "Claude认证失败")

            elif resp.status == 403:
                await self._record_circuit_result(url, http_status=403)
                if "disabled" in response_text.lower():
                    return ValidationResult(KeyStatus.INVALID, "Claude Key已禁用")
                return ValidationResult(KeyStatus.QUOTA_EXCEEDED, "Claude权限受限", "Claude", 0)

            elif resp.status == 429:
                await self._record_circuit_result(url, http_status=429)
                return ValidationResult(KeyStatus.QUOTA_EXCEEDED, "Claude速率限制")

            elif resp.status in CIRCUIT_BREAKER_HTTP_CODES:
                await self._record_circuit_result(url, http_status=resp.status)
                return ValidationResult(KeyStatus.CONNECTION_ERROR, f"网关错误 {resp.status}")

            else:
                await self._record_circuit_result(url, http_status=resp.status)
                return ValidationResult(KeyStatus.INVALID, f"HTTP {resp.status}")

    except aiohttp.ClientConnectorError as e:
        await self._record_circuit_result(base_url, error=e)
        return ValidationResult(KeyStatus.CONNECTION_ERROR, "Claude连接失败")
    except asyncio.TimeoutError as e:
        await self._record_circuit_result(base_url, error=e)
        return ValidationResult(KeyStatus.CONNECTION_ERROR, "Claude超时")
    except Exception as e:
        return ValidationResult(KeyStatus.INVALID, str(e)[:20])
