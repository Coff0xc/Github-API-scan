"""
深度验证器集成模块

将 deep_validator.py 的深度检测能力集成到现有的验证流程中
"""

import asyncio
from typing import Optional
from loguru import logger

from validator import OptimizedAsyncValidator, ValidationResult
from deep_validator import DeepValidator, DeepValidationResult
from database import Database, LeakedKey, KeyStatus


class IntegratedDeepValidator(OptimizedAsyncValidator):
    """
    增强型验证器 - 集成深度验证功能

    在标准验证基础上添加：
    - 余额透视
    - 额度分析
    - 模型访问权限检测
    - 价值评分
    """

    def __init__(self, db: Database, enable_deep_validation: bool = True):
        super().__init__(db)
        self.enable_deep_validation = enable_deep_validation
        self.deep_validator = None

    async def __aenter__(self):
        await super().__aenter__()
        if self.enable_deep_validation:
            self.deep_validator = DeepValidator(self.session)
        return self

    async def validate_with_depth(
        self,
        platform: str,
        api_key: str,
        base_url: str = "",
        source_url: str = ""
    ) -> tuple[ValidationResult, Optional[DeepValidationResult]]:
        """
        执行标准验证 + 深度验证

        Returns:
            (标准验证结果, 深度验证结果)
        """
        # 1. 标准验证
        standard_result = await self.validate(platform, api_key, base_url, source_url)

        # 2. 如果标准验证成功，执行深度验证
        deep_result = None
        if self.enable_deep_validation and standard_result.status == KeyStatus.VALID:
            try:
                deep_result = await self._deep_validate(platform, api_key, base_url)

                # 3. 合并深度验证结果到数据库
                if deep_result and deep_result.is_valid:
                    self._update_with_deep_result(api_key, standard_result, deep_result)

            except Exception as e:
                logger.warning(f"深度验证失败: {e}")

        return standard_result, deep_result

    async def _deep_validate(
        self,
        platform: str,
        api_key: str,
        base_url: str
    ) -> Optional[DeepValidationResult]:
        """执行深度验证"""
        if not self.deep_validator:
            return None

        if platform == "openai":
            return await self.deep_validator.deep_validate_openai(api_key, base_url)
        elif platform == "anthropic":
            return await self.deep_validator.deep_validate_anthropic(api_key, base_url)
        else:
            # 其他平台暂不支持深度验证
            return None

    def _update_with_deep_result(
        self,
        api_key: str,
        standard: ValidationResult,
        deep: DeepValidationResult
    ):
        """将深度验证结果更新到数据库"""
        try:
            self.db.update_key_status(
                api_key=api_key,
                status=standard.status,
                balance=standard.info,
                model_tier=deep.model_tier or standard.info,
                rpm=deep.rpm or 0,
                is_high_value=deep.is_high_value or standard.status == KeyStatus.VALID,
                # 深度验证字段
                balance_usd=deep.balance,
                used_quota_usd=deep.used_quota,
                total_quota_usd=deep.total_quota,
                tpm=deep.tpm,
                rpd=deep.rpd,
                has_gpt4=deep.has_gpt4,
                has_gpt5=deep.has_gpt5,
                has_claude_opus=deep.has_claude_opus,
                organization=deep.organization,
                account_name=deep.account_name,
                expiration_date=deep.expiration_date,
                key_type=deep.key_type,
                value_score=deep.value_score
            )

            if deep.is_high_value:
                logger.success(
                    f"🔥 高价值Key: {api_key[:20]}... | "
                    f"评分: {deep.value_score}/100 | "
                    f"余额: ${deep.balance:.2f} | "
                    f"模型: {deep.model_tier}"
                )

        except Exception as e:
            logger.error(f"更新深度验证结果失败: {e}")


async def validate_key_deep(
    platform: str,
    api_key: str,
    base_url: str = "",
    source_url: str = "",
    db_path: str = "leaked_keys.db"
) -> tuple[ValidationResult, Optional[DeepValidationResult]]:
    """
    便捷函数：执行单个Key的深度验证

    Args:
        platform: 平台名称 (openai, anthropic, gemini等)
        api_key: API密钥
        base_url: 自定义base URL（可选）
        source_url: 来源URL（可选）
        db_path: 数据库路径

    Returns:
        (标准验证结果, 深度验证结果)
    """
    db = Database(db_path)

    async with IntegratedDeepValidator(db, enable_deep_validation=True) as validator:
        return await validator.validate_with_depth(platform, api_key, base_url, source_url)


async def batch_validate_deep(
    keys: list[tuple[str, str, str]],
    db_path: str = "leaked_keys.db",
    concurrency: int = 50
) -> list[tuple[ValidationResult, Optional[DeepValidationResult]]]:
    """
    批量深度验证

    Args:
        keys: [(platform, api_key, base_url), ...]
        db_path: 数据库路径
        concurrency: 并发数

    Returns:
        验证结果列表
    """
    db = Database(db_path)
    results = []

    async with IntegratedDeepValidator(db, enable_deep_validation=True) as validator:
        semaphore = asyncio.Semaphore(concurrency)

        async def validate_one(platform, api_key, base_url):
            async with semaphore:
                return await validator.validate_with_depth(platform, api_key, base_url)

        tasks = [validate_one(p, k, b) for p, k, b in keys]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # 过滤异常
    return [r for r in results if not isinstance(r, Exception)]


# 测试代码
async def test_deep_validation():
    """测试深度验证功能"""
    print("=" * 80)
    print("深度验证测试")
    print("=" * 80)

    # 测试用例（使用虚拟key）
    test_keys = [
        ("openai", "sk-test-123456789", ""),
        ("anthropic", "sk-ant-test-123", ""),
    ]

    db = Database("test_deep_validation.db")

    async with IntegratedDeepValidator(db, enable_deep_validation=True) as validator:
        for platform, api_key, base_url in test_keys:
            print(f"\n测试 {platform}: {api_key[:20]}...")

            standard, deep = await validator.validate_with_depth(
                platform, api_key, base_url
            )

            print(f"标准验证: {standard.status.value}")

            if deep:
                print(f"深度验证:")
                print(f"  - 模型阶梯: {deep.model_tier}")
                print(f"  - 余额: ${deep.balance:.2f}")
                print(f"  - 价值评分: {deep.value_score}/100")
                print(f"  - 高价值: {deep.is_high_value}")
                print(f"  - GPT-4: {deep.has_gpt4}")
                print(f"  - GPT-5: {deep.has_gpt5}")
                print(f"  - Claude Opus: {deep.has_claude_opus}")
                print(f"  - 组织: {deep.organization or 'N/A'}")
                print(f"  - Key类型: {deep.key_type or 'N/A'}")

    print("\n" + "=" * 80)
    print("测试完成")


if __name__ == "__main__":
    asyncio.run(test_deep_validation())
