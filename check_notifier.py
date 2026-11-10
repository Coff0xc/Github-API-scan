#!/usr/bin/env python3
"""
通知系统测试脚本
================

用于测试各通知渠道是否配置正确

使用方法:
    # 从环境变量加载配置
    python test_notifier.py

    # 从配置文件加载
    python test_notifier.py --config notify_config.yaml

    # 测试特定渠道
    python test_notifier.py --channel discord
    python test_notifier.py --channel telegram

    # 发送测试报告
    python test_notifier.py --report
"""

import os
import sys
import asyncio
import argparse
from datetime import datetime
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from notifier_v2 import (
    NotifierV2,
    KeyInfo,
    Severity,
    DiscordChannel,
    SlackChannel,
    TelegramChannel,
    FeishuChannel,
    DingtalkChannel,
    ServerChanChannel,
    BarkChannel,
    FileChannel,
    SoundChannel,
    create_notifier_from_env,
    init_notifier,
)

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

console = Console()


def create_test_key(severity_level: str = "high") -> KeyInfo:
    """创建测试 Key 信息"""
    test_keys = {
        "critical": KeyInfo(
            platform="openai",
            api_key="sk-proj-test1234567890abcdefghijklmnopqrstuvwxyz",
            base_url="https://api.openai.com",
            model_tier="GPT-4-Turbo",
            balance="$150.00 remaining",
            rpm=10000,
            source_url="https://github.com/example/repo/blob/main/.env",
            is_high_value=True,
            found_time=datetime.now()
        ),
        "high": KeyInfo(
            platform="anthropic",
            api_key="sk-ant-api03-test1234567890abcdefghijklmnop",
            base_url="https://api.anthropic.com",
            model_tier="Claude-3.5-Sonnet",
            balance="Active",
            rpm=4000,
            source_url="https://github.com/example/repo/blob/main/config.py",
            is_high_value=True,
            found_time=datetime.now()
        ),
        "medium": KeyInfo(
            platform="gemini",
            api_key="AIzaSyTest1234567890abcdefghijklmnopqrs",
            base_url="https://generativelanguage.googleapis.com",
            model_tier="Gemini-1.5-Pro",
            balance="Free tier",
            rpm=60,
            source_url="https://github.com/example/repo/blob/main/app.js",
            is_high_value=False,
            found_time=datetime.now()
        ),
        "low": KeyInfo(
            platform="groq",
            api_key="gsk_test1234567890abcdefghijklmnopqrstuvwx",
            base_url="https://api.groq.com",
            model_tier="Llama-3-8B",
            balance="Quota exceeded",
            rpm=0,
            source_url="https://gist.github.com/user/abc123",
            is_high_value=False,
            found_time=datetime.now()
        )
    }
    return test_keys.get(severity_level, test_keys["high"])


async def test_single_channel(channel_name: str, notifier: NotifierV2) -> bool:
    """测试单个通知渠道"""
    channel_map = {
        "discord": DiscordChannel,
        "slack": SlackChannel,
        "telegram": TelegramChannel,
        "feishu": FeishuChannel,
        "dingtalk": DingtalkChannel,
        "serverchan": ServerChanChannel,
        "bark": BarkChannel,
        "file": FileChannel,
        "sound": SoundChannel,
    }

    if channel_name not in channel_map:
        console.print(f"[red]未知渠道: {channel_name}[/red]")
        console.print(f"可用渠道: {', '.join(channel_map.keys())}")
        return False

    # 查找对应的渠道
    target_channel = None
    for ch in notifier.channels:
        if ch.name.lower() == channel_name.lower():
            target_channel = ch
            break

    if not target_channel:
        console.print(f"[yellow]渠道 {channel_name} 未配置[/yellow]")
        return False

    if not target_channel.enabled:
        console.print(f"[yellow]渠道 {channel_name} 已禁用[/yellow]")
        return False

    console.print(f"\n[cyan]测试 {channel_name} 渠道...[/cyan]")

    test_key = create_test_key("high")
    try:
        result = await target_channel.send(test_key, "")
        if result:
            console.print(f"[green]✓ {channel_name} 测试成功![/green]")
        else:
            console.print(f"[red]✗ {channel_name} 测试失败[/red]")
        return result
    except Exception as e:
        console.print(f"[red]✗ {channel_name} 异常: {e}[/red]")
        return False


