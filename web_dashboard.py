"""
Web Dashboard for API Key Scanner (hardened)
============================================

A Flask-based web interface providing:
- Real-time scanning statistics
- Valid key visualization (masked by default)
- Search and filter capabilities
- Encrypted export functionality
- Live log streaming

Security model:
--------------
- DASHBOARD_TOKEN 环境变量设置访问令牌；未设置时进入"只读脱敏模式"，
  Key 永远脱敏显示、导出与 reveal 接口直接禁用。
- 令牌通过 X-API-Token 请求头传递（也接受 ?token= 查询参数，便于浏览器）。
- DASHBOARD_HOST 默认 127.0.0.1；仅在你理解风险时改为 0.0.0.0。
- /api/export 默认返回 Fernet 加密的 JSON（EXPORT_KEY 派生密钥，
  未设置 EXPORT_KEY 时从 DASHBOARD_TOKEN 派生），明文 key 不出网。
- 认证失败按 IP 限速，防暴力枚举。

Decrypt export:
--------------
    python -c "
    import base64,hashlib,sys
    from cryptography.fernet import Fernet
    secret=b'你的EXPORT_KEY或DASHBOARD_TOKEN'
    k=base64.urlsafe_b64encode(hashlib.pbkdf2_hmac('sha256',secret,b'github-api-scan/export/v1',200000))
    print(Fernet(k).decrypt(open(sys.argv[1],'rb').read()).decode())
    " export_xxx.bin
"""

import os
import io
import json
import base64
import hashlib
import hmac
import sqlite3
import time
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, jsonify, request, send_file
from flask_cors import CORS

from key_vault import vault

app = Flask(__name__)

# CORS: 仍开放给本机前端调试；跨域读取 key 类接口受 token 保护
CORS(app)

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

DASHBOARD_TOKEN = os.getenv("DASHBOARD_TOKEN", "").strip()
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "127.0.0.1").strip()
EXPORT_KEY_SECRET = os.getenv("EXPORT_KEY", "").strip() or DASHBOARD_TOKEN

AUTH_ENABLED = bool(DASHBOARD_TOKEN)

# 认证失败限速：每 IP 60 秒内最多 10 次失败
_AUTH_FAIL_LIMIT = 10
_AUTH_FAIL_WINDOW = 60
_auth_failures = defaultdict(deque)

# Global state
stats_queue = None
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

_EXPORT_SALT = b"github-api-scan/export/v1"
_EXPORT_ITERATIONS = 200_000


def _derive_export_key() -> bytes:
    """PBKDF2 派生导出加密密钥（EXPORT_KEY 优先，否则 DASHBOARD_TOKEN）"""
    derived = hashlib.pbkdf2_hmac(
        "sha256", EXPORT_KEY_SECRET.encode("utf-8"), _EXPORT_SALT, _EXPORT_ITERATIONS
    )
    return base64.urlsafe_b64encode(derived)


def _mask_key(api_key: str) -> str:
    """脱敏展示（vault 自动处理密文/明文两种存储形态）"""
    return vault.mask(api_key)


# ---------------------------------------------------------------------------
# 认证
# ---------------------------------------------------------------------------

def _client_ip() -> str:
    return request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()


def _auth_fail_limited(ip: str) -> bool:
    now = time.time()
    window = _auth_failures[ip]
    while window and now - window[0] > _AUTH_FAIL_WINDOW:
        window.popleft()
    return len(window) >= _AUTH_FAIL_LIMIT


def _record_auth_fail(ip: str):
    _auth_failures[ip].append(time.time())


def _auth_gate():
    """
    统一鉴权闸门。返回 None 表示通过；否则返回 (jsonify响应, 状态码)。

    - 未配置 DASHBOARD_TOKEN：受保护接口一律 403（功能禁用）
    - 失败次数超限：429（按 IP 限速）
    - 令牌错误/缺失：401（常量时间比对，不泄漏时序信息）
    """
    if not AUTH_ENABLED:
        return jsonify({'error': '未配置 DASHBOARD_TOKEN，该接口已禁用'}), 403

    supplied = request.headers.get("X-API-Token", "").strip() or request.args.get("token", "").strip()
    if not supplied:
        return jsonify({'error': '缺少令牌（X-API-Token 头或 ?token=）'}), 401

    if hmac.compare_digest(DASHBOARD_TOKEN.encode(), supplied.encode()):
        return None

    ip = _client_ip()
    if _auth_fail_limited(ip):
        return jsonify({'error': '认证失败次数过多，请稍后再试'}), 429
    _record_auth_fail(ip)
    return jsonify({'error': '令牌无效'}), 401


def check_auth() -> bool:
    """兼容判断：鉴权是否通过"""
    return _auth_gate() is None


