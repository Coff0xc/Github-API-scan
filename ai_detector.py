"""
AI 辅助检测模块 - 使用 LLM 进行智能密钥识别
============================================

核心功能:
1. 上下文感知检测 - 分析代码片段判断是否为真实 Key
2. 假阳性过滤 - 识别测试/示例/占位符 Key
3. 平台智能识别 - 自动判断 Key 所属平台
4. 置信度评估 - 输出检测结果的置信度

支持的 LLM 后端:
- Ollama (本地模型，推荐)
- OpenAI API (远程，需要 Key)
- Azure OpenAI
- 自定义 API 端点

参考技术:
- GitHub Copilot MetaReflection 技术 (94% 假阳性减少)
- Few-shot prompting
- Chain of Thought (CoT)
"""

import os
import re
import json
import asyncio
import hashlib
from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from collections import deque

import aiohttp
from aiohttp import ClientTimeout
from loguru import logger


# ============================================================================
#                              数据模型
# ============================================================================

class Confidence(Enum):
    """检测置信度"""
    NONE = "none"        # 不是 API Key
    LOW = "low"          # 可能是 Key，但不确定
    MEDIUM = "medium"    # 较可能是 Key
    HIGH = "high"        # 高度确信是 Key

    @property
    def score(self) -> float:
        return {
            Confidence.NONE: 0.0,
            Confidence.LOW: 0.3,
            Confidence.MEDIUM: 0.6,
            Confidence.HIGH: 0.9,
        }[self]


class KeyType(Enum):
    """Key 类型分类"""
    REAL = "real"              # 真实 Key
    TEST = "test"              # 测试 Key (sk-test-xxx)
    EXAMPLE = "example"        # 示例 Key (文档中的)
    PLACEHOLDER = "placeholder"  # 占位符 (YOUR_API_KEY)
    FAKE = "fake"              # 明显假的 Key
    UNKNOWN = "unknown"        # 无法判断


@dataclass
class AIDetectionResult:
    """AI 检测结果"""
    candidate_key: str              # 候选 Key
    confidence: Confidence          # 置信度
    key_type: KeyType               # Key 类型
    provider: str                   # 识别的平台 (openai, anthropic, etc.)
    reasoning: str                  # 推理过程
    context_indicators: List[str]   # 上下文指标
    is_likely_real: bool            # 是否可能是真实 Key
    raw_response: str = ""          # LLM 原始响应

    @property
    def should_validate(self) -> bool:
        """是否应该进行验证"""
        return (
            self.is_likely_real and
            self.confidence in [Confidence.MEDIUM, Confidence.HIGH] and
            self.key_type == KeyType.REAL
        )


@dataclass
class CodeContext:
    """代码上下文"""
    code_snippet: str           # 代码片段
    file_path: str = ""         # 文件路径
    line_number: int = 0        # 行号
    surrounding_lines: int = 5  # 上下文行数
    language: str = ""          # 编程语言

    def get_context_window(self, before: int = 3, after: int = 3) -> str:
        """获取上下文窗口"""
        lines = self.code_snippet.split('\n')
        # 简化：返回整个片段
        return self.code_snippet


# ============================================================================
#                              LLM 后端抽象
# ============================================================================

class LLMBackend(ABC):
    """LLM 后端抽象基类"""

    def __init__(self, name: str):
        self.name = name
        self.request_count = 0
        self.total_tokens = 0

    @abstractmethod
    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        """生成响应"""
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """检查是否可用"""
        pass


