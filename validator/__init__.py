"""
验证器包 - 平台验证原语

进程入口使用 validator_optimized.start_validators。本包提供熔断器、
ValidationResult，以及各平台的 validate_key_async。不要新增第三套验证循环。

平台判断在 validator.platforms；扫描入口使用 validator_optimized.py。
"""

from database import KeyStatus
from utils import mask_key
from validator.circuit import CircuitBreaker, CircuitState, circuit_breaker
from validator.engine import (
    AsyncValidator,
    get_scan_result_class,
    run_validator_loop,
    start_validators,
    validate_key_async,
)
from validator.types import (
    MAX_CONCURRENCY,
    REQUEST_TIMEOUT,
    RPM_ENTERPRISE_THRESHOLD,
    RPM_FREE_TRIAL_THRESHOLD,
    ValidationResult,
)

__all__ = [
    'AsyncValidator',
    'start_validators',
    'validate_key_async',
    'ValidationResult',
    'CircuitBreaker',
    'circuit_breaker',
    'mask_key',
    'MAX_CONCURRENCY',
    'REQUEST_TIMEOUT',
    'RPM_ENTERPRISE_THRESHOLD',
    'RPM_FREE_TRIAL_THRESHOLD',
]
