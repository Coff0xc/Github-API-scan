"""Azure OpenAI: api-key header, GET /openai/deployments."""

import asyncio

import aiohttp

from config import CIRCUIT_BREAKER_HTTP_CODES
from database import KeyStatus
from validator.types import ValidationResult


async def validate_azure(self, api_key: str, base_url: str) -> ValidationResult:
    """异步验证 Azure - 集成熍断器保护"""
    if not base_url:
        return ValidationResult(KeyStatus.UNVERIFIED, "缺少Endpoint")

    circuit_result = await self._check_circuit_breaker(base_url)
    if circuit_result:
        return circuit_result

    headers = {"api-key": api_key, "Content-Type": "application/json"}
    session = await self._get_session()
    proxy = self._get_proxy()

    try:
        url = f"{base_url.rstrip('/')}/openai/deployments?api-version=2023-05-15"
        async with session.get(url, headers=headers, proxy=proxy) as resp:
            if resp.status == 200:
                await self._record_circuit_result(url, success=True)
                return ValidationResult(KeyStatus.VALID, "Azure有效", "Azure-GPT", 0)
            elif resp.status == 429:
                await self._record_circuit_result(url, http_status=429)
                return ValidationResult(KeyStatus.QUOTA_EXCEEDED, "Azure配额耗尽")
            elif resp.status in CIRCUIT_BREAKER_HTTP_CODES:
                await self._record_circuit_result(url, http_status=resp.status)
                return ValidationResult(KeyStatus.CONNECTION_ERROR, f"网关错误 {resp.status}")
            else:
                await self._record_circuit_result(url, http_status=resp.status)
                return ValidationResult(KeyStatus.INVALID, f"HTTP {resp.status}")
    except aiohttp.ClientConnectorError as e:
        await self._record_circuit_result(base_url, error=e)
        return ValidationResult(KeyStatus.CONNECTION_ERROR, "Azure连接失败")
    except asyncio.TimeoutError as e:
        await self._record_circuit_result(base_url, error=e)
        return ValidationResult(KeyStatus.CONNECTION_ERROR, "Azure超时")
    except Exception as e:
        return ValidationResult(KeyStatus.INVALID, str(e)[:20])
