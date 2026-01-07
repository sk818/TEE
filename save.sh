#!/bin/bash

# Blore Project Save Script
# Backs up code to GitHub and large data files to OneDrive

echo "💾 Saving Blore project..."
echo ""

# Navigate to project directory
cd ~/blore || { echo "Error: blore directory not found!"; exit 1; }

# Check if we're in a git repo
if [ ! -d ".git" ]; then
    echo "❌ Error: Not a git repository!"
    echo "   Initialize git with: git init"
    exit 1
fi

# Step 1: Save code to Git/GitHub
echo "📝 Saving code to GitHub..."
echo ""

# Show what changed
echo "Files changed:"
git status --short

echo ""

# Parse optional flags
DRY_RUN=0
NO_PUSH=0
AUTOSAVE=0
NO_DATA=0

for arg in "$@"; do
    case "$arg" in
        --dry-run|-n)
            DRY_RUN=1
            ;;
        --no-push)
            NO_PUSH=1
            ;;
        --autosave)
            AUTOSAVE=1
            ;;
        --no-data)
            NO_DATA=1
            ;;
        --help|-h)
            echo "Usage: $0 [--dry-run|-n] [--no-push] [--autosave] [--no-data]"
            echo "  --dry-run, -n   : show files that would be staged/committed"
            echo "  --no-push        : commit locally but do not push to remote"
            echo "  --autosave       : use timestamped commit message if no message provided"
            echo "  --no-data        : skip backing up large data files to OneDrive"
            exit 0
            ;;
    esac
done

if [ "$DRY_RUN" -eq 1 ]; then
    echo "⚠️  Dry run: no changes will be staged or committed"
fi

# Ask for commit message
read -p "Enter commit message (or press Enter for default): " commit_msg
if [ -z "$commit_msg" ]; then
    if [ "$AUTOSAVE" -eq 1 ]; then
        commit_msg="Autosave: $(date --iso-8601=seconds 2>/dev/null || date)"
    else
        commit_msg="Update blore project"
    fi
fi

# Setup logging
LOGFILE="$(pwd)/save.log"
log(){
  echo "$(date --iso-8601=seconds 2>/dev/null || date) - $*" | tee -a "$LOGFILE"
}

log "Starting save.sh (dry_run=$DRY_RUN no_push=$NO_PUSH autosave=$AUTOSAVE no_data=$NO_DATA)"

# Add and commit code
if [ "$DRY_RUN" -eq 1 ]; then
    echo "Dry-run: files that would be staged:"
    git status --short
    log "Dry-run: files shown above"
else
    # Stage all tracked changes
    log "Staging code changes"
    git add -A || true

    # Remove deleted files from index
    log "Removing deleted files from index (if any)"
    git ls-files --deleted -z | xargs -0 -r git rm --cached || true
fi

# Commit if there are staged changes
if git diff --cached --quiet; then
    echo "ℹ️  No code changes to commit"
else
    if [ "$DRY_RUN" -eq 1 ]; then
        echo "Dry-run: commit would be created with message: $commit_msg"
        log "Dry-run: commit would be: $commit_msg"
    else
        git commit -m "$commit_msg"
        if [ $? -eq 0 ]; then
            echo "✓ Changes committed"
            if [ "$NO_PUSH" -eq 1 ]; then
                echo "ℹ️  --no-push set: commit created locally but not pushed"
                log "Commit created locally, not pushed (no-push)"
            else
                echo "⬆️  Pushing to GitHub..."
                if git push; then
                    echo "✓ Code backed up to GitHub"
                    log "Pushed to remote"
                else
                    echo "⚠️  Warning: Could not push to GitHub (check internet connection or remote settings)"
                    log "Push failed"
                fi
            fi
        else
            echo "⚠️  Commit failed"
            log "Commit failed"
        fi
    fi
fi

echo ""

# Step 2: Backup large data files to OneDrive (unless --no-data flag)
if [ "$NO_DATA" -eq 1 ]; then
    echo "ℹ️  Skipping data backup (--no-data flag set)"
    log "Data backup skipped"
