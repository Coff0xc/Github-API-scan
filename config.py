"""
Configuration Module - Centralized Configuration Management

This module provides:
- Proxy configuration (optional, for restricted networks)
- GitHub Token pool (multi-token rotation for rate limit bypass)
- Regex pattern library (50+ AI platforms)
- Default platform URLs
"""

import os
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, FrozenSet


# ============================================================================
#                          Circuit Breaker Configuration
# ============================================================================

# Protected domain whitelist - never circuit-break these domains
PROTECTED_DOMAINS: FrozenSet[str] = frozenset({
    # Official APIs
    "api.openai.com",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
    # Azure domain suffix
    "openai.azure.com",
    # GitHub file downloads
    "github.com",
    "raw.githubusercontent.com",
})

# Application-layer error HTTP status codes - DO NOT trigger circuit breaker
# (These indicate server is reachable but request is invalid)
SAFE_HTTP_STATUS_CODES: FrozenSet[int] = frozenset({
    400,  # Bad Request - malformed request
    401,  # Unauthorized - invalid key
    403,  # Forbidden - insufficient permissions
    404,  # Not Found - endpoint doesn't exist
    422,  # Unprocessable Entity - invalid parameters
    429,  # Rate Limit - throttled
})

# Gateway error HTTP status codes - TRIGGER circuit breaker
# (These indicate service is unavailable)
CIRCUIT_BREAKER_HTTP_CODES: FrozenSet[int] = frozenset({
    502,  # Bad Gateway
    503,  # Service Unavailable
    504,  # Gateway Timeout
})

# Circuit breaker parameters
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5   # Consecutive failures before opening circuit
CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 60   # Circuit recovery timeout (seconds)
CIRCUIT_BREAKER_HALF_OPEN_REQUESTS = 3  # Number of probe requests in half-open state


# ============================================================================
#                              Regex Pattern Library
# ============================================================================

