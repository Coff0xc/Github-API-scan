# Agent Pipeline

Grok Bot and Muse only read this findings file, then write disposition status back into it. They do not run scans, do not receive plaintext keys, and do not receive `DASHBOARD_TOKEN`.

## Findings file

```bash
python main_v2.2.py --authorized --findings-json findings.json
```

The `schema` in `findings.json` is `findings.v1`. Each record has only these fields:

| Field | Meaning |
|---|---|
| `fingerprint` | SHA-256 of the key, 64 hex characters. Used to write status back |
| `platform` | Platform name |
| `preview` | Masked preview |
| `repo` | `owner/name`; for a Gist, `gist:user`. Empty when it cannot be parsed |
| `path` | File path. Empty when it cannot be parsed |
| `commit` | Commit or branch name. When the link uses a branch, this is the branch name |
| `location` | Original link |
| `disposition` | `open`, `notified`, `rotated`, `false_positive` |
| `found_time` | Time it was stored |

The same data can also be read from the local dashboard: `GET /api/findings`. That endpoint has no reveal option.

## Writing status back

An agent only changes `disposition`; the other fields can be left as they are. Save the updates as `dispositions.json`:

```json
{
  "updates": [
    {"fingerprint": "<64 hex>", "disposition": "notified"}
  ]
}
```

Write them back to the database:

```bash
python main_v2.2.py --authorized --apply-dispositions dispositions.json --findings-json findings.json
```

A single record also works:

```bash
python main_v2.2.py --authorized --set-disposition <fingerprint> rotated
```

## How agents use it

Grok Bot's scheduled job reads `findings.json` or `GET /api/findings`, groups rows by `repo`, drafts a note to the maintainer, and — after a person confirms it — marks the matching fingerprints as `notified`.

Muse reads the same file and builds your own to-do list. Do not hand it the database, `DB_ENCRYPTION_KEY`, or `DASHBOARD_TOKEN`. That token can open the plaintext view on the dashboard.
