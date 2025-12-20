#!/usr/bin/env python3
"""
Download TESSERA embeddings from viewport.txt and save as GeoTIFF.
"""

import logging
import re
from pathlib import Path
from typing import Tuple, Optional, Callable

import numpy as np
import rasterio
from rasterio.transform import Affine

try:
    import geotessera as gt
except ImportError:
    gt = None

# Configure logging
logger = logging.getLogger(__name__)


def parse_viewport_bounds() -> Tuple[float, float, float, float]:
    """
    Parse viewport.txt and extract bounds as (min_lon, min_lat, max_lon, max_lat).
    """
    viewport_file = Path(__file__).parent.parent.parent / "viewport.txt"

    try:
        with open(viewport_file, 'r') as f:
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

        return (min_lon, min_lat, max_lon, max_lat)

    except FileNotFoundError:
        raise FileNotFoundError(f"viewport.txt not found at {viewport_file.absolute()}")


def check_existing_file(output_file: Path, bbox: Tuple[float, float, float, float]) -> Optional[dict]:
    """
    Check if an existing GeoTIFF file matches the requested bounds.

    Args:
        output_file: Path to check
        bbox: Expected bounding box

    Returns:
        Metadata dict if file exists and matches bounds, None otherwise
    """
    if not output_file.exists():
        logger.info(f"No existing file at {output_file}")
        return None

    try:
        with rasterio.open(output_file) as src:
            # Check if bounds match (with generous tolerance for floating point)
            bounds = src.bounds
            # Use 0.001 degrees tolerance (~100 meters) to account for reprojection differences
            tolerance = 0.001

            min_lon, min_lat, max_lon, max_lat = bbox

            logger.info(f"Checking cached file bounds:")
            logger.info(f"  Requested: ({min_lon:.6f}, {min_lat:.6f}) → ({max_lon:.6f}, {max_lat:.6f})")
            logger.info(f"  Cached:    ({bounds.left:.6f}, {bounds.bottom:.6f}) → ({bounds.right:.6f}, {bounds.top:.6f})")

            lon_match = (abs(bounds.left - min_lon) < tolerance and
                        abs(bounds.right - max_lon) < tolerance)
            lat_match = (abs(bounds.bottom - min_lat) < tolerance and
                        abs(bounds.top - max_lat) < tolerance)

            if lon_match and lat_match:
                size_mb = output_file.stat().st_size / (1024 * 1024)
                logger.info(f"✓ Found matching existing file (bounds match within {tolerance}°): {output_file}")

                return {
                    'success': True,
                    'file': str(output_file),
                    'size_mb': size_mb,
                    'width': src.width,
                    'height': src.height,
                    'bands': src.count,
                    'crs': str(src.crs),
                    'cached': True
                }
            else:
                logger.info(f"✗ Bounds don't match (tolerance: {tolerance}°)")
                if not lon_match:
                    logger.info(f"    Longitude mismatch: {abs(bounds.left - min_lon):.6f}°, {abs(bounds.right - max_lon):.6f}°")
                if not lat_match:
                    logger.info(f"    Latitude mismatch: {abs(bounds.bottom - min_lat):.6f}°, {abs(bounds.top - max_lat):.6f}°")

    except Exception as e:
        logger.warning(f"Error checking existing file: {e}")
        import traceback
        traceback.print_exc()

    return None


