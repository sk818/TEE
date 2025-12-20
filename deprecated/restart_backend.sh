#!/bin/bash
# Restart the TESSERA backend server
# Kills any existing uvicorn processes and starts a fresh backend

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}═══════════════════════════════════════${NC}"
echo -e "${YELLOW}TESSERA Backend Restart${NC}"
echo -e "${YELLOW}═══════════════════════════════════════${NC}"

# Kill existing backend processes
echo -e "${YELLOW}Stopping existing backend processes...${NC}"
if pkill -f "uvicorn backend.main" 2>/dev/null; then
    echo -e "${GREEN}✓ Stopped existing backend${NC}"
else
    echo -e "${YELLOW}  (No existing backend running)${NC}"
fi

# Wait for process to fully terminate
sleep 1

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Verify we're in the right directory
if [ ! -f "$SCRIPT_DIR/backend/main.py" ]; then
    echo -e "${RED}✗ Error: backend/main.py not found in $SCRIPT_DIR${NC}"
    exit 1
fi

# Check if venv exists
if [ ! -d "$SCRIPT_DIR/venv" ]; then
    echo -e "${RED}✗ Error: Virtual environment not found at $SCRIPT_DIR/venv${NC}"
    echo -e "${YELLOW}Please create it with: python3 -m venv $SCRIPT_DIR/venv${NC}"
    exit 1
fi

# Start backend
echo -e "${YELLOW}Starting backend on port 8000...${NC}"
source "$SCRIPT_DIR/venv/bin/activate"
python3 -m uvicorn backend.main:app --port 8000 > /tmp/backend.log 2>&1 &
BACKEND_PID=$!

echo -e "${GREEN}✓ Backend started (PID: $BACKEND_PID)${NC}"

# Wait for backend to be ready
echo -e "${YELLOW}Waiting for backend to be ready...${NC}"
sleep 3

# Check if backend is responding
if curl -s http://localhost:8000/api/viewport-info > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Backend is ready!${NC}"
    echo -e "${GREEN}═══════════════════════════════════════${NC}"
    echo -e "${GREEN}Backend running on http://localhost:8000${NC}"
    echo -e "${GREEN}═══════════════════════════════════════${NC}"
else
    echo -e "${RED}✗ Backend failed to respond${NC}"
    echo -e "${YELLOW}Check logs with: tail -50 /tmp/backend.log${NC}"
    exit 1
fi
