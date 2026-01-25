#!/usr/bin/env python3
"""
Download high-resolution RGB imagery for current viewport from Google Earth Engine.
Will search for the best available imagery including:
- Commercial high-res imagery (if available)
- Planet imagery (if available)
- Sentinel-2 as fallback

Reads viewport bounds from viewports/viewport.txt instead of hardcoding.
Uses cache checking to avoid re-downloading for previously-selected viewports.
Requires Google Earth Engine authentication.
"""

import sys
import ee
import geemap
import os
from pathlib import Path

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).parent))

from lib.viewport_utils import get_active_viewport, check_cache

# Configuration
YEAR = 2024
MAX_RESOLUTION_M = 5  # Target maximum 5m resolution
DATA_DIR = Path.home() / "blore_data"

def init_ee():
    """Initialize Earth Engine."""
    PROJECT_ID = '773394289916'

    try:
        # Initialize with specific project
        ee.Initialize(project=PROJECT_ID, opt_url='https://earthengine-highvolume.googleapis.com')
        print(f"✓ Earth Engine initialized with project {PROJECT_ID}")
        return True
    except Exception as e1:
        print(f"  First attempt failed: {e1}")
        try:
            # Try without high-volume URL
            print("  Trying standard endpoint...")
            ee.Initialize(project=PROJECT_ID)
            print(f"✓ Earth Engine initialized with project {PROJECT_ID}")
            return True
        except Exception as e2:
            print(f"✗ Earth Engine initialization failed: {e2}")
            print("\nTroubleshooting steps:")
            print("1. Make sure Earth Engine API is enabled at:")
            print(f"   https://console.cloud.google.com/apis/library/earthengine.googleapis.com?project={PROJECT_ID}")
            print("2. Re-run: earthengine authenticate --force")
            return False

def search_high_res_imagery(BBOX):
    """Search for available high-resolution imagery over current viewport."""

    # Define area of interest
    min_lon, min_lat, max_lon, max_lat = BBOX
    aoi = ee.Geometry.Rectangle([min_lon, min_lat, max_lon, max_lat])

    print(f"\nSearching for high-resolution imagery...")
    print(f"Area: {BBOX}")
    print(f"Target year: {YEAR}")
    print("=" * 70)

    available_sources = []

    # 1. Try Sentinel-2 Level-2A (10m RGB - baseline)
    try:
        s2 = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
              .filterBounds(aoi)
              .filterDate(f'{YEAR}-01-01', f'{YEAR}-12-31')
              .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)))

        count = s2.size().getInfo()
        if count > 0:
            available_sources.append({
                'name': 'Sentinel-2',
                'collection': s2,
                'resolution': 10,
                'bands': ['B4', 'B3', 'B2'],  # RGB
                'scale_name': ['Red', 'Green', 'Blue']
            })
            print(f"✓ Sentinel-2 (10m): {count} images available")
    except Exception as e:
        print(f"  Sentinel-2: Not available ({e})")

    # 2. Try Planet imagery (3-5m if available - usually requires subscription)
    try:
        planet = (ee.ImageCollection('projects/planet-nicfi/assets/basemaps/asia')
                  .filterBounds(aoi)
                  .filterDate(f'{YEAR}-01-01', f'{YEAR}-12-31'))

        count = planet.size().getInfo()
        if count > 0:
            available_sources.append({
                'name': 'Planet NICFI',
                'collection': planet,
                'resolution': 4.77,
                'bands': ['R', 'G', 'B'],
                'scale_name': ['Red', 'Green', 'Blue']
            })
            print(f"✓ Planet NICFI (4.77m): {count} images available")
    except Exception as e:
        print(f"  Planet: Not available ({e})")

    # 3. Try Google's high-resolution imagery (if available for the area)
    # Note: This may not be programmatically accessible

    if not available_sources:
        print("✗ No imagery sources available")
        return None

    # Select best available source (lowest resolution number = highest quality)
    best_source = min(available_sources, key=lambda x: x['resolution'])
    print(f"\n✓ Best available: {best_source['name']} at {best_source['resolution']}m resolution")

    return best_source