def download_embeddings(
    year: int,
    output_file: Path,
    progress_callback: Optional[Callable] = None
) -> dict:
    """
    Download TESSERA embeddings for the viewport and save as GeoTIFF.

    Checks for existing file first - if bounds match, reuses the cached file.

    Args:
        year: Year to download
        output_file: Path to save GeoTIFF file
        progress_callback: Optional callback(status_message, percent)

    Returns:
        Dictionary with metadata about the download
    """
    if gt is None:
        raise RuntimeError("geotessera library not available")

    # Parse bounds from viewport.txt
    bbox = parse_viewport_bounds()
    min_lon, min_lat, max_lon, max_lat = bbox

    logger.info(f"Downloading TESSERA embeddings for year {year}")
    logger.info(f"Bounding box: {bbox}")
    logger.info(f"Region: ({min_lat:.6f}°N to {max_lat:.6f}°N, {min_lon:.6f}°E to {max_lon:.6f}°E)")

    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Check for existing file with matching bounds
    if progress_callback:
        progress_callback("Checking for existing embeddings...", 2)

    existing = check_existing_file(output_file, bbox)
    if existing is not None:
        logger.info(f"Reusing cached embeddings from {output_file}")
        if progress_callback:
            progress_callback(f"Using cached embeddings ({existing['size_mb']:.1f} MB)", 100)
        return existing

    try:
        # Update UI: Starting download
        if progress_callback:
            progress_callback(f"Initializing GeoTessera...", 5)

        # Initialize GeoTessera
        embeddings_dir = output_file.parent / "cache"
        embeddings_dir.mkdir(parents=True, exist_ok=True)
        tessera = gt.GeoTessera(embeddings_dir=str(embeddings_dir))

        logger.info("✓ GeoTessera initialized")

        # Update UI: Starting to fetch tiles
        if progress_callback:
            progress_callback(f"Year {year}: Downloading tiles from GeoTessera...", 15)

        logger.info(f"Fetching mosaic for region...")

        # Fetch mosaic for the region
        mosaic_array, mosaic_transform, crs = tessera.fetch_mosaic_for_region(
            bbox=bbox,
            year=year,
            target_crs='EPSG:4326',
            auto_download=True
        )

        height, width, bands = mosaic_array.shape
        logger.info(f"✓ Downloaded mosaic: {width}×{height} pixels, {bands} bands")
        logger.info(f"  CRS: {crs}")
        logger.info(f"  Original transform: {mosaic_transform}")

        # Fix broken transform from tessera if needed
        # Calculate correct transform from bounding box and dimensions
        min_lon, min_lat, max_lon, max_lat = bbox
        pixel_width = (max_lon - min_lon) / width
        pixel_height = (max_lat - min_lat) / height

        # Create proper Affine transform
        corrected_transform = Affine(
            pixel_width,   # pixel width in degrees
            0.0,           # no rotation
            min_lon,       # upper left x
            0.0,           # no rotation
            -pixel_height, # pixel height in degrees (negative for top-down)
            max_lat        # upper left y
        )

        logger.info(f"  Corrected transform: {corrected_transform}")
        logger.info(f"  Pixel size: {pixel_width:.10f}° × {pixel_height:.10f}°")

        # Use corrected transform instead of tessera's broken one
        final_transform = corrected_transform

        # Update UI: Downloaded, now saving
        if progress_callback:
            progress_callback(f"Year {year}: Saving to GeoTIFF ({width}×{height})...", 40)

        # Save as GeoTIFF with proper georeferencing
        logger.info(f"Saving to GeoTIFF: {output_file}")

        with rasterio.open(
            output_file,
            'w',
            driver='GTiff',
            height=height,
            width=width,
            count=bands,
            dtype=mosaic_array.dtype,
            crs=crs,
            transform=final_transform,
            compress='lzw'
        ) as dst:
            for band in range(bands):
                dst.write(mosaic_array[:, :, band], band + 1)

        size_mb = output_file.stat().st_size / (1024 * 1024)
        logger.info(f"✓ Saved: {output_file} ({size_mb:.2f} MB)")

        # Update UI: Complete
        if progress_callback:
            progress_callback(f"Year {year}: ✓ Complete ({size_mb:.1f} MB)", 100)

        return {
            'success': True,
            'file': str(output_file),
            'size_mb': size_mb,
            'width': width,
            'height': height,
            'bands': bands,
            'crs': str(crs),
            'bbox': bbox
        }

    except Exception as e:
        logger.error(f"Error downloading embeddings: {e}")
        import traceback
        traceback.print_exc()

        if progress_callback:
            progress_callback(f"Error: {str(e)}", 0)

        return {
            'success': False,
            'error': str(e),
            'bbox': bbox
        }


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Download TESSERA embeddings from viewport.txt")
    parser.add_argument("--year", type=int, default=2024, help="Year to download")
    parser.add_argument("--output", type=str, default="embeddings.tif", help="Output GeoTIFF file")

    args = parser.parse_args()

    result = download_embeddings(args.year, Path(args.output))

    if result['success']:
        print(f"\n✅ Download complete!")
        print(f"File: {result['file']}")
        print(f"Size: {result['size_mb']:.1f} MB")
        print(f"Dimensions: {result['width']}×{result['height']}")
        print(f"Bands: {result['bands']}")
    else:
        print(f"\n❌ Download failed: {result['error']}")
        exit(1)
