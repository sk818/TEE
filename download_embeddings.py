#!/usr/bin/env python3
"""
Download Tessera embeddings for Bangalore region

Reads viewport bounds from viewports/viewport.txt instead of hardcoding.
Uses cache checking to avoid re-downloading for previously-selected viewports.
"""

import sys
import numpy as np
import rasterio
from rasterio.transform import Affine
from pathlib import Path
import geotessera as gt

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).parent))

from lib.viewport_utils import get_active_viewport, check_cache

# Configuration
YEARS = range(2024, 2025)  # 2024 only for faster download
DATA_DIR = Path.home() / "blore_data"
EMBEDDINGS_DIR = DATA_DIR / "embeddings"
MOSAICS_DIR = DATA_DIR / "mosaics"

def download_embeddings():
    """Download Tessera embeddings for current viewport."""

    # Read active viewport
    try:
        viewport = get_active_viewport()
        BBOX = viewport['bounds_tuple']
        viewport_id = viewport['viewport_id']
    except Exception as e:
        print(f"ERROR: Failed to read viewport: {e}", file=sys.stderr)
        sys.exit(1)

    # Create output directories
    EMBEDDINGS_DIR.mkdir(exist_ok=True)
    MOSAICS_DIR.mkdir(exist_ok=True)

    print(f"Downloading Tessera embeddings")
    print(f"Viewport: {viewport_id}")
    print(f"Bounding box: {BBOX}")
    print(f"Years: {min(YEARS)} to {max(YEARS)}")
    print(f"Embeddings will be downloaded to: {EMBEDDINGS_DIR.absolute()}")
    print(f"Mosaics will be saved to: {MOSAICS_DIR.absolute()}")
    print("=" * 60)

    # Initialize GeoTessera with embeddings directory
    tessera = gt.GeoTessera(embeddings_dir=str(EMBEDDINGS_DIR))

    for year in YEARS:
        print(f"\n📅 Processing year {year}...")
        output_file = MOSAICS_DIR / f"bangalore_{year}.tif"

        # Check cache for matching bounds
        cached_file = check_cache(BBOX, 'embeddings')
        if cached_file:
            print(f"   ✓ Cache hit! Using existing mosaic: {cached_file}")
            continue

        if output_file.exists():
            print(f"   ✓ Mosaic already exists: {output_file}")
            continue

        try:
            print(f"   Downloading and merging tiles...")

            # Fetch mosaic for the region (auto-downloads missing tiles)
            mosaic_array, mosaic_transform, crs = tessera.fetch_mosaic_for_region(
                bbox=BBOX,
                year=year,
                target_crs='EPSG:4326',
                auto_download=True
            )

            print(f"   ✓ Downloaded. Mosaic shape: {mosaic_array.shape}")
            print(f"   Saving to GeoTIFF: {output_file}")

            # Save mosaic to GeoTIFF
            height, width, bands = mosaic_array.shape

            with rasterio.open(
                output_file,
                'w',
                driver='GTiff',
                height=height,
                width=width,
                count=bands,
                dtype=mosaic_array.dtype,
                crs=crs,
                transform=mosaic_transform,
                compress='lzw'
            ) as dst:
                # Write each band
                for band in range(bands):
                    dst.write(mosaic_array[:, :, band], band + 1)

            size_mb = output_file.stat().st_size / (1024*1024)
            print(f"   ✓ Saved: {output_file} ({size_mb:.2f} MB)")

        except Exception as e:
            print(f"   ✗ Error processing {year}: {e}")
            import traceback
            traceback.print_exc()
            continue

    print("\n" + "=" * 60)
    print("Download complete!")
    print(f"\nTiles cached in: {EMBEDDINGS_DIR.absolute()}")
    print(f"Mosaics saved in: {MOSAICS_DIR.absolute()}")

    # List downloaded mosaics
    files = list(MOSAICS_DIR.glob("*.tif"))
    if files:
        print(f"\n✓ Created {len(files)} mosaics:")
        total_size = 0
        for f in sorted(files):
            size_mb = f.stat().st_size / (1024*1024)
            total_size += size_mb
            print(f"  - {f.name} ({size_mb:.2f} MB)")
        print(f"\nTotal size: {total_size:.2f} MB")
    else:
        print("\n⚠️  No mosaics were created.")

if __name__ == "__main__":
    download_embeddings()
