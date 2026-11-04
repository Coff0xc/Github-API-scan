# FOFA Integration Guide

## Overview

FOFA (https://fofa.info) is a cyberspace search engine that indexes public internet assets. This integration expands the scanner's search capabilities beyond GitHub to find exposed API keys on public websites, misconfigured servers, and exposed files.

## Features

- **Multi-source scanning** - Search beyond GitHub repositories
- **Cyberspace coverage** - Find keys in public web servers, APIs, config files
- **Platform-specific queries** - Optimized search for OpenAI, Anthropic, Gemini, etc.
- **Automatic extraction** - Reuse existing regex patterns
- **Rate limiting** - Built-in delays to respect API limits

## Setup

### 1. Get FOFA Account

1. Register at https://fofa.info
2. Purchase API access (free tier available)
3. Get your API key from https://fofa.info/userInfo

### 2. Configure Credentials

Add to `config_local.py`:

```python
# FOFA Configuration
FOFA_EMAIL = "your-email@example.com"
FOFA_API_KEY = "your-fofa-api-key-here"
```

### 3. Install (if needed)

FOFA integration uses standard Python libraries (requests, base64). No additional dependencies required.

## Usage

### Basic Search

```python
from source_fofa import FOFASearcher

# Initialize
fofa = FOFASearcher(
    email="your-email@example.com",
    api_key="your-api-key"
)

# Search for OpenAI keys
results = fofa.search_api_keys(platform="openai", max_results=100)

print(f"Found {len(results)} results")
for r in results:
    print(f"{r['platform']}: {r['api_key'][:20]}... from {r['source_url']}")
```

### Advanced Search

```python
# Custom FOFA query
query = 'body="OPENAI_API_KEY" && country="US"'
results = fofa.search(query, page=1, size=100)

# Extract keys from results
from config import REGEX_PATTERNS
extracted = fofa.extract_keys_from_results(results['results'], REGEX_PATTERNS)
```

### Integration with Main Scanner

Modify `main_v2.2.py` to include FOFA:

```python
from source_fofa import FOFASearcher
from config_local import FOFA_EMAIL, FOFA_API_KEY

# Initialize FOFA searcher
fofa = FOFASearcher(email=FOFA_EMAIL, api_key=FOFA_API_KEY)

# Search FOFA
if fofa.is_configured():
    logger.info("Searching FOFA...")
    fofa_results = fofa.search_api_keys(platform="all", max_results=1000)
    
    # Process results
    for result in fofa_results:
        scan_results.append(ScanResult(
            platform=result['platform'],
            api_key=result['api_key'],
            base_url="",
            source_url=result['source_url'],
        ))
```

## FOFA Query Syntax

### Basic Patterns

```
body="text"           # Search in page body
title="text"          # Search in page title
header="text"         # Search in HTTP headers
domain="example.com"  # Specific domain
ip="1.2.3.4"         # Specific IP
port="80"            # Specific port
country="US"         # Country code
```

### Operators

```
&&    # AND
||    # OR
!=    # NOT EQUAL
=     # EQUAL
```

### Platform-Specific Queries

**OpenAI:**
```
body="OPENAI_API_KEY" && body="sk-"
body="Authorization: Bearer sk-"
title="config" && body="sk-proj-"
```

**Anthropic:**
```
body="ANTHROPIC_API_KEY" && body="sk-ant-"
body="x-api-key" && body="sk-ant-"
```

**Gemini:**
```
body="GOOGLE_API_KEY" && body="AIza"
body="generativelanguage.googleapis.com"
```

**Azure OpenAI:**
```
body="AZURE_OPENAI_KEY"
body="openai.azure.com"
```

## API Limits

### Free Tier
- 100 queries/day
- 100 results per query
- 10,000 results/month

### Individual Plan ($59/year)
- 10,000 queries/year
- 10,000 results per query
- 1,000,000 results/year

### Enterprise Plan
- Custom limits
- Dedicated support

## Best Practices

### 1. Rate Limiting

Add delays between requests:
```python
import time
for page in range(1, 11):
    results = fofa.search(query, page=page)
    time.sleep(1)  # 1 second delay
```

### 2. Query Optimization

Be specific to reduce false positives:
```python
# ✗ Too broad
query = 'body="api_key"'

# ✓ More specific
query = 'body="OPENAI_API_KEY" && body="sk-proj-" && title="config"'
```

### 3. Deduplication

FOFA results may overlap with GitHub:
```python
# Check if key already found
if not db.key_exists(api_key):
    # Process new key
    pass
```

### 4. Error Handling

```python
try:
    results = fofa.search(query)
    if results and not results.get('error'):
        # Process results
        pass
except Exception as e:
    logger.error(f"FOFA search failed: {e}")
```

## Security Considerations

### 1. Credential Protection

Never commit FOFA credentials:
```python
# ✗ Don't do this
FOFA_API_KEY = "abc123..."  # In version control

# ✓ Use config_local.py or environment variables
from config_local import FOFA_API_KEY
```

### 2. Responsible Use

- Respect FOFA terms of service
- Don't abuse API rate limits
- Only scan for security research/authorized testing

### 3. Data Privacy

FOFA indexes public internet data, but:
- Be cautious with discovered keys
- Report responsibly
- Don't exploit found credentials

## Comparison with GitHub Search

| Feature | GitHub | FOFA |
|---------|--------|------|
| **Coverage** | Code repositories | Public web servers, APIs, configs |
| **Rate Limits** | 30/min per token | Plan-dependent |
| **Cost** | Free | Free tier + paid plans |
| **Key Density** | High (developers) | Medium (misconfigurations) |
| **False Positives** | Low | Medium |
| **API Quality** | Excellent | Good |

## Expected Impact

Adding FOFA as a search source:
- **+15-25% new keys** - Find keys in non-GitHub sources
- **Different key types** - Production keys vs development keys
- **Geographic diversity** - Keys from different regions
- **Misconfiguration focus** - Exposed config files, APIs

## Troubleshooting

### No Results

1. Check FOFA quota: https://fofa.info/userInfo
2. Verify query syntax
3. Try broader queries

### API Errors

**Error: "401 Unauthorized"**
- Check email and API key
- Verify account is active

**Error: "402 Payment Required"**
- Quota exceeded
- Upgrade plan or wait for reset

**Error: "Too Many Requests"**
- Rate limited
- Add delays between requests

### Integration Issues

**Keys not validating:**
- FOFA may return partial/obfuscated keys
- Use entropy filtering
- Verify key format before validation

## Example Results

```
Platform: openai
Key: sk-proj-abc123...
Source: https://example.com:8080
Domain: example.com
IP: 1.2.3.4
Title: Configuration Page

Platform: anthropic
Key: sk-ant-api03-xyz...
Source: https://api.server.com
Domain: server.com
IP: 5.6.7.8
Title: API Documentation
```

## Future Enhancements

- [ ] Automatic FOFA query generation
- [ ] Intelligent deduplication across sources
- [ ] FOFA result ranking
- [ ] Historical FOFA data analysis
- [ ] Multi-source correlation

---

**Status:** ✅ Production ready  
**Tested on:** FOFA API v1  
**Last Updated:** 2026-07-29
