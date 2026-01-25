#!/usr/bin/env python3
"""
Download Tessera embeddings for current viewport

Reads viewport bounds from active viewport configuration.
Uses cache checking to avoid re-downloading for previously-selected viewports.
"""

import sys
import json
import numpy as np
import rasterio
from rasterio.transform import Affine
from pathlib import Path
import geotessera as gt

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).parent))

from lib.viewport_utils import get_active_viewport, check_cache
from lib.progress_tracker import ProgressTracker
import math

# Configuration
YEARS = range(2024, 2025)  # 2024 only for faster download
DATA_DIR = Path.home() / "blore_data"
EMBEDDINGS_DIR = DATA_DIR / "embeddings"
MOSAICS_DIR = DATA_DIR / "mosaics"

# Tessera embeddings parameters
EMBEDDING_BANDS = 128
BYTES_PER_BAND = 4  # float32
PIXEL_SIZE_METERS = 10
METERS_PER_DEGREE_LAT = 111320  # Constant
COMPRESSION_RATIO = 0.4  # LZW compression typically achieves ~40% of original size

def estimate_mosaic_dimensions(bbox):
    """Estimate mosaic dimensions from bounding box.

    Args:
        bbox: tuple of (lon_min, lat_min, lon_max, lat_max)

    Returns:
        tuple of (estimated_width, estimated_height, estimated_file_size_mb)
    """
    lon_min, lat_min, lon_max, lat_max = bbox

    # Calculate center latitude for longitude scaling
    center_lat = (lat_min + lat_max) / 2
    cos_lat = math.cos(math.radians(center_lat))

    # Meters per degree at this latitude
    meters_per_degree_lon = METERS_PER_DEGREE_LAT * cos_lat

    # Calculate dimensions in pixels
    height_pixels = int((lat_max - lat_min) * METERS_PER_DEGREE_LAT / PIXEL_SIZE_METERS)
    width_pixels = int((lon_max - lon_min) * meters_per_degree_lon / PIXEL_SIZE_METERS)

    # Calculate uncompressed file size (width × height × bands × bytes_per_band)
    uncompressed_bytes = width_pixels * height_pixels * EMBEDDING_BANDS * BYTES_PER_BAND

    # Estimate compressed size with LZW compression
    compressed_bytes = int(uncompressed_bytes * COMPRESSION_RATIO)
    compressed_mb = compressed_bytes / (1024 * 1024)

    return width_pixels, height_pixels, compressed_mb, compressed_bytes

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

    # Estimate file size and dimensions
    est_width, est_height, est_mb, est_bytes = estimate_mosaic_dimensions(BBOX)
    print(f"\nEstimated dimensions: {est_width} × {est_height} pixels")
    print(f"Estimated file size (compressed): {est_mb:.1f} MB")

    print(f"\nEmbeddings will be downloaded to: {EMBEDDINGS_DIR.absolute()}")
    print(f"Mosaics will be saved to: {MOSAICS_DIR.absolute()}")
    print("=" * 60)

    # Initialize GeoTessera with embeddings directory
    tessera = gt.GeoTessera(embeddings_dir=str(EMBEDDINGS_DIR))

    # Track whether current viewport's mosaic was successfully created
    viewport_mosaic_created = False

    for year in YEARS:
        print(f"\n📅 Processing year {year}...")

        # Use viewport-specific filename for proper caching across viewports
        output_file = MOSAICS_DIR / f"{viewport_id}_embeddings_{year}.tif"

        print(f"   Target file: {output_file.name}")
        print(f"   Expected size: {est_mb:.1f} MB")
        progress.update("processing", f"Processing year {year}...", current_file=output_file.name, total_value=est_bytes)

        # Check cache for matching bounds
        cached_file = check_cache(BBOX, 'embeddings')
        if cached_file:
            print(f"   ✓ Cache hit! Using existing mosaic: {cached_file}")
            progress.update("processing", f"Using cached embeddings for {year}", current_file=output_file.name, current_value=est_bytes, total_value=est_bytes)
            continue

        if output_file.exists():
            print(f"   ✓ Mosaic already exists: {output_file}")
            actual_size_mb = output_file.stat().st_size / (1024 * 1024)
            print(f"     Actual size: {actual_size_mb:.1f} MB")
            progress.update("processing", f"Using existing mosaic for {year}", current_file=output_file.name, current_value=est_bytes, total_value=est_bytes)
            continue

        # Retry logic for download and validation
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                print(f"   Downloading and merging tiles (attempt {attempt}/{max_retries})...")
                progress.update("downloading", f"Downloading {output_file.name} - {est_width} × {est_height} pixels (~{est_mb:.1f} MB) - Attempt {attempt}/{max_retries}", current_file=output_file.name)

                # Define progress callback to capture geotessera tile downloads
                def on_geotessera_progress(current, total, status):
                    # status contains information about tiles being downloaded (e.g., "Fetching tile X")
                    progress.update("downloading", f"Downloading {output_file.name} ({est_mb:.1f} MB): {status}", current_value=current, total_value=total, current_file=f"{output_file.name} - {status}")

                # Fetch mosaic for the region (auto-downloads missing tiles)
                mosaic_array, mosaic_transform, crs = tessera.fetch_mosaic_for_region(
                    bbox=BBOX,
                    year=year,
                    target_crs='EPSG:4326',
                    auto_download=True,
                    progress_callback=on_geotessera_progress
                )

                print(f"   ✓ Downloaded. Mosaic shape: {mosaic_array.shape}")
                print(f"   Saving to GeoTIFF: {output_file}")

                # Save mosaic to GeoTIFF
                height, width, bands = mosaic_array.shape
                progress.update("saving", f"Writing {output_file.name} ({est_mb:.1f} MB) to disk - {bands} bands...", current_file=output_file.name, current_value=0, total_value=bands)

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
                        # Update progress: show bands written
                        progress.update("saving", f"Writing band {band+1}/{bands}...", current_file=output_file.name, current_value=band+1, total_value=bands)

                # Validate the saved file
                print(f"   Validating TIFF file...")
                try:
                    with rasterio.open(output_file) as src:
                        _ = src.read(1)  # Try reading first band
                    print(f"   ✓ File validation successful")

                    # Report actual file size
                    actual_size_mb = output_file.stat().st_size / (1024 * 1024)
                    print(f"   File size: {actual_size_mb:.1f} MB (estimated: {est_mb:.1f} MB)")
                    progress.update("processing", f"✓ Saved {output_file.name}: {actual_size_mb:.1f} MB ({est_width} × {est_height} pixels)", current_file=output_file.name, current_value=est_bytes, total_value=est_bytes)
                    break  # File is valid, exit retry loop
                except Exception as val_error:
                    print(f"   ✗ File validation failed: {val_error}")
                    output_file.unlink()  # Delete corrupted file
                    if attempt < max_retries:
                        progress.update("processing", f"File corrupted, retrying (attempt {attempt+1}/{max_retries})...", current_file=output_file.name)
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
                    progress.update("processing", f"Download failed, retrying (attempt {attempt+1}/{max_retries})...", current_file=output_file.name)
                    import time
                    time.sleep(5)  # Wait before retry
                    continue

        # Only continue to next year if this year was successful
        if output_file.exists():
            size_mb = output_file.stat().st_size / (1024*1024)
            print(f"   ✓ Saved: {output_file} ({size_mb:.2f} MB)")
            progress.update("processing", f"Saved {output_file.name} ({size_mb:.1f} MB)", current_value=int(size_mb), current_file=output_file.name)
            viewport_mosaic_created = True

    print("\n" + "=" * 60)
    print("Download complete!")
    print(f"\nTiles cached in: {EMBEDDINGS_DIR.absolute()}")
    print(f"Mosaics saved in: {MOSAICS_DIR.absolute()}")

    # Check if this viewport's mosaic was successfully created
    viewport_mosaic_file = MOSAICS_DIR / f"{viewport_id}_embeddings_2024.tif"

    if viewport_mosaic_file.exists():
        size_mb = viewport_mosaic_file.stat().st_size / (1024*1024)
        compression_ratio = (size_mb / (est_mb / COMPRESSION_RATIO)) * 100 if est_mb > 0 else 0
        print(f"\n✓ Created mosaic for {viewport_id}:")
        print(f"  - {viewport_mosaic_file.name}")
        print(f"    Expected size: {est_mb:.1f} MB")
        print(f"    Actual size:   {size_mb:.1f} MB")
        print(f"    Compression:   {compression_ratio:.1f}%")
        progress.complete(f"Downloaded {size_mb:.1f} MB of embeddings")
    else:
        # Check current status to avoid overwriting detailed error message
        try:
            with open(progress.progress_file, 'r') as f:
                current_progress = json.load(f)
                # Only set generic error if we don't already have a detailed error
                if current_progress.get("status") != "error":
                    print(f"\n✗ Error: Mosaic for {viewport_id} was not created (all downloads failed)")
                    progress.error(f"Failed to download embeddings after {max_retries} attempts")
        except (FileNotFoundError, json.JSONDecodeError):
            # Progress file doesn't exist or is invalid, set generic error
            print(f"\n✗ Error: Mosaic for {viewport_id} was not created (all downloads failed)")
            progress.error(f"Failed to download embeddings after {max_retries} attempts")

if __name__ == "__main__":
    download_embeddings()
