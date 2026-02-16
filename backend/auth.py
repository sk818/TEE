"""
Per-user authentication for TEE.

Uses a passwd file ({DATA_DIR}/passwd) with bcrypt-hashed passwords.
If no passwd file exists, auth is disabled (open access, backwards compatible).
"""

import os
import time
import secrets
import logging
from pathlib import Path
from functools import lru_cache

import bcrypt
from flask import request, session, jsonify, redirect

logger = logging.getLogger(__name__)

# Module state
_passwd_file: Path = None
_passwd_mtime: float = 0
_passwd_users: dict = {}  # username -> bcrypt_hash


def _load_passwd():
    """Reload passwd file if it has changed (mtime check)."""
    global _passwd_mtime, _passwd_users

    if _passwd_file is None or not _passwd_file.exists():
        _passwd_users = {}
        _passwd_mtime = 0
        return

    try:
        mtime = _passwd_file.stat().st_mtime
    except OSError:
        _passwd_users = {}
        _passwd_mtime = 0
        return

    if mtime == _passwd_mtime:
        return  # no change

    users = {}
    try:
        for line in _passwd_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if ':' not in line:
                continue
            username, hashed = line.split(':', 1)
            username = username.strip()
            hashed = hashed.strip()
            if username and hashed:
                users[username] = hashed
    except OSError as e:
        logger.error(f"Error reading passwd file: {e}")
        return

    _passwd_users = users
    _passwd_mtime = mtime
    logger.info(f"Loaded {len(users)} user(s) from passwd file")


def auth_enabled():
    """Return True if passwd file exists and has at least one user."""
    _load_passwd()
    return len(_passwd_users) > 0


def check_credentials(username, password):
    """Verify username/password against the passwd file."""
    _load_passwd()
    hashed = _passwd_users.get(username)
    if hashed is None:
        return False
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False


# Paths that never require authentication
PUBLIC_PATHS = {
    '/health',
    '/api/auth/login',
    '/api/auth/logout',
    '/api/auth/status',
    '/login.html',
}


def _is_public_path(path):
    """Check if the request path is public (no auth required)."""
    return path in PUBLIC_PATHS


def _require_auth():
    """before_request hook: enforce authentication when enabled."""
    if not auth_enabled():
        return  # no passwd file → open access

    if _is_public_path(request.path):
        return  # public endpoint

    if session.get('user'):
        return  # logged in

    # Not authenticated
    if request.path.startswith('/api/') or request.path.startswith('/tiles/') or request.path.startswith('/bounds/'):
        return jsonify({'error': 'Authentication required'}), 401
    else:
        return redirect('/login.html')


def init_auth(app, data_dir):
    """Initialize authentication on a Flask app.

    - Sets secret key from persistent file
    - Configures session cookies
    - Registers before_request hook and auth routes
    """
    global _passwd_file

    data_dir = Path(data_dir)
    _passwd_file = data_dir / 'passwd'

    # Persistent secret key so sessions survive restarts
    secret_key_file = data_dir / '.flask_secret_key'
    if secret_key_file.exists():
        app.secret_key = secret_key_file.read_text().strip()
    else:
        key = secrets.token_hex(32)
        data_dir.mkdir(parents=True, exist_ok=True)
        secret_key_file.write_text(key)
        secret_key_file.chmod(0o600)
        app.secret_key = key

    # Session config
    app.config['SESSION_COOKIE_NAME'] = 'tee_session'
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    # Register hook
    app.before_request(_require_auth)

    # Register routes
    @app.route('/api/auth/login', methods=['POST'])
    def auth_login():
        data = request.get_json(silent=True) or {}
        username = data.get('username', '').strip()
        password = data.get('password', '')

        if not username or not password:
            return jsonify({'success': False, 'error': 'Username and password required'}), 400

        if check_credentials(username, password):
            session['user'] = username
            return jsonify({'success': True, 'user': username})

        # Brute-force delay
        time.sleep(0.5)
        return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

    @app.route('/api/auth/logout', methods=['POST'])
    def auth_logout():
        session.pop('user', None)
        return jsonify({'success': True})

    @app.route('/api/auth/status', methods=['GET'])
    def auth_status():
        enabled = auth_enabled()
        user = session.get('user') if enabled else None
        return jsonify({
            'auth_enabled': enabled,
            'logged_in': user is not None,
            'user': user,
        })

    logger.info(f"Auth initialized (passwd file: {_passwd_file})")
