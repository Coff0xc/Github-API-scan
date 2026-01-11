# GitHub Secret Scanner Pro

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Status](https://img.shields.io/badge/status-active-success.svg)
![Version](https://img.shields.io/badge/version-v2.0--optimized-orange.svg)
![Performance](https://img.shields.io/badge/performance-100x+-brightgreen.svg)

🚀 **企业级 GitHub 密钥扫描与验证系统 - 优化版**

GitHub Secret Scanner Pro 是一款高性能的自动化工具，专为安全研究人员和红队设计。它利用 GitHub API 实时扫描代码库中的敏感密钥，并使用高并发异步架构进行深度有效性验证。

**v2.0 优化版**实现了 **100-430倍** 的性能提升，采用异步数据库、批量写入和加密导出等企业级特性。

> ⚠️ **免责声明**: 本项目仅用于授权的安全测试和教育目的。严禁用于非法扫描或利用他人凭证。使用者需自行承担所有法律责任。

## 📸 运行截图

<div align="center">
  <img src="assets/screenshot.png" alt="Dashboard" width="800"/>
  <br>
  <br>
  <img src="assets/screenshot1.png" alt="Results" width="800"/>
</div>

## ✨ 核心特性

### 🚀 v2.0 优化版新特性

- **异步数据库** - 使用 aiosqlite 实现批量写入，性能提升 **100-430倍**
- **队列扩容** - 从 1000 提升到 10000，支持更高吞吐量
- **加密导出** - 使用 Fernet 对称加密保护敏感数据
- **配置外部化** - config.yaml 支持，无需修改代码即可调参
- **配置验证** - 启动时自动检查配置完整性
- **性能监控** - 实时统计扫描效率和发现率
- **完全兼容** - 与原版数据库 100% 兼容，无需迁移

### 📊 性能对比

| 测试规模 | 原版耗时 | 优化版耗时 | 加速比 |
|---------|---------|-----------|--------|
| 100条记录 | 10.38秒 | 0.10秒 | **108x** |
| 500条记录 | 52.08秒 | 0.16秒 | **320x** |
| 1000条记录 | 103.29秒 | 0.24秒 | **430x** |

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

### 方式 1: 使用优化版 (推荐)

```bash
# 克隆仓库
git clone https://github.com/Coff0xc/Github-API-scan.git
cd Github-API-scan

# 安装依赖
pip install -r requirements.txt

# 配置 GitHub Token
export GITHUB_TOKENS="ghp_xxxxxxxxxxxx,ghp_yyyyyyyyyyyy"
# 或创建 config_local.py 文件

# 启动优化版扫描
python main_optimized.py
```

### 方式 2: 使用原版

```bash
# 使用原版 (兼容性测试)
python main.py
```

### 快速命令

```bash
# 查看统计
python main_optimized.py --stats

# 导出有效 Key
python main_optimized.py --export valid.txt --status valid

# 加密导出 (新功能)
python main_optimized.py --export-encrypted secure.bin

# 解密查看
python main_optimized.py --decrypt secure.bin --key-file secure.bin.key

# 性能测试
python benchmark.py
```

详细使用指南请查看 [QUICKSTART.md](QUICKSTART.md)

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
├── main.py                    # 原版主程序
├── main_optimized.py          # 优化版主程序 (推荐)
├── scanner.py                 # GitHub 扫描器
├── scanner_async.py           # 异步扫描器适配器
├── validator.py               # Key 验证器
├── validator_async.py         # 异步验证器适配器
├── monitor.py                 # 实时监控 + 推送
├── notifier.py                # 推送通知模块
├── database.py                # 同步数据库封装
├── async_database.py          # 异步数据库封装
├── config.py                  # 配置文件
├── config.yaml                # 外部配置文件
├── benchmark.py               # 性能测试脚本
├── source_gist.py             # Gist 扫描源
├── source_gitlab.py           # GitLab 扫描源
├── source_pastebin.py         # Pastebin 扫描源
├── source_searchcode.py       # SearchCode 扫描源
├── source_realtime.py         # GitHub Events 实时监控
├── ui.py                      # Rich TUI 界面
├── QUICKSTART.md              # 快速开始指南
├── OPTIMIZATION.md            # 优化技术文档
├── MIGRATION.md               # 迁移指南
└── OPTIMIZATION_SUMMARY.md    # 优化总结报告
```

## 📚 文档索引

- **[QUICKSTART.md](QUICKSTART.md)** - 5分钟快速上手指南
- **[OPTIMIZATION.md](OPTIMIZATION.md)** - 优化技术细节和架构说明
- **[MIGRATION.md](MIGRATION.md)** - 从原版迁移到优化版的完整指南
- **[OPTIMIZATION_SUMMARY.md](OPTIMIZATION_SUMMARY.md)** - 优化成果总结报告

## 🔧 配置调优

编辑 `config.yaml` 调整性能参数:

```yaml
# 高性能配置
validator:
  max_concurrency: 200
  num_workers: 4

database:
  batch_size: 100
  flush_interval: 2.0

# 低资源配置
validator:
  max_concurrency: 50
  num_workers: 1

database:
  batch_size: 20
  flush_interval: 10.0
```

## ⚠️ 免责声明

本项目仅用于**授权的安全测试和教育目的**。严禁用于非法扫描或利用他人凭证。

使用者需自行承担所有法律责任。作者不对任何滥用行为负责。

## 🔄 版本说明

### v2.0-optimized (2026-01-11)

**重大更新:**
- 异步数据库实现，性能提升 100-430倍
- 队列容量从 1000 扩展到 10000
- 新增加密导出功能
- 配置外部化支持
- 完善的文档体系

**新增文件:**
- `main_optimized.py` - 优化版主程序
- `validator_async.py` - 异步验证器
- `scanner_async.py` - 异步扫描器
- `config.yaml` - 外部配置文件
- `benchmark.py` - 性能测试脚本
- `QUICKSTART.md` - 快速开始指南
- `OPTIMIZATION.md` - 优化技术文档
- `MIGRATION.md` - 迁移指南
- `OPTIMIZATION_SUMMARY.md` - 优化总结

**兼容性:**
- 与原版数据库 100% 兼容
- 所有原版功能保持不变
- 可随时切换回原版

详细更新日志请查看 [OPTIMIZATION_SUMMARY.md](OPTIMIZATION_SUMMARY.md)

### v1.0 (原版)

- 基础扫描功能
- 多平台验证
- 推送通知系统

## 📝 许可证

[MIT License](LICENSE)

---

**Made with ❤️ for Security Researchers**