class OllamaBackend(LLMBackend):
    """
    Ollama 本地模型后端

    推荐模型:
    - llama3.2:3b (快速，适合初筛)
    - llama3.1:8b (平衡)
    - qwen2.5:7b (中文友好)
    - mistral:7b (高质量)
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2:3b",
        timeout: int = 30
    ):
        super().__init__("Ollama")
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = ClientTimeout(total=timeout)

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        url = f"{self.base_url}/api/generate"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,  # 低温度，更确定性
                "num_predict": 500,   # 限制输出长度
            }
        }

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self.request_count += 1
                        self.total_tokens += data.get("eval_count", 0)
                        return data.get("response", "")
                    else:
                        logger.warning(f"Ollama 请求失败: {resp.status}")
                        return ""
        except Exception as e:
            logger.error(f"Ollama 异常: {e}")
            return ""

    async def is_available(self) -> bool:
        try:
            async with aiohttp.ClientSession(timeout=ClientTimeout(total=5)) as session:
                async with session.get(f"{self.base_url}/api/tags") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        models = [m["name"] for m in data.get("models", [])]
                        # 检查模型是否存在
                        model_base = self.model.split(':')[0]
                        return any(model_base in m for m in models)
                    return False
        except Exception:
            return False


class OpenAIBackend(LLMBackend):
    """
    OpenAI API 后端

    支持:
    - OpenAI 官方 API
    - Azure OpenAI
    - 兼容 OpenAI API 的中转站
    """

    def __init__(
        self,
        api_key: str = None,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-3.5-turbo",
        timeout: int = 30
    ):
        super().__init__("OpenAI")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = ClientTimeout(total=timeout)

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.api_key:
            logger.warning("OpenAI API Key 未配置")
            return ""

        url = f"{self.base_url}/chat/completions"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 500,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self.request_count += 1
                        usage = data.get("usage", {})
                        self.total_tokens += usage.get("total_tokens", 0)
                        return data["choices"][0]["message"]["content"]
                    else:
                        text = await resp.text()
                        logger.warning(f"OpenAI 请求失败: {resp.status} - {text[:100]}")
                        return ""
        except Exception as e:
            logger.error(f"OpenAI 异常: {e}")
            return ""

    async def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            async with aiohttp.ClientSession(timeout=ClientTimeout(total=10)) as session:
                async with session.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"}
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False


class MockBackend(LLMBackend):
    """
    模拟后端 - 用于测试和无 LLM 环境

    使用规则引擎模拟 AI 检测
    """

    def __init__(self):
        super().__init__("Mock")

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        # 从 prompt 中提取候选 Key
        import re

        # 简单的规则引擎
        result = {
            "confidence": "MEDIUM",
            "key_type": "REAL",
            "provider": "unknown",
            "reasoning": "基于规则引擎分析",
            "is_likely_real": True
        }

        # 检测测试 Key
        test_patterns = [
            r'test', r'demo', r'example', r'sample', r'fake',
            r'xxx+', r'your[_-]?api[_-]?key', r'placeholder',
            r'insert[_-]?here', r'replace[_-]?me'
        ]

        prompt_lower = prompt.lower()
        for pattern in test_patterns:
            if re.search(pattern, prompt_lower):
                result["confidence"] = "LOW"
                result["key_type"] = "TEST"
                result["is_likely_real"] = False
                result["reasoning"] = f"检测到测试模式: {pattern}"
                break

        # 检测平台
        if "sk-" in prompt:
            result["provider"] = "openai"
        elif "sk-ant-" in prompt:
            result["provider"] = "anthropic"
        elif "AIzaSy" in prompt:
            result["provider"] = "google"
        elif "gsk_" in prompt:
            result["provider"] = "groq"

        return json.dumps(result)

    async def is_available(self) -> bool:
        return True


# ============================================================================
#                              AI 检测器核心
# ============================================================================

# 系统 Prompt - 使用 MetaReflection 技术
SYSTEM_PROMPT = """You are an expert security analyst specializing in API key detection and classification.

Your task is to analyze code snippets and determine if they contain real, valid API keys that should be reported as security issues.

Classification Guidelines:

1. REAL API Keys (should report):
   - Have proper format for the platform (sk-proj-, AIzaSy, etc.)
   - Appear in production code, config files, or environment variables
   - Have high entropy (random-looking characters)
   - Are NOT in comments explaining what format keys should look like

2. TEST/FAKE Keys (should NOT report):
   - Contain words like: test, demo, example, sample, fake, placeholder
   - Have patterns like: xxx, your_api_key, INSERT_HERE, <API_KEY>
   - Are in documentation or comments as examples
   - Have low entropy (repeating patterns)
   - Are clearly placeholder values

3. Context Indicators for REAL keys:
   - Used with actual API calls (requests.post, fetch, axios)
   - Stored in .env files, config.json, settings.py
   - Assigned to variables like api_key, secret_key, token
   - No surrounding documentation explaining format

4. Context Indicators for FAKE keys:
   - In README files or documentation
   - Surrounded by comments like "# Replace with your key"
   - In test files or mock data
   - Have generic placeholder names

