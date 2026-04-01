#!/usr/bin/env python3
"""
扩展验证器测试脚本
==================

测试 30+ 平台的 API Key 验证功能

使用方法:
    # 列出支持的平台
    python test_validator_extended.py --list

    # 测试单个平台
    python test_validator_extended.py --platform slack --token "xoxb-xxx"

    # 测试正则匹配
    python test_validator_extended.py --regex-test

    # 交互式测试
    python test_validator_extended.py --interactive
"""

import asyncio
import argparse
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.syntax import Syntax

from validator_extended import (
    ExtendedValidator,
    ExtendedKeyStatus,
    ExtendedValidationResult,
    EXTENDED_PLATFORMS,
    get_supported_platforms,
    get_platform_requirements,
    validate_extended,
)

from regex_extended import (
    EXTENDED_REGEX_PATTERNS,
    HIGH_PRIORITY_PATTERNS,
    CONTEXT_REQUIRED_PATTERNS,
    find_all_keys,
    identify_platform,
    get_high_priority_patterns,
    get_extended_search_keywords,
)

console = Console()


# ============================================================================
#                              测试用例
# ============================================================================

# 正则测试用例
REGEX_TEST_CASES = [
    # (测试名称, 测试文本, 期望匹配的平台列表)
    # 注意: 以下为正则测试用例，所有 Key 均为虚构格式，仅用于测试正则匹配
    (
        "Slack Bot Token",
        'SLACK_TOKEN="xoxb-xxxx-xxxx-xxxx"',  # 格式示例，非真实 token
        ["slack_token"]
    ),
    (
        "Discord Webhook",
        'https://discord.com/api/webhooks/1234567890123456789/AbCdEfGhIjKlMnOpQrStUvWxYz1234567890AbCdEfGhIjKl',
        ["discord_webhook"]
    ),
    (
        "Telegram Bot",
        'TELEGRAM_TOKEN="1234567890:ABCdefGHIjklMNOpqrsTUVwxyz123456789"',
        ["telegram_bot"]
    ),
    (
        "SendGrid API Key",
        'SENDGRID_API_KEY="SG.abcdefghijklmnopqrstuv.wxyz1234567890ABCDEFGHIJ"',
        ["sendgrid"]
    ),
    (
        "DigitalOcean Token",
        'DO_TOKEN="dop_v1_abcdef1234567890abcdef1234567890abcdef1234567890abcdef12345678"',
        ["digitalocean"]
    ),
    (
        "GitLab PAT",
        'GITLAB_TOKEN="glpat-FAKEFAKEFAKEFAKEFAKE"',
        ["gitlab_pat"]
    ),
    (
        "NPM Token",
        'NPM_TOKEN="npm_1234567890abcdefghijklmnopqrstuvwx"',
        ["npm_token"]
    ),
    (
        "Sentry Auth Token",
        'SENTRY_AUTH_TOKEN="sntrys_1234567890abcdefghijklmnopqrstuvwxyz1234567890abcdefghij"',
        ["sentry"]
    ),
    (
        "Notion Integration",
        'NOTION_TOKEN="secret_1234567890abcdefghijklmnopqrstuvwxyzABCDEF"',
        ["notion"]
    ),
    (
        "Linear API Key",
        'LINEAR_API_KEY="lin_api_xxxx"',  # 格式示例
        ["linear"]
    ),
    (
        "Stripe Secret Key",
        'STRIPE_SECRET_KEY="sk_live_xxxx"',  # 格式示例
        ["stripe_secret"]
    ),
    (
        "Mapbox Token",
        'MAPBOX_TOKEN="pk.eyJ1IjoiYWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXoxMjM0NTY3ODkwIiwiYSI6ImFiY2RlZmdoaWprbG1ub3BxcnMifQ.1234567890ABCDEFGHIJ"',
        ["mapbox"]
    ),
    (
        "AWS Access Key",
        'AWS_ACCESS_KEY_ID="AKIAIOSFODNN7EXAMPLE"',
        ["aws_access"]
    ),
    (
        "Private Key",
        '-----BEGIN RSA PRIVATE KEY-----',
        ["private_key_pem"]
    ),
    (
        "MongoDB Connection",
        'MONGODB_URI="mongodb+srv://user:pass@cluster.mongodb.net/db"',
        ["mongodb"]
    ),
]


# ============================================================================
#                              命令函数
# ============================================================================

