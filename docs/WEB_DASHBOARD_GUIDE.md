# Web dashboard

The page at `http://127.0.0.1:5000` is the findings list. It shows a fingerprint, a platform, a masked preview, a location, and a disposition. It does not show a key table, a balance, or a high-value count, and there is no export button on the page.

The header switches **EN / 中文**. English is the default unless the browser language is Chinese or the URL has `?lang=en` or `?lang=zh`.

## Start it

```bash
pip install -r requirements.txt
python web_dashboard.py
```

The process binds `DASHBOARD_HOST`, which defaults to `127.0.0.1`, on port 5000. The database is `DB_PATH` or `leaked_keys.db`.

Run a scan in another terminal if you want new rows. The page reads the same SQLite file the scanner writes, and it also works on a database you already have.

```bash
python main_v2.2.py --authorized --target-org your-org
```

## What you can do on the page

The top counts are all rows, open, notified, and rotated. Under that, a bar chart is the platform mix and a doughnut is disposition. Filters are disposition, platform, and a search across fingerprint, preview, and location. The table pages 50 rows at a time. Stats refresh every 5 seconds, the table every 10.

The fingerprint cell is shortened. The full 64 hex characters are on the tooltip. That full value is what a disposition change sends.

Paste `DASHBOARD_TOKEN` into the token field. The browser keeps it in `sessionStorage` and sends it only as `X-API-Token`. The body of the update is the fingerprint and the new disposition. The response echoes those two fields and `ok`. It does not echo a key.

## HTTP API

| Call | Auth | Body |
| --- | --- | --- |
| `GET /` | none | The findings page. |
| `GET /api/findings` | none | `findings.v1`. Any `reveal` parameter is ignored. |
| `GET /api/stats` | none | Totals, disposition counts, top platforms. `high_value_keys` may still be present for old rows. |
| `GET /api/platforms` | none | Platform names in the database. |
| `POST /api/findings/disposition` | `X-API-Token` | `{ "fingerprint": "<64 hex>", "disposition": "rotated" }`. |
| `GET /api/keys` | token only when `reveal=1` | Masked rows by default. |
| `GET /api/export` | token, and the token must be configured | Fernet bytes. `mask=1` returns masked JSON. |
| `POST /api/stats/update` | token | Progress the scanner pushes into the page. |

Missing header: 401. Token not configured: 403, and export is off. A wrong token is 401 until the same IP has failed 10 times in 60 seconds, then 429. The limiter uses the connecting address, not `X-Forwarded-For`.

`GET /api/findings` is open on purpose so an agent on the same machine can read masked rows. Do not publish the port. Binding `DASHBOARD_HOST` to anything other than loopback puts masked findings, and any unlocked export, on the network.

Export encryption uses PBKDF2-HMAC-SHA256 from `EXPORT_KEY`, or from `DASHBOARD_TOKEN` if export key is unset. The salt is `github-api-scan/export/v1`, 200,000 rounds.

## Layout

```text
web_dashboard.py
templates/dashboard.html
static/css/dashboard.css
static/js/dashboard.js
```

The browser loads Chart.js from a CDN. If the charts stay empty, the page itself is fine and the CDN was blocked.

## When it looks empty

The database file has to be the one the scanner wrote. `python main_v2.2.py --stats` prints counts from the default path. If the scan used `--db other.db`, start the panel with `DB_PATH` pointing at that file.

Port 5000 in use means another process has it. Stop that process, or call `run_server(port=5001)` from a one-off command. Do not switch the bind address to `0.0.0.0` to "fix" an empty page.
