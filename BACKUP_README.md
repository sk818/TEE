# Backup & Restore Guide

This project uses a two-part backup strategy to keep your work safe:

## 📁 Directory Structure

```
~/blore/                          # Git repository (source code only)
  ├── save.sh                      # Backup script
  ├── restore.sh                   # Restore script
  ├── src/                         # Python source code
  ├── public/                      # Web frontend
  └── (mosaics/, embeddings/, etc. NOT here)

~/blore_data/                      # Large data files (outside git)
  ├── mosaics/                     # Satellite imagery
  ├── embeddings/                  # Embedding vectors
  ├── pyramids/                    # Pyramid tiles
  └── faiss_indices/               # FAISS search indices

OneDrive/research/blore/data/      # Cloud backup of large files
  ├── mosaics/
  ├── embeddings/
  ├── pyramids/
  └── faiss_indices/
```

## 🚀 Quick Start

### Save Your Work

```bash
cd ~/blore
./save.sh
```

This will:
1. **Commit code changes** to GitHub (source code, configs, scripts)
2. **Backup data files** to OneDrive (mosaics, embeddings, pyramids, FAISS indices)

### Options

```bash
# Dry run - see what would be backed up without doing it
./save.sh --dry-run

# Commit code but don't push to remote
./save.sh --no-push

# Skip OneDrive data backup (code only)
./save.sh --no-data

# Use automatic timestamp for commit message
./save.sh --autosave

# Show help
./save.sh --help
```

### Restore Your Work

```bash
cd ~/blore
./restore.sh
```

This will:
1. Download large data files from OneDrive to `~/blore_data/`
2. Create symlinks in the project directory

Useful when:
- Cloning the repository on a new machine
- Recovering from accidental data deletion
- Syncing data with OneDrive backups

## 📊 What Gets Backed Up

### Git (Code) → GitHub
- Python scripts (`.py`)
- Web frontend (`.html`, `.js`, `.css`)
- Configuration files (`.json`, `.txt`, `.md`)
- Shell scripts (`.sh`)
- **NOT**: large binary files or generated data

### Data Files → OneDrive
- `mosaics/` - Satellite imagery GeoTIFFs (24GB)
- `embeddings/` - 128-dim embedding vectors (19GB)
- `pyramids/` - Multi-level pyramid tiles (735MB)
- `faiss_indices/` - FAISS search indices (168MB)

## 🔧 Manual Backup

If you prefer to backup manually:

```bash
# Backup to OneDrive
rsync -av ~/blore_data/mosaics/ \
  "~/OneDrive - University of Cambridge/research/blore/data/mosaics/"

# Restore from OneDrive
rsync -av \
  "~/OneDrive - University of Cambridge/research/blore/data/mosaics/" \
  ~/blore_data/mosaics/
```

## 📝 Log Files

Each backup/restore operation creates a log:

```bash
# View backup logs
tail -f ~/blore/save.log

# View restore logs
tail -f ~/blore/restore.log
```

## ⚙️ Setup for New Machine

If cloning the repo on a new machine:

```bash
# 1. Clone the repository
git clone <repo-url> ~/blore
cd ~/blore

# 2. Restore data from OneDrive
./restore.sh

# 3. Verify everything is in place
ls -lh mosaics embeddings pyramids faiss_indices
```

## 🚨 Troubleshooting

### OneDrive directory not found
- Make sure OneDrive is running and synced
- Check path: `~/OneDrive - University of Cambridge/research/blore/data/`
- Create directories manually if needed:
  ```bash
  mkdir -p ~/OneDrive\ -\ University\ of\ Cambridge/research/blore/data
  ```

### Symlinks not working
- Python scripts may expect symlinks or the actual directories
- If symlinks don't work, use the actual paths:
  - Mosaics: `~/blore_data/mosaics/`
  - Embeddings: `~/blore_data/embeddings/`
  - Pyramids: `~/blore_data/pyramids/`
  - FAISS: `~/blore_data/faiss_indices/`

### Large files still tracked in git
- If you accidentally committed large files before cleanup:
  ```bash
  # This was done already, but check:
  du -sh .git  # Should be ~188KB, not 67GB
  ```

## 💡 Best Practices

1. **Run save.sh regularly** - After significant changes or before leaving
2. **Use descriptive commit messages** - Makes it easier to find changes later
3. **Check git status** - Before saving, see what changed: `git status`
4. **Monitor OneDrive sync** - Ensure files are fully synced to cloud
5. **Test restore** - Occasionally test restore.sh to ensure backups are good

## 📞 Need Help?

- View script help: `./save.sh --help`
- Check logs: `tail -f save.log` or `tail -f restore.log`
- Test with dry-run: `./save.sh --dry-run`
