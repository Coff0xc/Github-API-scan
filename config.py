"""
配置模块 - 集中管理所有配置项

本模块提供：
- 代理配置（必需，中国大陆环境）
- GitHub Token 池（多 Token 轮询）
- 正则表达式库
- 平台默认 URL
"""

import os
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, FrozenSet


# ============================================================================
#                          熍断器配置 (Circuit Breaker)
# ============================================================================

# 受保护域名白名单 - 永远不会被熍断
PROTECTED_DOMAINS: FrozenSet[str] = frozenset({
    # 官方 API
    "api.openai.com",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
    # Azure 域名后缀
    "openai.azure.com",
    # GitHub 文件下载
    "github.com",
    "raw.githubusercontent.com",
})

# 应用层错误 HTTP 状态码 - 不触发熍断（说明服务器连通性正常）
SAFE_HTTP_STATUS_CODES: FrozenSet[int] = frozenset({
    400,  # Bad Request - 请求格式错误
    401,  # Unauthorized - Key 无效
    403,  # Forbidden - 权限不足
    404,  # Not Found - 端点不存在
    422,  # Unprocessable Entity - 请求参数错误
    429,  # Rate Limit - 被限流
})

# 网关错误 HTTP 状态码 - 触发熍断（说明服务不可用）
CIRCUIT_BREAKER_HTTP_CODES: FrozenSet[int] = frozenset({
    502,  # Bad Gateway
    503,  # Service Unavailable
    504,  # Gateway Timeout
})

# 熍断器参数
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5   # 连续失败次数阈值
CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 60   # 熍断恢复时间（秒）
CIRCUIT_BREAKER_HALF_OPEN_REQUESTS = 3  # 半开状态允许的试探请求数


# ============================================================================
#                              正则表达式库
# ============================================================================

