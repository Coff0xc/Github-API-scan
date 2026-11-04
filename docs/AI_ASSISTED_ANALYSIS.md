# AI 辅助分析接入指南

本工具内置了一个 LLM 辅助检测模块（`ai_detector.py` + `ai_scanner_integration.py`），
在**正则匹配之后、API 验证之前**对候选 Key 做上下文智能判断，过滤测试/示例/占位符
Key，减少无效验证请求。

> 原则提醒：AI 辅助分析只用于**降低假阳性**，提高自有资产审计的效率。它不改变工
> 具的使用边界（见根目录 AUTHORIZED_USE.md）。

## 它解决什么问题

正则管线会把 `sk-test-xxxx`、文档示例、脱敏占位符都当成候选 Key，而验证请求是对
目标 API 的真实网络调用。AI 层把代码片段交给 LLM 判断：

- 这是真实凭据，还是示例/测试数据？
- 上下文变量名、注释、文件类型是否表明它可用？
- 输出置信度（NONE/LOW/MEDIUM/HIGH）与理由

官方 README 声称该技术可减少 94% 假阳性（`ai_detector.py` 引 Copilot
MetaReflection 方案）。

## 接入方式（三选一）

### 方式 A：本地 Ollama（推荐，零 API 成本）

```bash
# 1. 安装并启动 Ollama，拉一个小模型
ollama pull llama3.2:3b        # 或 qwen2.5:7b（中文上下文更好）

# 2. 启用 AI 过滤并扫描
export AI_FILTER_ENABLED=1
python main_v2.2.py --authorized
```

Ollama 不可用时自动降级为纯规则引擎（MockBackend），不会中断扫描。

### 方式 B：OpenAI 兼容 API（官方 API 或中转站均可）

```bash
export AI_FILTER_ENABLED=1
export AI_DETECTOR_BACKEND=openai
export OPENAI_API_KEY=sk-xxxx                 # 你的 AI API Key
export AI_LLM_BASE_URL=https://api.openai.com/v1   # 可选，中转站填对应地址
export AI_LLM_MODEL=gpt-3.5-turbo             # 可选，默认 gpt-3.5-turbo
python main_v2.2.py --authorized
```

任何 OpenAI 兼容端点（DeepSeek、月之暗面、one-api 中转等）都能用，改
`AI_LLM_BASE_URL` 即可。

### 方式 C：单独调用（不跑扫描，只做分析）

```python
import asyncio
from ai_scanner_integration import should_validate_key

ok, reason = asyncio.run(should_validate_key(
    api_key="sk-proj-xxxxxxxxxxxxxxxx",
    code_snippet="OPENAI_API_KEY=sk-proj-xxxx  # production",
    platform="openai",
))
print(ok, reason)
```

## 实现说明

| 环节 | 位置 | 说明 |
|---|---|---|
| 规则预筛 | `ai_detector.QuickFilter` | 免 LLM 的快速判断（变量名/占位符/熵），先拦一批 |
| LLM 判断 | `ai_detector.AIDetector` + `SmartDetector.should_validate` | 只对规则拿不准的候选发起 LLM 调用 |
| 后端抽象 | `ai_detector.LLMBackend` → `OllamaBackend` / `OpenAIBackend` / `MockBackend` | temperature=0.1，max_tokens=500 |
| 管线挂载 | `ai_scanner_integration.patch_scanner_with_ai` | 补丁 `GitHubScanner._extract_keys_from_content`，同步桥接线程跑异步过滤 |
| 开关 | `scanner.start_scanner` → `_maybe_enable_ai_filter` | 环境变量 `AI_FILTER_ENABLED`，默认关闭 |

> 修复记录：旧版 `patch_scanner_with_ai` 挂载的函数名不存在（模块级
> `extract_keys_from_content` vs 实际的类方法 `_extract_keys_from_content`），
> 补丁静默失效；且异步过滤无法在同步管线里直接 await。两者均已修复。

## 成本与性能注意

- LLM 调用发生在**同步下载管线**内（桥接线程阻塞等待），单文件候选多时会拖慢
  扫描速度——建议搭配本地小模型（3B 级）使用；用远程 API 时注意并发账单。
- 每个 LLM 请求会把代码片段（前 1500 字符）发给后端。**扫描自有仓库时无碍；
  若扫描对象含他人代码，注意把内容发给第三方 API 的合规问题。**
- `AI_FILTER_ENABLED` 不设置时，行为与旧版完全一致（纯正则 + 熵过滤）。

## 相关文档

- [AI_DETECTOR_README.md](AI_DETECTOR_README.md) —— 检测器内部设计（提示词、置信度、缓存）
- [../AUTHORIZED_USE.md](../AUTHORIZED_USE.md) —— 使用边界
