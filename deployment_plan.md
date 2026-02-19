# Deployment Plan: Tessera Behind Apache on Public VM

## Overview

Deploy the Tessera Embedding Explorer (web server + tile server) behind Apache on a public-facing VM, enabling browser-only access with authentication and security hardening.

## Current Architecture

| Service | Port | Purpose |
|---------|------|---------|
| Web Server (Flask) | 8001 | API endpoints, similarity search |
| Tile Server (Flask) | 5125 | Map tile serving from GeoTIFFs |
| Frontend | - | Static HTML/JS served by web server |

**Hardcoded URLs to fix:**
- `viewer.html:569` - `const TILE_SERVER = 'http://localhost:5125'`
- `viewer.html:816,971` - `http://localhost:8001/api/viewports/...`

---

## Architecture After Deployment

```
Internet (Port 80/443)
         │
    ┌────▼────┐
    │  Apache │  ← HTTPS redirect, Auth, SSL, Caching, Rate Limiting
    └────┬────┘
         │
    ┌────┴────────────────┐
    │                     │
    ▼                     ▼
/api/* → Flask:8001    /tiles/* → Flask:5125
(localhost only)       (localhost only)
```

---

## Pre-Deployment Checklist

Before each deployment:
- [ ] Tested changes locally
- [ ] Verified VM has disk space (`df -h /var/tessera_data`)

---

## Phase 1: Environment Configuration

### 1.1 Create Directories and User
```bash
# Create tessera user (no login shell)
sudo useradd -r -s /sbin/nologin tessera

# Create directories
sudo mkdir -p /opt/tessera/releases /opt/tessera/shared
sudo mkdir -p /var/tessera_data/backups
sudo mkdir -p /var/log/tessera
sudo mkdir -p /etc/tessera

# Set ownership
sudo chown -R tessera:tessera /opt/tessera /var/tessera_data /var/log/tessera
sudo chmod 750 /var/tessera_data
```

---

## Phase 2: Apache Configuration

### 2.1 Enable Required Modules
```bash
sudo a2enmod proxy proxy_http headers rewrite ssl auth_basic deflate expires http2
sudo systemctl restart apache2
```

### 2.2 HTTP Virtual Host - Redirect Only (`/etc/apache2/sites-available/tessera.conf`)

```apache
<VirtualHost *:80>
    ServerName tessera.yourdomain.com

    # FORCE HTTPS - No exceptions (Basic Auth credentials must be encrypted)
    RewriteEngine On
    RewriteCond %{HTTPS} off
    RewriteRule ^(.*)$ https://%{HTTP_HOST}%{REQUEST_URI} [L,R=301]

    ErrorLog ${APACHE_LOG_DIR}/tessera_error.log
    CustomLog ${APACHE_LOG_DIR}/tessera_access.log combined
</VirtualHost>
```

### 2.3 HTTPS Virtual Host (`/etc/apache2/sites-available/tessera-ssl.conf`)

