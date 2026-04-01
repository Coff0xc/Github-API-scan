# AI 辅助检测模块 使用说明

## 概述

AI 辅助检测模块使用大语言模型 (LLM) 进行上下文感知的 API Key 检测，能够显著降低假阳性率。

**核心优势**:
- 🎯 **94% 假阳性减少** - 参考 GitHub Copilot MetaReflection 技术
- 🧠 **上下文感知** - 理解代码语义，识别真实 vs 测试 Key
- ⚡ **双层过滤** - 规则引擎快速筛选 + AI 深度分析
- 💰 **成本优化** - 优先使用本地 Ollama，节省 API 费用

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                    SmartDetector (智能检测器)                │
├────────────────────────────┬────────────────────────────────┤
│      QuickFilter           │         AIDetector             │
│      (规则引擎)             │         (LLM 分析)             │
│                            │                                │
│  • 测试模式检测            │  • Ollama 本地模型             │
│  • 熵值计算                │  • OpenAI API                  │
│  • 重复模式识别            │  • Few-shot 提示               │
│  • 文件路径分析            │  • Chain of Thought            │
└────────────────────────────┴────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │   检测结果        │
                    │  • 置信度         │
                    │  • Key 类型       │
                    │  • 平台识别       │
                    │  • 推理过程       │
                    └──────────────────┘
```

## 快速开始

### 1. 安装 Ollama (推荐)

```bash
# Linux/Mac
curl -fsSL https://ollama.ai/install.sh | sh

# Windows
# 从 https://ollama.ai/download 下载安装

# 拉取模型 (选择一个)
ollama pull llama3.2:3b    # 快速，适合初筛 (推荐)
ollama pull llama3.1:8b    # 平衡
ollama pull qwen2.5:7b     # 中文友好
ollama pull mistral:7b     # 高质量

# 验证
ollama list
```

### 2. 运行测试

```bash
# 检查后端可用性
python test_ai_detector.py --check

# 运行完整测试
python test_ai_detector.py --all

# 交互式测试
python test_ai_detector.py --interactive
```

### 3. 在代码中使用

```python
from ai_detector import SmartDetector, CodeContext

# 创建检测器
detector = SmartDetector()
await detector.initialize()

# 分析代码片段
context = CodeContext(
    code_snippet='''
    OPENAI_API_KEY = "sk-proj-abc123..."
    client = OpenAI(api_key=OPENAI_API_KEY)
    ''',
    file_path="config.py"
)

should_validate, result = await detector.should_validate(
    candidate_key="sk-proj-abc123...",
    code_context=context
)

if should_validate:
    print(f"应该验证: {result.provider} Key")
else:
    print(f"跳过: {result.reasoning}")
```

## 检测结果

### 置信度级别

| 级别 | 说明 | 处理建议 |
|------|------|---------|
| `HIGH` | 高度确信是真实 Key | 立即验证 |
| `MEDIUM` | 较可能是真实 Key | 验证 |
| `LOW` | 可能是 Key，但不确定 | 可选验证 |
| `NONE` | 不是 API Key | 跳过 |

### Key 类型

| 类型 | 说明 | 示例 |
|------|------|------|
| `REAL` | 真实 Key | 配置文件中的 Key |
| `TEST` | 测试 Key | `sk-test-xxx` |
| `EXAMPLE` | 示例 Key | 文档中的示例 |
| `PLACEHOLDER` | 占位符 | `YOUR_API_KEY` |
| `FAKE` | 明显假的 Key | `sk-xxxxxxxxxxxx` |

## 配置

### 环境变量

```bash
# AI 检测器开关
export AI_DETECTOR_ENABLED=true

# 后端选择: ollama, openai, mock
export AI_DETECTOR_BACKEND=ollama

# Ollama 配置
export OLLAMA_URL=http://localhost:11434
export OLLAMA_MODEL=llama3.2:3b

# OpenAI 配置 (备选)
export OPENAI_API_KEY=sk-xxx
export OPENAI_MODEL=gpt-3.5-turbo

# 快速过滤器
export AI_QUICK_FILTER=true

