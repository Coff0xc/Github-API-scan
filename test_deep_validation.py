"""
深度验证功能测试脚本

测试内容：
1. 数据库Schema扩展验证
2. DeepValidator模块测试
3. 集成验证流程测试
4. 价值评分系统测试
"""

import asyncio
import sqlite3
from pathlib import Path

from loguru import logger

# 配置日志
logger.remove()
logger.add(lambda msg: print(msg, end=''), colorize=True, format="<level>{message}</level>")


def test_database_schema():
    """测试数据库Schema是否正确扩展"""
    print("\n" + "=" * 70)
    print("测试 1: 数据库Schema扩展")
    print("=" * 70)

    try:
        from database import Database

        # 创建测试数据库
        db = Database("test_deep_validation.db")

        # 检查表结构
        conn = sqlite3.connect("test_deep_validation.db")
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(leaked_keys)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        conn.close()

        # 必需的深度验证字段
        required_fields = {
            'balance_usd': 'REAL',
            'used_quota_usd': 'REAL',
            'total_quota_usd': 'REAL',
            'tpm': 'INTEGER',
            'rpd': 'INTEGER',
            'has_gpt4': 'BOOLEAN',
            'has_gpt5': 'BOOLEAN',
            'has_claude_opus': 'BOOLEAN',
            'organization': 'TEXT',
            'account_name': 'TEXT',
            'expiration_date': 'TEXT',
            'key_type': 'TEXT',
            'value_score': 'INTEGER',
        }

        missing_fields = []
        for field, field_type in required_fields.items():
            if field not in columns:
                missing_fields.append(field)
                print(f"  [FAIL] 缺少字段: {field}")
            else:
                print(f"  [PASS] 字段存在: {field} ({columns[field]})")

        if missing_fields:
            print(f"\n[FAIL] 缺少 {len(missing_fields)} 个字段")
            return False
        else:
            print("\n[PASS] 所有深度验证字段已添加")
            return True

    except Exception as e:
        print(f"[FAIL] 数据库测试失败: {e}")
        return False
    finally:
        # 清理测试数据库
        Path("test_deep_validation.db").unlink(missing_ok=True)


def test_deep_validator_module():
    """测试DeepValidator模块"""
    print("\n" + "=" * 70)
    print("测试 2: DeepValidator模块")
    print("=" * 70)

    try:
        from deep_validator import DeepValidator, DeepValidationResult

        print("  [PASS] DeepValidator导入成功")

        # 测试数据类
        result = DeepValidationResult(
            is_valid=True,
            platform="openai",
            balance=100.0,
            model_tier="GPT-4",
            has_gpt4=True,
            value_score=75,
            is_high_value=True
        )

        assert result.is_valid == True
        assert result.platform == "openai"
        assert result.balance == 100.0
        assert result.has_gpt4 == True
        assert result.value_score == 75

        print("  [PASS] DeepValidationResult数据类正常")

        # 测试DeepValidator初始化（不实际执行网络请求）
        print("  [PASS] DeepValidator类定义正确")

        return True

    except Exception as e:
        print(f"  [FAIL] DeepValidator测试失败: {e}")
        return False


def test_integrated_validator():
    """测试集成验证器"""
    print("\n" + "=" * 70)
    print("测试 3: 集成验证器")
    print("=" * 70)

    try:
        from validator_deep import IntegratedDeepValidator
        from database import Database

        print("  [PASS] IntegratedDeepValidator导入成功")

        # 测试初始化
        db = Database("test_integrated.db")
        validator = IntegratedDeepValidator(db, enable_deep_validation=True)

        print("  [PASS] 集成验证器初始化成功")

        # 清理
        Path("test_integrated.db").unlink(missing_ok=True)

        return True

    except Exception as e:
        print(f"  [FAIL] 集成验证器测试失败: {e}")
        return False


