#!/bin/bash
# Quick test script to verify installation

echo "==================================="
echo "AI API Key Scanner - System Check"
echo "==================================="
echo ""

# Check Python version
echo "[1/5] Checking Python version..."
python --version 2>&1 | grep -q "3.1[0-9]" && echo "✅ Python 3.10+ detected" || echo "❌ Python 3.10+ required"
echo ""

# Check dependencies
echo "[2/5] Checking dependencies..."
python -c "import aiohttp; import rich; import loguru; from github import Github" 2>/dev/null && echo "✅ All dependencies installed" || echo "⚠️  Run: pip install -r requirements.txt"
echo ""

# Check configuration
echo "[3/5] Checking configuration..."
python -c "from config import config; print('✅ Configuration loaded')" 2>/dev/null || echo "❌ Configuration error"
echo ""

# Check GitHub token
echo "[4/5] Checking GitHub token..."
python -c "from config import config; exit(0 if config.github_tokens and config.github_tokens[0] else 1)" 2>/dev/null && echo "✅ GitHub token configured" || echo "⚠️  Add GitHub token to config_local.py"
echo ""

# Check regex patterns
echo "[5/5] Checking regex patterns..."
python -c "from config import REGEX_PATTERNS; import re; [re.compile(p) for p in REGEX_PATTERNS.values()]; print('✅ All 50 regex patterns valid')" 2>/dev/null || echo "❌ Regex validation failed"
echo ""

echo "==================================="
echo "System check complete!"
echo "==================================="
echo ""
echo "Next steps:"
echo "1. Configure GitHub token in config_local.py"
echo "2. Run: python main_v2.2.py"
echo "3. View results: python main_v2.2.py --stats"