REGEX_PATTERNS = {
    # ============================================================================
    #                          Major AI Platforms (2026 Update)
    # ============================================================================

    # OpenAI: GPT-5/4o series - sk-proj-xxx (project keys), sk-svcacct-xxx (service accounts)
    "openai": r'sk-(?:proj-|svcacct-)?[a-zA-Z0-9]{32,}',

    # Google Gemini 2.0: AIza prefix
    "gemini": r'AIza[0-9A-Za-z\-_]{35,39}',

    # Anthropic Claude 5/Opus 4.8: sk-ant-api03- prefix
    "anthropic": r'sk-ant-api0[0-9]-[a-zA-Z0-9\-_]{20,}',

    # Azure OpenAI: 32-character hexadecimal
    "azure": r'[a-f0-9]{32}',

    # ============================================================================
    #                          Mainstream AI Platforms (2026)
    # ============================================================================

    # xAI Grok (Elon Musk): xai- prefix
    "xai": r'xai-[a-zA-Z0-9]{40,64}',

    # Meta Llama API: llama- prefix
    "meta_llama": r'llama-[a-zA-Z0-9]{32,64}',

    # HuggingFace: hf_ prefix
    "huggingface": r'hf_[a-zA-Z0-9]{34,}',

    # Groq (Llama 3.1/3.3): gsk_ prefix
    "groq": r'gsk_[a-zA-Z0-9]{52}',

    # DeepSeek V3: sk- prefix, 48+ characters
    "deepseek": r'sk-[a-fA-F0-9]{48,64}',

    # Moonshot AI (Kimi): moonshot- prefix
    "moonshot": r'moonshot-[a-zA-Z0-9]{32,64}',

    # Zhipu AI (GLM-4): zhipu- or glm- prefix
    "zhipu": r'(?:zhipu|glm)-[a-zA-Z0-9]{32,64}',

    # Baichuan AI: baichuan- prefix
    "baichuan": r'baichuan-[a-zA-Z0-9]{32,64}',

    # MiniMax: minimax- prefix
    "minimax": r'minimax-[a-zA-Z0-9]{32,64}',

    # Cohere Command R+: co- prefix
    "cohere": r'co-[a-zA-Z0-9]{40,64}',

    # Mistral Large 2: 32-64 characters
    "mistral": r'[a-zA-Z0-9]{32,64}',

    # Together AI: 64-character hexadecimal
    "together": r'[a-fA-F0-9]{64}',

    # ============================================================================
    #                          AI Aggregators & Gateways (2026)
    # ============================================================================

    # OpenRouter (largest aggregator): sk-or- prefix
    "openrouter": r'sk-or-v1-[a-fA-F0-9]{64}',

    # AI Gateway / Cloudflare Workers AI: generic format
    "cloudflare_ai": r'[a-fA-F0-9]{32}',

    # Portkey (enterprise AI gateway): pk- prefix
    "portkey": r'pk-[a-zA-Z0-9]{40,}',

    # LiteLLM Proxy: custom format, usually sk- prefix
    "litellm": r'sk-[a-zA-Z0-9]{32,}',

    # ============================================================================
    #                          Cloud Provider AI APIs (2026)
    # ============================================================================

    # AWS Bedrock (Claude/Llama): AKIA prefix Access Key
    "aws_bedrock": r'AKIA[0-9A-Z]{16}',

    # Alibaba Cloud Bailian (Qwen/Tongyi): LTAI prefix
    "aliyun_bailian": r'LTAI[a-zA-Z0-9]{16,32}',

    # Volcano Engine (Doubao): volc- prefix
    "volcengine": r'volc-[a-zA-Z0-9]{32,64}',

    # Tencent Cloud Hunyuan: AKID prefix
    "tencent_hunyuan": r'AKID[a-zA-Z0-9]{32,48}',

    # Baidu Qianfan: typically contains access_token field
    "baidu_qianfan": r'24\.[a-zA-Z0-9]{32,}',

    # Google Cloud Vertex AI: ya29. prefix OAuth token
    "vertex_ai": r'ya29\.[a-zA-Z0-9\-_]{100,}',

    # Azure AI Services (non-OpenAI): 32-character hexadecimal
    "azure_ai": r'[a-fA-F0-9]{32}',

    # ============================================================================
    #                          Open Source Inference Platforms
    # ============================================================================

    # Replicate (open source model hosting): r8_ prefix
    "replicate": r'r8_[a-zA-Z0-9]{37,}',

    # Modal (GPU cloud): generic format
    "modal": r'modal-[a-zA-Z0-9]{32,}',

    # RunPod (GPU rental): generic format
    "runpod": r'[a-zA-Z0-9]{32,64}',

    # Baseten: 64-character hexadecimal
    "baseten": r'[a-fA-F0-9]{64}',

    # Perplexity: pplx- prefix
    "perplexity": r'pplx-[a-zA-Z0-9]{48,}',

    # Fireworks AI: fw_ prefix
    "fireworks": r'fw_[a-zA-Z0-9]{40,}',

    # ============================================================================
    #                          Enterprise AI Platforms
    # ============================================================================

    # Cohere Command R+: co- prefix
    "cohere": r'co-[a-zA-Z0-9]{40,64}',

    # AI21 Labs (Jamba): generic format
    "ai21": r'[a-zA-Z0-9]{40,64}',

    # Writer (enterprise LLM): wr- prefix
    "writer": r'wr-[a-zA-Z0-9]{32,}',

    # Forefront AI: ff- prefix
    "forefront": r'ff-[a-zA-Z0-9]{32,}',

    # ============================================================================
    #                          Regional AI Platform Additions
    # ============================================================================

    # SenseTime: sensetime- prefix
    "sensetime": r'sensetime-[a-zA-Z0-9]{32,}',

    # iFlytek Spark: xf- prefix
    "xunfei_spark": r'xf-[a-zA-Z0-9]{32,}',

    # Kunlun Tiangong: tiangong- prefix
    "tiangong": r'tiangong-[a-zA-Z0-9]{32,}',

    # Yi AI (01.AI): yi- prefix
    "lingyiwanwu": r'yi-[a-zA-Z0-9]{32,}',

    # StepFun: step- prefix
    "stepfun": r'step-[a-zA-Z0-9]{32,}',

    # ============================================================================
    #                          Generic Cloud Service APIs
    # ============================================================================

    # AWS Access Key: AKIA prefix, 20 characters
    "aws_access_key": r'AKIA[0-9A-Z]{16}',

    # AWS Secret Key: 40-character Base64
    "aws_secret_key": r'(?<!test)(?<!example)[A-Za-z0-9/+=]{40}(?=.*(?:aws|secret|key))',

    # GitHub Token: ghp_, gho_, ghu_, ghs_, ghr_ prefix
    "github_token": r'(?:ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9]{36,}',

    # Stripe: sk_live_ or rk_live_ prefix
    "stripe": r'(?:sk|rk)_live_[a-zA-Z0-9]{24,}',

    # Twilio: SK prefix, 32 characters
    "twilio": r'SK[a-f0-9]{32}',

    # SendGrid: SG. prefix
    "sendgrid": r'SG\.[a-zA-Z0-9\-_]{22,}\.[a-zA-Z0-9\-_]{22,}',

    # Slack: xox[baprs]- prefix
    "slack": r'xox[baprs]-[0-9]{10,}-[0-9]{10,}-[a-zA-Z0-9]{24,}',

    # Discord Bot Token
    "discord": r'[MN][A-Za-z\d]{23,}\.[\w-]{6}\.[\w-]{27}',

    # Telegram Bot Token
    "telegram": r'\d{8,10}:[a-zA-Z0-9_-]{35}',
}

