"""
FOFA Integration - Expand Search Sources

FOFA (https://fofa.info) is a cyberspace search engine similar to Shodan.
Integrate FOFA API to expand API key discovery sources beyond GitHub.
"""

import requests
import base64
import time
from typing import List, Dict, Optional
from loguru import logger


class FOFASearcher:
    """FOFA API integration for finding exposed API keys"""

    def __init__(self, email: str = "", api_key: str = ""):
        """
        Initialize FOFA searcher

        Args:
            email: FOFA account email
            api_key: FOFA API key (get from https://fofa.info/userInfo)
        """
        self.email = email
        self.api_key = api_key
        self.base_url = "https://fofa.info/api/v1/search/all"

    def is_configured(self) -> bool:
        """Check if FOFA credentials are configured"""
        return bool(self.email and self.api_key)

    def search(self, query: str, page: int = 1, size: int = 100) -> Optional[Dict]:
        """
        Search FOFA with query

        Args:
            query: FOFA search query (e.g., 'body="OPENAI_API_KEY"')
            page: Page number (starts from 1)
            size: Results per page (max 10000)

        Returns:
            Search results dict or None on error
        """
        if not self.is_configured():
            logger.warning("FOFA credentials not configured, skipping FOFA search")
            return None

        # Encode query to base64
        qbase64 = base64.b64encode(query.encode()).decode()

        params = {
            'email': self.email,
            'key': self.api_key,
            'qbase64': qbase64,
            'page': page,
            'size': size,
            'fields': 'host,ip,port,protocol,domain,title,body',
        }

        try:
            response = requests.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if data.get('error'):
                logger.error(f"FOFA API error: {data.get('errmsg')}")
                return None

            return data

        except requests.RequestException as e:
            logger.error(f"FOFA request failed: {e}")
            return None

    def search_api_keys(self, platform: str = "openai", max_results: int = 1000) -> List[Dict]:
        """
        Search for exposed API keys on FOFA

        Args:
            platform: Platform to search (openai, anthropic, etc.)
            max_results: Maximum results to fetch

        Returns:
            List of found results
        """
        # Build FOFA query based on platform
        queries = self._build_queries(platform)

        all_results = []
        for query in queries:
            logger.info(f"FOFA search: {query}")

            page = 1
            size = min(100, max_results)

            while len(all_results) < max_results:
                result = self.search(query, page=page, size=size)

                if not result or not result.get('results'):
                    break

                results = result['results']
                all_results.extend(results)

                logger.info(f"FOFA found {len(results)} results (total: {len(all_results)})")

                # Check if there are more pages
                if len(results) < size:
                    break

                page += 1
                time.sleep(1)  # Rate limiting

                if len(all_results) >= max_results:
                    break

        return all_results[:max_results]

    def _build_queries(self, platform: str) -> List[str]:
        """
        Build FOFA search queries for specific platform

        Args:
            platform: Platform name

        Returns:
            List of FOFA query strings
        """
        if platform == "openai":
            return [
                'body="OPENAI_API_KEY" && body="sk-"',
                'body="openai.api_key" && body="sk-"',
                'body="Authorization: Bearer sk-"',
                'title="config" && body="sk-proj-"',
                'body="OPENAI_BASE_URL" && body="sk-"',
            ]

        elif platform == "anthropic":
            return [
                'body="ANTHROPIC_API_KEY" && body="sk-ant-"',
                'body="anthropic.api_key"',
                'body="x-api-key" && body="sk-ant-"',
            ]

        elif platform == "gemini":
            return [
                'body="GOOGLE_API_KEY" && body="AIza"',
                'body="GEMINI_API_KEY"',
                'body="generativelanguage.googleapis.com"',
            ]

        elif platform == "all":
            # Aggregate queries for multiple platforms
            all_queries = []
            for p in ["openai", "anthropic", "gemini"]:
                all_queries.extend(self._build_queries(p))
            return all_queries

        else:
            # Generic API key patterns
            return [
                f'body="{platform.upper()}_API_KEY"',
                f'body="{platform}_api_key"',
            ]

    def extract_keys_from_results(self, results: List[Dict], patterns: Dict) -> List[Dict]:
        """
        Extract API keys from FOFA search results

        Args:
            results: FOFA search results
            patterns: Regex patterns dict (from config.REGEX_PATTERNS)

        Returns:
            List of extracted keys with metadata
        """
        import re

        extracted = []

        for result in results:
            if not result or len(result) < 7:
                continue

            host, ip, port, protocol, domain, title, body = result

            # Search for API keys in body content
            for platform, pattern in patterns.items():
                if platform == "azure":
                    continue

                for match in re.finditer(pattern, body):
                    api_key = match.group(0)

                    extracted.append({
                        'platform': platform,
                        'api_key': api_key,
                        'source': 'fofa',
                        'source_url': f"{protocol}://{host}:{port}",
                        'domain': domain,
                        'title': title,
                        'ip': ip,
                    })

        return extracted


def test_fofa():
    """Test FOFA integration"""
    print("FOFA Integration Test")
    print("=" * 60)

    # Example usage (requires FOFA account)
    fofa = FOFASearcher(
        email="your-email@example.com",
        api_key="your-fofa-api-key"
    )

    if not fofa.is_configured():
        print("⚠️  FOFA not configured")
        print("\nTo use FOFA:")
        print("1. Register at https://fofa.info")
        print("2. Get API key from https://fofa.info/userInfo")
        print("3. Configure in config_local.py:")
        print("   FOFA_EMAIL = 'your-email@example.com'")
        print("   FOFA_API_KEY = 'your-api-key'")
        return

    # Test search
    print("\nSearching FOFA for OpenAI keys...")
    results = fofa.search_api_keys(platform="openai", max_results=10)

    print(f"\nFound {len(results)} results")
    for i, r in enumerate(results[:3], 1):
        print(f"\n{i}. {r.get('source_url')}")
        print(f"   Platform: {r.get('platform')}")
        print(f"   Domain: {r.get('domain')}")


if __name__ == "__main__":
    test_fofa()