Output your analysis as JSON with these fields:
- confidence: "NONE" | "LOW" | "MEDIUM" | "HIGH"
- key_type: "REAL" | "TEST" | "EXAMPLE" | "PLACEHOLDER" | "FAKE"
- provider: detected platform (openai, anthropic, google, aws, etc.)
- reasoning: brief explanation of your decision
- is_likely_real: boolean"""


# Few-shot 示例
FEW_SHOT_EXAMPLES = [
    {
        "input": """
# config.py
OPENAI_API_KEY = "sk-proj-abc123def456ghi789jkl012mno345pqr678stu901vwx234yz"
client = OpenAI(api_key=OPENAI_API_KEY)
""",
        "output": {
            "confidence": "HIGH",
            "key_type": "REAL",
            "provider": "openai",
            "reasoning": "Real key in config file, used with actual OpenAI client, high entropy",
            "is_likely_real": True
        }
    },
    {
        "input": """
# Example usage:
# api_key = "sk-test-your-api-key-here"
# Replace with your actual API key
""",
        "output": {
            "confidence": "NONE",
            "key_type": "PLACEHOLDER",
            "provider": "openai",
            "reasoning": "Clearly a placeholder in documentation with 'test' and 'your-api-key' patterns",
            "is_likely_real": False
        }
    },
    {
        "input": """
const GEMINI_KEY = "AIzaSyDxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx";
fetch(`https://generativelanguage.googleapis.com/v1beta/models?key=${GEMINI_KEY}`)
""",
        "output": {
            "confidence": "LOW",
            "key_type": "TEST",
            "provider": "google",
            "reasoning": "Contains 'xxx' pattern indicating placeholder, despite being used in code",
            "is_likely_real": False
        }
    },
    {
        "input": """
