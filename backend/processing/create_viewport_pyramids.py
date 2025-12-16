#!/usr/bin/env python3
"""
Create multi-resolution pyramid GeoTIFFs from TESSERA embeddings.

Based on blore project's create_pyramids.py, creates 6 zoom levels
using Lanczos resampling.
"""

import logging
import sys
from pathlib import Path
from typing import Tuple, Callable, Optional
import numpy as np
from PIL import Image

try:
    import rasterio
    from rasterio.transform import from_bounds
    from rasterio.enums import Resampling
except ImportError:
    logger = logging.getLogger(__name__)
    logger.error("rasterio library not installed")
    logger.error("Install with: pip install rasterio")
    rasterio = None

# Configure logging
logger = logging.getLogger(__name__)

# Configuration
NUM_ZOOM_LEVELS = 6  # 6 pyramid levels
TARGET_SIZE = 4408  # Target size for each pyramid level


def normalize_band(band: np.ndarray) -> np.ndarray:
    """Normalize a band to 0-255 using percentile-based normalization."""
    valid_data = band[~np.isnan(band)]

    if len(valid_data) == 0:
        return np.zeros_like(band, dtype=np.uint8)

    # Get 2nd and 98th percentiles to avoid outliers
    p2, p98 = np.percentile(valid_data, [2, 98])

    # Normalize to 0-255
    if p98 > p2:
        normalized = np.clip((band - p2) / (p98 - p2) * 255, 0, 255)
    else:
        normalized = np.clip(band * 255, 0, 255)

    return normalized.astype(np.uint8)


def create_pyramid_level(
    input_file: Path,
    output_file: Path,
    scale_factor: int,
    target_size: int = TARGET_SIZE
) -> None:
    """
    Create pyramid level using 2x downsampling + upsampling to target size.

    Args:
        input_file: Input GeoTIFF file
        output_file: Output GeoTIFF file
        scale_factor: Scale factor (power of 2)
        target_size: Target output size
    """
    if rasterio is None:
        raise RuntimeError("rasterio library not available")

    with rasterio.open(input_file) as src:
        original_height = src.height
        original_width = src.width

        # Calculate intermediate downsampled dimensions
        intermediate_height = max(1, int(original_height / 2))
        intermediate_width = max(1, int(original_width / 2))

        # Step 1: Downsample by 2x using Lanczos
        downsampled_data = src.read(
            out_shape=(src.count, intermediate_height, intermediate_width),
            resampling=Resampling.lanczos
        )

        # Step 2: Upsample back to target size using Lanczos via PIL
        upsampled_bands = []
        for i in range(downsampled_data.shape[0]):
            img = Image.fromarray(downsampled_data[i], mode='L')
            img_upsampled = img.resize((target_size, target_size), Image.LANCZOS)
            upsampled_bands.append(np.array(img_upsampled))

        final_data = np.stack(upsampled_bands, axis=0)

        # Update transform to reflect the effective resolution change
        transform = src.transform * src.transform.scale(
            (src.width / intermediate_width) * (intermediate_width / target_size),
            (src.height / intermediate_height) * (intermediate_height / target_size)
        )

        # Update profile
        profile = src.profile.copy()
        profile.update({
            'height': target_size,
            'width': target_size,
            'transform': transform,
            'compress': 'lzw',
            'tiled': True,
            'blockxsize': 256,
            'blockysize': 256
        })

        # Write image
        with rasterio.open(output_file, 'w', **profile) as dst:
            dst.write(final_data)

    size_kb = output_file.stat().st_size / 1024
    spatial_scale = 10 * (2 ** scale_factor)  # 10m base resolution
    logger.info(f"Level {scale_factor}: {target_size}×{target_size} @ {spatial_scale}m/pixel ({size_kb:.1f} KB)")


def create_rgb_from_embeddings(
    embeddings: np.ndarray,
    bounds: Tuple[float, float, float, float],
    output_file: Path
) -> Path:
    """Extract first 3 bands from embeddings and save as RGB GeoTIFF."""
    logger.info(f"Creating RGB from embeddings...")

    height, width, dims = embeddings.shape

    # Extract first 3 bands
    bands_rgb = [embeddings[:, :, i] for i in range(min(3, dims))]

    # Pad with zeros if less than 3 dimensions
    while len(bands_rgb) < 3:
        bands_rgb.append(np.zeros((height, width), dtype=np.float32))

    # Normalize each band
    rgb_array = np.stack([
        normalize_band(band)
        for band in bands_rgb
    ], axis=0)

    # Save as RGB GeoTIFF
    if rasterio is None:
        raise RuntimeError("rasterio library not available")

    min_lon, min_lat, max_lon, max_lat = bounds
    transform = from_bounds(min_lon, min_lat, max_lon, max_lat, width, height)

    profile = {
        'driver': 'GTiff',
        'height': height,
        'width': width,
        'count': 3,
        'dtype': 'uint8',
        'crs': 'EPSG:4326',
        'transform': transform,
        'compress': 'lzw'
    }

    with rasterio.open(output_file, 'w', **profile) as dst:
        dst.write(rgb_array)

    logger.info(f"Created RGB: {output_file} ({width}×{height})")
    return output_file


