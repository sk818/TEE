#!/bin/bash

# Blore Project Status Script
# Quickly shows backup and sync status

echo "📊 Blore Project Status"
echo "========================"
echo ""

# Git status
echo "Git Repository:"
echo "  Branch: $(git branch --show-current)"
echo "  Status: $(if git diff --quiet && git diff --cached --quiet; then echo "✓ Clean"; else echo "⚠️  Changes pending"; fi)"
echo "  Size: $(du -sh .git | cut -f1)"
echo ""

# Data directories
DATA_DIR="$HOME/blore_data"
echo "Local Data (~/blore_data):"
if [ -d "$DATA_DIR" ]; then
    echo "  mosaics:      $(du -sh "$DATA_DIR/mosaics" 2>/dev/null | cut -f1 || echo "not found")"
    echo "  embeddings:   $(du -sh "$DATA_DIR/embeddings" 2>/dev/null | cut -f1 || echo "not found")"
    echo "  pyramids:     $(du -sh "$DATA_DIR/pyramids" 2>/dev/null | cut -f1 || echo "not found")"
    echo "  faiss_indices: $(du -sh "$DATA_DIR/faiss_indices" 2>/dev/null | cut -f1 || echo "not found")"
else
    echo "  ❌ Data directory not found at: $DATA_DIR"
fi
echo ""

# OneDrive status
echo "OneDrive Backup:"
ONEDRIVE_BACKUP=~/OneDrive\ -\ University\ of\ Cambridge/research/blore/data
if [ -d "$ONEDRIVE_BACKUP" ]; then
    echo "  Path: $ONEDRIVE_BACKUP"
    if [ -d "$ONEDRIVE_BACKUP/mosaics" ]; then
        echo "  ✓ Backups found"
    else
        echo "  ⚠️  Backup directory exists but is empty"
    fi
else
    echo "  ❌ OneDrive path not accessible: $ONEDRIVE_BACKUP"
fi
echo ""

# Disk space
echo "Disk Space:"
df -h . | tail -1 | awk '{printf "  Used: %s / %s (%s available)\n", $3, $2, $4}'
echo ""

# Recent backups
echo "Recent Backups:"
if [ -f "save.log" ]; then
    echo "  Last save.sh run:"
    tail -1 save.log | sed 's/^/    /'
else
    echo "  No save.log found (never backed up)"
fi
echo ""

# Quick actions
echo "Quick Actions:"
echo "  ./save.sh             - Backup code & data"
echo "  ./restore.sh          - Restore data from OneDrive"
echo "  ./save.sh --dry-run   - Preview what would be backed up"
echo "  git log --oneline     - View commit history"
echo ""