```apache
<VirtualHost *:443>
    ServerName tessera.yourdomain.com

    # SSL Configuration (use existing certs)
    SSLEngine on
    SSLCertificateFile /path/to/your/certificate.crt
    SSLCertificateKeyFile /path/to/your/private.key
    # SSLCertificateChainFile /path/to/chain.crt  # If needed

    # Modern SSL settings
    SSLProtocol all -SSLv3 -TLSv1 -TLSv1.1
    SSLCipherSuite ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384
    SSLHonorCipherOrder on

    # =========================================================
    # HTTP/2 - Multiplexed requests for faster tile loading
    # =========================================================
    Protocols h2 http/1.1

    # =========================================================
    # HEALTH CHECKS - Exempt from authentication (for monitoring)
    # =========================================================
    <Location /health>
        Require all granted
    </Location>
    <Location /api/health>
        Require all granted
    </Location>
    <Location /tiles-health>
        Require all granted
    </Location>

    # =========================================================
    # AUTHENTICATION - Everything else requires login
    # =========================================================
    <Location />
        AuthType Basic
        AuthName "Tessera Embeddings Explorer"
        AuthUserFile /etc/apache2/.htpasswd-tessera
        Require valid-user
    </Location>

    # =========================================================
    # PROXY SETTINGS
    # =========================================================
    ProxyPreserveHost On
    ProxyRequests Off
    ProxyTimeout 300

    # Tile server health (must come before /tiles)
    ProxyPass /tiles-health http://127.0.0.1:5125/health
    ProxyPassReverse /tiles-health http://127.0.0.1:5125/health

    # Route tile requests to tile server (port 5125)
    ProxyPass /tiles http://127.0.0.1:5125/tiles
    ProxyPassReverse /tiles http://127.0.0.1:5125/tiles
    ProxyPass /bounds http://127.0.0.1:5125/bounds
    ProxyPassReverse /bounds http://127.0.0.1:5125/bounds

    # Route API and static files to web server (port 8001)
    ProxyPass /api http://127.0.0.1:8001/api
    ProxyPassReverse /api http://127.0.0.1:8001/api
    ProxyPass / http://127.0.0.1:8001/
    ProxyPassReverse / http://127.0.0.1:8001/

    # =========================================================
    # SECURITY HEADERS
    # =========================================================
    Header always set X-Content-Type-Options "nosniff"
    Header always set X-Frame-Options "DENY"
    Header always set X-XSS-Protection "1; mode=block"
    Header always set Referrer-Policy "strict-origin-when-cross-origin"
    Header always set Strict-Transport-Security "max-age=31536000; includeSubDomains"

    # Content Security Policy - Allow CDN resources used by Leaflet/Three.js
    Header always set Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://unpkg.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline' https://unpkg.com https://cdnjs.cloudflare.com; img-src 'self' data: blob: https://*.tile.openstreetmap.org https://server.arcgisonline.com; connect-src 'self' https://nominatim.openstreetmap.org; font-src 'self'; frame-ancestors 'none';"

    # Remove server version info
    ServerSignature Off
    Header unset Server

    # =========================================================
    # COMPRESSION
    # =========================================================
    <IfModule mod_deflate.c>
        AddOutputFilterByType DEFLATE application/json text/html text/css application/javascript
        # Don't compress images (already compressed)
        SetEnvIfNoCase Request_URI "\.png$" no-gzip
    </IfModule>

    # =========================================================
    # CACHING
    # =========================================================
    <IfModule mod_expires.c>
        ExpiresActive On

        # Tile images - immutable, cache forever (1 year)
        <LocationMatch "^/tiles/.*\.png$">
            Header set Cache-Control "public, max-age=31536000, immutable"
        </LocationMatch>

        # Static files - cache 1 hour
        <LocationMatch "\.(html|js|css)$">
            Header set Cache-Control "public, max-age=3600"
        </LocationMatch>

        # API responses - no caching
        <Location /api>
            Header set Cache-Control "no-cache, no-store, must-revalidate"
            Header set Pragma "no-cache"
        </Location>
    </IfModule>

    # =========================================================
    # LOGGING
    # =========================================================
    ErrorLog ${APACHE_LOG_DIR}/tessera_ssl_error.log
    CustomLog ${APACHE_LOG_DIR}/tessera_ssl_access.log combined
    LogLevel warn
</VirtualHost>
```

### 2.4 Create Password File
```bash
sudo htpasswd -c /etc/apache2/.htpasswd-tessera tessera_user
sudo chmod 640 /etc/apache2/.htpasswd-tessera
sudo chown root:www-data /etc/apache2/.htpasswd-tessera
```

### 2.5 Password Management Procedure
```bash
# Add new user
sudo htpasswd /etc/apache2/.htpasswd-tessera new_user

# Remove user
sudo htpasswd -D /etc/apache2/.htpasswd-tessera old_user

# Change password (user re-adds themselves)
sudo htpasswd /etc/apache2/.htpasswd-tessera existing_user

# No Apache restart needed - changes are picked up automatically
```

### 2.6 Enable Sites
```bash
sudo a2ensite tessera.conf tessera-ssl.conf
sudo apache2ctl configtest
sudo systemctl reload apache2
```

---

## Phase 3: Flask App Modifications

### 3.1 Bind to Localhost Only (Security)

**File: `backend/web_server.py`** (bottom of file)
```python
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8001, debug=False, threaded=True)
```

**File: `tile_server.py`** (bottom of file)
```python
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5125, debug=False, threaded=True)
```

### 3.2 Add Health Check Endpoint

**File: `backend/web_server.py`** (add near other routes)
```python
@app.route('/health')
def health_check():
    """Simple health check for monitoring."""
    return jsonify({'status': 'ok', 'service': 'tessera-web'})
```

**File: `tile_server.py`** (already has /health endpoint - keep existing)

### 3.3 Add Configuration Endpoint

**File: `backend/web_server.py`**
```python
@app.route('/api/config')
def get_config():
    """Return frontend configuration."""
    return jsonify({
        'tile_server': '',  # Empty = relative URLs via Apache proxy
        'api_base': '/api',
        'version': '1.0.12'
    })
```

### 3.4 Restrict CORS in Production

