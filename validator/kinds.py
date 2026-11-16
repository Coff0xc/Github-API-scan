"""How honestly we checked a finding: protocol, generic HTTP, or match only."""

from __future__ import annotations

KIND_PROTOCOL = "protocol"
KIND_GENERIC_HTTP = "generic_http"
KIND_MATCH_ONLY = "match_only"

KINDS = (KIND_PROTOCOL, KIND_GENERIC_HTTP, KIND_MATCH_ONLY)

# Dedicated vendor/relay protocols, including OpenAI-compatible /v1/models.
PROTOCOL_PLATFORMS = frozenset({
    "openai",
    "relay",
    "anthropic",
    "gemini",
    "azure",
    "groq",
    "deepseek",
    "mistral",
    "together",
    "moonshot",
    "zhipu",
    "baichuan",
    "minimax",
    "openrouter",
    "litellm",
    "xai",
    "meta_llama",
    "portkey",
    "fireworks",
    "perplexity",
    "volcengine",
    "aliyun_bailian",
    "tencent_hunyuan",
})

# HTTP GET against a vendor path that is not the OpenAI-compatible protocol.
GENERIC_HTTP_PLATFORMS = frozenset({
    "huggingface",
    "cohere",
    "replicate",
    "stripe",
    "github_token",
    "cloudflare_ai",
    "aws_bedrock",
    "aws_access_key",
})

# OpenAI-compatible hosts use the cached GET /models path against the paired URL.
OPENAI_COMPAT_PLATFORMS = PROTOCOL_PLATFORMS - frozenset({
    "anthropic",
    "gemini",
    "azure",
})


def verification_kind(platform: str) -> str:
    name = (platform or "").strip().lower()
    if name in PROTOCOL_PLATFORMS:
        return KIND_PROTOCOL
    if name in GENERIC_HTTP_PLATFORMS:
        return KIND_GENERIC_HTTP
    from validator.platforms import PLATFORM_METHODS
    if f"validate_{name}" in PLATFORM_METHODS:
        return KIND_GENERIC_HTTP
    return KIND_MATCH_ONLY
