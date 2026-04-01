"""
扩展正则表达式库 - 30+ 平台密钥识别
=====================================

参考: https://github.com/streaak/keyhacks
      https://github.com/l4yton/RegHex

使用方法:
    from regex_extended import EXTENDED_REGEX_PATTERNS, merge_with_base_patterns

    # 合并到基础配置
    all_patterns = merge_with_base_patterns(base_patterns)
"""

from typing import Dict, List, Tuple
import re


# ============================================================================
#                              扩展正则表达式
# ============================================================================

EXTENDED_REGEX_PATTERNS: Dict[str, str] = {
    # ========================================================================
    #                       通信/消息平台
    # ========================================================================

    # Slack Token (xoxb-*, xoxp-*, xoxa-*, xoxr-*)
    "slack_token": r'xox[baprs]-(?:[0-9]{10,13}-){2,3}[a-zA-Z0-9]{24,}',

    # Slack Webhook
    "slack_webhook": r'https://hooks\.slack\.com/services/T[A-Z0-9]{8,}/B[A-Z0-9]{8,}/[a-zA-Z0-9]{24}',

    # Discord Bot Token (改进版)
    "discord_token": r'[MN][A-Za-z\d]{23,}\.[\w-]{6}\.[\w-]{27,}',

    # Discord Webhook
    "discord_webhook": r'https://discord(?:app)?\.com/api/webhooks/\d{17,20}/[\w-]{60,}',

    # Telegram Bot Token (改进版)
    "telegram_bot": r'\d{8,10}:[a-zA-Z0-9_-]{35}',

    # Twilio Account SID
    "twilio_sid": r'AC[a-f0-9]{32}',

    # Twilio Auth Token
    "twilio_auth": r'(?<=twilio)(?:[^a-zA-Z0-9]){0,20}[a-f0-9]{32}',

    # SendGrid API Key
    "sendgrid": r'SG\.[a-zA-Z0-9\-_]{22,}\.[a-zA-Z0-9\-_]{22,}',

    # Mailgun API Key
    "mailgun": r'key-[a-zA-Z0-9]{32}',

    # Mailchimp API Key
    "mailchimp": r'[a-f0-9]{32}-us\d{1,2}',

    # Postmark Server Token
    "postmark": r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}',

    # ========================================================================
    #                       云服务商
    # ========================================================================

    # DigitalOcean Token
    "digitalocean": r'dop_v1_[a-f0-9]{64}',

    # DigitalOcean OAuth (旧格式)
    "digitalocean_oauth": r'(?<!test)(?<!example)[a-f0-9]{64}(?=.*digitalocean)',

    # Heroku API Key
    "heroku": r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}(?=.*heroku)',

    # Cloudflare API Token
    "cloudflare_token": r'(?:^|[^a-zA-Z0-9])[a-zA-Z0-9_-]{40}(?=.*cloudflare)',

    # Cloudflare Global API Key
    "cloudflare_global": r'[a-f0-9]{37}(?=.*cloudflare)',

    # Vercel Token
    "vercel": r'[a-zA-Z0-9]{24}(?=.*vercel)',

    # Linode API Token
    "linode": r'[a-f0-9]{64}(?=.*linode)',

    # Vultr API Key
    "vultr": r'[A-Z0-9]{36}(?=.*vultr)',

    # ========================================================================
    #                       开发工具
    # ========================================================================

    # GitLab Personal Access Token
    "gitlab_pat": r'glpat-[a-zA-Z0-9\-_]{20,}',

    # GitLab Pipeline Token
    "gitlab_pipeline": r'glpt-[a-zA-Z0-9]{20,}',

    # GitLab Runner Token
    "gitlab_runner": r'GR1348941[a-zA-Z0-9\-_]{20}',

    # Bitbucket App Password (需要上下文)
    "bitbucket": r'[a-zA-Z0-9]{20,}(?=.*bitbucket)',

    # CircleCI Token
    "circleci": r'circle(?:ci)?[_-]?(?:token|api)[^a-zA-Z0-9]*[a-f0-9]{40}',

    # Travis CI Token
    "travis_ci": r'travis[_-]?(?:ci)?[_-]?(?:token|api)[^a-zA-Z0-9]*[a-zA-Z0-9]{22}',

    # NPM Token
    "npm_token": r'npm_[a-zA-Z0-9]{36}',

    # NPM Auth Token (旧格式)
    "npm_auth": r'//registry\.npmjs\.org/:_authToken=[a-zA-Z0-9\-_]+',

    # PyPI API Token
    "pypi": r'pypi-[a-zA-Z0-9_-]{100,}',

    # RubyGems API Key
    "rubygems": r'rubygems_[a-f0-9]{48}',

    # NuGet API Key
    "nuget": r'oy2[a-z0-9]{43}',

    # Docker Hub Access Token
    "docker_hub": r'dckr_pat_[a-zA-Z0-9_-]{27,}',

    # ========================================================================
    #                       监控/APM
    # ========================================================================

    # Datadog API Key
    "datadog_api": r'[a-f0-9]{32}(?=.*datadog)',

    # Datadog Application Key
    "datadog_app": r'[a-f0-9]{40}(?=.*datadog)',

    # Sentry Auth Token
    "sentry": r'sntrys_[a-zA-Z0-9]{58,}',

    # Sentry DSN
    "sentry_dsn": r'https://[a-f0-9]{32}@[a-z0-9]+\.ingest\.sentry\.io/\d+',

    # New Relic API Key
    "newrelic_api": r'NRAK-[A-Z0-9]{27}',

    # New Relic License Key
    "newrelic_license": r'[a-f0-9]{40}NRAL',

    # New Relic Browser Key
    "newrelic_browser": r'NRJS-[a-f0-9]{19}',

    # PagerDuty API Key (v1)
    "pagerduty": r'[a-zA-Z0-9+]{20}(?=.*pagerduty)',

    # PagerDuty Integration Key
    "pagerduty_integration": r'[a-f0-9]{32}(?=.*pagerduty)',

    # Elastic APM Secret Token
    "elastic_apm": r'[a-zA-Z0-9]{32,}(?=.*elastic)',

    # Splunk HEC Token
    "splunk_hec": r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}(?=.*splunk)',

    # ========================================================================
    #                       协作工具
    # ========================================================================

    # Notion Integration Token
    "notion": r'secret_[a-zA-Z0-9]{43}',

    # Linear API Key
    "linear": r'lin_api_[a-zA-Z0-9]{40}',

    # Asana Personal Access Token
    "asana": r'1/\d{16,}:[a-f0-9]{32}',

    # Airtable API Key
    "airtable": r'key[a-zA-Z0-9]{14}',

    # Airtable Personal Access Token
    "airtable_pat": r'pat[a-zA-Z0-9]{14}\.[a-f0-9]{64}',

    # Atlassian API Token (需要上下文)
    "atlassian": r'[a-zA-Z0-9]{24}(?=.*atlassian|jira|confluence)',

    # Trello API Key
    "trello": r'[a-f0-9]{32}(?=.*trello)',

    # Monday.com API Token
    "monday": r'eyJhbGciOiJIUzI1NiJ9\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+',

    # ClickUp API Token
    "clickup": r'pk_\d+_[A-Z0-9]{32}',

    # ========================================================================
    #                       分析平台
    # ========================================================================

    # Segment Write Key
    "segment": r'[a-zA-Z0-9]{32}(?=.*segment)',

    # Mixpanel Token
    "mixpanel": r'[a-f0-9]{32}(?=.*mixpanel)',

    # Amplitude API Key
    "amplitude": r'[a-f0-9]{32}(?=.*amplitude)',

    # Algolia API Key
    "algolia_api": r'[a-f0-9]{32}(?=.*algolia)',

    # Algolia Admin Key
    "algolia_admin": r'[a-f0-9]{32}(?=.*algolia.*admin)',

    # Google Analytics Measurement ID
    "ga_measurement": r'G-[A-Z0-9]{10}',

    # Google Analytics Tracking ID
    "ga_tracking": r'UA-\d{4,10}-\d{1,4}',

    # FullStory Org ID
    "fullstory": r'o-[A-Z0-9]+-na1',

    # Hotjar Site ID
    "hotjar": r'\d{7}(?=.*hotjar)',

    # ========================================================================
    #                       客服/CRM
    # ========================================================================

    # Zendesk API Token (需要上下文)
    "zendesk": r'[a-zA-Z0-9]{40}(?=.*zendesk)',

    # Intercom Access Token
    "intercom": r'dG9rO[a-zA-Z0-9_-]{50,}',

    # Freshdesk API Key (需要上下文)
    "freshdesk": r'[a-zA-Z0-9]{20}(?=.*freshdesk)',

    # HubSpot API Key
    "hubspot": r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}(?=.*hubspot)',

    # HubSpot Private App Token
    "hubspot_pat": r'pat-na1-[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}',

    # Salesforce Security Token (需要上下文)
    "salesforce": r'[a-zA-Z0-9]{24}(?=.*salesforce)',

    # ========================================================================
    #                       地图服务
    # ========================================================================

    # Mapbox Access Token
    "mapbox": r'pk\.[a-zA-Z0-9]{60,}\.[a-zA-Z0-9]{22}',

    # Mapbox Secret Token
    "mapbox_secret": r'sk\.[a-zA-Z0-9]{60,}\.[a-zA-Z0-9]{22}',

    # Google Maps API Key (改进版)
    "google_maps": r'AIza[0-9A-Za-z\-_]{35}',

    # HERE API Key
    "here": r'[a-zA-Z0-9_-]{43}(?=.*here\.com)',

    # TomTom API Key
    "tomtom": r'[a-zA-Z0-9]{32}(?=.*tomtom)',

    # ========================================================================
    #                       支付平台
    # ========================================================================

    # Stripe Secret Key (改进版)
    "stripe_secret": r'sk_live_[a-zA-Z0-9]{24,}',

    # Stripe Publishable Key
    "stripe_publishable": r'pk_live_[a-zA-Z0-9]{24,}',

    # Stripe Restricted Key
    "stripe_restricted": r'rk_live_[a-zA-Z0-9]{24,}',

    # Stripe Test Keys
    "stripe_test": r'[sr]k_test_[a-zA-Z0-9]{24,}',

    # PayPal Client ID (需要上下文)
    "paypal_client": r'A[a-zA-Z0-9_-]{79}(?=.*paypal)',

    # Square Access Token
    "square": r'sq0atp-[a-zA-Z0-9_-]{22}',

    # Square Application ID
    "square_app": r'sq0idp-[a-zA-Z0-9_-]{22}',

    # Braintree Access Token
    "braintree": r'access_token\$production\$[a-z0-9]{16}\$[a-f0-9]{32}',

    # Adyen API Key
    "adyen": r'AQE[a-zA-Z0-9]{10,}',

    # ========================================================================
    #                       社交媒体
    # ========================================================================

    # Twitter API Key
    "twitter_api": r'[a-zA-Z0-9]{25}(?=.*twitter)',

    # Twitter Bearer Token
    "twitter_bearer": r'AAAAAAAAAAAAAAAAAAA[a-zA-Z0-9%]+',

    # Facebook Access Token
    "facebook": r'EAA[a-zA-Z0-9]{100,}',

    # Instagram Access Token (类似 Facebook)
    "instagram": r'IGQV[a-zA-Z0-9_-]{100,}',

    # LinkedIn Client ID (需要上下文)
    "linkedin": r'[a-z0-9]{14}(?=.*linkedin)',

    # YouTube API Key (同 Google)
    "youtube": r'AIza[0-9A-Za-z\-_]{35}',

    # ========================================================================
    #                       存储服务
    # ========================================================================

    # AWS Access Key ID (改进版)
    "aws_access": r'(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}',

    # AWS Secret Access Key
    "aws_secret": r'(?<!test)(?<!example)[A-Za-z0-9/+=]{40}(?=.*(?:aws|secret|key))',

    # AWS Session Token
    "aws_session": r'FwoGZXIvYXdzE[a-zA-Z0-9/+=]+',

    # Google Cloud Service Account Key
    "gcp_service_account": r'"type"\s*:\s*"service_account"',

    # Azure Storage Account Key
    "azure_storage": r'[a-zA-Z0-9+/]{86}==',

    # Azure Shared Access Signature
    "azure_sas": r'sv=\d{4}-\d{2}-\d{2}&s[a-z]=.*&sig=[a-zA-Z0-9%/+=]+',

    # Firebase Database URL
    "firebase_db": r'https://[a-z0-9-]+\.firebaseio\.com',

    # Supabase Anon Key
    "supabase": r'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+',

    # PlanetScale Database URL
    "planetscale": r'mysql://[a-z0-9]+:[a-zA-Z0-9]+@[a-z0-9.-]+\.psdb\.cloud/[a-zA-Z0-9_-]+',

    # MongoDB Connection String
    "mongodb": r'mongodb(?:\+srv)?://[a-zA-Z0-9:._@%/-]+',

    # Redis URL
    "redis": r'redis://[a-zA-Z0-9:._@%/-]+',

    # ========================================================================
    #                       其他服务
    # ========================================================================

    # Shopify Access Token
    "shopify_access": r'shpat_[a-f0-9]{32}',

    # Shopify Shared Secret
    "shopify_secret": r'shpss_[a-f0-9]{32}',

    # Okta API Token
    "okta": r'00[a-zA-Z0-9_-]{40}(?=.*okta)',

    # Auth0 API Token (需要上下文)
    "auth0": r'[a-zA-Z0-9]{32,}(?=.*auth0)',

    # JWT Token (通用)
    "jwt": r'eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}',

    # Private Key (PEM)
    "private_key_pem": r'-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----',

    # SSH Private Key
    "ssh_private_key": r'-----BEGIN OPENSSH PRIVATE KEY-----',

    # PGP Private Key
    "pgp_private_key": r'-----BEGIN PGP PRIVATE KEY BLOCK-----',

    # Generic API Key Pattern (高熵值)
    "generic_api_key": r'(?:api[_-]?key|apikey|secret[_-]?key|auth[_-]?token)["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_-]{20,})["\']?',
}