REGEX_PATTERNS = {
    # ============================================================================
    #                          主流 AI 平台 (高优先级)
    # ============================================================================

    # OpenAI: 标准 key (sk-xxx) 和 project key (sk-proj-xxx)
    # 新格式: sk-proj-xxx (项目 Key), sk-svcacct-xxx (服务账户)
    "openai": r'(?<!example_)(?<!test_)(?<!demo_)(?<!fake_)(?<!sample_)(?<!dev_)(?<!staging_)sk-(?:proj-|svcacct-)?(?!(?:placeholder|example|test|demo|your|xxx|fake|sample|dev|staging|sandbox|xxxxxx|abcdef|123456|insert|replace))[a-zA-Z0-9\-_]{20,}',

    # Google Gemini / Google AI Studio: AIza 开头，39 字符
    "gemini": r'(?<!test)(?<!example)(?<!sample)(?<!dev)AIza[0-9A-Za-z\-_]{35}',

    # Anthropic Claude: sk-ant- 开头
    "anthropic": r'(?<!example_)(?<!test_)(?<!dev_)(?<!staging_)sk-ant-(?!(?:api0|xxx|test|demo|example|sample|dev|staging|sandbox|placeholder))[a-zA-Z0-9\-_]{20,}',

    # Azure OpenAI: 32位十六进制
    "azure": r'(?<![a-f0-9])(?!0{32})(?!f{32})(?!a{32})(?!e{32})[a-f0-9]{32}(?![a-f0-9])',

    # ============================================================================
    #                          新兴 AI 平台 (中优先级)
    # ============================================================================

    # HuggingFace: hf_ 开头
    "huggingface": r'hf_[a-zA-Z0-9]{34,}',

    # Groq: gsk_ 开头，52字符
    "groq": r'gsk_[a-zA-Z0-9]{52}',

    # DeepSeek: sk- 开头，48+ 字符 (与 OpenAI 区分靠长度)
    "deepseek": r'sk-[a-zA-Z0-9]{48,}',

    # Cohere: 40字符 Base64
    "cohere": r'(?<!test)(?<!example)[a-zA-Z0-9]{40}(?=.*cohere)',

    # Mistral AI: 32字符
    "mistral": r'(?<!test)(?<!example)[a-zA-Z0-9]{32}(?=.*mistral)',

    # Together AI: 64字符十六进制
    "together": r'[a-f0-9]{64}(?=.*together)',

    # Replicate: r8_ 开头
    "replicate": r'r8_[a-zA-Z0-9]{37,}',

    # Perplexity: pplx- 开头
    "perplexity": r'pplx-[a-zA-Z0-9]{48,}',

    # Fireworks AI: fw_ 开头
    "fireworks": r'fw_[a-zA-Z0-9]{40,}',

    # Anyscale: esecret_ 开头
    "anyscale": r'esecret_[a-zA-Z0-9]{40,}',

    # ============================================================================
    #                          云服务商 API (低优先级)
    # ============================================================================

    # AWS Access Key: AKIA 开头，20字符
    "aws_access_key": r'AKIA[0-9A-Z]{16}',

    # AWS Secret Key: 40字符 Base64
    "aws_secret_key": r'(?<!test)(?<!example)[A-Za-z0-9/+=]{40}(?=.*(?:aws|secret|key))',

    # GitHub Token: ghp_, gho_, ghu_, ghs_, ghr_ 开头
    "github_token": r'(?:ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9]{36,}',

    # Stripe: sk_live_ 或 rk_live_ 开头
    "stripe": r'(?:sk|rk)_live_[a-zA-Z0-9]{24,}',

    # Twilio: SK 开头，32字符
    "twilio": r'SK[a-f0-9]{32}',

    # SendGrid: SG. 开头
    "sendgrid": r'SG\.[a-zA-Z0-9\-_]{22,}\.[a-zA-Z0-9\-_]{22,}',

    # Slack: xox[baprs]- 开头
    "slack": r'xox[baprs]-[0-9]{10,}-[0-9]{10,}-[a-zA-Z0-9]{24,}',

    # Discord Bot Token
    "discord": r'[MN][A-Za-z\d]{23,}\.[\w-]{6}\.[\w-]{27}',

    # Telegram Bot Token
    "telegram": r'\d{8,10}:[a-zA-Z0-9_-]{35}',
}

# Azure 特征识别正则
AZURE_URL_PATTERN = r'https://[\w\-]+\.openai\.azure\.com'
AZURE_CONTEXT_KEYWORDS = ['azure', 'openai.azure.com', 'azure_endpoint', 'AZURE_OPENAI']

# Base URL 提取正则（用于上下文感知）
BASE_URL_PATTERNS = [
    # 带变量名的 URL 赋值
    r'(?:base_url|api_base|OPENAI_API_BASE|OPENAI_BASE_URL|host|endpoint|api_endpoint|API_URL|proxy_url|PROXY)\s*[=:]\s*["\']?(https?://[^\s"\'<>]+)["\']?',
    # 通用 HTTP URL
    r'(https?://[a-zA-Z0-9\-_.]+(?::\d+)?(?:/[a-zA-Z0-9\-_./]*)?)',
]

# URL 关键词优先级（用于排序提取到的 URL）
URL_PRIORITY_KEYWORDS = ['base', 'api', 'host', 'endpoint', 'proxy', 'openai', 'relay']


# ============================================================================
#                              配置类
# ============================================================================

