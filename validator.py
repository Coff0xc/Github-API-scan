"""
验证器模块 - 异步 API Key 验证 + 深度价值评估

核心特性：
1. AsyncIO + aiohttp 高并发验证 (100 并发)
2. 深度价值评估 (GPT-4 探测、余额检测、RPM 透视)
3. 状态细分（valid, invalid, quota_exceeded, connection_error）
4. UI 仪表盘集成

v2.1 优化：
- 导出 OptimizedAsyncValidator（使用连接池和智能重试）
- 保持原有 AsyncValidator 向后兼容
"""

import asyncio
import ssl
from typing import Tuple, Optional, Dict, Any
from datetime import datetime
from dataclasses import dataclass

import aiohttp
from aiohttp import ClientTimeout, TCPConnector
from loguru import logger

from config import (
    config,
    PROTECTED_DOMAINS,
    SAFE_HTTP_STATUS_CODES,
    CIRCUIT_BREAKER_HTTP_CODES,
    CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
    CIRCUIT_BREAKER_HALF_OPEN_REQUESTS
)
from database import Database, LeakedKey, KeyStatus


# ============================================================================
#                              常量与配置
# ============================================================================

# 最大并发数
MAX_CONCURRENCY = 100

# 请求超时
REQUEST_TIMEOUT = ClientTimeout(total=15, connect=10)

# 高价值模型列表
HIGH_VALUE_MODELS = ['gpt-4', 'gpt-4-turbo', 'gpt-4o', 'gpt-4-32k', 'claude-3-opus']

# RPM 阈值分级
RPM_ENTERPRISE_THRESHOLD = 3000   # >= 3000 为企业级
RPM_FREE_TRIAL_THRESHOLD = 20     # <= 20 为免费试用


# ============================================================================
#                          熍断器 (Circuit Breaker) - 防误杀保护
# ============================================================================

from enum import Enum
from urllib.parse import urlparse
import time
import threading


class CircuitState(Enum):
    """熍断器状态"""
    CLOSED = "closed"        # 正常，允许请求
    OPEN = "open"            # 熍断，拒绝请求
    HALF_OPEN = "half_open"  # 半开，允许试探请求


