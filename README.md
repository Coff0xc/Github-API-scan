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

## 📖 目录

- [核心特性](#-核心特性)
- [快速开始](#-快速开始)
- [安装](#-安装)
- [配置](#-配置)
- [使用指南](#-使用指南)
- [结果查看](#-结果查看)
- [项目结构](#-项目结构)
- [相关文档](#-相关文档)
- [贡献](#-贡献)
- [许可证](#-许可证)

## ✨ 核心特性

*   **⚡ 极致性能**: 基于 `asyncio` + `aiohttp` 的异步架构，支持 **100+ 高并发** 验证，吞吐量极高。
*   **🎯 多平台支持**: 原生支持验证多种主流 AI 服务：
    *   **OpenAI**: 支持标准 Key 及 Project Key，自动识别 GPT-4 权限、RPM 等级（企业级/免费试用）。
    *   **Anthropic (Claude)**: 识别 Claude-3 Opus/Sonnet 等高价值模型。
    *   **Google Gemini**: 识别 Gemini Pro 权限。
    *   **Azure OpenAI**: 上下文感知的 Endpoint 提取与验证。
*   **🛡️ 智能断路器**: 内置域名级断路器 (Circuit Breaker)，自动熔断不稳定的服务节点，防止阻塞扫描队列，同时具备防误杀保护。
*   **🔍 深度价值评估**:
    *   **GPT-4 探测**: 自动检测 Key 是否具备 GPT-4 访问权限。
    *   **余额检测**: 探测中转站/API 的账户余额。
    *   **RPM 透视**: 通过响应头分析速率限制，精准区分付费用户与试用用户。
*   **📊 Rich TUI 仪表盘**: 使用 `rich` 库构建的终端用户界面，实时展示队列状态、扫描速度、成功率和详细日志。
*   **🧠 智能过滤**:
    *   **Sniper Dorks**: 精心设计的搜索语法，精准狙击 `.env`, `config.json` 等高价值文件，自动排除测试/示例代码。
    *   **正则清洗**: 排除示例 Key (example, test, dev) 和低熵值字符串。
    *   **黑名单机制**: 自动过滤高风险或无价值的域名。
*   **💾 数据持久化**: 使用 SQLite 数据库存储所有结果，支持断点续传和自动去重。

## 🚀 快速开始

**想要立即开始？查看 [快速开始指南](QUICKSTART.md) 了解 5 分钟快速配置步骤！**

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

### 1. 配置 GitHub Tokens

为了突破 GitHub API 的速率限制，系统支持 **Token 池轮询**。

**创建 GitHub Personal Access Token:**

1. 访问 https://github.com/settings/tokens
2. 点击 "Generate new token (classic)"
3. 选择权限范围（至少需要 `public_repo` 权限）
4. 生成并复制 token

**配置 Token:**

**方式一：创建本地配置文件（推荐）**

```bash
# 复制配置模板
cp config_local.py.example config_local.py

# 编辑配置文件，填入你的 tokens
```

在 `config_local.py` 中添加：

```python
GITHUB_TOKENS = [
    "ghp_xxxxxxxxxxxx",
    "ghp_yyyyyyyyyyyy",
    # 建议添加多个 token 以提高扫描速度
]
```

**方式二：使用环境变量**

```bash
# Linux/Mac
export GITHUB_TOKENS="ghp_xxx,ghp_yyy,ghp_zzz"

# Windows PowerShell
$env:GITHUB_TOKENS = "ghp_xxx,ghp_yyy,ghp_zzz"
```

> ⚠️ **安全提示**: 永远不要将包含真实 token 的 `config.py` 提交到公共仓库！

### 2. 配置代理（可选）

如果需要使用代理访问 GitHub API 或 AI 服务 API：

*   **方法 A (环境变量)**:
    ```bash
    # Windows
    set PROXY_URL=http://127.0.0.1:7890
    
    # Linux/Mac
    export PROXY_URL=http://127.0.0.1:7890
    ```
*   **方法 B (配置文件)**:
    修改 `config.py` 中的 `proxy_url` 字段。
*   **方法 C (命令行参数)**:
    运行时使用 `--proxy` 参数。

## 🖥️ 使用指南

### 启动扫描

直接运行主程序即可启动 TUI 仪表盘并开始扫描：

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

## 📊 结果查看

扫描结果会自动保存在 `leaked_keys.db` SQLite 数据库中。

### 使用内置查看器

项目提供了一个简单的数据库查看工具 `view_db.py`：

```bash
python view_db.py
```

该工具将显示：
- 数据库中的表结构
- 记录总数
- 前 10 条记录预览

## 📂 项目结构

*   `main.py`: 程序入口，负责协调各组件。
*   `scanner.py`: **生产者**。调用 GitHub Search API，下载文件并提取潜在 Key。
*   `validator.py`: **消费者**。异步验证 Key 的有效性，执行深度探测。
*   `config.py`: 配置文件，包含正则规则、搜索语法和 Token 池。
*   `ui.py`: 基于 Rich 的终端界面实现。
*   `database.py`: SQLite 数据库封装。
*   `leaked_keys.db`: 默认数据存储文件。
*   `view_db.py`: 数据库查看工具。

## 🤝 贡献

欢迎贡献代码、报告问题或提出建议！

- 📖 查看 [贡献指南](CONTRIBUTING.md) 了解如何参与
- 🐛 [报告 Bug](https://github.com/YOUR_USERNAME/github-secret-scanner/issues)
- 💡 [提出建议](https://github.com/YOUR_USERNAME/github-secret-scanner/issues)

## 📚 相关文档

- [快速开始指南](QUICKSTART.md) - 5 分钟快速配置
- [GitHub 发布指南](GITHUB_PUBLISH_GUIDE.md) - 如何发布项目到 GitHub
- [安全检查清单](SECURITY_CHECKLIST.md) - 发布前的安全检查
- [贡献指南](CONTRIBUTING.md) - 如何参与项目开发

## ⚠️ 免责声明

本项目仅用于**授权的安全测试和教育目的**。严禁用于非法扫描或利用他人凭证。

使用者需自行承担所有法律责任。作者不对任何滥用行为负责。

## 📝 许可证

[MIT License](LICENSE)

## 🌟 Star History

如果这个项目对你有帮助，请考虑给它一个 Star ⭐

---

**Made with ❤️ for Security Researchers**
