"""
使用边界确认模块
================

本工具的设计用途严格限定为：

1. 扫描**自己拥有**的仓库 / 组织资产，检查是否存在意外泄露的凭据；
2. 在**获得资产所有方明确书面授权**的前提下执行安全评估
   （如受雇的渗透测试、红队演练、审计任务）。

不在此范围内的使用（包括但不限于：批量扫描他人仓库收集凭据、
验证非授权资产上的 Key、使用或转售发现的凭据）违反本工具的
使用条款，且可能触犯《刑法》第285/286条（非法获取计算机信息
系统数据罪 / 破坏计算机信息系统罪）、《网络安全法》《数据安
全法》，以及 GitHub/AWS/云厂商的服务条款。

详见根目录 AUTHORIZED_USE.md。

确认方式（三选一）：
- 运行时交互输入 y 确认
- 命令行追加 --authorized
- 环境变量 SCANNER_AUTHORIZED=1（适合 CI / Docker）
"""

import os
import sys

BOUNDARY_BANNER = """
╔══════════════════════════════════════════════════════════════════╗
║                      使用边界声明 (Use Boundary)                    ║
╠══════════════════════════════════════════════════════════════════╣
║  本工具仅限以下场景使用：                                          ║
║   ✓ 扫描你自己拥有或有管理权限的仓库 / 代码资产                     ║
║   ✓ 获得资产所有方明确书面授权的安全评估                            ║
║                                                                  ║
║  禁止：                                                           ║
║   ✗ 批量扫描他人仓库以收集凭据                                     ║
║   ✗ 验证、使用、传播非你授权资产上发现的 Key                        ║
║   ✗ 绕过平台速率限制或反滥用机制                                    ║
║                                                                  ║
║  发现泄露凭据的正确处置：                                          ║
║   1. 通知资产所有方轮换密钥    2. 不使用、不传播                    ║
║   3. 必要时通过平台官方渠道报告（如 GitHub Secret Scanning）        ║
║                                                                  ║
║  完整条款见 AUTHORIZED_USE.md。继续运行即表示你已阅读并同意。        ║
╚══════════════════════════════════════════════════════════════════╝
"""


def is_pre_confirmed() -> bool:
    """环境变量是否已确认授权"""
    return os.getenv("SCANNER_AUTHORIZED", "").strip().lower() in ("1", "true", "yes")


def check_authorization(cli_flag: bool = False, non_interactive: bool = False) -> bool:
    """
    使用边界确认。返回 True 表示可以继续。

    Args:
        cli_flag: 命令行是否传入 --authorized
        non_interactive: 非交互模式（CI/容器）下不阻塞，仅提示
    """
    if cli_flag or is_pre_confirmed():
        return True

    print(BOUNDARY_BANNER)

    if non_interactive or not sys.stdin.isatty():
        print("[ABORT] 未确认使用边界。以 --authorized 参数或 SCANNER_AUTHORIZED=1 "
              "环境变量声明你仅在授权范围内使用本工具。")
        return False

    try:
        answer = input("我确认仅在上述授权范围内使用本工具，是否继续? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False

    if answer in ("y", "yes"):
        print("[OK] 使用边界已确认，开始运行。\n")
        return True

    print("[ABORT] 已取消。")
    return False


def require_remote_scope(target_org: str = "", target_repo: str = "") -> bool:
    """
    远程 GitHub 搜索必须落到授权资产上。

    未提供 --target-org / --target-repo 时返回 False。仓库限定符必须是 owner/name。
    """
    org = (target_org or "").strip()
    repo = (target_repo or "").strip()
    if repo:
        if "/" not in repo or repo.startswith("/") or repo.endswith("/"):
            print("[ABORT] --target-repo 必须是 owner/name，例如 acme/api-server。")
            return False
        return True
    if org:
        if "/" in org or " " in org:
            print("[ABORT] --target-org 只能是组织名，不能包含空格或斜杠。")
            return False
        return True
    print("[ABORT] 远程扫描必须用 --target-org 或 --target-repo 限定到你拥有或获得授权的资产。")
    print("        只审计本机目录时用 --scan-local。统计、导出、出报告不需要该参数。")
    return False


def public_sources_allowed(explicit: bool) -> bool:
    """
    Gist / Pastebin / GitLab / Searchcode / Events 无法用 org: 或 repo: 限定。

    默认拒绝。授权范围确实包含这些公开源时，调用方传入 explicit=True。
    """
    if explicit:
        print("[WARN] 已打开无法按组织或仓库限定的公开源。"
              "只扫描书面授权范围内的内容。")
        return True
    print("[ABORT] Gist、Pastebin、GitLab、Searchcode、GitHub Events 不能限定到单个组织或仓库。")
    print("        授权范围确实包含这些来源时，追加 --allow-public-sources。")
    return False


def storage_encryption_ready(allow_plaintext: bool) -> bool:
    """扫描写库前要求 DB_ENCRYPTION_KEY，除非调用方显式允许明文。"""
    if os.getenv("DB_ENCRYPTION_KEY", "").strip():
        return True
    if allow_plaintext:
        print("[WARN] 已使用 --allow-plaintext-db，凭据将以明文写入数据库。")
        return True
    print("[ABORT] 未设置 DB_ENCRYPTION_KEY。扫描写入凭据前请设置该环境变量，")
    print("        或在你接受明文落盘时显式传入 --allow-plaintext-db。")
    return False