# ============================================================================
#                              高优先级模式（直接匹配）
# ============================================================================

HIGH_PRIORITY_PATTERNS = [
    # 格式明确，无需上下文
    "slack_token",
    "slack_webhook",
    "discord_token",
    "discord_webhook",
    "telegram_bot",
    "twilio_sid",
    "sendgrid",
    "mailgun",
    "mailchimp",
    "digitalocean",
    "gitlab_pat",
    "gitlab_pipeline",
    "gitlab_runner",
    "npm_token",
    "pypi",
    "rubygems",
    "nuget",
    "docker_hub",
    "sentry",
    "sentry_dsn",
    "newrelic_api",
    "newrelic_license",
    "newrelic_browser",
    "notion",
    "linear",
    "asana",
    "airtable",
    "airtable_pat",
    "hubspot_pat",
    "mapbox",
    "mapbox_secret",
    "stripe_secret",
    "stripe_publishable",
    "stripe_restricted",
    "square",
    "square_app",
    "braintree",
    "adyen",
    "twitter_bearer",
    "facebook",
    "instagram",
    "aws_access",
    "shopify_access",
    "shopify_secret",
    "private_key_pem",
    "ssh_private_key",
    "pgp_private_key",
]


# ============================================================================
#                              上下文相关模式
# ============================================================================

