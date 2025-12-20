#!/usr/bin/env python3
"""
Create RGB image pyramids from GeoTIFF for tile-server based visualization.

Builds a 5-level pyramid where:
- Level 0: 1m/pixel (finest, highest zoom)
- Level 1: ~3.16m/pixel
- Level 2: ~10m/pixel (source resolution)
- Level 3: ~31.6m/pixel
- Level 4: ~100m/pixel (coarsest, lowest zoom)

Each level zooms out by √10 ≈ 3.162 factor.
At highest zoom: 400×400 screen pixels = 40×40 embeddings = 400m×400m area.
"""

import logging
from pathlib import Path
from typing import Optional, Callable, Tuple
import numpy as np
import rasterio
from rasterio.transform import Affine
from rasterio.enums import Resampling
from PIL import Image

logger = logging.getLogger(__name__)

# Pyramid level factors: (level_num, zoom_factor_from_level_0)
# Level 0 is always the finest (1m/pixel base)
# Each subsequent level zooms out by √10 ≈ 3.162x
PYRAMID_FACTORS = [
    (0, 1.0),        # Level 0: 1m/pixel (base)
    (1, 3.162),      # Level 1: ~3.16m/pixel
    (2, 10.0),       # Level 2: ~10m/pixel
    (3, 31.62),      # Level 3: ~31.6m/pixel
    (4, 100.0),      # Level 4: ~100m/pixel
]

# Default number of levels if not specified
DEFAULT_NUM_LEVELS = 5


def calculate_new_shape(
    original_shape: Tuple[int, int],
    original_res: float,
    target_res: float
) -> Tuple[int, int]:
    """
    Calculate new shape when resampling from one resolution to another.

    Args:
        original_shape: (height, width) of original image
        original_res: Ground resolution in meters/pixel for original
        target_res: Ground resolution in meters/pixel for target

    Returns:
        (new_height, new_width)
    """
    height, width = original_shape

    # Scale factor: how many original pixels fit in one target pixel
    scale = target_res / original_res

    new_height = max(1, int(height / scale))
    new_width = max(1, int(width / scale))

    return (new_height, new_width)