**File: `backend/web_server.py`** (near top, replace existing CORS)
```python
import os
from flask_cors import CORS

# ... app = Flask(...) ...

if os.environ.get('TESSERA_ENV') == 'production':
    CORS(app, origins=[
        'https://tessera.yourdomain.com',
        'https://www.tessera.yourdomain.com'
    ])
else:
    CORS(app)  # Allow all in development
```

### 3.5 Labels (Client-Side Only)

Labels are stored exclusively in the browser's `localStorage` for user privacy. No server-side label storage exists — the SQLite labels API and `labels_db.py` have been removed.

---

## Phase 4: Frontend URL Changes

**File: `public/viewer.html`**

### 4.1 Replace Hardcoded TILE_SERVER (line ~569)
```javascript
// OLD:
const TILE_SERVER = 'http://localhost:5125';

// NEW:
let TILE_SERVER = '';  // Use relative URLs through Apache proxy
```

### 4.2 Replace Hardcoded API URLs (lines ~816, ~971)
```javascript
// OLD:
fetch(`http://localhost:8001/api/viewports/${currentViewportName}/available-years`)

// NEW:
fetch(`/api/viewports/${currentViewportName}/available-years`)
```

### 4.3 Update All Tile Layer URLs
```javascript
// OLD:
`${TILE_SERVER}/tiles/${viewport}/${year}/{z}/{x}/{y}.png`

// NEW:
`/tiles/${viewport}/${year}/{z}/{x}/{y}.png`
```

---

## Phase 5: Dependencies

### 5.1 Create requirements.txt

After testing locally, freeze your working environment:
```bash
pip freeze > requirements.txt
```

Or create a simple requirements.txt with the packages you need:
```
flask
flask-cors
numpy
rasterio
pillow
faiss-cpu
scipy
requests
gunicorn
```

---

## Phase 6: Production Deployment with Gunicorn

### 6.1 Gunicorn Config for Web Server (`/opt/tessera/shared/gunicorn_web.conf.py`)
```python
import multiprocessing

bind = "127.0.0.1:8001"
workers = min(multiprocessing.cpu_count() * 2 + 1, 4)
worker_class = "sync"
timeout = 300        # Long timeout for pipeline operations
max_requests = 1000  # Restart workers periodically to prevent memory leaks

accesslog = "/var/log/tessera/web_access.log"
errorlog = "/var/log/tessera/web_error.log"
loglevel = "info"
```

### 6.2 Gunicorn Config for Tile Server (`/opt/tessera/shared/gunicorn_tiles.conf.py`)
```python
import multiprocessing

bind = "127.0.0.1:5125"
workers = min(multiprocessing.cpu_count() * 2, 4)
worker_class = "sync"
timeout = 60
max_requests = 5000  # Restart workers periodically

accesslog = "/var/log/tessera/tiles_access.log"
errorlog = "/var/log/tessera/tiles_error.log"
loglevel = "info"
```

### 6.3 Systemd Service for Web Server (`/etc/systemd/system/tessera-web.service`)
```ini
[Unit]
Description=Tessera Web Server
After=network.target

