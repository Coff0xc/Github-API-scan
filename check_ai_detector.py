#!/usr/bin/env python3
"""
AI 检测器测试脚本
=================

测试 AI 辅助检测功能

使用方法:
    # 测试后端可用性
    python test_ai_detector.py --check

    # 运行完整测试
    python test_ai_detector.py

    # 使用特定后端
    python test_ai_detector.py --backend ollama
    python test_ai_detector.py --backend openai
    python test_ai_detector.py --backend mock

    # 交互式测试
    python test_ai_detector.py --interactive
"""

import asyncio
import argparse
import os
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.prompt import Prompt, Confirm

from ai_detector import (
    AIDetector,
    SmartDetector,
    QuickFilter,
    CodeContext,
    OllamaBackend,
    OpenAIBackend,
    MockBackend,
    Confidence,
    KeyType,
)

console = Console()


# ============================================================================
#                              测试用例
# ============================================================================

TEST_CASES = [
    {
        "name": "真实 OpenAI Key (config.py)",
        "code": '''
# config.py
import openai

OPENAI_API_KEY = "sk-proj-abc123def456ghi789jkl012mno345pqr678stu901vwx234yz567"
client = openai.OpenAI(api_key=OPENAI_API_KEY)

response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello!"}]
)
''',
        "candidate_key": "sk-proj-abc123def456ghi789jkl012mno345pqr678stu901vwx234yz567",
        "file_path": "config.py",
        "expected_real": True,
        "expected_provider": "openai"
    },
    {
        "name": "测试 Key (示例文档)",
        "code": '''
# README.md
## Quick Start

1. Get your API key from OpenAI
2. Set it in your environment:

```bash
export OPENAI_API_KEY="sk-test-your-api-key-here"
```

Replace `sk-test-your-api-key-here` with your actual key.
''',
        "candidate_key": "sk-test-your-api-key-here",
        "file_path": "README.md",
        "expected_real": False,
        "expected_provider": "openai"
    },
    {
        "name": "占位符 Key",
        "code": '''
const config = {
    apiKey: "YOUR_API_KEY_HERE",  // TODO: Replace with your actual key
    baseUrl: "https://api.openai.com/v1"
};
''',
        "candidate_key": "YOUR_API_KEY_HERE",
        "file_path": "config.js",
        "expected_real": False,
        "expected_provider": "unknown"
    },
    {
        "name": "真实 Anthropic Key (.env)",
        "code": '''
# .env
DATABASE_URL=postgres://localhost:5432/mydb
ANTHROPIC_API_KEY=sk-ant-api03-Kj8mN2pL5qR7tX9vY1wZ3aB4cD6eF8gH0iJ2kL4mN6oP8qR0sT2uV
SECRET_KEY=mysecretkey123
''',
        "candidate_key": "sk-ant-api03-Kj8mN2pL5qR7tX9vY1wZ3aB4cD6eF8gH0iJ2kL4mN6oP8qR0sT2uV",
        "file_path": ".env",
        "expected_real": True,
        "expected_provider": "anthropic"
    },
    {
        "name": "假 Key (xxx 模式)",
        "code": '''
const GEMINI_KEY = "AIzaSyDxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx";
// This is just a placeholder
''',
        "candidate_key": "AIzaSyDxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "file_path": "example.js",
        "expected_real": False,
        "expected_provider": "google"
    },
    {
        "name": "真实 Gemini Key",
        "code": '''
import google.generativeai as genai

genai.configure(api_key="AIzaSyB7mK9nL3pQ2rT5uW8xY0zA1bC3dE4fG5h")

model = genai.GenerativeModel('gemini-pro')
response = model.generate_content("Hello!")
''',
        "candidate_key": "AIzaSyB7mK9nL3pQ2rT5uW8xY0zA1bC3dE4fG5h",
        "file_path": "app.py",
        "expected_real": True,
        "expected_provider": "google"
    },
    {
        "name": "测试文件中的 Key",
        "code": '''
# test_api.py
import pytest

def test_openai_connection():
    """Test OpenAI API connection with mock key"""
    mock_key = "sk-proj-testkey123456789abcdefghijklmnopqrstuvwxyz"
    # This should not make real API calls
    assert len(mock_key) > 20
''',
        "candidate_key": "sk-proj-testkey123456789abcdefghijklmnopqrstuvwxyz",
        "file_path": "test_api.py",
        "expected_real": False,
        "expected_provider": "openai"
    },
    {
        "name": "真实 Groq Key",
        "code": '''
from groq import Groq

client = Groq(api_key="gsk_aB3cD4eF5gH6iJ7kL8mN9oP0qR1sT2uV3wX4yZ5")
''',
        "candidate_key": "gsk_aB3cD4eF5gH6iJ7kL8mN9oP0qR1sT2uV3wX4yZ5",
        "file_path": "main.py",
        "expected_real": True,
        "expected_provider": "groq"
    },
]


