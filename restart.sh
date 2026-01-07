#!/bin/bash
##
# Restart the Blore Viewport Manager Web Server
#
# Cleanly shuts down any existing web servers and starts a fresh one.
##

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🛑 Shutting down existing web servers..."

# Kill any Python processes running the web server
pkill -f "python.*backend/web_server.py" || true

# Kill any processes using port 8001
lsof -ti:8001 | xargs kill -9 2>/dev/null || true

# Give it a moment to clean up
sleep 1

echo "✓ Existing servers shut down"
echo ""
echo "🚀 Starting Blore Viewport Manager Web Server..."
echo ""

# Start the web server
python3 backend/web_server.py &

# Store the PID
WEB_SERVER_PID=$!

# Wait a moment for it to start
sleep 2

# Check if it's still running
if ps -p $WEB_SERVER_PID > /dev/null; then
    echo ""
    echo "✅ Web server started successfully (PID: $WEB_SERVER_PID)"
    echo ""
    echo "📍 Access the interface at: http://localhost:8001"
    echo "📝 Press Ctrl+C to stop the server"
    echo ""

    # Keep the script running with the web server
    wait $WEB_SERVER_PID
else
    echo ""
    echo "❌ Failed to start web server"
    echo "Check the error output above for details"
    exit 1
fi
