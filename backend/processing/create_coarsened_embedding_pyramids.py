#!/usr/bin/env python3
"""
Create coarsened 128D embedding pyramids for zoom-aware similarity computation.

Creates 6 levels of spatially-averaged 128D embeddings using 2×2 pooling.
Each level is 1/2 the size of the previous level.

Level 0: Original resolution (4408×4408)
Level 1: 2×2 pooling (2204×2204)
Level 2: 4×4 pooling (1102×1102)
Level 3: 8×8 pooling (551×551)
Level 4: 16×16 pooling (275×275)
Level 5: 32×32 pooling (137×137)

This enables fast similarity computation at any zoom level:
- Level 0: ~19.4M pixels × 128D = 2.5B operations (~5 seconds)
- Level 5: ~18K pixels × 128D = 2.3M operations (~5ms)
"""

import logging
import sys
from pathlib import Path
from typing import Optional, Callable
import numpy as np
import json

# Configure logging
logger = logging.getLogger(__name__)

# Configuration
NUM_ZOOM_LEVELS = 6  # 6 pyramid levels (0-5)
EMBEDDING_DIMENSIONS = 128  # TESSERA embeddings are 128D
POOLING_SIZE = 2  # 2×2 pooling


def apply_2x2_pooling(embeddings: np.ndarray) -> np.ndarray:
    """
    Apply 2×2 average pooling to embeddings.

    Args:
        embeddings: Array of shape (height, width, dimensions) with float32 dtype

    Returns:
        Pooled array of shape (height//2, width//2, dimensions)
    """
    height, width, dims = embeddings.shape

    # Handle odd dimensions by truncating
    height_even = (height // 2) * 2
    width_even = (width // 2) * 2

    if height_even < height or width_even < width:
        embeddings = embeddings[:height_even, :width_even, :]
        height, width = height_even, width_even

    # Reshape to enable pooling
    # From (height, width, dims) to (height//2, 2, width//2, 2, dims)
    embeddings_reshaped = embeddings.reshape(
        height // 2, 2,
        width // 2, 2,
        dims
    )

    # Average over the 2×2 blocks
    pooled = embeddings_reshaped.mean(axis=(1, 3))

    return pooled.astype(np.float32)


def create_coarsened_pyramids(
    raw_embeddings_dir: Path,
    coarsened_dir: Path,
    years: list,
    progress_callback: Optional[Callable] = None
) -> dict:
    """
    Create coarsened embedding pyramids from raw embeddings.

    Args:
        raw_embeddings_dir: Directory containing embeddings_*.npy files (raw/embeddings_{year}.npy)
        coarsened_dir: Output directory for coarsened pyramids
        years: List of years to process
        progress_callback: Optional callback(year, level, status, percent)

    Returns:
        Dictionary with pyramid dimensions for each level
    """
    logger.info("Creating coarsened embedding pyramids")
    logger.info(f"Input directory: {raw_embeddings_dir}")
    logger.info(f"Output directory: {coarsened_dir}")

    coarsened_dir.mkdir(parents=True, exist_ok=True)

    pyramid_info = {
        'dimensions': EMBEDDING_DIMENSIONS,
        'pooling_size': POOLING_SIZE,
        'levels': {}
    }

    for year_idx, year in enumerate(years):
        embeddings_file = raw_embeddings_dir / f'embeddings_{year}.npy'

        if not embeddings_file.exists():
            logger.warning(f"Embeddings file not found: {embeddings_file}")
            continue

        logger.info(f"Processing year {year}...")

        try:
            # Load full embeddings
            embeddings = np.load(embeddings_file)
            logger.info(f"Loaded embeddings shape: {embeddings.shape}")

            height, width, dims = embeddings.shape

            # Create year directory
            year_dir = coarsened_dir / str(year)
            year_dir.mkdir(parents=True, exist_ok=True)

            # Level 0: Original (just copy)
            level_0_file = year_dir / "level_0.npy"
            np.save(level_0_file, embeddings)

            if year_idx == 0:
                pyramid_info['levels'][0] = {
                    'height': height,
                    'width': width,
                    'dimensions': dims,
                    'pixels': height * width,
                    'pooling_factor': 1
                }

            size_mb = embeddings.nbytes / (1024 * 1024)
            logger.info(f"Level 0: {width}×{height}×{dims} ({size_mb:.2f} MB)")

            # Create levels 1-5 with 2×2 pooling
            current_embeddings = embeddings.copy()

            for level in range(1, NUM_ZOOM_LEVELS):
                if progress_callback:
                    level_progress = (level / NUM_ZOOM_LEVELS) * 100
                    overall_progress = (year_idx / len(years)) * 100 + (level_progress / len(years))
                    progress_callback(year, level, 'pooling', overall_progress)

                # Apply 2×2 pooling
                current_embeddings = apply_2x2_pooling(current_embeddings)
                height_coarse, width_coarse, dims_coarse = current_embeddings.shape

                # Save coarsened level
                level_file = year_dir / f"level_{level}.npy"
                np.save(level_file, current_embeddings)

                if year_idx == 0:
                    pooling_factor = 2 ** level
                    pyramid_info['levels'][level] = {
                        'height': height_coarse,
                        'width': width_coarse,
                        'dimensions': dims_coarse,
                        'pixels': height_coarse * width_coarse,
                        'pooling_factor': pooling_factor
                    }

                size_mb = current_embeddings.nbytes / (1024 * 1024)
                logger.info(f"Level {level}: {width_coarse}×{height_coarse}×{dims_coarse} ({size_mb:.2f} MB)")

            # Save metadata for this year
            metadata_file = year_dir / "metadata.json"
            year_metadata = {
                'year': year,
                'original_height': height,
                'original_width': width,
                'embedding_dimensions': dims,
                'levels': NUM_ZOOM_LEVELS,
                'created': str(Path.cwd())
            }

            with open(metadata_file, 'w') as f:
                json.dump(year_metadata, f, indent=2)

            logger.info(f"✓ Created {NUM_ZOOM_LEVELS} levels for year {year}")

            if progress_callback:
                overall_progress = ((year_idx + 1) / len(years)) * 100
                progress_callback(year, NUM_ZOOM_LEVELS - 1, 'complete', overall_progress)

        except Exception as e:
            logger.error(f"Error processing year {year}: {e}")
            raise

    logger.info("✅ Coarsened pyramid creation complete!")
    logger.info(f"Pyramid info: {pyramid_info}")

    return pyramid_info


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    import argparse

    parser = argparse.ArgumentParser(description="Create coarsened embedding pyramids")
    parser.add_argument("--embeddings-dir", type=str, required=True, help="Directory with embeddings_*.npy files")
    parser.add_argument("--coarsened-dir", type=str, required=True, help="Output directory for coarsened pyramids")
    parser.add_argument("--years", type=str, default="2024", help="Years to process (e.g., 2024 or 2017-2024)")

    args = parser.parse_args()

    # Parse years
    if "-" in args.years:
        start, end = args.years.split("-")
        years_list = list(range(int(start), int(end) + 1))
    else:
        years_list = [int(y) for y in args.years.split(",")]

    embeddings_dir = Path(args.embeddings_dir)
    coarsened_dir = Path(args.coarsened_dir)

    try:
        create_coarsened_pyramids(
            raw_embeddings_dir=embeddings_dir,
            coarsened_dir=coarsened_dir,
            years=years_list
        )
        print(f"\n✅ Coarsened pyramid creation complete!")
        print(f"Pyramids saved to: {coarsened_dir}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
