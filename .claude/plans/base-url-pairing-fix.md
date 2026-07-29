# Base URL 配对修复方案

## 问题诊断

**核心问题：** 当前验证逻辑存在致命缺陷 - 虽然 scanner 能从代码中提取 base_url，但 validator 在验证时会忽略它，统一使用官方 API 地址，导致**大量中转站密钥被误判为无效**。

### 当前流程问题

```
Scanner 提取: 
  api_key = "sk-xxx" 
  base_url = "https://api.relay-station.com/v1"  ✓ 正确提取
  
Validator 验证:
  使用 base_url = "https://api.openai.com/v1"  ✗ 强制覆盖为官方地址
  结果: 401 Unauthorized → 标记为 INVALID  ✗ 误杀
```

### 影响范围

1. **OpenAI 兼容中转站** - 最大受害者（OpenRouter、LiteLLM、自建代理等）
2. **Azure OpenAI** - 需要绑定特定 endpoint
3. **其他支持自定义 base_url 的平台** - Anthropic、Gemini 等

## 解决方案设计

### 核心修复点

#### 1. Validator 必须尊重传入的 base_url

**当前问题代码位置：** `validator.py:436-444`

```python
async def validate_openai(self, api_key: str, base_url: str) -> ValidationResult:
    if not base_url:  # ✗ 只在空值时才使用默认值
        base_url = config.default_base_urls["openai"]
```

**修复后逻辑：**
```python
async def validate_openai(self, api_key: str, base_url: str) -> ValidationResult:
    # ✓ 尊重传入的 base_url，只在为空时使用默认值
    if not base_url:
        base_url = config.default_base_urls["openai"]
    # ✓ 后续验证直接使用 base_url，不再覆盖
```

#### 2. 增强 base_url 提取逻辑

**当前问题：** `scanner.py:775` 的 `_extract_base_url` 已有实现，但需要验证其准确性

**改进方向：**
- 确保正则匹配覆盖所有常见变量名（`OPENAI_API_BASE`, `API_BASE_URL`, `PROXY_URL` 等）
- 增加优先级排序（优先使用显式声明的 base_url）
- 对中转站域名白名单支持

#### 3. 数据库已支持 base_url 存储

**确认：** `database.py:106` 表结构已包含 `base_url TEXT NOT NULL`
- 无需修改数据库 schema
- 已有索引 `idx_base_url`

### 实施步骤

#### Step 1: 审查并修复 validator.py 中所有平台的验证方法

需要检查的方法：
- `validate_openai()` - 最关键
- `validate_anthropic()`
- `validate_gemini()`
- `validate_azure()` - 已特殊处理
- 其他 OpenAI 兼容平台（groq, deepseek, moonshot 等）

**修复模式：**
```python
# ✗ 错误模式
if not base_url:
    base_url = default_url
else:
    base_url = default_url  # 强制覆盖

# ✓ 正确模式
if not base_url:
    base_url = default_url
# 后续使用传入的 base_url
```

#### Step 2: 增强 base_url 提取准确性

**文件：** `scanner.py:775`

改进点：
1. 扩展正则模式覆盖更多变量命名风格
2. 增加上下文窗口大小（当前可能过小）
3. 改进中转站域名识别逻辑

#### Step 3: 添加验证日志和调试信息

在验证时记录实际使用的 base_url：
```python
logger.debug(f"验证 {platform} key: {mask_key(api_key)}, base_url: {base_url}")
```

#### Step 4: 添加测试用例

创建测试验证：
1. 官方 API key + 默认 base_url → VALID
2. 中转站 key + 中转站 base_url → VALID
3. 中转站 key + 官方 base_url → INVALID（预期行为）

### 风险评估

**低风险：**
- 修改仅影响验证逻辑，不涉及数据库 schema
- Scanner 提取逻辑保持不变
- 向后兼容（空 base_url 时自动使用默认值）

**需要注意：**
- 中转站可能有特殊的鉴权方式（不完全兼容 OpenAI API）
- 某些中转站可能需要额外的 header 或参数

### 验证方案

修复后验证步骤：
1. 使用已知的中转站 API key + base_url 进行测试
2. 检查日志确认使用了正确的 base_url
3. 对比修复前后的验证结果统计（VALID vs INVALID 比例）

## 实施清单

- [ ] 审查 validator.py 所有验证方法
- [ ] 修复 validate_openai() 
- [ ] 修复其他 OpenAI 兼容平台验证方法
- [ ] 增强 scanner.py 的 base_url 提取逻辑
- [ ] 添加验证日志
- [ ] 创建测试用例
- [ ] 更新文档说明 base_url 配对功能