# Azure feature recognition regex
AZURE_URL_PATTERN = r'https://[\w\-]+\.openai\.azure\.com'
AZURE_CONTEXT_KEYWORDS = ['azure', 'openai.azure.com', 'azure_endpoint', 'AZURE_OPENAI']

# Base URL extraction regex (for context-aware detection)
BASE_URL_PATTERNS = [
    # URL assignment with variable names
    r'(?:base_url|api_base|OPENAI_API_BASE|OPENAI_BASE_URL|host|endpoint|api_endpoint|API_URL|proxy_url|PROXY)\s*[=:]\s*["\']?(https?://[^\s"\'<>]+)["\']?',
    # Generic HTTP URL
    r'(https?://[a-zA-Z0-9\-_.]+(?::\d+)?(?:/[a-zA-Z0-9\-_./]*)?)',
]

# URL keyword priority (for sorting extracted URLs)
URL_PRIORITY_KEYWORDS = ['base', 'api', 'host', 'endpoint', 'proxy', 'openai', 'relay']


# ============================================================================
#                              Configuration Class
# ============================================================================

@dataclass
class Config:
    """
    Global Configuration Class

    Important settings:
    - proxy_url: Proxy address (optional, for restricted networks)
    - github_tokens: GitHub Token list (required for scanning)
    """

    # ==================== Proxy Configuration ====================
    # Direct mode (no proxy)
    # To use proxy, set PROXY_URL environment variable or modify here
    proxy_url: str = field(
        default_factory=lambda: os.getenv("PROXY_URL", "")  # Direct mode
    )

    # ==================== GitHub Token Pool ====================
    # Multi-token rotation effectively bypasses rate limits
    # Unauthenticated: 10 requests/min, Authenticated: 30 requests/min
    # Multiple tokens can significantly increase scanning speed
    #
    # Configuration methods:
    # 1. Add tokens directly to this list (not recommended, may leak)
    # 2. Set GITHUB_TOKENS environment variable (recommended, comma-separated)
    # 3. Create config_local.py to override this config (recommended)
    github_tokens: List[str] = field(default_factory=lambda: (
        # Read from environment variable first
        os.getenv("GITHUB_TOKENS", "").split(",") if os.getenv("GITHUB_TOKENS") else [
            # ===== Empty by default, configure via environment or config_local.py =====
            # Example format:
            # "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            # "ghp_yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy",
        ]
    ))

    # Token rotation index
    _token_index: int = 0

    # ==================== Database Configuration ====================
    db_path: str = "leaked_keys.db"

    # ==================== Pastebin Configuration ====================
    # Pastebin Pro API Key (optional, for Scraping API)
    # Free users can skip this, but scanning efficiency will be lower
    pastebin_api_key: str = field(
        default_factory=lambda: os.getenv("PASTEBIN_API_KEY", "")
    )

    # ==================== Thread Configuration ====================
    consumer_threads: int = 20  # Validator thread count (IO-intensive, can increase)

    # ==================== Network Configuration ====================
    request_timeout: int = 15  # HTTP request timeout (seconds)

    # ==================== Circuit Breaker Configuration ====================
    circuit_breaker_enabled: bool = True  # Enable circuit breaker

    # ==================== Scan Configuration ====================
    context_window: int = 10  # Context window (N lines before/after)

    # Search keywords - 2026 High-Precision Sniper Mode v3.0
    # Strategy: Precise filename + new platform coverage + exclude test files
    search_keywords: List[str] = field(default_factory=lambda: [
        # ============================================================================
        #                          1. OpenAI GPT-5/4o Series (Ultra Fresh - Today)
        # ============================================================================
        'filename:.env OPENAI_API_KEY -test -example created:>2026-07-23',
        'filename:.env.production OPENAI_API_KEY created:>2026-07-23',
        'sk-proj- language:python -test -example created:>2026-07-23 forks:<5',
        'sk-proj- language:javascript -test -example created:>2026-07-23 forks:<5',
        '"Authorization: Bearer sk-proj-" -test created:>2026-07-23',
        'OPENAI_API_KEY=sk- -test created:>2026-07-23 stars:0..10',

        # ============================================================================
        #                          2. Anthropic Claude 5/Opus 4.8
        # ============================================================================
        'filename:.env ANTHROPIC_API_KEY -test -example',
        'filename:.env.production ANTHROPIC_API_KEY',
        'sk-ant-api03 -test -example',
        '"x-api-key: sk-ant-" -test',
        'CLAUDE_API_KEY language:python -test',

        # ============================================================================
        #                          3. Google Gemini 2.0
        # ============================================================================
        'filename:.env GEMINI_API_KEY -test -example',
        'AIzaSy language:python -test -example',
        'generativelanguage.googleapis.com -test',
        'GOOGLE_AI_API_KEY language:javascript -test',

        # ============================================================================
        #                          4. xAI Grok (2026 New)
        # ============================================================================
        'filename:.env XAI_API_KEY -test -example',
        'filename:.env GROK_API_KEY -test',
        'xai- language:python -test -example',
        'api.x.ai -test -example',
        'X_AI_API_KEY language:javascript -test',

        # ============================================================================
        #                          5. Meta Llama API (2026 Commercial)
        # ============================================================================
        'filename:.env META_API_KEY -test -example',
        'filename:.env LLAMA_API_KEY -test',
        'llama- language:python -test',
        'meta.ai/api -test',

        # ============================================================================
        #                          6. Azure OpenAI
        # ============================================================================
        'filename:.env AZURE_OPENAI_API_KEY -test -example',
        'openai.azure.com -test -example',
        'AZURE_OPENAI_ENDPOINT language:python -test',

        # ============================================================================
        #                          7. AI Aggregators/Gateways (Important!)
        # ============================================================================
        'filename:.env OPENROUTER_API_KEY -test -example',
        'sk-or-v1- language:python -test',
        'openrouter.ai -test',
        'filename:.env PORTKEY_API_KEY -test',
        'filename:.env LITELLM_KEY -test',
        'filename:cloudflare-workers AI_GATEWAY -test',

        # ============================================================================
        #                          8. Cloud Provider AI APIs (Important!)
        # ============================================================================
        # AWS Bedrock
        'filename:.env AWS_ACCESS_KEY_ID -test -example',
        'filename:.env AWS_SECRET_ACCESS_KEY -test',
        'bedrock-runtime language:python -test',
        'boto3.client("bedrock-runtime") -test',

        # Alibaba Cloud Bailian
        'filename:.env DASHSCOPE_API_KEY -test -example',
        'dashscope.aliyuncs.com -test',
        'ALIBABA_CLOUD_ACCESS_KEY language:python -test',

        # Volcano Engine (Doubao)
        'filename:.env VOLC_API_KEY -test -example',
        'ark.cn-beijing.volces.com -test',

        # Tencent Cloud Hunyuan
        'filename:.env TENCENT_SECRET_ID -test -example',
        'hunyuan.tencentcloudapi.com -test',

        # Baidu Qianfan
        'filename:.env QIANFAN_ACCESS_KEY -test',
        'aip.baidubce.com -test',

        # Google Vertex AI
        'filename:.env GOOGLE_APPLICATION_CREDENTIALS -test',
        'aiplatform.googleapis.com -test',

        # ============================================================================
        #                          9. Regional AI Platforms (2026 Mainstream)
        # ============================================================================
        # DeepSeek V3
        'filename:.env DEEPSEEK_API_KEY -test -example',
        'api.deepseek.com -test',

        # Moonshot AI (Kimi)
        'filename:.env MOONSHOT_API_KEY -test -example',
        'api.moonshot.cn -test',

        # Zhipu AI (GLM-4)
        'filename:.env ZHIPU_API_KEY -test -example',
        'open.bigmodel.cn -test',

        # Yi AI (01.AI)
        'filename:.env YI_API_KEY -test',
        'api.lingyiwanwu.com -test',

        # StepFun
        'filename:.env STEPFUN_API_KEY -test',
        'api.stepfun.com -test',

        # iFlytek Spark
        'filename:.env SPARK_API_KEY -test',
        'spark-api.xf-yun.com -test',

        # ============================================================================
        #                          10. API Proxies / One-API / New-API
        # ============================================================================
        'filename:.env OPENAI_BASE_URL -test -example',
        'one-api sk- -test',
        'new-api sk- -test',
        'openai-sb.com -test',
        'api2d.com -test',

        # ============================================================================
        #                          11. HuggingFace & Open Source Inference
        # ============================================================================
        'filename:.env HF_TOKEN -test -example',
        'hf_ language:python -test -example',
        'filename:.env REPLICATE_API_TOKEN -test',
        'r8_ language:python -test',
        'filename:.env MODAL_TOKEN -test',
        'filename:.env RUNPOD_API_KEY -test',

        # ============================================================================
        #                          12. Groq (Llama 3.3)
        # ============================================================================
        'filename:.env GROQ_API_KEY -test -example',
        'gsk_ language:python -test',

        # ============================================================================
        #                          13. Other International AI Platforms
        # ============================================================================
        'filename:.env COHERE_API_KEY -test',
        'filename:.env MISTRAL_API_KEY -test',
        'filename:.env PERPLEXITY_API_KEY -test',
        'pplx- language:python -test',
        'filename:.env AI21_API_KEY -test',
        'filename:.env WRITER_API_KEY -test',

        # ============================================================================
        #                          14. Other Cloud Service APIs
        # ============================================================================
        'filename:.env GITHUB_TOKEN -test',
        'ghp_ language:python -test',
        'filename:.env STRIPE_SECRET_KEY -test',
        'sk_live_ -test',

        # ============================================================================
        #                          15. High-Value File Paths (2026 Container/IaC)
        # ============================================================================
        'path:deploy/ .env -test',
        'path:production/ .env -test',
        'filename:docker-compose.yml API_KEY -test',
        'filename:Dockerfile ENV OPENAI -test',
        'filename:kubernetes.yaml secret -test',
        'filename:.github/workflows/ API_KEY -test',
        'filename:terraform.tfvars API_KEY -test',
        'filename:pulumi secret -test',
        'path:.gitlab-ci.yml API_KEY -test',
        'path:Jenkinsfile credentials -test',
    ])
    
    # ==================== Platform Default URLs (2026 Comprehensive Update) ====================
    default_base_urls: Dict[str, str] = field(default_factory=lambda: {
        # ============ Major AI Platforms ============
        "openai": "https://api.openai.com/v1",
        "gemini": "https://generativelanguage.googleapis.com/v1beta",
        "anthropic": "https://api.anthropic.com/v1",
        "azure": "",
        "xai": "https://api.x.ai/v1",
        "meta_llama": "https://api.meta.ai/v1",

        # ============ AI Aggregators/Gateways ============
        "openrouter": "https://openrouter.ai/api/v1",
        "cloudflare_ai": "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run",
        "portkey": "https://api.portkey.ai/v1",
        "litellm": "http://localhost:4000",  # Local deployment

        # ============ Cloud Provider AI APIs ============
        "aws_bedrock": "https://bedrock-runtime.{region}.amazonaws.com",
        "aliyun_bailian": "https://dashscope.aliyuncs.com/api/v1",
        "volcengine": "https://ark.cn-beijing.volces.com/api/v3",
        "tencent_hunyuan": "https://hunyuan.tencentcloudapi.com",
        "baidu_qianfan": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1",
        "vertex_ai": "https://{region}-aiplatform.googleapis.com/v1",
        "azure_ai": "https://{endpoint}.cognitiveservices.azure.com",

        # ============ Regional AI Platforms ============
        "deepseek": "https://api.deepseek.com/v1",
        "moonshot": "https://api.moonshot.cn/v1",
        "zhipu": "https://open.bigmodel.cn/api/paas/v4",
        "baichuan": "https://api.baichuan-ai.com/v1",
        "minimax": "https://api.minimax.chat/v1",
        "sensetime": "https://api.sensenova.cn/v1",
        "xunfei_spark": "https://spark-api.xf-yun.com/v1",
        "tiangong": "https://sky-api.singularity-ai.com/v1",
        "lingyiwanwu": "https://api.lingyiwanwu.com/v1",
        "stepfun": "https://api.stepfun.com/v1",

        # ============ International AI Platforms ============
        "huggingface": "https://api-inference.huggingface.co",
        "groq": "https://api.groq.com/openai/v1",
        "cohere": "https://api.cohere.ai/v1",
        "mistral": "https://api.mistral.ai/v1",
        "together": "https://api.together.xyz/v1",
        "replicate": "https://api.replicate.com/v1",
        "perplexity": "https://api.perplexity.ai",
        "fireworks": "https://api.fireworks.ai/inference/v1",
        "ai21": "https://api.ai21.com/studio/v1",
        "writer": "https://api.writer.com/v1",
        "forefront": "https://api.forefront.ai/v1",

        # ============ Open Source Inference Platforms ============
        "modal": "https://api.modal.com/v1",
        "runpod": "https://api.runpod.io/v2",
        "baseten": "https://model-{model_id}.api.baseten.co/production/predict",

        # ============ Generic Cloud Services ============
        "aws_access_key": "",
        "aws_secret_key": "",
        "github_token": "https://api.github.com",
        "stripe": "https://api.stripe.com",
    })

    @property
    def proxies(self) -> Optional[Dict[str, str]]:
        """Return requests proxy format"""
        if self.proxy_url:
            return {"http": self.proxy_url, "https": self.proxy_url}
        return None

    def get_token(self) -> str:
        """Get current token"""
        if not self.github_tokens:
            return ""
        return self.github_tokens[self._token_index % len(self.github_tokens)]

    def rotate_token(self) -> str:
        """Rotate to next token"""
        if not self.github_tokens:
            return ""
        self._token_index = (self._token_index + 1) % len(self.github_tokens)
        return self.github_tokens[self._token_index]

    def get_random_token(self) -> str:
        """Get random token"""
        if not self.github_tokens:
            return ""
        return random.choice(self.github_tokens)


