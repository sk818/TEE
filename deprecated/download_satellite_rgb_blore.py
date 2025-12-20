#!/usr/bin/env python3
"""
Download Sentinel-2 RGB imagery for viewport specified in viewport.txt
Using Microsoft Planetary Computer (no authentication required)
"""

import planetary_computer
import pystac_client
import rasterio
from rasterio.merge import merge
from rasterio.warp import calculate_default_transform, reproject, Resampling
from pathlib import Path
import numpy as np
from tempfile import TemporaryDirectory
import re

# Configuration
VIEWPORT_FILE = Path("viewport.txt")
YEAR = 2024
RESOLUTION = 10  # meters per pixel

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
OUTPUT_FILE = Path("mosaics/satellite_rgb.tif")

def download_satellite_rgb():
    """Download RGB satellite imagery for specified viewport using Planetary Computer."""

    print(f"Downloading Sentinel-2 RGB imagery from viewport.txt")
    print(f"Bounding box: {BBOX}")
    print(f"Year: {YEAR}")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Resolution: {RESOLUTION}m per pixel")
    print("=" * 60)

    # Check if satellite RGB already exists
    if OUTPUT_FILE.exists():
        print(f"\n✓ Satellite RGB already cached at: {OUTPUT_FILE}")
        size_mb = OUTPUT_FILE.stat().st_size / (1024*1024)
        print(f"  Size: {size_mb:.2f} MB")
        print("  Skipping download...")
        return

    try:
        # Connect to Microsoft Planetary Computer STAC API
        print("\nConnecting to Microsoft Planetary Computer...")
        catalog = pystac_client.Client.open(
            "https://planetarycomputer.microsoft.com/api/stac/v1",
            modifier=planetary_computer.sign_inplace,
        )

        # Search for Sentinel-2 imagery
        print(f"Searching for Sentinel-2 images in {YEAR}...")
        min_lon, min_lat, max_lon, max_lat = BBOX

        search = catalog.search(
            collections=["sentinel-2-l2a"],
            bbox=[min_lon, min_lat, max_lon, max_lat],
            datetime=f"{YEAR}-01-01/{YEAR}-12-31",
            query={"eo:cloud_cover": {"lt": 20}}  # Less than 20% cloud cover
        )

        items = list(search.items())
        print(f"✓ Found {len(items)} images")

        if len(items) == 0:
            print("✗ No images found for the specified criteria")
            return

        # Load and process the data
        print("Loading and compositing imagery...")

        with TemporaryDirectory() as tmpdir:
            # Collect all red, green, blue bands from all items
            red_bands = []
            green_bands = []
            blue_bands = []

            for idx, item in enumerate(items[:10]):  # Limit to 10 clearest images
                print(f"  Processing image {idx+1}/10...")

                # Sign the assets
                signed_item = planetary_computer.sign(item)

                # Get band URLs
                red_url = signed_item.assets['B04'].href
                green_url = signed_item.assets['B03'].href
                blue_url = signed_item.assets['B02'].href

                red_bands.append(red_url)
                green_bands.append(green_url)
                blue_bands.append(blue_url)

            print("Creating median composite and saving...")

            # Process each color band
            rgb_arrays = []
            transform_out = None
            profile = None

            for band_idx, (band_name, band_urls) in enumerate([
                ('red', red_bands),
                ('green', green_bands),
                ('blue', blue_bands)
            ]):
                print(f"  Processing {band_name} band...")

                # Read and merge all tiles for this band IN THEIR NATIVE CRS
                src_files_to_mosaic = []
                for url in band_urls:
                    src = rasterio.open(url)
                    src_files_to_mosaic.append(src)

                # Merge tiles in native CRS (UTM)
                mosaic_utm, transform_utm = merge(src_files_to_mosaic)

                # Get the CRS from the source files
                src_crs = src_files_to_mosaic[0].crs

                # Close files
                for src in src_files_to_mosaic:
                    src.close()

                # Calculate transform for EPSG:4326 output
                # Resolution in degrees (~10m at equator = 0.00009 degrees)
                res_degrees = RESOLUTION / 111000

                # Calculate output dimensions for target bounds in EPSG:4326
                width_4326 = int((max_lon - min_lon) / res_degrees)
                height_4326 = int((max_lat - min_lat) / res_degrees)

                # Calculate target transform for EPSG:4326
                from rasterio.transform import from_bounds
                transform_4326 = from_bounds(min_lon, min_lat, max_lon, max_lat, width_4326, height_4326)

                # Reproject from UTM to EPSG:4326
                mosaic_wgs84 = np.zeros((height_4326, width_4326), dtype=mosaic_utm.dtype)

                reproject(
                    source=mosaic_utm[0] if mosaic_utm.ndim == 3 else mosaic_utm,
                    destination=mosaic_wgs84,
                    src_transform=transform_utm,
                    src_crs=src_crs,
                    dst_transform=transform_4326,
                    dst_crs='EPSG:4326',
                    resampling=Resampling.bilinear
                )

                # Normalize to 0-255
                mosaic_normalized = np.clip(mosaic_wgs84 / 3000 * 255, 0, 255).astype(np.uint8)
                rgb_arrays.append(mosaic_normalized)

                if transform_out is None:
                    transform_out = transform_4326
                    # Create profile for EPSG:4326
                    profile = {
                        'driver': 'GTiff',
                        'crs': 'EPSG:4326',
                        'transform': transform_4326,
                        'width': width_4326,
                        'height': height_4326
                    }

            # Stack RGB
            rgb_stack = np.stack(rgb_arrays, axis=0)

            print(f"  Final shape: {rgb_stack.shape}")

            # Update profile for output
            profile.update({
                'driver': 'GTiff',
                'height': rgb_stack.shape[1],
                'width': rgb_stack.shape[2],
                'count': 3,
                'dtype': 'uint8',
                'transform': transform_out,
                'compress': 'lzw'
            })

            # Save
            print(f"Saving to GeoTIFF: {OUTPUT_FILE}")
            with rasterio.open(OUTPUT_FILE, 'w', **profile) as dst:
                dst.write(rgb_stack)

        size_mb = OUTPUT_FILE.stat().st_size / (1024*1024)
        print(f"✓ Saved: {OUTPUT_FILE} ({size_mb:.2f} MB)")

        # Display info
        with rasterio.open(OUTPUT_FILE) as src:
            print(f"\nImage info:")
            print(f"  Size: {src.width} × {src.height} pixels")
            print(f"  Bands: {src.count} (RGB)")
            print(f"  CRS: {src.crs}")
            print(f"  Bounds: {src.bounds}")

        print("\n✅ Satellite RGB imagery download complete!")

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    download_satellite_rgb()
