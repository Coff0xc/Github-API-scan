"""Table-driven GET checks for Bearer/Token platforms with the same status map."""

from dataclasses import dataclass
from typing import Dict, Optional

from loguru import logger

from database import KeyStatus
from validator.types import ValidationResult


@dataclass(frozen=True)
class GetSpec:
    name: str
    default_base: str = ""
    path: str = "models"
    auth: str = "bearer"
    valid_info: str = ""
    valid_statuses: tuple = (200,)
    count_models: bool = False
    count_label: str = ""
    empty_unverified: str = ""
    fixed_url: str = ""
    parse_github: bool = False
    drain_body: bool = False
    handle_429: bool = True
    log_name: str = ""
    doc: str = ""


SPECS = (
    GetSpec(
        name="huggingface",
        default_base="https://api-inference.huggingface.co",
        path="models/gpt2",
        valid_info="HuggingFace 有效",
        log_name="HuggingFace",
        doc="验证 Hugging Face API Key",
    ),
    GetSpec(
        name="groq",
        default_base="https://api.groq.com/openai/v1",
        valid_info="Groq 有效",
        log_name="Groq",
        doc="验证 Groq API Key",
    ),
    GetSpec(
        name="deepseek",
        default_base="https://api.deepseek.com",
        valid_info="DeepSeek 有效",
        log_name="DeepSeek",
        doc="验证 DeepSeek API Key",
    ),
    GetSpec(
        name="cohere",
        default_base="https://api.cohere.ai/v1",
        valid_info="Cohere 有效",
        log_name="Cohere",
        doc="验证 Cohere API Key",
    ),
    GetSpec(
        name="mistral",
        default_base="https://api.mistral.ai/v1",
        valid_info="Mistral 有效",
        log_name="Mistral",
        doc="验证 Mistral API Key",
    ),
    GetSpec(
        name="together",
        default_base="https://api.together.xyz/v1",
        valid_info="Together 有效",
        log_name="Together",
        doc="验证 Together AI API Key",
    ),
    GetSpec(
        name="replicate",
        default_base="https://api.replicate.com/v1",
        path="account",
        auth="token",
        valid_info="Replicate 有效",
        log_name="Replicate",
        doc="验证 Replicate API Key",
    ),
    GetSpec(
        name="perplexity",
        default_base="https://api.perplexity.ai",
        valid_info="Perplexity 有效",
        log_name="Perplexity",
        doc="验证 Perplexity API Key",
    ),
    GetSpec(
        name="fireworks",
        default_base="https://api.fireworks.ai/inference/v1",
        valid_info="Fireworks 有效",
        log_name="Fireworks",
        doc="验证 Fireworks AI API Key",
    ),
    GetSpec(
        name="stripe",
        fixed_url="https://api.stripe.com/v1/balance",
        valid_info="Stripe 有效",
        drain_body=True,
        handle_429=False,
        log_name="Stripe",
        doc="验证 Stripe API Key",
    ),
    GetSpec(
        name="github_token",
        fixed_url="https://api.github.com/user",
        auth="github",
        parse_github=True,
        handle_429=False,
        log_name="GitHub",
        doc="验证 GitHub Token",
    ),
    GetSpec(
        name="moonshot",
        default_base="https://api.moonshot.cn/v1",
        count_models=True,
        count_label="Moonshot 有效 ({n}模型)",
        log_name="Moonshot",
        doc="验证 Moonshot AI (Kimi) API Key",
    ),
    GetSpec(
        name="zhipu",
        default_base="https://open.bigmodel.cn/api/paas/v4",
        valid_info="Zhipu AI 有效",
        log_name="Zhipu",
        doc="验证 Zhipu AI (智谱) API Key",
    ),
    GetSpec(
        name="baichuan",
        default_base="https://api.baichuan-ai.com/v1",
        valid_info="Baichuan 有效",
        log_name="Baichuan",
        doc="验证 Baichuan AI (百川智能) API Key",
    ),
    GetSpec(
        name="minimax",
        default_base="https://api.minimax.chat/v1",
        path="text/chatcompletion",
        valid_info="MiniMax 有效",
        valid_statuses=(200, 400),
        log_name="MiniMax",
        doc="验证 MiniMax API Key",
    ),
    GetSpec(
        name="aliyun_bailian",
        default_base="https://dashscope.aliyuncs.com/api/v1",
        path="services/aigc/text-generation/generation",
        valid_info="阿里百炼 有效",
        valid_statuses=(200, 400),
        log_name="阿里百炼",
        doc="验证阿里云百炼 API Key",
    ),
    GetSpec(
        name="volcengine",
        default_base="https://ark.cn-beijing.volces.com/api/v3",
        valid_info="火山引擎 有效",
        log_name="火山引擎",
        doc="验证火山引擎 (字节跳动) API Key",
    ),
    GetSpec(
        name="tencent_hunyuan",
        default_base="https://hunyuan.tencentcloudapi.com",
        path="/",
        valid_info="腾讯混元 有效",
        valid_statuses=(200, 400),
        log_name="腾讯混元",
        doc="验证腾讯混元 API Key",
    ),
    GetSpec(
        name="openrouter",
        default_base="https://openrouter.ai/api/v1",
        count_models=True,
        count_label="OpenRouter 有效 ({n}模型)",
        log_name="OpenRouter",
        doc="验证 OpenRouter API Key",
    ),
    GetSpec(
        name="portkey",
        default_base="https://api.portkey.ai/v1",
        auth="portkey",
        valid_info="Portkey 有效",
        log_name="Portkey",
        doc="验证 Portkey API Key",
    ),
    GetSpec(
        name="litellm",
        default_base="http://localhost:4000",
        count_models=True,
        count_label="LiteLLM 有效 ({n}模型)",
        log_name="LiteLLM",
        doc="验证 LiteLLM Proxy API Key",
    ),
    GetSpec(
        name="cloudflare_ai",
        path="",
        valid_info="Cloudflare AI 有效",
        valid_statuses=(200, 400),
        empty_unverified="需要 account_id",
        log_name="Cloudflare AI",
        doc="验证 Cloudflare Workers AI API Key",
    ),
    GetSpec(
        name="xai",
        default_base="https://api.x.ai/v1",
        valid_info="xAI Grok 有效",
        log_name="xAI",
        doc="验证 xAI Grok API Key",
    ),
    GetSpec(
        name="meta_llama",
        default_base="https://api.meta.ai/v1",
        valid_info="Meta Llama 有效",
        log_name="Meta Llama",
        doc="验证 Meta Llama API Key",
    ),
)


