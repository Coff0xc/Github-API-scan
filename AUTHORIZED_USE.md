# 使用边界声明（AUTHORIZED USE）

> **本工具只能用于你拥有或获得授权的资产。** 运行任何扫描入口时，程序会要求你
> 显式确认本声明（`--authorized` 参数或 `SCANNER_AUTHORIZED=1` 环境变量，或交互
> 输入 `y`）。

## 1. 允许的使用场景

| 场景 | 说明 |
|---|---|
| 自有资产审计 | 扫描**你自己拥有/管理**的仓库、组织、代码资产，发现意外提交的凭据 |
| 授权安全评估 | 受资产所有方**明确书面授权**的渗透测试、红队演练、安全审计 |
| 泄露应急响应 | 你的凭据泄露后，评估影响范围（需同时具备对相关资产的处置权） |
| 安全研究与教学 | 在**自建测试环境**中研究泄露检测技术、验证检测规则 |

**Scope 绑定**：授权评估时请使用 `--target-org` / `--target-repo` 把远程搜索
限定在客户资产内、`--scan-local` 限定在授权目录内——扫描范围与授权范围一一
对应，这也是渗透测试报告中 scope 声明的证据。

## 2. 明确禁止的使用场景

- ❌ 批量扫描他人仓库、Gist、Pastebin、FOFA 等来源**收集**凭据
- ❌ 对非授权资产上发现的 Key 进行**验证**（哪怕只是"测试是否有效"）
- ❌ 使用、转售、传播扫描发现的任何凭据
- ❌ 规避 GitHub / 云厂商的速率限制、反滥用机制
- ❌ 扫描后不处置——发现泄露凭据却不通知所有方

## 3. 发现泄露凭据的正确处置流程

1. **通知所有方**：通过仓库 issue / 私密联系方式 / 平台官方渠道告知（不要贴出完整 Key）
2. **不使用、不保存**：验证其"是否有效"本身就是未授权访问，你可能触犯法律
3. **平台报告**：GitHub 用户可用 [Secret Scanning alerts](https://docs.github.com/code-security/secret-scanning/managing-alerts-from-secret-scanning)；
   提供商侧（AWS/OpenAI 等）多已加入 GitHub [合作伙伴计划](https://docs.github.com/code-security/secret-scanning/introduction/supported-secret-scanning-patterns)，泄露会被自动通知并吊销
4. **自查工具**：给你的仓库装 [gitleaks](https://github.com/gitleaks/gitleaks) 或
   [TruffleHog](https://github.com/trufflesecurity/trufflehog) 做持续检测 + pre-commit 钩子

## 4. 法律边界（非法律意见，仅供参考）

- **中国**：《刑法》第 285 条（非法获取计算机信息系统数据罪）、第 286 条（破坏计算
  机信息系统罪）；《网络安全法》《数据安全法》对未授权访问和数据获取均有约束。
  "Key 是公开泄露的"**不构成**合法访问抗辩——使用泄露凭据调用 API 即属未授权访问。
- **GitHub ToS**：自动化批量抓取受 API 条款约束；以收集凭据为目的的搜索可能被
  判定为滥用并封号。
- **其他司法辖区**：美国 CFAA、欧盟 NIS2/GDPR 等对未授权访问同样有刑事/行政责任。

## 5. 本工具内建的边界机制

| 机制 | 位置 | 作用 |
|---|---|---|
| 启动确认 | `use_boundary.py`，唯一实现 `main_v2.2.py` | 未确认边界不启动。其余 main 文件只做转发 |
| 远程范围 | `require_remote_scope` | 没有 `--target-org` 或 `--target-repo` 时不发起 GitHub 搜索 |
| 公开源开关 | `--allow-public-sources` | 不能按组织限定的来源默认关闭 |
| 写库加密 | `storage_encryption_ready` | 扫描写入前要求 `DB_ENCRYPTION_KEY`，或显式 `--allow-plaintext-db` |
| `PROTECTED_DOMAINS` | `config.py` | 官方 API 域名不参与熔断（降低对官方服务的干扰） |
| SSRF 防护 | `validator_optimized.py` `_is_likely_valid_relay` | 阻止向内网/本机地址发起验证请求 |
| 熵过滤 + 黑名单 | `scanner.py` | 测试/示例 Key 与文档路径不入库 |
| 静态加密 | `key_vault.py`（`DB_ENCRYPTION_KEY`） | 结果库不落明文，降低结果库本身成为泄露源的风险 |
| Dashboard 鉴权 | `web_dashboard.py`（`DASHBOARD_TOKEN`） | 结果默认脱敏，导出走加密 |

## 6. 一句话原则

> **扫描的目的是"让你的资产更安全"，不是"让别人的资产变成你的资源"。**
> 如果一个动作你需要隐瞒着做，那它大概率越界了。
