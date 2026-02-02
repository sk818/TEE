#!/usr/bin/env python3
"""
Compute UMAP 2D projection of embeddings.

Usage:
    python3 compute_umap.py Eddington 2024
"""

import sys
import numpy as np
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

DATA_DIR = Path.home() / "blore_data"
FAISS_INDICES_DIR = DATA_DIR / "faiss_indices"


def compute_umap(viewport_name, year):
    """Compute UMAP for embeddings."""
    try:
        import umap
    except ImportError:
        logger.error("❌ UMAP not installed. Install with: pip install umap-learn")
        return False

    faiss_dir = FAISS_INDICES_DIR / viewport_name / str(year)

    if not faiss_dir.exists():
        logger.error(f"❌ FAISS index not found: {faiss_dir}")
        return False

    embeddings_file = faiss_dir / "all_embeddings.npy"
    if not embeddings_file.exists():
        logger.error(f"❌ Embeddings not found: {embeddings_file}")
        return False

    umap_file = faiss_dir / "umap_coords.npy"
    if umap_file.exists():
        logger.info(f"✓ Already computed: {umap_file}")
        return True

    logger.info(f"📊 Computing UMAP for {viewport_name}/{year}...")
    logger.info(f"   Loading embeddings...")

    try:
        embeddings = np.load(str(embeddings_file))
        logger.info(f"   Embeddings: {embeddings.shape}")

        logger.info(f"   Fitting UMAP...")
        reducer = umap.UMAP(
            n_neighbors=15,
            min_dist=0.1,
            n_components=2,
            n_jobs=1,
            verbose=False
        )
        umap_coords = reducer.fit_transform(embeddings)

        logger.info(f"   Saving UMAP...")
        np.save(str(umap_file), umap_coords)
        size_mb = umap_file.stat().st_size / (1024 * 1024)
        logger.info(f"✓ UMAP saved: {umap_file}")
        logger.info(f"   Size: {size_mb:.1f} MB")

        return True

    except Exception as e:
        logger.error(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    if len(sys.argv) < 3:
        logger.error("Usage: python3 compute_umap.py <viewport> <year>")
        logger.error("Example: python3 compute_umap.py Eddington 2024")
        sys.exit(1)

    viewport = sys.argv[1]
    year = int(sys.argv[2])

    success = compute_umap(viewport, year)
    sys.exit(0 if success else 1)
