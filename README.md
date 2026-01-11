# GitHub Secret Scanner Pro

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Status](https://img.shields.io/badge/status-active-success.svg)
![Version](https://img.shields.io/badge/version-v2.2--smart--cache-orange.svg)
![Performance](https://img.shields.io/badge/performance-100x+-brightgreen.svg)

🚀 **企业级 GitHub 密钥扫描与验证系统 - v2.2 智能缓存版**

GitHub Secret Scanner Pro 是一款高性能的自动化工具，专为安全研究人员和红队设计。它利用 GitHub API 实时扫描代码库中的敏感密钥，并使用高并发异步架构进行深度有效性验证。

**v2.2 智能缓存版**在 v2.1 基础上引入智能缓存系统和批量验证优化，实现 **30-50%** 的额外性能提升。

> ⚠️ **免责声明**: 本项目仅用于授权的安全测试和教育目的。严禁用于非法扫描或利用他人凭证。使用者需自行承担所有法律责任。

## 📸 运行截图

<div align="center">
  <img src="assets/screenshot.png" alt="Dashboard" width="800"/>
  <br>
  <br>
  <img src="assets/screenshot1.png" alt="Results" width="800"/>
</div>

## ✨ 核心特性

### 🚀 v2.2 智能缓存版新特性

**在 v2.1 基础上的智能缓存优化：**

- **3层缓存架构** - L1验证结果缓存 + L2域名健康度 + L3指纹去重，命中率 30-50%
- **批量验证优化** - 按域名分组验证，网络请求减少 40-60%，DNS查询减少 70-80%
- **域名健康追踪** - 自动识别死域名并跳过，避免无效验证
- **LRU缓存淘汰** - 智能淘汰最少使用条目，内存使用可控
- **自动缓存清理** - 定期清理过期缓存，保持系统高效

**v2.1 优化特性（保留）：**

- **HTTP 连接池** - 按域名复用连接，减少 TCP/TLS 握手开销 70-80%
- **智能重试机制** - 指数退避 + 错误分类，成功率提升 15-25%
- **动态队列管理** - 根据内存压力自动调整，内存使用降低 30-50%
- **性能监控系统** - P50/P95/P99 延迟统计，实时吞吐量追踪

**v2.0 核心特性（保留）：**

- **异步数据库** - 使用 aiosqlite 实现批量写入，性能提升 **100-430倍**
- **队列扩容** - 从 1000 提升到 10000，支持更高吞吐量
- **加密导出** - 使用 Fernet 对称加密保护敏感数据
- **配置外部化** - config.yaml 支持，无需修改代码即可调参
- **配置验证** - 启动时自动检查配置完整性
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

### 方式 1: 使用 v2.2 智能缓存版 (推荐)

```bash
# 克隆仓库
git clone https://github.com/Coff0xc/Github-API-scan.git
cd Github-API-scan

# 安装依赖
pip install -r requirements.txt

# 配置 GitHub Token
export GITHUB_TOKENS="ghp_xxxxxxxxxxxx,ghp_yyyyyyyyyyyy"
# 或创建 config_local.py 文件

# 启动 v2.2 智能缓存版扫描
python main_v2.2.py

# 禁用缓存（回退到 v2.1 行为）
python main_v2.2.py --no-cache
```

### 方式 2: 使用 v2.1 优化版

```bash
# 使用 v2.1 优化版
python main_v2.1.py
```

### 方式 3: 使用原版

```bash
# 使用原版 (兼容性测试)
python main.py
```

### 快速命令

```bash
# 查看统计
python main_v2.2.py --stats

# 导出有效 Key
python main_v2.2.py --export valid.txt --status valid

# 导出 CSV 格式
python main_v2.2.py --export-csv keys.csv --status valid

# 加密导出
python main_v2.2.py --export-encrypted secure.bin

# 解密查看
python main_v2.2.py --decrypt secure.bin --key-file secure.bin.key

# 性能测试
python benchmark.py

# v2.2 功能测试
python test_v2.2.py
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
├── main_v2.1.py               # v2.1 优化版主程序
├── main_v2.2.py               # v2.2 智能缓存版主程序 (推荐)
├── scanner.py                 # GitHub 扫描器
├── scanner_async.py           # 异步扫描器适配器
├── validator.py               # Key 验证器
├── validator_async.py         # 异步验证器适配器
├── validator_optimized.py     # v2.2 优化版验证器
├── cache_manager.py           # v2.2 智能缓存管理器
├── batch_validator.py         # v2.2 批量验证器
├── connection_pool.py         # v2.1 HTTP 连接池
├── retry_handler.py           # v2.1 智能重试处理器
├── queue_manager.py           # v2.1 动态队列管理器
├── performance_monitor.py     # v2.1 性能监控系统
├── monitor.py                 # 实时监控 + 推送
├── notifier.py                # 推送通知模块
├── database.py                # 同步数据库封装
├── async_database.py          # 异步数据库封装
├── config.py                  # 配置文件
├── config.yaml                # 外部配置文件
├── benchmark.py               # 性能测试脚本
├── test_v2.2.py               # v2.2 功能测试
├── source_gist.py             # Gist 扫描源
├── source_gitlab.py           # GitLab 扫描源
├── source_pastebin.py         # Pastebin 扫描源
├── source_searchcode.py       # SearchCode 扫描源
├── source_realtime.py         # GitHub Events 实时监控
├── ui.py                      # Rich TUI 界面
├── QUICKSTART.md              # 快速开始指南
├── OPTIMIZATION.md            # 优化技术文档
├── OPTIMIZATION_V2.1.md       # v2.1 优化报告
├── OPTIMIZATION_V2.2.md       # v2.2 优化报告
├── MIGRATION.md               # 迁移指南
└── OPTIMIZATION_SUMMARY.md    # 优化总结报告
```

## 📚 文档索引

- **[QUICKSTART.md](QUICKSTART.md)** - 5分钟快速上手指南
- **[OPTIMIZATION.md](OPTIMIZATION.md)** - 优化技术细节和架构说明
- **[OPTIMIZATION_V2.1.md](OPTIMIZATION_V2.1.md)** - v2.1 优化报告（连接池、智能重试、动态队列）
- **[OPTIMIZATION_V2.2.md](OPTIMIZATION_V2.2.md)** - v2.2 优化报告（智能缓存、批量验证）
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

### v2.2-smart-cache (2026-01-12)

**重大更新:**
- 智能缓存系统 - 3层缓存架构（L1/L2/L3），缓存命中率 30-50%
- 批量验证优化 - 按域名分组，网络请求减少 40-60%
- 域名健康度追踪 - 自动识别死域名并跳过
- LRU 缓存淘汰 - 智能淘汰最少使用条目
- 自动缓存清理 - 定期清理过期缓存

**新增文件:**
- `main_v2.2.py` - v2.2 智能缓存版主程序
- `cache_manager.py` - 智能缓存管理器
- `batch_validator.py` - 批量验证器
- `validator_optimized.py` - v2.2 优化版验证器
- `test_v2.2.py` - v2.2 功能测试
- `OPTIMIZATION_V2.2.md` - v2.2 优化报告

**性能提升:**
- 验证延迟降低 30-40%
- 网络请求减少 40-60%
- DNS 查询减少 70-80%
- 重复验证减少 60-80%

**兼容性:**
- 完全兼容 v2.1 所有功能
- 可通过 `--no-cache` 禁用缓存
- 数据库格式无变化

详细更新日志请查看 [OPTIMIZATION_V2.2.md](OPTIMIZATION_V2.2.md)

### v2.1-optimized (2026-01-11)

**重大更新:**
- HTTP 连接池 - 按域名复用连接，减少 TCP/TLS 握手开销 70-80%
- 智能重试机制 - 指数退避 + 错误分类，成功率提升 15-25%
- 动态队列管理 - 根据内存压力自动调整，内存使用降低 30-50%
- 性能监控系统 - P50/P95/P99 延迟统计，实时吞吐量追踪

**新增文件:**
- `main_v2.1.py` - v2.1 优化版主程序
- `connection_pool.py` - HTTP 连接池管理器
- `retry_handler.py` - 智能重试处理器
- `queue_manager.py` - 动态队列管理器
- `performance_monitor.py` - 性能监控系统
- `OPTIMIZATION_V2.1.md` - v2.1 优化报告

**兼容性:**
- 完全兼容 v2.0 所有功能
- 数据库格式无变化

详细更新日志请查看 [OPTIMIZATION_V2.1.md](OPTIMIZATION_V2.1.md)

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