# Global configuration instance
config = Config()

# ============================================================================
#                          Local Configuration Override (config_local.py)
# ============================================================================
# Try to import local config file to override default settings
# config_local.py should contain real tokens and sensitive config
# This file is in .gitignore and won't be committed to Git
try:
    from config_local import *

    # Update config if config_local.py defines GITHUB_TOKENS
    if 'GITHUB_TOKENS' in dir():
        config.github_tokens = GITHUB_TOKENS

    # Update config if PROXY_URL is defined
    if 'PROXY_URL' in dir() and PROXY_URL:
        config.proxy_url = PROXY_URL

    # Update other config items if defined
    if 'DB_PATH' in dir():
        config.db_path = DB_PATH
    if 'CONSUMER_THREADS' in dir():
        config.consumer_threads = CONSUMER_THREADS
    if 'REQUEST_TIMEOUT' in dir():
        config.request_timeout = REQUEST_TIMEOUT

    # Pastebin API Key
    if 'PASTEBIN_API_KEY' in dir():
        config.pastebin_api_key = PASTEBIN_API_KEY

    print("[OK] Loaded local config file: config_local.py")
except ImportError:
    # config_local.py doesn't exist, use default config
    if not config.github_tokens or not any(config.github_tokens):
        print("[WARNING] GitHub Tokens not configured!")
        print("   Please create config_local.py file or set GITHUB_TOKENS environment variable")
        print("   Reference: config_local.py.example")
except Exception as e:
    print(f"[WARNING] Error loading config_local.py: {e}")

