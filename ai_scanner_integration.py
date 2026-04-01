"""
AI 检测器与 Scanner 集成模块
============================

将 AI 辅助检测集成到扫描流程中，
在正则匹配后、验证前进行智能过滤
"""

import asyncio
from typing import Optional, Tuple, List
from dataclasses import dataclass

from loguru import logger

from ai_detector import (
    SmartDetector,
    AIDetector,
    QuickFilter,
    CodeContext,
    AIDetectionResult,
    Confidence,
    KeyType,
    OllamaBackend,
    OpenAIBackend,
    MockBackend,
    get_smart_detector,
    init_smart_detector,
)


@dataclass
class FilteredScanResult:
    """过滤后的扫描结果"""
    platform: str
    api_key: str
    base_url: str
    source_url: str
    file_sha: str
    code_snippet: str
    file_path: str

    # AI 检测结果
    ai_result: Optional[AIDetectionResult] = None
    should_validate: bool = True
    filter_reason: str = ""


class ScannerAIIntegration:
    """
    Scanner AI 集成类

    在 scanner.py 的扫描流程中集成 AI 过滤
    """

    def __init__(
        self,
        enable_ai: bool = True,
        enable_quick_filter: bool = True,
        ollama_model: str = "llama3.2:3b",
        ollama_url: str = "http://localhost:11434"
    ):
        """
        Args:
            enable_ai: 是否启用 AI 分析
            enable_quick_filter: 是否启用快速规则过滤
            ollama_model: Ollama 模型名称
            ollama_url: Ollama 服务地址
        """
        self.enable_ai = enable_ai
        self.enable_quick_filter = enable_quick_filter
        self.ollama_model = ollama_model
        self.ollama_url = ollama_url

        self.detector: Optional[SmartDetector] = None
        self.initialized = False

        # 统计
        self.stats = {
            "total_candidates": 0,
            "quick_filtered": 0,
            "ai_filtered": 0,
            "passed_to_validate": 0
        }

    async def initialize(self) -> bool:
        """初始化 AI 检测器"""
        if self.initialized:
            return True

        try:
            # 尝试初始化 Ollama 后端
            if self.enable_ai:
                backend = OllamaBackend(
                    base_url=self.ollama_url,
                    model=self.ollama_model
                )

                if await backend.is_available():
                    ai_detector = AIDetector(backend=backend)
                    self.detector = SmartDetector(ai_detector=ai_detector)
                    logger.info(f"AI 检测器已初始化 (Ollama: {self.ollama_model})")
                else:
                    # 降级到 Mock 后端
                    logger.warning("Ollama 不可用，使用规则引擎模式")
                    ai_detector = AIDetector(backend=MockBackend())
                    self.detector = SmartDetector(ai_detector=ai_detector)
            else:
                # 仅使用规则过滤
                ai_detector = AIDetector(backend=MockBackend())
                self.detector = SmartDetector(ai_detector=ai_detector)
                logger.info("AI 检测器已初始化 (规则引擎模式)")

            await self.detector.initialize()
            self.initialized = True
            return True

        except Exception as e:
            logger.error(f"AI 检测器初始化失败: {e}")
            # 创建降级检测器
            ai_detector = AIDetector(backend=MockBackend())
            self.detector = SmartDetector(ai_detector=ai_detector)
            self.initialized = True
            return False

    async def filter_candidate(
        self,
        platform: str,
        api_key: str,
        code_snippet: str,
        file_path: str = "",
        base_url: str = "",
        source_url: str = ""
    ) -> FilteredScanResult:
        """
        过滤候选 Key

        Args:
            platform: 平台名称
            api_key: 候选 API Key
            code_snippet: 代码片段
            file_path: 文件路径
            base_url: Base URL
            source_url: 来源 URL

        Returns:
            过滤后的结果
        """
        self.stats["total_candidates"] += 1

        # 确保已初始化
        if not self.initialized:
            await self.initialize()

        # 创建代码上下文
        context = CodeContext(
            code_snippet=code_snippet,
            file_path=file_path
        )

        # 执行检测
        should_validate, ai_result = await self.detector.should_validate(
            candidate_key=api_key,
            code_context=context,
            use_ai=self.enable_ai
        )

        # 构建结果
        result = FilteredScanResult(
            platform=platform,
            api_key=api_key,
            base_url=base_url,
            source_url=source_url,
            file_sha="",
            code_snippet=code_snippet,
            file_path=file_path,
            ai_result=ai_result,
            should_validate=should_validate,
            filter_reason="" if should_validate else ai_result.reasoning
        )

        # 更新统计
        if not should_validate:
            if ai_result.confidence == Confidence.NONE:
                self.stats["quick_filtered"] += 1
            else:
                self.stats["ai_filtered"] += 1
        else:
            self.stats["passed_to_validate"] += 1

        return result

    async def filter_batch(
        self,
        candidates: List[dict],
        concurrency: int = 10
    ) -> List[FilteredScanResult]:
        """
        批量过滤候选 Key

        Args:
            candidates: 候选列表 [{"platform": ..., "api_key": ..., "code_snippet": ...}, ...]
            concurrency: 并发数

        Returns:
            过滤后的结果列表
        """
        semaphore = asyncio.Semaphore(concurrency)

        async def filter_with_semaphore(candidate: dict) -> FilteredScanResult:
            async with semaphore:
                return await self.filter_candidate(
                    platform=candidate.get("platform", "unknown"),
                    api_key=candidate.get("api_key", ""),
                    code_snippet=candidate.get("code_snippet", ""),
                    file_path=candidate.get("file_path", ""),
                    base_url=candidate.get("base_url", ""),
                    source_url=candidate.get("source_url", "")
                )

        tasks = [filter_with_semaphore(c) for c in candidates]
        return await asyncio.gather(*tasks)

    def get_stats(self) -> dict:
        """获取统计信息"""
        stats = self.stats.copy()

        if self.detector:
            stats["detector_stats"] = self.detector.get_stats()

        # 计算过滤率
        if stats["total_candidates"] > 0:
            stats["filter_rate"] = (
                stats["quick_filtered"] + stats["ai_filtered"]
            ) / stats["total_candidates"] * 100
        else:
            stats["filter_rate"] = 0.0

        return stats