async def test_all_channels(notifier: NotifierV2):
    """测试所有已配置的渠道"""
    console.print("\n[bold cyan]═══ 通知系统测试 ═══[/bold cyan]\n")

    # 显示渠道配置状态
    table = Table(title="通知渠道配置状态")
    table.add_column("渠道", style="cyan")
    table.add_column("状态", style="green")
    table.add_column("最低级别", style="yellow")

    for channel in notifier.channels:
        status = "✓ 已启用" if channel.enabled else "✗ 已禁用"
        status_style = "green" if channel.enabled else "red"
        table.add_row(
            channel.name,
            f"[{status_style}]{status}[/{status_style}]",
            channel.min_severity.value if hasattr(channel, 'min_severity') else "low"
        )

    console.print(table)
    console.print()

    # 确认测试
    if not Confirm.ask("是否发送测试通知到所有已启用的渠道?", default=True):
        console.print("[yellow]测试取消[/yellow]")
        return

    # 选择测试级别
    level = Prompt.ask(
        "选择测试级别",
        choices=["critical", "high", "medium", "low"],
        default="high"
    )

    console.print(f"\n[cyan]发送 {level.upper()} 级别测试通知...[/cyan]\n")

    test_key = create_test_key(level)

    # 发送测试通知
    results = await notifier.notify(test_key, force=True)

    # 显示结果
    console.print("\n[bold]测试结果:[/bold]")
    for channel_name, success in results.items():
        if success is True:
            console.print(f"  [green]✓ {channel_name}: 成功[/green]")
        elif success is False:
            console.print(f"  [red]✗ {channel_name}: 失败[/red]")
        else:
            console.print(f"  [yellow]○ {channel_name}: {success}[/yellow]")


async def test_report(notifier: NotifierV2):
    """测试每日报告"""
    console.print("\n[cyan]发送测试报告...[/cyan]")

    # 模拟一些统计数据
    notifier.daily_stats = {
        "total_found": 42,
        "by_severity": {
            "critical": 2,
            "high": 8,
            "medium": 25,
            "low": 7,
        },
        "by_platform": {
            "openai": 15,
            "anthropic": 10,
            "gemini": 8,
            "groq": 5,
            "deepseek": 4,
        },
        "high_value_keys": [
            {"platform": "openai", "key": "sk-proj-****abcd", "model": "GPT-4-Turbo", "time": datetime.now().isoformat()},
            {"platform": "anthropic", "key": "sk-ant-****efgh", "model": "Claude-3-Opus", "time": datetime.now().isoformat()},
        ]
    }

    results = await notifier.send_daily_report()

    console.print("\n[bold]报告发送结果:[/bold]")
    for channel_name, success in results.items():
        status = "[green]✓ 成功[/green]" if success else "[red]✗ 失败[/red]"
        console.print(f"  {channel_name}: {status}")


async def interactive_setup():
    """交互式配置向导"""
    console.print(Panel.fit(
        "[bold cyan]GitHub Secret Scanner Pro - 通知系统配置向导[/bold cyan]\n\n"
        "此向导将帮助你配置通知渠道",
        title="欢迎"
    ))

    notifier = NotifierV2()

    # Discord
    if Confirm.ask("\n是否配置 Discord 通知?", default=False):
        webhook = Prompt.ask("请输入 Discord Webhook URL")
        if webhook:
            notifier.add_channel(DiscordChannel(webhook))
            console.print("[green]✓ Discord 已添加[/green]")

    # Telegram
    if Confirm.ask("\n是否配置 Telegram 通知?", default=False):
        token = Prompt.ask("请输入 Bot Token")
        chat_id = Prompt.ask("请输入 Chat ID")
        if token and chat_id:
            notifier.add_channel(TelegramChannel(token, chat_id))
            console.print("[green]✓ Telegram 已添加[/green]")

    # Slack
    if Confirm.ask("\n是否配置 Slack 通知?", default=False):
        webhook = Prompt.ask("请输入 Slack Webhook URL")
        if webhook:
            notifier.add_channel(SlackChannel(webhook))
            console.print("[green]✓ Slack 已添加[/green]")

    # 飞书
    if Confirm.ask("\n是否配置飞书通知?", default=False):
        webhook = Prompt.ask("请输入飞书 Webhook URL")
        if webhook:
            notifier.add_channel(FeishuChannel(webhook))
            console.print("[green]✓ 飞书已添加[/green]")

    # 钉钉
    if Confirm.ask("\n是否配置钉钉通知?", default=False):
        webhook = Prompt.ask("请输入钉钉 Webhook URL")
        secret = Prompt.ask("请输入加签密钥 (可选，直接回车跳过)", default="")
        if webhook:
            notifier.add_channel(DingtalkChannel(webhook, secret))
            console.print("[green]✓ 钉钉已添加[/green]")

    # 默认添加文件和声音
    notifier.add_channel(FileChannel())
    notifier.add_channel(SoundChannel())

    if notifier.channels:
        console.print(f"\n[green]已配置 {len(notifier.channels)} 个通知渠道[/green]")

        if Confirm.ask("\n是否立即测试?", default=True):
            await test_all_channels(notifier)

    return notifier