.env file:
ANTHROPIC_API_KEY=sk-ant-api03-Kj8mN2pL5qR7tX9vY1wZ3aB4cD6eF8gH0iJ2kL4mN6oP8qR0sT2uV4wX6yZ8
""",
        "output": {
            "confidence": "HIGH",
            "key_type": "REAL",
            "provider": "anthropic",
            "reasoning": "Real Anthropic key format in .env file, high entropy, no placeholder indicators",
            "is_likely_real": True
        }
    }
]


class AIDetector:
    """
    AI 辅助密钥检测器

    使用 LLM 进行上下文感知的密钥检测，
    显著降低假阳性率（参考 GitHub Copilot 94% 减少）
    """

    def __init__(
        self,
        backend: LLMBackend = None,
        use_few_shot: bool = True,
        cache_enabled: bool = True,
        cache_size: int = 1000
    ):
        """
        初始化 AI 检测器

        Args:
            backend: LLM 后端，默认尝试 Ollama -> Mock
            use_few_shot: 是否使用 few-shot 示例
            cache_enabled: 是否启用缓存
            cache_size: 缓存大小
        """
        self.backend = backend
        self.use_few_shot = use_few_shot
        self.cache_enabled = cache_enabled
        self._cache: Dict[str, AIDetectionResult] = {}
        self._cache_order: deque = deque(maxlen=cache_size)

        # 统计
        self.stats = {
            "total_analyzed": 0,
            "cache_hits": 0,
            "real_detected": 0,
            "fake_filtered": 0,
            "errors": 0
        }

    async def initialize(self) -> bool:
        """初始化检测器，自动选择可用后端"""
        if self.backend and await self.backend.is_available():
            logger.info(f"AI 检测器使用后端: {self.backend.name}")
            return True

        # 尝试 Ollama
        ollama = OllamaBackend()
        if await ollama.is_available():
            self.backend = ollama
            logger.info(f"AI 检测器使用 Ollama: {ollama.model}")
            return True

        # 尝试 OpenAI
        if os.getenv("OPENAI_API_KEY"):
            openai = OpenAIBackend()
            if await openai.is_available():
                self.backend = openai
                logger.info("AI 检测器使用 OpenAI API")
                return True

        # 降级到 Mock
        self.backend = MockBackend()
        logger.warning("AI 检测器使用模拟后端（规则引擎）")
        return True

    def _build_prompt(self, code_context: CodeContext, candidate_key: str) -> str:
        """构建检测 prompt"""
        prompt_parts = []

        # Few-shot 示例
        if self.use_few_shot:
            prompt_parts.append("Here are some examples of how to analyze API keys:\n")
            for i, example in enumerate(FEW_SHOT_EXAMPLES[:2], 1):  # 只用2个示例节省 token
                prompt_parts.append(f"Example {i}:")
                prompt_parts.append(f"Input:\n```\n{example['input'].strip()}\n```")
                prompt_parts.append(f"Output: {json.dumps(example['output'])}\n")

        # 当前任务
        prompt_parts.append("Now analyze this code snippet:")
        prompt_parts.append(f"```\n{code_context.code_snippet}\n```")
        prompt_parts.append(f"\nCandidate API Key: {candidate_key}")

        if code_context.file_path:
            prompt_parts.append(f"File: {code_context.file_path}")

        prompt_parts.append("\nProvide your analysis as JSON:")

        return "\n".join(prompt_parts)

    def _parse_response(self, response: str, candidate_key: str) -> AIDetectionResult:
        """解析 LLM 响应"""
        try:
            # 尝试提取 JSON
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                # 尝试直接解析
                data = json.loads(response)

            return AIDetectionResult(
                candidate_key=candidate_key,
                confidence=Confidence[data.get("confidence", "LOW").upper()],
                key_type=KeyType[data.get("key_type", "UNKNOWN").upper()],
                provider=data.get("provider", "unknown"),
                reasoning=data.get("reasoning", ""),
                context_indicators=data.get("context_indicators", []),
                is_likely_real=data.get("is_likely_real", False),
                raw_response=response
            )
        except Exception as e:
            logger.debug(f"解析 LLM 响应失败: {e}")
            # 返回保守结果
            return AIDetectionResult(
                candidate_key=candidate_key,
                confidence=Confidence.MEDIUM,
                key_type=KeyType.UNKNOWN,
                provider="unknown",
                reasoning=f"解析失败，保守处理: {str(e)[:50]}",
                context_indicators=[],
                is_likely_real=True,  # 保守：宁可误报也不漏报
                raw_response=response
            )

    def _get_cache_key(self, code_context: CodeContext, candidate_key: str) -> str:
        """生成缓存键"""
        content = f"{code_context.code_snippet}:{candidate_key}"
        return hashlib.md5(content.encode()).hexdigest()

    async def analyze(
        self,
        code_context: CodeContext,
        candidate_key: str
    ) -> AIDetectionResult:
        """
        分析代码上下文中的候选 Key

        Args:
            code_context: 代码上下文
            candidate_key: 候选 API Key

        Returns:
            AI 检测结果
        """
        self.stats["total_analyzed"] += 1

        # 检查缓存
        if self.cache_enabled:
            cache_key = self._get_cache_key(code_context, candidate_key)
            if cache_key in self._cache:
                self.stats["cache_hits"] += 1
                return self._cache[cache_key]

        # 确保后端已初始化
        if not self.backend:
            await self.initialize()

        try:
            # 构建 prompt
            prompt = self._build_prompt(code_context, candidate_key)

            # 调用 LLM
            response = await self.backend.generate(prompt, SYSTEM_PROMPT)

            if not response:
                # LLM 无响应，返回保守结果
                return AIDetectionResult(
                    candidate_key=candidate_key,
                    confidence=Confidence.MEDIUM,
                    key_type=KeyType.UNKNOWN,
                    provider="unknown",
                    reasoning="LLM 无响应，保守处理",
                    context_indicators=[],
                    is_likely_real=True
                )

            # 解析响应
            result = self._parse_response(response, candidate_key)

            # 更新统计
            if result.is_likely_real:
                self.stats["real_detected"] += 1
            else:
                self.stats["fake_filtered"] += 1

            # 缓存结果
            if self.cache_enabled:
                self._cache[cache_key] = result
                self._cache_order.append(cache_key)

                # 清理超出容量的缓存
                while len(self._cache) > self._cache_order.maxlen:
                    old_key = self._cache_order.popleft()
                    self._cache.pop(old_key, None)

            return result

        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"AI 检测异常: {e}")

            # 返回保守结果
            return AIDetectionResult(
                candidate_key=candidate_key,
                confidence=Confidence.MEDIUM,
                key_type=KeyType.UNKNOWN,
                provider="unknown",
                reasoning=f"检测异常: {str(e)[:50]}",
                context_indicators=[],
                is_likely_real=True  # 保守：异常时不过滤
            )

    async def batch_analyze(
        self,
        items: List[Tuple[CodeContext, str]],
        concurrency: int = 5
    ) -> List[AIDetectionResult]:
        """
        批量分析

        Args:
            items: [(代码上下文, 候选Key), ...]
            concurrency: 并发数

        Returns:
            检测结果列表
        """
        semaphore = asyncio.Semaphore(concurrency)

        async def analyze_with_semaphore(ctx: CodeContext, key: str):
            async with semaphore:
                return await self.analyze(ctx, key)

        tasks = [analyze_with_semaphore(ctx, key) for ctx, key in items]
        return await asyncio.gather(*tasks)

    def get_stats(self) -> dict:
        """获取统计信息"""
        stats = self.stats.copy()
        if self.backend:
            stats["backend"] = self.backend.name
            stats["backend_requests"] = self.backend.request_count
            stats["backend_tokens"] = self.backend.total_tokens
        stats["cache_size"] = len(self._cache)
        return stats


# ============================================================================
#                              快速过滤器 (无需 LLM)
# ============================================================================

class QuickFilter:
    """
    快速过滤器 - 使用规则引擎预筛选

    在调用 LLM 之前先用规则快速过滤明显的假 Key，
    节省 LLM 调用成本
    """

    # 测试 Key 模式
    TEST_PATTERNS = [
        r'test',
        r'demo',
        r'example',
        r'sample',
        r'fake',
        r'dummy',
        r'mock',
        r'placeholder',
        r'your[_-]?api[_-]?key',
        r'insert[_-]?here',
        r'replace[_-]?me',
        r'xxx+',
        r'aaa+',
        r'123+',
        r'abc+',
        r'\*{3,}',
        r'<[^>]+>',  # <API_KEY>
        r'\$\{[^}]+\}',  # ${API_KEY}
        r'\{\{[^}]+\}\}',  # {{API_KEY}}
    ]

    # 文档/示例文件模式
    DOC_FILE_PATTERNS = [
        r'readme',
        r'example',
        r'sample',
        r'demo',
        r'test',
        r'mock',
        r'docs?/',
        r'documentation',
        r'\.md$',
        r'\.rst$',
        r'\.txt$',
    ]

    # 注释指示器
    COMMENT_INDICATORS = [
        '# example',
        '# replace',
        '# your',
        '// example',
        '// replace',
        '/* example',
        '<!-- example',
        'TODO:',
        'FIXME:',
    ]

    def __init__(self):
        self.test_regex = re.compile(
            '|'.join(self.TEST_PATTERNS),
            re.IGNORECASE
        )
        self.doc_regex = re.compile(
            '|'.join(self.DOC_FILE_PATTERNS),
            re.IGNORECASE
        )

    def is_likely_fake(self, candidate_key: str, context: str = "", file_path: str = "") -> Tuple[bool, str]:
        """
        快速判断是否为假 Key

        Returns:
            (is_fake, reason)
        """
        key_lower = candidate_key.lower()
        context_lower = context.lower()

        # 1. 检查 Key 本身是否包含测试模式
        if self.test_regex.search(key_lower):
            match = self.test_regex.search(key_lower)
            return True, f"Key 包含测试模式: {match.group()}"

        # 2. 检查文件路径
        if file_path and self.doc_regex.search(file_path.lower()):
            return True, f"文件路径表明是文档/测试文件"

        # 3. 检查上下文中的注释指示器
        for indicator in self.COMMENT_INDICATORS:
            if indicator.lower() in context_lower:
                return True, f"上下文包含指示器: {indicator}"

        # 4. 检查 Key 熵值 (低熵值 = 假 Key)
        entropy = self._calculate_entropy(candidate_key)
        if entropy < 3.0:
            return True, f"熵值过低: {entropy:.2f}"

        # 5. 检查重复模式
        if self._has_repeating_pattern(candidate_key):
            return True, "Key 包含重复模式"

        return False, ""

    @staticmethod
    def _calculate_entropy(s: str) -> float:
        """计算字符串熵值"""
        import math
        if not s:
            return 0.0
        freq = {}
        for c in s:
            freq[c] = freq.get(c, 0) + 1
        entropy = 0.0
        for count in freq.values():
            p = count / len(s)
            entropy -= p * math.log2(p)
        return entropy

    @staticmethod
    def _has_repeating_pattern(s: str, min_repeat: int = 3) -> bool:
        """检查是否有重复模式"""
        # 检查连续重复字符
        for i in range(len(s) - min_repeat):
            if s[i] == s[i+1] == s[i+2]:
                return True

        # 检查重复子串
        for length in range(2, min(6, len(s) // 3)):
            pattern = s[:length]
            if s.startswith(pattern * 3):
                return True

        return False


# ============================================================================
#                              组合检测器
# ============================================================================

class SmartDetector:
    """
    智能组合检测器

    结合快速规则过滤 + AI 深度分析，
    在准确性和性能之间取得平衡
    """

    def __init__(
        self,
        ai_detector: AIDetector = None,
        quick_filter: QuickFilter = None,
        ai_threshold: Confidence = Confidence.LOW
    ):
        """
        Args:
            ai_detector: AI 检测器
            quick_filter: 快速过滤器
            ai_threshold: 触发 AI 分析的最低置信度
        """
        self.ai_detector = ai_detector or AIDetector()
        self.quick_filter = quick_filter or QuickFilter()
        self.ai_threshold = ai_threshold

        self.stats = {
            "total_processed": 0,
            "quick_filtered": 0,
            "ai_analyzed": 0,
            "final_passed": 0
        }

    async def initialize(self) -> bool:
        """初始化"""
        return await self.ai_detector.initialize()

    async def should_validate(
        self,
        candidate_key: str,
        code_context: CodeContext = None,
        use_ai: bool = True
    ) -> Tuple[bool, AIDetectionResult]:
        """
        判断候选 Key 是否应该进行验证

        Args:
            candidate_key: 候选 Key
            code_context: 代码上下文 (如果为 None，只进行规则检测)
            use_ai: 是否使用 AI 分析

        Returns:
            (should_validate, detection_result)
        """
        self.stats["total_processed"] += 1

        # Step 1: 快速规则过滤
        context_str = code_context.code_snippet if code_context else ""
        file_path = code_context.file_path if code_context else ""

        is_fake, reason = self.quick_filter.is_likely_fake(
            candidate_key, context_str, file_path
        )

        if is_fake:
            self.stats["quick_filtered"] += 1
            return False, AIDetectionResult(
                candidate_key=candidate_key,
                confidence=Confidence.NONE,
                key_type=KeyType.FAKE,
                provider="unknown",
                reasoning=f"快速过滤: {reason}",
                context_indicators=[],
                is_likely_real=False
            )

        # Step 2: AI 深度分析 (可选)
        if use_ai and code_context:
            self.stats["ai_analyzed"] += 1
            result = await self.ai_detector.analyze(code_context, candidate_key)

            if not result.should_validate:
                return False, result

            self.stats["final_passed"] += 1
            return True, result

        # 没有上下文或不使用 AI，默认通过
        self.stats["final_passed"] += 1
        return True, AIDetectionResult(
            candidate_key=candidate_key,
            confidence=Confidence.MEDIUM,
            key_type=KeyType.UNKNOWN,
            provider="unknown",
            reasoning="无上下文，默认通过",
            context_indicators=[],
            is_likely_real=True
        )

    def get_stats(self) -> dict:
        """获取统计信息"""
        stats = self.stats.copy()
        stats["ai_stats"] = self.ai_detector.get_stats()

        # 计算过滤率
        if stats["total_processed"] > 0:
            stats["filter_rate"] = (
                stats["quick_filtered"] +
                stats["ai_analyzed"] - stats["final_passed"]
            ) / stats["total_processed"]
        else:
            stats["filter_rate"] = 0.0

        return stats


# ============================================================================
#                              全局实例
# ============================================================================

_smart_detector: Optional[SmartDetector] = None


async def get_smart_detector() -> SmartDetector:
    """获取全局智能检测器实例"""
    global _smart_detector
    if _smart_detector is None:
        _smart_detector = SmartDetector()
        await _smart_detector.initialize()
    return _smart_detector


async def init_smart_detector(
    backend: LLMBackend = None,
    use_ai: bool = True
) -> SmartDetector:
    """初始化全局智能检测器"""
    global _smart_detector

    if backend:
        ai_detector = AIDetector(backend=backend)
    else:
        ai_detector = AIDetector()

    _smart_detector = SmartDetector(ai_detector=ai_detector)
    await _smart_detector.initialize()

    return _smart_detector