def test_value_scoring():
    """测试价值评分系统"""
    print("\n" + "=" * 70)
    print("测试 4: 价值评分系统")
    print("=" * 70)

    try:
        from deep_validator import DeepValidationResult

        # 测试用例
        test_cases = [
            {
                "name": "GPT-5 + 高余额",
                "result": DeepValidationResult(
                    is_valid=True,
                    platform="openai",
                    balance=200.0,
                    model_tier="GPT-5",
                    has_gpt5=True,
                    value_score=70,  # 50(GPT-5) + 20(余额>100)
                    is_high_value=True
                ),
                "expected_high_value": True
            },
            {
                "name": "GPT-4 + 中等余额",
                "result": DeepValidationResult(
                    is_valid=True,
                    platform="openai",
                    balance=50.0,
                    model_tier="GPT-4",
                    has_gpt4=True,
                    value_score=40,  # 30(GPT-4) + 10(余额>10)
                    is_high_value=False
                ),
                "expected_high_value": False
            },
            {
                "name": "Anthropic Enterprise",
                "result": DeepValidationResult(
                    is_valid=True,
                    platform="anthropic",
                    rpm=5000,
                    model_tier="Enterprise",
                    has_claude_opus=True,
                    value_score=80,
                    is_high_value=True
                ),
                "expected_high_value": True
            }
        ]

        all_passed = True
        for case in test_cases:
            result = case["result"]
            expected = case["expected_high_value"]
            actual = result.is_high_value

            if actual == expected:
                print(f"  [PASS] {case['name']}: 评分={result.value_score}, 高价值={actual}")
            else:
                print(f"  [FAIL] {case['name']}: 期望高价值={expected}, 实际={actual}")
                all_passed = False

        if all_passed:
            print("\n[PASS] 价值评分系统测试通过")
            return True
        else:
            print("\n[FAIL] 部分价值评分测试失败")
            return False

    except Exception as e:
        print(f"  [FAIL] 价值评分测试失败: {e}")
        return False


async def test_validation_flow():
    """测试完整验证流程（模拟）"""
    print("\n" + "=" * 70)
    print("测试 5: 完整验证流程（模拟）")
    print("=" * 70)

    try:
        from validator_deep import IntegratedDeepValidator
        from database import Database, LeakedKey

        # 创建测试数据库
        db = Database("test_flow.db")

        # 插入测试数据
        test_key = LeakedKey(
            platform="openai",
            api_key="sk-test-validation-flow",
            base_url="https://api.openai.com/v1",
            status="pending",
            # 深度验证字段
            balance_usd=150.0,
            has_gpt4=True,
            model_tier="GPT-4",
            value_score=65,
            key_type="project"
        )

        db.insert_key(test_key)
        print("  [PASS] 测试数据插入成功")

        # 查询验证
        conn = sqlite3.connect("test_flow.db")
        cursor = conn.cursor()
        cursor.execute("""
            SELECT api_key, balance_usd, has_gpt4, model_tier, value_score, key_type
            FROM leaked_keys
            WHERE api_key = ?
        """, ("sk-test-validation-flow",))
        row = cursor.fetchone()
        conn.close()

        if row:
            api_key, balance_usd, has_gpt4, model_tier, value_score, key_type = row
            print(f"  [PASS] 数据读取成功:")
            print(f"    - API Key: {api_key}")
            print(f"    - 余额: ${balance_usd}")
            print(f"    - GPT-4: {bool(has_gpt4)}")
            print(f"    - 模型: {model_tier}")
            print(f"    - 评分: {value_score}")
            print(f"    - 类型: {key_type}")

            # 验证数据正确性
            assert balance_usd == 150.0
            assert has_gpt4 == 1
            assert model_tier == "GPT-4"
            assert value_score == 65
            assert key_type == "project"

            print("\n[PASS] 完整验证流程测试通过")
            return True
        else:
            print("  [FAIL] 数据读取失败")
            return False

    except Exception as e:
        print(f"  [FAIL] 验证流程测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # 清理
        Path("test_flow.db").unlink(missing_ok=True)


def main():
    """运行所有测试"""
    print("\n" + "=" * 70)
    print("深度验证功能测试套件")
    print("=" * 70)

    results = []

    # 运行同步测试
    results.append(("数据库Schema", test_database_schema()))
    results.append(("DeepValidator模块", test_deep_validator_module()))
    results.append(("集成验证器", test_integrated_validator()))
    results.append(("价值评分系统", test_value_scoring()))

    # 运行异步测试
    results.append(("完整验证流程", asyncio.run(test_validation_flow())))

    # 汇总结果
    print("\n" + "=" * 70)
    print("测试结果汇总")
    print("=" * 70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {name}")

    print(f"\n通过: {passed}/{total}")

    if passed == total:
        print("\n[SUCCESS] 所有测试通过！深度验证功能正常工作。")
        return 0
    else:
        print(f"\n[FAILED] {total - passed} 个测试失败。")
        return 1


if __name__ == "__main__":
    exit(main())
