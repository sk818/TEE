#!/bin/bash
# Restart backend and tile server services

set -e

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$PROJECT_DIR"

echo "Stopping existing services..."
pkill -f "python.*main.py" || true
pkill -f "python.*tile_server" || true
sleep 1

echo "Activating virtual environment..."
source venv/bin/activate

echo "Starting backend (port 8000)..."
cd backend
python main.py > /tmp/tee_backend.log 2>&1 &
BACKEND_PID=$!
echo "Backend started with PID $BACKEND_PID"
sleep 2

echo "Starting tile server (port 8001)..."
python tile_server.py > /tmp/tee_tile_server.log 2>&1 &
TILE_SERVER_PID=$!
echo "Tile server started with PID $TILE_SERVER_PID"
sleep 2

# Check if services are running
echo "Checking service health..."
if curl -s http://localhost:8000/api/viewport-info > /dev/null 2>&1; then
    echo "✓ Backend is running"
else
    echo "✗ Backend failed to start - check logs with: tail /tmp/tee_backend.log"
fi

if curl -s http://localhost:8001/api/tiles/health > /dev/null 2>&1; then
    echo "✓ Tile server is running"
else
    echo "✗ Tile server failed to start - check logs with: tail /tmp/tee_tile_server.log"
fi

echo "Done! Backend and tile server are ready."
echo "View logs:"
echo "  Backend:    tail -f /tmp/tee_backend.log"
echo "  Tile Server: tail -f /tmp/tee_tile_server.log"
