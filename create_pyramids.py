#!/usr/bin/env python3
"""
Create image pyramids (12 zoom levels) for Tessera embeddings and satellite RGB.

For Tessera: Extract first 3 bands as RGB, then create pyramids
For Satellite RGB: Create pyramids from existing RGB image

Uses Lanczos resampling for high-quality downsampling to reduce blockiness.

Output structure:
pyramids/
  ├── 2017/
  │   ├── level_0.tif  (full resolution)
  │   ├── level_1.tif  (1/2 resolution)
  │   ├── ...
  │   └── level_11.tif  (1/2048 resolution)
  ├── 2018/
  ├── ...
  ├── 2024/
  └── satellite/
"""

import sys
import numpy as np
import rasterio
from rasterio.enums import Resampling
from pathlib import Path
from PIL import Image

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).parent))
from lib.progress_tracker import ProgressTracker

# Configuration
DATA_DIR = Path.home() / "blore_data"
MOSAICS_DIR = DATA_DIR / "mosaics"
PCA_MOSAICS_DIR = DATA_DIR / "mosaics" / "pca"
PYRAMIDS_BASE_DIR = DATA_DIR / "pyramids"
YEARS = range(2024, 2025)  # 2024 only
NUM_ZOOM_LEVELS = 6  # 6 useful zoom levels (skip the very zoomed-out tiny levels)


def create_rgb_from_tessera(input_file, output_file, upscale_factor=3):
    """Extract first 3 bands from Tessera embedding, upscale for smoothness, and save as RGB."""
    print(f"  Extracting RGB from {input_file.name}...")

    with rasterio.open(input_file) as src:
        # Read first 3 bands
        band1 = src.read(1)
        band2 = src.read(2)
        band3 = src.read(3)

        # Normalize to 0-255 (assuming embeddings are roughly -1 to 1 or 0 to 1)
        # We'll use percentile-based normalization for robustness
        def normalize_band(band):
            # Get 2nd and 98th percentiles to avoid outliers
            p2, p98 = np.percentile(band[~np.isnan(band)], [2, 98])
            # Normalize to 0-255
            normalized = np.clip((band - p2) / (p98 - p2) * 255, 0, 255)
            return normalized.astype(np.uint8)

        rgb_array = np.stack([
            normalize_band(band1),
            normalize_band(band2),
            normalize_band(band3)
        ], axis=0)

        # Upscale by 3x for crisp pixel boundaries (nearest-neighbor preserves embedding boundaries)
        if upscale_factor > 1:
            print(f"  Upscaling by {upscale_factor}x with nearest-neighbor for crisp boundaries...")
            new_height = src.height * upscale_factor
            new_width = src.width * upscale_factor

            # Use PIL nearest-neighbor upscaling to preserve crisp pixel boundaries
            upscaled_bands = []
            for i in range(3):
                img = Image.fromarray(rgb_array[i], mode='L')
                img_upscaled = img.resize((new_width, new_height), Image.NEAREST)
                upscaled_bands.append(np.array(img_upscaled))

            rgb_array = np.stack(upscaled_bands, axis=0)

            # Update transform for new resolution
            transform = src.transform * src.transform.scale(
                1.0 / upscale_factor,
                1.0 / upscale_factor
            )
        else:
            transform = src.transform

        # Save as RGB GeoTIFF
        profile = src.profile.copy()
        profile.update({
            'count': 3,
            'dtype': 'uint8',
            'compress': 'lzw',
            'height': rgb_array.shape[1],
            'width': rgb_array.shape[2],
            'transform': transform
        })

        with rasterio.open(output_file, 'w', **profile) as dst:
            dst.write(rgb_array)

    print(f"  ✓ Created RGB: {output_file} ({rgb_array.shape[2]}×{rgb_array.shape[1]})")
    return output_file