def download_imagery(source_info, output_file):
    """Download imagery from the selected source in tiles."""
    import rasterio
    from rasterio.merge import merge as rasterio_merge
    from rasterio.io import MemoryFile
    from tempfile import TemporaryDirectory

    min_lon, min_lat, max_lon, max_lat = BBOX

    print(f"\nDownloading {source_info['name']} imagery...")
    print(f"  Region: {BBOX}")
    print(f"  Resolution: {source_info['resolution']}m/pixel")
    print(f"  Bands: {source_info['bands']} -> RGB")
    print(f"  CRS: EPSG:4326")

    # Get median composite to reduce clouds
    collection = source_info['collection']
    median_img = collection.median()

    # Select RGB bands
    rgb = median_img.select(source_info['bands'])

    # Split area into smaller tiles (2x2 grid = 4 tiles)
    lon_step = (max_lon - min_lon) / 2
    lat_step = (max_lat - min_lat) / 2

    tiles = []
    for i in range(2):
        for j in range(2):
            tile_min_lon = min_lon + i * lon_step
            tile_max_lon = min_lon + (i + 1) * lon_step
            tile_min_lat = min_lat + j * lat_step
            tile_max_lat = min_lat + (j + 1) * lat_step

            tiles.append({
                'bounds': [tile_min_lon, tile_min_lat, tile_max_lon, tile_max_lat],
                'name': f'tile_{i}_{j}'
            })

    print(f"\nDownloading in {len(tiles)} tiles to avoid size limits...")
    output_file.parent.mkdir(exist_ok=True)

    try:
        with TemporaryDirectory() as tmpdir:
            tile_files = []

            for idx, tile in enumerate(tiles):
                print(f"  Downloading tile {idx+1}/{len(tiles)}...")

                aoi = ee.Geometry.Rectangle(tile['bounds'])
                rgb_clipped = rgb.clip(aoi)

                tile_file = Path(tmpdir) / f"{tile['name']}.tif"

                try:
                    geemap.ee_export_image(
                        rgb_clipped,
                        filename=str(tile_file),
                        scale=source_info['resolution'],
                        region=aoi,
                        file_per_band=False
                    )

                    if tile_file.exists():
                        tile_files.append(str(tile_file))
                        size_kb = tile_file.stat().st_size / 1024
                        print(f"    ✓ Tile {idx+1} downloaded ({size_kb:.1f} KB)")
                    else:
                        print(f"    ✗ Tile {idx+1} failed")

                except Exception as e:
                    print(f"    ✗ Tile {idx+1} error: {e}")
                    continue

            if not tile_files:
                print("✗ No tiles downloaded successfully")
                return False

            # Merge tiles
            print(f"\nMerging {len(tile_files)} tiles...")
            src_files_to_mosaic = []

            for tile_file in tile_files:
                src = rasterio.open(tile_file)
                src_files_to_mosaic.append(src)

            mosaic, out_trans = rasterio_merge(src_files_to_mosaic)

            # Get metadata from first file
            out_meta = src_files_to_mosaic[0].meta.copy()
            out_meta.update({
                "driver": "GTiff",
                "height": mosaic.shape[1],
                "width": mosaic.shape[2],
                "transform": out_trans,
                "compress": "lzw"
            })

            # Write merged file
            with rasterio.open(output_file, "w", **out_meta) as dest:
                dest.write(mosaic)

            # Close source files
            for src in src_files_to_mosaic:
                src.close()

            if output_file.exists():
                size_mb = output_file.stat().st_size / (1024 * 1024)
                print(f"✓ Downloaded: {output_file} ({size_mb:.2f} MB)")

                # Display info
                with rasterio.open(output_file) as src:
                    print(f"\nImage info:")
                    print(f"  Size: {src.width} × {src.height} pixels")
                    print(f"  Bands: {src.count} (RGB)")
                    print(f"  CRS: {src.crs}")
                    print(f"  Bounds: {src.bounds}")
                    print(f"  Resolution: ~{source_info['resolution']}m/pixel")

                return True
            else:
                print("✗ Merge failed - file not created")
                return False

    except Exception as e:
        print(f"✗ Download error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main function."""
    print("=" * 70)
    print("Google Earth Engine High-Resolution RGB Download")
    print("=" * 70)

    # Read active viewport
    try:
        viewport = get_active_viewport()
        BBOX = viewport['bounds_tuple']
        viewport_id = viewport['viewport_id']
    except Exception as e:
        print(f"ERROR: Failed to read viewport: {e}", file=sys.stderr)
        return

    # Use viewport-specific filename for proper caching across viewports
    output_file = DATA_DIR / "mosaics" / f"{viewport_id}_highres_rgb.tif"

    # Check cache for matching bounds
    cached_file = check_cache(BBOX, 'satellite')
    if cached_file:
        print(f"✓ Cache hit! Using existing satellite data: {cached_file}")
        return

    print(f"Viewport: {viewport_id}")

    # Initialize Earth Engine
    if not init_ee():
        return

    # Search for imagery
    source_info = search_high_res_imagery(BBOX)
    if not source_info:
        return

    # Download
    success = download_imagery(source_info, output_file)

    if success:
        print("\n" + "=" * 70)
        print("✅ Download complete!")
        print(f"\nNext steps:")
        print(f"  1. Regenerate pyramids: python create_pyramids.py")
        print(f"  2. Restart tile server: python tile_server.py")
        print(f"  3. View in browser: viewer.html")
    else:
        print("\n✗ Download failed")

if __name__ == "__main__":
    main()
