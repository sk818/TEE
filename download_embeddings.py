#!/usr/bin/env python3
"""
Download Tessera embeddings for current viewport

Reads viewport bounds from active viewport configuration.
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
from lib.progress_tracker import ProgressTracker

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

    # Initialize progress tracker
    progress = ProgressTracker(f"{viewport_id}_embeddings")
    progress.update("starting", f"Initializing download for {viewport_id}...")

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
        progress.update("processing", f"Processing year {year}...", current_file=f"embeddings_{year}")

        # Use viewport-specific filename for proper caching across viewports
        output_file = MOSAICS_DIR / f"{viewport_id}_embeddings_{year}.tif"

        # Check cache for matching bounds
        cached_file = check_cache(BBOX, 'embeddings')
        if cached_file:
            print(f"   ✓ Cache hit! Using existing mosaic: {cached_file}")
            progress.update("processing", f"Using cached embeddings for {year}", current_file=f"embeddings_{year}")
            continue

        if output_file.exists():
            print(f"   ✓ Mosaic already exists: {output_file}")
            progress.update("processing", f"Using existing mosaic for {year}", current_file=f"embeddings_{year}")
            continue

        # Retry logic for download and validation
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                print(f"   Downloading and merging tiles (attempt {attempt}/{max_retries})...")
                progress.update("downloading", f"Downloading embeddings for {year} (attempt {attempt}/{max_retries})...", current_file=f"embeddings_{year}")

                # Fetch mosaic for the region (auto-downloads missing tiles)
                mosaic_array, mosaic_transform, crs = tessera.fetch_mosaic_for_region(
                    bbox=BBOX,
                    year=year,
                    target_crs='EPSG:4326',
                    auto_download=True
                )

                print(f"   ✓ Downloaded. Mosaic shape: {mosaic_array.shape}")
                print(f"   Saving to GeoTIFF: {output_file}")
                progress.update("saving", f"Saving embeddings to disk...", current_file=f"embeddings_{year}")

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

                # Validate the saved file
                print(f"   Validating TIFF file...")
                try:
                    with rasterio.open(output_file) as src:
                        _ = src.read(1)  # Try reading first band
                    print(f"   ✓ File validation successful")
                    break  # File is valid, exit retry loop
                except Exception as val_error:
                    print(f"   ✗ File validation failed: {val_error}")
                    output_file.unlink()  # Delete corrupted file
                    if attempt < max_retries:
                        progress.update("processing", f"File corrupted, retrying (attempt {attempt+1}/{max_retries})...", current_file=f"embeddings_{year}")
                        import time
                        time.sleep(5)  # Wait before retry
                        continue
                    else:
                        progress.error(f"File corrupted after {max_retries} attempts for {year}")
                        raise Exception(f"Corrupted file: {val_error}")

            except Exception as e:
                if attempt == max_retries:
                    print(f"   ✗ Error processing {year} after {max_retries} attempts: {e}")
                    import traceback
                    traceback.print_exc()
                    progress.error(f"Error downloading embeddings for {year}: {e}")
                    break
                else:
                    print(f"   ⚠️  Attempt {attempt} failed, retrying: {e}")
                    progress.update("processing", f"Download failed, retrying (attempt {attempt+1}/{max_retries})...", current_file=f"embeddings_{year}")
                    import time
                    time.sleep(5)  # Wait before retry
                    continue

        # Only continue to next year if this year was successful
        if output_file.exists():
            size_mb = output_file.stat().st_size / (1024*1024)
            print(f"   ✓ Saved: {output_file} ({size_mb:.2f} MB)")
            progress.update("processing", f"Saved {size_mb:.1f} MB", current_value=int(size_mb), current_file=f"embeddings_{year}")

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
        progress.complete(f"Downloaded {total_size:.1f} MB of embeddings")
    else:
        print("\n⚠️  No mosaics were created.")
        progress.complete("No new mosaics downloaded (already cached)")

if __name__ == "__main__":
    download_embeddings()
