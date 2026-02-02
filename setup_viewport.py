#!/usr/bin/env python3
"""
Complete workflow: Download embeddings → Create FAISS indexes → Compute UMAP

Usage:
    python3 setup_viewport.py --years 2022,2023,2024 --umap-year 2024
    python3 setup_viewport.py --years 2024                        (uses 2024 for UMAP)
"""

import sys
import subprocess
from pathlib import Path
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)

REPO_DIR = Path(__file__).parent


def run_command(cmd, description):
    """Run a shell command and check for errors."""
    logger.info(f"\n{'=' * 70}")
    logger.info(f"📍 {description}")
    logger.info(f"{'=' * 70}")
    logger.info(f"$ {' '.join(cmd)}\n")

    result = subprocess.run(cmd, cwd=REPO_DIR)
    if result.returncode != 0:
        logger.error(f"❌ Failed: {description}")
        return False

    logger.info(f"✓ Success: {description}")
    return True


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Complete viewport setup: download embeddings → create FAISS → compute UMAP'
    )
    parser.add_argument(
        '--years',
        type=str,
        required=True,
        help='Comma-separated years (e.g., 2022,2023,2024)'
    )
    parser.add_argument(
        '--umap-year',
        type=str,
        help='Year to compute UMAP from (default: last year in --years)'
    )

    args = parser.parse_args()

    # Parse years
    years = [y.strip() for y in args.years.split(',')]
    logger.info(f"\n🎯 Viewport Setup Workflow")
    logger.info(f"   Years to download: {', '.join(years)}")

    # Determine UMAP year
    umap_year = args.umap_year if args.umap_year else years[-1]
    logger.info(f"   UMAP year: {umap_year}")

    # Step 1: Download embeddings
    logger.info(f"\n{'=' * 70}")
    logger.info(f"STEP 1: Download Embeddings")
    logger.info(f"{'=' * 70}")

    cmd = ['./venv/bin/python3', 'download_embeddings.py', '--years', args.years]
    if not run_command(cmd, f"Download embeddings for {args.years}"):
        return 1

    # Step 2: Create RGB visualizations
    logger.info(f"\n{'=' * 70}")
    logger.info(f"STEP 2: Create RGB Visualizations")
    logger.info(f"{'=' * 70}")

    cmd = ['./venv/bin/python3', 'create_rgb_embeddings.py']
    if not run_command(cmd, f"Create RGB visualizations for all downloaded years"):
        return 1

    # Step 3: Create pyramids (CRITICAL for viewer to work)
    logger.info(f"\n{'=' * 70}")
    logger.info(f"STEP 3: Create Pyramid Tiles")
    logger.info(f"{'=' * 70}")

    cmd = ['./venv/bin/python3', 'create_pyramids.py']
    if not run_command(cmd, f"Create pyramid tiles for web viewing"):
        return 1

    # Step 4: Create FAISS indexes
    logger.info(f"\n{'=' * 70}")
    logger.info(f"STEP 4: Create FAISS Indexes")
    logger.info(f"{'=' * 70}")

    cmd = ['./venv/bin/python3', 'create_faiss_index.py']
    if not run_command(cmd, f"Create FAISS indexes for all downloaded years"):
        return 1

    # Step 5: Compute UMAP
    logger.info(f"\n{'=' * 70}")
    logger.info(f"STEP 5: Compute UMAP")
    logger.info(f"{'=' * 70}")

    # First, get viewport name from active viewport
    try:
        from lib.viewport_utils import get_active_viewport
        viewport = get_active_viewport()
        viewport_name = viewport['viewport_id']
    except Exception as e:
        logger.error(f"❌ Failed to read active viewport: {e}")
        return 1

    cmd = ['./venv/bin/python3', 'compute_umap.py', viewport_name, umap_year]
    if not run_command(cmd, f"Compute UMAP for {viewport_name}/{umap_year}"):
        logger.warning(f"⚠️  UMAP computation failed (may need: pip install umap-learn)")
        return 1

    # Summary
    logger.info(f"\n{'=' * 70}")
    logger.info(f"✅ Viewport Setup Complete!")
    logger.info(f"{'=' * 70}")
    logger.info(f"\n📊 Results:")
    logger.info(f"   Viewport: {viewport_name}")
    logger.info(f"   Years downloaded: {args.years}")
    logger.info(f"   Pyramids: Created for web viewing")
    logger.info(f"   FAISS indexes: Created for each year")
    logger.info(f"   UMAP: Computed for {umap_year}")
    logger.info(f"\n🚀 Next steps:")
    logger.info(f"   1. Run: bash restart.sh")
    logger.info(f"   2. Open: http://localhost:8001")
    logger.info(f"   3. Panel 4 will show UMAP visualization\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