CONTEXT_REQUIRED_PATTERNS = [
    # 需要上下文关键词才能准确匹配
    "twilio_auth",
    "digitalocean_oauth",
    "heroku",
    "cloudflare_token",
    "cloudflare_global",
    "vercel",
    "linode",
    "vultr",
    "bitbucket",
    "circleci",
    "travis_ci",
    "datadog_api",
    "datadog_app",
    "pagerduty",
    "pagerduty_integration",
    "elastic_apm",
    "splunk_hec",
    "atlassian",
    "trello",
    "segment",
    "mixpanel",
    "amplitude",
    "algolia_api",
    "algolia_admin",
    "hotjar",
    "zendesk",
    "freshdesk",
    "hubspot",
    "salesforce",
    "here",
    "tomtom",
    "paypal_client",
    "twitter_api",
    "linkedin",
    "aws_secret",
    "okta",
    "auth0",
]


# ============================================================================
#                              工具函数
# ============================================================================

def merge_with_base_patterns(base_patterns: Dict[str, str]) -> Dict[str, str]:
    """
    合并扩展模式到基础模式

    Args:
        base_patterns: 基础正则模式字典

    Returns:
        合并后的模式字典
    """
    merged = base_patterns.copy()

    for name, pattern in EXTENDED_REGEX_PATTERNS.items():
        # 避免覆盖已有的核心模式
        if name not in merged:
            merged[name] = pattern

    return merged


