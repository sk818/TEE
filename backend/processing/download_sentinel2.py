#!/usr/bin/env python3
"""
Download Sentinel-2 RGB imagery for a specific viewport region.

Primary method: ESA openEO API (Copernicus Data Space)
Fallback method: Microsoft Planetary Computer API (no authentication required).
Downloads Red (B04), Green (B03), Blue (B02) bands and creates a median composite.
"""

import logging
from pathlib import Path
from typing import Tuple, Optional, Callable
import numpy as np

try:
    import openeo
except ImportError:
    openeo = None

try:
    import planetary_computer
    import pystac_client
    import rasterio
    from rasterio.merge import merge
    from rasterio.warp import reproject, Resampling
    from rasterio.transform import from_bounds
except ImportError:
    logger = logging.getLogger(__name__)
    logger.error("Required libraries not installed")
    logger.error("Install with: pip install planetary-computer pystac-client rasterio")

# Configure logging
logger = logging.getLogger(__name__)

# Configuration
PLANETARY_COMPUTER_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
SENTINEL2_COLLECTION = "sentinel-2-l2a"
CLOUD_COVER_THRESHOLD = 20  # Less than 20% cloud cover
RESOLUTION = 10  # meters per pixel
NUM_IMAGES = 10  # Max number of images to composite
OPENEO_BACKEND_URL = "https://openeo.dataspace.copernicus.eu/openeo/1.1.0"


def download_sentinel2_rgb_openeo(
    bounds: Tuple[float, float, float, float],
    year: int,
    output_file: Path,
    progress_callback: Optional[Callable] = None
) -> Path:
    """
    Download Sentinel-2 RGB imagery using ESA openEO API (Copernicus Data Space).

    Args:
        bounds: (min_lon, min_lat, max_lon, max_lat) in WGS84
        year: Year to download (e.g., 2024)
        output_file: Path to save GeoTIFF
        progress_callback: Optional callback(status, percent)

    Returns:
        Path to output GeoTIFF file
    """
    if openeo is None:
        raise RuntimeError("openEO library not available. Install with: pip install openeo")

    min_lon, min_lat, max_lon, max_lat = bounds
    output_file.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Downloading Sentinel-2 via openEO for year {year}")
    logger.info(f"Bounds: ({min_lon}, {min_lat}) to ({max_lon}, {max_lat})")
    logger.info(f"Backend: {OPENEO_BACKEND_URL}")

    try:
        if progress_callback:
            progress_callback("connecting", 5)

        # Connect to Copernicus Data Space
        logger.info("Connecting to Copernicus Data Space via openEO...")
        connection = openeo.connect(OPENEO_BACKEND_URL)

        if progress_callback:
            progress_callback("loading", 15)

        # Define the spatial and temporal extent
        spatial_extent = {
            "west": min_lon,
            "east": max_lon,
            "south": min_lat,
            "north": max_lat,
            "crs": "EPSG:4326"
        }

        temporal_extent = [f"{year}-01-01", f"{year}-12-31"]

        logger.info("Loading Sentinel-2 data...")

        # Load Sentinel-2 Level 2A data
        s2_data = connection.load_collection(
            "SENTINEL2_L2A",
            spatial_extent=spatial_extent,
            temporal_extent=temporal_extent,
            bands=["B04", "B03", "B02"],  # Red, Green, Blue
            max_cloud_cover=CLOUD_COVER_THRESHOLD
        )

        if progress_callback:
            progress_callback("processing", 30)

        # Apply median composite to reduce clouds
        logger.info("Creating median composite...")
        s2_composite = s2_data.median_time()

        # Scale to 0-255 (Sentinel-2 is 0-10000)
        s2_scaled = s2_composite / 10000 * 255

        # Resample to 10m resolution
        s2_resampled = s2_scaled.resample_spatial(resolution=RESOLUTION)

        if progress_callback:
            progress_callback("downloading", 50)

        # Save as GeoTIFF
        logger.info(f"Saving to {output_file}...")

        # Create the save result and download it
        save_result = s2_resampled.save_result(format="GTiff")

        if progress_callback:
            progress_callback("downloading", 70)

        # Download to output file
        save_result.download(outputfile=str(output_file))

        if progress_callback:
            progress_callback("complete", 100)

        logger.info(f"✓ Saved: {output_file}")
        size_mb = output_file.stat().st_size / (1024 * 1024)
        logger.info(f"File size: {size_mb:.2f} MB")

        return output_file

    except Exception as e:
        logger.error(f"Error downloading Sentinel-2 via openEO: {e}")
        if progress_callback:
            progress_callback("error", 0)
        raise


