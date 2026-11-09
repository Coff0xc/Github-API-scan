# Local scanning

`--scan-local` is how you audit a checkout you already have: the working tree, plus every distinct Git blob in the history. GitHub code search only sees what the default branch shows today. A key that was committed and later deleted is still in `.git` until someone rewrites history.

The same validators, database, findings file, and notice path are used as for a remote scan. The result you hand over is still `findings.json`, not a ranked list of balances.

## Commands

```bash
python main_v2.2.py --authorized --scan-local D:\customer-repo
python main_v2.2.py --authorized --scan-local D:\customer-repo --no-git-history
python main_v2.2.py --authorized --scan-local D:\customer-repo --report threat.md
python main_v2.2.py --authorized --report threat.md
python main_v2.2.py --authorized --report threat.md --reveal-report
```

`--reveal-report` prints full keys into the Markdown. Keep that file out of git and inside the written scope of the engagement.

A remote search of the same customer is a separate command, and it still needs a scope:

```bash
python main_v2.2.py --authorized --target-org customer-org
python main_v2.2.py --authorized --target-repo customer-org/api-server
```

## What the history walk actually does

```text
working tree ── files that are on disk now
git history ── git rev-list --all --objects
               git cat-file --batch, one read per blob hash
               commit messages, separately
        │
        ▼
extract, pair the key with base_url, drop samples
        │
        ▼
validation queue → SQLite → findings.json
```

Identical bytes in two paths are one blob. The hash is stored in `scanned_blobs`, and the next run does not read it again. A tracked file whose blob was already scanned is skipped in the worktree walk. Blobs over the size cap (500 KB unless `config.yaml` says otherwise) and blobs that look binary are remembered and skipped.

A deleted file still shows up, because the blob remains reachable from an old commit. The location looks like:

```text
local://git@15f000ba86:app/settings.py
local://app/settings.py
local://git@15f000ba86:commit-message
```

The short hash is the first 10 characters of the blob or commit. Pairing uses the file text around the key, so `OPENAI_BASE_URL=` on the previous line stays attached. That is the reason the walker reads the blob instead of a zero-context diff line.

## Threat report

`--report` writes Markdown for an authorized assessment. It counts rows in the database, then lists credentials whose status is `valid` or `quota_exceeded`. Both are live. Rows are ordered by the time they were found, newest first. Each row has the platform, status, masked preview, location, and time. Model tier and RPM appear only when that check returned them, and they do not change the order. `--reveal-report` replaces the preview with the full key.

The closing section of the report is the remediation list: revoke the key, remove it from Git history with something like `git filter-repo`, check the provider console for use, and put a pre-commit hook on the repository.

## A scoped engagement

```bash
export SCANNER_AUTHORIZED=1
export DB_ENCRYPTION_KEY="a-long-random-passphrase"

python main_v2.2.py --scan-local D:\customer\monorepo --report P1_local.md
python main_v2.2.py --target-org customer-org --report P2_org.md
python main_v2.2.py --findings-json findings.json
```

PowerShell uses `$env:SCANNER_AUTHORIZED = "1"`. The database is the evidence store. Leave it encrypted, and do not attach `findings.json` or the report to a ticket that other people can read unless the engagement says to.