@dataclass
class Config:
    """
    全局配置类
    
    重要配置项：
    - proxy_url: 代理地址（中国大陆必需）
    - github_tokens: GitHub Token 列表
    """
    
    # ==================== 代理配置 ====================
    # 直连模式（无代理）
    # 如需代理，可设置环境变量 PROXY_URL 或直接修改此处
    proxy_url: str = field(
        default_factory=lambda: os.getenv("PROXY_URL", "")  # 直连模式
    )
    
    # ==================== GitHub Token 池 ====================
    # 多 Token 轮询可有效规避速率限制
    # 未认证: 10次/分钟, 认证: 30次/分钟
    # 多个 Token 可大幅提升扫描速度
    # 
    # 配置方式：
    # 1. 直接在此列表中添加 token（不推荐，易泄露）
    # 2. 设置环境变量 GITHUB_TOKENS（推荐，用逗号分隔多个token）
    # 3. 创建 config_local.py 覆盖此配置（推荐）
    github_tokens: List[str] = field(default_factory=lambda: (
        # 优先从环境变量读取
        os.getenv("GITHUB_TOKENS", "").split(",") if os.getenv("GITHUB_TOKENS") else [
            # ===== 默认为空，请通过环境变量或 config_local.py 配置 =====
            # 示例格式：
            # "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            # "ghp_yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy",
        ]
    ))
    
    # Token 轮询索引
    _token_index: int = 0
    
    # ==================== 数据库配置 ====================
    db_path: str = "leaked_keys.db"

    # ==================== Pastebin 配置 ====================
    # Pastebin Pro API Key (可选，用于 Scraping API)
    # 免费用户可以不配置，但扫描效率较低
    pastebin_api_key: str = field(
        default_factory=lambda: os.getenv("PASTEBIN_API_KEY", "")
    )
    
    # ==================== 线程配置 ====================
    consumer_threads: int = 20  # 验证器线程数（IO 密集型，可开多）
    
    # ==================== 网络配置 ====================
    request_timeout: int = 15  # HTTP 请求超时（秒）
    
    # ==================== 熍断器配置 ====================
    circuit_breaker_enabled: bool = True  # 是否启用熍断器
    
    # ==================== 扫描配置 ====================
    context_window: int = 10  # 上下文窗口（前后各 N 行）
    
    # 搜索关键词 - 高精度狙击模式 (Sniper Dorks) v2.0
    # 策略: 精准文件名 + 排除测试/示例 + 多平台覆盖
    search_keywords: List[str] = field(default_factory=lambda: [
        # ============================================================================
        #                          1. OpenAI 高价值目标
        # ============================================================================
        'filename:.env OPENAI_API_KEY NOT staging NOT sandbox NOT example',
        'filename:.env.local OPENAI_API_KEY NOT test',
        'filename:.env.production OPENAI_API_KEY',
        'filename:.env.prod OPENAI_API_KEY',
        'filename:secrets.yaml openai_api_key NOT example',
        'filename:secrets.json OPENAI_API_KEY NOT test',
        'filename:config.json sk-proj- NOT example NOT test',
        'sk-proj- language:python NOT test NOT example NOT mock NOT staging',
        'sk-proj- language:javascript NOT test NOT example NOT mock',
        '"Authorization: Bearer sk-" NOT test NOT example',
        'OPENAI_API_KEY= sk- NOT test NOT example NOT staging',

        # ============================================================================
        #                          2. Anthropic Claude
        # ============================================================================
        'filename:.env ANTHROPIC_API_KEY NOT staging NOT example',
        'filename:.env CLAUDE_API_KEY NOT sandbox NOT test',
        'filename:.env.production ANTHROPIC_API_KEY',
        'sk-ant-api03 NOT test NOT example NOT staging',
        '"x-api-key" sk-ant- NOT test NOT example',
        'anthropic_api_key language:python NOT test NOT example',

        # ============================================================================
        #                          3. Google Gemini / AI Studio
        # ============================================================================
        'filename:.env GEMINI_API_KEY NOT test NOT example',
        'filename:.env GOOGLE_AI_KEY NOT staging',
        'AIzaSy language:json NOT example NOT test NOT dev',
        'AIzaSy language:python NOT test NOT example',
        'generativelanguage.googleapis.com key= NOT test',

        # ============================================================================
        #                          4. Azure OpenAI
        # ============================================================================
        'filename:.env AZURE_OPENAI_API_KEY NOT staging NOT example',
        'filename:.env AZURE_OPENAI_KEY NOT test',
        'openai.azure.com api-key NOT example NOT test NOT staging',
        'AZURE_OPENAI_ENDPOINT language:python NOT test',

        # ============================================================================
        #                          5. 中转站 / One-API / New-API
        # ============================================================================
        'filename:.env OPENAI_BASE_URL NOT sandbox NOT example',
        'filename:.env BASE_URL openai NOT staging NOT test',
        'filename:config.py ONEAPI NOT test',
        'filename:config.py one-api NOT example',
        'new-api sk- NOT test NOT demo NOT example',
        'one-api sk- NOT test NOT demo',
        'api.openai-proxy sk- NOT test',

        # ============================================================================
        #                          6. HuggingFace
        # ============================================================================
        'filename:.env HUGGINGFACE_API_KEY NOT test NOT example',
        'filename:.env HF_TOKEN NOT staging',
        'filename:.env HUGGINGFACE_TOKEN NOT test',
        'hf_ language:python NOT test NOT example NOT mock',
        '"Authorization: Bearer hf_" NOT test',

        # ============================================================================
        #                          7. Groq
        # ============================================================================
        'filename:.env GROQ_API_KEY NOT test NOT example',
        'gsk_ language:python NOT test NOT example',
        'api.groq.com Authorization NOT test',

        # ============================================================================
        #                          8. DeepSeek
        # ============================================================================
        'filename:.env DEEPSEEK_API_KEY NOT test NOT example',
        'api.deepseek.com sk- NOT test NOT example',
        'deepseek language:python sk- NOT test',

        # ============================================================================
        #                          9. 新兴 AI 平台
        # ============================================================================
        # Cohere
        'filename:.env COHERE_API_KEY NOT test NOT example',
        'cohere.ai api-key NOT test',

        # Mistral
        'filename:.env MISTRAL_API_KEY NOT test NOT example',
        'api.mistral.ai NOT test NOT example',

        # Together AI
        'filename:.env TOGETHER_API_KEY NOT test',
        'api.together.xyz NOT test NOT example',

        # Replicate
        'filename:.env REPLICATE_API_TOKEN NOT test',
        'r8_ language:python NOT test NOT example',

        # Perplexity
        'filename:.env PERPLEXITY_API_KEY NOT test',
        'pplx- language:python NOT test',

        # Fireworks
        'filename:.env FIREWORKS_API_KEY NOT test',
        'fw_ language:python NOT test NOT example',

        # ============================================================================
        #                          10. 云服务商 API
        # ============================================================================
        # AWS
        'filename:.env AWS_ACCESS_KEY_ID NOT test NOT example NOT staging',
        'filename:.env AWS_SECRET_ACCESS_KEY NOT test NOT example',
        'AKIA language:python NOT test NOT example NOT mock',

        # GitHub Token
        'filename:.env GITHUB_TOKEN NOT test NOT example',
        'ghp_ language:python NOT test NOT example NOT mock',

        # Stripe
        'filename:.env STRIPE_SECRET_KEY NOT test NOT example',
        'sk_live_ NOT test NOT example NOT staging',

        # Twilio
        'filename:.env TWILIO_AUTH_TOKEN NOT test NOT example',

        # SendGrid
        'filename:.env SENDGRID_API_KEY NOT test NOT example',
        'SG. language:python NOT test NOT example',

        # ============================================================================
        #                          11. 高价值文件路径
        # ============================================================================
        'path:deploy/ .env NOT test NOT example',
        'path:production/ .env NOT staging',
        'path:config/ secrets NOT test NOT example',
        'path:scripts/ api_key NOT test NOT example',
        'filename:docker-compose.yml OPENAI NOT test',
        'filename:docker-compose.yml API_KEY NOT example',
        'filename:Dockerfile ENV OPENAI NOT test',
    ])
    
    # ==================== 平台默认 URL ====================
    default_base_urls: Dict[str, str] = field(default_factory=lambda: {
        # 主流 AI 平台
        "openai": "https://api.openai.com",
        "gemini": "https://generativelanguage.googleapis.com/v1beta",
        "anthropic": "https://api.anthropic.com",
        "azure": "",
        # 新兴 AI 平台
        "huggingface": "https://api-inference.huggingface.co",
        "groq": "https://api.groq.com/openai/v1",
        "deepseek": "https://api.deepseek.com",
        "cohere": "https://api.cohere.ai/v1",
        "mistral": "https://api.mistral.ai/v1",
        "together": "https://api.together.xyz/v1",
        "replicate": "https://api.replicate.com/v1",
        "perplexity": "https://api.perplexity.ai",
        "fireworks": "https://api.fireworks.ai/inference/v1",
        "anyscale": "https://api.endpoints.anyscale.com/v1",
        # 云服务商
        "aws_access_key": "",
        "aws_secret_key": "",
        "github_token": "https://api.github.com",
        "stripe": "https://api.stripe.com",
        "twilio": "https://api.twilio.com",
        "sendgrid": "https://api.sendgrid.com",
        "slack": "https://slack.com/api",
        "discord": "https://discord.com/api",
        "telegram": "https://api.telegram.org",
    })
    
    @property
    def proxies(self) -> Optional[Dict[str, str]]:
        """返回 requests 代理格式"""
        if self.proxy_url:
            return {"http": self.proxy_url, "https": self.proxy_url}
        return None
    
    def get_token(self) -> str:
        """获取当前 Token"""
        if not self.github_tokens:
            return ""
        return self.github_tokens[self._token_index % len(self.github_tokens)]
    
    def rotate_token(self) -> str:
        """轮换到下一个 Token"""
        if not self.github_tokens:
            return ""
        self._token_index = (self._token_index + 1) % len(self.github_tokens)
        return self.github_tokens[self._token_index]
    
    def get_random_token(self) -> str:
        """随机获取一个 Token"""
        if not self.github_tokens:
            return ""
        return random.choice(self.github_tokens)


