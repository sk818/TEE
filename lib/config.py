"""
Centralized configuration for TEE (Tessera Embeddings Explorer).

All paths are configurable via environment variables for Docker support.
Defaults to ~/blore_data for local development.
"""

import os
from pathlib import Path

# Base data directory - configurable via BLORE_DATA_DIR env var
DATA_DIR = Path(os.environ.get('BLORE_DATA_DIR', Path.home() / 'blore_data'))

# Subdirectories
MOSAICS_DIR = DATA_DIR / 'mosaics'
PYRAMIDS_DIR = DATA_DIR / 'pyramids'
FAISS_DIR = DATA_DIR / 'faiss_indices'
EMBEDDINGS_DIR = DATA_DIR / 'embeddings'
PROGRESS_DIR = DATA_DIR / 'progress'
# Application directory - configurable via BLORE_APP_DIR env var
APP_DIR = Path(os.environ.get('BLORE_APP_DIR', Path.home() / 'blore'))
VIEWPORTS_DIR = APP_DIR / 'viewports'


def ensure_dirs():
    """Create all required directories if they don't exist."""
    for d in [DATA_DIR, MOSAICS_DIR, PYRAMIDS_DIR, FAISS_DIR, EMBEDDINGS_DIR, PROGRESS_DIR, VIEWPORTS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
