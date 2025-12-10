# GitHub Secret Scanner Pro

🚀 **企业级 GitHub 密钥扫描与验证系统**

GitHub Secret Scanner Pro 是一款高性能的自动化工具，专为安全研究人员和红队设计。它利用 GitHub API 实时扫描代码库中的敏感密钥，并使用高并发异步架构进行深度有效性验证。

> ⚠️ **免责声明**: 本项目仅用于授权的安全测试和教育目的。严禁用于非法扫描或利用他人凭证。使用者需自行承担所有法律责任。

## 📸 界面预览

![GitHub Secret Scanner Pro - 完整版 UI 界面](assets/screenshot.png)

*完整版 TUI 仪表盘：实时统计数据、扫描日志、有效 Key 列表一目了然*

> 📢 **版本说明**: 本公开仓库所含代码并非完全版本，仅作为安全研究项目展示使用。出于安全与合规考量，最新、最强大的完整版本未上传至此公开仓库。若需要最新最强大的版本，请发送邮件至 **Coff0xc@protonmail.com**。

## ✨ 核心特性

*   **⚡ 异步架构**: 基于 `asyncio` + `aiohttp` 实现异步下载与验证。公开版默认配置：下载并发 20、验证并发 40、线程数 6（完整版支持更高并发与更多线程）。
*   **🎯 多平台支持**: 原生支持验证多种主流 AI 服务：
    *   **OpenAI**: 支持标准 Key 及 Project Key，自动识别 GPT-4 权限、RPM 等级（企业级/免费试用）。
    *   **Anthropic (Claude)**: 识别 Claude-3 Opus/Sonnet 等高价值模型。
    *   **Google Gemini**: 识别 Gemini Pro 权限。
    *   **Azure OpenAI**: 上下文感知的 Endpoint 提取与验证。
*   **🛡️ 智能断路器**: 域名级 Circuit Breaker，5 次连续失败后熔断 60 秒，半开状态允许 3 次试探。官方 API 域名（`api.openai.com` 等）受白名单保护，永不熔断。
*   **🔍 深度价值评估**:
    *   **GPT-4 探测**: 自动检测 Key 是否具备 GPT-4 访问权限。
    *   **余额检测**: 探测中转站/API 的账户余额。
    *   **RPM 透视**: 通过响应头分析速率限制，精准区分付费用户与试用用户。
*   **📊 Rich TUI 仪表盘**: 使用 `rich` 库构建的终端用户界面，实时展示队列状态、扫描速度、成功率和详细日志。
*   **🧠 智能过滤**:
    *   **Sniper Dorks**: 公开版包含 5 条基础搜索语法示例（完整版包含 20+ 条高精度狙击规则）。
    *   **熵值检测**: 阈值 3.8，过滤低质量假 Key（如 `sk-test-123`）。
    *   **正则清洗**: 排除示例 Key（example, test, dev, staging, sandbox 等）。
    *   **路径/域名黑名单**: 自动跳过 `/test/`, `/examples/`, `localhost`, `ngrok.io` 等无价值目标。
*   **💾 数据持久化**: 使用 SQLite 数据库存储所有结果，支持断点续传和自动去重。

## 🛠️ 安装

确保你的 Python 版本 >= 3.9。

```bash
# 克隆仓库
git clone https://github.com/yourusername/github-secret-scanner.git
cd github-secret-scanner

# 安装依赖
# 推荐安装 speedups 扩展以获得最佳性能
pip install -r requirements.txt
```

## ⚙️ 配置

### 1. 配置代理 (中国大陆必需)

由于 GitHub API 和各大 AI 厂商的 API 在部分地区无法直接访问，建议配置代理。

*   **方法 A (环境变量)**:
    ```bash
    set PROXY_URL=http://127.0.0.1:7890
    ```
*   **方法 B (配置文件)**:
    修改 `config.py` 中的 `proxy_url` 字段。
*   **方法 C (命令行参数)**:
    运行时使用 `--proxy` 参数。

### 2. 配置 GitHub Tokens（已脱敏）

默认不再内置任何 PAT；请通过环境变量注入以避免泄露：

```bash
set GITHUB_TOKENS=ghp_xxx,ghp_yyy  # 逗号或空格分隔均可
```

运行时会自动解析 `GITHUB_TOKENS` 并轮换使用。你也可以在代码里手动赋值，但请勿提交真实 Token。

## 🚀 使用方法

### 启动扫描

直接运行主程序即可启动 TUI 仪表盘并开始扫描（默认并发已下调，资源占用更温和）：

```bash
python main.py
```

如果你需要指定代理：

```bash
python main.py --proxy http://127.0.0.1:7890
```

### 导出结果

将数据库中的有效 Key 导出为文本文件：

```bash
python main.py --export output.txt
```

导出为 CSV 格式（包含详细元数据：余额、模型分级、RPM等）：

```bash
python main.py --export-csv results.csv
```

仅导出特定状态的 Key：

```bash
python main.py --export output.txt --status valid
python main.py --export output.txt --status quota_exceeded
```

### 查看统计

查看数据库中的统计概览：

```bash
python main.py --stats
```

## 📂 项目结构

*   `main.py`: 程序入口，Producer-Consumer 架构协调器，支持 `--export`/`--stats` 等命令。
*   `scanner.py`: **生产者** — 调用 GitHub Search API，aiohttp 异步批量下载，熵值/黑名单过滤，SHA 去重。
*   `validator.py`: **消费者** — asyncio 异步验证，GPT-4 探测、余额检测、RPM 透视，断路器保护。
*   `config.py`: 集中配置（正则、搜索语法、断路器参数、Token 池），公开版已脱敏。
*   `ui.py`: Rich TUI 仪表盘（实时统计、日志、有效 Key 列表）。
*   `database.py`: SQLite 封装，`leaked_keys` 与 `scanned_blobs` 双表持久化去重。
*   `check_db.py` / `view_db.py`: 数据库快速查看/交互查询脚本。

> **公开版轻量化配置**：下载并发 20、验证并发 40、线程 6、请求超时 12s、搜索关键词 5 条。如需更高强度扫描，请联系获取完整版或自行在 `config.py` / `scanner.py` / `validator.py` 中调整参数。

## 📝 许可证

[MIT License](LICENSE)
