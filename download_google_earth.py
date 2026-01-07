#!/usr/bin/env python3
"""
Download Google Earth RGB imagery for current viewport
Using Google Earth Engine API

Reads viewport bounds from viewports/viewport.txt instead of hardcoding.
Uses cache checking to avoid re-downloading for previously-selected viewports.
"""

import sys
import ee
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from pathlib import Path
import requests
from io import BytesIO

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).parent))

from lib.viewport_utils import get_active_viewport, check_cache

# Configuration
YEAR = 2024  # Most recent year
SCALE = 10  # meters per pixel (Sentinel-2 resolution)
DATA_DIR = Path.home() / "blore_data"
OUTPUT_FILE = DATA_DIR / "mosaics" / "bangalore_google_earth.tif"

def authenticate_ee():
    """Authenticate with Google Earth Engine."""
    try:
        ee.Initialize()
        print("✓ Already authenticated with Earth Engine")
        return True
    except Exception:
        print("Need to authenticate with Earth Engine...")
        print("This will open a browser window for authentication.")
        try:
            ee.Authenticate()
            ee.Initialize()
            print("✓ Authentication successful")
            return True
        except Exception as e:
            print(f"✗ Authentication failed: {e}")
            return False

def download_rgb_image():
    """Download RGB satellite imagery for current viewport."""

    # Read active viewport
    try:
        viewport = get_active_viewport()
        BBOX = viewport['bounds_tuple']
        viewport_id = viewport['viewport_id']
    except Exception as e:
        print(f"ERROR: Failed to read viewport: {e}", file=sys.stderr)
        return

    # Check cache for matching bounds
    cached_file = check_cache(BBOX, 'satellite')
    if cached_file:
        print(f"✓ Cache hit! Using existing satellite data: {cached_file}")
        return

    print(f"Downloading Google Earth RGB imagery")
    print(f"Viewport: {viewport_id}")
    print(f"Bounding box: {BBOX}")
    print(f"Year: {YEAR}")
    print(f"Output: {OUTPUT_FILE}")
    print("=" * 60)

    # Authenticate
    if not authenticate_ee():
        print("\n⚠️  Please run: earthengine authenticate")
        print("Then run this script again.")
        return

    # Define region of interest
    min_lon, min_lat, max_lon, max_lat = BBOX
    region = ee.Geometry.Rectangle([min_lon, min_lat, max_lon, max_lat])

    print(f"\nFetching Sentinel-2 imagery for {YEAR}...")

    # Get Sentinel-2 surface reflectance imagery
    # Using harmonized data (post-2022 processing)
    collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                  .filterBounds(region)
                  .filterDate(f'{YEAR}-01-01', f'{YEAR}-12-31')
                  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
                  .select(['B4', 'B3', 'B2']))  # Red, Green, Blue

    # Get median composite (reduces clouds and gaps)
    image = collection.median().clip(region)

    # Normalize to 0-255 for RGB display
    # Sentinel-2 values are typically 0-3000 for good reflectance
    image_vis = image.divide(3000).multiply(255).byte()

    print("✓ Image prepared")
    print("Downloading...")

    # Get download URL
    url = image_vis.getDownloadURL({
        'region': region,
        'scale': SCALE,
        'format': 'GEO_TIFF',
        'crs': 'EPSG:4326'
    })

    print(f"Download URL obtained, fetching data...")

    # Download the image
    response = requests.get(url)
    response.raise_for_status()

    # Save to file
    with open(OUTPUT_FILE, 'wb') as f:
        f.write(response.content)

    size_mb = OUTPUT_FILE.stat().st_size / (1024*1024)
    print(f"✓ Saved: {OUTPUT_FILE} ({size_mb:.2f} MB)")

    # Read and display info
    with rasterio.open(OUTPUT_FILE) as src:
        print(f"\nImage info:")
        print(f"  Size: {src.width} × {src.height} pixels")
        print(f"  Bands: {src.count} (RGB)")
        print(f"  CRS: {src.crs}")
        print(f"  Bounds: {src.bounds}")

    print("\n✅ Google Earth imagery download complete!")

if __name__ == "__main__":
    download_rgb_image()
