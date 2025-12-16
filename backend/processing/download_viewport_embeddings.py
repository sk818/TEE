#!/usr/bin/env python3
"""
Download TESSERA embeddings for a specific viewport using geotessera.

Based on blore project's download_embeddings.py but adapted for
dynamic viewport processing.
"""

import logging
import sys
from pathlib import Path
from typing import Tuple, Callable, Optional
import numpy as np

# Configure logging
logger = logging.getLogger(__name__)

# Try importing geotessera
try:
    import geotessera as gt
except ImportError:
    logger.error("geotessera library not installed")
    logger.error("Install with: pip install geotessera")
    gt = None


def download_embeddings_for_viewport(
    bounds: Tuple[float, float, float, float],
    years: list,
    output_dir: Path,
    progress_callback: Optional[Callable] = None,
    auto_download: bool = True
) -> dict:
    """
    Download TESSERA embeddings for specified viewport bounds.

    Args:
        bounds: (min_lon, min_lat, max_lon, max_lat) in WGS84
        years: List of years to download
        output_dir: Directory to save raw embeddings
        progress_callback: Optional callback(year, status, percent)
        auto_download: Whether to auto-download tiles via geotessera

    Returns:
        Dictionary with metadata about downloaded embeddings
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    if gt is None:
        raise RuntimeError("geotessera library not available")

    metadata = {
        'bounds': bounds,
        'years': [],
        'files': {},
        'error': None
    }

    logger.info(f"Downloading TESSERA embeddings for bounds {bounds}")
    logger.info(f"Years: {min(years)}-{max(years)}")
    logger.info(f"Output directory: {output_dir}")

    try:
        # Initialize GeoTessera
        tessera = gt.GeoTessera(embeddings_dir=str(output_dir))

        for idx, year in enumerate(years):
            progress_percent = (idx / len(years)) * 100

            if progress_callback:
                progress_callback(year, 'downloading', progress_percent)

            logger.info(f"Downloading embeddings for year {year}...")

            try:
                # Fetch mosaic for the region (auto-downloads missing tiles)
                mosaic_array, mosaic_transform, crs = tessera.fetch_mosaic_for_region(
                    bbox=bounds,
                    year=year,
                    target_crs='EPSG:4326',
                    auto_download=auto_download
                )

                logger.info(f"Downloaded mosaic shape: {mosaic_array.shape}")

                # Save as numpy array
                output_file = output_dir / f'embeddings_{year}.npy'
                np.save(output_file, mosaic_array.astype(np.float32))

                metadata['years'].append(year)
                metadata['files'][year] = str(output_file)

                logger.info(f"Saved embeddings for year {year}: {output_file}")

                if progress_callback:
                    progress_callback(year, 'complete', ((idx + 1) / len(years)) * 100)

            except Exception as e:
                logger.error(f"Error downloading year {year}: {e}")
                metadata['error'] = f"Failed to download year {year}: {str(e)}"
                raise

    except Exception as e:
        logger.exception(f"Error in download_embeddings_for_viewport: {e}")
        metadata['error'] = str(e)
        raise

    logger.info(f"Download complete! Downloaded {len(metadata['years'])} years")
    return metadata


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Example usage
    import argparse

    parser = argparse.ArgumentParser(description="Download TESSERA embeddings for a viewport")
    parser.add_argument("--min-lon", type=float, required=True, help="Minimum longitude")
    parser.add_argument("--min-lat", type=float, required=True, help="Minimum latitude")
    parser.add_argument("--max-lon", type=float, required=True, help="Maximum longitude")
    parser.add_argument("--max-lat", type=float, required=True, help="Maximum latitude")
    parser.add_argument("--output-dir", type=str, default="embeddings", help="Output directory")
    parser.add_argument("--years", type=str, default="2017-2024", help="Years range (e.g., 2017-2024)")

    args = parser.parse_args()

    # Parse years
    if "-" in args.years:
        start, end = args.years.split("-")
        years_list = list(range(int(start), int(end) + 1))
    else:
        years_list = [int(y) for y in args.years.split(",")]

    bounds = (args.min_lon, args.min_lat, args.max_lon, args.max_lat)
    output_dir = Path(args.output_dir)

    try:
        metadata = download_embeddings_for_viewport(
            bounds=bounds,
            years=years_list,
            output_dir=output_dir
        )
        print(f"\n✅ Download complete!")
        print(f"Downloaded {len(metadata['years'])} years")
        print(f"Files saved to: {output_dir}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
