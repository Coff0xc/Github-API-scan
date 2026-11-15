"""OpenAI-compatible GET /models with chat fallback."""

import asyncio

import aiohttp
from loguru import logger

from config import CIRCUIT_BREAKER_HTTP_CODES, config
from database import KeyStatus
from validator.types import (
    RPM_ENTERPRISE_THRESHOLD,
    RPM_FREE_TRIAL_THRESHOLD,
    ValidationResult,
)


async def validate_openai(self, api_key: str, base_url: str) -> ValidationResult:
    """异步验证 OpenAI / 中转站 - 集成熍断器保护"""

    if not base_url:
        base_url = config.default_base_urls["openai"]

    logger.debug(f"验证 OpenAI key {api_key[:15]}..., base_url: {base_url}")

    if not self._is_likely_valid_relay(base_url):
        return ValidationResult(KeyStatus.INVALID, "base_url 无效")

    circuit_result = await self._check_circuit_breaker(base_url)
    if circuit_result:
        return circuit_result

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    session = await self._get_session()
    proxy = self._get_proxy()

    model_tier = "GPT-3.5"
    rpm = 0
    models_list = []

    for url in self._try_url_variants(base_url, "models"):
        try:
            async with session.get(url, headers=headers, proxy=proxy) as resp:
                rpm = int(resp.headers.get('x-ratelimit-limit-requests', 0))

                if resp.status == 200:
                    await self._record_circuit_result(url, success=True)

                    data = await resp.json()
                    models_list = [m.get("id", "") for m in data.get("data", [])]

                    for m in models_list:
                        if any(hv in m.lower() for hv in ['gpt-4', 'gpt-4o']):
                            model_tier = "GPT-4"
                            break

                    model_names = [m[:15] for m in models_list[:3]]
                    info = f"{len(models_list)}模型: {', '.join(model_names)}"

                    rpm_tier = ""
                    if rpm >= RPM_ENTERPRISE_THRESHOLD:
                        rpm_tier = "Enterprise"
                    elif rpm > 0 and rpm <= RPM_FREE_TRIAL_THRESHOLD:
                        rpm_tier = "Free Trial"

                    if rpm_tier:
                        info = f"{info} [{rpm_tier}]"

                    return ValidationResult(KeyStatus.VALID, info, model_tier, rpm)

                elif resp.status == 429:
                    await self._record_circuit_result(url, http_status=429)
                    return ValidationResult(KeyStatus.QUOTA_EXCEEDED, "配额耗尽")

                elif resp.status in CIRCUIT_BREAKER_HTTP_CODES:
                    await self._record_circuit_result(url, http_status=resp.status)
                    continue
                else:
                    await self._record_circuit_result(url, http_status=resp.status)

        except asyncio.TimeoutError as e:
            await self._record_circuit_result(url, error=e)
            continue
        except aiohttp.ClientConnectorError as e:
            await self._record_circuit_result(url, error=e)
            return ValidationResult(KeyStatus.CONNECTION_ERROR, "连接失败")
        except Exception as e:
            logger.debug(f"验证异常: {type(e).__name__}: {e}")
            continue

    chat_body = {"model": "gpt-3.5-turbo", "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 1}

    for url in self._try_url_variants(base_url, "chat/completions"):
        try:
            async with session.post(url, headers=headers, json=chat_body, proxy=proxy) as resp:
                if resp.status == 200:
                    await self._record_circuit_result(url, success=True)
                    return ValidationResult(KeyStatus.VALID, "有效(chat)", model_tier, rpm)
                elif resp.status == 429:
                    await self._record_circuit_result(url, http_status=429)
                    return ValidationResult(KeyStatus.QUOTA_EXCEEDED, "配额耗尽")
                elif resp.status in CIRCUIT_BREAKER_HTTP_CODES:
                    await self._record_circuit_result(url, http_status=resp.status)
                    continue
                else:
                    await self._record_circuit_result(url, http_status=resp.status)
        except aiohttp.ClientConnectorError as e:
            await self._record_circuit_result(url, error=e)
            return ValidationResult(KeyStatus.CONNECTION_ERROR, "连接失败")
        except asyncio.TimeoutError as e:
            await self._record_circuit_result(url, error=e)
            continue
        except Exception as e:
            logger.debug(f"验证异常: {type(e).__name__}: {e}")
            continue

    return ValidationResult(KeyStatus.INVALID, "认证失败")