# ============================================================================
#                              测试函数
# ============================================================================

async def check_backends():
    """检查各后端可用性"""
    console.print("\n[bold cyan]═══ 检查 LLM 后端可用性 ═══[/bold cyan]\n")

    table = Table(title="后端状态")
    table.add_column("后端", style="cyan")
    table.add_column("状态", style="green")
    table.add_column("详情", style="dim")

    # Ollama
    ollama = OllamaBackend()
    ollama_available = await ollama.is_available()
    table.add_row(
        "Ollama (本地)",
        "[green]✓ 可用[/green]" if ollama_available else "[red]✗ 不可用[/red]",
        f"模型: {ollama.model}" if ollama_available else "请安装 Ollama 并拉取模型"
    )

    # OpenAI
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if openai_key:
        openai = OpenAIBackend(api_key=openai_key)
        openai_available = await openai.is_available()
        table.add_row(
            "OpenAI API",
            "[green]✓ 可用[/green]" if openai_available else "[red]✗ 不可用[/red]",
            "Key 已配置" if openai_available else "Key 无效或网络问题"
        )
    else:
        table.add_row(
            "OpenAI API",
            "[yellow]○ 未配置[/yellow]",
            "设置 OPENAI_API_KEY 环境变量"
        )

    # Mock
    table.add_row(
        "Mock (规则引擎)",
        "[green]✓ 可用[/green]",
        "始终可用，作为降级方案"
    )

    console.print(table)

    # 推荐
    console.print("\n[bold]推荐配置:[/bold]")
    if ollama_available:
        console.print("  [green]✓[/green] 使用 Ollama 本地模型 (免费、快速、隐私)")
    elif openai_key:
        console.print("  [yellow]→[/yellow] 使用 OpenAI API (需要费用)")
    else:
        console.print("  [yellow]→[/yellow] 使用规则引擎模式 (无需 LLM)")
        console.print("\n  安装 Ollama 获得最佳体验:")
        console.print("  [cyan]curl -fsSL https://ollama.ai/install.sh | sh[/cyan]")
        console.print("  [cyan]ollama pull llama3.2:3b[/cyan]")


async def run_quick_filter_tests():
    """测试快速过滤器"""
    console.print("\n[bold cyan]═══ 快速过滤器测试 ═══[/bold cyan]\n")

    quick_filter = QuickFilter()

    table = Table(title="快速过滤测试结果")
    table.add_column("测试用例", style="cyan")
    table.add_column("结果", style="green")
    table.add_column("原因", style="dim")

    passed = 0
    failed = 0

    for test in TEST_CASES:
        is_fake, reason = quick_filter.is_likely_fake(
            candidate_key=test["candidate_key"],
            context=test["code"],
            file_path=test["file_path"]
        )

        # 检查结果是否符合预期
        expected_fake = not test["expected_real"]
        correct = (is_fake == expected_fake)

        if correct:
            passed += 1
            status = "[green]✓ 正确[/green]"
        else:
            failed += 1
            status = "[red]✗ 错误[/red]"

        table.add_row(
            test["name"],
            status,
            reason[:40] if reason else "通过过滤"
        )

    console.print(table)
    console.print(f"\n[bold]结果: {passed}/{len(TEST_CASES)} 通过[/bold]")