class CircuitBreaker:
    """
    域名熍断器 - 带防误杀保护
    
    核心安全逻辑：
    1. 受保护域名白名单 - 永远不熍断
    2. 严格错误界定 - 只有连接层错误才触发熍断
    """
    
    def __init__(self):
        # 域名 -> 状态信息
        self._domain_states: Dict[str, dict] = {}
        self._lock = threading.Lock()  # 线程安全
    
    @staticmethod
    def _extract_domain(url: str) -> str:
        """从 URL 提取域名"""
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower().split(':')[0]  # 移除端口号
        except Exception:
            return ""
    
    @staticmethod
    def _is_protected_domain(domain: str) -> bool:
        """
        检查域名是否受保护
        
        支持后缀匹配，例如 my-resource.openai.azure.com 会匹配 openai.azure.com
        """
        if not domain:
            return True  # 空域名默认保护
        
        # 精确匹配
        if domain in PROTECTED_DOMAINS:
            return True
        
        # 后缀匹配（用于 Azure 等动态子域名）
        for protected in PROTECTED_DOMAINS:
            if domain.endswith('.' + protected) or domain.endswith(protected):
                return True
        
        return False
    
    @staticmethod
    def _is_network_error(error: Exception = None, http_status: int = None) -> bool:
        """
        判断是否为网络层错误（应触发熍断）
        
        网络层错误：
        - 连接拒绝/DNS 失败 (ClientConnectorError)
        - 超时 (TimeoutError)
        - 网关错误 502/503/504
        
        应用层错误（不触发熍断）：
        - 401/403/429 等业务错误
        """
        # 检查异常类型
        if error is not None:
            if isinstance(error, (aiohttp.ClientConnectorError, asyncio.TimeoutError)):
                return True
            # ServerDisconnectedError 等也算网络错误
            if isinstance(error, aiohttp.ServerDisconnectedError):
                return True
        
        # 检查 HTTP 状态码
        if http_status is not None:
            if http_status in CIRCUIT_BREAKER_HTTP_CODES:
                return True
            # 应用层错误不触发熍断
            if http_status in SAFE_HTTP_STATUS_CODES:
                return False
        
        return False
    
    async def get_state(self, url: str) -> CircuitState:
        """获取域名的熍断状态"""
        domain = self._extract_domain(url)
        
        # 受保护域名永远返回 CLOSED
        if self._is_protected_domain(domain):
            return CircuitState.CLOSED
        
        with self._lock:
            if domain not in self._domain_states:
                return CircuitState.CLOSED
            
            state_info = self._domain_states[domain]
            current_state = state_info.get('state', CircuitState.CLOSED)
            
            # 检查是否应从 OPEN 转为 HALF_OPEN
            if current_state == CircuitState.OPEN:
                open_time = state_info.get('open_time', 0)
                if time.time() - open_time >= CIRCUIT_BREAKER_RECOVERY_TIMEOUT:
                    state_info['state'] = CircuitState.HALF_OPEN
                    state_info['half_open_requests'] = 0
                    return CircuitState.HALF_OPEN
            
            return current_state
    
    async def is_allowed(self, url: str) -> bool:
        """检查请求是否允许"""
        state = await self.get_state(url)
        
        if state == CircuitState.CLOSED:
            return True
        elif state == CircuitState.OPEN:
            return False
        else:  # HALF_OPEN
            domain = self._extract_domain(url)
            with self._lock:
                state_info = self._domain_states.get(domain, {})
                half_open_requests = state_info.get('half_open_requests', 0)
                if half_open_requests < CIRCUIT_BREAKER_HALF_OPEN_REQUESTS:
                    state_info['half_open_requests'] = half_open_requests + 1
                    return True
                return False
    
    async def record_success(self, url: str):
        """记录成功请求"""
        domain = self._extract_domain(url)
        
        if self._is_protected_domain(domain):
            return
        
        with self._lock:
            if domain in self._domain_states:
                # 成功后重置状态
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
        """
        记录失败请求 - 带防误杀保护
        
        Args:
            url: 请求 URL
            error: 异常对象
            http_status: HTTP 状态码
        """
        domain = self._extract_domain(url)
        
        # ========== 安全检查 1: 受保护域名 ==========
        if self._is_protected_domain(domain):
            return  # 直接忽略，不记录失败
        
        # ========== 安全检查 2: 应用层错误 ==========
        if not self._is_network_error(error, http_status):
            return  # 业务错误不触发熍断
        
        # ========== 记录网络层失败 ==========
        with self._lock:
            if domain not in self._domain_states:
                self._domain_states[domain] = {
                    'state': CircuitState.CLOSED,
                    'failure_count': 0
                }
            
            state_info = self._domain_states[domain]
            state_info['failure_count'] = state_info.get('failure_count', 0) + 1
            
            # 检查是否触发熍断
            if state_info['failure_count'] >= CIRCUIT_BREAKER_FAILURE_THRESHOLD:
                state_info['state'] = CircuitState.OPEN
                state_info['open_time'] = time.time()
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取熍断器统计信息"""
        with self._lock:
            stats = {}
            for domain, info in self._domain_states.items():
                stats[domain] = {
                    'state': info.get('state', CircuitState.CLOSED).value,
                    'failure_count': info.get('failure_count', 0)
                }
            return stats


# 全局熍断器实例
circuit_breaker = CircuitBreaker()


def mask_key(key: str) -> str:
    """遮蔽 API Key 中间部分"""
    if len(key) <= 12:
        return key[:4] + "..." + key[-4:]
    return key[:8] + "..." + key[-4:]


@dataclass
class ValidationResult:
    """验证结果数据类"""
    status: KeyStatus
    info: str
    model_tier: str = ""
    rpm: int = 0
    balance_usd: float = 0.0
    is_high_value: bool = False


class AsyncValidator:
    """异步 API Key 验证器 - 集成熍断器保护"""
    
    def __init__(self, db: Database, dashboard=None):
        self.db = db
        self.dashboard = dashboard
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
        self._session: Optional[aiohttp.ClientSession] = None
        self._circuit_breaker = circuit_breaker  # 使用全局熍断器
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 aiohttp session"""
        if self._session is None or self._session.closed:
            # 配置代理
            connector = TCPConnector(
                limit=MAX_CONCURRENCY,
                ssl=ssl.create_default_context(),
                force_close=True
            )
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=REQUEST_TIMEOUT,
                trust_env=True  # 支持环境变量代理
            )
        return self._session
    
    async def close(self):
        """关闭 session"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    def _get_proxy(self) -> Optional[str]:
        """获取代理 URL"""
        return config.proxy_url if config.proxy_url else None
    
    def _log(self, message: str, level: str = "INFO"):
        """输出日志"""
        if self.dashboard:
            self.dashboard.add_log(message, level)
    
    def _try_url_variants(self, base_url: str, path: str) -> list:
        """生成 URL 变体"""
        base_url = base_url.rstrip('/')
        path = path.lstrip('/')
        
        variants = [f"{base_url}/{path}"]
        
        if '/v1' not in base_url:
            variants.append(f"{base_url}/v1/{path}")
        
        if '/v1' in base_url:
            base_without_v1 = base_url.replace('/v1', '')
            variants.append(f"{base_without_v1}/v1/{path}")
        
        return variants
    
    # ========================================================================
    #                           熍断器集成方法
    # ========================================================================
    
    async def _check_circuit_breaker(self, base_url: str) -> Optional[ValidationResult]:
        """
        检查熍断器状态
        
        Returns:
            如果被熍断，返回 CONNECTION_ERROR 结果；否则返回 None
        """
        if not config.circuit_breaker_enabled:
            return None
        
        if not await self._circuit_breaker.is_allowed(base_url):
            self._log(f"熍断中: {base_url[:30]}...", "WARN")
            return ValidationResult(KeyStatus.CONNECTION_ERROR, "域名熍断中")
        
        return None
    
    async def _record_circuit_result(
        self, 
        url: str, 
        success: bool = False, 
        error: Exception = None,
        http_status: int = None
    ):
        """记录请求结果到熍断器"""
        if not config.circuit_breaker_enabled:
            return
        
        if success:
            await self._circuit_breaker.record_success(url)
        else:
            await self._circuit_breaker.record_failure(url, error, http_status)
    
    # ========================================================================
    #                           异步验证方法
    # ========================================================================
    
    def _is_likely_valid_relay(self, base_url: str) -> bool:
        """
        检查 URL 是否可能是有效的中转站 + SSRF 防护
        
        安全检查：
        1. 排除明显不是 API 中转站的 URL
        2. 阻止私有 IP 地址 (RFC1918, loopback, link-local)
        3. 阻止危险域名后缀
        """
        if not base_url:
            return True  # 空 URL 会使用默认值
        
        url_lower = base_url.lower()
        
        # ========== SSRF 防护: 强制 HTTPS ==========
        if not url_lower.startswith('https://'):
            if not (url_lower.startswith('http://localhost') or url_lower.startswith('http://127.0.0.1')):
                if url_lower.startswith('http://'):
                    return False
        
        # ========== SSRF 防护: 阻止私有 IP ==========
        try:
            from urllib.parse import urlparse
            import ipaddress
            parsed = urlparse(base_url)
            host = parsed.hostname or ''
            try:
                ip = ipaddress.ip_address(host)
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                    return False
            except ValueError:
                pass
            for suffix in ['.local', '.internal', '.corp', '.lan', '.home']:
                if host.endswith(suffix):
                    return False
        except Exception:
            return False
        
        # 无效域名黑名单
        invalid_domains = [
            'docs.djangoproject.com',
            'docs.python.org',
            'developer.mozilla.org',
            'stackoverflow.com',
            'themoviedb.org',
            'prisma.io',
            'pris.ly',
            'every.to',
            'makersuite.google.com',
            '/settings',
            '/ref/',
            '/docs/',
            '/guide',
        ]
        
        for invalid in invalid_domains:
            if invalid in url_lower:
                return False
        
        return True
    
    async def validate_openai(self, api_key: str, base_url: str) -> ValidationResult:
        """异步验证 OpenAI / 中转站 - 集成熍断器保护"""
        
        # ========== 新增：预检查 base_url 有效性 ==========
        if not self._is_likely_valid_relay(base_url):
            return ValidationResult(KeyStatus.INVALID, "base_url 无效")
        
        if not base_url:
            base_url = config.default_base_urls["openai"]
        
        # 熍断器检查
        circuit_result = await self._check_circuit_breaker(base_url)
        if circuit_result:
            return circuit_result
        
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        session = await self._get_session()
        proxy = self._get_proxy()
        
        model_tier = "GPT-3.5"
        rpm = 0
        models_list = []
        
        # Step 1: GET /models
        for url in self._try_url_variants(base_url, "models"):
            try:
                async with session.get(url, headers=headers, proxy=proxy) as resp:
                    # 提取 RPM
                    rpm = int(resp.headers.get('x-ratelimit-limit-requests', 0))
                    
                    if resp.status == 200:
                        # 记录成功
                        await self._record_circuit_result(url, success=True)
                        
                        data = await resp.json()
                        models_list = [m.get("id", "") for m in data.get("data", [])]
                        
                        # 检测高价值模型
                        for m in models_list:
                            if any(hv in m.lower() for hv in ['gpt-4', 'gpt-4o']):
                                model_tier = "GPT-4"
                                break
                        
                        model_names = [m[:15] for m in models_list[:3]]
                        info = f"{len(models_list)}模型: {', '.join(model_names)}"
                        
                        # RPM 透视标记
                        rpm_tier = ""
                        if rpm >= RPM_ENTERPRISE_THRESHOLD:
                            rpm_tier = "Enterprise"
                        elif rpm > 0 and rpm <= RPM_FREE_TRIAL_THRESHOLD:
                            rpm_tier = "Free Trial"
                        
                        if rpm_tier:
                            info = f"{info} [{rpm_tier}]"
                        
                        is_high = model_tier == "GPT-4" or rpm >= RPM_ENTERPRISE_THRESHOLD
                        
                        return ValidationResult(KeyStatus.VALID, info, model_tier, rpm, 0.0, is_high)
                    
                    elif resp.status == 429:
                        # 429 是应用层错误，不触发熍断
                        await self._record_circuit_result(url, http_status=429)
                        return ValidationResult(KeyStatus.QUOTA_EXCEEDED, "配额耗尽")
                    
                    elif resp.status in CIRCUIT_BREAKER_HTTP_CODES:
                        # 502/503/504 网关错误
                        await self._record_circuit_result(url, http_status=resp.status)
                        continue
                    else:
                        # 其他状态码 (401/403 等)
                        await self._record_circuit_result(url, http_status=resp.status)
                        
            except asyncio.TimeoutError as e:
                await self._record_circuit_result(url, error=e)
                continue
            except aiohttp.ClientConnectorError as e:
                await self._record_circuit_result(url, error=e)
                return ValidationResult(KeyStatus.CONNECTION_ERROR, "连接失败")
            except Exception as e:
                logger.debug(f"验证异常: {type(e).__name__}: {e}")
                continue
        
        # Step 2: POST /chat/completions (Fallback)
        chat_body = {"model": "gpt-3.5-turbo", "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 1}
        
        for url in self._try_url_variants(base_url, "chat/completions"):
            try:
                async with session.post(url, headers=headers, json=chat_body, proxy=proxy) as resp:
                    if resp.status == 200:
                        await self._record_circuit_result(url, success=True)
                        return ValidationResult(KeyStatus.VALID, "有效(chat)", model_tier, rpm, 0.0, False)
                    elif resp.status == 429:
                        await self._record_circuit_result(url, http_status=429)
                        return ValidationResult(KeyStatus.QUOTA_EXCEEDED, "配额耗尽")
                    elif resp.status in CIRCUIT_BREAKER_HTTP_CODES:
                        await self._record_circuit_result(url, http_status=resp.status)
                        continue
                    else:
                        await self._record_circuit_result(url, http_status=resp.status)
            except aiohttp.ClientConnectorError as e:
                await self._record_circuit_result(url, error=e)
                return ValidationResult(KeyStatus.CONNECTION_ERROR, "连接失败")
            except asyncio.TimeoutError as e:
                await self._record_circuit_result(url, error=e)
                continue
            except Exception as e:
                logger.debug(f"验证异常: {type(e).__name__}: {e}")
                continue
        
        return ValidationResult(KeyStatus.INVALID, "认证失败")
    
    async def validate_gemini(self, api_key: str, base_url: str) -> ValidationResult:
        """异步验证 Gemini - 集成熍断器保护"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        
        # 熍断器检查（Gemini 域名在白名单中，不会被熍断）
        circuit_result = await self._check_circuit_breaker(url)
        if circuit_result:
            return circuit_result
        
        session = await self._get_session()
        proxy = self._get_proxy()
        
        try:
            async with session.get(url, proxy=proxy) as resp:
                if resp.status == 200:
                    await self._record_circuit_result(url, success=True)
                    data = await resp.json()
                    models = data.get("models", [])
                    # Gemini Pro 检测
                    has_pro = any('gemini-1.5-pro' in m.get('name', '').lower() for m in models)
                    tier = "Gemini-Pro" if has_pro else "Gemini"
                    return ValidationResult(KeyStatus.VALID, f"{len(models)}模型", tier, 0, 0.0, has_pro)
                elif resp.status == 429:
                    await self._record_circuit_result(url, http_status=429)
                    return ValidationResult(KeyStatus.QUOTA_EXCEEDED, "Gemini配额耗尽")
                elif resp.status in CIRCUIT_BREAKER_HTTP_CODES:
                    await self._record_circuit_result(url, http_status=resp.status)
                    return ValidationResult(KeyStatus.CONNECTION_ERROR, f"网关错误 {resp.status}")
                else:
                    await self._record_circuit_result(url, http_status=resp.status)
                    return ValidationResult(KeyStatus.INVALID, f"HTTP {resp.status}")
        except aiohttp.ClientConnectorError as e:
            await self._record_circuit_result(url, error=e)
            return ValidationResult(KeyStatus.CONNECTION_ERROR, "Gemini连接失败")
        except asyncio.TimeoutError as e:
            await self._record_circuit_result(url, error=e)
            return ValidationResult(KeyStatus.CONNECTION_ERROR, "Gemini超时")
        except Exception as e:
            return ValidationResult(KeyStatus.INVALID, str(e)[:20])
    
    async def validate_anthropic(self, api_key: str, base_url: str) -> ValidationResult:
        """
        异步验证 Anthropic Claude Key - 集成熍断器保护
        
        Anthropic 使用专用 Headers:
        - x-api-key: API Key
        - anthropic-version: API 版本
        
        必须用 POST /v1/messages 验证（不支持 GET /models）
        
        特殊处理:
        - 400 + "credit balance is too low" → QUOTA_EXCEEDED（Key 有效但没钱）
        - 401 → INVALID（认证失败）
        """
        if not base_url:
            base_url = config.default_base_urls["anthropic"]
        
        # 熍断器检查
        circuit_result = await self._check_circuit_breaker(base_url)
        if circuit_result:
            return circuit_result
        
        # Anthropic 专用 Headers
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        # 必须 POST 请求
        body = {
            "model": "claude-3-haiku-20240307",
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "Hi"}]
        }
        
        session = await self._get_session()
        proxy = self._get_proxy()
        
        try:
            url = f"{base_url.rstrip('/')}/v1/messages"
            async with session.post(url, headers=headers, json=body, proxy=proxy) as resp:
                response_text = await resp.text()
                
                if resp.status == 200:
                    await self._record_circuit_result(url, success=True)
                    # 尝试解析模型信息
                    try:
                        data = await resp.json()
                        model_used = data.get("model", "claude-3")
                        # 检测是否为高价值模型 (Opus/Sonnet)
                        is_high = "opus" in model_used.lower() or "sonnet" in model_used.lower()
                        tier = "Claude-3-Opus" if "opus" in model_used.lower() else "Claude-3"
                        return ValidationResult(KeyStatus.VALID, "Claude有效", tier, 0, 0.0, is_high)
                    except Exception:
                        return ValidationResult(KeyStatus.VALID, "Claude有效", "Claude-3", 0, 0.0, True)
                
                elif resp.status == 400:
                    # 关键：检查是否为余额不足（Key 有效但没钱）
                    await self._record_circuit_result(url, http_status=400)
                    if "credit" in response_text.lower() and "balance" in response_text.lower():
                        # "credit balance is too low" - Key 有效但配额耗尽
                        return ValidationResult(KeyStatus.QUOTA_EXCEEDED, "Claude余额不足", "Claude-3", 0, 0.0, False)
                    elif "billing" in response_text.lower():
                        # 账单问题也视为有效但无配额
                        return ValidationResult(KeyStatus.QUOTA_EXCEEDED, "Claude账单问题", "Claude-3", 0, 0.0, False)
                    else:
                        # 其他 400 错误（可能是请求格式问题，但 Key 可能有效）
                        return ValidationResult(KeyStatus.VALID, "有效(请求错误)", "Claude", 0, 0.0, False)
                
                elif resp.status == 401:
                    # 认证失败 - Key 无效
                    await self._record_circuit_result(url, http_status=401)
                    return ValidationResult(KeyStatus.INVALID, "Claude认证失败")
                
                elif resp.status == 403:
                    # 权限不足 - 可能 Key 有效但被禁用
                    await self._record_circuit_result(url, http_status=403)
                    if "disabled" in response_text.lower():
                        return ValidationResult(KeyStatus.INVALID, "Claude Key已禁用")
                    return ValidationResult(KeyStatus.QUOTA_EXCEEDED, "Claude权限受限", "Claude", 0, 0.0, False)
                
                elif resp.status == 429:
                    await self._record_circuit_result(url, http_status=429)
                    return ValidationResult(KeyStatus.QUOTA_EXCEEDED, "Claude速率限制")
                
                elif resp.status in CIRCUIT_BREAKER_HTTP_CODES:
                    await self._record_circuit_result(url, http_status=resp.status)
                    return ValidationResult(KeyStatus.CONNECTION_ERROR, f"网关错误 {resp.status}")
                
                else:
                    await self._record_circuit_result(url, http_status=resp.status)
                    return ValidationResult(KeyStatus.INVALID, f"HTTP {resp.status}")
                    
        except aiohttp.ClientConnectorError as e:
            await self._record_circuit_result(base_url, error=e)
            return ValidationResult(KeyStatus.CONNECTION_ERROR, "Claude连接失败")
        except asyncio.TimeoutError as e:
            await self._record_circuit_result(base_url, error=e)
            return ValidationResult(KeyStatus.CONNECTION_ERROR, "Claude超时")
        except Exception as e:
            return ValidationResult(KeyStatus.INVALID, str(e)[:20])
    
    async def validate_azure(self, api_key: str, base_url: str) -> ValidationResult:
        """异步验证 Azure - 集成熍断器保护"""
        if not base_url:
            return ValidationResult(KeyStatus.UNVERIFIED, "缺少Endpoint")
        
        # 熍断器检查（Azure 域名在白名单中，不会被熍断）
        circuit_result = await self._check_circuit_breaker(base_url)
        if circuit_result:
            return circuit_result
        
        headers = {"api-key": api_key, "Content-Type": "application/json"}
        session = await self._get_session()
        proxy = self._get_proxy()
        
        try:
            url = f"{base_url.rstrip('/')}/openai/deployments?api-version=2023-05-15"
            async with session.get(url, headers=headers, proxy=proxy) as resp:
                if resp.status == 200:
                    await self._record_circuit_result(url, success=True)
                    return ValidationResult(KeyStatus.VALID, "Azure有效", "Azure-GPT", 0, 0.0, True)
                elif resp.status == 429:
                    await self._record_circuit_result(url, http_status=429)
                    return ValidationResult(KeyStatus.QUOTA_EXCEEDED, "Azure配额耗尽")
                elif resp.status in CIRCUIT_BREAKER_HTTP_CODES:
                    await self._record_circuit_result(url, http_status=resp.status)
                    return ValidationResult(KeyStatus.CONNECTION_ERROR, f"网关错误 {resp.status}")
                else:
                    await self._record_circuit_result(url, http_status=resp.status)
                    return ValidationResult(KeyStatus.INVALID, f"HTTP {resp.status}")
        except aiohttp.ClientConnectorError as e:
            await self._record_circuit_result(base_url, error=e)
            return ValidationResult(KeyStatus.CONNECTION_ERROR, "Azure连接失败")
        except asyncio.TimeoutError as e:
            await self._record_circuit_result(base_url, error=e)
            return ValidationResult(KeyStatus.CONNECTION_ERROR, "Azure超时")
        except Exception as e:
            return ValidationResult(KeyStatus.INVALID, str(e)[:20])
    
    async def probe_gpt4(self, api_key: str, base_url: str) -> bool:
        """探测是否支持 GPT-4"""
        if not base_url:
            base_url = config.default_base_urls["openai"]
        
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        body = {"model": "gpt-4", "messages": [{"role": "user", "content": "1"}], "max_tokens": 1}
        
        session = await self._get_session()
        proxy = self._get_proxy()
        
        for url in self._try_url_variants(base_url, "chat/completions"):
            try:
                async with session.post(url, headers=headers, json=body, proxy=proxy) as resp:
                    return resp.status == 200
            except Exception as e:
                logger.debug(f"验证异常: {type(e).__name__}: {e}")
                continue
        return False
    
    async def probe_billing(self, api_key: str, base_url: str) -> dict:
        """
        探测中转站/官方 API 余额
        
        返回:
            {
                'balance': float,      # 余额 (USD)
                'used': float,         # 已使用
                'limit': float,        # 总额度
                'source': str          # 余额来源
            }
        """
        result = {'balance': 0.0, 'used': 0.0, 'limit': 0.0, 'source': ''}
        
        headers = {"Authorization": f"Bearer {api_key}"}
        session = await self._get_session()
        proxy = self._get_proxy()
        
        # ========== 1. OpenAI 官方余额检测 ==========
        if not base_url or "api.openai.com" in base_url:
            # 官方 API 余额查询需要 organization header
            # 但大多数泄露的 Key 没有这个信息，跳过
            return result
        
        # ========== 2. 中转站余额检测 ==========
        billing_endpoints = [
            # one-api / new-api 格式 (最常见)
            {
                'path': '/api/user/self',
                'fields': ['quota', 'used_quota', 'data.quota', 'data.used_quota']
            },
            {
                'path': '/api/user/info', 
                'fields': ['quota', 'used_quota', 'balance', 'data.quota']
            },
            # OpenAI 兼容格式
            {
                'path': '/dashboard/billing/subscription',
                'fields': ['hard_limit_usd', 'soft_limit_usd', 'system_hard_limit_usd']
            },
            {
                'path': '/v1/dashboard/billing/subscription',
                'fields': ['hard_limit_usd', 'soft_limit_usd']
            },
            {
                'path': '/dashboard/billing/credit_grants',
                'fields': ['total_granted', 'total_used', 'total_available']
            },
            # 其他中转站
            {
                'path': '/user/info',
                'fields': ['balance', 'quota', 'credits', 'remaining']
            },
            {
                'path': '/api/status',
                'fields': ['quota', 'balance', 'credits']
            },
        ]
        
        for endpoint in billing_endpoints:
            try:
                url = f"{base_url.rstrip('/')}{endpoint['path']}"
                async with session.get(url, headers=headers, proxy=proxy) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        balance = self._extract_balance_from_response(data, endpoint['fields'])
                        if balance > 0:
                            result['balance'] = balance
                            result['source'] = endpoint['path']
                            return result
            except Exception as e:
                logger.debug(f"验证异常: {type(e).__name__}: {e}")
                continue
        
        return result
    
    def _extract_balance_from_response(self, data: dict, fields: list) -> float:
        """
        从响应数据中提取余额
        
        支持嵌套字段如 'data.quota'
        """
        for field in fields:
            try:
                value = data
                for key in field.split('.'):
                    if isinstance(value, dict):
                        value = value.get(key)
                    else:
                        value = None
                        break
                
                if value is not None and value != 0:
                    balance = float(value)
                    # one-api 的 quota 单位是 "500000" 表示 $5
                    # 需要除以 100000 转换为美元
                    if balance > 10000:
                        balance = balance / 100000
                    return balance
            except (ValueError, TypeError, AttributeError):
                continue
        return 0.0
    
    async def probe_quota_by_request(self, api_key: str, base_url: str) -> dict:
        """
        通过实际请求测试额度
        
        这是最准确的方法：尝试发送一个最小请求
        
        返回:
            {
                'has_quota': bool,     # 是否有额度
                'error_type': str,     # 错误类型 (quota/rate_limit/auth/other)
                'message': str         # 详细信息
            }
        """
        if not base_url:
            base_url = config.default_base_urls["openai"]
        
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        session = await self._get_session()
        proxy = self._get_proxy()
        
        # 最小化请求：1 token
        chat_body = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": "1"}],
            "max_tokens": 1
        }
        
        for url in self._try_url_variants(base_url, "chat/completions"):
            try:
                async with session.post(url, headers=headers, json=chat_body, proxy=proxy) as resp:
                    response_text = await resp.text()
                    
                    if resp.status == 200:
                        return {'has_quota': True, 'error_type': None, 'message': '有额度'}
                    
                    elif resp.status == 429:
                        # 区分配额耗尽 vs 速率限制
                        if 'quota' in response_text.lower() or 'exceeded' in response_text.lower():
                            return {'has_quota': False, 'error_type': 'quota', 'message': '配额耗尽'}
                        elif 'rate' in response_text.lower():
                            # 速率限制说明 Key 有效，只是请求太快
                            return {'has_quota': True, 'error_type': 'rate_limit', 'message': '速率限制(有额度)'}
                        else:
                            return {'has_quota': False, 'error_type': 'quota', 'message': '429错误'}
                    
                    elif resp.status == 401:
                        return {'has_quota': False, 'error_type': 'auth', 'message': '认证失败'}
                    
                    elif resp.status == 402:
                        # Payment Required - 明确表示没钱
                        return {'has_quota': False, 'error_type': 'quota', 'message': '需要付款'}
                    
                    elif resp.status == 400:
                        # 检查是否为余额不足
                        if 'insufficient' in response_text.lower() or 'quota' in response_text.lower():
                            return {'has_quota': False, 'error_type': 'quota', 'message': '余额不足'}
                        # 其他 400 错误可能是请求格式问题，Key 可能有效
                        return {'has_quota': True, 'error_type': 'other', 'message': '请求错误'}
                    
                    else:
                        return {'has_quota': False, 'error_type': 'other', 'message': f'HTTP {resp.status}'}
                        
            except asyncio.TimeoutError:
                continue
            except aiohttp.ClientConnectorError:
                return {'has_quota': False, 'error_type': 'connection', 'message': '连接失败'}
            except Exception as e:
                logger.debug(f"验证异常: {type(e).__name__}: {e}")
                continue
        
        return {'has_quota': False, 'error_type': 'other', 'message': '无法验证'}
    

    # ========================================================================
    #                           新增平台验证方法
    # ========================================================================

    async def validate_huggingface(self, api_key: str, base_url: str) -> ValidationResult:
        """验证 Hugging Face API Key"""
        if not base_url:
            base_url = "https://api-inference.huggingface.co"

        headers = {"Authorization": f"Bearer {api_key}"}
        proxy = config.proxy_url or None

        session = await self._get_session()
        try:
            async with session.get(
                f"{base_url.rstrip('/')}/models/gpt2",
                headers=headers, proxy=proxy
            ) as resp:
                if resp.status == 200:
                    return ValidationResult(KeyStatus.VALID, "HuggingFace 有效")
                elif resp.status == 401:
                    return ValidationResult(KeyStatus.INVALID, "无效")
                elif resp.status == 429:
                    return ValidationResult(KeyStatus.QUOTA_EXCEEDED, "配额耗尽")
        except Exception as e:
            logger.debug(f"HuggingFace 验证异常: {e}")
        return ValidationResult(KeyStatus.CONNECTION_ERROR, "连接失败")

    async def validate_groq(self, api_key: str, base_url: str) -> ValidationResult:
        """验证 Groq API Key"""
        if not base_url:
            base_url = "https://api.groq.com/openai/v1"

        headers = {"Authorization": f"Bearer {api_key}"}
        proxy = config.proxy_url or None

        session = await self._get_session()
        try:
            async with session.get(
                f"{base_url.rstrip('/')}/models",
                headers=headers, proxy=proxy
            ) as resp:
                if resp.status == 200:
                    return ValidationResult(KeyStatus.VALID, "Groq 有效")
                elif resp.status == 401:
                    return ValidationResult(KeyStatus.INVALID, "无效")
                elif resp.status == 429:
                    return ValidationResult(KeyStatus.QUOTA_EXCEEDED, "配额耗尽")
        except Exception as e:
            logger.debug(f"Groq 验证异常: {e}")
        return ValidationResult(KeyStatus.CONNECTION_ERROR, "连接失败")

    async def validate_deepseek(self, api_key: str, base_url: str) -> ValidationResult:
        """验证 DeepSeek API Key"""
        if not base_url:
            base_url = "https://api.deepseek.com"

        headers = {"Authorization": f"Bearer {api_key}"}
        proxy = config.proxy_url or None

        session = await self._get_session()
        try:
            async with session.get(
                f"{base_url.rstrip('/')}/models",
                headers=headers, proxy=proxy
            ) as resp:
                if resp.status == 200:
                    return ValidationResult(KeyStatus.VALID, "DeepSeek 有效")
                elif resp.status == 401:
                    return ValidationResult(KeyStatus.INVALID, "无效")
                elif resp.status == 429:
                    return ValidationResult(KeyStatus.QUOTA_EXCEEDED, "配额耗尽")
        except Exception as e:
            logger.debug(f"DeepSeek 验证异常: {e}")
        return ValidationResult(KeyStatus.CONNECTION_ERROR, "连接失败")

    async def validate_cohere(self, api_key: str, base_url: str) -> ValidationResult:
        """验证 Cohere API Key"""
        if not base_url:
            base_url = "https://api.cohere.ai/v1"

        headers = {"Authorization": f"Bearer {api_key}"}
        proxy = config.proxy_url or None

        session = await self._get_session()
        try:
            async with session.get(
                f"{base_url.rstrip('/')}/models",
                headers=headers, proxy=proxy
            ) as resp:
                if resp.status == 200:
                    return ValidationResult(KeyStatus.VALID, "Cohere 有效")
                elif resp.status == 401:
                    return ValidationResult(KeyStatus.INVALID, "无效")
                elif resp.status == 429:
                    return ValidationResult(KeyStatus.QUOTA_EXCEEDED, "配额耗尽")
        except Exception as e:
            logger.debug(f"Cohere 验证异常: {e}")
        return ValidationResult(KeyStatus.CONNECTION_ERROR, "连接失败")

    async def validate_mistral(self, api_key: str, base_url: str) -> ValidationResult:
        """验证 Mistral API Key"""
        if not base_url:
            base_url = "https://api.mistral.ai/v1"

        headers = {"Authorization": f"Bearer {api_key}"}
        proxy = config.proxy_url or None

        session = await self._get_session()
        try:
            async with session.get(
                f"{base_url.rstrip('/')}/models",
                headers=headers, proxy=proxy
            ) as resp:
                if resp.status == 200:
                    return ValidationResult(KeyStatus.VALID, "Mistral 有效")
                elif resp.status == 401:
                    return ValidationResult(KeyStatus.INVALID, "无效")
                elif resp.status == 429:
                    return ValidationResult(KeyStatus.QUOTA_EXCEEDED, "配额耗尽")
        except Exception as e:
            logger.debug(f"Mistral 验证异常: {e}")
        return ValidationResult(KeyStatus.CONNECTION_ERROR, "连接失败")

    async def validate_together(self, api_key: str, base_url: str) -> ValidationResult:
        """验证 Together AI API Key"""
        if not base_url:
            base_url = "https://api.together.xyz/v1"

        headers = {"Authorization": f"Bearer {api_key}"}
        proxy = config.proxy_url or None

        session = await self._get_session()
        try:
            async with session.get(
                f"{base_url.rstrip('/')}/models",
                headers=headers, proxy=proxy
            ) as resp:
                if resp.status == 200:
                    return ValidationResult(KeyStatus.VALID, "Together 有效")
                elif resp.status == 401:
                    return ValidationResult(KeyStatus.INVALID, "无效")
                elif resp.status == 429:
                    return ValidationResult(KeyStatus.QUOTA_EXCEEDED, "配额耗尽")
        except Exception as e:
            logger.debug(f"Together 验证异常: {e}")
        return ValidationResult(KeyStatus.CONNECTION_ERROR, "连接失败")

    async def validate_replicate(self, api_key: str, base_url: str) -> ValidationResult:
        """验证 Replicate API Key"""
        if not base_url:
            base_url = "https://api.replicate.com/v1"

        headers = {"Authorization": f"Token {api_key}"}
        proxy = config.proxy_url or None

        session = await self._get_session()
        try:
            async with session.get(
                f"{base_url.rstrip('/')}/account",
                headers=headers, proxy=proxy
            ) as resp:
                if resp.status == 200:
                    return ValidationResult(KeyStatus.VALID, "Replicate 有效")
                elif resp.status == 401:
                    return ValidationResult(KeyStatus.INVALID, "无效")
                elif resp.status == 429:
                    return ValidationResult(KeyStatus.QUOTA_EXCEEDED, "配额耗尽")
        except Exception as e:
            logger.debug(f"Replicate 验证异常: {e}")
        return ValidationResult(KeyStatus.CONNECTION_ERROR, "连接失败")

    async def validate_perplexity(self, api_key: str, base_url: str) -> ValidationResult:
        """验证 Perplexity API Key"""
        if not base_url:
            base_url = "https://api.perplexity.ai"

        headers = {"Authorization": f"Bearer {api_key}"}
        proxy = config.proxy_url or None

        session = await self._get_session()
        try:
            async with session.get(
                f"{base_url.rstrip('/')}/models",
                headers=headers, proxy=proxy
            ) as resp:
                if resp.status == 200:
                    return ValidationResult(KeyStatus.VALID, "Perplexity 有效")
                elif resp.status == 401:
                    return ValidationResult(KeyStatus.INVALID, "无效")
                elif resp.status == 429:
                    return ValidationResult(KeyStatus.QUOTA_EXCEEDED, "配额耗尽")
        except Exception as e:
            logger.debug(f"Perplexity 验证异常: {e}")
        return ValidationResult(KeyStatus.CONNECTION_ERROR, "连接失败")

    async def validate_fireworks(self, api_key: str, base_url: str) -> ValidationResult:
        """验证 Fireworks AI API Key"""
        if not base_url:
            base_url = "https://api.fireworks.ai/inference/v1"

        headers = {"Authorization": f"Bearer {api_key}"}
        proxy = config.proxy_url or None

        session = await self._get_session()
        try:
            async with session.get(
                f"{base_url.rstrip('/')}/models",
                headers=headers, proxy=proxy
            ) as resp:
                if resp.status == 200:
                    return ValidationResult(KeyStatus.VALID, "Fireworks 有效")
                elif resp.status == 401:
                    return ValidationResult(KeyStatus.INVALID, "无效")
                elif resp.status == 429:
                    return ValidationResult(KeyStatus.QUOTA_EXCEEDED, "配额耗尽")
        except Exception as e:
            logger.debug(f"Fireworks 验证异常: {e}")
        return ValidationResult(KeyStatus.CONNECTION_ERROR, "连接失败")

    async def validate_stripe(self, api_key: str, base_url: str) -> ValidationResult:
        """验证 Stripe API Key"""
        headers = {"Authorization": f"Bearer {api_key}"}
        proxy = config.proxy_url or None

        session = await self._get_session()
        try:
            async with session.get(
                "https://api.stripe.com/v1/balance",
                headers=headers, proxy=proxy
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    balance = sum(b.get('amount', 0) for b in data.get('available', [])) / 100
                    return ValidationResult(KeyStatus.VALID, f"Stripe ${balance:.2f}", is_high_value=balance > 0)
                elif resp.status == 401:
                    return ValidationResult(KeyStatus.INVALID, "无效")
        except Exception as e:
            logger.debug(f"Stripe 验证异常: {e}")
        return ValidationResult(KeyStatus.CONNECTION_ERROR, "连接失败")

    async def validate_github_token(self, api_key: str, base_url: str) -> ValidationResult:
        """验证 GitHub Token"""
        headers = {"Authorization": f"token {api_key}"}
        proxy = config.proxy_url or None

        session = await self._get_session()
        try:
            async with session.get(
                "https://api.github.com/user",
                headers=headers, proxy=proxy
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    username = data.get('login', 'unknown')
                    return ValidationResult(KeyStatus.VALID, f"GitHub @{username}")
                elif resp.status == 401:
                    return ValidationResult(KeyStatus.INVALID, "无效")
        except Exception as e:
            logger.debug(f"GitHub 验证异常: {e}")
        return ValidationResult(KeyStatus.CONNECTION_ERROR, "连接失败")

    async def validate_aws_access_key(self, api_key: str, base_url: str) -> ValidationResult:
        """验证 AWS Access Key (仅格式检查，不实际调用)"""
        # AWS 验证需要 Secret Key 配对，这里只做格式检查
        if api_key.startswith('AKIA') and len(api_key) == 20:
            return ValidationResult(KeyStatus.UNVERIFIED, "AWS Key 格式正确")
        return ValidationResult(KeyStatus.INVALID, "格式错误")

    async def validate_single(self, result: 'ScanResult') -> ValidationResult:
        """验证单个结果（统一入口）"""
        platform = result.platform.lower()

        # 主流 AI 平台
        if platform == "azure" or result.is_azure:
            return await self.validate_azure(result.api_key, result.base_url)
        elif platform == "gemini":
            return await self.validate_gemini(result.api_key, result.base_url)
        elif platform == "anthropic":
            return await self.validate_anthropic(result.api_key, result.base_url)
        # 新兴 AI 平台
        elif platform == "huggingface":
            return await self.validate_huggingface(result.api_key, result.base_url)
        elif platform == "groq":
            return await self.validate_groq(result.api_key, result.base_url)
        elif platform == "deepseek":
            return await self.validate_deepseek(result.api_key, result.base_url)
        elif platform == "cohere":
            return await self.validate_cohere(result.api_key, result.base_url)
        elif platform == "mistral":
            return await self.validate_mistral(result.api_key, result.base_url)
        elif platform == "together":
            return await self.validate_together(result.api_key, result.base_url)
        elif platform == "replicate":
            return await self.validate_replicate(result.api_key, result.base_url)
        elif platform == "perplexity":
            return await self.validate_perplexity(result.api_key, result.base_url)
        elif platform == "fireworks":
            return await self.validate_fireworks(result.api_key, result.base_url)
        # 云服务商
        elif platform == "stripe":
            return await self.validate_stripe(result.api_key, result.base_url)
        elif platform == "github_token":
            return await self.validate_github_token(result.api_key, result.base_url)
        elif platform == "aws_access_key":
            return await self.validate_aws_access_key(result.api_key, result.base_url)
        # 默认使用 OpenAI 兼容验证
        else:
            return await self.validate_openai(result.api_key, result.base_url)
    
    async def process_result(self, result: 'ScanResult'):
        """
        异步处理单个结果
        
        包含第二层去重防御：在验证前检查 Key 是否已存在于数据库
        """
        async with self.semaphore:
            masked = mask_key(result.api_key)
            
            # ========== 第二层防御：Key 级去重 ==========
            # 在发起任何网络请求之前，先检查数据库
            if self.db.key_exists(result.api_key):
                self._log(f"[SKIP] Key 已在数据库中: {masked}", "SKIP")
                if self.dashboard:
                    self.dashboard.increment_stat("skipped_duplicate")
                return
            
            # 入库（带唯一约束保护）
            leaked_key = LeakedKey(
                platform=result.platform,
                api_key=result.api_key,
                base_url=result.base_url,
                status=KeyStatus.PENDING.value,
                source_url=result.source_url,
                found_time=datetime.now()
            )
            
            if not self.db.insert_key(leaked_key):
                # 并发情况下可能被其他线程先插入
                self._log(f"[SKIP] Key 插入冲突: {masked}", "SKIP")
                return
            
            # 验证
            self._log(f"验证 {masked}...", "INFO")
            vr = await self.validate_single(result)
            
            # 深度探测（仅对有效的 OpenAI/Relay Key）
            if vr.status == KeyStatus.VALID and result.platform.lower() in ['openai', 'relay']:
                # 并行探测 GPT-4 和余额
                gpt4_task = asyncio.create_task(self.probe_gpt4(result.api_key, result.base_url))
                billing_task = asyncio.create_task(self.probe_billing(result.api_key, result.base_url))
                quota_task = asyncio.create_task(self.probe_quota_by_request(result.api_key, result.base_url))
                
                has_gpt4, billing_result, quota_result = await asyncio.gather(
                    gpt4_task, billing_task, quota_task
                )
                
                if has_gpt4:
                    vr.model_tier = "GPT-4"
                    vr.is_high_value = True
                
                # 使用余额检测结果
                if billing_result.get('balance', 0) > 0:
                    vr.balance_usd = billing_result['balance']
                    vr.is_high_value = True
                
                # 使用实际请求测试结果更新状态
                if not quota_result.get('has_quota', True):
                    if quota_result.get('error_type') == 'quota':
                        vr.status = KeyStatus.QUOTA_EXCEEDED
                        vr.info = quota_result.get('message', '配额耗尽')
                    elif quota_result.get('error_type') == 'auth':
                        vr.status = KeyStatus.INVALID
                        vr.info = '认证失败'
            
            # 更新数据库
            balance_str = vr.info
            if vr.balance_usd > 0:
                balance_str = f"${vr.balance_usd:.2f} | {vr.info}"
            if vr.model_tier:
                balance_str = f"{vr.model_tier} | {balance_str}"
            
            self.db.update_key_status(
                result.api_key, 
                vr.status, 
                balance_str,
                model_tier=vr.model_tier,
                rpm=vr.rpm,
                is_high_value=vr.is_high_value
            )
            
            # 更新 UI
            if self.dashboard:
                source_short = result.source_url.split('/')[-1] if '/' in result.source_url else result.source_url
                
                if vr.status == KeyStatus.VALID:
                    self.dashboard.add_valid_key(
                        platform=result.platform,
                        masked_key=masked,
                        balance=balance_str,
                        source=source_short,
                        is_high_value=vr.is_high_value
                    )
                    level = "VALID" if not vr.is_high_value else "HIGH"
                    self._log(f"✓ 有效! {vr.model_tier or result.platform.upper()} {masked}", level)
                
                elif vr.status == KeyStatus.QUOTA_EXCEEDED:
                    self.dashboard.add_valid_key(
                        platform=result.platform,
                        masked_key=masked,
                        balance=f"配额耗尽",
                        source=source_short
                    )
                    self.dashboard.increment_stat("quota_exceeded")
                    self._log(f"⚠ 配额耗尽 {masked}", "WARN")
                
                elif vr.status == KeyStatus.CONNECTION_ERROR:
                    self.dashboard.increment_stat("connection_errors")
                    self._log(f"✗ 连接失败 {masked}", "ERROR")
                
                else:
                    self.dashboard.increment_stat("invalid_keys")
    
    async def run_batch(self, results: list):
        """批量验证"""
        tasks = [self.process_result(r) for r in results]
        await asyncio.gather(*tasks, return_exceptions=True)


# ============================================================================
#                              辅助函数
# ============================================================================

# ScanResult 导入（延迟导入避免循环依赖）
def get_scan_result_class():
    from scanner import ScanResult
    return ScanResult


async def run_validator_loop(
    result_queue: 'asyncio.Queue',
    db: Database,
    stop_event: 'asyncio.Event',
    dashboard = None
):
    """运行异步验证循环"""
    validator = AsyncValidator(db, dashboard)
    
    try:
        while not stop_event.is_set():
            try:
                # 批量获取队列中的任务
                batch = []
                try:
                    while len(batch) < 50:  # 每批最多 50 个
                        result = result_queue.get_nowait()
                        batch.append(result)
                except asyncio.QueueEmpty:
                    pass
                
                if batch:
                    if dashboard:
                        dashboard.update_stats(queue_size=result_queue.qsize())
                    await validator.run_batch(batch)
                else:
                    await asyncio.sleep(0.5)
                    
            except Exception as e:
                if dashboard:
                    dashboard.add_log(f"验证错误: {str(e)[:30]}", "ERROR")
                await asyncio.sleep(1)
    finally:
        await validator.close()


# ============================================================================
#                          同步包装器（兼容 threading）
# ============================================================================

import queue as sync_queue


def _validator_thread_worker(
    result_queue: sync_queue.Queue,
    db: Database,
    stop_event: threading.Event,
    dashboard = None
):
    """
    验证器线程工作函数
    
    在线程中运行 asyncio 事件循环，实现真正的异步验证
    """
    async def async_worker():
        validator = AsyncValidator(db, dashboard)
        try:
            while not stop_event.is_set():
                try:
                    # 批量获取队列中的任务
                    batch = []
                    try:
                        while len(batch) < 50:
                            result = result_queue.get_nowait()
                            batch.append(result)
                    except sync_queue.Empty:
                        pass
                    
                    if batch:
                        if dashboard:
                            dashboard.update_stats(queue_size=result_queue.qsize())
                        await validator.run_batch(batch)
                    else:
                        await asyncio.sleep(0.3)
                        
                except Exception as e:
                    if dashboard:
                        dashboard.add_log(f"验证错误: {str(e)[:30]}", "ERROR")
                    await asyncio.sleep(1)
        finally:
            await validator.close()
    
    # 在新的事件循环中运行
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(async_worker())
    finally:
        loop.close()


def start_validators(
    result_queue: sync_queue.Queue,
    db: Database,
    stop_event: threading.Event,
    dashboard = None,
    num_workers: int = 1
) -> list:
    """
    启动验证器线程
    
    注意：由于使用了 100 并发的 asyncio.Semaphore，
    实际上只需要 1 个线程即可处理 100 并发请求。
    多线程模式下每个线程独立运行自己的事件循环。
    
    Args:
        result_queue: 结果队列（同步）
        db: 数据库实例
        stop_event: 停止事件
        dashboard: UI 仪表盘
        num_workers: 工作线程数（建议 1-2，因为内部是 100 并发）
    
    Returns:
        线程列表
    """
    threads = []
    
    # 实际上 1 个线程 + 100 并发已足够，但保留多线程接口兼容性
    actual_workers = min(num_workers, 2)  # 最多 2 个，避免资源浪费
    
    for i in range(actual_workers):
        thread = threading.Thread(
            target=_validator_thread_worker,
            args=(result_queue, db, stop_event, dashboard),
            name=f"AsyncValidator-{i}",
            daemon=True
        )
        thread.start()
        threads.append(thread)
    
    if dashboard:
        dashboard.add_log(f"启动 {actual_workers} 个异步验证器 (100 并发/个)", "INFO")

    return threads


# ============================================================================
#                          v2.1 优化版导出
# ============================================================================

# 导出优化版验证器（使用连接池和智能重试）
try:
    from validator_optimized import OptimizedAsyncValidator
    __all__ = ['AsyncValidator', 'OptimizedAsyncValidator', 'start_validators',
               'ValidationResult', 'CircuitBreaker', 'circuit_breaker', 'mask_key',
               'MAX_CONCURRENCY', 'REQUEST_TIMEOUT', 'HIGH_VALUE_MODELS',
               'RPM_ENTERPRISE_THRESHOLD', 'RPM_FREE_TRIAL_THRESHOLD']
except ImportError:
    # 如果优化模块不可用，只导出原版
    __all__ = ['AsyncValidator', 'start_validators', 'ValidationResult',
               'CircuitBreaker', 'circuit_breaker', 'mask_key',
               'MAX_CONCURRENCY', 'REQUEST_TIMEOUT', 'HIGH_VALUE_MODELS',
               'RPM_ENTERPRISE_THRESHOLD', 'RPM_FREE_TRIAL_THRESHOLD']
    logger.warning("v2.1 优化模块不可用，使用原版验证器")
