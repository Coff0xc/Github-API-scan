"""Gemini: GET /models?key=."""

import asyncio

import aiohttp
from loguru import logger

from config import CIRCUIT_BREAKER_HTTP_CODES, config
from database import KeyStatus
from validator.types import ValidationResult


async def validate_gemini(self, api_key: str, base_url: str) -> ValidationResult:
    """异步验证 Gemini - 集成熍断器保护"""
    if not base_url:
        base_url = config.default_base_urls.get(
            "gemini", "https://generativelanguage.googleapis.com/v1beta"
        )

    logger.debug(f"验证 Gemini key {api_key[:15]}..., base_url: {base_url}")

    url = f"{base_url.rstrip('/')}/models?key={api_key}"

    circuit_result = await self._check_circuit_breaker(url)
    if circuit_result:
        return circuit_result

    session = await self._get_session()
    proxy = self._get_proxy()

    try:
        async with session.get(url, proxy=proxy) as resp:
            if resp.status == 200:
                await self._record_circuit_result(url, success=True)
                data = await resp.json()
                models = data.get("models", [])
                has_pro = any('gemini-1.5-pro' in m.get('name', '').lower() for m in models)
                tier = "Gemini-Pro" if has_pro else "Gemini"
                return ValidationResult(KeyStatus.VALID, f"{len(models)}模型", tier, 0, 0.0, has_pro)
            elif resp.status == 429:
                await self._record_circuit_result(url, http_status=429)
                return ValidationResult(KeyStatus.QUOTA_EXCEEDED, "Gemini配额耗尽")
            elif resp.status in CIRCUIT_BREAKER_HTTP_CODES:
                await self._record_circuit_result(url, http_status=resp.status)
                return ValidationResult(KeyStatus.CONNECTION_ERROR, f"网关错误 {resp.status}")
            else:
                await self._record_circuit_result(url, http_status=resp.status)
                return ValidationResult(KeyStatus.INVALID, f"HTTP {resp.status}")
    except aiohttp.ClientConnectorError as e:
        await self._record_circuit_result(url, error=e)
        return ValidationResult(KeyStatus.CONNECTION_ERROR, "Gemini连接失败")
    except asyncio.TimeoutError as e:
        await self._record_circuit_result(url, error=e)
        return ValidationResult(KeyStatus.CONNECTION_ERROR, "Gemini超时")
    except Exception as e:
        return ValidationResult(KeyStatus.INVALID, str(e)[:20])
