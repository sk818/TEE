#!/bin/bash
# Start all Blore services with proper venv setup

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python3"

echo "Starting Blore services..."
echo "Using Python: $VENV_PYTHON"

# Kill any existing instances
pkill -f "web_server.py" 2>/dev/null || true
pkill -f "tile_server.py" 2>/dev/null || true
sleep 2

# Start backend
echo "Starting backend on port 8001..."
$VENV_PYTHON "$PROJECT_DIR/backend/web_server.py" > /tmp/backend.log 2>&1 &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

# Start tile server
echo "Starting tile server on port 5125..."
$VENV_PYTHON "$PROJECT_DIR/tile_server.py" > /tmp/tile_server.log 2>&1 &
TILE_PID=$!
echo "Tile server PID: $TILE_PID"

sleep 3

# Check if services are running
if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo "❌ Backend failed to start!"
    tail -20 /tmp/backend.log
    exit 1
fi

if ! kill -0 $TILE_PID 2>/dev/null; then
    echo "❌ Tile server failed to start!"
    tail -20 /tmp/tile_server.log
    exit 1
fi

echo "✅ All services started successfully!"
echo ""
echo "Backend: http://localhost:8001"
echo "Logs:"
echo "  Backend:     /tmp/backend.log"
echo "  Tile server: /tmp/tile_server.log"
echo ""
echo "To view logs:"
echo "  tail -f /tmp/backend.log"
echo "  tail -f /tmp/tile_server.log"