def create_pyramid_level(input_file, output_file, scale_factor, target_size=4408, use_nearest=False):
    """Create pyramid level - constant 4408×4408 output, with 2x2 averaging between levels.

    Args:
        use_nearest: If True, use nearest-neighbor resampling (crisp boundaries).
                     If False, use Lanczos (smooth). Top 3 levels use nearest-neighbor
                     for crisp 10m embedding boundaries.
    """
    resampling_method = Resampling.nearest if use_nearest else Resampling.lanczos
    resize_filter = Image.NEAREST if use_nearest else Image.LANCZOS

    with rasterio.open(input_file) as src:
        original_height = src.height
        original_width = src.width

        # Calculate intermediate downsampled dimensions
        intermediate_height = max(1, int(original_height / 2))
        intermediate_width = max(1, int(original_width / 2))

        # Step 1: Downsample by 2x using specified resampling method
        downsampled_data = src.read(
            out_shape=(src.count, intermediate_height, intermediate_width),
            resampling=resampling_method
        )

        # Step 2: Upsample back to target size (4408×4408) using specified filter
        upsampled_bands = []
        for i in range(downsampled_data.shape[0]):
            img = Image.fromarray(downsampled_data[i], mode='L')
            img_upsampled = img.resize((target_size, target_size), resize_filter)
            upsampled_bands.append(np.array(img_upsampled))

        final_data = np.stack(upsampled_bands, axis=0)

        # Update transform to reflect the effective resolution change
        # Even though output is 4408×4408, each pixel represents a larger area
        transform = src.transform * src.transform.scale(
            (src.width / intermediate_width) * (intermediate_width / target_size),
            (src.height / intermediate_height) * (intermediate_height / target_size)
        )

        # Update profile
        profile = src.profile.copy()
        profile.update({
            'height': target_size,
            'width': target_size,
            'transform': transform
        })

        # Write image
        with rasterio.open(output_file, 'w', **profile) as dst:
            dst.write(final_data)

    size_kb = output_file.stat().st_size / 1024
    spatial_scale = 10 * (2 ** scale_factor)  # 20m, 40m, 80m, etc.
    resampling_label = "nearest" if use_nearest else "lanczos"
    print(f"    Level {scale_factor}: {target_size}×{target_size} @ {spatial_scale}m/pixel [{resampling_label}] ({size_kb:.1f} KB)")


def upscale_image(source_file, output_file, upscale_factor=3):
    """Upscale an RGB image with nearest-neighbor for crisp pixel boundaries."""
    print(f"  Upscaling {source_file.name} by {upscale_factor}x with nearest-neighbor...")

    with rasterio.open(source_file) as src:
        data = src.read()

        new_height = src.height * upscale_factor
        new_width = src.width * upscale_factor

        # Upscale each band using PIL's nearest-neighbor for crisp boundaries
        upscaled_bands = []
        for i in range(data.shape[0]):
            img = Image.fromarray(data[i], mode='L' if data.shape[0] == 1 else 'L')
            img_upscaled = img.resize((new_width, new_height), Image.NEAREST)
            upscaled_bands.append(np.array(img_upscaled))

        upscaled_data = np.stack(upscaled_bands, axis=0)

        # Update transform
        transform = src.transform * src.transform.scale(
            1.0 / upscale_factor,
            1.0 / upscale_factor
        )

        # Update profile
        profile = src.profile.copy()
        profile.update({
            'height': new_height,
            'width': new_width,
            'transform': transform
        })

        with rasterio.open(output_file, 'w', **profile) as dst:
            dst.write(upscaled_data)

    print(f"  ✓ Upscaled to {new_width}×{new_height}")
    return output_file


