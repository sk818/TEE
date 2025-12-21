#!/usr/bin/env python3
"""
Create RGB image pyramids from GeoTIFF for tile-server based visualization.

Uses the blore project approach:
- Creates constant 4408×4408 output for all levels
- Each level: 2x2 averaging (Lanczos) then upscale back to 4408×4408
- This maintains visual quality and smooth transitions
- 6 zoom levels for smooth progression
"""

import logging
from pathlib import Path
from typing import Optional, Callable
import numpy as np
import rasterio
from rasterio.transform import Affine
from rasterio.enums import Resampling
from PIL import Image

logger = logging.getLogger(__name__)

# Constants - matching blore project approach
DEFAULT_NUM_LEVELS = 6  # 6 zoom levels for smooth transitions
CONSTANT_OUTPUT_SIZE = 4408  # All pyramid levels output at this size




def create_pyramid_level(input_file: Path, output_file: Path, level: int) -> dict:
    """
    Create a pyramid level using blore approach:
    - 2x2 averaging (Lanczos downsampling)
    - Upscale back to constant 4408×4408 output
    - This maintains visual quality and smooth zoom transitions

    Args:
        input_file: Source GeoTIFF (level 0 or previous level)
        output_file: Output level file
        level: Level number (1-5)

    Returns:
        Dictionary with metadata
    """
    with rasterio.open(input_file) as src:
        original_height = src.height
        original_width = src.width

        logger.info(f"  Creating level {level}: 2x2 averaging then upscale...")

        # Step 1: Downsample by 2x using Lanczos (2x2 averaging)
        intermediate_height = max(1, original_height // 2)
        intermediate_width = max(1, original_width // 2)

        downsampled_data = src.read(
            out_shape=(src.count, intermediate_height, intermediate_width),
            resampling=Resampling.lanczos
        )

        # Step 2: Upscale back to constant size using Lanczos
        upsampled_bands = []
        for i in range(downsampled_data.shape[0]):
            img = Image.fromarray(downsampled_data[i], mode='L')
            img_upsampled = img.resize(
                (CONSTANT_OUTPUT_SIZE, CONSTANT_OUTPUT_SIZE),
                Image.LANCZOS
            )
            upsampled_bands.append(np.array(img_upsampled))

        final_data = np.stack(upsampled_bands, axis=0)

        # Calculate new transform
        # Each pixel now represents a larger geographic area
        bounds = src.bounds
        transform = Affine(
            (bounds.right - bounds.left) / CONSTANT_OUTPUT_SIZE,
            0.0,
            bounds.left,
            0.0,
            -(bounds.top - bounds.bottom) / CONSTANT_OUTPUT_SIZE,
            bounds.top
        )

        # Write output
        output_file.parent.mkdir(parents=True, exist_ok=True)

        output_profile = src.profile.copy()
        output_profile.update({
            'height': CONSTANT_OUTPUT_SIZE,
            'width': CONSTANT_OUTPUT_SIZE,
            'transform': transform,
            'compress': 'lzw'
        })

        with rasterio.open(output_file, 'w', **output_profile) as dst:
            dst.write(final_data)

        file_size_kb = output_file.stat().st_size / 1024
        spatial_scale = 10 * (2 ** level)  # 20m, 40m, 80m, etc at each level
        logger.info(f"    Level {level}: {CONSTANT_OUTPUT_SIZE}×{CONSTANT_OUTPUT_SIZE} @ {spatial_scale}m/pixel ({file_size_kb:.1f} KB)")

        return {
            'success': True,
            'file': str(output_file),
            'width': CONSTANT_OUTPUT_SIZE,
            'height': CONSTANT_OUTPUT_SIZE,
            'bands': final_data.shape[0],
            'size_kb': file_size_kb
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
    Create RGB image pyramid using blore approach.

    Creates 6 zoom levels with:
    - Constant 4408×4408 output for all levels
    - 2x2 averaging (Lanczos) then upscale back to maintain quality
    - Smooth zoom transitions

    Supports caching: pyramids are only recreated if source RGB is newer.

    Args:
        rgb_file: Path to source RGB GeoTIFF
        output_dir: Directory to save pyramid levels (viewport-specific)
        source_resolution: Ground resolution of source (unused, for compatibility)
        num_levels: Number of pyramid levels (default 6)
        progress_callback: Optional callback(level, status, percent)
        check_cache: If True, reuse existing pyramids if source hasn't changed

    Returns:
        Dictionary with pyramid metadata
    """
    if not rgb_file.exists():
        raise FileNotFoundError(f"RGB file not found: {rgb_file}")

    if num_levels < 1 or num_levels > 6:
        raise ValueError("num_levels must be between 1 and 6")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Check if we can use cached pyramids
    metadata_file = output_dir / "pyramid_metadata.json"
    if check_cache and metadata_file.exists():
        try:
            import json
            with open(metadata_file, 'r') as f:
                cached_meta = json.load(f)

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

    logger.info(f"Creating RGB pyramids (blore approach)")
    logger.info(f"Source: {rgb_file}")
    logger.info(f"Output: {output_dir}")
    logger.info(f"Levels: {num_levels} (constant {CONSTANT_OUTPUT_SIZE}×{CONSTANT_OUTPUT_SIZE} output)")

    pyramid_info = {
        'source_file': str(rgb_file),
        'output_dir': str(output_dir),
        'method': 'blore',
        'description': 'Constant 4408×4408 output. Each level: 2x2 averaging then upscale.',
        'constant_output_size': CONSTANT_OUTPUT_SIZE,
        'created_at': str(Path.cwd()),
        'source_mtime': rgb_file.stat().st_mtime,
        'levels': {}
    }

    try:
        # Level 0: Copy source to output directory
        level_0_file = output_dir / "level_0.tif"

        if progress_callback:
            progress_callback(0, "Creating level 0...", 0)

        with rasterio.open(rgb_file) as src:
            profile = src.profile.copy()
            data = src.read()
            bounds = src.bounds

            # Ensure output is constant size - upscale if needed
            if src.height != CONSTANT_OUTPUT_SIZE or src.width != CONSTANT_OUTPUT_SIZE:
                logger.info(f"  Upscaling level 0 from {src.width}×{src.height} to {CONSTANT_OUTPUT_SIZE}×{CONSTANT_OUTPUT_SIZE}")
                upscaled_bands = []
                for i in range(data.shape[0]):
                    img = Image.fromarray(data[i], mode='L')
                    img_upscaled = img.resize((CONSTANT_OUTPUT_SIZE, CONSTANT_OUTPUT_SIZE), Image.LANCZOS)
                    upscaled_bands.append(np.array(img_upscaled))
                data = np.stack(upscaled_bands, axis=0)

            # Create transform for constant size
            transform = Affine(
                (bounds.right - bounds.left) / CONSTANT_OUTPUT_SIZE,
                0.0,
                bounds.left,
                0.0,
                -(bounds.top - bounds.bottom) / CONSTANT_OUTPUT_SIZE,
                bounds.top
            )

            profile.update({
                'height': CONSTANT_OUTPUT_SIZE,
                'width': CONSTANT_OUTPUT_SIZE,
                'transform': transform,
                'compress': 'lzw'
            })

            with rasterio.open(level_0_file, 'w', **profile) as dst:
                dst.write(data)

        size_kb = level_0_file.stat().st_size / 1024
        logger.info(f"  Level 0: {CONSTANT_OUTPUT_SIZE}×{CONSTANT_OUTPUT_SIZE} @ 10m/pixel ({size_kb:.1f} KB)")
        pyramid_info['levels'][0] = {
            'file': 'level_0.tif',
            'width': CONSTANT_OUTPUT_SIZE,
            'height': CONSTANT_OUTPUT_SIZE,
            'size_kb': size_kb
        }

        # Create downsampled levels
        prev_level_file = level_0_file
        for level in range(1, num_levels):
            percent = (level / num_levels) * 100
            if progress_callback:
                progress_callback(level, f"Creating level {level}...", percent)

            level_file = output_dir / f"level_{level}.tif"
            result = create_pyramid_level(prev_level_file, level_file, level)

            if not result['success']:
                raise Exception(f"Failed to create level {level}")

            pyramid_info['levels'][level] = {
                'file': f'level_{level}.tif',
                'width': result['width'],
                'height': result['height'],
                'size_kb': result['size_kb']
            }

            prev_level_file = level_file

        logger.info(f"\n✅ Pyramid creation complete! ({num_levels} levels)")

        # Save metadata for caching
        import json
        with open(metadata_file, 'w') as f:
            json.dump(pyramid_info, f, indent=2)
        logger.info(f"✓ Saved pyramid metadata")

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

    parser = argparse.ArgumentParser(description="Create RGB image pyramids (blore approach)")
    parser.add_argument("--input", type=str, required=True, help="Input RGB GeoTIFF file")
    parser.add_argument("--output-dir", type=str, required=True, help="Output directory for pyramid levels")
    parser.add_argument("--levels", type=int, default=6, help="Number of pyramid levels to create (1-6, default: 6)")

    args = parser.parse_args()

    result = create_rgb_pyramids(
        rgb_file=Path(args.input),
        output_dir=Path(args.output_dir),
        num_levels=args.levels
    )

    if result['success']:
        print("\n✅ Pyramid creation successful!")
        print(f"Created {args.levels} pyramid levels")
        print(f"Output: {args.output_dir}")
    else:
        print(f"\n❌ Error: {result['error']}")
        exit(1)
