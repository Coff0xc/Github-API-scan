<h1 align="center">AI API Key Scanner</h1>

<p align="center">
扫一个组织、一个仓库，或一份本地 git 树。<br>
每条发现是一对 <code>(密钥, base_url)</code>：向文件里写的那个地址确认密钥是否仍有效，再写出脱敏记录。<br>
完整密钥留在跑扫描的那台机器上。
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-3776AB?logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/license-MIT-111827" alt="MIT license">
  &nbsp;<a href="README.md">English</a>
</p>

<p align="center">
  <img src="assets/screenshot.png" alt="发现记录面板：平台、脱敏预览、文件位置、处置状态" width="920">
</p>

```bash
git clone https://github.com/Coff0xc/Github-API-scan.git
cd Github-API-scan
pip install -e ".[dev]"

aikeyscan --authorized --target-org your-org
aikeyscan --authorized --target-repo owner/name
aikeyscan --authorized --scan-local ./your-repo

python web_dashboard.py    # http://127.0.0.1:5000
```

`python main_v2.2.py` 仍是同一条命令。

处理顺序：从文件（本地历史按 blob 去重）抽出密钥形状 → 熵和路径丢掉示例串 → 重叠命中只留更长的 → 绑最近的 `base_url` → 向该主机验证（SSRF 拦私网，本机中转可走 loopback）→ 一次写入最终状态。正则在 import 时编译一次。远程搜索必须带 `--target-org` 或 `--target-repo`。

运行前读 [AUTHORIZED_USE.md](AUTHORIZED_USE.md)，用 `--authorized` 确认范围。远程搜索必须带 `--target-org` 或 `--target-repo`。完整说明、字段表、面板接口见 [英文 README](README.md)。

## 三条常用命令

```bash
aikeyscan --authorized --target-org your-org
python web_dashboard.py
aikeyscan --findings-json findings.json
```

`GITHUB_TOKENS`、`DB_ENCRYPTION_KEY`、`DASHBOARD_TOKEN` 用环境变量或 `config_local.py` 配置，不要提交进 git。
