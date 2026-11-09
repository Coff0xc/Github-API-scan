**English** · [简体中文](README.zh-CN.md)

# AI API Key Scanner

Find leaked API keys inside a GitHub organization, repository, or local checkout you are allowed to audit. Pair each key with the API address next to it, check it only on that authorized target, and finish with a masked finding you can hand to the owner.

The only entry point is `main_v2.2.py`.

![Python 3.10+](https://img.shields.io/badge/python-3.10+-3776AB?logo=python&logoColor=white)
![License MIT](https://img.shields.io/badge/license-MIT-111827)
![Findings schema](https://img.shields.io/badge/findings-v1-1d4ed8)

<p align="center">
  <img src="assets/screenshot.png" alt="English findings dashboard with fingerprints, platforms, masked previews, locations, and disposition" width="920">
</p>

<p align="center">
  <sub>Local dashboard in English. The rows are example data for a fictional <code>acme-labs</code> organization. Previews are masked. The page does not show a live key, a balance, or a value score.</sub>
</p>

## In one minute

Use this when you are responsible for the code, even if someone else runs the scanner.

1. Point the scan at a GitHub organization, one `owner/name` repository, or a folder on disk that you own or have written permission to test.
2. When it finishes, open `findings.json` or the local dashboard at `http://127.0.0.1:5000`.
3. Each row is one place a credential showed up. You see the service name, a short masked preview, and the file it came from.
4. Tell the owner. The notice contains the platform, the preview, and the location. It does not contain the full key.
5. After the key is revoked, mark that row `rotated`. If the row was a placeholder or a document sample, mark it `false positive`.

A person who never opens a terminal can still read the dashboard. The language switch in the header is **EN / 中文**. English is the default unless the browser language is Chinese, or the page is opened with `?lang=en` or `?lang=zh`.

## Contents

- [What a finding is](#what-a-finding-is)
- [How a scan works](#how-a-scan-works)
- [Install](#install)
- [Configure](#configure)
- [Run](#run)
- [Dashboard](#dashboard)
- [Commands](#commands)
- [Notifications](#notifications)
- [Threat report](#threat-report)
- [Agents](#agents)
- [Platforms](#platforms)
- [Configuration files](#configuration-files)
- [Authorization boundary](#authorization-boundary)
- [Where the code lives](#where-the-code-lives)
- [More documentation](#more-documentation)
- [License](#license)

## What a finding is

The hand-off file is `findings.json`. Its `schema` is `findings.v1`. One object is one appearance of a credential. The same file is what `GET /api/findings` returns. That response has no reveal switch.

| Field | What it tells you |
| --- | --- |
| `fingerprint` | SHA-256 of the key, 64 hex characters. This is the id you use to change disposition. |
| `platform` | Service name, such as `openai`, `anthropic`, `azure`, or `openrouter`. |
| `preview` | Masked form, first 6 characters, an ellipsis, and the last 4. |
| `repo` | `owner/name`. A Gist is `gist:user`. Empty when the URL cannot be parsed. |
| `path` | File path inside that repo. Empty when the URL has no path. |
| `commit` | Commit or branch name taken from the URL. |
| `location` | Original URL or local path. |
| `disposition` | `open`, `notified`, `rotated`, or `false_positive`. |
| `found_time` | When the row was stored. |

```json
{
  "schema": "findings.v1",
  "generated_at": "2026-11-10T08:00:00Z",
  "findings": [
    {
      "fingerprint": "06f934c99f8f30950ff32100387372c829f385d213587e2ebd710e930992099b",
      "platform": "openai",
      "preview": "sk-pro...k9Q2",
      "repo": "acme-labs/billing-api",
      "path": ".env",
      "commit": "4c1e9a2",
      "location": "https://github.com/acme-labs/billing-api/blob/4c1e9a2/.env",
      "disposition": "open",
      "found_time": "2026-11-10T07:40:00"
    }
  ]
}
```

That fingerprint and preview are an illustration. They are not a credential.

| Disposition | Meaning | Who sets it |
| --- | --- | --- |
| `open` | Stored, and nobody has handled it yet. | The scan, by default. |
| `notified` | A configured channel accepted the notice. | The notifier, after a successful send. |
| `rotated` | The key was revoked or replaced. | A person, with `--set-disposition` or the dashboard. |
| `false_positive` | A sample, a placeholder, or not a secret. | A person. |

`findings.json` and `dispositions.json` are gitignored. Do not commit them.

## How a scan works

1. **Search.** A remote scan sends GitHub code-search queries only after you pass `--target-org` or `--target-repo`. Without one of those, no GitHub search request goes out. `--scan-local` reads a directory on disk, including current files and Git history. Each distinct Git blob is parsed once; the next run skips blobs already stored in `scanned_blobs`, and a key already in the database is not sent for validation again.
2. **Pair.** The extractor takes a key and, when the same context has one, the `base_url` beside it. An official API host, an Azure resource, and a relay are then different targets.
3. **Filter.** Entropy checks and a path blocklist drop obvious samples such as `sk-test`, documentation placeholders, and vendor example files.
4. **Validate.** The check runs only against the paired address, and only for an asset you are allowed to test. The stored status is `pending`, `valid`, `invalid`, or `quota_exceeded`. `quota_exceeded` means the credential answered and then hit a limit. It is still a live credential for an authorized assessment.
5. **Store.** With `DB_ENCRYPTION_KEY` set, the `api_key` column is Fernet ciphertext. Deduplication uses the SHA-256 `key_hash`. A scan refuses to write until that key is set, unless you pass `--allow-plaintext-db`. Balance and `is_high_value` are not written on this path.
6. **Hand off.** The scan writes `findings.json`.

Optional pieces sit beside that loop. `AI_FILTER_ENABLED=1` adds a model pass that drops likely false positives. It is off unless you turn it on. Public sources that cannot be limited to one organization — Gist, Pastebin, GitLab Snippets, Searchcode, and GitHub Events — stay off unless you also pass `--allow-public-sources`.

The validator refuses private, link-local, reserved, and multicast addresses, and it refuses a DNS name when any answer is in those ranges. An empty `base_url` means the vendor's own API.

## Install

Python 3.10 or newer.

```bash
git clone https://github.com/Coff0xc/Github-API-scan.git
cd Github-API-scan
pip install -r requirements.txt
```

On Windows, skip `uvloop` if a dependency mentions it. The scanner runs without it.

## Configure

Keep tokens out of the repository. `config_local.py` is gitignored. You can use environment variables instead.

bash:

```bash
export GITHUB_TOKENS="ghp_your_token_here"
export DB_ENCRYPTION_KEY="a-long-random-passphrase"
export DASHBOARD_TOKEN="another-random-passphrase"
```

PowerShell:

```powershell
$env:GITHUB_TOKENS = "ghp_your_token_here"
$env:DB_ENCRYPTION_KEY = "a-long-random-passphrase"
$env:DASHBOARD_TOKEN = "another-random-passphrase"
```

Or copy `config_local.py.example` to `config_local.py` and fill in `GITHUB_TOKENS` there.

The GitHub token needs permission to search the organization or repository you are auditing. For a classic token, that is the repository scope that can read those repositories. Several tokens can share the search rate limit. Put them in `GITHUB_TOKENS`, separated by commas, or as a list in `config_local.py`.

`DB_ENCRYPTION_KEY` encrypts keys at rest. `DASHBOARD_TOKEN` is required to change a disposition from the browser. Reading the masked findings list does not send the token. Treat both values like passwords: long, random, and absent from chat logs and tickets.

## Run

Confirm [AUTHORIZED_USE.md](AUTHORIZED_USE.md) with `--authorized`, or set `SCANNER_AUTHORIZED=1` in CI. In an interactive terminal, the program asks you to type `y` when neither is set. Docker Compose does not turn that switch on for you, and it does not choose an organization.

```bash
python main_v2.2.py --authorized --target-org your-org
python main_v2.2.py --authorized --target-repo owner/name
python main_v2.2.py --authorized --scan-local D:\repos\target
```

`--target-repo` must be `owner/name`. It wins over `--target-org` when both are present.

`--scan-local` walks the working tree and the Git history, so a key that was deleted in a later commit can still appear. `--no-git-history` keeps the scan on the files that are there now.

Each of those commands writes `findings.json` in the working directory when it finishes. Another path:

```bash
python main_v2.2.py --authorized --target-org your-org --findings-json reports/findings.json
```

`--findings-json` alone, with no scan target, exports the database you already have and then exits.

## Dashboard

```bash
python web_dashboard.py
```

Open `http://127.0.0.1:5000`. The host is `127.0.0.1` unless you set `DASHBOARD_HOST`. Binding any other address puts the panel on the network. Do that only with a strong `DASHBOARD_TOKEN`.

The home page is the findings list in the screenshot:

- Counts for all rows, open, notified, and rotated.
- Platform counts and a disposition chart.
- Filters for disposition, platform, and a search across fingerprint, preview, and location.
- A table of fingerprint, platform, masked preview, repository and path, and disposition.
- **EN / 中文** in the header. The choice is remembered in this browser.

The fingerprint column shows a short form. The full 64 hex characters are on the row tooltip and are the value you submit.

To change a disposition in the browser, paste `DASHBOARD_TOKEN` into the token field. The browser stores it in `sessionStorage` and sends it as the `X-API-Token` header. The request body is the fingerprint and the new disposition. The response echoes those two fields and `ok`. It does not echo a key. A missing token is HTTP 401. An unset server token rejects protected calls with HTTP 403. A wrong token is rate-limited with HTTP 429.

`GET /api/findings` is the masked list and does not require the token. There is no export button on this page.

The database file defaults to `leaked_keys.db`. `DB_PATH` selects another file for both the scanner and the dashboard.

## Commands

Everyday use:

```bash
python main_v2.2.py --stats
python main_v2.2.py --findings-json findings.json
python main_v2.2.py --set-disposition <64-hex-fingerprint> notified
python main_v2.2.py --set-disposition <64-hex-fingerprint> rotated
python main_v2.2.py --apply-dispositions dispositions.json

python main_v2.2.py --export results.txt --status valid
python main_v2.2.py --export-csv results.csv --status valid
python main_v2.2.py --export-encrypted secure.bin

python main_v2.2.py --authorized --report threat.md
```

Text and CSV are masked. `--reveal` prints full keys into an export. Use it only inside an authorized assessment, and do not commit the file.

| Flag | Effect |
| --- | --- |
| `--authorized` | Confirm the use boundary for this process. |
| `--target-org ORG` | Limit GitHub search to one organization. |
| `--target-repo OWNER/REPO` | Limit GitHub search to one repository. |
| `--scan-local DIR` | Scan a local directory and its Git history. |
| `--no-git-history` | With `--scan-local`, skip older commits. |
| `--findings-json FILE` | Write the masked findings document. |
| `--set-disposition FINGERPRINT STATUS` | Set one row to `open`, `notified`, `rotated`, or `false_positive`. |
| `--apply-dispositions FILE` | Apply a JSON list of fingerprint updates. |
| `--stats` | Print database counts. |
| `--export FILE` | Masked text export. `--status valid` or `quota_exceeded` filters it. |
| `--export-csv FILE` | Masked CSV export. |
| `--export-encrypted FILE` | Fernet export. The key is written beside it. |
| `--decrypt FILE` | Decrypt a file produced by `--export-encrypted`. |
| `--key-file KEY` | Key file for `--decrypt`. |
| `--reveal` | Put full keys in a text or CSV export. |
| `--report FILE` | Write a Markdown threat report. |
| `--reveal-report` | Include full keys in that report. |
| `--db FILE` | Database path. Default `leaked_keys.db`. |
| `--proxy URL` | HTTP proxy for outbound calls. |
| `--allow-plaintext-db` | Allow a scan to store keys without `DB_ENCRYPTION_KEY`. |
| `--allow-public-sources` | Allow Gist, Pastebin, GitLab, Searchcode, and Events. |
| `--gist` `--pastebin` `--gitlab` `--searchcode` `--realtime` | Turn on one of those sources. Still needs `--allow-public-sources`. |
| `--all-sources` | Turn all of them on. Still needs `--allow-public-sources`. |
| `--pastebin-key KEY` | Pastebin Pro API key, used only if Pastebin is enabled. |
| `--no-cache` | Skip the validation cache for this run. |
| `--no-monitor` | Skip the performance monitor. |
| `--no-dynamic-queue` | Keep the queue size fixed. |

An agent disposition file looks like this:

```json
{
  "updates": [
    {"fingerprint": "<64 hex>", "disposition": "rotated"}
  ]
}
```

A bare array, or an object with `findings`, is accepted as well. Extra fields are ignored. The fingerprint still has to be 64 hex characters, and the disposition has to be one of the four names.

## Notifications

If you configure a channel, a `valid` or `quota_exceeded` result can send a disclosure notice: platform, masked preview, and location, plus a line that says the notice has no full key and no balance. When a channel accepts it, the row becomes `notified`.

Channels are read from `notify_config.yaml` (or `NOTIFY_CONFIG`) and from the environment: `DISCORD_WEBHOOK`, `SLACK_WEBHOOK`, `TELEGRAM_BOT_TOKEN`, `FEISHU_WEBHOOK`, `DINGTALK_WEBHOOK`, `SERVERCHAN_KEY`, `BARK_DEVICE_KEY`. If none of those are set, nothing is sent and the row stays `open`. Copy `notify_config.example.yaml` when you want a file. Details are in [docs/NOTIFY_README.md](docs/NOTIFY_README.md).

`rotated` stays a manual mark. The tool cannot see whether a vendor console actually revoked the key.

## Threat report

```bash
python main_v2.2.py --authorized --report threat.md
python main_v2.2.py --authorized --scan-local D:\repos\target --report threat.md
```

The report is for an authorized assessment. It treats `valid` and `quota_exceeded` as live credentials and it is masked by default. `--reveal-report` prints full keys into the Markdown file. Keep that file out of git.

## Agents

Grok Bot and Muse read the findings file and write dispositions back. They do not start a scan. They do not receive raw keys, `DB_ENCRYPTION_KEY`, or `DASHBOARD_TOKEN`. The contract is in [docs/AGENT_PIPELINE.md](docs/AGENT_PIPELINE.md).

## Platforms

Rules exist for OpenAI, Anthropic, Gemini, Azure OpenAI, xAI, Meta Llama, OpenRouter, Portkey, LiteLLM, Cloudflare AI, AWS Bedrock, Vertex AI, Alibaba Cloud, Volcano Engine, Tencent Hunyuan, Baidu Qianfan, DeepSeek, Moonshot, Zhipu, Groq, Cohere, Mistral, Hugging Face, Together, Replicate, Perplexity, and Fireworks.

A provider without its own rule can still match the generic pattern. GitHub tokens, AWS keys, and Stripe keys are in that generic set.

Naming a platform here means the scanner knows a shape and a place to check. It does not mean a key from an unapproved repository should be checked.

## Configuration files

Later sources override earlier ones: built-in defaults, then `config.yaml`, then `config_local.py`, then command-line flags.

`config.yaml` is read for entropy threshold, concurrency, blocklists, and batch size. Edit it for how hard the scanner works. Put secrets in the environment or in `config_local.py`, not in `config.yaml`.

## Authorization boundary

Allowed work is an audit of assets you own, an assessment with written permission from the owner, emergency handling of your own credentials where you can still revoke them, and detection research inside a lab you control.

Do not use the scanner to collect keys from repositories you are not allowed to test. Do not validate someone else's key. Do not use a key the scan found, and do not pass it on. When you find a leak, tell the owner without pasting the secret.

The program enforces the scope checks above. The policy text, including what to do after a find, is [AUTHORIZED_USE.md](AUTHORIZED_USE.md). How to report a bug in this project without pasting keys, database files, or tokens is [SECURITY.md](SECURITY.md).

## Where the code lives

```
main_v2.2.py            only entry point
scanner.py              search, and key / base_url pairing
validator_optimized.py  validation loop used by the entry point
validator.py            circuit breaker, result types, request
findings_feed.py        masked findings document
database.py             SQLite
key_vault.py            encryption at rest
threat_report.py        assessment report
web_dashboard.py        local dashboard
notifier_v2.py          notification channels
use_boundary.py         startup confirmation and scope checks
```

## More documentation

- [AUTHORIZED_USE.md](AUTHORIZED_USE.md)
- [SECURITY.md](SECURITY.md)
- [docs/QUICKSTART.md](docs/QUICKSTART.md)
- [docs/USAGE_GUIDE.md](docs/USAGE_GUIDE.md)
- [docs/LOCAL_SCANNING.md](docs/LOCAL_SCANNING.md)
- [docs/AGENT_PIPELINE.md](docs/AGENT_PIPELINE.md)
- [docs/DOCKER_GUIDE.md](docs/DOCKER_GUIDE.md)
- [docs/NOTIFY_README.md](docs/NOTIFY_README.md)
- [docs/AI_ASSISTED_ANALYSIS.md](docs/AI_ASSISTED_ANALYSIS.md)

## License

MIT. See [LICENSE](LICENSE).
