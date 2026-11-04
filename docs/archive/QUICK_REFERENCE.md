# Quick Reference Guide

## Scanner Commands

```bash
# Basic scanning
python main_v2.2.py                    # Start scanning with TUI
python main_v2.2.py --no-cache         # Disable cache
python main_v2.2.py --all-sources      # Scan all sources

# View results
python main_v2.2.py --stats            # Show statistics
python main_v2.2.py --export valid.txt --status valid
python main_v2.2.py --export-csv results.csv

# Other versions
python main_v2.1.py                    # v2.1 (connection pool)
python main.py                         # Original version
```

## Configuration Checklist

- [ ] Python 3.10+ installed
- [ ] Dependencies installed: `pip install -r requirements.txt`
- [ ] GitHub token added to `config_local.py`
- [ ] (Optional) Proxy configured if needed

## Platform Coverage

**50+ platforms including:**
- OpenAI, Anthropic, Google Gemini, Azure OpenAI
- OpenRouter, Portkey, LiteLLM (AI aggregators)
- AWS Bedrock, Vertex AI, Alibaba Cloud
- DeepSeek, Moonshot, Zhipu (regional)
- Plus 30+ more...

## Performance

- **Speed:** 430x faster than manual
- **Cache:** 30-50% hit rate
- **Efficiency:** 61% fewer requests

## Files to Know

- `config_local.py` - Your GitHub token goes here
- `config.yaml` - Performance tuning
- `leaked_keys.db` - Results database
- `README.md` - Full documentation

## Getting Help

1. Read `USAGE_GUIDE.md` for step-by-step instructions
2. Check `README.md` for detailed docs
3. Run `python test_system.py` to verify setup

## Quick Troubleshooting

**"GitHub Tokens not configured"**
→ Add token to `config_local.py`

**"Rate limit exceeded"**
→ Add more tokens or wait 60 minutes

**"No dependencies"**
→ Run `pip install -r requirements.txt`

## Legal Reminder

✅ Authorized testing only
✅ Report findings responsibly
❌ Don't exploit found keys
❌ Don't scan without permission