# 全局配置实例
config = Config()

# ============================================================================
#                          本地配置覆盖 (config_local.py)
# ============================================================================
# 尝试导入本地配置文件以覆盖默认设置
# config_local.py 应该包含真实的 tokens 和敏感配置
# 该文件已被 .gitignore 忽略，不会被提交到 Git
try:
    from config_local import *
    
    # 如果 config_local.py 定义了 GITHUB_TOKENS，更新配置
    if 'GITHUB_TOKENS' in dir():
        config.github_tokens = GITHUB_TOKENS
    
    # 如果定义了 PROXY_URL，更新配置
    if 'PROXY_URL' in dir() and PROXY_URL:
        config.proxy_url = PROXY_URL
    
    # 如果定义了其他配置项，也可以在此更新
    if 'DB_PATH' in dir():
        config.db_path = DB_PATH
    if 'CONSUMER_THREADS' in dir():
        config.consumer_threads = CONSUMER_THREADS
    if 'REQUEST_TIMEOUT' in dir():
        config.request_timeout = REQUEST_TIMEOUT

    # Pastebin API Key
    if 'PASTEBIN_API_KEY' in dir():
        config.pastebin_api_key = PASTEBIN_API_KEY

    print("[OK] 已加载本地配置文件 config_local.py")
except ImportError:
    # config_local.py 不存在，使用默认配置
    if not config.github_tokens or not any(config.github_tokens):
        print("[WARNING] 警告: 未配置 GitHub Tokens！")
        print("   请创建 config_local.py 文件或设置环境变量 GITHUB_TOKENS")
        print("   参考: config_local.py.example")
except Exception as e:
    print(f"[WARNING] 加载 config_local.py 时出错: {e}")
