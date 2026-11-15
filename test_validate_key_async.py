"""validate_key_async 分发原语 + SSRF 防护的回归测试。

背景：validator_optimized 的验证 worker 对非 openai/relay 平台调用
validator.validate_key_async，但该函数自 edf3439 起从未真正存在，
远程扫描的非 openai 平台验证一启动就 ImportError。

SSRF 部分：validate_single 现在对一切非空自定义 base_url 做防护
（此前只有 validate_openai 检查，其余 30 个平台方法会被恶意仓库
诱导去探测内网）。

全部用 mock 或 loopback 死端口，不打真实网络。
"""

from validator import AsyncValidator, CircuitBreaker, ValidationResult, validate_key_async
from database import KeyStatus

# 公网字面量 IP，https scheme，过 SSRF 防护且无需 DNS
PUBLIC_URL = "https://93.184.216.34/v1"


async def test_dispatch_routes_to_platform_method(monkeypatch):
    """平台名应路由到对应 validate_* 方法，元组形状正确。"""
    calls = []

    async def fake_gemini(self, api_key, base_url):
        calls.append((api_key, base_url))
        return ValidationResult(KeyStatus.VALID, "ok", "Gemini-Pro", 1000)

    monkeypatch.setattr(AsyncValidator, "validate_gemini", fake_gemini)

    status, balance, tier, rpm, high = await validate_key_async("gemini", "k1", PUBLIC_URL)

    assert calls == [("k1", PUBLIC_URL)]
    assert status == KeyStatus.VALID
    assert tier == "Gemini-Pro"
    assert rpm == 1000
    assert balance == ""
    assert high is False


async def test_azure_flag_set_for_azure_platform(monkeypatch):
    """platform=azure 应触发 AsyncValidator 的 azure 特判分支。"""
    calls = []

    async def fake_azure(self, api_key, base_url):
        calls.append(base_url)
        return ValidationResult(KeyStatus.INVALID, "no endpoint")

    monkeypatch.setattr(AsyncValidator, "validate_azure", fake_azure)

    await validate_key_async("azure", "abc123", "")

    assert calls == [""]


async def test_unknown_platform_falls_back_to_openai(monkeypatch):
    """未知平台回落 OpenAI 兼容验证。"""
    calls = []

    async def fake_openai(self, api_key, base_url):
        calls.append(base_url)
        return ValidationResult(KeyStatus.INVALID, "auth failed")

    monkeypatch.setattr(AsyncValidator, "validate_openai", fake_openai)

    status, *_ = await validate_key_async("future_platform", "sk-x", PUBLIC_URL)

    assert calls == [PUBLIC_URL]
    assert status == KeyStatus.INVALID


async def test_ssrf_guard_blocks_private_url_before_dispatch(monkeypatch):
    """非 openai 平台的内网 base_url 必须在分发前被 SSRF 防护拦下。"""
    called = []

    async def fake_gemini(self, api_key, base_url):
        called.append(base_url)
        return ValidationResult(KeyStatus.VALID, "ok")

    monkeypatch.setattr(AsyncValidator, "validate_gemini", fake_gemini)

    status, *_ = await validate_key_async("gemini", "k", "http://192.168.1.1/v1")

    assert status == KeyStatus.INVALID
    assert called == []


async def test_loopback_dead_port_returns_connection_error():
    """真实路径冒烟：loopback 死端口立即拒绝连接，返回 CONNECTION_ERROR。"""
    status, *_ = await validate_key_async("gemini", "AIzaSyTest", "http://127.0.0.1:1/v1beta")
    assert status in (KeyStatus.CONNECTION_ERROR, KeyStatus.INVALID)


async def test_accepts_caller_circuit_breaker(monkeypatch):
    """调用方传入的熔断器实例应被采用，不影响返回元组。"""
    breaker = CircuitBreaker()

    async def fake_openai(self, api_key, base_url):
        return ValidationResult(KeyStatus.INVALID, "blocked")

    monkeypatch.setattr(AsyncValidator, "validate_openai", fake_openai)

    status, *_ = await validate_key_async(
        "other", "sk-y", PUBLIC_URL, circuit_breaker=breaker
    )
    assert status == KeyStatus.INVALID


PLATFORM_VALIDATE_METHODS = (
    "validate_openai",
    "validate_gemini",
    "validate_anthropic",
    "validate_azure",
    "validate_huggingface",
    "validate_groq",
    "validate_deepseek",
    "validate_cohere",
    "validate_mistral",
    "validate_together",
    "validate_replicate",
    "validate_perplexity",
    "validate_fireworks",
    "validate_stripe",
    "validate_github_token",
    "validate_moonshot",
    "validate_zhipu",
    "validate_baichuan",
    "validate_minimax",
    "validate_aliyun_bailian",
    "validate_volcengine",
    "validate_tencent_hunyuan",
    "validate_aws_bedrock",
    "validate_openrouter",
    "validate_portkey",
    "validate_litellm",
    "validate_cloudflare_ai",
    "validate_xai",
    "validate_meta_llama",
    "validate_aws_access_key",
)


def test_all_platform_methods_bound_on_async_validator():
    from database import Database

    validator = AsyncValidator(Database(":memory:"))
    for name in PLATFORM_VALIDATE_METHODS:
        assert hasattr(validator, name), name
        assert callable(getattr(validator, name))
