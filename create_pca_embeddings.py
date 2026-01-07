#!/usr/bin/env python3
"""
Create PCA-projected embeddings from Tessera embeddings.
Reduces 128 dimensions to 3 for RGB visualization.
"""

import numpy as np
import rasterio
from sklearn.decomposition import IncrementalPCA
from pathlib import Path
# from tqdm import tqdm  # Disabled to reduce output

# Configuration
MOSAICS_DIR = Path("mosaics")
OUTPUT_DIR = Path("mosaics/pca")
YEARS = range(2024, 2025)  # 2024 only
N_COMPONENTS = 3  # RGB
CHUNK_SIZE = 1000  # Process in chunks to save memory

def compute_pca_for_year(year):
    """Compute PCA projection for a single year's embeddings."""

    input_file = MOSAICS_DIR / f"bangalore_{year}.tif"
    output_file = OUTPUT_DIR / f"bangalore_{year}_pca.tif"

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

        # Read all data (reshape to [pixels, bands])
        print(f"  Reading embeddings...")
        data = src.read()  # Shape: (bands, height, width)
        data_reshaped = data.reshape(n_bands, -1).T  # Shape: (pixels, bands)

        # Remove NaN/invalid values
        valid_mask = ~np.isnan(data_reshaped).any(axis=1)
        valid_data = data_reshaped[valid_mask]

        print(f"  Valid pixels: {valid_data.shape[0]:,} / {data_reshaped.shape[0]:,}")

        # Compute PCA
        print(f"  Computing PCA ({n_bands} → {N_COMPONENTS} dimensions)...")
        pca = IncrementalPCA(n_components=N_COMPONENTS)

        # Fit PCA in chunks
        for i in range(0, len(valid_data), CHUNK_SIZE):
            chunk = valid_data[i:i+CHUNK_SIZE]
            pca.partial_fit(chunk)

        # Transform all data
        print(f"  Transforming data...")
        pca_result = np.full((data_reshaped.shape[0], N_COMPONENTS), np.nan)

        for i in range(0, len(valid_data), CHUNK_SIZE):
            chunk_indices = np.where(valid_mask)[0][i:i+CHUNK_SIZE]
            chunk = valid_data[i:i+CHUNK_SIZE]
            pca_result[chunk_indices] = pca.transform(chunk)

        # Reshape back to image
        pca_image = pca_result.T.reshape(N_COMPONENTS, height, width)

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

                print(f"    PC{i+1}: range [{p2:.2f}, {p98:.2f}] → [0, 255]")

        # Save PCA result
        print(f"  Saving to {output_file}...")
        OUTPUT_DIR.mkdir(exist_ok=True)

        profile = src.profile.copy()
        profile.update({
            'count': N_COMPONENTS,
            'dtype': 'uint8'
        })

        with rasterio.open(output_file, 'w', **profile) as dst:
            dst.write(rgb_image)

        # Print explained variance
        explained_var = pca.explained_variance_ratio_
        total_var = explained_var.sum() * 100
        print(f"\n  ✓ PCA complete!")
        print(f"    Explained variance: {explained_var[0]*100:.1f}%, {explained_var[1]*100:.1f}%, {explained_var[2]*100:.1f}%")
        print(f"    Total: {total_var:.1f}% of variance captured")

        size_mb = output_file.stat().st_size / (1024 * 1024)
        print(f"    Output: {output_file} ({size_mb:.1f} MB)")

        return True

def main():
    """Process all years."""
    print("=" * 70)
    print("Creating PCA-projected embeddings for visualization")
    print("=" * 70)

    success_count = 0

    for year in YEARS:
        if compute_pca_for_year(year):
            success_count += 1

    print("\n" + "=" * 70)
    print(f"✅ Complete! Processed {success_count} years")
    print(f"\nPCA embeddings saved in: {OUTPUT_DIR.absolute()}")
    print("\nNext steps:")
    print("  1. Create pyramids: modify create_pyramids.py to include PCA mosaics")
    print("  2. Add PCA panel to viewer")

if __name__ == "__main__":
    main()
