"""
Web Dashboard for API Key Scanner

A Flask-based web interface providing:
- Real-time scanning statistics
- Valid key visualization
- Search and filter capabilities
- Export functionality
- Live log streaming
"""

from flask import Flask, render_template, jsonify, request, send_file
from flask_cors import CORS
import sqlite3
import json
from datetime import datetime
from pathlib import Path
import threading
import queue

app = Flask(__name__)
CORS(app)

# Global state
stats_queue = queue.Queue()
current_stats = {
    'total_scanned': 0,
    'total_keys_found': 0,
    'valid_keys': 0,
    'invalid_keys': 0,
    'quota_exceeded': 0,
    'connection_errors': 0,
    'is_running': False,
    'current_keyword': '',
}


class DatabaseReader:
    """Read-only database access for dashboard"""

    def __init__(self, db_path='leaked_keys.db'):
        self.db_path = db_path

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_stats(self):
        """Get overall statistics"""
        conn = self.get_connection()
        cursor = conn.cursor()

        stats = {
            'total_keys': cursor.execute('SELECT COUNT(*) FROM leaked_keys').fetchone()[0],
            'valid_keys': cursor.execute('SELECT COUNT(*) FROM leaked_keys WHERE status = "valid"').fetchone()[0],
            'invalid_keys': cursor.execute('SELECT COUNT(*) FROM leaked_keys WHERE status = "invalid"').fetchone()[0],
            'quota_exceeded': cursor.execute('SELECT COUNT(*) FROM leaked_keys WHERE status = "quota_exceeded"').fetchone()[0],
            'high_value_keys': cursor.execute('SELECT COUNT(*) FROM leaked_keys WHERE is_high_value = 1').fetchone()[0],
        }

        # Platform breakdown
        cursor.execute('''
            SELECT platform, COUNT(*) as count
            FROM leaked_keys
            WHERE status = "valid"
            GROUP BY platform
            ORDER BY count DESC
            LIMIT 10
        ''')
        stats['top_platforms'] = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return stats

    def get_keys(self, status=None, platform=None, limit=100, offset=0, search=None):
        """Get keys with filtering"""
        conn = self.get_connection()
        cursor = conn.cursor()

        query = 'SELECT * FROM leaked_keys WHERE 1=1'
        params = []

        if status:
            query += ' AND status = ?'
            params.append(status)

        if platform:
            query += ' AND platform = ?'
            params.append(platform)

        if search:
            query += ' AND (api_key LIKE ? OR source_url LIKE ?)'
            params.extend([f'%{search}%', f'%{search}%'])

        query += ' ORDER BY found_time DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])

        cursor.execute(query, params)
        keys = [dict(row) for row in cursor.fetchall()]

        # Get total count
        count_query = query.split('ORDER BY')[0].replace('SELECT *', 'SELECT COUNT(*)')
        cursor.execute(count_query, params[:-2])
        total = cursor.fetchone()[0]

        conn.close()
        return {'keys': keys, 'total': total}

    def get_platforms(self):
        """Get list of platforms"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT platform FROM leaked_keys ORDER BY platform')
        platforms = [row[0] for row in cursor.fetchall()]
        conn.close()
        return platforms


db_reader = DatabaseReader()


# ============================================================================
#                              Routes
# ============================================================================

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('dashboard.html')


@app.route('/api/stats')
def api_stats():
    """Get current statistics"""
    db_stats = db_reader.get_stats()
    db_stats.update(current_stats)
    return jsonify(db_stats)


@app.route('/api/keys')
def api_keys():
    """Get keys with filtering"""
    status = request.args.get('status')
    platform = request.args.get('platform')
    limit = int(request.args.get('limit', 100))
    offset = int(request.args.get('offset', 0))
    search = request.args.get('search')

    result = db_reader.get_keys(status, platform, limit, offset, search)
    return jsonify(result)


@app.route('/api/platforms')
def api_platforms():
    """Get list of platforms"""
    platforms = db_reader.get_platforms()
    return jsonify(platforms)


@app.route('/api/export')
def api_export():
    """Export keys to JSON"""
    status = request.args.get('status')
    platform = request.args.get('platform')

    result = db_reader.get_keys(status, platform, limit=10000)

    filename = f'export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    filepath = Path(filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(result['keys'], f, indent=2, ensure_ascii=False)

    return send_file(filepath, as_attachment=True)


@app.route('/api/stats/update', methods=['POST'])
def api_stats_update():
    """Update current stats (called by scanner)"""
    global current_stats
    data = request.get_json()
    current_stats.update(data)
    return jsonify({'status': 'ok'})


def run_server(host='127.0.0.1', port=5000):
    """Run Flask server"""
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == '__main__':
    print("Starting Web Dashboard...")
    print("Access at: http://127.0.0.1:5000")
    run_server()
