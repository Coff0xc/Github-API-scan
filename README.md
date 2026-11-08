# AI API Key Scanner

Scan GitHub repositories for leaked AI API keys and validate them. Supports 50+ platforms including OpenAI, Claude, Gemini, and basically everything else you'd want to check.

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Version](https://img.shields.io/badge/version-3.0-orange.svg)

**Latest update (July 2026)**: Added support for OpenRouter, AWS Bedrock, xAI Grok, and a bunch of other platforms that appeared this year.

<img src="assets/screenshot.png" alt="Dashboard" width="800"/>

## What does this do?

Searches GitHub for exposed API keys, then validates them to see if they actually work. Simple as that.

The tool has a terminal UI and skips keys it has already checked. The old "430x" figure was not an end-to-end measurement. `benchmark.py` only times database inserts.

## Supported platforms

**Major AI platforms:**
- OpenAI (GPT-4, GPT-5)
- Anthropic (Claude)
- Google (Gemini)
- Azure OpenAI
- xAI (Grok)
- Meta (Llama API)

**API aggregators** (these are gold mines):
- OpenRouter
- Portkey
- LiteLLM
- Cloudflare Workers AI

**Cloud provider AI services:**
- AWS Bedrock
- Google Vertex AI
- Alibaba Cloud
- Volcano Engine
- Tencent Cloud
- Baidu Qianfan

**Regional providers:**
- DeepSeek, Moonshot, Zhipu (Chinese platforms)
- Groq, Mistral, Cohere (International)
- Plus 20+ more platforms

Full list: OpenAI, Anthropic, Google Gemini, Azure, xAI, Meta Llama, OpenRouter, Portkey, LiteLLM, Cloudflare AI, AWS Bedrock, Vertex AI, Alibaba Cloud, Volcano Engine, Tencent Hunyuan, Baidu Qianfan, DeepSeek, Moonshot, Zhipu, Yi AI, StepFun, iFlytek, HuggingFace, Groq, Cohere, Mistral, Together AI, Replicate, Perplexity, Fireworks, AI21, Writer, Forefront, Modal, RunPod, Baseten, and generic services like AWS, GitHub tokens, Stripe, etc.

## Performance

Tested on 1000 keys:

Async I/O, caching, connection pooling, and batch writes are what the v2.2 path actually changes. Do not treat the old 0.24-second table as a full scan benchmark.

## Quick start

**Requirements:**
- Python 3.10+
- GitHub personal access token (free, takes 2 minutes to get)

**Install:**

```bash
git clone https://github.com/Coff0xc/Github-API-scan.git
cd Github-API-scan
pip install -r requirements.txt
```

**Configure:**

Create `config_local.py` (or copy `.env.example` to `.env` for Docker):

```python
GITHUB_TOKENS = [
    "ghp_your_token_here",  # Get from github.com/settings/tokens
]

# Optional proxy
PROXY_URL = ""  # e.g., "http://127.0.0.1:7890"
```

To get a GitHub token:
1. Go to https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Check `public_repo` 
4. Copy the token

**Run:**

```bash
python main_v2.2.py --authorized --target-org your-org
```

Remote search does not start without `--target-org` or `--target-repo`. Set `DB_ENCRYPTION_KEY` first, or pass `--allow-plaintext-db`.

> `--authorized` confirms the use boundary in AUTHORIZED_USE.md. `SCANNER_AUTHORIZED=1` does the same for CI. Docker Compose does not set that variable for you. Without either one, an interactive terminal asks for `y`.

**Recommended security environment variables** (copy from `.env.example`):

```bash
export DB_ENCRYPTION_KEY=<随机长密码>   # 结果库静态加密（api_key 不落明文）
export DASHBOARD_TOKEN=<随机长密码>     # Web 面板访问令牌（未设置时功能受限）
```

## Usage

Basic commands:

```bash
# Remote scan. Refuses to start unless the search is limited to an org or repo.
python main_v2.2.py --authorized --target-org your-org

# View stats
python main_v2.2.py --stats

# Export is masked unless you pass --reveal
python main_v2.2.py --export results.txt --status valid

# Export to CSV
python main_v2.2.py --export-csv results.csv --status valid

# Encrypted export (recommended when you need the raw key)
python main_v2.2.py --export-encrypted secure.bin
```

Set `DB_ENCRYPTION_KEY` before a scan writes anything. `--allow-plaintext-db` is the explicit override.

Advanced options:

```bash
# Disable cache (slower but uses less memory)
python main_v2.2.py --authorized --target-org your-org --no-cache

# Public sources are not limited by org: or repo:. They stay off unless you opt in.
python main_v2.2.py --authorized --target-org your-org --all-sources --allow-public-sources

# Use custom database
python main_v2.2.py --db custom.db --stats
```

**授权渗透 / 自有资产审计（authorized engagement）：**

```bash
# 本地仓库审计：当前文件 + 全量 Git 历史（已删除的密钥也能找到）
python main_v2.2.py --authorized --scan-local D:\repos\target

# 扫描 + 直接产出威胁报告（存活凭据 = 威胁点，附处置建议）
python main_v2.2.py --authorized --scan-local D:\repos\target --report threat.md

# 远程 GitHub 搜索限定到授权范围（所有查询自动追加 org:/repo: 限定符）
python main_v2.2.py --authorized --target-org customer-org
python main_v2.2.py --authorized --target-repo customer-org/api-server

# 基于已有结果库单独出报告（默认脱敏，--reveal-report 输出完整 Key）
python main_v2.2.py --authorized --report threat.md --reveal-report
```

详见 [docs/LOCAL_SCANNING.md](docs/LOCAL_SCANNING.md)。

## How it works

1. **Scan**: Searches GitHub using optimized queries (93 different search patterns)
2. **Filter**: Removes test keys, fake keys, and garbage using entropy analysis
3. **Deduplicate**: Checks cache and database to avoid re-validating
4. **Validate**: Tests keys against actual API endpoints (100+ concurrent requests)
5. **Store**: Saves results to SQLite database

The tool uses a 3-layer cache:
- L1: Validation results (30-50% hit rate)
- L2: Domain health (skips dead domains)
- L3: Key fingerprints (duplicate detection)

## Security hardening (v3.0.1)

| Mechanism | How to enable | Effect |
|---|---|---|
| 使用边界确认 | `--authorized` / `SCANNER_AUTHORIZED=1` | 启动前强制确认仅授权使用。Docker 不再默认写成 1 |
| 远程范围 | `--target-org` / `--target-repo` | 没有范围时 GitHub 搜索不会发出 |
| 公开源 | `--allow-public-sources` | Gist、Pastebin、GitLab、Searchcode、Events 默认关闭 |
| 写库加密 | `DB_ENCRYPTION_KEY` | 未设置时扫描拒绝写入，除非 `--allow-plaintext-db` |
| 导出脱敏 | `--export` / `--reveal` | 文本和 CSV 默认脱敏 |
| 代理管道 | `--findings-json` | 给 Grok Bot / Muse 的 JSON 不含明文 Key。说明见 [docs/AGENT_PIPELINE.md](docs/AGENT_PIPELINE.md) |
| 结果库静态加密 | `DB_ENCRYPTION_KEY` 环境变量 | `api_key` 列存 Fernet 密文，去重走 SHA-256 指纹 |
| Web 面板鉴权 | `DASHBOARD_TOKEN` 环境变量 | Key 默认脱敏；reveal/导出/推送需令牌，认证失败限速 |
| 加密导出 | `GET /api/export`（需令牌） | 返回 Fernet 加密 JSON；`mask=1` 可导脱敏版 |
| config.yaml 生效 | 编辑 `config.yaml` | 熵阈值/并发/黑名单/批量写入等参数现由代码实际读取 |

`config.yaml` 现在是真实生效的外部配置（优先级：内置默认 < config.yaml <
config_local.py < 命令行参数）。

## Configuration

Edit `config.yaml` to tune performance:

```yaml
# High-performance setup (16GB+ RAM)
validator:
  max_concurrency: 200
  num_workers: 4

database:
  batch_size: 100
  flush_interval: 2.0

# Low-resource setup (8GB RAM)
validator:
  max_concurrency: 50
  num_workers: 1

database:
  batch_size: 20
  flush_interval: 10.0
```

## Project structure

```
├── main_v2.2.py          # Only implementation
├── main.py               # Shim. Forwards arguments to main_v2.2.py
├── main_v2.1.py          # Shim
├── main_optimized.py     # Shim
│
├── scanner.py            # GitHub scanning (requires an org or repo)
├── validator_optimized.py # Validation path used by main_v2.2.py
├── validator.py          # Shared validation primitives
├── database.py           # SQLite storage
├── config.py             # Platform config (50+ platforms)
│
├── cache_manager.py      # Smart caching
├── batch_validator.py    # Batch processing
├── connection_pool.py    # HTTP connection reuse
├── retry_handler.py      # Retry logic
│
├── source_*.py           # Additional sources (Gist, GitLab, etc.)
├── monitor.py            # Real-time monitoring
├── ui.py                 # Terminal UI
└── config.yaml           # User config
```

## Version history

**v3.0 (2026-07-24):**
- Added 20+ new platforms (OpenRouter, AWS Bedrock, xAI Grok, etc.)
- Updated GitHub search syntax (removed deprecated `NOT` operator)
- All comments and docs now in English
- 93 optimized search queries (up from 70)

**v2.2 (2026-01-12):**
- Smart caching system (30-50% cache hit rate)
- Batch validation (40-60% fewer requests)
- Domain health tracking

**v2.1 (2026-01-11):**
- HTTP connection pooling
- Smart retry mechanism
- Performance monitoring

**v2.0 (2026-01-11):**
- Async database writes (`benchmark.py` measures this micro-benchmark only)
- Queue expansion (1000 → 10000)
- Encrypted export

## Legal stuff

This tool is for **authorized security testing only**. See [AUTHORIZED_USE.md](AUTHORIZED_USE.md) for the full boundary policy (enforced at startup).

Don't use it to:
- Scan repos you don't have permission to test
- Exploit keys you find
- Do anything illegal

If you find leaked keys:
1. Report them to the repo owner
2. Don't use them
3. Don't share them

The authors are not responsible for misuse. You're an adult, act like one.

## Security recommendations

**For researchers:**
- Always get authorization first
- Use encrypted export for findings
- Report through proper channels
- Rate limit your scans

**For developers who got breached:**

If this tool found your key:

```bash
# 1. Revoke the key NOW (don't wait)

# 2. Remove from git history
git filter-repo --path path/to/file --invert-paths

# 3. Add to .gitignore
echo ".env*" >> .gitignore
echo "config_local.py" >> .gitignore

# 4. Use environment variables
export OPENAI_API_KEY="sk-..."

# 5. Install pre-commit hooks
pip install pre-commit gitleaks
pre-commit install
```

## Performance

`benchmark.py` compares synchronous and asynchronous SQLite inserts on synthetic rows. It does not search GitHub or call provider APIs. Run it locally if you need a number for the database path. The 108x / 320x / 430x table that used to be here was not reproducible from that script and has been removed.

## Documentation

**根目录**
- [AUTHORIZED_USE.md](AUTHORIZED_USE.md) - **使用边界声明（必读）**

**docs/**
- [QUICKSTART.md](docs/QUICKSTART.md) - Get started in 5 minutes
- [USAGE_GUIDE.md](docs/USAGE_GUIDE.md) - 完整使用说明
- [AI_ASSISTED_ANALYSIS.md](docs/AI_ASSISTED_ANALYSIS.md) - AI 辅助假阳性过滤接入（Ollama / OpenAI 兼容 API）
- [DOCKER_GUIDE.md](docs/DOCKER_GUIDE.md) - Docker 部署
- [FOFA_GUIDE.md](docs/FOFA_GUIDE.md) - FOFA 扩展源
- [WEB_DASHBOARD_GUIDE.md](docs/WEB_DASHBOARD_GUIDE.md) - Web 面板
- [DEEP_VALIDATION_GUIDE.md](docs/DEEP_VALIDATION_GUIDE.md) - 深度验证
- [REALTIME_PIPELINE_GUIDE.md](docs/REALTIME_PIPELINE_GUIDE.md) - 实时通知管道
- [NOTIFY_README.md](docs/NOTIFY_README.md) - 通知渠道配置
- [OPTIMIZATION.md](docs/OPTIMIZATION.md) - Technical details
- [MIGRATION.md](docs/MIGRATION.md) - Upgrade guide
- [CHANGELOG_V3.0.md](docs/CHANGELOG_V3.0.md) - What's new
- [archive/](docs/archive/) - 历史过程文档（50+ 份开发报告存档）

## Contributing

Found a bug? Want to add a platform? PRs welcome.

```bash
# Fork and clone
git clone https://github.com/Coff0xc/Github-API-scan.git

# Create branch
git checkout -b feature/new-platform

# Make changes and test
python test_v2.2.py

# Submit PR
git push origin feature/new-platform
```

## FAQ

**Q: Is this legal?**  
A: Yes, if you have authorization. No, if you don't.

**Q: Why do I need a GitHub token?**  
A: GitHub rate limits unauthenticated requests to 10/min. With a token you get 30/min per token.

**Q: Can I scan private repos?**  
A: No. This tool only scans public repositories.

**Q: What if a key is rate limited?**  
A: The tool marks it as "quota_exceeded" instead of "invalid". Still a valid key, just hit the limit.

**Q: Why are some platforms missing?**  
A: Either they don't have a public API, or I haven't added them yet. PRs welcome.

**Q: Can this get me in trouble?**  
A: Only if you use it irresponsibly. Don't be stupid.

## License

MIT License. See [LICENSE](LICENSE) file.

## Credits

Built by security researchers, for security researchers.

Uses: aiohttp, Rich, PyGithub, loguru, and other open source libraries.

---

**Use responsibly.** Don't be the reason GitHub adds more rate limits.