# 缓存
export AI_CACHE_ENABLED=true
export AI_CACHE_SIZE=1000
```

### YAML 配置

在 `notify_config.yaml` 中添加:

```yaml
ai_detector:
  enabled: true
  backend: ollama  # ollama, openai, mock

  # Ollama 配置
  ollama_url: http://localhost:11434
  ollama_model: llama3.2:3b

  # OpenAI 配置 (备选)
  openai_api_key: ""
  openai_model: gpt-3.5-turbo

  # 快速过滤器
  quick_filter_enabled: true

  # 缓存
  cache_enabled: true
  cache_size: 1000
```

## 集成到 Scanner

### 方式一: 直接使用

```python
from ai_scanner_integration import ScannerAIIntegration

# 创建集成实例
ai_integration = ScannerAIIntegration(
    enable_ai=True,
    ollama_model="llama3.2:3b"
)
await ai_integration.initialize()

# 过滤候选 Key
result = await ai_integration.filter_candidate(
    platform="openai",
    api_key="sk-proj-xxx",
    code_snippet="...",
    file_path="config.py"
)

if result.should_validate:
    # 继续验证
    pass
else:
    print(f"AI 过滤: {result.filter_reason}")
```

### 方式二: 便捷函数

```python
from ai_scanner_integration import should_validate_key

should_validate, reason = await should_validate_key(
    api_key="sk-proj-xxx",
    code_snippet="...",
    file_path="config.py"
)
```

## 性能优化

### 1. 使用快速过滤器预筛选

快速过滤器使用规则引擎，无需 LLM 调用:

```python
from ai_detector import QuickFilter

quick_filter = QuickFilter()
is_fake, reason = quick_filter.is_likely_fake(
    candidate_key="sk-test-xxx",
    context="# test file",
    file_path="test.py"
)

if is_fake:
    print(f"快速过滤: {reason}")
    # 跳过 LLM 分析
```

### 2. 批量处理

```python
candidates = [
    {"platform": "openai", "api_key": "sk-xxx", "code_snippet": "..."},
    # ...
]

results = await ai_integration.filter_batch(candidates, concurrency=10)
```

### 3. 缓存

默认启用缓存，相同的代码片段+Key 组合只分析一次:

```python
detector = AIDetector(cache_enabled=True, cache_size=1000)
```

## 测试命令

```bash
# 检查后端状态
python test_ai_detector.py --check

# 测试快速过滤器
python test_ai_detector.py --quick

# 测试 AI 检测器
python test_ai_detector.py --backend ollama
python test_ai_detector.py --backend openai
python test_ai_detector.py --backend mock

# 运行所有测试
python test_ai_detector.py --all

# 交互式测试
python test_ai_detector.py --interactive
```

## 推荐模型

| 模型 | 大小 | 速度 | 质量 | 推荐场景 |
|------|------|------|------|---------|
| `llama3.2:3b` | 2GB | ⚡⚡⚡ | ⭐⭐⭐ | 快速初筛 (推荐) |
| `llama3.1:8b` | 5GB | ⚡⚡ | ⭐⭐⭐⭐ | 平衡 |
| `qwen2.5:7b` | 4GB | ⚡⚡ | ⭐⭐⭐⭐ | 中文代码 |
| `mistral:7b` | 4GB | ⚡⚡ | ⭐⭐⭐⭐⭐ | 高质量 |
| `gpt-3.5-turbo` | - | ⚡ | ⭐⭐⭐⭐⭐ | 云端备选 |

## 文件清单

```
├── ai_detector.py              # AI 检测核心模块
├── ai_scanner_integration.py   # Scanner 集成模块
├── test_ai_detector.py         # 测试脚本
└── AI_DETECTOR_README.md       # 本文档
```

## 故障排除

### Ollama 连接失败

```bash
# 检查 Ollama 服务
curl http://localhost:11434/api/tags

# 重启 Ollama
ollama serve
```

### 模型不存在

```bash
# 列出已安装模型
ollama list

# 拉取模型
ollama pull llama3.2:3b
```

### 检测结果不准确

1. 尝试使用更大的模型 (`llama3.1:8b`)
2. 检查代码上下文是否完整
3. 使用交互式测试调试

## 更新日志

### v1.0.0 (2026-01)

- 初始版本
- 支持 Ollama/OpenAI/Mock 后端
- 快速规则过滤器
- Few-shot + Chain of Thought 提示
- 结果缓存