def get_high_priority_patterns() -> Dict[str, str]:
    """获取高优先级模式（无需上下文）"""
    return {
        name: EXTENDED_REGEX_PATTERNS[name]
        for name in HIGH_PRIORITY_PATTERNS
        if name in EXTENDED_REGEX_PATTERNS
    }


def get_context_patterns() -> Dict[str, str]:
    """获取需要上下文的模式"""
    return {
        name: EXTENDED_REGEX_PATTERNS[name]
        for name in CONTEXT_REQUIRED_PATTERNS
        if name in EXTENDED_REGEX_PATTERNS
    }


def compile_patterns() -> Dict[str, re.Pattern]:
    """编译所有正则表达式"""
    compiled = {}
    for name, pattern in EXTENDED_REGEX_PATTERNS.items():
        try:
            compiled[name] = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            print(f"警告: 正则编译失败 [{name}]: {e}")
    return compiled


def find_all_keys(text: str, patterns: Dict[str, str] = None) -> List[Tuple[str, str, int]]:
    """
    在文本中查找所有可能的密钥

    Args:
        text: 要搜索的文本
        patterns: 使用的模式字典，默认使用所有模式

    Returns:
        List of (platform, key, position)
    """
    if patterns is None:
        patterns = EXTENDED_REGEX_PATTERNS

    results = []

    for name, pattern in patterns.items():
        try:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                key = match.group(0) if match.lastindex is None else match.group(1)
                results.append((name, key, match.start()))
        except Exception as e:
            continue

    # 按位置排序
    results.sort(key=lambda x: x[2])

    return results


