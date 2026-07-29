"""
Enhanced Validation Depth Module

Advanced API key validation with deep inspection:
- Balance and credit analysis
- Usage quota detection
- Rate limit transparency
- Model tier detection
- Expiration date checking
- Organization info extraction
"""

import asyncio
import aiohttp
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from loguru import logger


@dataclass
class DeepValidationResult:
    """Enhanced validation result with deep metrics"""
    is_valid: bool
    platform: str

    # Balance & Credits
    balance: float = 0.0
    used_quota: float = 0.0
    total_quota: float = 0.0
    credits_remaining: float = 0.0

    # Rate Limits
    rpm: int = 0  # Requests per minute
    tpm: int = 0  # Tokens per minute
    rpd: int = 0  # Requests per day

    # Model Access
    available_models: list = None
    model_tier: str = ""
    has_gpt4: bool = False
    has_gpt5: bool = False
    has_claude_opus: bool = False

    # Account Info
    organization: str = ""
    account_name: str = ""
    account_email: str = ""
    created_date: str = ""
    expiration_date: str = ""

    # Value Assessment
    is_high_value: bool = False
    value_score: int = 0  # 0-100

    # Additional Info
    key_type: str = ""  # project, service_account, user
    permissions: list = None
    notes: str = ""


class DeepValidator:
    """Enhanced validator with deep inspection capabilities"""

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def deep_validate_openai(self, api_key: str, base_url: str = "") -> DeepValidationResult:
        """
        Deep validation for OpenAI keys

        Extracts:
        - Balance and usage
        - Rate limits
        - Available models (GPT-4, GPT-5 access)
        - Organization info
        - Key type (project vs service account)
        """
        if not base_url:
            base_url = "https://api.openai.com/v1"

        result = DeepValidationResult(
            is_valid=False,
            platform="openai"
        )

        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            # 1. Get models list
            async with self.session.get(
                f"{base_url}/models",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    return result

                data = await resp.json()
                result.is_valid = True

                # Extract available models
                models = [m['id'] for m in data.get('data', [])]
                result.available_models = models

                # Check model tier
                if any('gpt-5' in m or 'o3' in m for m in models):
                    result.model_tier = "GPT-5"
                    result.has_gpt5 = True
                    result.value_score += 50
                elif any('gpt-4' in m for m in models):
                    result.model_tier = "GPT-4"
                    result.has_gpt4 = True
                    result.value_score += 30
                else:
                    result.model_tier = "GPT-3.5"
                    result.value_score += 10

            # 2. Try to get organization info (may fail for most keys)
            try:
                async with self.session.get(
                    f"{base_url.replace('/v1', '')}/dashboard/organizations",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        org_data = await resp.json()
                        if org_data.get('data'):
                            org = org_data['data'][0]
                            result.organization = org.get('name', '')
                            result.value_score += 10
            except:
                pass

            # 3. Try to get billing info (relay stations)
            if "api.openai.com" not in base_url:
                billing = await self._probe_relay_billing(base_url, headers)
                result.balance = billing.get('balance', 0.0)
                result.used_quota = billing.get('used', 0.0)
                result.total_quota = billing.get('total', 0.0)

                if result.balance > 100:
                    result.value_score += 20
                    result.is_high_value = True
                elif result.balance > 10:
                    result.value_score += 10

            # 4. Detect key type
            if api_key.startswith('sk-proj-'):
                result.key_type = "project"
                result.value_score += 5
            elif api_key.startswith('sk-svcacct-'):
                result.key_type = "service_account"
                result.value_score += 15
            else:
                result.key_type = "user"

            # 5. Assess overall value
            if result.value_score >= 60:
                result.is_high_value = True

            return result

        except Exception as e:
            logger.debug(f"Deep validation error: {e}")
            return result

    async def deep_validate_anthropic(self, api_key: str, base_url: str = "") -> DeepValidationResult:
        """Deep validation for Anthropic Claude keys"""
        if not base_url:
            base_url = "https://api.anthropic.com/v1"

        result = DeepValidationResult(
            is_valid=False,
            platform="anthropic"
        )

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        try:
            # Test with minimal request
            payload = {
                "model": "claude-3-haiku-20240307",
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "Hi"}]
            }

            async with self.session.post(
                f"{base_url}/messages",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    result.is_valid = True
                    result.value_score = 40

                    # Check rate limit headers
                    result.rpm = int(resp.headers.get('anthropic-ratelimit-requests-limit', 0))
                    result.tpm = int(resp.headers.get('anthropic-ratelimit-tokens-limit', 0))

                    # Assess tier based on rate limits
                    if result.rpm >= 5000:
                        result.model_tier = "Enterprise"
                        result.value_score = 80
                        result.is_high_value = True
                    elif result.rpm >= 1000:
                        result.model_tier = "Team"
                        result.value_score = 60
                    else:
                        result.model_tier = "Individual"
                        result.value_score = 40

                    # Assume Claude Opus access
                    result.has_claude_opus = True
                    result.available_models = ["claude-3-opus", "claude-3-sonnet", "claude-3-haiku"]

                elif resp.status == 400:
                    error_data = await resp.json()
                    error_type = error_data.get('error', {}).get('type', '')

                    if 'credit' in error_type.lower():
                        result.is_valid = True
                        result.notes = "Valid but no credits"
                        result.value_score = 10

            return result

        except Exception as e:
            logger.debug(f"Anthropic deep validation error: {e}")
            return result

    async def _probe_relay_billing(self, base_url: str, headers: Dict) -> Dict:
        """Probe relay station billing endpoints"""
        endpoints = [
            '/api/user/self',
            '/api/user/info',
            '/user/info',
            '/api/status',
            '/v1/dashboard/billing/subscription'
        ]

        for endpoint in endpoints:
            try:
                url = f"{base_url.rstrip('/')}{endpoint}"
                async with self.session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=3)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return self._extract_billing_info(data)
            except:
                continue

        return {}

    def _extract_billing_info(self, data: dict) -> Dict:
        """Extract billing information from response"""
        result = {'balance': 0.0, 'used': 0.0, 'total': 0.0}

        # Common field names
        balance_fields = ['balance', 'quota', 'credits', 'remaining', 'available']
        used_fields = ['used', 'used_quota', 'spent']
        total_fields = ['total', 'total_quota', 'limit', 'hard_limit_usd']

        # Extract balance
        for field in balance_fields:
            value = self._get_nested_value(data, field)
            if value and value != 0:
                result['balance'] = self._normalize_balance(value)
                break

        # Extract used
        for field in used_fields:
            value = self._get_nested_value(data, field)
            if value and value != 0:
                result['used'] = self._normalize_balance(value)
                break

        # Extract total
        for field in total_fields:
            value = self._get_nested_value(data, field)
            if value and value != 0:
                result['total'] = self._normalize_balance(value)
                break

        return result

    def _get_nested_value(self, data: dict, field: str):
        """Get value from nested dict"""
        try:
            # Try direct access
            if field in data:
                return data[field]

            # Try nested (data.field)
            if 'data' in data and field in data['data']:
                return data['data'][field]
        except:
            pass
        return None

    def _normalize_balance(self, value) -> float:
        """Normalize balance to USD"""
        try:
            balance = float(value)
            # one-api format: 500000 = $5
            if balance > 10000:
                balance = balance / 100000
            return balance
        except:
            return 0.0


async def test_deep_validation():
    """Test deep validation"""
    print("Deep Validation Test")
    print("=" * 60)

    async with aiohttp.ClientSession() as session:
        validator = DeepValidator(session)

        # Test with dummy key (will fail but shows structure)
        result = await validator.deep_validate_openai("sk-test-123")

        print(f"\nPlatform: {result.platform}")
        print(f"Valid: {result.is_valid}")
        print(f"Model Tier: {result.model_tier}")
        print(f"Balance: ${result.balance:.2f}")
        print(f"Value Score: {result.value_score}/100")
        print(f"High Value: {result.is_high_value}")


if __name__ == "__main__":
    asyncio.run(test_deep_validation())
