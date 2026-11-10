"""AI 假阳性过滤管线的 hermetic 测试。

AI_FILTER_ENABLED=1 时 scanner 提取管线会挂上 AI 过滤（opt-in）。
这些测试用 MockBackend（纯规则引擎，不出网）覆盖：
- MockBackend 对测试样例 Key 的判定
- 过滤统计的正确性
- _maybe_enable_ai_filter 的开关接线
- patch_scanner_with_ai 的包裹与失败回落
"""

from types import SimpleNamespace

import pytest

from ai_scanner_integration import (
    ScannerAIIntegration,
    patch_scanner_with_ai,
)
import ai_scanner_integration
import scanner

CLEAN_SNIPPET = 'OPENAI_API_KEY = "sk-proj-Ab12Cd34Ef56Gh78Ij90Kl12Mn34Qr78"'
TESTY_SNIPPET = 'OPENAI_API_KEY = "sk-test-Ab12Cd34"  # test key, do not use'


async def _mock_integration() -> ScannerAIIntegration:
    """enable_ai=False → 规则引擎 MockBackend，无任何网络。"""
    integration = ScannerAIIntegration(enable_ai=False)
    assert await integration.initialize()
    return integration


async def test_quick_filter_flags_test_looking_key():
    """enable_ai=False 时只有规则层：测试样例 Key 被丢。"""
    integration = await _mock_integration()
    result = await integration.filter_candidate(
        platform="openai",
        api_key=TESTY_KEY,
        code_snippet=TESTY_SNIPPET,
    )
    assert result.should_validate is False
    assert result.filter_reason


async def test_ai_stage_scans_snippet_for_test_patterns(monkeypatch):
    """enable_ai=True（ollama 不可用时回落 Mock）时，内容里的 test 模式也会被抓。

    Key 本身干净、只有上下文可疑——这是正则层抓不到、需要 AI 层的场景。
    """
    monkeypatch.setenv("AI_DETECTOR_BACKEND", "ollama")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    integration = ScannerAIIntegration(enable_ai=True)
    assert await integration.initialize()

    result = await integration.filter_candidate(
        platform="openai",
        api_key=REAL_KEY,
        code_snippet=TESTY_SNIPPET,
    )
    assert result.should_validate is False
    assert "test" in result.filter_reason.lower()


async def test_clean_candidate_passes():
    integration = await _mock_integration()
    result = await integration.filter_candidate(
        platform="openai",
        api_key="sk-proj-Ab12Cd34Ef56Gh78Ij90Kl12Mn34Qr78",
        code_snippet=CLEAN_SNIPPET,
    )
    assert result.should_validate is True
    assert result.filter_reason == ""


async def test_filter_batch_and_stats():
    integration = await _mock_integration()
    candidates = [
        {"platform": "openai", "api_key": f"sk-test-{i}", "code_snippet": TESTY_SNIPPET}
        for i in range(2)
    ] + [
        {"platform": "openai",
         "api_key": "sk-proj-Ab12Cd34Ef56Gh78Ij90Kl12Mn34Qr78",
         "code_snippet": CLEAN_SNIPPET},
    ]

    results = await integration.filter_batch(candidates)
    assert len(results) == 3
    assert [r.should_validate for r in results] == [False, False, True]

    stats = integration.get_stats()
    assert stats["total_candidates"] == 3
    assert stats["quick_filtered"] + stats["ai_filtered"] == 2
    assert stats["passed_to_validate"] == 1
    assert abs(stats["filter_rate"] - (2 / 3 * 100)) < 0.01


def test_wiring_disabled_by_default(monkeypatch):
    """未设置 AI_FILTER_ENABLED 时不得挂载补丁。"""
    monkeypatch.delenv("AI_FILTER_ENABLED", raising=False)
    calls = []
    monkeypatch.setattr(
        ai_scanner_integration, "patch_scanner_with_ai",
        lambda *a, **k: calls.append((a, k)),
    )

    scanner._maybe_enable_ai_filter()

    assert calls == []


def test_wiring_enabled_calls_patch(monkeypatch):
    """AI_FILTER_ENABLED=1 时以 scanner 模块本体 + integration 实例发起挂载。"""
    monkeypatch.setenv("AI_FILTER_ENABLED", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("AI_DETECTOR_BACKEND", "ollama")

    calls = []
    monkeypatch.setattr(
        ai_scanner_integration, "patch_scanner_with_ai",
        lambda *a, **k: calls.append((a, k)),
    )

    scanner._maybe_enable_ai_filter()

    assert len(calls) == 1
    args, _ = calls[0]
    assert args[0] is scanner
    assert isinstance(args[1], ScannerAIIntegration)


REAL_KEY = "sk-proj-Ab12Cd34Ef56Gh78Ij90Kl12Mn34Qr78"


TESTY_KEY = "sk-test-Ab12Cd34Ef56"


class _FakeScanner:
    def __init__(self):
        self.calls = 0

    def _extract_keys_from_content(self, content, source_url=""):
        self.calls += 1
        return [
            SimpleNamespace(platform="openai", api_key=TESTY_KEY, base_url=""),
            SimpleNamespace(platform="openai", api_key=REAL_KEY, base_url=""),
        ]


async def test_patch_drops_filtered_and_falls_back(monkeypatch):
    """包裹后的提取器：测试样例被丢、干净结果保留、过滤抛错时回落原结果。"""
    fake_module = SimpleNamespace(GitHubScanner=_FakeScanner)
    integration = await _mock_integration()
    patch_scanner_with_ai(fake_module, integration)

    instance = _FakeScanner()
    kept = instance._extract_keys_from_content(CLEAN_SNIPPET)
    assert [r.api_key for r in kept] == [REAL_KEY]

    async def _boom(**_kwargs):
        raise RuntimeError("llm down")

    monkeypatch.setattr(integration.detector, "should_validate", _boom)
    fallback = instance._extract_keys_from_content(CLEAN_SNIPPET)
    assert [r.api_key for r in fallback] == [TESTY_KEY, REAL_KEY]
