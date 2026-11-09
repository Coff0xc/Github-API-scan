# 通知系统 v2.0 使用说明

## 概述

通知系统 v2.0 是 GitHub Secret Scanner Pro 的增强版通知模块，支持 **10+ 通知渠道** 和 **智能分级通知**。

## 新增功能

### 🔔 支持的通知渠道

| 渠道 | 免费 | 限制 | 特点 |
|------|------|------|------|
| Discord | ✅ | 无 | 支持富文本 Embed，推荐使用 |
| Slack | ✅ | 无 | 支持 Block Kit |
| Telegram | ✅ | 无 | 全球可用，速度快 |
| 飞书 | ✅ | 无 | 支持卡片消息 |
| 钉钉 | ✅ | 无 | 支持加签安全 |
| Server酱 | ✅ | 有 | 微信推送 |
| Bark | ✅ | 无 | iOS 推送 |
| PushPlus | ✅ | 有 | QQ/微信推送 |
| WxPusher | ✅ | 无 | 微信推送 |
| 文件 | ✅ | 无 | 本地记录 |
| 声音 | ✅ | 无 | 系统提示音 |

### 🎯 严重性分级

| 级别 | 触发条件 | 通知行为 |
|------|---------|---------|
| **CRITICAL** 🚨 | GPT-4/Claude-3-Opus + 余额>$100 | 立即通知，无视静默时段 |
| **HIGH** 🔥 | GPT-4/Claude-3 或余额>$10 | 立即通知 |
| **MEDIUM** ✅ | 普通有效 Key | 正常通知 |
| **LOW** ⚠️ | 配额耗尽但有效 | 可选通知 |

### 🛡️ 智能防护

- **通知去重**: 同一 Key 只通知一次
- **速率限制**: 防止通知刷屏 (默认 30条/分钟)
- **静默时段**: 夜间不打扰 (Critical 除外)

## 快速开始

### 方式一: 环境变量配置 (推荐)

```bash
# Discord
export DISCORD_WEBHOOK="https://discord.com/api/webhooks/xxx/xxx"

# Telegram
export TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
export TELEGRAM_CHAT_ID="123456789"

# 飞书
export FEISHU_WEBHOOK="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"

# 钉钉
export DINGTALK_WEBHOOK="https://oapi.dingtalk.com/robot/send?access_token=xxx"
export DINGTALK_SECRET="SECxxx"  # 可选，加签密钥

# 运行扫描器。远程搜索必须带组织或仓库。
python main_v2.2.py --authorized --target-org your-org
```

### 方式二: 配置文件

```bash
# 复制配置模板
cp notify_config.example.yaml notify_config.yaml

# 编辑配置
vim notify_config.yaml

# 测试通知
python test_notifier.py --config notify_config.yaml
```

## 测试通知

```bash
# 交互式测试
python test_notifier.py

# 测试所有渠道
python test_notifier.py --all

# 测试特定渠道
python test_notifier.py --channel discord
python test_notifier.py --channel telegram

# 测试不同级别
python test_notifier.py --all --level critical
python test_notifier.py --all --level high

# 发送测试报告
python test_notifier.py --report

# 交互式配置向导
python test_notifier.py --setup
```

## 配置详解

### Discord Webhook 获取

1. 打开 Discord 服务器
2. 服务器设置 → 整合 → Webhook
3. 新建 Webhook，复制 URL

### Telegram Bot 获取

1. 与 [@BotFather](https://t.me/BotFather) 对话
2. 发送 `/newbot`，按提示创建
3. 保存 Bot Token
4. 与你的 Bot 对话，发送任意消息
5. 访问 `https://api.telegram.org/bot<TOKEN>/getUpdates` 获取 chat_id

### 飞书机器人获取

1. 打开飞书群设置
2. 群机器人 → 添加机器人 → 自定义机器人
3. 复制 Webhook 地址

### 钉钉机器人获取

1. 打开钉钉群设置
2. 智能群助手 → 添加机器人 → 自定义
3. 选择"加签"安全设置，复制 Webhook 和密钥

## 集成到现有代码

### 方式一: 直接调用

```python
from notify_integration import notify_key_found

# 在发现有效 Key 时调用
await notify_key_found(
    platform="openai",
    api_key="sk-xxx",
    model_tier="GPT-4",
    balance="$50.00",
    is_high_value=True
)
```

### 方式二: 初始化集成

```python
from notify_integration import init_notify_integration, get_notify_integration

# 启动时初始化
init_notify_integration("notify_config.yaml")

# 任何地方获取实例
integration = get_notify_integration()
await integration.on_key_validated(...)
```

### 方式三: Validator 补丁 (自动集成)

```python
from validator import AsyncValidator
from notify_integration import patch_validator_for_notifications

# 为 Validator 添加通知功能
patch_validator_for_notifications(AsyncValidator, "notify_config.yaml")

# 之后所有验证成功都会自动发送通知
```

## 配置文件示例

```yaml
# notify_config.yaml
discord:
  enabled: true
  webhook_url: "https://discord.com/api/webhooks/xxx/xxx"

telegram:
  enabled: true
  bot_token: "xxx"
  chat_id: "xxx"

# 静默时段 (23:00 - 07:00 不通知，Critical 除外)
quiet_hours:
  enabled: true
  start: "23:00"
  end: "07:00"

# 速率限制
rate_limit:
  enabled: true
  window: 60
  max_count: 30
```

## 通知效果预览

### Discord

```
🔥 发现 OPENAI Key!
━━━━━━━━━━━━━━━━━━━━━━━
平台: OPENAI
级别: HIGH
Key: sk-proj-****abcd
模型: GPT-4-Turbo
余额: $50.00
来源: GitHub Link
━━━━━━━━━━━━━━━━━━━━━━━
GitHub Secret Scanner Pro
```

### Telegram

```
🔥 发现 OPENAI Key!

平台: openai
级别: HIGH
Key: sk-proj-****abcd
模型: GPT-4-Turbo
余额: $50.00

查看来源

GitHub Secret Scanner Pro
```

## 故障排除

### 通知没有收到

1. 检查 Webhook/Token 是否正确
2. 运行 `python test_notifier.py --channel <渠道名>` 测试
3. 检查网络是否能访问对应服务

### 通知太多/太少

1. 调整 `min_severity` 配置
2. 启用 `quiet_hours` 静默时段
3. 调整 `rate_limit` 速率限制

### 重复通知

通知系统默认启用去重，同一 Key 只会通知一次。如需重置：

```python
notifier.notified_keys.clear()
```

## 文件清单

```
├── notifier_v2.py           # 增强版通知系统核心
├── notify_config.example.yaml  # 配置文件模板
├── notify_integration.py    # 集成模块
├── test_notifier.py         # 测试脚本
└── NOTIFY_README.md         # 本文档
```

## 更新日志

### v2.0.0 (2026-01)

- 新增 Discord/Slack/飞书 支持
- 新增严重性分级系统
- 新增通知去重、速率限制
- 新增静默时段配置
- 新增每日汇总报告
- 重构为模块化架构
