#!/bin/bash
##
# Restart TEE Services (Web Server + Tile Server)
#
# Uses Flask's built-in threaded server (no gunicorn needed).
# Auto-detects: if 'tee' system user exists, runs as tee (server mode).
# Otherwise runs as the current user (local development).
##

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON="$SCRIPT_DIR/venv/bin/python3"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

# Auto-detect run mode: server (tee user) vs local (current user)
if id tee >/dev/null 2>&1; then
    RUN="sudo -u tee"
    MODE="server"
    echo "TEE server mode (running as tee user)"
else
    RUN=""
    MODE="local"
    echo "TEE local mode (running as $(whoami))"
fi

echo "Shutting down existing services..."

# Kill any existing TEE processes
pkill -f "python.*backend/web_server.py" 2>/dev/null || true
pkill -f "python.*tile_server.py" 2>/dev/null || true
pkill -f "gunicorn.*backend.web_server" 2>/dev/null || true
pkill -f "gunicorn.*tile_server" 2>/dev/null || true
lsof -ti:8001 2>/dev/null | xargs kill -9 2>/dev/null || true
lsof -ti:5125 2>/dev/null | xargs kill -9 2>/dev/null || true
sleep 1

# Set host: localhost for server (behind Apache), all interfaces for local dev
if [ "$MODE" = "server" ]; then
    HOST="127.0.0.1"
else
    HOST="0.0.0.0"
fi

# Start web server
echo "  Web server on $HOST:8001"
$RUN $PYTHON "$SCRIPT_DIR/backend/web_server.py" --prod --host "$HOST" --port 8001 \
    >> "$LOG_DIR/web_server.log" 2>&1 &
WEB_PID=$!

# Start tile server
echo "  Tile server on $HOST:5125"
$RUN $PYTHON "$SCRIPT_DIR/tile_server.py" --prod --host "$HOST" --port 5125 \
    >> "$LOG_DIR/tile_server.log" 2>&1 &
TILE_PID=$!

sleep 2

# Verify
FAILED=false
if ps -p $WEB_PID > /dev/null 2>&1; then
    echo "  Web server OK (PID: $WEB_PID)"
else
    echo "  Web server FAILED -- check $LOG_DIR/web_server.log"
    FAILED=true
fi

if ps -p $TILE_PID > /dev/null 2>&1; then
    echo "  Tile server OK (PID: $TILE_PID)"
else
    echo "  Tile server FAILED -- check $LOG_DIR/tile_server.log"
    FAILED=true
fi

if [ "$FAILED" = true ]; then
    exit 1
fi

echo ""
echo "TEE running at http://$HOST:8001"
echo "Logs: $LOG_DIR/"