def create_pyramids_for_image(source_file, output_dir, name, upscale_factor=1):
    """Create all pyramid levels for a single image - constant 4408×4408 output."""
    print(f"\n📸 Creating pyramids for {name}...")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Level 0: Native resolution (should already be 4408×4408)
    level_0 = output_dir / "level_0.tif"

    with rasterio.open(source_file) as src:
        profile = src.profile.copy()
        data = src.read()
        with rasterio.open(level_0, 'w', **profile) as dst:
            dst.write(data)

    size_kb = level_0.stat().st_size / 1024
    with rasterio.open(level_0) as src:
        print(f"    Level 0: {src.width}×{src.height} @ 10m/pixel ({size_kb:.1f} KB)")

    # Create downsampled levels with constant 4408×4408 output
    # Each level averages 2x2 pixels from previous level, then upsamples to 4408×4408
    # Use nearest-neighbor for top 3 levels (0-2) to preserve crisp 10m embedding boundaries
    # Use Lanczos for coarser levels (3+) for smoother appearance at lower zoom
    prev_level_file = level_0
    for level in range(1, NUM_ZOOM_LEVELS):
        level_file = output_dir / f"level_{level}.tif"
        use_nearest = (level <= 2)  # Levels 1-2 use nearest-neighbor (top 3 with level_0)
        create_pyramid_level(prev_level_file, level_file, level, use_nearest=use_nearest)
        prev_level_file = level_file

    print(f"  ✓ Created {NUM_ZOOM_LEVELS} zoom levels in {output_dir}")


