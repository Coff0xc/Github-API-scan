# AI-Assisted Detection Module — User Guide

## Overview

The AI-assisted detection module uses a large language model (LLM) for context-aware API key detection, and can cut the false-positive rate significantly.

**Key strengths**:
- 🎯 **94% fewer false positives** - based on GitHub Copilot MetaReflection
- 🧠 **Context-aware** - understands code semantics and tells real keys apart from test keys
- ⚡ **Two-layer filtering** - fast rule-engine screening + in-depth AI analysis
- 💰 **Cost-optimized** - prefers local Ollama, saving API fees

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ SmartDetector (Smart Detector)                              │
├────────────────────────────┬────────────────────────────────┤
│      QuickFilter           │         AIDetector             │
│ (Rule engine)              │ (LLM analysis)                 │
│                            │                                │
│ • Test-pattern detection   │ • Local Ollama model           │
│ • Entropy calculation      │ • OpenAI API                   │
│ • Duplicate-pattern check  │ • Few-shot prompts             │
│ • File-path analysis       │ • Chain of Thought             │
└────────────────────────────┴────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │ Detection result │
                    │  • Confidence    │
                    │  • Key type      │
                    │  • Platform      │
                    │  • Reasoning     │
                    └──────────────────┘
```

## Quick start

### 1. Install Ollama (recommended)

```bash
# Linux/Mac
curl -fsSL https://ollama.ai/install.sh | sh

# Windows
# Download and install from https://ollama.ai/download

# Pull a model (pick one)
ollama pull llama3.2:3b    # Fast, good for first-pass screening (recommended)
ollama pull llama3.1:8b    # Balanced
ollama pull qwen2.5:7b     # Good with Chinese text
ollama pull mistral:7b     # High quality

# Verify
ollama list
```

### 2. Run the tests

```bash
# Check backend availability
python check_ai_detector.py --check

# Run the full test suite
python check_ai_detector.py --all

# Interactive test
python check_ai_detector.py --interactive
```

### 3. Using it in code

```python
from ai_detector import SmartDetector, CodeContext

# Create the detector
detector = SmartDetector()
await detector.initialize()

# Analyze a code snippet
context = CodeContext(
    code_snippet='''
    OPENAI_API_KEY = "sk-proj-abc123..."
    client = OpenAI(api_key=OPENAI_API_KEY)
    ''',
    file_path="config.py"
)

should_validate, result = await detector.should_validate(
    candidate_key="sk-proj-abc123...",
    code_context=context
)

if should_validate:
    print(f"Should validate: {result.provider} Key")
else:
    print(f"Skip: {result.reasoning}")
```

## Detection results

### Confidence levels

| Level | Meaning | Recommended action |
|------|------|---------|
| `HIGH` | Highly confident this is a real key | Validate immediately |
| `MEDIUM` | Likely a real key | Validate |
| `LOW` | Might be a key, but uncertain | Optional validation |
| `NONE` | Not an API key | Skip |

### Key types

| Type | Meaning | Example |
|------|------|------|
| `REAL` | Real key | A key in a config file |
| `TEST` | Test key | `sk-test-xxx` |
| `EXAMPLE` | Example key | An example in documentation |
| `PLACEHOLDER` | Placeholder | `YOUR_API_KEY` |
| `FAKE` | Clearly fake key | `sk-xxxxxxxxxxxx` |

## Configuration

### Environment variables

```bash
# AI detector switch
export AI_DETECTOR_ENABLED=true

# Backend: ollama, openai, mock
export AI_DETECTOR_BACKEND=ollama

# Ollama settings
export OLLAMA_URL=http://localhost:11434
export OLLAMA_MODEL=llama3.2:3b

# OpenAI settings (fallback)
export OPENAI_API_KEY=sk-xxx
export OPENAI_MODEL=gpt-3.5-turbo

# Quick filter
export AI_QUICK_FILTER=true

