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

import numpy as np
import rasterio
from rasterio.enums import Resampling
from pathlib import Path
from PIL import Image

# Configuration
MOSAICS_DIR = Path("mosaics")
PCA_MOSAICS_DIR = Path("mosaics/pca")
PYRAMIDS_DIR = Path("pyramids")
PCA_PYRAMIDS_DIR = Path("pyramids/pca")
YEARS = range(2017, 2025)
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

        # Upscale by 3x for smoother appearance using high-quality Lanczos
        if upscale_factor > 1:
            print(f"  Upscaling by {upscale_factor}x for smoother rendering...")
            new_height = src.height * upscale_factor
            new_width = src.width * upscale_factor

            # Use PIL for high-quality Lanczos upscaling
            upscaled_bands = []
            for i in range(3):
                img = Image.fromarray(rgb_array[i], mode='L')
                img_upscaled = img.resize((new_width, new_height), Image.LANCZOS)
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


def create_pyramid_level(input_file, output_file, scale_factor, target_size=4408):
    """Create pyramid level - constant 4408×4408 output, with 2x2 averaging between levels."""
    with rasterio.open(input_file) as src:
        original_height = src.height
        original_width = src.width

        # Calculate intermediate downsampled dimensions
        intermediate_height = max(1, int(original_height / 2))
        intermediate_width = max(1, int(original_width / 2))

        # Step 1: Downsample by 2x using Lanczos (2x2 averaging)
        downsampled_data = src.read(
            out_shape=(src.count, intermediate_height, intermediate_width),
            resampling=Resampling.lanczos
        )

        # Step 2: Upsample back to target size (4408×4408) using Lanczos
        upsampled_bands = []
        for i in range(downsampled_data.shape[0]):
            img = Image.fromarray(downsampled_data[i], mode='L')
            img_upsampled = img.resize((target_size, target_size), Image.LANCZOS)
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
    print(f"    Level {scale_factor}: {target_size}×{target_size} @ {spatial_scale}m/pixel ({size_kb:.1f} KB)")


def upscale_image(source_file, output_file, upscale_factor=3):
    """Upscale an RGB image for smoother rendering."""
    print(f"  Upscaling {source_file.name} by {upscale_factor}x...")

    with rasterio.open(source_file) as src:
        data = src.read()

        new_height = src.height * upscale_factor
        new_width = src.width * upscale_factor

        # Upscale each band using PIL's Lanczos
        upscaled_bands = []
        for i in range(data.shape[0]):
            img = Image.fromarray(data[i], mode='L' if data.shape[0] == 1 else 'L')
            img_upscaled = img.resize((new_width, new_height), Image.LANCZOS)
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
    prev_level_file = level_0
    for level in range(1, NUM_ZOOM_LEVELS):
        level_file = output_dir / f"level_{level}.tif"
        create_pyramid_level(prev_level_file, level_file, level)
        prev_level_file = level_file

    print(f"  ✓ Created {NUM_ZOOM_LEVELS} zoom levels in {output_dir}")


def main():
    """Main function to create all pyramids."""
    print("=" * 70)
    print("Creating Image Pyramids for Tessera Embeddings and Satellite RGB")
    print("=" * 70)

    PYRAMIDS_DIR.mkdir(exist_ok=True)

    # Process Tessera embeddings (2017-2024)
    for year in YEARS:
        tessera_file = MOSAICS_DIR / f"bangalore_{year}.tif"

        if not tessera_file.exists():
            print(f"\n⚠️  Skipping {year}: File not found")
            continue

        # First, create RGB from first 3 bands (no upscaling - keep native 10m resolution)
        rgb_temp_file = PYRAMIDS_DIR / f"temp_rgb_{year}.tif"
        rgb_file = create_rgb_from_tessera(tessera_file, rgb_temp_file, upscale_factor=1)

        # Create pyramids from native resolution RGB
        year_dir = PYRAMIDS_DIR / str(year)
        create_pyramids_for_image(rgb_file, year_dir, f"Tessera {year}", upscale_factor=1)

        # Clean up temp file
        rgb_temp_file.unlink()

    # Process satellite RGB (no upscaling - keep native 10m resolution)
    satellite_file = MOSAICS_DIR / "satellite_rgb.tif"
    if satellite_file.exists():
        satellite_dir = PYRAMIDS_DIR / "satellite"
        create_pyramids_for_image(satellite_file, satellite_dir, "Satellite RGB", upscale_factor=1)
    else:
        print(f"\n⚠️  Satellite RGB file not found: {satellite_file}")

    # Process PCA embeddings (2017-2024)
    print("\n" + "=" * 70)
    print("Processing PCA Embeddings")
    print("=" * 70)

    PCA_PYRAMIDS_DIR.mkdir(exist_ok=True)

    for year in YEARS:
        pca_file = PCA_MOSAICS_DIR / f"bangalore_{year}_pca.tif"

        if not pca_file.exists():
            print(f"\n⚠️  Skipping PCA {year}: File not found")
            continue

        # Create pyramids from PCA RGB (already in RGB format)
        pca_year_dir = PCA_PYRAMIDS_DIR / str(year)
        create_pyramids_for_image(pca_file, pca_year_dir, f"PCA {year}", upscale_factor=1)

    print("\n" + "=" * 70)
    print("✅ Pyramid generation complete!")
    print(f"\nPyramids saved in:")
    print(f"  - Tessera: {PYRAMIDS_DIR.absolute()}")
    print(f"  - PCA: {PCA_PYRAMIDS_DIR.absolute()}")

    # Summary
    years_created = [d.name for d in PYRAMIDS_DIR.iterdir() if d.is_dir()]
    pca_years_created = [d.name for d in PCA_PYRAMIDS_DIR.iterdir() if d.is_dir()]
    print(f"\nCreated Tessera pyramids for: {', '.join(sorted(years_created))}")
    print(f"Created PCA pyramids for: {', '.join(sorted(pca_years_created))}")

    # Calculate total size
    total_size = sum(f.stat().st_size for f in PYRAMIDS_DIR.rglob("*.tif"))
    pca_total_size = sum(f.stat().st_size for f in PCA_PYRAMIDS_DIR.rglob("*.tif"))
    total_mb = total_size / (1024 * 1024)
    pca_total_mb = pca_total_size / (1024 * 1024)
    print(f"\nTessera pyramid size: {total_mb:.1f} MB")
    print(f"PCA pyramid size: {pca_total_mb:.1f} MB")
    print(f"Total: {(total_mb + pca_total_mb):.1f} MB")


if __name__ == "__main__":
    main()