def create_pyramids_for_viewport(
    embeddings_dir: Path,
    pyramids_dir: Path,
    years: list,
    progress_callback: Optional[Callable] = None
) -> None:
    """
    Create multi-resolution pyramids from embeddings.

    Args:
        embeddings_dir: Directory with embeddings_*.npy files
        pyramids_dir: Base directory for output pyramids
        years: List of years to process
        progress_callback: Optional callback(year, level, status, percent)
    """
    if rasterio is None:
        raise RuntimeError("rasterio library not available")

    logger.info(f"Creating pyramids from embeddings")
    logger.info(f"Input directory: {embeddings_dir}")
    logger.info(f"Output directory: {pyramids_dir}")

    pyramids_dir.mkdir(parents=True, exist_ok=True)

    # Determine bounds from first embeddings file (you might want to pass this as parameter)
    # For now, we'll infer from the data
    bounds = (-180, -90, 180, 90)  # Default global bounds

    for year_idx, year in enumerate(years):
        embeddings_file = embeddings_dir / f'embeddings_{year}.npy'

        if not embeddings_file.exists():
            logger.warning(f"Embeddings file not found: {embeddings_file}")
            continue

        logger.info(f"Processing year {year}...")

        try:
            # Load embeddings
            embeddings = np.load(embeddings_file)
            logger.info(f"Loaded embeddings shape: {embeddings.shape}")

            year_dir = pyramids_dir / str(year)
            year_dir.mkdir(parents=True, exist_ok=True)

            # Create RGB from first 3 bands
            rgb_file = year_dir / "temp_rgb.tif"
            create_rgb_from_embeddings(embeddings, bounds, rgb_file)

            # Level 0: Native resolution
            level_0_file = year_dir / "level_0.tif"
            rgb_file.rename(level_0_file)

            size_kb = level_0_file.stat().st_size / 1024
            with rasterio.open(level_0_file) as src:
                logger.info(f"Level 0: {src.width}×{src.height} @ 10m/pixel ({size_kb:.1f} KB)")

            # Create pyramid levels 1-5
            prev_level_file = level_0_file
            for level in range(1, NUM_ZOOM_LEVELS):
                level_file = year_dir / f"level_{level}.tif"

                if progress_callback:
                    level_progress = (level / NUM_ZOOM_LEVELS) * 100
                    overall_progress = (year_idx / len(years)) * 100 + (level_progress / len(years))
                    progress_callback(year, level, 'creating', overall_progress)

                create_pyramid_level(prev_level_file, level_file, level)
                prev_level_file = level_file

            logger.info(f"✓ Created {NUM_ZOOM_LEVELS} levels for year {year}")

            if progress_callback:
                overall_progress = ((year_idx + 1) / len(years)) * 100
                progress_callback(year, NUM_ZOOM_LEVELS - 1, 'complete', overall_progress)

        except Exception as e:
            logger.error(f"Error processing year {year}: {e}")
            raise

    logger.info("✅ Pyramid creation complete!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Example usage
    import argparse

    parser = argparse.ArgumentParser(description="Create pyramid GeoTIFFs from embeddings")
    parser.add_argument("--embeddings-dir", type=str, required=True, help="Directory with embeddings_*.npy files")
    parser.add_argument("--pyramids-dir", type=str, required=True, help="Output directory for pyramids")
    parser.add_argument("--years", type=str, default="2017-2024", help="Years range (e.g., 2017-2024)")

    args = parser.parse_args()

    # Parse years
    if "-" in args.years:
        start, end = args.years.split("-")
        years_list = list(range(int(start), int(end) + 1))
    else:
        years_list = [int(y) for y in args.years.split(",")]

    embeddings_dir = Path(args.embeddings_dir)
    pyramids_dir = Path(args.pyramids_dir)

    try:
        create_pyramids_for_viewport(
            embeddings_dir=embeddings_dir,
            pyramids_dir=pyramids_dir,
            years=years_list
        )
        print(f"\n✅ Pyramid creation complete!")
        print(f"Pyramids saved to: {pyramids_dir}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