def list_platforms():
    """列出所有支持的平台"""
    console.print("\n[bold cyan]═══ 支持的平台列表 ═══[/bold cyan]\n")

    # 按类别分组
    categories = {
        "通信/消息": ["slack", "discord", "telegram", "twilio", "sendgrid", "mailgun", "mailchimp"],
        "云服务商": ["digitalocean", "heroku", "cloudflare", "vercel"],
        "开发工具": ["gitlab", "bitbucket", "circleci", "travis_ci", "npm", "docker_hub"],
        "监控/APM": ["datadog", "sentry", "newrelic", "pagerduty"],
        "协作工具": ["notion", "linear", "asana", "airtable", "atlassian"],
        "分析平台": ["segment", "mixpanel", "amplitude", "algolia"],
        "客服/CRM": ["zendesk", "intercom", "freshdesk"],
        "地图服务": ["mapbox", "google_maps"],
        "支付平台": ["paypal", "square"],
    }

    for category, platforms in categories.items():
        console.print(f"\n[bold yellow]{category}[/bold yellow]")
        table = Table(show_header=True, header_style="cyan")
        table.add_column("平台", width=15)
        table.add_column("必需参数", width=40)
        table.add_column("描述", width=30)

        for platform in platforms:
            if platform in EXTENDED_PLATFORMS:
                info = EXTENDED_PLATFORMS[platform]
                required = ", ".join(info.get("required", []))
                desc = info.get("description", "")
                table.add_row(platform, required, desc)

        console.print(table)

    console.print(f"\n[dim]共 {len(EXTENDED_PLATFORMS)} 个平台[/dim]")


def list_regex_patterns():
    """列出所有正则模式"""
    console.print("\n[bold cyan]═══ 正则表达式模式 ═══[/bold cyan]\n")

    # 高优先级模式
    console.print("[bold yellow]高优先级模式 (无需上下文)[/bold yellow]")
    table = Table(show_header=True, header_style="cyan")
    table.add_column("模式名", width=25)
    table.add_column("正则表达式", width=60)

    for name in HIGH_PRIORITY_PATTERNS[:10]:  # 显示前 10 个
        if name in EXTENDED_REGEX_PATTERNS:
            pattern = EXTENDED_REGEX_PATTERNS[name]
            # 截断过长的正则
            if len(pattern) > 55:
                pattern = pattern[:52] + "..."
            table.add_row(name, pattern)

    console.print(table)
    console.print(f"[dim]... 共 {len(HIGH_PRIORITY_PATTERNS)} 个高优先级模式[/dim]")

    # 上下文相关模式
    console.print("\n[bold yellow]上下文相关模式[/bold yellow]")
    table = Table(show_header=True, header_style="cyan")
    table.add_column("模式名", width=25)
    table.add_column("正则表达式", width=60)

    for name in CONTEXT_REQUIRED_PATTERNS[:10]:  # 显示前 10 个
        if name in EXTENDED_REGEX_PATTERNS:
            pattern = EXTENDED_REGEX_PATTERNS[name]
            if len(pattern) > 55:
                pattern = pattern[:52] + "..."
            table.add_row(name, pattern)

    console.print(table)
    console.print(f"[dim]... 共 {len(CONTEXT_REQUIRED_PATTERNS)} 个上下文相关模式[/dim]")

    console.print(f"\n[bold]总计: {len(EXTENDED_REGEX_PATTERNS)} 个正则模式[/bold]")


def run_regex_tests():
    """运行正则测试"""
    console.print("\n[bold cyan]═══ 正则表达式测试 ═══[/bold cyan]\n")

    table = Table(show_header=True, header_style="cyan")
    table.add_column("测试用例", width=20)
    table.add_column("期望匹配", width=20)
    table.add_column("实际匹配", width=20)
    table.add_column("结果", width=10)

    passed = 0
    failed = 0

    for name, text, expected in REGEX_TEST_CASES:
        # 查找匹配
        matches = find_all_keys(text)
        matched_patterns = [m[0] for m in matches]

        # 检查是否匹配到期望的模式
        found_expected = all(exp in matched_patterns for exp in expected)

        if found_expected:
            passed += 1
            status = "[green]✓ 通过[/green]"
        else:
            failed += 1
            status = "[red]✗ 失败[/red]"

        table.add_row(
            name,
            ", ".join(expected),
            ", ".join(matched_patterns[:2]) or "-",
            status
        )

    console.print(table)
    console.print(f"\n[bold]结果: {passed}/{len(REGEX_TEST_CASES)} 通过[/bold]")


