#!/usr/bin/env python3
"""
Download Tessera embeddings for viewport specified in viewport.txt
"""

import numpy as np
import rasterio
from rasterio.transform import Affine
from pathlib import Path
import geotessera as gt
import re

# Configuration
YEARS = range(2017, 2025)  # 2017-2024
EMBEDDINGS_DIR = Path("embeddings")
MOSAICS_DIR = Path("mosaics")
VIEWPORT_FILE = Path("viewport.txt")

def parse_viewport_bounds():
    """Parse viewport.txt and extract bounds as BBOX (min_lon, min_lat, max_lon, max_lat)."""
    try:
        with open(VIEWPORT_FILE, 'r') as f:
            content = f.read()

        # Extract bounds using regex
        min_lat_match = re.search(r'Min Latitude:\s*([-\d.]+)°', content)
        max_lat_match = re.search(r'Max Latitude:\s*([-\d.]+)°', content)
        min_lon_match = re.search(r'Min Longitude:\s*([-\d.]+)°', content)
        max_lon_match = re.search(r'Max Longitude:\s*([-\d.]+)°', content)

        if not all([min_lat_match, max_lat_match, min_lon_match, max_lon_match]):
            raise ValueError("Could not parse all bounds from viewport.txt")

        min_lat = float(min_lat_match.group(1))
        max_lat = float(max_lat_match.group(1))
        min_lon = float(min_lon_match.group(1))
        max_lon = float(max_lon_match.group(1))

        bbox = (min_lon, min_lat, max_lon, max_lat)
        return bbox
    except FileNotFoundError:
        raise FileNotFoundError(f"viewport.txt not found at {VIEWPORT_FILE.absolute()}")

# Load BBOX from viewport.txt
BBOX = parse_viewport_bounds()

def download_embeddings():
    """Download Tessera embeddings for specified viewport."""

    # Create output directories
    EMBEDDINGS_DIR.mkdir(exist_ok=True)
    MOSAICS_DIR.mkdir(exist_ok=True)

    print(f"Downloading Tessera embeddings from viewport.txt")
    print(f"Bounding box: {BBOX}")
    print(f"Years: {min(YEARS)} to {max(YEARS)}")
    print(f"Embeddings will be downloaded to: {EMBEDDINGS_DIR.absolute()}")
    print(f"Mosaics will be saved to: {MOSAICS_DIR.absolute()}")
    print("=" * 60)

    # Initialize GeoTessera with embeddings directory
    tessera = gt.GeoTessera(embeddings_dir=str(EMBEDDINGS_DIR))

    for year in YEARS:
        # Check if embeddings for this year are already cached
        year_cache_dir = EMBEDDINGS_DIR / str(year)
        cached_tiles = list(year_cache_dir.glob("*.tif")) + list(year_cache_dir.glob("*/*.tif")) if year_cache_dir.exists() else []

        mosaic_output = MOSAICS_DIR / f"bangalore_{year}.tif"
        if mosaic_output.exists() and cached_tiles:
            print(f"\n📅 Year {year}: ✓ Already cached and processed, skipping...")
            continue

        print(f"\n📅 Processing year {year}...")
        output_file = MOSAICS_DIR / f"bangalore_{year}.tif"

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