else
    echo "💿 Backing up large data files to OneDrive..."
    echo ""

    # Create OneDrive backup directory if it doesn't exist
    ONEDRIVE_BACKUP=~/OneDrive\ -\ University\ of\ Cambridge/research/blore/data
    if [ ! -d "$ONEDRIVE_BACKUP" ]; then
        echo "Creating backup directory: $ONEDRIVE_BACKUP"
        mkdir -p "$ONEDRIVE_BACKUP"
        log "Created OneDrive backup directory"
    fi

    DATA_DIR="$HOME/blore_data"

    if [ ! -d "$DATA_DIR" ]; then
        echo "ℹ️  Data directory not found: $DATA_DIR"
        echo "   Large data files are stored in: $DATA_DIR"
        log "Data directory not found: $DATA_DIR"
    else
        # Backup mosaics
        if [ -d "$DATA_DIR/mosaics" ]; then
            if [ "$DRY_RUN" -eq 1 ]; then
                echo "Dry-run: would backup mosaics directory"
                log "Dry-run: mosaics backup"
            else
                echo "Backing up mosaics directory..."
                log "Backing up mosaics ($(du -sh "$DATA_DIR/mosaics" | cut -f1))"
                rsync -av --progress "$DATA_DIR/mosaics/" "$ONEDRIVE_BACKUP/mosaics/"
                echo "✓ mosaics backed up"
                log "mosaics backup complete"
            fi
        else
            echo "ℹ️  mosaics directory not found"
            log "mosaics directory not found"
        fi

        echo ""

        # Backup embeddings
        if [ -d "$DATA_DIR/embeddings" ]; then
            if [ "$DRY_RUN" -eq 1 ]; then
                echo "Dry-run: would backup embeddings directory"
                log "Dry-run: embeddings backup"
            else
                echo "Backing up embeddings directory..."
                log "Backing up embeddings ($(du -sh "$DATA_DIR/embeddings" | cut -f1))"
                rsync -av --progress "$DATA_DIR/embeddings/" "$ONEDRIVE_BACKUP/embeddings/"
                echo "✓ embeddings backed up"
                log "embeddings backup complete"
            fi
        else
            echo "ℹ️  embeddings directory not found"
            log "embeddings directory not found"
        fi

        echo ""

        # Backup pyramids
        if [ -d "$DATA_DIR/pyramids" ]; then
            if [ "$DRY_RUN" -eq 1 ]; then
                echo "Dry-run: would backup pyramids directory"
                log "Dry-run: pyramids backup"
            else
                echo "Backing up pyramids directory..."
                log "Backing up pyramids ($(du -sh "$DATA_DIR/pyramids" | cut -f1))"
                rsync -av --progress "$DATA_DIR/pyramids/" "$ONEDRIVE_BACKUP/pyramids/"
                echo "✓ pyramids backed up"
                log "pyramids backup complete"
            fi
        else
            echo "ℹ️  pyramids directory not found"
            log "pyramids directory not found"
        fi

        echo ""

        # Backup FAISS indices
        if [ -d "$DATA_DIR/faiss_indices" ]; then
            if [ "$DRY_RUN" -eq 1 ]; then
                echo "Dry-run: would backup FAISS indices directory"
                log "Dry-run: FAISS indices backup"
            else
                echo "Backing up FAISS indices directory..."
                log "Backing up FAISS indices ($(du -sh "$DATA_DIR/faiss_indices" | cut -f1))"
                rsync -av --progress "$DATA_DIR/faiss_indices/" "$ONEDRIVE_BACKUP/faiss_indices/"
                echo "✓ FAISS indices backed up"
                log "FAISS indices backup complete"
            fi
        else
            echo "ℹ️  FAISS indices directory not found"
            log "FAISS indices directory not found"
        fi
    fi

    echo ""
fi

echo "✅ Save complete!"
echo ""
echo "📊 Summary:"
echo "   Code: Backed up to GitHub (main branch)"
echo "   Large data: $ONEDRIVE_BACKUP"
echo ""
echo "🔒 Your work is safe!"
