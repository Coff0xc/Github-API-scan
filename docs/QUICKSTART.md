# 快速开始

唯一入口是 `main_v2.2.py`。远程搜索只在你指定的组织或仓库里进行。

## 安装

```bash
git clone https://github.com/Coff0xc/Github-API-scan.git
cd Github-API-scan
pip install -r requirements.txt
```

Python 3.10+。Windows 上不要安装 `uvloop`。

## 配置

令牌不要提交进仓库。任选一种：

```bash
export GITHUB_TOKENS="ghp_your_token_here"
export DB_ENCRYPTION_KEY="一段足够长的随机密码"
```

或复制 `config_local.py.example` 为 `config_local.py`，只在本机保存。

GitHub 令牌需要能搜索你要审计的那个组织或仓库。经典令牌至少勾选对应仓库的读取权限。

## 第一次扫描

```bash
python main_v2.2.py --authorized --target-org your-org
```

`--target-repo` 必须是 `owner/name`。没有这两个参数之一，GitHub 搜索不会发出。

未设置 `DB_ENCRYPTION_KEY` 时，扫描拒绝写入，除非加上 `--allow-plaintext-db`。

本地目录：

```bash
python main_v2.2.py --authorized --scan-local D:\repos\target
```

## 查看和导出

```bash
python main_v2.2.py --stats
python main_v2.2.py --export results.txt --status valid
python main_v2.2.py --findings-json findings.json
```

文本和 CSV 默认脱敏。明文导出需要 `--reveal`。`findings.json` 给外部代理，里面没有明文密钥。说明见 [AGENT_PIPELINE.md](AGENT_PIPELINE.md)。

## 相关文档

- [AUTHORIZED_USE.md](../AUTHORIZED_USE.md)
- [USAGE_GUIDE.md](USAGE_GUIDE.md)
- [LOCAL_SCANNING.md](LOCAL_SCANNING.md)
- [MIGRATION.md](MIGRATION.md)
