#!/bin/bash
##
# Restart Blore Services (Web Server + Tile Server)
#
# Cleanly shuts down any existing services and starts fresh instances.
##

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🛑 Shutting down existing services..."

# Kill any Python/gunicorn processes running the servers
pkill -f "python.*backend/web_server.py" || true
pkill -f "python.*tile_server.py" || true
pkill -f "gunicorn.*backend.web_server" || true
pkill -f "gunicorn.*tile_server" || true

# Kill any processes using ports 8001 and 5125
lsof -ti:8001 | xargs kill -9 2>/dev/null || true
lsof -ti:5125 | xargs kill -9 2>/dev/null || true

# Give it a moment to clean up
sleep 1

echo "✓ Existing services shut down"
echo ""
echo "🚀 Starting Blore Services..."
echo ""

# macOS: prevent gunicorn fork() crash with Obj-C runtime
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES

# Start the web server
echo "  → Web server on port 8001"
TILE_SERVER_URL=http://localhost:5125 ./venv/bin/gunicorn -w 1 --threads 4 -b 0.0.0.0:8001 backend.web_server:app > /tmp/web_server.log 2>&1 &
WEB_SERVER_PID=$!

# Start the tile server
echo "  → Tile server on port 5125"
./venv/bin/gunicorn -w 1 --threads 4 -b 0.0.0.0:5125 tile_server:app > /tmp/tile_server.log 2>&1 &
TILE_SERVER_PID=$!

# Wait a moment for them to start
sleep 2

echo ""
echo "Checking services..."

# Check if web server is still running
if ps -p $WEB_SERVER_PID > /dev/null; then
    echo "✅ Web server started (PID: $WEB_SERVER_PID)"
else
    echo "❌ Failed to start web server"
    tail -20 /tmp/web_server.log
    exit 1
fi

# Check if tile server is still running
if ps -p $TILE_SERVER_PID > /dev/null; then
    echo "✅ Tile server started (PID: $TILE_SERVER_PID)"
else
    echo "❌ Failed to start tile server"
    tail -20 /tmp/tile_server.log
    exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ All services started successfully!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📍 Access the interface at: http://localhost:8001"
echo ""
echo "Logs:"
echo "  Web server:  tail -f /tmp/web_server.log"
echo "  Tile server: tail -f /tmp/tile_server.log"
echo ""
echo "📝 Press Ctrl+C to stop the servers"
echo ""

# Keep the script running (both servers run in background)
wait
