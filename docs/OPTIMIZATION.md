# 关于旧的性能数字

这里以前写过「3–5 倍」「100–430 倍」和一张 0.24 秒的对比表。那些数字不能复现为一次完整扫描，已经从仓库里撤掉。

`benchmark.py` 只计时合成行的 SQLite 插入。它不搜索 GitHub，也不请求模型厂商。

入口、范围和导出行为以 [README](../README.md) 和 [QUICKSTART.md](QUICKSTART.md) 为准。
