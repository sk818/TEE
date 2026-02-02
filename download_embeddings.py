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
DEFAULT_YEARS = range(2017, 2026)  # Support 2017-2025 (Sentinel-2 availability)
DATA_DIR = Path.home() / "blore_data"
EMBEDDINGS_DIR = DATA_DIR / "embeddings"
MOSAICS_DIR = DATA_DIR / "mosaics"

# Parse command line arguments for year selection
import argparse
parser = argparse.ArgumentParser(description='Download Tessera embeddings')
parser.add_argument('--years', type=str, help='Comma-separated years to download (e.g., 2017,2018,2024)')
args = parser.parse_args()

if args.years:
    try:
        # Parse comma-separated years and convert to integers
        requested_years = sorted([int(y.strip()) for y in args.years.split(',') if y.strip()])
        if requested_years:
            YEARS = requested_years
        else:
            YEARS = DEFAULT_YEARS
    except (ValueError, IndexError):
        YEARS = DEFAULT_YEARS
else:
    YEARS = DEFAULT_YEARS

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

    # Track successful downloads for metadata
    successful_years = []

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
            successful_years.append(year)
            continue

        if output_file.exists():
            print(f"   ✓ Mosaic already exists: {output_file}")
            actual_size_mb = output_file.stat().st_size / (1024 * 1024)
            print(f"     Actual size: {actual_size_mb:.1f} MB")
            progress.update("processing", f"Using existing mosaic for {year}", current_file=output_file.name, current_value=est_bytes, total_value=est_bytes)
            successful_years.append(year)
            continue

        # Retry logic for download and validation
        max_retries = 3
        year_success = False

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
                    year_success = True
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
                    print(f"   ⚠️  Year {year} not available: {e}")
                    progress.update("processing", f"Year {year} not available, skipping...", current_file=output_file.name)
                    break
                else:
                    print(f"   ⚠️  Attempt {attempt} failed, retrying: {e}")
                    progress.update("processing", f"Download failed, retrying (attempt {attempt+1}/{max_retries})...", current_file=output_file.name)
                    import time
                    time.sleep(5)  # Wait before retry
                    continue

        # Track successful downloads
        if output_file.exists() and year_success:
            size_mb = output_file.stat().st_size / (1024*1024)
            print(f"   ✓ Saved: {output_file} ({size_mb:.2f} MB)")
            progress.update("processing", f"Saved {output_file.name} ({size_mb:.1f} MB)", current_value=int(size_mb), current_file=output_file.name)
            successful_years.append(year)

    print("\n" + "=" * 60)
    print("Download complete!")
    print(f"\nTiles cached in: {EMBEDDINGS_DIR.absolute()}")
    print(f"Mosaics saved in: {MOSAICS_DIR.absolute()}")

    # Save metadata about successful downloads
    metadata_file = MOSAICS_DIR / f"{viewport_id}_years.json"
    metadata = {'available_years': sorted(successful_years)}
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f)
    print(f"✓ Saved metadata: {metadata_file}")
    print(f"Successfully downloaded years: {sorted(successful_years)}")

    # Check if any mosaics were successfully created
    if successful_years:
        print(f"\n✓ Created mosaics for {viewport_id}:")
        total_size_mb = 0
        for year in successful_years:
            mosaic_file = MOSAICS_DIR / f"{viewport_id}_embeddings_{year}.tif"
            if mosaic_file.exists():
                size_mb = mosaic_file.stat().st_size / (1024*1024)
                total_size_mb += size_mb
                compression_ratio = (size_mb / (est_mb / COMPRESSION_RATIO)) * 100 if est_mb > 0 else 0
                print(f"  - {mosaic_file.name} ({size_mb:.1f} MB, {compression_ratio:.1f}% compression)")
        print(f"\nTotal downloaded: {total_size_mb:.1f} MB for {len(successful_years)} years")
        progress.complete(f"Downloaded {total_size_mb:.1f} MB of embeddings ({len(successful_years)} years)")
    else:
        print(f"\n✗ Error: No mosaics for {viewport_id} were created (all downloads failed)")
        progress.error(f"Failed to download embeddings for any year")

if __name__ == "__main__":
    download_embeddings()