def main():
    """Main function to create all pyramids."""
    # Import here to avoid issues if viewport file doesn't exist
    try:
        from lib.viewport_utils import get_active_viewport
        viewport = get_active_viewport()
        viewport_id = viewport['viewport_id']
    except Exception as e:
        print(f"Warning: Could not read active viewport: {e}")
        print("Processing any available mosaic files...")
        viewport_id = None

    # Initialize progress tracker
    progress = ProgressTracker(f"{viewport_id}_pyramids" if viewport_id else "pyramids")
    progress.update("starting", "Initializing pyramid creation...")

    print("=" * 70)
    print("Creating Image Pyramids for Tessera Embeddings and Satellite RGB")
    print("=" * 70)
    if viewport_id:
        print(f"Viewport: {viewport_id}")

    PYRAMIDS_BASE_DIR.mkdir(exist_ok=True)

    # Process Tessera embeddings (2017-2024)
    for year in YEARS:
        # First try viewport-specific filename
        if viewport_id:
            tessera_file = MOSAICS_DIR / f"{viewport_id}_embeddings_{year}.tif"
        else:
            tessera_file = None

        # Fallback to old Bangalore filename for compatibility
        if not tessera_file or not tessera_file.exists():
            tessera_file = MOSAICS_DIR / f"bangalore_{year}.tif"

        if not tessera_file.exists():
            print(f"\n⚠️  Skipping {year}: File not found")
            progress.update("processing", f"Skipped {year}: file not found", current_file=f"embeddings_{year}")
            continue

        print(f"\nProcessing {tessera_file.name}...")
        progress.update("processing", f"Creating pyramids for {year}...", current_file=f"embeddings_{year}")

        # First, create RGB from first 3 bands (upscale 3x for maximum resolution when zoomed in)
        rgb_temp_file = PYRAMIDS_BASE_DIR / f"temp_rgb_{year}.tif"
        rgb_file = create_rgb_from_tessera(tessera_file, rgb_temp_file, upscale_factor=3)

        # Create viewport-specific pyramid directory
        if viewport_id:
            viewport_pyramids_dir = PYRAMIDS_BASE_DIR / viewport_id
        else:
            # Fallback for backward compatibility if viewport can't be determined
            viewport_pyramids_dir = PYRAMIDS_BASE_DIR / "rethymno"

        viewport_pyramids_dir.mkdir(parents=True, exist_ok=True)

        # Create pyramids from native resolution RGB
        year_dir = viewport_pyramids_dir / str(year)
        create_pyramids_for_image(rgb_file, year_dir, f"Tessera {year}", upscale_factor=1)
        progress.update("processing", f"Created pyramid levels for {year}", current_file=f"embeddings_{year}", current_value=year-2023)

        # Clean up temp file
        rgb_temp_file.unlink()

    # Process satellite RGB (upscale 3x to match Tessera resolution for consistency)
    if viewport_id:
        satellite_file = MOSAICS_DIR / f"{viewport_id}_satellite_rgb.tif"
    else:
        satellite_file = None

    # Fallback to old Bangalore filename for compatibility
    if not satellite_file or not satellite_file.exists():
        satellite_file = MOSAICS_DIR / "bangalore_satellite_rgb.tif"

    if satellite_file.exists():
        satellite_upscaled_file = PYRAMIDS_BASE_DIR / "temp_satellite_upscaled.tif"
        upscale_image(satellite_file, satellite_upscaled_file, upscale_factor=3)

        # Create viewport-specific satellite directory
        if viewport_id:
            viewport_pyramids_dir = PYRAMIDS_BASE_DIR / viewport_id
        else:
            # Fallback for backward compatibility if viewport can't be determined
            viewport_pyramids_dir = PYRAMIDS_BASE_DIR / "rethymno"

        viewport_pyramids_dir.mkdir(parents=True, exist_ok=True)
        satellite_dir = viewport_pyramids_dir / "satellite"
        create_pyramids_for_image(satellite_upscaled_file, satellite_dir, "Satellite RGB", upscale_factor=1)
        satellite_upscaled_file.unlink()
    else:
        print(f"\n⚠️  Satellite RGB file not found: {satellite_file}")

    # Process PCA embeddings (2017-2024)
    print("\n" + "=" * 70)
    print("Processing PCA Embeddings")
    print("=" * 70)

    for year in YEARS:
        pca_file = PCA_MOSAICS_DIR / f"bangalore_{year}_pca.tif"

        if not pca_file.exists():
            print(f"\n⚠️  Skipping PCA {year}: File not found")
            continue

        # Create viewport-specific PCA directory
        if viewport_id:
            viewport_pyramids_dir = PYRAMIDS_BASE_DIR / viewport_id
        else:
            # Fallback for backward compatibility if viewport can't be determined
            viewport_pyramids_dir = PYRAMIDS_BASE_DIR / "rethymno"

        pca_pyramids_dir = viewport_pyramids_dir / "pca"
        pca_pyramids_dir.mkdir(parents=True, exist_ok=True)

        # Upscale PCA RGB for better resolution
        pca_upscaled_file = pca_pyramids_dir / f"bangalore_{year}_pca_upscaled.tif"
        upscale_image(pca_file, pca_upscaled_file, upscale_factor=3)

        # Create pyramids from upscaled PCA RGB
        pca_year_dir = pca_pyramids_dir / str(year)
        create_pyramids_for_image(pca_upscaled_file, pca_year_dir, f"PCA {year}", upscale_factor=1)

        # Clean up upscaled temp file
        pca_upscaled_file.unlink()

    print("\n" + "=" * 70)
    print("✅ Pyramid generation complete!")
    print(f"\nPyramids saved in:")

    # Calculate total size and summarize by viewport
    if viewport_id:
        viewport_pyramids_dir = PYRAMIDS_BASE_DIR / viewport_id
    else:
        viewport_pyramids_dir = PYRAMIDS_BASE_DIR / "rethymno"

    if viewport_pyramids_dir.exists():
        print(f"  - {viewport_pyramids_dir.absolute()}")

        # Summary of years created for this viewport
        years_created = [d.name for d in (viewport_pyramids_dir).iterdir() if d.is_dir() and d.name not in ['satellite', 'pca']]
        print(f"\nCreated Tessera pyramids for: {', '.join(sorted(years_created))}")

        # Check for PCA
        pca_dir = viewport_pyramids_dir / "pca"
        if pca_dir.exists():
            pca_years_created = [d.name for d in pca_dir.iterdir() if d.is_dir()]
            print(f"Created PCA pyramids for: {', '.join(sorted(pca_years_created))}")

        # Calculate total size
        total_size = sum(f.stat().st_size for f in viewport_pyramids_dir.rglob("*.tif"))
        total_mb = total_size / (1024 * 1024)
        print(f"\nViewport pyramid size: {total_mb:.1f} MB")

        # Update progress to complete
        progress.complete(f"Created pyramids: {total_mb:.1f} MB for {viewport_id or 'rethymno'}")
    else:
        print(f"  - {viewport_pyramids_dir.absolute()} (not created)")
        progress.complete("Pyramid generation complete (no viewports found)")


if __name__ == "__main__":
    main()
