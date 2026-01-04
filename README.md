# GitHub Secret Scanner Pro

![Python](https://img.shields.io/badge/python-3.9+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Status](https://img.shields.io/badge/status-active-success.svg)

🚀 **企业级 GitHub 密钥扫描与验证系统**

GitHub Secret Scanner Pro 是一款高性能的自动化工具，专为安全研究人员和红队设计。它利用 GitHub API 实时扫描代码库中的敏感密钥，并使用高并发异步架构进行深度有效性验证。

> ⚠️ **免责声明**: 本项目仅用于授权的安全测试和教育目的。严禁用于非法扫描或利用他人凭证。使用者需自行承担所有法律责任。

## 📸 运行截图

<div align="center">
  <img src="assets/screenshot.png" alt="Dashboard" width="800"/>
  <br>
  <br>
  <img src="assets/screenshot1.png" alt="Results" width="800"/>
</div>

## ✨ 核心特性

### 🔍 多源扫描
- **GitHub Code Search** - 精准搜索泄露的密钥
- **GitHub Gist** - 扫描公开 Gist
- **GitLab** - 支持 GitLab 公开仓库
- **Pastebin** - 实时监控粘贴板
- **SearchCode** - 跨平台代码搜索
- **GitHub Events API** - 实时监控新提交

### 🎯 多平台验证
支持验证 **12+ AI 平台** 的 API Key：

| 平台 | 验证方式 | 深度探测 |
|------|----------|----------|
| OpenAI | chat/completions | GPT-4 权限、余额、RPM |
| Anthropic | messages | Claude-3 模型识别 |
| Google Gemini | generateContent | 配额检测 |
| Azure OpenAI | 上下文感知 | Endpoint 自动提取 |
| Groq | chat/completions | 模型列表 |
| DeepSeek | chat/completions | 余额检测 |
| Mistral | chat/completions | 模型权限 |
| Cohere | chat | API 状态 |
| Together | chat/completions | 模型列表 |
| HuggingFace | whoami | 账户验证 |
| Replicate | account | 账户状态 |
| Perplexity | chat/completions | 在线模型 |

### 📱 实时推送通知
发现可用 Key 时立即推送：
- **微信** - WxPusher (免费无限制)
- **微信/QQ** - PushPlus
- **Telegram** - Bot 推送
- **钉钉** - 机器人 Webhook
- **声音** - 本地蜂鸣提醒
- **文件** - 自动记录到桌面

### ⚡ 高性能架构
- **异步并发** - asyncio + aiohttp，100+ 并发验证
- **智能断路器** - 自动熔断不稳定节点
- **Token 池轮询** - 突破 GitHub API 限制
- **断点续传** - SQLite 持久化存储

## 🚀 快速开始

```bash
# 克隆仓库
git clone https://github.com/Coff0xc/Github-API-scan.git
cd Github-API-scan

# 安装依赖
pip install -r requirements.txt

# 配置 GitHub Token
cp config_local.py.example config_local.py
# 编辑 config_local.py 填入你的 GitHub Token

# 启动扫描
python main.py
```

## ⚙️ 配置

### GitHub Token 配置

```python
# config_local.py
GITHUB_TOKENS = [
    "ghp_xxxxxxxxxxxx",
    "ghp_yyyyyyyyyyyy",
]
```

或使用环境变量：
```bash
export GITHUB_TOKENS="ghp_xxx,ghp_yyy"
```

### 推送通知配置

编辑 `monitor.py` 配置推送：

```python
notifier = Notifier(
    wxpusher_token="YOUR_TOKEN",      # WxPusher
    wxpusher_uid="YOUR_UID",
    # telegram_token="BOT_TOKEN",     # Telegram
    # telegram_chat_id="CHAT_ID",
    # dingtalk_webhook="WEBHOOK_URL", # 钉钉
)
```

## 🖥️ 使用指南

```bash
# 启动扫描 (TUI 仪表盘)
python main.py

# 启动实时监控 + 推送
python monitor.py

# 导出结果
python main.py --export output.txt
python main.py --export-csv results.csv

# 查看统计
python main.py --stats
```

## 📂 项目结构

```
├── main.py              # 主程序入口
├── scanner.py           # GitHub 扫描器
├── validator.py         # Key 验证器
├── monitor.py           # 实时监控 + 推送
├── notifier.py          # 推送通知模块
├── database.py          # 数据库封装
├── config.py            # 配置文件
├── source_gist.py       # Gist 扫描源
├── source_gitlab.py     # GitLab 扫描源
├── source_pastebin.py   # Pastebin 扫描源
├── source_searchcode.py # SearchCode 扫描源
├── source_realtime.py   # GitHub Events 实时监控
└── ui.py                # Rich TUI 界面
```

## ⚠️ 免责声明

本项目仅用于**授权的安全测试和教育目的**。严禁用于非法扫描或利用他人凭证。

使用者需自行承担所有法律责任。作者不对任何滥用行为负责。

## 📝 许可证

[MIT License](LICENSE)

---

**Made with ❤️ for Security Researchers**