def _headers(spec: GetSpec, api_key: str) -> dict:
    if spec.auth == "token":
        return {"Authorization": f"Token {api_key}"}
    if spec.auth == "github":
        return {"Authorization": f"token {api_key}"}
    if spec.auth == "portkey":
        return {"x-portkey-api-key": api_key}
    return {"Authorization": f"Bearer {api_key}"}


def _url(spec: GetSpec, base_url: str) -> Optional[str]:
    if spec.fixed_url:
        return spec.fixed_url
    if spec.empty_unverified and not base_url:
        return None
    if not base_url:
        base_url = spec.default_base
    if spec.path:
        return f"{base_url.rstrip('/')}/{spec.path.lstrip('/')}"
    return base_url.rstrip('/')


async def run_get(self, spec: GetSpec, api_key: str, base_url: str) -> ValidationResult:
    if spec.empty_unverified and not base_url:
        return ValidationResult(KeyStatus.UNVERIFIED, spec.empty_unverified)

    url = _url(spec, base_url)
    headers = _headers(spec, api_key)
    session = await self._get_session()
    proxy = self._get_proxy()

    try:
        async with session.get(url, headers=headers, proxy=proxy) as resp:
            if resp.status in spec.valid_statuses:
                if spec.parse_github:
                    data = await resp.json()
                    username = data.get('login', 'unknown')
                    return ValidationResult(KeyStatus.VALID, f"GitHub @{username}")
                if spec.count_models:
                    data = await resp.json()
                    models = data.get("data", [])
                    return ValidationResult(
                        KeyStatus.VALID, spec.count_label.format(n=len(models))
                    )
                if spec.drain_body:
                    await resp.read()
                return ValidationResult(KeyStatus.VALID, spec.valid_info)
            elif resp.status == 401:
                return ValidationResult(KeyStatus.INVALID, "无效")
            elif spec.handle_429 and resp.status == 429:
                return ValidationResult(KeyStatus.QUOTA_EXCEEDED, "配额耗尽")
    except Exception as e:
        logger.debug(f"{spec.log_name} 验证异常: {e}")
    return ValidationResult(KeyStatus.CONNECTION_ERROR, "连接失败")


def _make_validator(spec: GetSpec):
    async def _validate(self, api_key: str, base_url: str) -> ValidationResult:
        return await run_get(self, spec, api_key, base_url)

    _validate.__name__ = f"validate_{spec.name}"
    _validate.__qualname__ = f"AsyncValidator.validate_{spec.name}"
    _validate.__doc__ = spec.doc
    return _validate


GET_VALIDATORS: Dict[str, object] = {
    f"validate_{spec.name}": _make_validator(spec) for spec in SPECS
}
