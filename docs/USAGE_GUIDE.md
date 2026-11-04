# How to Use the Scanner - Step by Step

## Current Status
✅ Configuration loaded successfully  
✅ 50 regex patterns validated  
✅ 93 search queries ready  
⚠️ GitHub token needs to be configured

## Quick Start Guide

### Step 1: Get GitHub Token (2 minutes)

1. Visit: https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Name: `AI Scanner`
4. Select scope: **public_repo** (read-only)
5. Click "Generate token"
6. Copy the token (starts with `ghp_`)

### Step 2: Configure Token

Edit `config_local.py` and replace the placeholder:

```python
GITHUB_TOKENS = [
    "ghp_your_actual_token_here",  # Replace this
]
```

### Step 3: Run Scanner

```bash
# Basic scan
python main_v2.2.py

# View current statistics
python main_v2.2.py --stats

# Scan with all sources (GitHub, Gist, GitLab, etc.)
python main_v2.2.py --all-sources
```

## What You'll See

The terminal UI will show:

```
┌─────────────────────────────────────────┐
│  AI API Key Scanner - v2.2 Dashboard   │
├─────────────────────────────────────────┤
│  Scanning: GitHub Code Search           │
│  Queue: 234 items                       │
│  Valid keys found: 12                   │
│  Cache hit rate: 42%                    │
│                                         │
│  Recent finds:                          │
│  • OpenAI (GPT-4): sk-proj-xxx...      │
│  • Anthropic (Claude): sk-ant-xxx...   │
│  • OpenRouter: sk-or-v1-xxx...         │
└─────────────────────────────────────────┘
```

## Export Results

```bash
# Export valid keys to text file
python main_v2.2.py --export valid_keys.txt --status valid

# Export to CSV for analysis
python main_v2.2.py --export-csv results.csv --status valid

# Encrypted export (recommended for sensitive data)
python main_v2.2.py --export-encrypted secure.bin
```

## Platform Coverage

The scanner will search for keys from:

**Major AI platforms:**
- OpenAI (GPT-4, GPT-5)
- Anthropic (Claude)
- Google Gemini
- Azure OpenAI
- xAI Grok
- Meta Llama

**AI Aggregators (high value targets):**
- OpenRouter (multi-platform access)
- Portkey
- LiteLLM
- Cloudflare Workers AI

**Cloud AI Services:**
- AWS Bedrock
- Google Vertex AI
- Alibaba Cloud
- Volcano Engine
- Tencent Cloud
- Baidu Qianfan

**Plus 30+ more platforms...**

## Search Strategy

The scanner uses 93 optimized queries targeting:

1. **Environment files** (.env, .env.production, .env.local)
2. **Config files** (secrets.yaml, config.json)
3. **Container configs** (docker-compose.yml, Kubernetes secrets)
4. **IaC files** (terraform.tfvars, pulumi configs)
5. **CI/CD configs** (GitHub Actions, GitLab CI, Jenkins)

## Performance Expectations

- **Speed:** Processes 1000 keys in ~0.24 seconds (430x faster than manual)
- **Cache:** 30-50% hit rate (skips already-validated keys)
- **Network:** 61% fewer requests than naive approach
- **Memory:** Efficient queue management, handles 10,000+ items

## Troubleshooting

**Error: "GitHub Tokens not configured"**
- Solution: Add your token to `config_local.py`

**Error: "Rate limit exceeded"**
- Solution: Add more tokens to `config_local.py` or wait 60 minutes

**Error: "Connection refused"**
- Solution: Check your internet connection, try adding proxy in config

**No results found**
- Normal: Real leaked keys are rare
- Check: Try `--all-sources` to scan more locations
- Verify: Run `--stats` to see database contents

## Advanced Usage

```bash
# Disable cache (use less memory)
python main_v2.2.py --no-cache

# Custom database location
python main_v2.2.py --db /path/to/custom.db

# Use proxy (for restricted networks)
# Edit config_local.py:
PROXY_URL = "http://127.0.0.1:7890"

# Run with specific sources only
python main_v2.2.py --gist  # GitHub Gist only
python main_v2.2.py --gitlab  # GitLab only
```

## Performance Tuning

Edit `config.yaml` for your hardware:

```yaml
# High-performance (16GB+ RAM)
validator:
  max_concurrency: 200  # More parallel validations
  num_workers: 4        # More CPU workers

# Low-resource (8GB RAM)
validator:
  max_concurrency: 50
  num_workers: 1
```

## Legal Reminder

⚠️ **Only scan authorized targets**

This tool is for:
- ✅ Security research
- ✅ Authorized penetration testing
- ✅ Auditing your own repositories

Not for:
- ❌ Unauthorized scanning
- ❌ Exploiting found keys
- ❌ Illegal activities

## Next Steps

1. **Configure your token** (see Step 1 above)
2. **Run first scan**: `python main_v2.2.py`
3. **Export results**: `python main_v2.2.py --export results.txt --status valid`
4. **Report findings**: Use responsible disclosure

## Need Help?

- Check `README.md` for detailed documentation
- Check `QUICKSTART.md` for 5-minute guide
- Review `OPTIMIZATION_V2.2.md` for technical details

---

**Ready to start?** Configure your GitHub token and run `python main_v2.2.py`
