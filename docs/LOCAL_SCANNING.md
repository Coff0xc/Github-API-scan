# 本地资产扫描与威胁报告

授权渗透 / 自有资产审计的核心工作流：**扫本地仓库（含全量 git 历史）→ 验证 → 出威胁报告**。

## 为什么扫本地 + 历史

- GitHub Code Search 只能看到**当前分支的最新文件**；而大量泄露藏在**历史提交**里
  （密钥用完即删，但 `.git` 对象里永远都在）。
- 社区标配 gitleaks / TruffleHog 均以"全量历史扫描"为核心能力，本工具对齐了这一点。
- 内网/私有仓库无法通过 GitHub 搜索触达，本地扫描是唯一路径。

## 命令速查

```bash
# 1. 扫描本地仓库（当前文件 + 全量 git 历史），命中后自动走 API 验证
python main_v2.2.py --authorized --scan-local D:\customer-repo

# 2. 只扫当前文件，不扫历史
python main_v2.2.py --authorized --scan-local D:\customer-repo --no-git-history

# 3. 扫描 + 直接产出威胁报告
python main_v2.2.py --authorized --scan-local D:\customer-repo --report threat.md

# 4. 基于已有结果库单独出报告（默认脱敏；--reveal-report 输出完整 Key）
python main_v2.2.py --authorized --report threat.md
python main_v2.2.py --authorized --report threat.md --reveal-report

# 5. 远程 GitHub 搜索限定到授权范围（org / repo），所有 93 条查询自动追加 org:/repo:
python main_v2.2.py --authorized --target-org customer-org
python main_v2.2.py --authorized --target-repo customer-org/api-server
```

## 工作机制

```
本地目录 ──┬── 当前文件遍历（复用 scanner 的扩展名/路径黑名单/大小限制）
           └── git log --all -p 流式解析（每个历史提交的每个 diff 块）
                    ↓ 统一提取管线：BPE 解码 → 正则 → 熵/测试词过滤
                    ↓ base_url 上下文提取（OPENAI_BASE_URL 等变量赋值）
                    ↓ ScanResult → 验证队列 → API 验证 → SQLite
                    ↓ --report → 威胁报告（存活凭据 = 威胁点，逐项处置建议）
```

- 历史扫描覆盖**已删除文件**：密钥在历史提交里出现过的都会被找到
- 结果与远程扫描共用同一套验证器、数据库、通知和报告链路
- `source_url` 形如 `local://git@a1b2c3d4e5:config/settings.py`，可直接定位到提交

## 威胁报告内容

1. **总览**：候选总数、存活凭据数（威胁点数）、各平台分布
2. **威胁点清单**：每个存活凭据的平台/Key/模型档位/余额/RPM/泄露位置/发现时间，高价值排序
3. **处置建议**：轮换密钥 → git filter-repo 清历史 → 查账单 → 部署 gitleaks/Push Protection

报告默认脱敏；`--reveal-report` 的完整版属敏感交付物，注意分发范围与客户授权条款。

## 渗透项目工作流建议

```bash
# 1) 界定范围并声明授权
set SCANNER_AUTHORIZED=1

# 2) 客户本地资产（历史含已删除的密钥）
python main_v2.2.py --scan-local D:\customer\monorepo --report P1_local_threats.md

# 3) 客户 GitHub 组织（限定 scope 的远程搜索）
python main_v2.2.py --target-org customer-org --report P2_org_threats.md

# 4) 汇总交付
#    --report 文件即为渗透测试报告附件；DB 保留原始证据（建议开启 DB_ENCRYPTION_KEY）
```