async def run_ai_detector_tests(backend_name: str = "auto"):
    """测试 AI 检测器"""
    console.print(f"\n[bold cyan]═══ AI 检测器测试 (后端: {backend_name}) ═══[/bold cyan]\n")

    # 选择后端
    if backend_name == "ollama":
        backend = OllamaBackend()
    elif backend_name == "openai":
        backend = OpenAIBackend()
    elif backend_name == "mock":
        backend = MockBackend()
    else:
        # 自动选择
        backend = None

    # 创建检测器
    detector = SmartDetector(ai_detector=AIDetector(backend=backend) if backend else None)
    await detector.initialize()

    console.print(f"使用后端: [cyan]{detector.ai_detector.backend.name}[/cyan]\n")

    table = Table(title="AI 检测测试结果")
    table.add_column("测试用例", style="cyan", width=25)
    table.add_column("预期", style="yellow", width=8)
    table.add_column("实际", style="green", width=8)
    table.add_column("置信度", width=8)
    table.add_column("类型", width=12)
    table.add_column("结果", width=8)

    passed = 0
    failed = 0

    for test in TEST_CASES:
        context = CodeContext(
            code_snippet=test["code"],
            file_path=test["file_path"]
        )

        should_validate, result = await detector.should_validate(
            candidate_key=test["candidate_key"],
            code_context=context,
            use_ai=True
        )

        # 检查结果
        expected = test["expected_real"]
        correct = (should_validate == expected)

        if correct:
            passed += 1
            status = "[green]✓[/green]"
        else:
            failed += 1
            status = "[red]✗[/red]"

        table.add_row(
            test["name"][:25],
            "真实" if expected else "假",
            "真实" if should_validate else "假",
            result.confidence.value,
            result.key_type.value,
            status
        )

    console.print(table)
    console.print(f"\n[bold]结果: {passed}/{len(TEST_CASES)} 通过[/bold]")

    # 显示统计
    stats = detector.get_stats()
    console.print(f"\n[dim]统计: 过滤率 {stats['filter_rate']*100:.1f}%[/dim]")


async def interactive_test():
    """交互式测试"""
    console.print(Panel.fit(
        "[bold cyan]AI 检测器交互式测试[/bold cyan]\n\n"
        "输入代码片段和候选 Key，查看 AI 分析结果",
        title="交互模式"
    ))

    # 初始化检测器
    detector = SmartDetector()
    await detector.initialize()
    console.print(f"后端: [cyan]{detector.ai_detector.backend.name}[/cyan]\n")

    while True:
        console.print("\n" + "="*50)

        # 输入代码片段
        console.print("[yellow]输入代码片段 (输入空行结束):[/yellow]")
        code_lines = []
        while True:
            line = input()
            if not line:
                break
            code_lines.append(line)

        if not code_lines:
            if Confirm.ask("退出交互模式?", default=True):
                break
            continue

        code = "\n".join(code_lines)

        # 输入候选 Key
        candidate_key = Prompt.ask("候选 Key")
        if not candidate_key:
            continue

        file_path = Prompt.ask("文件路径 (可选)", default="")

        # 分析
        console.print("\n[cyan]分析中...[/cyan]")

        context = CodeContext(code_snippet=code, file_path=file_path)
        should_validate, result = await detector.should_validate(
            candidate_key=candidate_key,
            code_context=context,
            use_ai=True
        )

        # 显示结果
        console.print("\n[bold]分析结果:[/bold]")
        console.print(f"  应该验证: {'[green]是[/green]' if should_validate else '[red]否[/red]'}")
        console.print(f"  置信度: [cyan]{result.confidence.value}[/cyan]")
        console.print(f"  类型: [yellow]{result.key_type.value}[/yellow]")
        console.print(f"  平台: {result.provider}")
        console.print(f"  推理: {result.reasoning}")


async def main():
    parser = argparse.ArgumentParser(description="AI 检测器测试工具")
    parser.add_argument("--check", action="store_true", help="检查后端可用性")
    parser.add_argument("--backend", choices=["auto", "ollama", "openai", "mock"], default="auto", help="指定后端")
    parser.add_argument("--quick", action="store_true", help="仅测试快速过滤器")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互式测试")
    parser.add_argument("--all", "-a", action="store_true", help="运行所有测试")

    args = parser.parse_args()

    if args.check:
        await check_backends()
        return

    if args.interactive:
        await interactive_test()
        return

    if args.quick:
        await run_quick_filter_tests()
        return

    if args.all:
        await check_backends()
        await run_quick_filter_tests()
        await run_ai_detector_tests(args.backend)
        return

    # 默认运行 AI 检测测试
    await run_ai_detector_tests(args.backend)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]测试已取消[/yellow]")