def identify_platform(key: str) -> List[str]:
    """
    识别密钥可能属于的平台

    Args:
        key: 要识别的密钥

    Returns:
        可能的平台列表
    """
    matches = []

    for name, pattern in EXTENDED_REGEX_PATTERNS.items():
        try:
            if re.match(pattern, key, re.IGNORECASE):
                matches.append(name)
        except Exception:
            continue

    return matches


# ============================================================================
#                              搜索关键词扩展
# ============================================================================

EXTENDED_SEARCH_KEYWORDS = [
    # 通信平台
    'filename:.env SLACK_TOKEN NOT test NOT example',
    'filename:.env SLACK_WEBHOOK NOT staging',
    'xoxb- language:python NOT test NOT example',
    'hooks.slack.com/services NOT test',

    # Discord
    'filename:.env DISCORD_TOKEN NOT test',
    'discord.com/api/webhooks NOT test',

    # 云服务商
    'filename:.env DIGITALOCEAN_TOKEN NOT test',
    'dop_v1_ language:python NOT test',
    'filename:.env HEROKU_API_KEY NOT test',
    'filename:.env CLOUDFLARE_API_TOKEN NOT test',
    'filename:.env VERCEL_TOKEN NOT test',

    # 开发工具
    'glpat- language:python NOT test NOT example',
    'filename:.env GITLAB_TOKEN NOT test',
    'filename:.env CIRCLECI_TOKEN NOT test',
    'npm_token language:json NOT test',
    'filename:.npmrc _authToken NOT test',
    'dckr_pat_ language:yaml NOT test',

    # 监控/APM
    'filename:.env DATADOG_API_KEY NOT test',
    'sntrys_ language:python NOT test',
    'sentry.io NOT test NOT example',
    'NRAK- language:python NOT test',
    'filename:.env PAGERDUTY_API_KEY NOT test',

    # 协作工具
    'secret_ notion language:python NOT test',
    'lin_api_ language:python NOT test',
    'filename:.env ASANA_TOKEN NOT test',
    'filename:.env AIRTABLE_API_KEY NOT test',

    # 分析平台
    'filename:.env SEGMENT_WRITE_KEY NOT test',
    'filename:.env MIXPANEL_TOKEN NOT test',
    'filename:.env AMPLITUDE_API_KEY NOT test',
    'filename:.env ALGOLIA_API_KEY NOT test',

    # 支付平台
    'sk_live_ NOT test NOT example NOT staging',
    'sq0atp- language:python NOT test',
    'filename:.env PAYPAL_CLIENT_ID NOT test',

    # 存储服务
    'shpat_ language:ruby NOT test',
    'filename:.env SHOPIFY_ACCESS_TOKEN NOT test',
    'mongodb+srv:// NOT test NOT example',
    'redis:// password NOT test NOT example',

    # 私钥
    '"BEGIN RSA PRIVATE KEY" NOT test NOT example',
    '"BEGIN EC PRIVATE KEY" NOT test',
    '"BEGIN OPENSSH PRIVATE KEY" NOT test',
]


