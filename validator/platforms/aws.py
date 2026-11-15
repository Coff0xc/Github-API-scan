"""AWS keys: format-only, no live call."""

from database import KeyStatus
from validator.types import ValidationResult


async def validate_aws_bedrock(self, api_key: str, base_url: str) -> ValidationResult:
    """验证 AWS Bedrock Access Key (仅格式检查)"""
    if api_key.startswith('AKIA') and len(api_key) == 20:
        return ValidationResult(KeyStatus.UNVERIFIED, "AWS Bedrock Key 格式正确")
    return ValidationResult(KeyStatus.INVALID, "格式错误")


async def validate_aws_access_key(self, api_key: str, base_url: str) -> ValidationResult:
    """验证 AWS Access Key (仅格式检查，不实际调用)"""
    if api_key.startswith('AKIA') and len(api_key) == 20:
        return ValidationResult(KeyStatus.UNVERIFIED, "AWS Key 格式正确")
    return ValidationResult(KeyStatus.INVALID, "格式错误")
