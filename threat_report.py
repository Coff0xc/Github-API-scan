"""
威胁报告生成器
==============

把验证结果整理成渗透测试交付物（Markdown）：
- 总览统计（按状态/平台）
- 威胁点清单：**存活凭据**（valid）与有效但配额耗尽（quota_exceeded）
- 每个威胁点附处置建议（轮换密钥）

默认脱敏输出，--reveal-report 时才输出完整 Key（报告本身属敏感交付物，
注意分发范围）。

用法：
    python main_v2.2.py --authorized --report threat_report.md
    python main_v2.2.py --authorized --report threat_report.md --reveal-report
"""

import os
from datetime import datetime

from database import Database
from key_vault import vault


def _mask(key: str) -> str:
    plain = vault.decrypt(key) if key else ""
    if not plain:
        return ""
    if len(plain) <= 10:
        return plain[:3] + "***"
    return f"{plain[:6]}...{plain[-4:]}"


def _cell(value: str) -> str:
    """markdown 表格单元格转义"""
    return (value or "").replace("|", "\\|").replace("\n", " ")


def generate_report(db_path: str, out_path: str, reveal: bool = False) -> str:
    """
    生成威胁报告。

    Args:
        db_path: 结果数据库路径
        out_path: markdown 输出路径
        reveal: True 输出完整 Key（默认脱敏）

    Returns:
        摘要文本（打印用）
    """
    db = Database(db_path)
    stats = db.get_stats()
    live_keys = db.get_valid_keys()  # valid + quota_exceeded，技术上都是活凭据

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    total = stats.get("total", 0)
    valid_count = len([k for k in live_keys if k.status == "valid"])
    quota_count = len([k for k in live_keys if k.status == "quota_exceeded"])

    lines = []
    lines.append("# 泄露凭据威胁报告")
    lines.append("")
    lines.append(f"> 生成时间: {now}  ")
    lines.append("> 数据来源: `{}`（仅包含授权范围内扫描所得数据）".format(db_path))
    lines.append("> Key 展示: **{}**".format("完整明文" if reveal else "脱敏"))
    lines.append("")
    lines.append("## 1. 总览")
    lines.append("")
    lines.append("| 指标 | 数量 |")
    lines.append("|---|---|")
    lines.append(f"| 入库候选总数 | {total} |")
    lines.append(f"| **存活凭据 (valid)** | **{valid_count}** |")
    lines.append(f"| 有效但配额耗尽 (quota_exceeded) | {quota_count} |")
    for status, count in sorted(stats.get("statuses", {}).items()):
        if status not in ("valid", "quota_exceeded"):
            lines.append(f"| {status} | {count} |")
    lines.append("")

    # 平台分布
    platforms = stats.get("platforms", {})
    if platforms:
        lines.append("### 平台分布")
        lines.append("")
        lines.append("| 平台 | 候选数 |")
        lines.append("|---|---|")
        for platform, count in sorted(platforms.items(), key=lambda x: -x[1]):
            lines.append(f"| {_cell(platform)} | {count} |")
        lines.append("")

    # 威胁点明细
    lines.append("## 2. 威胁点（存活凭据清单）")
    lines.append("")
    if not live_keys:
        lines.append("无存活凭据。所有入库候选均已失效或无法验证。")
    else:
        # 高价值优先，余额次之
        live_keys.sort(key=lambda k: (not k.is_high_value, -k.balance_usd))

        lines.append("| # | 平台 | Key | 模型档位 | 余额 | RPM | 高价值 | 泄露位置 | 发现时间 |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for i, k in enumerate(live_keys, 1):
            key_display = k.api_key if reveal else _mask(k.api_key)
            balance = f"${k.balance_usd:.2f}" if k.balance_usd else (_cell(k.balance) or "-")
            found = k.found_time.strftime("%Y-%m-%d %H:%M") if k.found_time else "-"
            lines.append(
                f"| {i} | {_cell(k.platform)} | `{_cell(key_display)}` "
                f"| {_cell(k.model_tier) or '-'} | {balance} "
                f"| {k.rpm or '-'} | {'⭐' if k.is_high_value else '-'} "
                f"| {_cell(k.source_url) or '-'} | {found} |"
            )
        lines.append("")

        lines.append("## 3. 处置建议（按威胁点逐项执行）")
        lines.append("")
        lines.append("1. **立即轮换**下表凭据——`valid` 状态意味着当前仍可调用，属于")
        lines.append("   最高优先级威胁点；即使 `quota_exceeded`，凭据本体仍然有效。")
        lines.append("2. 在 **git 历史**中清除泄露来源（`git filter-repo`），仅删除最新")
        lines.append("   提交不够——历史提交仍持有旧密钥。")
        lines.append("3. 排查凭据的**滥用痕迹**（服务商控制台的调用日志/账单）。")
        lines.append("4. 部署 pre-commit 钩子（gitleaks）与 CI 全量历史扫描（TruffleHog），")
        lines.append("   并优先启用平台侧 Push Protection。")
        lines.append("")
        lines.append("| # | 平台 | Key | 处置动作 |")
        lines.append("|---|---|---|---|")
        for i, k in enumerate(live_keys, 1):
            key_display = k.api_key if reveal else _mask(k.api_key)
            lines.append(f"| {i} | {_cell(k.platform)} | `{_cell(key_display)}` | 轮换 + 清历史 + 查账单 |")

    lines.append("")
    lines.append("---")
    lines.append("*本报告基于授权范围内的扫描结果生成；凭据信息属敏感数据，请控制分发范围。*")

    report = "\n".join(lines)
    out_path = os.path.abspath(out_path)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)

    return (f"威胁报告已生成: {out_path}\n"
            f"  存活凭据: {valid_count} | 配额耗尽: {quota_count} | 候选总数: {total}"
            f" | Key 展示: {'明文' if reveal else '脱敏'}")
