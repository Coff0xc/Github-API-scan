# 深度验证功能指南 (P4)

## 概述

深度验证（Deep Validation）是对标准API密钥验证的增强，提供更详细的密钥价值评估和使用信息。

### 核心能力

- ✅ **余额透视** - 精确检测账户余额（美元）
- ✅ **额度分析** - 已用/总额度追踪
- ✅ **速率限制探测** - RPM/TPM/RPD 检测
- ✅ **模型访问权限** - GPT-4/GPT-5/Claude Opus 检测
- ✅ **账户信息提取** - 组织、账户名、密钥类型
- ✅ **价值评分系统** - 0-100分智能评分
- ✅ **高价值Key标记** - 自动识别高价值密钥

---

## 架构设计

```
标准验证 (validator.py)
    ↓ 验证成功
深度验证 (deep_validator.py)
    ↓ 提取深度信息
数据库存储 (database.py)
    ↓ 更新扩展字段
Dashboard展示 (web_dashboard.py)
```

### 模块说明

| 模块 | 职责 |
|------|------|
| `deep_validator.py` | 深度检测引擎 - 余额/模型/速率探测 |
| `validator_deep.py` | 集成层 - 将深度检测整合到验证流程 |
| `database.py` | 扩展schema - 存储13个深度验证字段 |

---

## 数据库Schema扩展

### 新增字段

```sql
-- 余额与配额
balance_usd REAL DEFAULT 0.0          -- 余额（美元）
used_quota_usd REAL DEFAULT 0.0       -- 已用额度
total_quota_usd REAL DEFAULT 0.0      -- 总额度

-- 速率限制
tpm INTEGER DEFAULT 0                 -- Tokens per minute
rpd INTEGER DEFAULT 0                 -- Requests per day

-- 模型访问权限
has_gpt4 BOOLEAN DEFAULT 0            -- GPT-4访问权限
has_gpt5 BOOLEAN DEFAULT 0            -- GPT-5访问权限
has_claude_opus BOOLEAN DEFAULT 0     -- Claude Opus访问权限

-- 账户信息
organization TEXT DEFAULT ''          -- 组织名称
account_name TEXT DEFAULT ''          -- 账户名称
expiration_date TEXT DEFAULT ''       -- 到期日期
key_type TEXT DEFAULT ''              -- 密钥类型: project/service_account/user

-- 价值评估
value_score INTEGER DEFAULT 0         -- 价值评分 0-100
```

### 迁移支持

数据库自动迁移 - 已有数据库无需手动修改，启动时自动添加新字段。

---

## 使用方法

### 1. 单个Key深度验证

```python
from validator_deep import validate_key_deep

# 执行深度验证
standard_result, deep_result = await validate_key_deep(
    platform="openai",
    api_key="sk-proj-xxx",
    base_url="https://api.openai.com/v1"
)

if deep_result and deep_result.is_valid:
    print(f"余额: ${deep_result.balance:.2f}")
    print(f"价值评分: {deep_result.value_score}/100")
    print(f"模型阶梯: {deep_result.model_tier}")
    print(f"GPT-4访问: {deep_result.has_gpt4}")
```

### 2. 批量深度验证

```python
from validator_deep import batch_validate_deep

keys = [
    ("openai", "sk-proj-xxx", ""),
    ("anthropic", "sk-ant-xxx", ""),
    ("openai", "sk-xxx", "https://api.relay.com/v1"),
]

results = await batch_validate_deep(keys, concurrency=50)

for standard, deep in results:
    if deep and deep.is_high_value:
        print(f"🔥 高价值Key发现: 评分 {deep.value_score}/100")
```

### 3. 集成到现有验证流程

```python
from validator_deep import IntegratedDeepValidator
from database import Database

db = Database("leaked_keys.db")

async with IntegratedDeepValidator(db, enable_deep_validation=True) as validator:
    # 自动执行标准验证 + 深度验证
    standard, deep = await validator.validate_with_depth(
        platform="openai",
        api_key="sk-xxx",
        base_url=""
    )
    # 深度验证结果自动写入数据库
```

---

## 价值评分系统

### 评分规则

| 因素 | 分数 |
|------|------|
| **模型访问** |  |
| GPT-5 / O3 访问 | +50 |
| GPT-4 访问 | +30 |
| GPT-3.5 only | +10 |
| **余额** |  |
| 余额 > $100 | +20 |
| 余额 > $10 | +10 |
| **速率限制** |  |
| RPM ≥ 5000 (Enterprise) | +40 |
| RPM ≥ 1000 (Team) | +20 |
| **密钥类型** |  |
| Service Account | +15 |
| Project Key | +5 |
| User Key | 0 |
| **组织信息** |  |
| 有组织名称 | +10 |

### 高价值判定

- **评分 ≥ 60** → 自动标记为高价值Key
- **余额 > $100** → 自动标记为高价值Key

---

## 深度验证详情

### OpenAI 深度检测

```python
async def deep_validate_openai(api_key, base_url):
    # 1. 模型列表探测
    models = await get_models(api_key)
    # 检测 GPT-4/GPT-5 访问

    # 2. 组织信息探测 (如果可访问)
    org_info = await get_organization(api_key)

    # 3. 余额探测 (针对中转站)
    if is_relay_station(base_url):
        billing = await probe_relay_billing(api_key)

    # 4. 密钥类型识别
    if api_key.startswith('sk-proj-'):
        key_type = "project"
    elif api_key.startswith('sk-svcacct-'):
        key_type = "service_account"
    
    # 5. 价值评分计算
    value_score = calculate_score(models, billing, key_type)
```

