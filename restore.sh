#!/bin/bash

# Blore Project Restore Script
# Restores large data files from OneDrive backup

echo "📥 Restoring Blore project data from OneDrive..."
echo ""

# Navigate to project directory
cd ~/blore || { echo "Error: blore directory not found!"; exit 1; }

# Check if blore_data directory exists
DATA_DIR="$HOME/blore_data"
if [ -d "$DATA_DIR" ]; then
    echo "ℹ️  Data directory already exists at: $DATA_DIR"
    read -p "Do you want to restore/update from OneDrive? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Restore cancelled."
        exit 0
    fi
else
    echo "Creating data directory: $DATA_DIR"
    mkdir -p "$DATA_DIR"
fi

# OneDrive backup location
ONEDRIVE_BACKUP=~/OneDrive\ -\ University\ of\ Cambridge/research/blore/data

if [ ! -d "$ONEDRIVE_BACKUP" ]; then
    echo "❌ Error: OneDrive backup directory not found!"
    echo "   Expected: $ONEDRIVE_BACKUP"
    echo ""
    echo "   Make sure:"
    echo "   1. OneDrive is mounted/accessible"
    echo "   2. You've run ./save.sh at least once to create backups"
    exit 1
fi

echo "Restoring from: $ONEDRIVE_BACKUP"
echo ""

# Setup logging
LOGFILE="$(pwd)/restore.log"
log(){
  echo "$(date --iso-8601=seconds 2>/dev/null || date) - $*" | tee -a "$LOGFILE"
}

log "Starting restore.sh"

# Restore mosaics
if [ -d "$ONEDRIVE_BACKUP/mosaics" ]; then
    echo "Restoring mosaics..."
    log "Restoring mosaics"
    rsync -av --progress "$ONEDRIVE_BACKUP/mosaics/" "$DATA_DIR/mosaics/"
    echo "✓ mosaics restored"
else
    echo "ℹ️  mosaics backup not found in OneDrive"
    log "mosaics backup not found"
fi

echo ""

# Restore embeddings
if [ -d "$ONEDRIVE_BACKUP/embeddings" ]; then
    echo "Restoring embeddings..."
    log "Restoring embeddings"
    rsync -av --progress "$ONEDRIVE_BACKUP/embeddings/" "$DATA_DIR/embeddings/"
    echo "✓ embeddings restored"
else
    echo "ℹ️  embeddings backup not found in OneDrive"
    log "embeddings backup not found"
fi

echo ""

# Restore pyramids
if [ -d "$ONEDRIVE_BACKUP/pyramids" ]; then
    echo "Restoring pyramids..."
    log "Restoring pyramids"
    rsync -av --progress "$ONEDRIVE_BACKUP/pyramids/" "$DATA_DIR/pyramids/"
    echo "✓ pyramids restored"
else
    echo "ℹ️  pyramids backup not found in OneDrive"
    log "pyramids backup not found"
fi

echo ""

# Restore FAISS indices
if [ -d "$ONEDRIVE_BACKUP/faiss_indices" ]; then
    echo "Restoring FAISS indices..."
    log "Restoring FAISS indices"
    rsync -av --progress "$ONEDRIVE_BACKUP/faiss_indices/" "$DATA_DIR/faiss_indices/"
    echo "✓ FAISS indices restored"
else
    echo "ℹ️  FAISS indices backup not found in OneDrive"
    log "FAISS indices backup not found"
fi

echo ""

# Create symlinks (optional)
echo "Creating symlinks to data directory..."
ln -sf "$DATA_DIR/mosaics" ./mosaics 2>/dev/null && echo "✓ mosaics symlink created"
ln -sf "$DATA_DIR/embeddings" ./embeddings 2>/dev/null && echo "✓ embeddings symlink created"
ln -sf "$DATA_DIR/pyramids" ./pyramids 2>/dev/null && echo "✓ pyramids symlink created"
ln -sf "$DATA_DIR/faiss_indices" ./faiss_indices 2>/dev/null && echo "✓ FAISS indices symlink created"

echo ""
echo "✅ Restore complete!"
echo ""
echo "📊 Data restored to: $DATA_DIR"
echo ""
log "Restore complete"
