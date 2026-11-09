# Quick start

One entry point: `main_v2.2.py`. A remote search runs only inside the organization or repository you name.

## Install

Python 3.10 or newer.

```bash
git clone https://github.com/Coff0xc/Github-API-scan.git
cd Github-API-scan
pip install -r requirements.txt
```

On Windows, skip `uvloop` if a dependency mentions it.

## Configure

Do not commit tokens. Either export them:

```bash
export GITHUB_TOKENS="ghp_your_token_here"
export DB_ENCRYPTION_KEY="a-long-random-passphrase"
export DASHBOARD_TOKEN="another-random-passphrase"
```

or copy `config_local.py.example` to `config_local.py` and set `GITHUB_TOKENS` there. That file is gitignored.

The GitHub token needs read access to the organization or repository you are auditing. `DB_ENCRYPTION_KEY` encrypts keys at rest. Without it, a scan refuses to write unless you pass `--allow-plaintext-db`.

## First scan

Confirm [AUTHORIZED_USE.md](../AUTHORIZED_USE.md) with `--authorized`, or set `SCANNER_AUTHORIZED=1` in CI.

```bash
python main_v2.2.py --authorized --target-org your-org
python main_v2.2.py --authorized --target-repo owner/name
python main_v2.2.py --authorized --scan-local D:\repos\target
```

`--target-repo` is `owner/name`. Without one of those two flags, GitHub search does not start. When the scan finishes it writes `findings.json`: fingerprint, platform, masked preview, location, and disposition. No full key, no balance.

Open the same rows in a browser:

```bash
python web_dashboard.py
```

The page is `http://127.0.0.1:5000`.

## Look at what you already have

```bash
python main_v2.2.py --stats
python main_v2.2.py --findings-json findings.json
python main_v2.2.py --export results.txt --status valid
```

Text and CSV are masked. A full key in an export requires `--reveal`. `findings.json` is for a person or an agent, and it never contains a raw key. See [AGENT_PIPELINE.md](AGENT_PIPELINE.md).

## Read next

- [../README.md](../README.md)
- [../AUTHORIZED_USE.md](../AUTHORIZED_USE.md)
- [USAGE_GUIDE.md](USAGE_GUIDE.md)
- [LOCAL_SCANNING.md](LOCAL_SCANNING.md)
- [WEB_DASHBOARD_GUIDE.md](WEB_DASHBOARD_GUIDE.md)
