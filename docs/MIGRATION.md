# Migration

The only entry point now is `main_v2.2.py`. `main.py`, `main_optimized.py`, and `main_v2.1.py` have been deleted — do not rename or call them again.

Old commands only need the entry point swapped, plus the scope that is now mandatory:

```bash
python main_v2.2.py --authorized --target-org your-org
python main_v2.2.py --authorized --target-repo owner/name
```

Writing to the database requires `DB_ENCRYPTION_KEY`. Add `--allow-plaintext-db` only when you explicitly accept plaintext storage on disk.

Gist, Pastebin, GitLab, Searchcode, and Events are off by default; add `--allow-public-sources` to enable them. These sources are not limited by `org:` / `repo:` — read [AUTHORIZED_USE.md](../AUTHORIZED_USE.md) before using them.

The old "3–5×" and "100–430×" figures were not end-to-end measurements and cannot be used to compare versions.
