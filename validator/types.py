"""Shared validation types and tunables."""

from dataclasses import dataclass

from aiohttp import ClientTimeout

from config import config
from database import KeyStatus

MAX_CONCURRENCY = config.validator_max_concurrency
REQUEST_TIMEOUT = ClientTimeout(total=config.request_timeout, connect=10)

RPM_ENTERPRISE_THRESHOLD = 3000
RPM_FREE_TRIAL_THRESHOLD = 20


@dataclass
class ValidationResult:
    """验证结果：状态、说明、模型档位、RPM。"""
    status: KeyStatus
    info: str
    model_tier: str = ""
    rpm: int = 0
