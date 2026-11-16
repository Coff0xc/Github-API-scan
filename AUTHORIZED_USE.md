# Authorized Use Statement (AUTHORIZED USE)

> **This tool may only be used on assets you own or are authorized to test.** Every scan entry point asks you to
> explicitly confirm this statement (the `--authorized` flag, the `SCANNER_AUTHORIZED=1` environment variable, or
> interactive input `y`).

## 1. Permitted use cases

| Scenario | Description |
|---|---|
| Own-asset audit | Scanning repositories, organizations, and code assets **you own or manage**, to find credentials committed by accident |
| Authorized security assessment | Penetration tests, red-team exercises, and security audits carried out under **explicit written authorization** from the asset owner |
| Leak incident response | Assessing the impact after your own credentials leak (you must also hold the right to act on the affected assets) |
| Security research and teaching | Studying leak-detection techniques and validating detection rules in a **self-built test environment** |

**Scope binding**: for an authorized assessment, use `--target-org` / `--target-repo` to limit remote search
to the client's assets and `--scan-local` to limit it to an authorized directory — the scan scope must match the
authorized scope one-to-one, which also serves as the scope statement in a penetration test report.

## 2. Explicitly prohibited use cases

- ❌ Bulk-scanning other people's repositories, Gists, Pastebin, FOFA, and similar sources to **collect** credentials
- ❌ **Validating** a key found on an asset you are not authorized to test (even just "checking whether it works")
- ❌ Using, reselling, or distributing any credential found by a scan
- ❌ Circumventing GitHub's or cloud vendors' rate limits and anti-abuse mechanisms
- ❌ Scanning without follow-up — finding a leaked credential and not notifying its owner

## 3. Correct handling when you find a leaked credential

1. **Notify the owner**: tell them via a repository issue, a private contact channel, or the platform's official channel (do not paste the full key)
2. **Do not use it, do not keep it**: checking "whether it works" is itself unauthorized access, and may break the law
3. **Report to the platform**: GitHub users can use [Secret Scanning alerts](https://docs.github.com/code-security/secret-scanning/managing-alerts-from-secret-scanning);
   most providers (AWS, OpenAI, and others) have joined GitHub's [partner program](https://docs.github.com/code-security/secret-scanning/introduction/supported-secret-scanning-patterns), so a leak is automatically reported to them and the key revoked
4. **Check your own projects**: install [gitleaks](https://github.com/gitleaks/gitleaks) or
   [TruffleHog](https://github.com/trufflesecurity/trufflehog) on your repositories for continuous detection, plus a pre-commit hook

## 4. Legal boundaries (not legal advice; for reference only)

- **China**: Article 285 of the Criminal Law (illegally obtaining computer information system data) and Article 286 (damaging computer
  information systems); the Cybersecurity Law and the Data Security Law both constrain unauthorized access and data acquisition.
  "The key was publicly leaked" is **not** a defense for lawful access — using a leaked credential to call an API is unauthorized access.
- **GitHub ToS**: automated bulk scraping is governed by the API terms; searching for the purpose of collecting credentials may be
  judged abuse and get the account banned.
- **Other jurisdictions**: the US CFAA, the EU NIS2/GDPR, and similar laws carry criminal or administrative liability for unauthorized access.

## 5. Built-in boundary mechanisms in this tool

| Mechanism | Location | Effect |
|---|---|---|
| Startup confirmation | `use_boundary.py`, the only implementation in `main_v2.2.py` | Does not start without boundary confirmation. The other main files only forward to it |
| Remote scope | `require_remote_scope` | No GitHub search is started without `--target-org` or `--target-repo` |
| Public-source switch | `--allow-public-sources` | Sources that cannot be limited to one organization are off by default |
| Encrypted database writes | `storage_encryption_ready` | Requires `DB_ENCRYPTION_KEY` before writing scan results, or an explicit `--allow-plaintext-db` |
| `PROTECTED_DOMAINS` | `config.py` | Official API domains are excluded from the circuit breaker (less interference with official services) |
| SSRF protection | `validator_optimized.py` `_is_likely_valid_relay` | Blocks validation requests to intranet/localhost addresses |
| Entropy filter + blacklist | `scanner.py` | Test/example keys and documentation paths are not stored |
| Static encryption | `key_vault.py` (`DB_ENCRYPTION_KEY`) | The results database is not stored in plaintext, so it is less likely to become a leak source itself |
| Dashboard authentication | `web_dashboard.py` (`DASHBOARD_TOKEN`) | Results are masked by default; export is encrypted |

## 6. The one-line principle

> **The purpose of scanning is "to make your assets safer", not "to turn other people's assets into your resources".**
> If you have to do something in secret, it is probably out of bounds.
