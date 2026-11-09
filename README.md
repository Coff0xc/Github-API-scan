# AI API Key Scanner

在授权范围内找出泄露的 API 密钥，配对中转地址，扫描结束给出脱敏发现记录。唯一入口是 `main_v2.2.py`。范围是你拥有或已获授权的 GitHub 组织、仓库，或本机目录。

程序先把密钥和它旁边的 `base_url` 配成一对，再按 [AUTHORIZED_USE.md](AUTHORIZED_USE.md) 的边界决定要不要向该地址发验证请求。结果进本地 SQLite。交给人或代理的默认材料是脱敏发现记录，不是一套能直接调用的密钥。

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

<img src="assets/screenshot.png" alt="Dashboard" width="800"/>

## 它做什么

1. **搜索。** 远程搜索必须带 `--target-org` 或 `--target-repo`。没有范围，GitHub 请求不会发出。`--scan-local` 扫本地目录，包含当前文件和 Git 历史。
2. **配对。** 从命中文件里取出密钥，并尽量绑定同一上下文里的 `base_url`。中转站、Azure 和官方地址因此不会被当成同一个目标。
3. **过滤。** 熵和路径黑名单去掉 `sk-test`、文档占位符和明显的假值。
4. **验证。** 只应对授权资产这么做。验证结果是 `pending`、`valid`、`invalid` 或 `quota_exceeded`。对别人的密钥做「是否有效」不在允许范围内。
5. **入库。** 设置 `DB_ENCRYPTION_KEY` 后，`api_key` 列是 Fernet 密文，去重用 SHA-256。未设置时扫描拒绝写入，除非显式加上 `--allow-plaintext-db`。
6. **交出。** 扫描结束会写出 `findings.json`。里面只有指纹、平台、脱敏预览、仓库、路径、提交、链接、处置状态和发现时间。处置状态是 `open`、`notified`、`rotated`、`false_positive`。配了通知渠道时，可用密钥会发出平台、预览和位置，然后标成 `notified`。确认吊销后用 `--set-disposition <指纹> rotated`。余额和高价值不写入结果。

`--report` 生成的是授权评估用的威胁报告，默认脱敏。完整密钥只在 `--reveal` 或 `--reveal-report` 时出现。

Grok Bot 和 Muse 只读发现文件、回写处置状态。它们不跑扫描，也不拿 `DB_ENCRYPTION_KEY` 和 `DASHBOARD_TOKEN`。见 [docs/AGENT_PIPELINE.md](docs/AGENT_PIPELINE.md)。

## 快速开始

Python 3.10+。

```bash
git clone https://github.com/Coff0xc/Github-API-scan.git
cd Github-API-scan
pip install -r requirements.txt
```

令牌和库密钥放在环境变量或 gitignore 掉的 `config_local.py` 里：

```bash
export GITHUB_TOKENS="ghp_your_token_here"
export DB_ENCRYPTION_KEY="一段足够长的随机密码"
export DASHBOARD_TOKEN="另一段随机密码"
```

```bash
python main_v2.2.py --authorized --target-org your-org
python main_v2.2.py --authorized --target-repo owner/name
python main_v2.2.py --authorized --scan-local D:\repos\target
```

`--authorized` 表示确认 [AUTHORIZED_USE.md](AUTHORIZED_USE.md)。CI 里用 `SCANNER_AUTHORIZED=1`。都没有时，交互终端会要求输入 `y`。Docker Compose 不会替你打开这个开关，也不会替你填组织名。

## 常用命令

```bash
python main_v2.2.py --stats
python main_v2.2.py --findings-json findings.json
python main_v2.2.py --set-disposition <64位指纹> rotated
python main_v2.2.py --set-disposition <64位指纹> notified
python main_v2.2.py --apply-dispositions dispositions.json

python main_v2.2.py --export results.txt --status valid
python main_v2.2.py --export-csv results.csv --status valid
python main_v2.2.py --export-encrypted secure.bin

python main_v2.2.py --authorized --report threat.md
python main_v2.2.py --authorized --scan-local D:\repos\target --report threat.md
```

文本和 CSV 默认脱敏。Gist、Pastebin、GitLab、Searchcode、Events 不受组织或仓库限定，默认关闭，要同时加 `--allow-public-sources`。

## 识别范围

OpenAI、Anthropic、Gemini、Azure OpenAI、xAI、Meta Llama、OpenRouter、Portkey、LiteLLM、Cloudflare AI、AWS Bedrock、Vertex AI、阿里云、火山引擎、腾讯混元、百度千帆、DeepSeek、Moonshot、智谱、Groq、Cohere、Mistral，以及 Hugging Face、Together、Replicate、Perplexity、Fireworks 等。没有单独规则的服务走通用匹配。GitHub 令牌、AWS、Stripe 也在通用范围内。

## 边界

允许的是自有资产审计、书面授权的评估、你自己凭据的应急，以及自建环境里的检测研究。

不要用它扫没有授权的仓库来收集密钥，不要验证别人的密钥，不要使用或传播扫到的密钥。发现之后要通知资产所有方，通知里不贴完整密钥。细节在 [AUTHORIZED_USE.md](AUTHORIZED_USE.md) 和 [SECURITY.md](SECURITY.md)。

## 配置

优先级是内置默认值，然后 `config.yaml`，然后 `config_local.py`，最后是命令行。`config.yaml` 里的熵阈值、并发、黑名单和批量写入会被读进去。

本机面板默认是 `127.0.0.1:5000`。令牌只放在请求头 `X-API-Token`。

## 代码从哪读

```
main_v2.2.py            唯一入口
scanner.py              搜索，以及密钥和 base_url 的配对
validator_optimized.py  入口使用的验证循环
validator.py            熔断、验证结果、验证请求
findings_feed.py        脱敏发现记录
database.py             SQLite
key_vault.py            结果库加密
threat_report.py        授权评估报告
web_dashboard.py        本机面板
```

## 文档

- [docs/QUICKSTART.md](docs/QUICKSTART.md)
- [docs/USAGE_GUIDE.md](docs/USAGE_GUIDE.md)
- [docs/LOCAL_SCANNING.md](docs/LOCAL_SCANNING.md)
- [docs/AGENT_PIPELINE.md](docs/AGENT_PIPELINE.md)
- [docs/DOCKER_GUIDE.md](docs/DOCKER_GUIDE.md)
- [docs/WEB_DASHBOARD_GUIDE.md](docs/WEB_DASHBOARD_GUIDE.md)
- [docs/NOTIFY_README.md](docs/NOTIFY_README.md)

## 许可

MIT。见 [LICENSE](LICENSE)。
