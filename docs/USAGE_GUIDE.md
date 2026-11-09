# Using the scanner

One command starts a scan: `python main_v2.2.py`. A remote search does not run until you name an organization or an `owner/name` repository. While it runs, the terminal shows progress and the latest findings. When it finishes, read `findings.json` or the local dashboard. Those are the records you keep.

## Configure a token

Create a classic token at [github.com/settings/tokens](https://github.com/settings/tokens) with read access to the repositories you are allowed to audit.

```python
# config_local.py, gitignored
GITHUB_TOKENS = [
    "ghp_your_token_here",
]
```

Or export `GITHUB_TOKENS`. Also set `DB_ENCRYPTION_KEY` before a scan that writes the database. Without it, the scan stops unless you pass `--allow-plaintext-db`.

## Run

```bash
python main_v2.2.py --authorized --target-org your-org
python main_v2.2.py --authorized --target-repo owner/name
python main_v2.2.py --authorized --scan-local D:\repos\target
```

`--authorized` confirms [AUTHORIZED_USE.md](../AUTHORIZED_USE.md). In CI, set `SCANNER_AUTHORIZED=1`.

Public sources such as Gist and Pastebin stay off unless the written scope includes them. Then you add both the source flag and `--allow-public-sources`.

## What the terminal shows

The header is **AI API Key Scanner**. Next to it are the run state, which GitHub token is in use, and whether traffic goes through a proxy.

The stats panel counts files scanned, candidates found, valid hits, invalid results, quota hits, connection errors, and the validation queue.

The table under that is titled **发现记录**. The columns are platform, masked preview, status, and location. A row appears when a check comes back valid. There is no balance column and no high-value marker. The log beside it is the same run in text: searches, skips, and valid or quota lines.

The picture below is the shape of that screen, not a capture of a real scan.

```text
┌ AI API Key Scanner ──────────────────────────────┐
│ 运行中 │ Tokens: 1/2 │ 代理: 直连模式            │
├──────────────────────┬───────────────────────────┤
│ 扫描文件          40 │ [10:01:12] [SCAN] acme    │
│ 有效命中           2 │ [10:01:40] [VALID] openai │
├──────────────────────┴───────────────────────────┤
│ 发现记录                                          │
│ 平台     预览            状态    位置             │
│ openai   sk-pro...k9Q2   valid   acme-labs/...env │
└───────────────────────────────────────────────────┘
```

## After the scan

The process writes `findings.json` in the working directory. Each record has a fingerprint, platform, masked preview, location, and disposition. Open the same rows in a browser:

```bash
python web_dashboard.py
```

The page is `http://127.0.0.1:5000`. Mark a row rotated only after the key is revoked. See [WEB_DASHBOARD_GUIDE.md](WEB_DASHBOARD_GUIDE.md).

Other ways to read what was stored:

```bash
python main_v2.2.py --stats
python main_v2.2.py --findings-json findings.json
python main_v2.2.py --export results.txt --status valid
python main_v2.2.py --authorized --report threat.md
```

Text and CSV are masked. `--reveal` puts full keys in an export. Do not commit that file.

## When something fails

**GitHub tokens are not configured.** Put a token in `config_local.py` or `GITHUB_TOKENS`.

**Rate limit.** Add another token, or wait for the window to reset.

**The scan refuses to start.** A remote search needs `--target-org` or `--target-repo`. A write needs `DB_ENCRYPTION_KEY` or `--allow-plaintext-db`.

**No findings.** That can be the truth for the repository you named. `python main_v2.2.py --stats` shows what is already in the database. Widening to public paste sites is a scope decision, not a way to debug an empty org.

**The terminal table is empty but stats show quota hits.** Quota results are counted in the stats panel and in `findings.json`. The live table lists valid hits.

## Boundary

Scan assets you own, or assets the owner has authorized you to test. Do not use a key the scan found. The full policy is [AUTHORIZED_USE.md](../AUTHORIZED_USE.md). The shorter path is [QUICKSTART.md](QUICKSTART.md). The map of the pipeline is [../README.md](../README.md).
