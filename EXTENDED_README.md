# 扩展平台验证模块 使用说明

## 概述

扩展平台验证模块参考 [KeyHacks](https://github.com/streaak/keyhacks) 添加了 **30+ 平台** 的 API Key 识别和验证能力。

## 支持的平台

### 通信/消息平台 (7个)

| 平台 | 验证方法 | 凭证要求 |
|------|----------|----------|
| Slack | `auth.test` API | token |
| Discord | Users API | token |
| Telegram | `getMe` API | token |
| Twilio | Account API | account_sid, auth_token |
| SendGrid | User Profile API | api_key |
| Mailgun | Domains API | api_key |
| Mailchimp | Account API | api_key |

### 云服务商 (4个)

| 平台 | 验证方法 | 凭证要求 |
|------|----------|----------|
| DigitalOcean | Account API | token |
| Heroku | Account API | api_key |
| Cloudflare | Token Verify / User API | api_key, [email] |
| Vercel | User API | token |

### 开发工具 (6个)

| 平台 | 验证方法 | 凭证要求 |
|------|----------|----------|
| GitLab | User API | token |
| Bitbucket | User API | username, app_password |
| CircleCI | Me API | token |
| Travis CI | User API | token |
| NPM | User API | token |
| Docker Hub | Login API | username, password |

### 监控/APM (4个)

| 平台 | 验证方法 | 凭证要求 |
|------|----------|----------|
| Datadog | Validate API | api_key, [app_key] |
| Sentry | Root API | auth_token |
| New Relic | GraphQL API | api_key |
| PagerDuty | Users/Me API | api_key |

### 协作工具 (5个)

| 平台 | 验证方法 | 凭证要求 |
|------|----------|----------|
| Notion | Users/Me API | token |
| Linear | GraphQL API | api_key |
| Asana | Users/Me API | token |
| Airtable | Whoami API | api_key |
| Atlassian | Myself API | email, api_token, domain |

### 分析平台 (4个)

| 平台 | 验证方法 | 凭证要求 |
|------|----------|----------|
| Segment | Track API | write_key |
| Mixpanel | Track API | token |
| Amplitude | HTTP API | api_key |
| Algolia | Keys API | app_id, api_key |

### 客服/CRM (3个)

| 平台 | 验证方法 | 凭证要求 |
|------|----------|----------|
| Zendesk | Users/Me API | subdomain, email, api_token |
| Intercom | Me API | token |
| Freshdesk | Agents/Me API | subdomain, api_key |

### 地图服务 (2个)

| 平台 | 验证方法 | 凭证要求 |
|------|----------|----------|
| Mapbox | Tokens API | token |
| Google Maps | Geocoding API | api_key |

### 支付平台 (2个)

| 平台 | 验证方法 | 凭证要求 |
|------|----------|----------|
| PayPal | OAuth Token | client_id, secret |
| Square | Merchants API | access_token |

## 快速开始

### 1. 命令行测试

```bash
# 列出支持的平台
python test_validator_extended.py --list

# 列出正则模式
python test_validator_extended.py --list-regex

# 运行正则测试
python test_validator_extended.py --regex-test

# 测试单个平台
python test_validator_extended.py -p slack --token "xoxb-xxx"
python test_validator_extended.py -p github --token "ghp_xxx"

# 交互式测试
python test_validator_extended.py --interactive
```

### 2. 代码集成

```python
from validator_extended import (
    ExtendedValidator,
    validate_extended,
    get_supported_platforms,
)

# 方式一: 使用便捷函数
result = await validate_extended(
    platform="slack",
    credentials={"token": "xoxb-xxx"}
)

if result.status == ExtendedKeyStatus.VALID:
    print(f"有效: {result.message}")

# 方式二: 使用验证器实例
validator = ExtendedValidator(proxy_url="http://127.0.0.1:7890")
result = await validator.validate_slack_token("xoxb-xxx")
await validator.close()
```

### 3. 正则匹配

```python
from regex_extended import (
    find_all_keys,
    identify_platform,
    get_high_priority_patterns,
)

# 在文本中查找所有密钥
text = '''
SLACK_TOKEN="xoxb-1234567890123-xxx"
STRIPE_KEY="sk_live_abcdef"
'''

matches = find_all_keys(text)
for platform, key, position in matches:
    print(f"找到 {platform}: {key[:20]}...")

# 识别单个密钥的平台
platforms = identify_platform("sk_live_abcdefghijklmnop")
print(f"可能的平台: {platforms}")
```

## 正则表达式库

### 高优先级模式 (无需上下文)

这些模式格式明确，可直接匹配：

| 模式名 | 正则表达式 | 示例 |
|--------|-----------|------|
| slack_token | `xox[baprs]-...` | xoxb-1234567890-xxx |
| discord_webhook | `https://discord.com/api/webhooks/...` | - |
| sendgrid | `SG\.xxx\.xxx` | SG.xxx.xxx |
| digitalocean | `dop_v1_xxx` | dop_v1_xxx |
| gitlab_pat | `glpat-xxx` | glpat-xxx |
| npm_token | `npm_xxx` | npm_xxx |
| sentry | `sntrys_xxx` | sntrys_xxx |
| notion | `secret_xxx` | secret_xxx |
| stripe_secret | `sk_live_xxx` | sk_live_xxx |
| mapbox | `pk.xxx.xxx` | pk.xxx.xxx |
| aws_access | `AKIA/ASIA/AIDA...` | AKIAIOSFODNN7EXAMPLE |

### 上下文相关模式

这些模式需要上下文关键词辅助判断：

| 模式名 | 上下文关键词 |
|--------|-------------|
| heroku | heroku |
| cloudflare | cloudflare |
| datadog | datadog |
| zendesk | zendesk |
| algolia | algolia |

## 扩展搜索关键词

模块提供了针对新平台的 GitHub 搜索关键词：

```python
from regex_extended import get_extended_search_keywords

keywords = get_extended_search_keywords()
# 返回 50+ 精选搜索关键词
```

示例关键词：
```
filename:.env SLACK_TOKEN NOT test NOT example
xoxb- language:python NOT test NOT example
glpat- language:python NOT test NOT example
dop_v1_ language:python NOT test
sntrys_ language:python NOT test
sk_live_ NOT test NOT example NOT staging
```

## 集成到 Scanner

### 方式一: 替换正则库

```python
from config import REGEX_PATTERNS
from regex_extended import merge_with_base_patterns

# 合并扩展模式
ALL_PATTERNS = merge_with_base_patterns(REGEX_PATTERNS)
```

### 方式二: 扩展验证器

在 `validator.py` 的 `validate_single` 方法中添加：

```python
from validator_extended import ExtendedValidator

# 对于扩展平台，使用扩展验证器
ext_validator = ExtendedValidator(proxy_url=self._get_proxy())
if platform in EXTENDED_PLATFORMS:
    result = await ext_validator.validate(platform, {"token": api_key})
    return ValidationResult(
        status=KeyStatus.VALID if result.status == ExtendedKeyStatus.VALID else KeyStatus.INVALID,
        info=result.message,
        is_high_value=result.is_high_value
    )
```

### 方式三: 搜索关键词扩展

```python
from config import Config
from regex_extended import get_extended_search_keywords

# 扩展搜索关键词
config = Config()
config.search_keywords.extend(get_extended_search_keywords())
```

## 验证结果

### 状态枚举

| 状态 | 说明 |
|------|------|
| `VALID` | 验证成功，凭证有效 |
| `INVALID` | 验证失败，凭证无效 |
| `QUOTA_EXCEEDED` | 配额耗尽或过期 |
| `PARTIAL` | 部分有效（权限受限） |
| `CONNECTION_ERROR` | 网络连接错误 |
| `UNVERIFIED` | 无法验证 |

### 结果字段

```python
@dataclass
class ExtendedValidationResult:
    status: ExtendedKeyStatus      # 状态
    message: str                   # 描述消息
    platform: str                  # 平台名
    extra_info: Dict[str, Any]     # 额外信息（用户名、邮箱等）
    is_high_value: bool            # 是否为高价值凭证
```

## 文件清单

```
├── validator_extended.py       # 扩展验证器核心 (30+ 平台)
├── regex_extended.py           # 扩展正则表达式库 (50+ 模式)
├── test_validator_extended.py  # 测试脚本
└── EXTENDED_README.md          # 本文档
```

## 参考资料

- [KeyHacks](https://github.com/streaak/keyhacks) - API Key 验证方法集合
- [RegHex](https://github.com/l4yton/RegHex) - 正则表达式库
- [TruffleHog](https://github.com/trufflesecurity/trufflehog) - Secret 扫描器

## 更新日志

### v1.0.0 (2026-01)

- 初始版本
- 支持 30+ 平台验证
- 50+ 正则表达式模式
- 高优先级/上下文相关模式分类
- 扩展搜索关键词