def resample_geotiff(
    src_path: Path,
    dst_path: Path,
    new_resolution: float,
    source_resolution: float = 10.0,
    resampling_method=Resampling.bilinear
) -> dict:
    """
    Resample a GeoTIFF to a new ground resolution.

    Args:
        src_path: Source GeoTIFF path
        dst_path: Destination GeoTIFF path
        new_resolution: Target ground resolution in meters/pixel
        source_resolution: Source ground resolution in meters/pixel
        resampling_method: Resampling algorithm (bilinear, nearest, etc.)

    Returns:
        Dictionary with metadata
    """
    with rasterio.open(src_path) as src:
        # Calculate new dimensions
        old_height, old_width = src.height, src.width
        new_height, new_width = calculate_new_shape(
            (old_height, old_width),
            source_resolution,
            new_resolution
        )

        logger.info(f"Resampling from {old_width}×{old_height} to {new_width}×{new_height}")
        logger.info(f"  Source resolution: {source_resolution}m/pixel")
        logger.info(f"  Target resolution: {new_resolution}m/pixel")

        # Calculate new transform based on bounds and new dimensions
        # This properly handles cases where the source transform is broken/incomplete
        bounds = src.bounds
        old_transform = src.transform

        # Calculate pixel size in geographic coordinates (degrees)
        # Scale factor from old to new resolution
        scale_factor = new_resolution / source_resolution
        new_pixel_width_deg = (bounds.right - bounds.left) / new_width
        new_pixel_height_deg = (bounds.top - bounds.bottom) / new_height

        # Create corrected transform with proper geographic coordinates
        new_transform = Affine(
            new_pixel_width_deg,  # pixel width in degrees
            0.0,                   # no rotation
            bounds.left,           # upper left x
            0.0,                   # no rotation
            -new_pixel_height_deg, # pixel height in degrees (negative for top-down)
            bounds.top             # upper left y
        )

        logger.info(f"  New transform: {new_transform}")
        logger.info(f"  Pixel size: {new_pixel_width_deg:.10f}° × {new_pixel_height_deg:.10f}°")

        # Read source data
        data = src.read()
        logger.info(f"Read {src.count} bands, dtype={data.dtype}")

        # Resample each band
        resampled_data = []
        for band_idx, band_data in enumerate(data, 1):
            # Use PIL for resampling as it's fast and simple
            # Convert to PIL Image (H, W format)
            if band_data.dtype == np.uint8:
                img = Image.fromarray(band_data, mode='L')
            else:
                # Normalize to 0-255 for PIL
                if band_data.max() > band_data.min():
                    normalized = (
                        (band_data - band_data.min()) /
                        (band_data.max() - band_data.min()) * 255
                    ).astype(np.uint8)
                else:
                    normalized = np.zeros_like(band_data, dtype=np.uint8)
                img = Image.fromarray(normalized, mode='L')

            # Resize using bilinear interpolation
            resized_img = img.resize(
                (new_width, new_height),
                Image.LANCZOS if resampling_method == Resampling.bilinear else Image.NEAREST
            )

            # Convert back to numpy, restore original dtype
            resized_array = np.array(resized_img)
            if band_data.dtype != np.uint8:
                # Scale back to original range
                if band_data.max() > band_data.min():
                    resized_array = resized_array.astype(band_data.dtype) * (
                        band_data.max() - band_data.min()
                    ) / 255.0 + band_data.min()
                else:
                    resized_array = np.zeros((new_height, new_width), dtype=band_data.dtype)
            else:
                resized_array = resized_array.astype(np.uint8)

            resampled_data.append(resized_array)

        resampled_data = np.array(resampled_data)

        # Write output
        dst_path.parent.mkdir(parents=True, exist_ok=True)

        output_profile = src.profile.copy()
        output_profile.update({
            'height': new_height,
            'width': new_width,
            'transform': new_transform,
            'compress': 'lzw'
        })

        with rasterio.open(dst_path, 'w', **output_profile) as dst:
            dst.write(resampled_data)

        logger.info(f"Saved: {dst_path}")

        return {
            'success': True,
            'file': str(dst_path),
            'width': new_width,
            'height': new_height,
            'bands': resampled_data.shape[0],
            'resolution_m_per_pixel': new_resolution,
            'size_mb': dst_path.stat().st_size / (1024 * 1024)
        }


