# 快速开始 - GitHub Secret Scanner Pro 优化版

5 分钟快速上手优化版扫描器。

---

## 🚀 快速安装

### 1. 克隆项目

```bash
git clone https://github.com/Coff0xc/Github-API-scan.git
cd Github-API-scan
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

**新增依赖说明:**
- `aiosqlite>=0.19.0` - 异步数据库
- `cryptography>=41.0.0` - 加密导出
- `PyYAML>=6.0.0` - 配置文件解析
- `uvloop>=0.19.0` - 性能提升 (仅 Linux/Mac)

### 3. 配置 GitHub Token

**方式 1: 环境变量 (推荐)**

```bash
export GITHUB_TOKENS="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx,ghp_yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"
```

**方式 2: 配置文件**

创建 `config_local.py`:

```python
GITHUB_TOKENS = [
    "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "ghp_yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy",
]
```

---

## 🎯 基础使用

### 启动扫描

唯一入口是 `main_v2.2.py`。

远程扫描必须同时满足：

- `--target-org` 或 `--target-repo`
- `DB_ENCRYPTION_KEY`，或者你明确接受明文落盘时加 `--allow-plaintext-db`
- `--authorized`，或交互输入 `y`，或环境变量 `SCANNER_AUTHORIZED=1`

```bash
python main_v2.2.py --authorized --target-org your-org
```

### 查看统计

```bash
python main_optimized.py --stats
```

输出示例:
```
=== 数据库统计 ===
总 Key 数量: 1234
有效 Key: 56
无效 Key: 1178
待验证: 0
```

### 导出数据

```bash
# 导出所有有效 Key
python main_optimized.py --export valid_keys.txt --status valid

# 导出为 CSV
python main_optimized.py --export-csv keys.csv --status valid
```

---

## 🔐 加密导出 (新功能)

### 加密导出

```bash
python main_optimized.py --export-encrypted keys_encrypted.bin
```

生成两个文件:
- `keys_encrypted.bin` - 加密数据
- `keys_encrypted.bin.key` - 解密密钥

### 解密查看

```bash
python main_optimized.py --decrypt keys_encrypted.bin --key-file keys_encrypted.bin.key
```

---

## ⚙️ 配置调整

### 编辑 config.yaml

```yaml
# 调整并发数
validator:
  max_concurrency: 150  # 默认 100

# 调整批量大小
database:
  batch_size: 100  # 默认 50
  flush_interval: 3.0  # 默认 5.0

# 调整扫描参数
scanner:
  entropy_threshold: 3.5  # 默认 3.8
  max_file_size_kb: 1000  # 默认 500
```

---

## 📊 性能对比

运行性能测试:

```bash
python benchmark.py
```

预期结果:
```
=== 性能对比测试 ===

原版 (main.py):
- 数据库写入: 100 keys/s
- 队列容量: 1000

优化版 (main_optimized.py):
- 数据库写入: 400 keys/s (4x)
- 队列容量: 10000 (10x)

✅ 优化版性能提升显著!
```

---

## 🔍 常用命令

### 扫描相关

```bash
# 基础扫描（必须带授权范围）
python main_v2.2.py --authorized --target-org your-org

# 公开源不能按组织限定，默认关闭
python main_v2.2.py --authorized --target-org your-org --pastebin --gist --allow-public-sources
```

### 数据管理

```bash
# 查看统计
python main_optimized.py --stats

# 导出有效 Key
python main_optimized.py --export valid.txt --status valid

# 导出所有 Key
python main_optimized.py --export all.txt

# 加密导出
python main_optimized.py --export-encrypted secure.bin
```

### 数据库操作

```bash
# 备份数据库
cp leaked_keys.db leaked_keys.db.backup

# 查看数据库大小
ls -lh leaked_keys.db

# 清理数据库 (谨慎!)
rm leaked_keys.db
```

---

## ⚠️ 常见问题

### Q1: 提示 "未配置 GitHub Tokens"

**A:** 需要配置至少一个 GitHub Token:

```bash
export GITHUB_TOKENS="ghp_your_token_here"
```

或创建 `config_local.py` 文件。

### Q2: 提示 "ModuleNotFoundError: No module named 'aiosqlite'"

**A:** 安装缺失依赖:

```bash
pip install aiosqlite cryptography pyyaml
```

### Q3: 性能提升不明显

**A:** 检查配置:

```yaml
# config.yaml
validator:
  max_concurrency: 150  # 提升并发
database:
  batch_size: 100  # 增大批量
```

### Q4: 数据库锁定错误

**A:** 确保没有其他进程在使用数据库:

```bash
# 检查进程
ps aux | grep main

# 停止其他实例
pkill -f main_optimized.py
```

### Q5: Windows 上 uvloop 安装失败

**A:** uvloop 仅支持 Linux/Mac，Windows 会自动跳过:

```bash
# Windows 用户可以忽略此依赖
pip install -r requirements.txt  # 会自动跳过 uvloop
```

---

## 🎓 进阶使用

### 1. 代理配置

编辑 `config_local.py`:

```python
PROXY_URL = "http://127.0.0.1:7890"
```

### 2. 自定义搜索关键词

编辑 `config.py`:

```python
SEARCH_KEYWORDS = [
    "openai api key",
    "anthropic api key",
    "your custom keyword",
]
```

### 3. 调整熵值阈值

编辑 `config.yaml`:

```yaml
scanner:
  entropy_threshold: 3.5  # 降低阈值发现更多 Key
```

### 4. 启用性能监控

编辑 `config.yaml`:

```yaml
monitoring:
  enable_prometheus: true
  prometheus_port: 8000
```

---

## 📈 性能优化建议

### 高性能配置

适用于高性能服务器:

```yaml
validator:
  max_concurrency: 200
  num_workers: 4

database:
  batch_size: 100
  flush_interval: 2.0

scanner:
  async_download_concurrency: 100
```

### 低资源配置

适用于个人电脑:

```yaml
validator:
  max_concurrency: 50
  num_workers: 1

database:
  batch_size: 20
  flush_interval: 10.0

scanner:
  async_download_concurrency: 30
```

---

## 🔄 从原版迁移

### 1. 备份数据

```bash
cp leaked_keys.db leaked_keys.db.backup
```

### 2. 测试优化版

```bash
python main_optimized.py --stats
```

### 3. 正式切换

```bash
mv main.py main_old.py
mv main_optimized.py main.py
```

### 4. 验证功能

```bash
# 运行 1 分钟测试
timeout 60 python main.py

# 检查统计
python main.py --stats
```

详细迁移指南请查看 `MIGRATION.md`。

---

## 📚 相关文档

- `OPTIMIZATION.md` - 优化详细说明
- `MIGRATION.md` - 迁移指南
- `README.md` - 项目说明
- `config.yaml` - 配置文件

---

## 🆘 获取帮助

### 查看帮助

```bash
python main_optimized.py --help
```

### 检查日志

```bash
# 查看最近日志
tail -f scanner.log

# 搜索错误
grep ERROR scanner.log
```

### 报告问题

遇到问题请在 GitHub Issues 报告,包含:
1. 错误信息
2. 运行环境 (Python 版本, OS)
3. 配置文件内容
4. 日志片段

---

## ✅ 快速检查清单

启动前检查:

- [ ] 已安装所有依赖
- [ ] 已配置 GitHub Token
- [ ] 数据库文件可写
- [ ] 网络连接正常
- [ ] (可选) 已配置代理

---

**快速开始完成!**

现在你可以开始使用优化版扫描器了。

如需更多帮助,请查看 `OPTIMIZATION.md` 和 `MIGRATION.md`。
