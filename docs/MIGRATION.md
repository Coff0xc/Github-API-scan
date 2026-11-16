# 迁移

当前安装入口是 `aikeyscan`（`pip install -e .`）。`python main_v2.2.py` 仍转发到同一实现。`main.py`、`main_optimized.py`、`main_v2.1.py` 已经删除。

```bash
aikeyscan --authorized --target-org your-org
aikeyscan --authorized --target-repo owner/name
```

扫描结束退出码：`0` 无存活密钥，`2` 有 live/quota，`1` 授权或范围失败。产物在 `.aikeyscan/runs/<id>/`。

写数据库需要 `DB_ENCRYPTION_KEY`。只有明确接受明文落盘时才加 `--allow-plaintext-db`。

Gist、Pastebin、GitLab、Searchcode、Events 默认关闭，要加 `--allow-public-sources`。这些来源不受 `org:` / `repo:` 限制，使用前先看 [AUTHORIZED_USE.md](../AUTHORIZED_USE.md)。

旧文档里的 3–5 倍、100–430 倍不是端到端测量，不能用来比较版本。