def create_rgb_pyramids(
    rgb_file: Path,
    output_dir: Path,
    source_resolution: float = 1.0,
    num_levels: int = DEFAULT_NUM_LEVELS,
    progress_callback: Optional[Callable] = None,
    check_cache: bool = True
) -> dict:
    """
    Create RGB image pyramid from a source GeoTIFF.

    The pyramid structure assumes:
    - Source RGB is at the finest resolution (e.g., 1m/pixel)
    - Level 0 is created at 1m/pixel
    - Each subsequent level zooms out by √10 ≈ 3.162x

    At highest zoom: 400×400 screen pixels = 40×40 embeddings = 400m×400m area.

    Supports caching: pyramids are only recreated if the source RGB file is newer
    than the cached pyramids.

    Args:
        rgb_file: Path to source RGB GeoTIFF
        output_dir: Directory to save pyramid levels (viewport-specific)
        source_resolution: Ground resolution of source in meters/pixel (default 1.0m)
        num_levels: Number of pyramid levels to create (1-5)
        progress_callback: Optional callback(level, status, percent)
        check_cache: If True, reuse existing pyramids if source file hasn't changed

    Returns:
        Dictionary with pyramid metadata
    """
    if not rgb_file.exists():
        raise FileNotFoundError(f"RGB file not found: {rgb_file}")

    if num_levels < 1 or num_levels > 5:
        raise ValueError("num_levels must be between 1 and 5")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Check if we can use cached pyramids
    metadata_file = output_dir / "pyramid_metadata.json"
    if check_cache and metadata_file.exists():
        try:
            import json
            with open(metadata_file, 'r') as f:
                cached_meta = json.load(f)

            # Get file modification times
            rgb_mtime = rgb_file.stat().st_mtime
            cached_mtime = cached_meta.get('source_mtime', 0)

            if rgb_mtime <= cached_mtime:
                logger.info(f"✓ Found cached pyramids for {rgb_file.name}")
                logger.info(f"  Source unchanged since: {cached_meta.get('created_at')}")
                if progress_callback:
                    progress_callback(0, "Using cached pyramids", 100)
                cached_meta['cached'] = True
                return {
                    'success': True,
                    'pyramid_info': cached_meta
                }
        except Exception as e:
            logger.warning(f"Error checking cache: {e}")

    logger.info(f"Creating RGB pyramids from {rgb_file}")
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"Source resolution: {source_resolution}m/pixel")
    logger.info(f"Number of levels: {num_levels}")

    pyramid_info = {
        'source_file': str(rgb_file),
        'source_resolution_m': source_resolution,
        'output_dir': str(output_dir),
        'description': 'Each level zooms out by √10 ≈ 3.162x. Level 0 = 1m/pixel (highest zoom)',
        'created_at': str(Path.cwd()),
        'source_mtime': rgb_file.stat().st_mtime,
        'levels': {}
    }

    try:
        # Create each level
        for level_idx in range(num_levels):
            level_num, factor = PYRAMID_FACTORS[level_idx]

            # Target resolution for this level
            target_resolution = source_resolution * factor

            percent = (level_idx / num_levels) * 100
            if progress_callback:
                progress_callback(level_num, f"Creating level {level_num} ({target_resolution:.2f}m/pixel)...", percent)

            logger.info(f"\n{'='*60}")
            logger.info(f"Level {level_num}: {target_resolution:.2f}m/pixel (factor: {factor}x)")
            logger.info(f"{'='*60}")

            # Output file for this level
            level_file = output_dir / f"level_{level_num}.tif"

            # Resample
            result = resample_geotiff(
                src_path=rgb_file,
                dst_path=level_file,
                new_resolution=target_resolution,
                source_resolution=source_resolution,
                resampling_method=Resampling.bilinear
            )

            if not result['success']:
                raise Exception(f"Failed to create level {level_num}")

            pyramid_info['levels'][level_num] = {
                'file': level_file.name,
                'resolution_m_per_pixel': target_resolution,
                'width': result['width'],
                'height': result['height'],
                'size_mb': result['size_mb']
            }

            logger.info(f"✓ Level {level_num} complete")

        logger.info(f"\n{'='*60}")
        logger.info(f"✅ Pyramid creation complete!")
        logger.info(f"{'='*60}")

        # Save metadata for caching
        import json
        with open(metadata_file, 'w') as f:
            json.dump(pyramid_info, f, indent=2)
        logger.info(f"✓ Saved pyramid metadata to {metadata_file}")

        if progress_callback:
            progress_callback(num_levels - 1, "Complete", 100)

        return {
            'success': True,
            'pyramid_info': pyramid_info
        }

    except Exception as e:
        logger.error(f"Error creating pyramids: {e}")
        import traceback
        traceback.print_exc()

        if progress_callback:
            progress_callback(0, f"Error: {str(e)}", 0)

        return {
            'success': False,
            'error': str(e)
        }


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Create RGB image pyramids")
    parser.add_argument("--input", type=str, required=True, help="Input RGB GeoTIFF file")
    parser.add_argument("--output-dir", type=str, required=True, help="Output directory for pyramid levels")
    parser.add_argument("--source-resolution", type=float, default=1.0, help="Source resolution in m/pixel (default: 1.0m)")
    parser.add_argument("--levels", type=int, default=5, help="Number of pyramid levels to create (1-5, default: 5)")

    args = parser.parse_args()

    result = create_rgb_pyramids(
        rgb_file=Path(args.input),
        output_dir=Path(args.output_dir),
        source_resolution=args.source_resolution,
        num_levels=args.levels
    )

    if result['success']:
        print("\n✅ Pyramid creation successful!")
        print(f"Pyramid info: {result['pyramid_info']}")
    else:
        print(f"\n❌ Error: {result['error']}")
        exit(1)
