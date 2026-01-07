#!/usr/bin/env python3
"""
Create FAISS index from embedding mosaics for fast similarity search.

Two-step approach:
1. Create IVF-PQ index from sampled embeddings (every 4×4 pixels)
2. Store ALL embeddings as numpy array for threshold-based filtering

Enables queries like: "Find all pixels similar to embedding X with similarity > threshold"
"""

import sys
import numpy as np
import rasterio
from pathlib import Path
import json
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).parent))

from lib.viewport_utils import get_active_viewport

# Configuration
MOSAICS_DIR = Path("mosaics")
FAISS_INDICES_DIR = Path("faiss_indices")
SAMPLING_FACTOR = 4  # Every 4×4 pixels (reduces 19M → 1.2M vectors)
EMBEDDING_DIM = 128

def check_faiss_installed():
    """Check if FAISS is installed, provide helpful message if not."""
    try:
        import faiss
        return True
    except ImportError:
        logger.error("FAISS not installed. Install with: pip install faiss-cpu")
        return False


def normalize_embeddings(embeddings):
    """Normalize uint8 embeddings [0-255] to float32 [0-1] for FAISS."""
    return embeddings.astype(np.float32) / 255.0


def create_faiss_index():
    """Create FAISS index and store all embeddings for current viewport."""

    # Check FAISS availability
    if not check_faiss_installed():
        sys.exit(1)

    import faiss

    # Read active viewport
    try:
        viewport = get_active_viewport()
        viewport_id = viewport['viewport_id']
        bounds = viewport['bounds_tuple']
    except Exception as e:
        logger.error(f"Failed to read viewport: {e}")
        sys.exit(1)

    # Find mosaic file
    mosaic_file = MOSAICS_DIR / "bangalore_2024.tif"
    if not mosaic_file.exists():
        logger.warning(f"Mosaic file not found: {mosaic_file}")
        return

    logger.info("=" * 70)
    logger.info("Creating FAISS Index for Embeddings")
    logger.info("=" * 70)
    logger.info(f"Viewport: {viewport_id}")
    logger.info(f"Mosaic file: {mosaic_file.name}")
    logger.info(f"Sampling factor: {SAMPLING_FACTOR}×{SAMPLING_FACTOR}")

    # Create output directory
    output_dir = FAISS_INDICES_DIR / viewport_id
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        with rasterio.open(mosaic_file) as src:
            height, width = src.height, src.width
            logger.info(f"Mosaic dimensions: {width}×{height}")
            logger.info(f"Total pixels: {width * height:,}")

            # Step 1: Read sampled embeddings for FAISS index
            logger.info(f"\n📊 Step 1: Creating IVF-PQ index from sampled pixels...")
            logger.info(f"   Reading every {SAMPLING_FACTOR}×{SAMPLING_FACTOR} pixel...")

            sampled_embeddings = []
            sampled_coords = []

            for y in range(0, height, SAMPLING_FACTOR):
                for x in range(0, width, SAMPLING_FACTOR):
                    # Read 128 bands at this pixel (3×3 window to ensure data)
                    from rasterio import windows as rasterio_windows
                    window = rasterio_windows.Window(
                        max(0, x - 1), max(0, y - 1), 3, 3
                    )
                    data = src.read(window=window)  # (128, 3, 3)

                    # Extract center pixel
                    center_x = min(1, x)
                    center_y = min(1, y)
                    embedding = data[:, center_y, center_x]  # (128,)
                    sampled_embeddings.append(embedding)
                    sampled_coords.append((x, y))

            sampled_embeddings = np.array(sampled_embeddings, dtype=np.uint8)
            logger.info(f"   ✓ Sampled {len(sampled_embeddings):,} pixels")

            # Normalize to float32 [0-1]
            sampled_embeddings_f32 = normalize_embeddings(sampled_embeddings)

            # Create IVF-PQ index
            logger.info(f"   Creating IVF-PQ index...")
            # IVF: 1024 cells, PQ: 64 subquantizers (128/2 = 64)
            nlist = min(1024, max(100, len(sampled_embeddings) // 100))
            quantizer = faiss.IndexFlatL2(EMBEDDING_DIM)
            index = faiss.IndexIVFPQ(quantizer, EMBEDDING_DIM, nlist, 64, 8)
            index.train(sampled_embeddings_f32)
            index.add(sampled_embeddings_f32)

            # Save FAISS index
            index_file = output_dir / "embeddings.index"
            faiss.write_index(index, str(index_file))
            logger.info(f"   ✓ Saved FAISS index: {index_file}")
            index_size_mb = index_file.stat().st_size / (1024 * 1024)
            logger.info(f"     Index size: {index_size_mb:.1f} MB")

            # Step 2: Read ALL embeddings for threshold-based search
            logger.info(f"\n💾 Step 2: Storing all pixel embeddings...")
            logger.info(f"   Reading all {width * height:,} pixels...")

            all_embeddings = []
            pixel_coords = []

            # Read in chunks to manage memory
            chunk_size = 256
            for y_start in range(0, height, chunk_size):
                y_end = min(y_start + chunk_size, height)
                logger.info(f"   Processing rows {y_start}-{y_end}...")

                # Read all bands for this chunk
                from rasterio import windows as rasterio_windows
                window = rasterio_windows.Window(0, y_start, width, y_end - y_start)
                chunk_data = src.read(window=window)  # (128, chunk_height, width)

                # Reshape: (128, chunk_height, width) → (chunk_height*width, 128)
                chunk_height = chunk_data.shape[1]
                chunk_embeddings = chunk_data.transpose(1, 2, 0).reshape(-1, EMBEDDING_DIM)
                all_embeddings.append(chunk_embeddings)

                # Generate pixel coordinates
                for y in range(y_start, y_end):
                    for x in range(width):
                        pixel_coords.append((x, y))

            all_embeddings = np.vstack(all_embeddings).astype(np.uint8)
            logger.info(f"   ✓ Loaded all embeddings: {all_embeddings.shape}")

            # Save all embeddings
            embeddings_file = output_dir / "all_embeddings.npy"
            np.save(embeddings_file, all_embeddings)
            logger.info(f"   ✓ Saved all embeddings: {embeddings_file}")
            embeddings_size_mb = embeddings_file.stat().st_size / (1024 * 1024)
            logger.info(f"     Size: {embeddings_size_mb:.1f} MB")

            # Save pixel coordinates (x, y) as numpy array for quick lookup
            coords_array = np.array(pixel_coords, dtype=np.int32)
            coords_file = output_dir / "pixel_coords.npy"
            np.save(coords_file, coords_array)

            # Step 3: Create metadata JSON
            logger.info(f"\n📋 Step 3: Creating metadata...")

            metadata = {
                "viewport_id": viewport_id,
                "viewport_bounds": list(bounds),  # (min_lat, min_lon, max_lat, max_lon)
                "mosaic_file": str(mosaic_file),
                "mosaic_height": height,
                "mosaic_width": width,
                "num_total_pixels": width * height,
                "num_sampled_pixels": len(sampled_embeddings),
                "sampling_factor": SAMPLING_FACTOR,
                "embedding_dim": EMBEDDING_DIM,
                "pixel_size_meters": 10,
                "crs": "EPSG:4326",
                "geotransform": {
                    "a": src.transform.a,  # pixel width (degrees)
                    "b": src.transform.b,  # rotation
                    "c": src.transform.c,  # x offset (longitude)
                    "d": src.transform.d,  # rotation
                    "e": src.transform.e,  # pixel height (degrees, negative)
                    "f": src.transform.f   # y offset (latitude)
                },
                "faiss_index_type": f"IVF{nlist},PQ64"
            }

            metadata_file = output_dir / "metadata.json"
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            logger.info(f"   ✓ Saved metadata: {metadata_file}")

    except Exception as e:
        logger.error(f"Error creating FAISS index: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("✅ FAISS index creation complete!")
    logger.info(f"\nFiles created in {output_dir}/:")
    logger.info(f"  - embeddings.index ({index_size_mb:.1f} MB)")
    logger.info(f"  - all_embeddings.npy ({embeddings_size_mb:.1f} MB)")
    logger.info(f"  - pixel_coords.npy ({coords_file.stat().st_size / 1024:.1f} KB)")
    logger.info(f"  - metadata.json")
    total_size = (index_size_mb + embeddings_size_mb +
                  coords_file.stat().st_size / (1024 * 1024) +
                  metadata_file.stat().st_size / (1024 * 1024))
    logger.info(f"\nTotal size: {total_size:.1f} MB")
    logger.info("=" * 70)


if __name__ == "__main__":
    create_faiss_index()
