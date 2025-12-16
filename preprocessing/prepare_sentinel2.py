#!/usr/bin/env python3
"""
Prepare Sentinel-2 quarterly composites in Zarr format.
"""

import numpy as np
import zarr
from pathlib import Path
from typing import List

def create_zarr_store(output_path: Path,
                      shape: tuple,
                      chunks: tuple):
    """
    Create Zarr array for Sentinel-2 composites.

    Args:
        output_path: Path to .zarr directory
        shape: (years, quarters, height, width, bands)
        chunks: Chunk size for each dimension
    """
    store = zarr.DirectoryStore(output_path)
    root = zarr.group(store=store, overwrite=True)

    composites = root.create_dataset(
        'composites',
        shape=shape,
        chunks=chunks,
        dtype='uint16',
        compressor=zarr.Blosc(cname='zstd', clevel=5)
    )

    # Store metadata
    root.attrs['description'] = 'Sentinel-2 quarterly median composites'
    root.attrs['bands'] = ['B4', 'B3', 'B2']  # RGB
    root.attrs['scale_factor'] = 10000

    return composites

def load_and_process_composite(file_path: Path) -> np.ndarray:
    """
    Load Sentinel-2 composite and prepare for storage.
    Expected input: GeoTIFF with shape (height, width, 3)
    """
    # Use rasterio or similar to load GeoTIFF
    # composite = rasterio.open(file_path).read().transpose(1, 2, 0)
    # return composite
    pass

def populate_zarr(composites_dir: Path,
                  output_zarr: Path,
                  years: List[int],
                  quarters: List[int]):
    """
    Load all quarterly composites and populate Zarr store.
    """
    shape = (len(years), len(quarters), 2000, 2000, 3)
    chunks = (1, 1, 256, 256, 3)

    z = create_zarr_store(output_zarr, shape, chunks)

    for y_idx, year in enumerate(years):
        for q_idx, quarter in enumerate(quarters):
            file_pattern = f"s2_composite_{year}_Q{quarter}.tif"
            file_path = composites_dir / file_pattern

            if file_path.exists():
                print(f"Processing {year} Q{quarter}...")
                composite = load_and_process_composite(file_path)
                z[y_idx, q_idx, :, :, :] = composite
            else:
                print(f"Warning: Missing {file_path}")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--years', nargs='+', type=int,
                        default=list(range(2017, 2025)))

    args = parser.parse_args()

    populate_zarr(args.input, args.output, args.years, [1, 2, 3, 4])
