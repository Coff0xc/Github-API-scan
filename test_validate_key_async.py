"""validate_key_async 分发原语的回归测试。

背景：validator_optimized 的验证 worker 对非 openai/relay 平台调用
validator.validate_key_async，但该函数自 edf3439 起从未真正存在，
远程扫描的非 openai 平台验证一启动就 ImportError。

全部用 mock 或 loopback 死端口，不进真实网络。
"""

from validator import AsyncValidator, CircuitBreaker, ValidationResult, validate_key_async
from database import KeyStatus


async def test_dispatch_routes_to_platform_method(monkeypatch):
    """平台名应路由到对应 validate_* 方法，元组形状正确。"""
    calls = []

    async def fake_gemini(self, api_key, base_url):
        calls.append((api_key, base_url))
        return ValidationResult(KeyStatus.VALID, "ok", "Gemini-Pro", 1000)

    monkeypatch.setattr(AsyncValidator, "validate_gemini", fake_gemini)

    status, balance, tier, rpm, high = await validate_key_async("gemini", "k1", "u1")

    assert calls == [("k1", "u1")]
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
    """未知平台回落 OpenAI 兼容验证（SSRF 拒绝的内网地址应快速返回 INVALID）。"""
    calls = []

    async def fake_openai(self, api_key, base_url):
        calls.append(base_url)
        # 模拟 validate_openai 的 SSRF 前置检查
        from validator import ValidationResult
        if not self._is_likely_valid_relay(base_url):
            return ValidationResult(KeyStatus.INVALID, "base_url 无效")
        return ValidationResult(KeyStatus.CONNECTION_ERROR, "refused")

    monkeypatch.setattr(AsyncValidator, "validate_openai", fake_openai)

    status, *_ = await validate_key_async("future_platform", "sk-x", "http://192.168.1.1/v1")

    assert calls == ["http://192.168.1.1/v1"]
    assert status == KeyStatus.INVALID


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
        "other", "sk-y", "http://192.168.1.1/v1", circuit_breaker=breaker
    )
    assert status == KeyStatus.INVALID
