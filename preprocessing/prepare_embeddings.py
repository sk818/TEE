#!/usr/bin/env python3
"""
Prepare TESSERA embeddings for efficient GPU access.
- Convert uint8 to float16
- Normalize to unit vectors
- Write in custom binary format
"""

import numpy as np
from pathlib import Path
import struct

def normalize_embeddings(embeddings: np.ndarray) -> np.ndarray:
    """
    Normalize embeddings to unit vectors.

    Args:
        embeddings: Array of shape (height, width, 128) with uint8 values

    Returns:
        Normalized embeddings as float16
    """
    # Convert to float
    embeddings_f32 = embeddings.astype(np.float32) / 255.0

    # Normalize to unit length
    norms = np.linalg.norm(embeddings_f32, axis=-1, keepdims=True)
    norms = np.maximum(norms, 1e-8)  # Avoid division by zero
    embeddings_normalized = embeddings_f32 / norms

    # Convert to float16 to save space
    return embeddings_normalized.astype(np.float16)

def write_embedding_file(embeddings: np.ndarray,
                         year: int,
                         bounds: tuple,
                         output_path: Path):
    """
    Write embeddings in custom binary format with header.
    """
    height, width, dims = embeddings.shape
    min_lon, min_lat, max_lon, max_lat = bounds

    with open(output_path, 'wb') as f:
        # Write header
        f.write(b'TESS')  # Magic number
        f.write(struct.pack('I', 1))  # Version
        f.write(struct.pack('I', year))
        f.write(struct.pack('I', width))
        f.write(struct.pack('I', height))
        f.write(struct.pack('I', dims))
        f.write(struct.pack('d', min_lon))
        f.write(struct.pack('d', min_lat))
        f.write(struct.pack('d', max_lon))
        f.write(struct.pack('d', max_lat))
        f.write(b'\x00' * 16)  # Reserved

        # Write data (row-major order)
        embeddings.tofile(f)

def process_all_embeddings(input_dir: Path,
                           output_dir: Path,
                           bounds: tuple):
    """
    Process all embedding files in input directory.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    for embedding_file in sorted(input_dir.glob('*.npy')):
        year = int(embedding_file.stem.split('_')[-1])
        print(f"Processing embeddings for {year}...")

        # Load raw embeddings (uint8)
        embeddings = np.load(embedding_file)

        # Normalize
        embeddings_normalized = normalize_embeddings(embeddings)

        # Write binary file
        output_file = output_dir / f'embeddings_{year}_{bounds[0]:.4f}_{bounds[1]:.4f}.bin'
        write_embedding_file(embeddings_normalized, year, bounds, output_file)

        print(f"  Saved to {output_file}")
        print(f"  Size: {output_file.stat().st_size / 1024 / 1024:.2f} MB")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--bounds', nargs=4, type=float, required=True)

    args = parser.parse_args()

    process_all_embeddings(args.input, args.output, tuple(args.bounds))