# ============================================================================
#                         Scanner 补丁函数
# ============================================================================

def patch_scanner_with_ai(scanner_module, ai_integration: ScannerAIIntegration = None):
    """
    为 Scanner 模块添加 AI 过滤功能

    Usage:
        from scanner import *
        from ai_scanner_integration import patch_scanner_with_ai, ScannerAIIntegration

        ai_integration = ScannerAIIntegration()
        patch_scanner_with_ai(scanner_module, ai_integration)
    """
    if ai_integration is None:
        ai_integration = ScannerAIIntegration()

    # 保存原始的 extract_keys 函数
    if hasattr(scanner_module, 'extract_keys_from_content'):
        original_extract = scanner_module.extract_keys_from_content

        async def patched_extract(content: str, source_url: str = "", file_path: str = ""):
            # 调用原始提取函数
            results = original_extract(content, source_url, file_path)

            if not results:
                return results

            # 确保 AI 集成已初始化
            if not ai_integration.initialized:
                await ai_integration.initialize()

            # 过滤结果
            filtered_results = []
            for result in results:
                filtered = await ai_integration.filter_candidate(
                    platform=result.platform if hasattr(result, 'platform') else 'unknown',
                    api_key=result.api_key if hasattr(result, 'api_key') else str(result),
                    code_snippet=content[:1000],  # 限制上下文长度
                    file_path=file_path,
                    base_url=result.base_url if hasattr(result, 'base_url') else '',
                    source_url=source_url
                )

                if filtered.should_validate:
                    filtered_results.append(result)
                else:
                    logger.debug(f"AI 过滤: {filtered.filter_reason}")

            return filtered_results

        scanner_module.extract_keys_from_content = patched_extract
        logger.info("已为 Scanner 添加 AI 过滤补丁")


# ============================================================================
#                         便捷函数
# ============================================================================

_global_ai_integration: Optional[ScannerAIIntegration] = None


async def get_ai_integration() -> ScannerAIIntegration:
    """获取全局 AI 集成实例"""
    global _global_ai_integration

    if _global_ai_integration is None:
        _global_ai_integration = ScannerAIIntegration()
        await _global_ai_integration.initialize()

    return _global_ai_integration


async def should_validate_key(
    api_key: str,
    code_snippet: str = "",
    file_path: str = "",
    platform: str = "unknown"
) -> Tuple[bool, str]:
    """
    便捷函数：判断候选 Key 是否应该验证

    Returns:
        (should_validate, reason)
    """
    integration = await get_ai_integration()
    result = await integration.filter_candidate(
        platform=platform,
        api_key=api_key,
        code_snippet=code_snippet,
        file_path=file_path
    )

    return result.should_validate, result.filter_reason


# ============================================================================
#                         配置类
# ============================================================================

@dataclass
class AIConfig:
    """AI 检测配置"""
    enabled: bool = True
    backend: str = "ollama"  # ollama, openai, mock
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    openai_api_key: str = ""
    openai_model: str = "gpt-3.5-turbo"
    quick_filter_enabled: bool = True
    cache_enabled: bool = True
    cache_size: int = 1000

    @classmethod
    def from_env(cls) -> "AIConfig":
        """从环境变量加载配置"""
        import os
        return cls(
            enabled=os.getenv("AI_DETECTOR_ENABLED", "true").lower() == "true",
            backend=os.getenv("AI_DETECTOR_BACKEND", "ollama"),
            ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
            ollama_model=os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
            quick_filter_enabled=os.getenv("AI_QUICK_FILTER", "true").lower() == "true",
            cache_enabled=os.getenv("AI_CACHE_ENABLED", "true").lower() == "true",
            cache_size=int(os.getenv("AI_CACHE_SIZE", "1000")),
        )

    @classmethod
    def from_yaml(cls, path: str) -> "AIConfig":
        """从 YAML 文件加载配置"""
        import yaml
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        ai_config = data.get('ai_detector', {})
        return cls(
            enabled=ai_config.get('enabled', True),
            backend=ai_config.get('backend', 'ollama'),
            ollama_url=ai_config.get('ollama_url', 'http://localhost:11434'),
            ollama_model=ai_config.get('ollama_model', 'llama3.2:3b'),
            openai_api_key=ai_config.get('openai_api_key', ''),
            openai_model=ai_config.get('openai_model', 'gpt-3.5-turbo'),
            quick_filter_enabled=ai_config.get('quick_filter_enabled', True),
            cache_enabled=ai_config.get('cache_enabled', True),
            cache_size=ai_config.get('cache_size', 1000),
        )
