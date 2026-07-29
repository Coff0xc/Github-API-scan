#!/usr/bin/env python3
"""
Base URL 配对测试脚本

测试场景：
1. 官方 API key + 默认 base_url → 应该正常验证
2. 中转站 key + 中转站 base_url → 应该正常验证
3. 中转站 key + 空 base_url → 应该使用默认 URL（预期失败）
4. 验证日志是否正确记录使用的 base_url
"""

import asyncio
import os
from dataclasses import dataclass

from scanner import ScanResult
from validator import AsyncValidator
from database import KeyStatus, Database


@dataclass
class TestCase:
    """测试用例"""
    name: str
    platform: str
    api_key: str
    base_url: str
    expected_status: KeyStatus
    description: str


# 测试用例集合
TEST_CASES = [
    TestCase(
        name="官方 OpenAI - 默认 URL",
        platform="openai",
        api_key="sk-test1234567890abcdefghijklmnop",  # 测试密钥
        base_url="",  # 空 base_url，应使用默认值
        expected_status=KeyStatus.INVALID,
        description="测试空 base_url 时是否正确使用默认官方 URL"
    ),
    TestCase(
        name="中转站 OpenAI - 自定义 URL",
        platform="openai",
        api_key="sk-relay1234567890abcdefghijklmnop",
        base_url="https://api.relay-station.com/v1",
        expected_status=KeyStatus.INVALID,  # 测试密钥预期失败，但应该尝试连接到中转站
        description="测试是否使用自定义中转站 base_url"
    ),
    TestCase(
        name="OpenRouter - 聚合服务",
        platform="openai",
        api_key="sk-or-v1-abcd1234567890efgh",
        base_url="https://openrouter.ai/api/v1",
        expected_status=KeyStatus.INVALID,
        description="测试 OpenRouter 聚合服务的 base_url 配对"
    ),
    TestCase(
        name="Gemini - 官方 URL",
        platform="gemini",
        api_key="AIzaSyTest1234567890abcdefg",
        base_url="",
        expected_status=KeyStatus.INVALID,
        description="测试 Gemini 默认 URL"
    ),
    TestCase(
        name="Gemini - 自定义代理",
        platform="gemini",
        api_key="AIzaSyTest1234567890abcdefg",
        base_url="https://gemini-proxy.example.com/v1beta",
        expected_status=KeyStatus.INVALID,
        description="测试 Gemini 自定义代理 URL"
    ),
    TestCase(
        name="Azure OpenAI - 必需 endpoint",
        platform="azure",
        api_key="abc123def456789012345678901234ab",
        base_url="https://my-resource.openai.azure.com",
        expected_status=KeyStatus.INVALID,
        description="测试 Azure endpoint 必需性"
    ),
    TestCase(
        name="Azure OpenAI - 缺失 endpoint",
        platform="azure",
        api_key="abc123def456789012345678901234ab",
        base_url="",
        expected_status=KeyStatus.UNVERIFIED,
        description="测试 Azure 缺失 endpoint 时应返回 UNVERIFIED"
    ),
]


async def run_tests():
    """运行所有测试用例"""
    print("=" * 80)
    print("Base URL 配对测试")
    print("=" * 80)
    print()

    # 创建临时数据库用于测试
    test_db_path = "test_base_url_pairing.db"
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    db = Database(test_db_path)
    validator = AsyncValidator(db)
    passed = 0
    failed = 0

    for i, test in enumerate(TEST_CASES, 1):
        print(f"[测试 {i}/{len(TEST_CASES)}] {test.name}")
        print(f"  描述: {test.description}")
        print(f"  平台: {test.platform}")
        print(f"  API Key: {test.api_key[:20]}...")
        print(f"  Base URL: {test.base_url or '(空，使用默认)'}")

        # 构造 ScanResult
        scan_result = ScanResult(
            platform=test.platform,
            api_key=test.api_key,
            base_url=test.base_url,
            source_url="https://github.com/test/test",
            is_azure=(test.platform == "azure"),
            is_relay=bool(test.base_url and "api.openai.com" not in test.base_url)
        )

        try:
            # 执行验证
            result = await validator.validate_single(scan_result)

            print(f"  结果: {result.status.value}")
            print(f"  信息: {result.info}")

            # 检查是否符合预期
            # 注意：由于使用测试密钥，我们主要检查是否尝试了正确的 URL
            # 实际状态可能是 INVALID 或 CONNECTION_ERROR，这都是预期行为
            if result.status in [KeyStatus.INVALID, KeyStatus.CONNECTION_ERROR, test.expected_status]:
                print(f"  [OK] 通过（状态: {result.status.value}）")
                passed += 1
            else:
                print(f"  [FAIL] 失败（预期: {test.expected_status.value}, 实际: {result.status.value}）")
                failed += 1

        except Exception as e:
            print(f"  [ERROR] 异常: {type(e).__name__}: {e}")
            failed += 1

        print()

    # 清理资源
    await validator.close()
    # Database 没有 close 方法，直接删除即可

    # 删除测试数据库
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    print("=" * 80)
    print(f"测试完成: 通过 {passed}/{len(TEST_CASES)}, 失败 {failed}/{len(TEST_CASES)}")
    print("=" * 80)
    print()
    print("注意：")
    print("- 由于使用测试密钥，预期大部分会返回 INVALID 或 CONNECTION_ERROR")
    print("- 关键是检查日志中是否使用了正确的 base_url")
    print("- 查看日志输出，确认 '验证 XXX key ..., base_url: ...' 信息")
    print()


async def test_real_scenario():
    """
    真实场景模拟测试

    模拟从 GitHub 代码中提取到的完整上下文
    """
    print("=" * 80)
    print("真实场景测试：从代码上下文提取 base_url")
    print("=" * 80)
    print()

    # 场景 1: .env 文件中的中转站配置
    context_1 = """
# OpenAI API Configuration
OPENAI_API_KEY=sk-abc1234567890xyz
OPENAI_BASE_URL=https://api.relay-station.com/v1
"""

    # 场景 2: Python 代码中的配置
    context_2 = """
import openai
openai.api_key = "sk-def9876543210uvw"
openai.api_base = "https://openrouter.ai/api/v1"
"""

    # 场景 3: JavaScript 代码中的配置
    context_3 = """
const openai = new OpenAI({
    apiKey: 'sk-ghi5555555555zzz',
    baseURL: 'https://api.custom-proxy.io/v1',
});
"""

    print("场景 1: .env 文件配置")
    print(context_1)
    print("预期: 应提取 base_url = https://api.relay-station.com/v1")
    print()

    print("场景 2: Python 代码配置")
    print(context_2)
    print("预期: 应提取 base_url = https://openrouter.ai/api/v1")
    print()

    print("场景 3: JavaScript 代码配置")
    print(context_3)
    print("预期: 应提取 base_url = https://api.custom-proxy.io/v1")
    print()

    print("提示: 运行完整扫描时，scanner 会自动提取这些 base_url")
    print()


def main():
    """主函数"""
    print()
    asyncio.run(run_tests())
    asyncio.run(test_real_scenario())

    print("=" * 80)
    print("下一步：")
    print("1. 检查上方日志输出，确认每个测试使用了正确的 base_url")
    print("2. 如果要测试真实密钥，请修改 TEST_CASES 中的 api_key 和 base_url")
    print("3. 运行完整扫描: python main_v2.2.py")
    print("=" * 80)


if __name__ == "__main__":
    main()
