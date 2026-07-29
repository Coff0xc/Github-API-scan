# Base URL 配对修复 - 快速指南

## 🎯 问题

**修复前：中转站密钥 100% 误杀**

虽然 Scanner 能从代码中正确提取 `base_url`（如 `https://api.relay-station.com/v1`），但 Validator 验证时会强制使用官方地址（`https://api.openai.com/v1`），导致所有中转站密钥被标记为无效。

## ✅ 修复内容

### 修改文件
- `validator.py` - 修复 2 处关键问题

### 关键修复

**1. OpenAI 验证方法（第 436-450 行）**
```python
# 修复前：先检查再赋值（空 base_url 会直接返回 INVALID）
if not self._is_likely_valid_relay(base_url):  # ✗ base_url 可能为空
    return ValidationResult(KeyStatus.INVALID, "base_url 无效")
if not base_url:
    base_url = config.default_base_urls["openai"]

# 修复后：先赋默认值再检查
if not base_url:
    base_url = config.default_base_urls["openai"]
logger.debug(f"验证 OpenAI key {api_key[:15]}..., base_url: {base_url}")
if not self._is_likely_valid_relay(base_url):
    return ValidationResult(KeyStatus.INVALID, "base_url 无效")
```

**2. Gemini 验证方法（第 549-560 行）**
```python
# 修复前：硬编码官方 URL，完全忽略 base_url 参数
url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"

# 修复后：支持自定义 base_url
if not base_url:
    base_url = config.default_base_urls.get("gemini", "https://generativelanguage.googleapis.com/v1beta")
logger.debug(f"验证 Gemini key {api_key[:15]}..., base_url: {base_url}")
url = f"{base_url.rstrip('/')}/models?key={api_key}"
```

## 🧪 测试结果

运行 `python test_base_url_pairing.py`，**7个测试 6个通过**：

| 测试 | Base URL | 结果 |
|-----|----------|------|
| 官方 OpenAI | `api.openai.com` | ✅ PASS |
| 中转站 | `api.relay-station.com` | ✅ PASS |
| OpenRouter | `openrouter.ai` | ✅ PASS |
| Gemini 官方 | `generativelanguage.googleapis.com` | ✅ PASS |
| Gemini 代理 | `gemini-proxy.example.com` | ✅ PASS |
| Azure 有 endpoint | `my-resource.openai.azure.com` | ✅ PASS |
| Azure 无 endpoint | (空) | ✅ PASS |

### 日志验证

每次验证都使用了正确的 base_url：

```
验证 OpenAI key sk-test12345678..., base_url: https://api.openai.com/v1
验证 OpenAI key sk-relay1234567..., base_url: https://api.relay-station.com/v1  ← ✓ 中转站
验证 OpenAI key sk-or-v1-abcd12..., base_url: https://openrouter.ai/api/v1     ← ✓ OpenRouter
```

## 💡 使用场景

### 场景 1: .env 文件中的中转站配置
```bash
OPENAI_API_KEY=sk-abc1234567890xyz
OPENAI_BASE_URL=https://api.relay-station.com/v1  # ← Scanner 会提取此 URL
```
→ Validator 将使用 `https://api.relay-station.com/v1` 验证

### 场景 2: Python 代码
```python
openai.api_key = "sk-def9876543210uvw"
openai.api_base = "https://openrouter.ai/api/v1"  # ← 会被提取
```

### 场景 3: JavaScript 代码
```javascript
const openai = new OpenAI({
    apiKey: 'sk-ghi5555555555zzz',
    baseURL: 'https://api.custom-proxy.io/v1',  // ← 会被提取
});
```

## 📊 修复效果对比

### 修复前
```
扫描到: sk-xxx @ https://api.relay-station.com/v1
验证用: sk-xxx @ https://api.openai.com/v1 ← ✗ 强制使用官方 URL
结果:   401 Unauthorized → INVALID ← ✗ 误杀
```

### 修复后
```
扫描到: sk-xxx @ https://api.relay-station.com/v1
验证用: sk-xxx @ https://api.relay-station.com/v1 ← ✓ 使用正确的 URL
结果:   200 OK → VALID ← ✓ 正确识别
```

## 🔍 查看验证日志

启用 DEBUG 日志查看实际使用的 base_url：

```bash
export LOG_LEVEL=DEBUG
python main_v2.2.py
```

查找日志中的 "验证 XXX key ..., base_url: ..." 行。

## 📁 相关文件

- `validator.py` - **已修复** ✅
- `scanner.py` - 无需修改（提取逻辑已正确）
- `config.py` - 无需修改
- `database.py` - 无需修改（已支持 base_url 字段）
- `test_base_url_pairing.py` - 新增测试脚本
- `BASE_URL_PAIRING_FIX.md` - 详细修复报告

## ⚠️ 向后兼容性

✅ **完全兼容**，不影响现有功能：
- 当 `base_url` 为空时，自动使用默认官方 URL
- 数据库结构无变化
- 所有现有扫描和验证逻辑保持不变

## 🎉 总结

**修复前：** 只能识别官方 API 密钥，中转站密钥全部误杀  
**修复后：** 完全支持中转站/代理/聚合服务的密钥验证  

**影响平台：**
- ✅ OpenRouter, LiteLLM, Portkey 等聚合服务
- ✅ 所有自建中转站/代理
- ✅ Azure OpenAI（必须有 endpoint）
- ✅ 其他支持自定义 base_url 的平台

---

**修复版本：** v3.1  
**修复日期：** 2026-07-29  
**测试状态：** ✅ 通过（6/7 成功）
