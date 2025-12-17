#!/usr/bin/env python3
"""
Download Sentinel-2 RGB imagery using openEO API.

Uses ESA/Copernicus Data Space backend (no authentication required for basic queries).
This is an alternative to Planetary Computer that may be more reliable.
"""

import logging
from pathlib import Path
from typing import Tuple, Optional, Callable
import numpy as np
from tempfile import TemporaryDirectory

try:
    import openeo
    from openeo.processes import ProcessBuilderContext
except ImportError:
    logging.error("openEO library not installed")
    logging.error("Install with: pip install openeo")
    openeo = None

logger = logging.getLogger(__name__)

# Configuration
BACKEND_URL = "https://openeo.dataspace.copernicus.eu/openeo/1.1.0"
RESOLUTION = 10  # meters per pixel
CLOUD_THRESHOLD = 20  # Less than 20% cloud cover


def download_sentinel2_rgb_openeo(
    bounds: Tuple[float, float, float, float],
    year: int,
    output_file: Path,
    progress_callback: Optional[Callable] = None
) -> Path:
    """
    Download Sentinel-2 RGB imagery using openEO.

    Args:
        bounds: (min_lon, min_lat, max_lon, max_lat) in WGS84
        year: Year to download (e.g., 2024)
        output_file: Path to save GeoTIFF
        progress_callback: Optional callback(status, percent)

    Returns:
        Path to output GeoTIFF file
    """
    min_lon, min_lat, max_lon, max_lat = bounds
    output_file.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Downloading Sentinel-2 via openEO for year {year}")
    logger.info(f"Bounds: ({min_lon}, {min_lat}) to ({max_lon}, {max_lat})")
    logger.info(f"Backend: {BACKEND_URL}")

    try:
        if openeo is None:
            raise RuntimeError("openEO library not available")

        if progress_callback:
            progress_callback("connecting", 5)

        # Connect to Copernicus Data Space
        logger.info("Connecting to Copernicus Data Space via openEO...")
        connection = openeo.connect(BACKEND_URL)

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
            "SENTINEL2",
            spatial_extent=spatial_extent,
            temporal_extent=temporal_extent,
            bands=["B04", "B03", "B02"],  # Red, Green, Blue
            max_cloud_cover=CLOUD_THRESHOLD
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
        
        with TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir) / "temp.tif"
            s2_resampled.save_result(format="GeoTIFF", filename=str(temp_path))
            
            # Move to final location
            import shutil
            shutil.move(str(temp_path), str(output_file))

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


if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Download Sentinel-2 RGB imagery via openEO")
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

        result = download_sentinel2_rgb_openeo(
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
