#!/usr/bin/env python3
"""
Compute PCA on 8 years of embeddings for visualization.
"""

import numpy as np
from sklearn.decomposition import IncrementalPCA
from pathlib import Path
import struct

def load_embeddings_for_pca(embedding_dir: Path, years: list) -> np.ndarray:
    """
    Load all years of embeddings and flatten for PCA.

    Returns:
        Array of shape (n_pixels, n_temporal_features)
        where n_temporal_features = 128 * n_years
    """
    all_embeddings = []

    for year in sorted(years):
        # Look for file with or without bounds in name
        files = list(embedding_dir.glob(f'embeddings_{year}*.bin'))
        if not files:
            raise FileNotFoundError(f"No embedding file found for year {year}")
        file_path = files[0]

        # Read header to get dimensions
        with open(file_path, 'rb') as f:
            magic = f.read(4)
            version = struct.unpack('I', f.read(4))[0]
            year_stored = struct.unpack('I', f.read(4))[0]
            width = struct.unpack('I', f.read(4))[0]
            height = struct.unpack('I', f.read(4))[0]
            dims = struct.unpack('I', f.read(4))[0]

            # Skip bounds and reserved space (8*4 bytes for bounds + 16 reserved)
            f.seek(4 + 4 + 4 + 4 + 4 + 4 + 32 + 16)  # Total header = 72 bytes

            # Read embeddings as float16
            embeddings = np.fromfile(f, dtype=np.float16)
            embeddings = embeddings.reshape(height, width, dims)
            all_embeddings.append(embeddings)

    # Stack along temporal dimension
    stacked = np.stack(all_embeddings, axis=-1)  # (H, W, 128, 8)

    # Reshape to (n_pixels, 128*8)
    n_pixels = stacked.shape[0] * stacked.shape[1]
    features = stacked.reshape(n_pixels, -1)

    return features, stacked.shape[:2]

def compute_pca_components(features: np.ndarray,
                           n_components: int = 3) -> tuple:
    """
    Compute PCA using incremental PCA for memory efficiency.

    Returns:
        (transformed_features, explained_variance)
    """
    print("Computing PCA...")

    # Use IncrementalPCA for memory efficiency
    pca = IncrementalPCA(n_components=n_components, batch_size=10000)

    # Fit in batches
    n_samples = features.shape[0]
    batch_size = 10000

    for i in range(0, n_samples, batch_size):
        batch = features[i:i+batch_size]
        pca.partial_fit(batch)

    # Transform all data
    transformed = pca.transform(features)

    print(f"Explained variance: {pca.explained_variance_ratio_}")

    return transformed, pca.explained_variance_ratio_

def normalize_for_visualization(components: np.ndarray) -> np.ndarray:
    """
    Normalize PCA components to 0-1 range for RGB visualization.
    """
    # Normalize each component independently
    normalized = np.zeros_like(components)

    for i in range(components.shape[-1]):
        comp = components[:, i]
        min_val = np.percentile(comp, 1)  # Clip outliers
        max_val = np.percentile(comp, 99)
        normalized[:, i] = np.clip((comp - min_val) / (max_val - min_val), 0, 1)

    return normalized

def write_pca_file(components: np.ndarray,
                   shape: tuple,
                   explained_variance: np.ndarray,
                   bounds: tuple,
                   output_path: Path):
    """
    Write PCA components in custom binary format.
    """
    height, width = shape
    n_components = components.shape[1]
    min_lon, min_lat, max_lon, max_lat = bounds

    # Reshape back to spatial dimensions
    components_spatial = components.reshape(height, width, n_components)

    with open(output_path, 'wb') as f:
        # Write header
        f.write(b'PCA3')
        f.write(struct.pack('I', width))
        f.write(struct.pack('I', height))
        f.write(struct.pack('I', n_components))

        # Write explained variance
        for var in explained_variance:
            f.write(struct.pack('f', var))

        f.write(b'\x00' * 8)  # Reserved

        # Write data as float32
        components_spatial.astype(np.float32).tofile(f)

def main(embedding_dir: Path,
         output_path: Path,
         bounds: tuple,
         years: list):
    """
    Main PCA computation pipeline.
    """
    # Load embeddings
    print("Loading embeddings...")
    features, shape = load_embeddings_for_pca(embedding_dir, years)

    # Compute PCA
    components, explained_var = compute_pca_components(features, n_components=3)

    # Normalize for visualization
    components_norm = normalize_for_visualization(components)

    # Write output
    print(f"Writing PCA components to {output_path}...")
    write_pca_file(components_norm, shape, explained_var, bounds, output_path)

    print("Done!")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True,
                        help='Directory containing processed embeddings')
    parser.add_argument('--output', type=Path, required=True,
                        help='Output PCA file')
    parser.add_argument('--bounds', nargs=4, type=float, required=True)
    parser.add_argument('--years', nargs='+', type=int,
                        default=list(range(2017, 2025)))

    args = parser.parse_args()

    main(args.input, args.output, tuple(args.bounds), args.years)
