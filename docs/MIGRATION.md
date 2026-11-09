# 迁移

当前唯一入口是 `main_v2.2.py`。`main.py`、`main_optimized.py`、`main_v2.1.py` 已经删除，不要再重命名或调用它们。

旧命令只需要换入口名，并补上现在强制的范围：

```bash
python main_v2.2.py --authorized --target-org your-org
python main_v2.2.py --authorized --target-repo owner/name
```

写数据库需要 `DB_ENCRYPTION_KEY`。只有明确接受明文落盘时才加 `--allow-plaintext-db`。

Gist、Pastebin、GitLab、Searchcode、Events 默认关闭，要加 `--allow-public-sources`。这些来源不受 `org:` / `repo:` 限制，使用前先看 [AUTHORIZED_USE.md](../AUTHORIZED_USE.md)。

旧文档里的 3–5 倍、100–430 倍不是端到端测量，不能用来比较版本。
