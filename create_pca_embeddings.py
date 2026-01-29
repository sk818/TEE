#!/usr/bin/env python3
"""
Create RGB visualization from Tessera embeddings.
Uses the first 3 bands directly (no PCA).
"""

import sys
import numpy as np
import rasterio
from pathlib import Path
# from tqdm import tqdm  # Disabled to reduce output

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).parent))

from lib.viewport_utils import get_active_viewport

# Configuration
DATA_DIR = Path.home() / "blore_data"
MOSAICS_DIR = DATA_DIR / "mosaics"
OUTPUT_DIR = DATA_DIR / "mosaics" / "pca"
YEARS = range(2024, 2025)  # 2024 only
N_COMPONENTS = 3  # RGB
CHUNK_SIZE = 1000  # Process in chunks to save memory

def compute_pca_for_year(year, viewport_id=None):
    """Create RGB visualization from first 3 embedding bands."""

    # Use viewport-specific filename
    if viewport_id:
        input_file = MOSAICS_DIR / f"{viewport_id}_embeddings_{year}.tif"
        output_file = OUTPUT_DIR / f"{viewport_id}_{year}_pca.tif"
    else:
        print(f"⚠️  Skipping PCA {year}: No viewport specified")
        return False

    if output_file.exists():
        print(f"✓ Skipping {year}: PCA file already exists")
        return True

    if not input_file.exists():
        print(f"⚠️  Skipping {year}: File not found")
        return False

    print(f"\n📊 Processing {year} embeddings...")

    with rasterio.open(input_file) as src:
        # Get dimensions
        n_bands = src.count
        height = src.height
        width = src.width

        print(f"  Input: {width}×{height} with {n_bands} bands")

        # Read first 3 bands directly (no PCA)
        print(f"  Reading first {N_COMPONENTS} bands as RGB...")
        if n_bands < N_COMPONENTS:
            print(f"  ⚠️  WARNING: Only {n_bands} bands available, need {N_COMPONENTS}")
            return False

        # Read first 3 bands
        rgb_bands = src.read(1, window=None)  # Will read band by band
        pca_image = np.zeros((N_COMPONENTS, height, width), dtype=np.float32)
        for i in range(N_COMPONENTS):
            pca_image[i] = src.read(i+1)  # Bands are 1-indexed

        print(f"  Using first {N_COMPONENTS} bands directly as RGB")

        # Normalize to 0-255 for RGB visualization
        print(f"  Normalizing to RGB (0-255)...")
        rgb_image = np.zeros_like(pca_image, dtype=np.uint8)

        for i in range(N_COMPONENTS):
            band = pca_image[i]
            valid_band = band[~np.isnan(band)]

            if len(valid_band) > 0:
                # Use percentile normalization (2nd to 98th percentile)
                p2, p98 = np.percentile(valid_band, [2, 98])

                # Clip and scale to 0-255
                band_clipped = np.clip(band, p2, p98)
                band_normalized = ((band_clipped - p2) / (p98 - p2) * 255).astype(np.uint8)
                rgb_image[i] = band_normalized

                print(f"    Band {i+1}: range [{p2:.2f}, {p98:.2f}] → [0, 255]")

        # Save RGB result
        print(f"  Saving to {output_file}...")
        OUTPUT_DIR.mkdir(exist_ok=True)

        profile = src.profile.copy()
        profile.update({
            'count': N_COMPONENTS,
            'dtype': 'uint8'
        })

        with rasterio.open(output_file, 'w', **profile) as dst:
            dst.write(rgb_image)

        # Print info
        print(f"\n  ✓ RGB visualization complete!")
        print(f"    Using first 3 embedding dimensions as RGB")

        size_mb = output_file.stat().st_size / (1024 * 1024)
        print(f"    Output: {output_file} ({size_mb:.1f} MB)")

        return True

def main():
    """Process all years."""
    print("=" * 70)
    print("Creating RGB visualizations from embedding first 3 bands")
    print("=" * 70)

    # Try to get active viewport, but continue if not available for backwards compatibility
    viewport_id = None
    try:
        viewport = get_active_viewport()
        viewport_id = viewport['viewport_id']
        print(f"Viewport: {viewport_id}")
    except Exception as e:
        print(f"Warning: Could not read active viewport: {e}")
        print("Processing any available mosaic files...")

    success_count = 0

    for year in YEARS:
        if compute_pca_for_year(year, viewport_id):
            success_count += 1

    print("\n" + "=" * 70)
    print(f"✅ Complete! Processed {success_count} years")
    print(f"\nPCA embeddings saved in: {OUTPUT_DIR.absolute()}")
    print("\nNext steps:")
    print("  1. Create pyramids: modify create_pyramids.py to include PCA mosaics")
    print("  2. Add PCA panel to viewer")

if __name__ == "__main__":
    main()
