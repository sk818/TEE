#!/usr/bin/env python3
"""
Download Google Earth RGB imagery for viewport specified in viewport.txt
Using Google Earth Engine API
"""

import ee
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from pathlib import Path
import requests
from io import BytesIO
import re

# Configuration
VIEWPORT_FILE = Path("viewport.txt")
YEAR = 2024  # Most recent year
SCALE = 10  # meters per pixel (Sentinel-2 resolution)

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
OUTPUT_FILE = Path("mosaics/google_earth_rgb.tif")

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
    """Download RGB satellite imagery for specified viewport."""

    print(f"Downloading Google Earth RGB imagery from viewport.txt")
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
