# Web Dashboard Guide

## Overview

The Web Dashboard provides a modern browser-based interface for monitoring and managing API key scanning results.

## Features

- 📊 **Real-time Statistics** - Live view of scanning progress and results
- 📈 **Interactive Charts** - Platform distribution and status breakdown
- 🔍 **Search & Filter** - Find keys by status, platform, or keyword
- 📥 **Export** - Download results as JSON
- 🎨 **Modern UI** - Responsive design works on desktop and mobile

## Quick Start

### 1. Install Dependencies

```bash
pip install flask flask-cors
```

Or install all dependencies:

```bash
pip install -r requirements.txt
```

### 2. Start the Dashboard

```bash
python web_dashboard.py
```

The dashboard will be available at: **http://127.0.0.1:5000**

### 3. Run Scanner (Optional)

In another terminal, start the scanner:

```bash
python main_v2.2.py
```

The dashboard will automatically display results from the database.

## Usage

### Navigation

- **Stats Cards** - Overview of total, valid, invalid, and high-value keys
- **Platform Chart** - Bar chart showing key distribution by platform
- **Status Chart** - Pie chart showing valid/invalid/quota breakdown
- **Filters** - Filter by status (valid/invalid/quota) and platform
- **Search** - Search keys by API key or source URL
- **Export** - Download filtered results as JSON

### Filtering

1. **By Status:**
   - All - Show all keys
   - Valid - Only valid keys
   - Invalid - Only invalid keys
   - Quota Exceeded - Keys that hit rate limits

2. **By Platform:**
   - Select from dropdown (OpenAI, Anthropic, etc.)

3. **By Search:**
   - Type in search box to filter by key or URL
   - Auto-updates after 500ms

### Export

Click the **Export** button to download current filtered results as JSON.

## Architecture

```
web_dashboard.py          # Flask backend
├── templates/
│   └── dashboard.html    # HTML template
├── static/
│   ├── css/
│   │   └── dashboard.css # Styles
│   └── js/
│       └── dashboard.js  # Frontend logic
```

## API Endpoints

### GET /api/stats
Get current statistics including:
- Total keys, valid, invalid, quota exceeded
- High-value key count
- Top platforms

**Response:**
```json
{
  "total_keys": 1523,
  "valid_keys": 245,
  "invalid_keys": 1200,
  "quota_exceeded": 78,
  "high_value_keys": 42,
  "top_platforms": [
    {"platform": "openai", "count": 123},
    {"platform": "anthropic", "count": 45}
  ]
}
```

### GET /api/keys
Get keys with filtering and pagination.

**Query Parameters:**
- `status` - Filter by status (valid/invalid/quota_exceeded)
- `platform` - Filter by platform
- `search` - Search in key or URL
- `limit` - Results per page (default: 100)
- `offset` - Pagination offset

**Response:**
```json
{
  "keys": [
    {
      "platform": "openai",
      "api_key": "sk-proj-...",
      "status": "valid",
      "info": "有效",
      "source_url": "https://github.com/...",
      "found_time": "2026-07-29 12:00:00"
    }
  ],
  "total": 245
}
```

### GET /api/platforms
Get list of all platforms in database.

**Response:**
```json
["openai", "anthropic", "gemini", "azure"]
```

### GET /api/export
Export filtered keys to JSON file.

**Query Parameters:**
- Same as `/api/keys` (status, platform)

## Configuration

### Change Host/Port

Edit `web_dashboard.py`:

```python
if __name__ == '__main__':
    run_server(host='0.0.0.0', port=8080)  # Listen on all interfaces
```

### Database Path

By default uses `leaked_keys.db` in current directory.

Change in `web_dashboard.py`:

```python
db_reader = DatabaseReader(db_path='path/to/your/database.db')
```

## Integration with Scanner

The dashboard reads from the same SQLite database used by the scanner.

**Standalone mode:** Dashboard can run independently and show historical results

**Live mode:** Run both scanner and dashboard simultaneously for real-time monitoring

## Troubleshooting

### Port Already in Use

Change the port:
```python
run_server(port=8080)
```

### Database Not Found

Make sure `leaked_keys.db` exists:
```bash
ls leaked_keys.db
```

Run the scanner first to create the database:
```bash
python main_v2.2.py
```

### No Data Showing

Check if database has data:
```bash
python check_db.py
```

### Charts Not Loading

Make sure Chart.js CDN is accessible. Check browser console for errors.

## Security Notes

- Dashboard is for **local use only** by default (127.0.0.1)
- Do not expose to public internet without authentication
- API keys are masked in the UI but full keys are in database
- Use caution when exporting data

## Performance

- Auto-refresh: Stats every 5s, keys every 10s
- Pagination: 100 keys per page
- Database queries are optimized with indexes
- Charts update in real-time without page reload

## Browser Compatibility

Tested on:
- Chrome/Edge 90+
- Firefox 88+
- Safari 14+

## Next Steps

- Add authentication for multi-user access
- WebSocket support for real-time updates
- More detailed analytics and trends
- Dark mode toggle
- Customizable refresh intervals

---

**Status:** ✅ Production ready  
**Version:** 1.0  
**Last Updated:** 2026-07-29
