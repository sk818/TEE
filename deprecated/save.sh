#!/bin/bash

# TEE (Tessera Embeddings Explorer) Project Save Script
# Run this to backup code to GitHub and large files to OneDrive

echo "💾 Saving TEE project..."
echo ""

# Navigate to project directory
cd ~/tee || { echo "Error: tee directory not found!"; exit 1; }

# Check if we're in a git repo
if [ ! -d ".git" ]; then
    echo "❌ Error: Not a git repository!"
    echo "   Initialize git with: git init"
    echo "   Add remote with: git remote add origin <your-github-url>"
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
# Parse positional flags (simple parsing)
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
        --help|-h)
            echo "Usage: $0 [--dry-run|-n] [--no-push] [--autosave]"
            echo "  --dry-run, -n   : show files that would be staged/committed"
            echo "  --no-push        : commit locally but do not push to remote"
            echo "  --autosave       : use timestamped commit message 'Autosave: DATE' if no message provided"
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
        commit_msg="Update TEE"
    fi
fi

# Setup logging
LOGFILE="$(pwd)/save.log"
log(){
  echo "$(date --iso-8601=seconds 2>/dev/null || date) - $*" | tee -a "$LOGFILE"
}

log "Starting save.sh (dry_run=$DRY_RUN no_push=$NO_PUSH autosave=$AUTOSAVE)"

# Stage .ts, .svelte, .py, .wgsl, .json, .md files and configs
# Excludes node_modules, dist, .git, venv, etc.
FIND_CMD=(find . \
    \( -path "./.git" -o -path "./dist" -o -path "./node_modules" -o -path "./venv" -o -path "./.vscode" \) -prune -o \
    -type f \( \
        -name "*.ts" \
        -o -name "*.svelte" \
        -o -name "*.py" \
        -o -name "*.wgsl" \
        -o -name "*.json" \
        -o -name "*.md" \
        -o -name "*.html" \
        -o -name "*.js" \
        -o -name "*.sh" \
        -o -name ".gitignore" \
    \) -print0)

if [ "$DRY_RUN" -eq 1 ]; then
    echo "Dry-run: files matching patterns (excluded dirs pruned):"
    "${FIND_CMD[@]//-print0/-print}" | sed 's/^\.\///'  # pretty print without leading ./
    log "Dry-run listing displayed"
else
    # Stage found files
    log "Staging .ts/.svelte/.py/.wgsl files"
    "${FIND_CMD[@]}" | xargs -0 git add -- || true

    # Also stage configuration files explicitly
    if [ -f "package.json" ]; then git add package.json; fi
    if [ -f "package-lock.json" ]; then git add package-lock.json; fi
    if [ -f "tsconfig.json" ]; then git add tsconfig.json; fi
    if [ -f "vite.config.ts" ]; then git add vite.config.ts; fi
    if [ -f "svelte.config.js" ]; then git add svelte.config.js; fi
    if [ -f "README.md" ]; then git add README.md; fi
fi

# Remove deleted files from the index (in case files were deleted)
if [ "$DRY_RUN" -eq 0 ]; then
    log "Removing deleted files from index (if any)"
    git ls-files --deleted -z | xargs -0 -r git rm --cached || true
else
    echo "Dry-run: would remove deleted files from index (git rm)"
    log "Dry-run: would remove deleted files from index"
fi

# Commit if there are staged changes
if git diff --cached --quiet; then
    echo "ℹ️  No code changes staged to commit"
else
    if [ "$DRY_RUN" -eq 1 ]; then
        echo "Dry-run: commit would be created with message: $commit_msg"
        log "Dry-run: commit would be: $commit_msg"
    else
        git commit -m "$commit_msg"
    fi
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
    fi
fi

echo ""

# Step 2: Backup large files to OneDrive
echo "💿 Backing up large files to OneDrive..."
echo ""

# Create OneDrive backup directory if it doesn't exist
ONEDRIVE_BACKUP=~/OneDrive\ -\ University\ of\ Cambridge/top/code/TEE
if [ ! -d "$ONEDRIVE_BACKUP" ]; then
    echo "Creating backup directory: $ONEDRIVE_BACKUP"
    mkdir -p "$ONEDRIVE_BACKUP"
fi

# Backup public/data directory (preprocessed embeddings, sentinel data)
if [ -d "public/data" ]; then
    echo "Backing up public/data directory..."
    rsync -av --progress public/data/ "$ONEDRIVE_BACKUP/public_data/"
    echo "✓ public/data directory backed up"
else
    echo "ℹ️  public/data directory not found (will be created during preprocessing)"
fi

echo ""

# Backup dist directory (production build) if it exists
if [ -d "dist" ]; then
    echo "Backing up dist directory (production build)..."
    rsync -av --progress dist/ "$ONEDRIVE_BACKUP/dist/"
    echo "✓ dist directory backed up"
else
    echo "ℹ️  dist directory not found (run 'npm run build' first)"
fi

echo ""

# Backup venv directory metadata (requirements are in git, but backing up installed packages)
if [ -d "venv" ]; then
    echo "Backing up Python venv metadata..."
    if [ -f "preprocessing/requirements.txt" ]; then
        cp preprocessing/requirements.txt "$ONEDRIVE_BACKUP/requirements.txt"
        echo "✓ requirements.txt backed up"
    fi
else
    echo "ℹ️  venv directory not found"
fi

echo ""

# Backup any large image or data files in root
if ls *.pdf 1> /dev/null 2>&1; then
    echo "Backing up PDF files..."
    rsync -av --progress *.pdf "$ONEDRIVE_BACKUP/"
    echo "✓ PDF files backed up"
fi

if [ -d "images" ]; then
    echo "Backing up images directory..."
    rsync -av --progress images/ "$ONEDRIVE_BACKUP/images/"
    echo "✓ images directory backed up"
fi

echo ""

# Summary
LAST_COMMIT=$(git log -1 --pretty=format:"%h - %s" 2>/dev/null || echo "No commits yet")
echo "✅ Save complete!"
echo ""
echo "📊 Summary:"
echo "   Code: Backed up to GitHub"
echo "   Last commit: $LAST_COMMIT"
echo "   Large files: Backed up to $ONEDRIVE_BACKUP"
echo ""
echo "🔒 Your work is safe!"
echo ""
