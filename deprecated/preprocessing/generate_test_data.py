#!/usr/bin/env python3
"""
Generate synthetic test embedding data for the TEE pipeline.
This creates realistic embedding arrays that can be processed through
the full preprocessing pipeline.
"""

import numpy as np
from pathlib import Path
import argparse

def generate_test_embeddings(width: int = 256,
                             height: int = 256,
                             dimensions: int = 128,
                             years: list = None) -> dict:
    """
    Generate synthetic but realistic embedding data.

    Args:
        width: Image width in pixels
        height: Image height in pixels
        dimensions: Embedding vector dimensions (typically 128)
        years: List of years to generate

    Returns:
        Dictionary mapping year -> embedding array
    """
    if years is None:
        years = list(range(2017, 2025))

    embeddings = {}

    for year in years:
        print(f"Generating embeddings for {year} ({width}x{height}x{dimensions})...")

        # Create embeddings with spatial structure
        # Use different random seed per year for variation
        np.random.seed(year)

        # Generate base embeddings
        emb = np.random.randn(height, width, dimensions).astype(np.uint8)

        # Add some spatial structure (gradients)
        for i in range(dimensions):
            # Add spatial patterns
            x = np.linspace(0, 1, width)
            y = np.linspace(0, 1, height)
            X, Y = np.meshgrid(x, y)

            # Create smooth spatial variation
            pattern = (np.sin(X * 3) * np.cos(Y * 3) + 1) * 127

            # Blend with random noise
            emb[:, :, i] = (emb[:, :, i] * 0.7 + pattern * 0.3).astype(np.uint8)

        embeddings[year] = emb

    return embeddings

def save_test_data(embeddings: dict, output_dir: Path):
    """
    Save embeddings in .npy format for processing.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    for year, emb in embeddings.items():
        output_file = output_dir / f'embeddings_{year}.npy'
        np.save(output_file, emb)
        print(f"  Saved: {output_file} ({emb.shape}, {emb.nbytes / 1024 / 1024:.1f} MB)")

def main():
    parser = argparse.ArgumentParser(description='Generate synthetic test embeddings')
    parser.add_argument('--width', type=int, default=256, help='Image width (default: 256)')
    parser.add_argument('--height', type=int, default=256, help='Image height (default: 256)')
    parser.add_argument('--dimensions', type=int, default=128, help='Embedding dimensions (default: 128)')
    parser.add_argument('--years', nargs='+', type=int, default=list(range(2017, 2025)),
                       help='Years to generate (default: 2017-2024)')
    parser.add_argument('--output', type=Path, default=Path('data/raw_embeddings'),
                       help='Output directory (default: data/raw_embeddings)')

    args = parser.parse_args()

    print("=" * 70)
    print("GENERATING SYNTHETIC TEST EMBEDDINGS")
    print("=" * 70)
    print(f"Size: {args.width}x{args.height} pixels")
    print(f"Dimensions: {args.dimensions}")
    print(f"Years: {args.years[0]}-{args.years[-1]} ({len(args.years)} years)")
    print(f"Output: {args.output}")
    print("=" * 70)

    # Generate embeddings
    embeddings = generate_test_embeddings(
        width=args.width,
        height=args.height,
        dimensions=args.dimensions,
        years=args.years
    )

    # Save embeddings
    save_test_data(embeddings, args.output)

    print("\n✅ Test data generated successfully!")
    print(f"\nNext step: Run prepare_embeddings.py to process these embeddings:")
    print(f"  python3 preprocessing/prepare_embeddings.py \\")
    print(f"    --input {args.output} \\")
    print(f"    --output public/data/embeddings \\")
    print(f"    --bounds -0.5 51.5 0.5 52.5")

if __name__ == "__main__":
    main()
