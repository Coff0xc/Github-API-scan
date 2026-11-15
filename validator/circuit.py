"""Domain circuit breaker with protected-host and app-error guards."""

import asyncio
import threading
import time
from enum import Enum
from typing import Any, Dict
from urllib.parse import urlparse

import aiohttp

from config import (
    CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    CIRCUIT_BREAKER_HALF_OPEN_REQUESTS,
    CIRCUIT_BREAKER_HTTP_CODES,
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
    PROTECTED_DOMAINS,
    SAFE_HTTP_STATUS_CODES,
)


class CircuitState(Enum):
    """熍断器状态"""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """
    域名熍断器 - 带防误杀保护

    1. 受保护域名白名单永远不熍断
    2. 只有连接层错误才触发熍断
    """

    def __init__(self):
        self._domain_states: Dict[str, dict] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _extract_domain(url: str) -> str:
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower().split(':')[0]
        except Exception:
            return ""

    @staticmethod
    def _is_protected_domain(domain: str) -> bool:
        if not domain:
            return True

        if domain in PROTECTED_DOMAINS:
            return True

        for protected in PROTECTED_DOMAINS:
            if domain.endswith('.' + protected) or domain.endswith(protected):
                return True

        return False

    @staticmethod
    def _is_network_error(error: Exception = None, http_status: int = None) -> bool:
        if error is not None:
            if isinstance(error, (aiohttp.ClientConnectorError, asyncio.TimeoutError)):
                return True
            if isinstance(error, aiohttp.ServerDisconnectedError):
                return True

        if http_status is not None:
            if http_status in CIRCUIT_BREAKER_HTTP_CODES:
                return True
            if http_status in SAFE_HTTP_STATUS_CODES:
                return False

        return False

    async def get_state(self, url: str) -> CircuitState:
        domain = self._extract_domain(url)

        if self._is_protected_domain(domain):
            return CircuitState.CLOSED

        with self._lock:
            if domain not in self._domain_states:
                return CircuitState.CLOSED

            state_info = self._domain_states[domain]
            current_state = state_info.get('state', CircuitState.CLOSED)

            if current_state == CircuitState.OPEN:
                open_time = state_info.get('open_time', 0)
                if time.time() - open_time >= CIRCUIT_BREAKER_RECOVERY_TIMEOUT:
                    state_info['state'] = CircuitState.HALF_OPEN
                    state_info['half_open_requests'] = 0
                    return CircuitState.HALF_OPEN

            return current_state

    async def is_allowed(self, url: str) -> bool:
        state = await self.get_state(url)

        if state == CircuitState.CLOSED:
            return True
        elif state == CircuitState.OPEN:
            return False
        else:
            domain = self._extract_domain(url)
            with self._lock:
                state_info = self._domain_states.get(domain, {})
                half_open_requests = state_info.get('half_open_requests', 0)
                if half_open_requests < CIRCUIT_BREAKER_HALF_OPEN_REQUESTS:
                    state_info['half_open_requests'] = half_open_requests + 1
                    return True
                return False

    async def record_success(self, url: str):
        domain = self._extract_domain(url)

        if self._is_protected_domain(domain):
            return

        with self._lock:
            if domain in self._domain_states:
                self._domain_states[domain] = {
                    'state': CircuitState.CLOSED,
                    'failure_count': 0
                }

    async def record_failure(
        self,
        url: str,
        error: Exception = None,
        http_status: int = None
    ):
        domain = self._extract_domain(url)

        if self._is_protected_domain(domain):
            return

        if not self._is_network_error(error, http_status):
            return

        with self._lock:
            if domain not in self._domain_states:
                self._domain_states[domain] = {
                    'state': CircuitState.CLOSED,
                    'failure_count': 0
                }

            state_info = self._domain_states[domain]
            state_info['failure_count'] = state_info.get('failure_count', 0) + 1

            if state_info['failure_count'] >= CIRCUIT_BREAKER_FAILURE_THRESHOLD:
                state_info['state'] = CircuitState.OPEN
                state_info['open_time'] = time.time()

    async def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            stats = {}
            for domain, info in self._domain_states.items():
                stats[domain] = {
                    'state': info.get('state', CircuitState.CLOSED).value,
                    'failure_count': info.get('failure_count', 0)
                }
            return stats


circuit_breaker = CircuitBreaker()