@app.after_request
def _security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Cache-Control", "no-store")
    return resp


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

    def get_keys(self, status=None, platform=None, limit=100, offset=0, search=None,
                 reveal: bool = False):
        """Get keys with filtering. api_key 默认脱敏，仅显式 reveal 且通过鉴权时返回明文"""
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
            # 明文搜索：对哈希/密文库无法 LIKE，改为按指纹精确匹配或模糊匹配来源
            params.append(vault.hash_key(search))
            query += ' AND (key_hash = ? OR source_url LIKE ?)'
            params.append(f'%{search}%')

        query += ' ORDER BY found_time DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])

        cursor.execute(query, params)
        keys = []
        for row in cursor.fetchall():
            item = dict(row)
            stored = item.get('api_key', '') or ''
            item['api_key'] = vault.decrypt(stored) if reveal else _mask_key(stored)
            keys.append(item)

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


db_reader = DatabaseReader(os.getenv("DB_PATH", "leaked_keys.db"))


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
    try:
        db_stats = db_reader.get_stats()
    except sqlite3.Error:
        db_stats = {}
    db_stats.update(current_stats)
    db_stats['auth_enabled'] = AUTH_ENABLED
    return jsonify(db_stats)


@app.route('/api/keys')
def api_keys():
    """Get keys with filtering（默认脱敏；reveal=1 需令牌）"""
    status = request.args.get('status')
    platform = request.args.get('platform')
    limit = min(int(request.args.get('limit', 100)), 1000)
    offset = max(int(request.args.get('offset', 0)), 0)
    search = request.args.get('search')

    reveal = request.args.get('reveal') in ('1', 'true')
    if reveal:
        gate = _auth_gate()
        if gate:
            return gate

    result = db_reader.get_keys(status, platform, limit, offset, search, reveal=reveal)
    return jsonify(result)


@app.route('/api/findings')
def api_findings():
    """代理只读发现。永远不含明文 Key，忽略任何 reveal 参数。"""
    from findings_feed import build_document
    return jsonify(build_document(db_reader.db_path))


@app.route('/api/platforms')
def api_platforms():
    """Get list of platforms"""
    platforms = db_reader.get_platforms()
    return jsonify(platforms)


@app.route('/api/export')
def api_export():
    """
    Export keys.

    - 必须配置并通过令牌鉴权（未配置 DASHBOARD_TOKEN 时直接禁用）
    - 默认返回 Fernet 加密的 JSON（.bin），密钥由 EXPORT_KEY 或 DASHBOARD_TOKEN 派生
    - mask=1 时返回脱敏 JSON（无明文 key，可安全流转）
    """
    if not AUTH_ENABLED:
        return jsonify({'error': '未配置 DASHBOARD_TOKEN，导出功能已禁用'}), 403
    gate = _auth_gate()
    if gate:
        return gate

    status = request.args.get('status')
    platform = request.args.get('platform')
    mask_only = request.args.get('mask') in ('1', 'true')

    result = db_reader.get_keys(status, platform, limit=10000, reveal=not mask_only)

    payload = json.dumps(result['keys'], indent=2, ensure_ascii=False).encode('utf-8')
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if mask_only:
        return send_file(
            io.BytesIO(payload),
            as_attachment=True,
            download_name=f'export_masked_{stamp}.json',
            mimetype='application/json',
        )

    from cryptography.fernet import Fernet
    encrypted = Fernet(_derive_export_key()).encrypt(payload)
    return send_file(
        io.BytesIO(encrypted),
        as_attachment=True,
        download_name=f'export_{stamp}.bin',
        mimetype='application/octet-stream',
    )


@app.route('/api/stats/update', methods=['POST'])
def api_stats_update():
    """Update current stats (called by scanner; requires token)"""
    if not AUTH_ENABLED:
        return jsonify({'status': 'error', 'message': '未配置 DASHBOARD_TOKEN，推送接口已禁用'}), 403
    gate = _auth_gate()
    if gate:
        return gate

    global current_stats
    data = request.get_json(silent=True) or {}
    for key in current_stats:
        if key in data:
            current_stats[key] = data[key]
    return jsonify({'status': 'ok'})


def run_server(host=None, port=5000):
    """Run Flask server（默认仅监听本机回环地址）"""
    bind_host = host or DASHBOARD_HOST
    app.run(host=bind_host, port=port, debug=False, threaded=True)


if __name__ == '__main__':
    print("Starting Web Dashboard...")
    if AUTH_ENABLED:
        print(f"Auth: ENABLED (DASHBOARD_TOKEN set) | reveal/export 可用")
    else:
        print("Auth: DISABLED (未设置 DASHBOARD_TOKEN)")
        print("  - Key 仅脱敏显示，reveal / export / stats 推送已禁用")
        print("  - 设置环境变量 DASHBOARD_TOKEN 后重启以启用完整功能")
    if DASHBOARD_HOST not in ("127.0.0.1", "localhost"):
        print(f"⚠ 警告: 监听 {DASHBOARD_HOST} 会将面板暴露到网络，请确认已设置强令牌！")
    print(f"Access at: http://{DASHBOARD_HOST}:5000")
    run_server()