def get_extended_search_keywords() -> List[str]:
    """获取扩展搜索关键词"""
    return EXTENDED_SEARCH_KEYWORDS.copy()


# ============================================================================
#                              平台到正则映射
# ============================================================================

PLATFORM_REGEX_MAP = {
    # 平台名 -> 对应的正则模式名列表
    "slack": ["slack_token", "slack_webhook"],
    "discord": ["discord_token", "discord_webhook"],
    "telegram": ["telegram_bot"],
    "twilio": ["twilio_sid", "twilio_auth"],
    "sendgrid": ["sendgrid"],
    "mailgun": ["mailgun"],
    "mailchimp": ["mailchimp"],
    "digitalocean": ["digitalocean", "digitalocean_oauth"],
    "heroku": ["heroku"],
    "cloudflare": ["cloudflare_token", "cloudflare_global"],
    "vercel": ["vercel"],
    "gitlab": ["gitlab_pat", "gitlab_pipeline", "gitlab_runner"],
    "circleci": ["circleci"],
    "travis_ci": ["travis_ci"],
    "npm": ["npm_token", "npm_auth"],
    "docker_hub": ["docker_hub"],
    "datadog": ["datadog_api", "datadog_app"],
    "sentry": ["sentry", "sentry_dsn"],
    "newrelic": ["newrelic_api", "newrelic_license", "newrelic_browser"],
    "pagerduty": ["pagerduty", "pagerduty_integration"],
    "notion": ["notion"],
    "linear": ["linear"],
    "asana": ["asana"],
    "airtable": ["airtable", "airtable_pat"],
    "atlassian": ["atlassian"],
    "segment": ["segment"],
    "mixpanel": ["mixpanel"],
    "amplitude": ["amplitude"],
    "algolia": ["algolia_api", "algolia_admin"],
    "zendesk": ["zendesk"],
    "intercom": ["intercom"],
    "freshdesk": ["freshdesk"],
    "hubspot": ["hubspot", "hubspot_pat"],
    "mapbox": ["mapbox", "mapbox_secret"],
    "google_maps": ["google_maps"],
    "stripe": ["stripe_secret", "stripe_publishable", "stripe_restricted", "stripe_test"],
    "square": ["square", "square_app"],
    "paypal": ["paypal_client"],
    "aws": ["aws_access", "aws_secret", "aws_session"],
    "shopify": ["shopify_access", "shopify_secret"],
    "okta": ["okta"],
    "auth0": ["auth0"],
}


def get_regex_for_platform(platform: str) -> List[str]:
    """获取平台对应的正则模式名"""
    return PLATFORM_REGEX_MAP.get(platform.lower(), [])


def get_patterns_for_platform(platform: str) -> Dict[str, str]:
    """获取平台对应的正则模式"""
    pattern_names = get_regex_for_platform(platform)
    return {
        name: EXTENDED_REGEX_PATTERNS[name]
        for name in pattern_names
        if name in EXTENDED_REGEX_PATTERNS
    }
