# AI-Assisted Analysis Integration Guide

This tool has a built-in LLM-assisted detection module (`ai_detector.py` + `ai_scanner_integration.py`) that
applies contextual judgment to candidate keys **after regex matching and before API validation**, filtering out
test/example/placeholder keys and reducing wasted validation requests.

> Reminder of the principle: AI-assisted analysis exists only to **reduce false positives** and make audits of your
> own assets more efficient. It does not change the tool's usage boundaries (see AUTHORIZED_USE.md in the repository root).

## What problem it solves

The regex pipeline treats `sk-test-xxxx`, documentation examples, and masked placeholders as candidate keys, while a
validation request is a real network call to the target API. The AI layer hands the code snippet to an LLM and asks:

- Is this a real credential, or example/test data?
- Do the surrounding variable names, comments, and file type suggest it is usable?
- Output a confidence level (NONE/LOW/MEDIUM/HIGH) and a reason

The official README claims this technique cuts false positives by 94% (`ai_detector.py` cites the Copilot
MetaReflection approach).

## Integration options (pick one of three)

### Option A: Local Ollama (recommended, zero API cost)

```bash
# 1. Install and start Ollama, then pull a small model
ollama pull llama3.2:3b        # or qwen2.5:7b (better with Chinese context)

# 2. Enable AI filtering and scan
export AI_FILTER_ENABLED=1
python main_v2.2.py --authorized --target-org your-org
```

If Ollama is unavailable, it automatically falls back to the pure rule engine (MockBackend) and the scan is not interrupted.

### Option B: OpenAI-compatible API (official API or a relay)

```bash
export AI_FILTER_ENABLED=1
export AI_DETECTOR_BACKEND=openai
export OPENAI_API_KEY=sk-xxxx                 # your AI API key
export AI_LLM_BASE_URL=https://api.openai.com/v1   # optional; a relay goes here
export AI_LLM_MODEL=gpt-3.5-turbo             # optional, default gpt-3.5-turbo
python main_v2.2.py --authorized --target-org your-org
```

Any OpenAI-compatible endpoint (DeepSeek, Moonshot, a one-api relay, and others) works — just change
`AI_LLM_BASE_URL`.

### Option C: Standalone call (analysis only, no scan)

```python
import asyncio
from ai_scanner_integration import should_validate_key

ok, reason = asyncio.run(should_validate_key(
    api_key="sk-proj-xxxxxxxxxxxxxxxx",
    code_snippet="OPENAI_API_KEY=sk-proj-xxxx  # production",
    platform="openai",
))
print(ok, reason)
```

## Implementation notes

| Stage | Location | Notes |
|---|---|---|
| Rule pre-screen | `ai_detector.QuickFilter` | Fast judgment without an LLM (variable names / placeholders / entropy), blocking a batch first |
| LLM judgment | `ai_detector.AIDetector` + `SmartDetector.should_validate` | Sends an LLM call only for candidates the rules cannot decide |
| Backend abstraction | `ai_detector.LLMBackend` → `OllamaBackend` / `OpenAIBackend` / `MockBackend` | temperature=0.1, max_tokens=500 |
| Pipeline hook | `ai_scanner_integration.patch_scanner_with_ai` | Patches `GitHubScanner._extract_keys_from_content`, bridging async filtering from a sync thread |
| Switch | `scanner.start_scanner` → `_maybe_enable_ai_filter` | Environment variable `AI_FILTER_ENABLED`, off by default |

> Fix record: the old `patch_scanner_with_ai` hooked a function name that did not exist (module-level
> `extract_keys_from_content` vs the actual class method `_extract_keys_from_content`), so the
> patch silently did nothing; and async filtering could not be awaited directly inside the sync pipeline. Both are now fixed.

## Cost and performance notes

- LLM calls happen inside the **synchronous download pipeline** (a bridge thread blocks waiting), so a file with many candidates
  slows the scan — pair it with a small local model (3B class); when using a remote API, watch concurrent billing.
- Each LLM request sends the code snippet (first 1500 characters) to the backend. **That is harmless when scanning your own
  repositories; if the scan target contains other people's code, consider the compliance issue of sending its content to a third-party API.**
- When `AI_FILTER_ENABLED` is unset, behavior is exactly the same as the old version (pure regex + entropy filtering).

## Related docs

- [AI_DETECTOR_README.md](AI_DETECTOR_README.md) — detector internals (prompts, confidence, caching)
- [../AUTHORIZED_USE.md](../AUTHORIZED_USE.md) — usage boundaries
