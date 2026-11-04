# Changelog - v3.0 (2026 Edition)

## Release Date: 2026-07-24

## 🚀 Major Updates

### Platform Coverage Expansion (50+ Platforms)

**AI Aggregators & Gateways (New):**
- OpenRouter (sk-or-v1-)
- Portkey (pk-)
- LiteLLM Proxy
- Cloudflare Workers AI

**Cloud Provider AI Services (New):**
- AWS Bedrock (Claude/Llama hosting)
- Alibaba Cloud Bailian (Qwen/Tongyi)
- Volcano Engine (Doubao)
- Tencent Cloud Hunyuan
- Baidu Qianfan
- Google Vertex AI
- Azure AI Services

**Emerging Platforms (New):**
- xAI Grok (Elon Musk)
- Meta Llama API (Commercial)
- DeepSeek V3
- Moonshot AI (Kimi)
- Zhipu AI (GLM-4)
- Yi AI (01.AI)
- StepFun
- iFlytek Spark
- SenseTime
- Kunlun Tiangong

**Enterprise Solutions (New):**
- AI21 Labs (Jamba)
- Writer
- Forefront AI

**Open Source Inference (New):**
- Modal (GPU Cloud)
- RunPod
- Baseten

### Detection Improvements

**GitHub Code Search Syntax Modernization:**
- Removed deprecated `NOT` operator
- Updated to `-test -example` syntax (2024+ GitHub API requirement)
- 93 optimized search queries covering all major platforms

**Regex Pattern Updates:**
- 50+ platform-specific patterns optimized for 2026 API key formats
- Support for new key prefixes (xai-, llama-, moonshot-, etc.)
- Improved entropy filtering to reduce false positives

**Enhanced File Targeting:**
- Container/IaC file detection (Kubernetes secrets, Terraform vars)
- CI/CD configuration scanning (.github/workflows, .gitlab-ci.yml, Jenkinsfile)
- Infrastructure-as-Code focus (Pulumi, Terraform, CloudFormation)

### Internationalization

**Full English Documentation:**
- All Chinese comments translated to English
- README completely rewritten in English
- Configuration file comments in English
- No regional identifiers in codebase

**Platform Coverage:**
- Global reach: Americas, Europe, Asia-Pacific
- Regional provider support without language barriers
- Neutral naming conventions

### Performance & Architecture

**Retained from v2.2:**
- 3-layer smart cache (30-50% hit rate)
- Batch validation (40-60% fewer requests)
- HTTP connection pool (70-80% overhead reduction)
- Smart retry mechanism (15-25% success boost)
- Dynamic queue management (30-50% memory reduction)

**Database Performance:**
- 100-430x speedup vs original version
- Async SQLite operations
- Batch writes with configurable flush intervals

## 🔧 Configuration Changes

### Breaking Changes

1. **Search Query Syntax:**
   ```diff
   - 'filename:.env OPENAI_API_KEY NOT test NOT example'
   + 'filename:.env OPENAI_API_KEY -test -example'
   ```

2. **Platform URLs Updated:**
   - All URLs now include `/v1` API version where applicable
   - Cloud provider URLs use variable templates (`{region}`, `{account_id}`)

### New Configuration Options

**Platform Default URLs:**
```python
default_base_urls = {
    # 45 platforms with complete endpoint definitions
    "openrouter": "https://openrouter.ai/api/v1",
    "aws_bedrock": "https://bedrock-runtime.{region}.amazonaws.com",
    # ... (see config.py for complete list)
}
```

**Search Keywords:**
- 93 optimized queries (up from ~70 in v2.2)
- Organized by platform category
- Container/IaC specific queries added

## 📊 Statistics

- **Platforms Supported:** 50+ (up from ~30)
- **Regex Patterns:** 50+ (up from ~25)
- **Search Queries:** 93 (up from ~70)
- **Performance:** 430x faster than original (unchanged)
- **Cache Hit Rate:** 30-50% (unchanged from v2.2)

## 🔄 Migration Guide

### From v2.2 to v3.0

**No database migration required** - v3.0 is fully backward compatible with v2.2 databases.

**Step 1: Update configuration**
```bash
# Backup your config_local.py
cp config_local.py config_local.py.backup

# Pull latest changes
git pull origin main

# Restore your tokens
# config_local.py format unchanged
```

**Step 2: Update dependencies (optional)**
```bash
pip install -r requirements.txt --upgrade
```

**Step 3: Test**
```bash
# Verify config loads
python -c "from config import config; print('OK')"

# Test with --stats
python main_v2.2.py --stats
```

### Deprecated Features

**None** - All v2.2 features retained in v3.0.

## 🐛 Bug Fixes

1. **Fixed duplicate "replicate" entry in REGEX_PATTERNS**
   - Removed duplicate regex definition
   - Platform now correctly mapped once

2. **Fixed GitHub Code Search query syntax errors**
   - All queries updated to use `-` operator instead of `NOT`
   - Queries now compatible with GitHub API 2024+ requirements

3. **Improved entropy threshold filtering**
   - Reduced false positives for test keys
   - Better detection of sequential character patterns

## 🔐 Security Enhancements

**Key Format Recognition:**
- Updated patterns for 2026 API key formats
- Support for multi-prefix keys (sk-proj-, sk-svcacct-, sk-ant-api03-)
- Improved Azure and cloud provider key detection

**Circuit Breaker Protection:**
- Protected domains expanded to cover new platforms
- Improved error classification (network vs API)
- Better retry logic for transient failures

## 📝 Documentation Updates

**New Documentation:**
- `README.md` - Complete rewrite in English, comprehensive platform list
- `CHANGELOG_V3.0.md` - This file
- `config_local.py` - Template with detailed comments

**Updated Documentation:**
- `QUICKSTART.md` - Updated for 2026 platforms (TODO)
- `OPTIMIZATION.md` - Reflects v3.0 architecture (TODO)

## 🙏 Acknowledgments

Thank you to all contributors and security researchers who reported issues and suggested improvements.

## 📞 Support

- **Issues:** https://github.com/YourUsername/AI-API-Scanner/issues
- **Security:** Report via GitHub Security Advisories
- **Discussions:** https://github.com/YourUsername/AI-API-Scanner/discussions

---

**Full Changelog:** [v2.2...v3.0](https://github.com/YourUsername/AI-API-Scanner/compare/v2.2...v3.0)