def download_sentinel2_rgb(
    bounds: Tuple[float, float, float, float],
    year: int,
    output_file: Path,
    progress_callback: Optional[Callable] = None
) -> Path:
    """
    Download Sentinel-2 RGB imagery and create median composite.

    Tries ESA openEO first (more reliable), falls back to Planetary Computer if needed.

    Args:
        bounds: (min_lon, min_lat, max_lon, max_lat)
        year: Year to download (e.g., 2024)
        output_file: Path to save GeoTIFF
        progress_callback: Optional callback(status, percent) for progress reporting

    Returns:
        Path to output GeoTIFF file
    """
    min_lon, min_lat, max_lon, max_lat = bounds

    logger.info(f"Downloading Sentinel-2 RGB for year {year}")
    logger.info(f"Bounds: ({min_lon}, {min_lat}) to ({max_lon}, {max_lat})")
    logger.info(f"Cloud cover threshold: {CLOUD_COVER_THRESHOLD}%")

    # Try openEO first (more reliable for global coverage)
    if openeo is not None:
        try:
            logger.info("Attempting download via ESA openEO (Copernicus Data Space)...")
            return download_sentinel2_rgb_openeo(
                bounds=bounds,
                year=year,
                output_file=output_file,
                progress_callback=progress_callback
            )
        except Exception as e:
            logger.warning(f"openEO download failed, will try Planetary Computer: {e}")
            if progress_callback:
                progress_callback("fallback", 10)
    else:
        logger.info("openEO not available, using Planetary Computer as primary method")

    # Fallback to Planetary Computer
    try:
        if progress_callback:
            progress_callback('connecting', 0)

        # Connect to Planetary Computer STAC API
        logger.info("Connecting to Microsoft Planetary Computer...")
        catalog = pystac_client.Client.open(
            PLANETARY_COMPUTER_URL,
            modifier=planetary_computer.sign_inplace,
        )

        if progress_callback:
            progress_callback('searching', 10)

        # Search for Sentinel-2 imagery
        logger.info(f"Searching for Sentinel-2 images in {year}...")
        search = catalog.search(
            collections=[SENTINEL2_COLLECTION],
            bbox=[min_lon, min_lat, max_lon, max_lat],
            datetime=f"{year}-01-01/{year}-12-31",
            query={"eo:cloud_cover": {"lt": CLOUD_COVER_THRESHOLD}}
        )

        items = list(search.items())
        logger.info(f"Found {len(items)} images with < {CLOUD_COVER_THRESHOLD}% cloud cover")

        if len(items) == 0:
            logger.warning("No images found for the specified criteria")
            if progress_callback:
                progress_callback('no_data', 100)
            raise RuntimeError(f"No Sentinel-2 imagery found for {year} with < {CLOUD_COVER_THRESHOLD}% cloud cover")

        # Limit to NUM_IMAGES clearest images
        items_to_process = items[:NUM_IMAGES]
        logger.info(f"Processing {len(items_to_process)} clearest images...")

        if progress_callback:
            progress_callback('loading', 20)

        # Collect band URLs
        red_bands = []
        green_bands = []
        blue_bands = []

        for idx, item in enumerate(items_to_process):
            signed_item = planetary_computer.sign(item)

            # Get band URLs
            red_url = signed_item.assets['B04'].href  # Red
            green_url = signed_item.assets['B03'].href  # Green
            blue_url = signed_item.assets['B02'].href  # Blue

            red_bands.append(red_url)
            green_bands.append(green_url)
            blue_bands.append(blue_url)

            logger.info(f"  Image {idx + 1}: {item.id}")

        if progress_callback:
            progress_callback('merging', 30)

        # Create temporary directory for processing
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            rgb_arrays = []
            transform_out = None
            profile = None

            # Process each color band
            for band_idx, (band_name, band_urls) in enumerate([
                ('red', red_bands),
                ('green', green_bands),
                ('blue', blue_bands)
            ]):
                logger.info(f"Processing {band_name} band...")

                if progress_callback:
                    progress_value = 30 + (band_idx / 3) * 30
                    progress_callback(f'processing_{band_name}', int(progress_value))

                # Read and merge all tiles for this band
                src_files_to_mosaic = []
                for url in band_urls:
                    try:
                        src = rasterio.open(url)
                        src_files_to_mosaic.append(src)
                    except Exception as e:
                        logger.warning(f"Failed to open band {band_name} from {url}: {e}")
                        continue

                if not src_files_to_mosaic:
                    logger.warning(f"No valid sources for {band_name} band")
                    continue

                # Merge tiles
                try:
                    mosaic_utm, transform_utm = merge(src_files_to_mosaic)
                    src_crs = src_files_to_mosaic[0].crs
                except Exception as e:
                    logger.error(f"Failed to merge {band_name} band: {e}")
                    for src in src_files_to_mosaic:
                        src.close()
                    raise

                # Close files
                for src in src_files_to_mosaic:
                    src.close()

                # Calculate transform for EPSG:4326
                # Resolution in degrees (~10m at equator ≈ 0.00009 degrees)
                res_degrees = RESOLUTION / 111000

                # Calculate output dimensions for target bounds in EPSG:4326
                width_4326 = int((max_lon - min_lon) / res_degrees)
                height_4326 = int((max_lat - min_lat) / res_degrees)

                # Calculate target transform for EPSG:4326
                transform_4326 = from_bounds(min_lon, min_lat, max_lon, max_lat, width_4326, height_4326)

                # Reproject from UTM to EPSG:4326
                mosaic_wgs84 = np.zeros((height_4326, width_4326), dtype=mosaic_utm.dtype)

                try:
                    reproject(
                        source=mosaic_utm[0] if mosaic_utm.ndim == 3 else mosaic_utm,
                        destination=mosaic_wgs84,
                        src_transform=transform_utm,
                        src_crs=src_crs,
                        dst_transform=transform_4326,
                        dst_crs='EPSG:4326',
                        resampling=Resampling.bilinear
                    )
                except Exception as e:
                    logger.error(f"Failed to reproject {band_name} band: {e}")
                    raise

                # Normalize to 0-255
                # Sentinel-2 typical range is 0-3000, clip and scale
                mosaic_normalized = np.clip(mosaic_wgs84 / 3000 * 255, 0, 255).astype(np.uint8)
                rgb_arrays.append(mosaic_normalized)

                if transform_out is None:
                    transform_out = transform_4326
                    profile = {
                        'driver': 'GTiff',
                        'crs': 'EPSG:4326',
                        'transform': transform_4326,
                        'width': width_4326,
                        'height': height_4326
                    }

            if progress_callback:
                progress_callback('stacking', 70)

            # Stack RGB and save
            if len(rgb_arrays) != 3:
                logger.error(f"Expected 3 bands, got {len(rgb_arrays)}")
                raise RuntimeError(f"Failed to extract RGB bands")

            rgb_stack = np.stack(rgb_arrays, axis=0)
            logger.info(f"RGB stack shape: {rgb_stack.shape}")

            # Update profile for output
            profile.update({
                'driver': 'GTiff',
                'height': rgb_stack.shape[1],
                'width': rgb_stack.shape[2],
                'count': 3,
                'dtype': 'uint8',
                'transform': transform_out,
                'compress': 'lzw',
                'tiled': True,
                'blockxsize': 256,
                'blockysize': 256
            })

            # Save GeoTIFF
            if progress_callback:
                progress_callback('saving', 85)

            output_file.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"Saving Sentinel-2 RGB to {output_file}...")

            with rasterio.open(output_file, 'w', **profile) as dst:
                dst.write(rgb_stack)

            logger.info(f"✓ Saved: {output_file}")

            # Verify output
            size_mb = output_file.stat().st_size / (1024 * 1024)
            with rasterio.open(output_file) as src:
                logger.info(f"Image info:")
                logger.info(f"  Size: {src.width} × {src.height} pixels")
                logger.info(f"  Bands: {src.count} (RGB)")
                logger.info(f"  CRS: {src.crs}")
                logger.info(f"  Bounds: {src.bounds}")
                logger.info(f"  File size: {size_mb:.2f} MB")

            if progress_callback:
                progress_callback('complete', 100)

            logger.info("✅ Sentinel-2 download complete!")
            return output_file

    except Exception as e:
        logger.error(f"Error downloading Sentinel-2 data: {e}")
        if progress_callback:
            progress_callback('error', 0)
        raise


if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Download Sentinel-2 RGB imagery")
    parser.add_argument("--bounds", type=str, required=True, help="Bounds as min_lon,min_lat,max_lon,max_lat")
    parser.add_argument("--year", type=int, required=True, help="Year to download")
    parser.add_argument("--output", type=str, required=True, help="Output GeoTIFF path")

    args = parser.parse_args()

    try:
        bounds = tuple(map(float, args.bounds.split(",")))
        if len(bounds) != 4:
            raise ValueError("Bounds must have 4 values: min_lon,min_lat,max_lon,max_lat")

        output_path = Path(args.output)

        def progress_callback(status, percent):
            print(f"[{percent}%] {status}")

        result = download_sentinel2_rgb(
            bounds=bounds,
            year=args.year,
            output_file=output_path,
            progress_callback=progress_callback
        )

        print(f"\n✅ Downloaded to: {result}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