[Service]
Type=simple
User=tessera
Group=tessera
WorkingDirectory=/opt/tessera
Environment="TESSERA_DATA=/var/tessera_data"
ExecStart=/opt/tessera/venv/bin/gunicorn -c /opt/tessera/gunicorn_web.conf.py backend.web_server:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 6.4 Systemd Service for Tile Server (`/etc/systemd/system/tessera-tiles.service`)
```ini
[Unit]
Description=Tessera Tile Server
After=network.target

[Service]
Type=simple
User=tessera
Group=tessera
WorkingDirectory=/opt/tessera
Environment="TESSERA_DATA=/var/tessera_data"
ExecStart=/opt/tessera/venv/bin/gunicorn -c /opt/tessera/gunicorn_tiles.conf.py tile_server:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

---

## Phase 7: Security Hardening

### 7.1 Firewall Rules
```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
# Explicitly deny direct Flask access (defense in depth)
sudo ufw deny 8001/tcp
sudo ufw deny 5125/tcp
sudo ufw enable
```

### 7.2 Fail2ban (Optional)

If you observe brute force attempts in Apache logs, add Fail2ban:
```bash
sudo apt install fail2ban
# Configure /etc/fail2ban/jail.d/tessera.conf to watch Apache auth logs
```

For a small internal deployment with known users, this is usually not needed.

---

## Phase 8: Logging and Monitoring

### 8.1 Log Rotation

**File: `/etc/logrotate.d/tessera`**
```
/var/log/tessera/*.log {
    daily
    rotate 14
    compress
    missingok
    notifempty
}
```

### 8.2 External Monitoring (Optional)

For uptime alerts, use a free service like UptimeRobot to monitor:
`https://tessera.yourdomain.com/health`

---

## Phase 9: Backups

Labels are stored in the browser's `localStorage` (no server-side data to back up). If you later add server-side state, add a backup cron job here.

---

## Phase 10: Deployment

### 10.1 Directory Structure
```
/opt/tessera/
    backend/            # Flask web server code
    public/             # Static files (viewer.html, etc.)
    tile_server.py      # Tile server
    requirements.txt
    venv/               # Python virtualenv
    gunicorn_web.conf.py
    gunicorn_tiles.conf.py
```

### 10.2 Deploy Script

**File: `/opt/tessera/deploy.sh`**
```bash
#!/bin/bash
set -e

cd /opt/tessera

echo "=== Deploying Tessera ==="

# Pull latest code
echo "Pulling latest code..."
git pull

# Update dependencies
echo "Updating dependencies..."
source venv/bin/activate
pip install -r requirements.txt --quiet

# Restart services
echo "Restarting services..."
sudo systemctl restart tessera-web tessera-tiles

# Verify
sleep 3
curl -sf http://127.0.0.1:8001/health > /dev/null && echo "Web server: OK" || echo "Web server: FAILED"
curl -sf http://127.0.0.1:5125/health > /dev/null && echo "Tile server: OK" || echo "Tile server: FAILED"

echo "=== Done ==="
```

### 10.3 Rollback

If something breaks:
```bash
cd /opt/tessera
git log --oneline -5           # Find previous working commit
git checkout <commit-hash>     # Checkout that commit
sudo systemctl restart tessera-web tessera-tiles
```

---

## Phase 11: Data Transfer

### 11.1 Transfer Data
```bash
# Use screen/tmux for long transfers
screen -S tessera-transfer

# Transfer data
rsync -avz --progress \
    --exclude='*.tmp' \
    --exclude='__pycache__' \
    ~/blore_data/ user@vm:/var/tessera_data/

# Ctrl+A, D to detach; screen -r tessera-transfer to resume
```

### 11.2 Set Up Code on VM
```bash
# Clone the repo
cd /opt
sudo git clone https://github.com/sk818/TEE.git tessera
sudo chown -R tessera:tessera /opt/tessera

# Create virtualenv and install dependencies
cd /opt/tessera
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn

# Copy config files
cp gunicorn_*.conf.py /opt/tessera/

# Make deploy script executable
chmod +x deploy.sh
```

---

## Phase 12: Performance (Already Optimized)

The Apache configuration already includes key performance features:

- **HTTP/2**: Multiplexed requests for faster tile loading
- **Browser caching**:
  - Tiles: `Cache-Control: public, max-age=31536000, immutable` (1 year)
  - Static files: 1 hour cache
- **Compression**: gzip for JSON, HTML, CSS, JS

No additional code changes needed. If you observe performance issues after deployment, measure first, then optimize.

---

## Verification Checklist

### Security
- [ ] HTTP redirects to HTTPS (`curl -I http://tessera.yourdomain.com`)
- [ ] Direct access to :8001/:5125 blocked (firewall)
- [ ] Unauthenticated access returns 401
- [ ] Valid credentials grant access

### Functionality
- [ ] Viewer loads after login
- [ ] Tiles display correctly
- [ ] Similarity search works
- [ ] Labels save/load correctly (client-side localStorage)

### Operations
- [ ] Services running (`systemctl status tessera-web tessera-tiles`)
- [ ] Health endpoints responding (`curl http://127.0.0.1:8001/health`)
- [ ] Logs being written (`tail /var/log/tessera/web_access.log`)
- [ ] Backups running (`ls /var/tessera_data/backups/`)

---

## Configuration Decisions

- **Authentication**: Apache Basic Auth (htpasswd file)
- **SSL**: Use existing SSL certificate on VM
- **Data Storage**: Local disk at `/var/tessera_data/`
- **Deployment**: Simple git pull + restart
- **Logging**: Default Gunicorn format (human-readable)

---

## Design Principles

This deployment prioritizes **simplicity and robustness**:

- **Fewer moving parts**: Each feature is a liability until proven essential
- **Use defaults**: Proven configurations that just work
- **Measure first**: Only add complexity when you have evidence of a problem

### Future Enhancements (If Needed)

| Symptom | Add |
|---------|-----|
| Brute force attempts | Fail2ban |
| Slow repeated tile requests | Apache disk cache |
| Need log aggregation | JSON log format |
| Slow searches | FAISS index caching |
| Frequent deployments | Versioned releases with rollback |