def show_env_help():
    """显示环境变量配置帮助"""
    help_text = """
[bold cyan]环境变量配置说明[/bold cyan]

支持以下环境变量来配置通知渠道:

[yellow]Discord:[/yellow]
  DISCORD_WEBHOOK=https://discord.com/api/webhooks/xxx/xxx

[yellow]Slack:[/yellow]
  SLACK_WEBHOOK=https://hooks.slack.com/services/xxx/xxx/xxx

[yellow]Telegram:[/yellow]
  TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
  TELEGRAM_CHAT_ID=123456789

[yellow]飞书:[/yellow]
  FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/xxx

[yellow]钉钉:[/yellow]
  DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=xxx
  DINGTALK_SECRET=SECxxxxx (可选)

[yellow]Server酱:[/yellow]
  SERVERCHAN_KEY=SCTxxxxx

[yellow]Bark:[/yellow]
  BARK_SERVER=https://api.day.app (可选)
  BARK_DEVICE_KEY=xxxxx

[bold]使用示例:[/bold]

  # Linux/Mac
  export DISCORD_WEBHOOK="https://discord.com/api/webhooks/xxx/xxx"
  export TELEGRAM_BOT_TOKEN="xxx"
  export TELEGRAM_CHAT_ID="xxx"
  python test_notifier.py

  # Windows PowerShell
  $env:DISCORD_WEBHOOK="https://discord.com/api/webhooks/xxx/xxx"
  python test_notifier.py

  # Windows CMD
  set DISCORD_WEBHOOK=https://discord.com/api/webhooks/xxx/xxx
  python test_notifier.py
"""
    console.print(Panel(help_text, title="环境变量配置帮助"))


async def main():
    parser = argparse.ArgumentParser(description="通知系统测试工具")
    parser.add_argument("--config", "-c", help="配置文件路径")
    parser.add_argument("--channel", help="测试特定渠道")
    parser.add_argument("--report", action="store_true", help="发送测试报告")
    parser.add_argument("--setup", action="store_true", help="交互式配置向导")
    parser.add_argument("--env-help", action="store_true", help="显示环境变量配置帮助")
    parser.add_argument("--all", "-a", action="store_true", help="测试所有渠道")
    parser.add_argument(
        "--level", "-l",
        choices=["critical", "high", "medium", "low"],
        default="high",
        help="测试通知级别"
    )

    args = parser.parse_args()

    # 显示环境变量帮助
    if args.env_help:
        show_env_help()
        return

    # 交互式配置
    if args.setup:
        await interactive_setup()
        return

    # 初始化通知器
    if args.config:
        console.print(f"[cyan]从配置文件加载: {args.config}[/cyan]")
        notifier = init_notifier(args.config)
    else:
        console.print("[cyan]从环境变量加载配置...[/cyan]")
        notifier = create_notifier_from_env()

    if not notifier.channels:
        console.print("[yellow]警告: 没有配置任何通知渠道[/yellow]")
        console.print("请设置环境变量或使用 --config 指定配置文件")
        console.print("使用 --env-help 查看环境变量配置说明")
        console.print("使用 --setup 进入交互式配置向导")
        return

    # 测试特定渠道
    if args.channel:
        await test_single_channel(args.channel, notifier)
        return

    # 发送测试报告
    if args.report:
        await test_report(notifier)
        return

    # 测试所有渠道
    if args.all:
        console.print(f"\n[cyan]发送 {args.level.upper()} 级别测试通知到所有渠道...[/cyan]")
        test_key = create_test_key(args.level)
        results = await notifier.notify(test_key, force=True)

        console.print("\n[bold]测试结果:[/bold]")
        for channel_name, success in results.items():
            if success is True:
                console.print(f"  [green]✓ {channel_name}: 成功[/green]")
            else:
                console.print(f"  [red]✗ {channel_name}: 失败[/red]")
        return

    # 默认: 交互式测试
    await test_all_channels(notifier)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]测试已取消[/yellow]")