### Anthropic 深度检测

```python
async def deep_validate_anthropic(api_key, base_url):
    # 1. 最小请求探测
    response = await test_request(api_key)
    
    # 2. 速率限制提取（从响应头）
    rpm = response.headers.get('anthropic-ratelimit-requests-limit')
    tpm = response.headers.get('anthropic-ratelimit-tokens-limit')
    
    # 3. 账户等级推断
    if rpm >= 5000:
        tier = "Enterprise"
    elif rpm >= 1000:
        tier = "Team"
    else:
        tier = "Individual"
    
    # 4. 价值评分
    value_score = calculate_score(tier, rpm, tpm)
```

### 中转站余额探测

支持的中转站格式：
- One-API / New-API
- 自定义中转站

探测端点：
```
/api/user/self
/api/user/info
/user/info
/api/status
/v1/dashboard/billing/subscription
```

余额格式转换：
- One-API: `500000 → $5.00`
- 标准格式: `5.0 → $5.00`

---

## 性能影响

### 时间开销

- **标准验证**: 1-3秒
- **深度验证**: +1-2秒（额外开销）
- **总时长**: 2-5秒/key

### 优化策略

1. **并发控制** - 默认50并发，避免触发速率限制
2. **超时设置** - 深度检测超时3-5秒，快速失败
3. **缓存机制** - 模型列表等信息缓存（计划中）
4. **可选开关** - `enable_deep_validation=True/False`

---

## 输出示例

### 控制台输出

```
🔥 高价值Key: sk-proj-xxxxxxxxxxxxx | 评分: 85/100 | 余额: $156.32 | 模型: GPT-5
```

### 数据库查询

```sql
-- 查询所有高价值Key
SELECT api_key, platform, value_score, balance_usd, model_tier, key_type
FROM leaked_keys
WHERE is_high_value = 1
ORDER BY value_score DESC;

-- 查询GPT-5访问权限的Key
SELECT api_key, organization, balance_usd, value_score
FROM leaked_keys
WHERE has_gpt5 = 1;

-- 查询企业级Anthropic Key
SELECT api_key, rpm, tpm, model_tier, value_score
FROM leaked_keys
WHERE platform = 'anthropic' AND rpm >= 5000;
```

### Dashboard展示

Web Dashboard 自动展示：
- 高价值Key列表（红色标记）
- 价值评分排序
- 余额统计图表
- 模型访问权限分布

---

## 支持的平台

| 平台 | 深度验证支持 | 检测项目 |
|------|-------------|----------|
| **OpenAI** | ✅ 完整支持 | 模型/余额/组织/密钥类型 |
| **Anthropic** | ✅ 完整支持 | 速率限制/账户等级 |
| **中转站** | ✅ 完整支持 | 余额/额度/模型 |
| Gemini | 🔄 计划中 | 配额/项目信息 |
| Azure OpenAI | 🔄 计划中 | 部署信息/配额 |
| 其他平台 | ⏳ 待开发 | - |

---

## 扩展指南

### 添加新平台深度检测

1. 在 `deep_validator.py` 添加方法：

```python
async def deep_validate_newplatform(self, api_key: str, base_url: str) -> DeepValidationResult:
    result = DeepValidationResult(is_valid=False, platform="newplatform")
    
    # 实现平台特定的深度检测逻辑
    # ...
    
    return result
```

2. 在 `validator_deep.py` 集成：

```python
async def _deep_validate(self, platform: str, api_key: str, base_url: str):
    # ...
    elif platform == "newplatform":
        return await self.deep_validator.deep_validate_newplatform(api_key, base_url)
```

---

## 常见问题

### Q: 深度验证失败会影响标准验证吗？
A: 不会。深度验证失败只记录警告，不影响标准验证结果。

### Q: 如何禁用深度验证？
A: 设置 `enable_deep_validation=False`:
```python
validator = IntegratedDeepValidator(db, enable_deep_validation=False)
```

### Q: 深度验证会触发速率限制吗？
A: 可能。深度验证会额外发送1-3个请求。建议降低并发数。

### Q: 中转站余额探测准确吗？
A: 依赖中转站API实现。One-API/New-API格式支持较好。

### Q: 价值评分的阈值可以调整吗？
A: 可以。修改 `deep_validator.py` 中的评分规则。

---

## 技术细节

### 线程安全

- 数据库操作使用 `threading.Lock`
- 异步操作使用 `asyncio.Semaphore`

### 错误处理

- 深度验证异常不影响主流程
- 所有网络请求设置超时
- 失败时记录警告日志

### 数据一致性

- 使用事务保证原子性
- 唯一索引防止重复
- 自动时间戳记录

---

## 路线图

- [ ] **v1.0** - OpenAI/Anthropic/中转站深度验证 ✅
- [ ] **v1.1** - Gemini/Azure深度验证
- [ ] **v1.2** - 余额历史追踪
- [ ] **v1.3** - 使用量趋势分析
- [ ] **v2.0** - 实时余额监控（WebSocket）

---

## 相关文档

- [BASE_URL_PAIRING_FIX.md](./BASE_URL_PAIRING_FIX.md) - Base URL配对修复
- [WEB_DASHBOARD_GUIDE.md](./WEB_DASHBOARD_GUIDE.md) - Dashboard使用指南
- [OPTIMIZATION_SUMMARY.md](./OPTIMIZATION_SUMMARY.md) - 优化总览

---

**文档版本**: 1.0  
**最后更新**: 2026-07-29  
**贡献者**: Coff0xc