async def test_platform(platform: str, credentials: dict):
    """测试单个平台"""
    console.print(f"\n[bold cyan]═══ 测试 {platform} ═══[/bold cyan]\n")

    # 检查平台是否支持
    if platform.lower() not in EXTENDED_PLATFORMS:
        console.print(f"[red]错误: 不支持的平台 '{platform}'[/red]")
        console.print("使用 --list 查看支持的平台")
        return

    # 检查必需参数
    platform_info = EXTENDED_PLATFORMS[platform.lower()]
    required = platform_info.get("required", [])
    missing = [r for r in required if r not in credentials or not credentials[r]]

    if missing:
        console.print(f"[red]错误: 缺少必需参数: {', '.join(missing)}[/red]")
        console.print(f"必需参数: {', '.join(required)}")
        return

    # 执行验证
    console.print(f"验证中...")
    result = await validate_extended(platform, credentials)

    # 显示结果
    if result.status == ExtendedKeyStatus.VALID:
        console.print(f"\n[green]✓ 验证成功![/green]")
        console.print(f"  状态: [green]{result.status.value}[/green]")
    elif result.status == ExtendedKeyStatus.INVALID:
        console.print(f"\n[red]✗ 验证失败[/red]")
        console.print(f"  状态: [red]{result.status.value}[/red]")
    else:
        console.print(f"\n[yellow]⚠ 验证结果[/yellow]")
        console.print(f"  状态: [yellow]{result.status.value}[/yellow]")

    console.print(f"  消息: {result.message}")

    if result.extra_info:
        console.print(f"  详情: {result.extra_info}")

    if result.is_high_value:
        console.print(f"  [bold red]⚠ 高价值 Key![/bold red]")


async def interactive_test():
    """交互式测试"""
    console.print(Panel.fit(
        "[bold cyan]扩展验证器交互式测试[/bold cyan]\n\n"
        "选择平台并输入凭证进行验证",
        title="交互模式"
    ))

    while True:
        console.print("\n" + "=" * 50)

        # 选择平台
        platform = Prompt.ask(
            "平台名称 (输入 'list' 查看列表, 'quit' 退出)"
        ).strip().lower()

        if platform == "quit" or platform == "q":
            break

        if platform == "list":
            # 简洁列表
            platforms = list(EXTENDED_PLATFORMS.keys())
            for i in range(0, len(platforms), 5):
                console.print("  " + ", ".join(platforms[i:i+5]))
            continue

        if platform not in EXTENDED_PLATFORMS:
            console.print(f"[red]不支持的平台: {platform}[/red]")
            continue

        # 获取平台要求
        platform_info = EXTENDED_PLATFORMS[platform]
        required = platform_info.get("required", [])
        optional = platform_info.get("optional", [])

        console.print(f"\n[cyan]{platform_info.get('description', '')}[/cyan]")
        console.print(f"必需: {', '.join(required)}")
        if optional:
            console.print(f"可选: {', '.join(optional)}")

        # 收集凭证
        credentials = {}

        for param in required:
            value = Prompt.ask(f"  {param}")
            if not value:
                console.print("[red]必需参数不能为空[/red]")
                break
            credentials[param] = value
        else:
            # 可选参数
            for param in optional:
                value = Prompt.ask(f"  {param} (可选)", default="")
                if value:
                    credentials[param] = value

            # 执行验证
            await test_platform(platform, credentials)


async def main():
    parser = argparse.ArgumentParser(description="扩展验证器测试工具")
    parser.add_argument("--list", "-l", action="store_true", help="列出支持的平台")
    parser.add_argument("--list-regex", action="store_true", help="列出正则模式")
    parser.add_argument("--regex-test", action="store_true", help="运行正则测试")
    parser.add_argument("--platform", "-p", type=str, help="要测试的平台")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互式测试")

    # 凭证参数
    parser.add_argument("--token", type=str, help="Token/API Key")
    parser.add_argument("--api-key", type=str, help="API Key")
    parser.add_argument("--username", type=str, help="用户名")
    parser.add_argument("--password", type=str, help="密码")
    parser.add_argument("--email", type=str, help="邮箱")
    parser.add_argument("--subdomain", type=str, help="子域名")
    parser.add_argument("--domain", type=str, help="域名")

    args = parser.parse_args()

    if args.list:
        list_platforms()
        return

    if args.list_regex:
        list_regex_patterns()
        return

    if args.regex_test:
        run_regex_tests()
        return

    if args.interactive:
        await interactive_test()
        return

    if args.platform:
        # 构建凭证
        credentials = {}
        if args.token:
            credentials["token"] = args.token
        if args.api_key:
            credentials["api_key"] = args.api_key
        if args.username:
            credentials["username"] = args.username
        if args.password:
            credentials["password"] = args.password
        if args.email:
            credentials["email"] = args.email
        if args.subdomain:
            credentials["subdomain"] = args.subdomain
        if args.domain:
            credentials["domain"] = args.domain

        await test_platform(args.platform, credentials)
        return

    # 默认显示帮助
    parser.print_help()
    console.print("\n[dim]示例:[/dim]")
    console.print("  python test_validator_extended.py --list")
    console.print("  python test_validator_extended.py --regex-test")
    console.print("  python test_validator_extended.py --interactive")
    console.print("  python test_validator_extended.py -p slack --token xoxb-xxx")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]测试已取消[/yellow]")
