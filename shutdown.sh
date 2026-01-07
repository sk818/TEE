#!/bin/bash
##
# Shutdown the Blore Viewport Manager Web Server
#
# Cleanly stops any running web servers.
##

echo "🛑 Shutting down Blore Viewport Manager Web Server..."
echo ""

STOPPED=false

# Kill any Python processes running the web server
if pkill -f "python.*backend/web_server.py" 2>/dev/null; then
    echo "✓ Stopped Python web server process"
    STOPPED=true
fi

# Kill any processes using port 8001
if lsof -ti:8001 2>/dev/null | xargs kill -9 2>/dev/null; then
    echo "✓ Freed port 8001"
    STOPPED=true
fi

if [ "$STOPPED" = true ]; then
    echo ""
    echo "✅ Web server shut down successfully"
else
    echo ""
    echo "⚠️  No running web server found"
fi
