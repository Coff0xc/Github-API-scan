"""
工具函数模块 - 通用工具函数集合

提供:
- 熵值计算 (LRU缓存)
- Key/URL 过滤检测
- 字符串处理
- 文件过滤
"""

import math
from functools import lru_cache
from collections import Counter
from typing import Tuple


# ============================================================================
#                              常量定义
# ============================================================================

# 熵值阈值
ENTROPY_THRESHOLD = 3.8

# 测试 Key 关键词
TEST_KEY_PATTERNS = [
    'test', 'demo', 'example', 'sample', 'fake', 'dummy', 'placeholder',
    'xxx', 'your_', 'your-', '<your', '{your', 'abcdef', '123456',
    'insert', 'replace', 'xxxxxx', 'aaaaaa', 'dev_', 'dev-', 'staging',
    'sandbox', 'tutorial', 'workshop', 'playground', 'temp_', 'tmp_', 'mock_', 'stub_',
]

# 域名黑名单
DOMAIN_BLACKLIST = [
    'localhost', '127.0.0.1', '0.0.0.0', 'example.com', 'test.com',
    'my-api', 'your-api', 'xxx', 'placeholder', 'fake', 'dummy', 'sample', 'mock',
    'staging.', 'sandbox.', 'dev.', 'demo.', 'test.', '.local', '.internal',
    'ngrok.io', 'localtunnel',
]

# 文件过滤配置
MAX_FILE_SIZE_KB = 500

BLOCKED_EXTENSIONS = {
    '.lock', '.min.js', '.min.css', '.map', '.md', '.rst', '.txt',
    '.html', '.htm', '.css', '.scss', '.less', '.svg', '.png', '.jpg',
    '.jpeg', '.gif', '.ico', '.woff', '.woff2', '.ttf', '.eot',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip', '.tar', '.gz', '.rar',
    '.exe', '.dll', '.so', '.dylib', '.pyc', '.pyo', '.class', '.ipynb', '.csv',
}

PATH_BLACKLIST = [
    '/test/', '/tests/', '/__tests__/', '/spec/', '/specs/',
    '/mock/', '/mocks/', '/__mocks__/', '/fixture/', '/fixtures/',
    '/example/', '/examples/', '/sample/', '/samples/', '/demo/', '/demos/',
    '/doc/', '/docs/', '/vendor/', '/node_modules/', '/venv/', '/.venv/',
    '/dist/', '/build/', '/out/', '/coverage/', '/.github/ISSUE_TEMPLATE/',
    '/sandbox/', '/playground/', '/staging/', '/tutorial/', '/tutorials/',
    '/workshop/', '/workshops/', '/boilerplate/', '/starter/',
]


# ============================================================================
#                              工具函数
# ============================================================================

@lru_cache(maxsize=4096)
def calculate_entropy(s: str) -> float:
    """计算字符串香农熵 (带 LRU 缓存)"""
    if not s:
        return 0.0
    freq = Counter(s)
    length = len(s)
    return -sum((c / length) * math.log2(c / length) for c in freq.values() if c > 0)


@lru_cache(maxsize=2048)
def is_test_key(api_key: str) -> bool:
    """检测是否为测试 Key (带 LRU 缓存)"""
    key_lower = api_key.lower()
    return any(p in key_lower for p in TEST_KEY_PATTERNS)


@lru_cache(maxsize=1024)
def is_blacklisted_url(url: str) -> bool:
    """检测 URL 是否在黑名单中 (带 LRU 缓存)"""
    if not url:
        return False
    url_lower = url.lower()
    return any(b in url_lower for b in DOMAIN_BLACKLIST)


def mask_key(api_key: str) -> str:
    """遮蔽 API Key"""
    if len(api_key) <= 12:
        return api_key[:4] + "..." + api_key[-4:]
    return api_key[:8] + "..." + api_key[-4:]


def should_skip_file(file_path: str, file_size: int = 0) -> Tuple[bool, str]:
    """检查文件是否应该跳过"""
    file_path_lower = file_path.lower()

    # 文件大小检查
    if file_size > 0 and file_size > MAX_FILE_SIZE_KB * 1024:
        return True, f"file_too_large:{file_size // 1024}KB"

    # 路径黑名单
    for bp in PATH_BLACKLIST:
        if bp in file_path_lower:
            return True, f"path_blacklist:{bp}"

    # 文件后缀检查
    ext = ''
    if '.' in file_path:
        if file_path_lower.endswith('.min.js'):
            ext = '.min.js'
        elif file_path_lower.endswith('.min.css'):
            ext = '.min.css'
        else:
            ext = '.' + file_path.rsplit('.', 1)[-1].lower()

    if ext in BLOCKED_EXTENSIONS:
        return True, f"blocked_ext:{ext}"

    # 重要文件检查
    important_files = ['dockerfile', '.env', 'config', 'secret', 'credential']
    file_name = file_path.rsplit('/', 1)[-1].lower() if '/' in file_path else file_path.lower()
    if any(imp in file_name for imp in important_files):
        return False, ""

    return False, ""


def has_sequential_chars(s: str, min_len: int = 6) -> bool:
    """检测连续递增/递减字符"""
    if len(s) < min_len:
        return False
    count = 1
    for i in range(1, len(s)):
        if ord(s[i]) == ord(s[i - 1]) + 1 or ord(s[i]) == ord(s[i - 1]) - 1:
            count += 1
            if count >= min_len:
                return True
        else:
            count = 1
    return False


def clear_caches():
    """清理所有 LRU 缓存"""
    calculate_entropy.cache_clear()
    is_test_key.cache_clear()
    is_blacklisted_url.cache_clear()


def get_cache_stats() -> dict:
    """获取缓存统计信息"""
    return {
        "entropy": calculate_entropy.cache_info()._asdict(),
        "test_key": is_test_key.cache_info()._asdict(),
        "blacklist_url": is_blacklisted_url.cache_info()._asdict(),
    }