# Cache
export AI_CACHE_ENABLED=true
export AI_CACHE_SIZE=1000
```

### YAML configuration

Add to `notify_config.yaml`:

```yaml
ai_detector:
  enabled: true
  backend: ollama  # ollama, openai, mock

  # Ollama settings
  ollama_url: http://localhost:11434
  ollama_model: llama3.2:3b

  # OpenAI settings (fallback)
  openai_api_key: ""
  openai_model: gpt-3.5-turbo

  # Quick filter
  quick_filter_enabled: true

  # Cache
  cache_enabled: true
  cache_size: 1000
```

## Integrating with the Scanner

### Option 1: Use it directly

```python
from ai_scanner_integration import ScannerAIIntegration

# Create an integration instance
ai_integration = ScannerAIIntegration(
    enable_ai=True,
    ollama_model="llama3.2:3b"
)
await ai_integration.initialize()

# Filter candidate keys
result = await ai_integration.filter_candidate(
    platform="openai",
    api_key="sk-proj-xxx",
    code_snippet="...",
    file_path="config.py"
)

if result.should_validate:
    # Continue validation
    pass
else:
    print(f"AI filter: {result.filter_reason}")
```

### Option 2: Convenience function

```python
from ai_scanner_integration import should_validate_key

should_validate, reason = await should_validate_key(
    api_key="sk-proj-xxx",
    code_snippet="...",
    file_path="config.py"
)
```

## Performance tuning

### 1. Pre-screen with the quick filter

The quick filter uses a rule engine and needs no LLM call:

```python
from ai_detector import QuickFilter

quick_filter = QuickFilter()
is_fake, reason = quick_filter.is_likely_fake(
    candidate_key="sk-test-xxx",
    context="# test file",
    file_path="test.py"
)

if is_fake:
    print(f"Quick filter: {reason}")
    # Skip LLM analysis
```

### 2. Batch processing

```python
candidates = [
    {"platform": "openai", "api_key": "sk-xxx", "code_snippet": "..."},
    # ...
]

results = await ai_integration.filter_batch(candidates, concurrency=10)
```

### 3. Caching

Caching is on by default; the same snippet+key combination is analyzed only once:

```python
detector = AIDetector(cache_enabled=True, cache_size=1000)
```

## Test commands

```bash
# Check backend status
python check_ai_detector.py --check

# Test the quick filter
python check_ai_detector.py --quick

# Test the AI detector
python check_ai_detector.py --backend ollama
python check_ai_detector.py --backend openai
python check_ai_detector.py --backend mock

# Run all tests
python check_ai_detector.py --all

# Interactive test
python check_ai_detector.py --interactive
```

## Recommended models

| Model | Size | Speed | Quality | Best for |
|------|------|------|------|---------|
| `llama3.2:3b` | 2GB | ⚡⚡⚡ | ⭐⭐⭐ | Fast first-pass screening (recommended) |
| `llama3.1:8b` | 5GB | ⚡⚡ | ⭐⭐⭐⭐ | Balanced |
| `qwen2.5:7b` | 4GB | ⚡⚡ | ⭐⭐⭐⭐ | Chinese code |
| `mistral:7b` | 4GB | ⚡⚡ | ⭐⭐⭐⭐⭐ | High quality |
| `gpt-3.5-turbo` | - | ⚡ | ⭐⭐⭐⭐⭐ | Cloud fallback |

## File list

```
├── ai_detector.py              # AI detection core module
├── ai_scanner_integration.py   # Scanner integration module
├── check_ai_detector.py         # Test script
└── AI_DETECTOR_README.md       # This document
```

## Troubleshooting

### Ollama connection failed

```bash
# Check the Ollama service
curl http://localhost:11434/api/tags

# Restart Ollama
ollama serve
```

### Model not found

```bash
# List installed models
ollama list

# Pull the model
ollama pull llama3.2:3b
```

### Inaccurate detection results

1. Try a larger model (`llama3.1:8b`)
2. Check that the code context is complete
3. Debug with the interactive test

## Changelog

### v1.0.0 (2026-01)

- Initial release
- Ollama/OpenAI/Mock backends
- Fast rule filter
- Few-shot + Chain of Thought prompts
- Result caching
