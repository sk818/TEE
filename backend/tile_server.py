#!/usr/bin/env python3
"""
Tile server for serving Sentinel-2 RGB and visualization pyramids as PNG tiles.

Uses rio-tiler to serve GeoTIFF pyramids via standard TMS (Tile Map Service) endpoints.
Dynamically selects pyramid level based on Leaflet zoom level.
"""

import logging
from pathlib import Path
from typing import Optional
import io
import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import numpy as np

try:
    from rio_tiler.io import Reader
    from rio_tiler.models import ImageData
except ImportError:
    logger = logging.getLogger(__name__)
    logger.error("rio-tiler not installed")
    logger.error("Install with: pip install rio-tiler")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="TEE Tile Server",
    description="Tile server for TESSERA Embedding Explorer",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
DATA_DIR = Path(__file__).parent.parent / "public" / "data" / "viewports"
DEFAULT_TILE_SIZE = 2048  # Large tiles for smooth rendering (matching blore approach)



# RGB pyramids are stored per-viewport at: viewports/{viewport_id}/pyramids/{year}/level_N.tif

# Zoom level to pyramid level mapping for embedding pyramids
# Leaflet requests tiles at z=0 to z=28
# We have pyramid levels 0-5 (6 levels)
# Map z=13-18 → level 0 (full res)
#     z=11-12 → level 1 (2x coarsening)
#     z=9-10  → level 2
#     z=7-8   → level 3
#     z=5-6   → level 4
#     z=0-4   → level 5 (32x coarsening)
def zoom_to_pyramid_level(z: int, max_pyramid_level: int = 5) -> int:
    """Map Leaflet zoom level to pyramid level for embedding pyramids."""
    # Each 2 zoom levels = 1 pyramid level
    pyramid_level = (18 - z) // 2
    return max(0, min(max_pyramid_level, pyramid_level))


def zoom_to_rgb_pyramid_level(z: int, max_pyramid_level: int = 5) -> int:
    """
    Map Leaflet zoom level to RGB pyramid level (blore approach).

    With tileSize=2048 and zoomOffset=-3:
    - Displayed zoom 12 → requests z=9 → level 1
    - Displayed zoom 14 → requests z=11 → level 0
    - Displayed zoom 16 → requests z=13 → level 0 (clamped)

    Each 2 zoom levels = 1 pyramid level, with base at z=12.
    """
    # Map zoom to pyramid level: (12 - z) // 2
    # z=12 → level 0, z=10 → level 1, z=8 → level 2, z=6 → level 3, z=4 → level 4, z=2 → level 5
    pyramid_level = max(0, (12 - z) // 2)
    return min(max_pyramid_level, pyramid_level)


def tile_to_bbox(x: int, y: int, z: int) -> tuple:
    """Convert tile coordinates to bounding box in EPSG:4326."""
    import math

    n = 2.0 ** z
    lon_min = x / n * 360.0 - 180.0
    lon_max = (x + 1) / n * 360.0 - 180.0

    lat_max_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat_min_rad = math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n)))

    lat_max = math.degrees(lat_max_rad)
    lat_min = math.degrees(lat_min_rad)

    return (lon_min, lat_min, lon_max, lat_max)


def get_rgb_tile(
    tif_path: Path,
    bbox: tuple,
    tile_size: int = DEFAULT_TILE_SIZE,
    band_indices: Optional[list] = None
) -> Image.Image:
    """
    Extract a tile from a GeoTIFF and return as PIL Image.

    Args:
        tif_path: Path to GeoTIFF file
        bbox: (min_lon, min_lat, max_lon, max_lat) bounding box
        tile_size: Output tile size in pixels
        band_indices: Which bands to use (None = all)

    Returns:
        PIL Image in RGB mode
    """
    with Reader(str(tif_path)) as src:
        # Read tile from GeoTIFF
        img_data = src.part(bbox, width=tile_size, height=tile_size)

        # Extract bands
        data = img_data.data

        if band_indices is not None:
            # Select specific bands
            data = data[band_indices, :, :]

        # Handle different input formats
        if data.shape[0] == 1:
            # Single band - duplicate to RGB
            arr = data[0]
            rgb = np.stack([arr, arr, arr], axis=0)
        elif data.shape[0] == 3:
            # Already RGB
            rgb = data[:3]
        elif data.shape[0] > 3:
            # More than 3 bands - take first 3
            rgb = data[:3]
        else:
            # Less than 3 bands - pad with zeros
            rgb = np.zeros((3, data.shape[1], data.shape[2]), dtype=data.dtype)
            rgb[:data.shape[0]] = data

        # Transpose to (H, W, C) for PIL
        rgb_t = np.transpose(rgb, (1, 2, 0))

        # Ensure uint8
        if rgb_t.dtype != np.uint8:
            # Scale to 0-255 if needed
            if rgb_t.max() > 255:
                rgb_t = (rgb_t / rgb_t.max() * 255).astype(np.uint8)
            else:
                rgb_t = rgb_t.astype(np.uint8)

        # Create PIL image
        img = Image.fromarray(rgb_t, mode='RGB')

        return img


# ============================================================================
# API Routes
# ============================================================================

@app.get("/api/tiles/sentinel2/{viewport_id}/{year}/{z}/{x}/{y}.png")
async def get_sentinel2_tile(viewport_id: str, year: int, z: int, x: int, y: int):
    """Serve Sentinel-2 RGB tile."""
    try:
        # Sentinel-2 is not pyramided in this implementation,
        # always use the full resolution GeoTIFF
        tif_path = DATA_DIR / viewport_id / "sentinel2" / f"{year}_rgb.tif"

        if not tif_path.exists():
            # Return transparent tile if file doesn't exist
            img = Image.new('RGBA', (DEFAULT_TILE_SIZE, DEFAULT_TILE_SIZE), (0, 0, 0, 0))
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)
            return Response(content=buf.getvalue(), media_type="image/png")

        # Get tile bounds
        bbox = tile_to_bbox(x, y, z)

        try:
            # Read tile from GeoTIFF
            img = get_rgb_tile(tif_path, bbox, DEFAULT_TILE_SIZE)

            # Save to buffer
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)

            return Response(content=buf.getvalue(), media_type="image/png")

        except Exception as e:
            logger.warning(f"Error reading tile sentinel2/{viewport_id}/{year}/{z}/{x}/{y}: {e}")
            # Return transparent tile on error
            img = Image.new('RGBA', (DEFAULT_TILE_SIZE, DEFAULT_TILE_SIZE), (0, 0, 0, 0))
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)
            return Response(content=buf.getvalue(), media_type="image/png")

    except Exception as e:
        logger.error(f"Error serving Sentinel-2 tile: {e}")
        return Response(content=f"Error: {e}", status_code=500)


@app.get("/api/tiles/embeddings/{viewport_id}/{year}/{z}/{x}/{y}.png")
async def get_embeddings_tile(viewport_id: str, year: int, z: int, x: int, y: int):
    """Serve embeddings visualization tile (RGB pyramids)."""
    try:
        # Map zoom level to pyramid level
        pyramid_level = zoom_to_pyramid_level(z)

        # Get pyramid level file
        tif_path = DATA_DIR / viewport_id / "pyramids" / str(year) / f"level_{pyramid_level}.tif"

        if not tif_path.exists():
            # Return transparent tile if file doesn't exist
            img = Image.new('RGBA', (DEFAULT_TILE_SIZE, DEFAULT_TILE_SIZE), (0, 0, 0, 0))
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)
            logger.info(f"File not found: {tif_path}")
            return Response(content=buf.getvalue(), media_type="image/png")

        # Get tile bounds
        bbox = tile_to_bbox(x, y, z)

        try:
            # Read tile from GeoTIFF
            img = get_rgb_tile(tif_path, bbox, DEFAULT_TILE_SIZE)

            # Save to buffer
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)

            logger.debug(f"Served embeddings tile {viewport_id}/{year}/level_{pyramid_level}/{z}/{x}/{y}")

            return Response(content=buf.getvalue(), media_type="image/png")

        except Exception as e:
            logger.warning(f"Error reading tile embeddings/{viewport_id}/{year}/level_{pyramid_level}/{z}/{x}/{y}: {e}")
            # Return transparent tile on error
            img = Image.new('RGBA', (DEFAULT_TILE_SIZE, DEFAULT_TILE_SIZE), (0, 0, 0, 0))
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)
            return Response(content=buf.getvalue(), media_type="image/png")

    except Exception as e:
        logger.error(f"Error serving embeddings tile: {e}")
        return Response(content=f"Error: {e}", status_code=500)


@app.get("/api/tiles/rgb/{viewport_id}/{year}/{z}/{x}/{y}.png")
async def get_rgb_pyramid_tile(viewport_id: str, year: int, z: int, x: int, y: int):
    """Serve RGB pyramid tile from viewport-specific pyramids (blore approach with 2048px tiles)."""
    try:
        # Use 2048px tiles for smooth rendering (blore approach)
        tile_size = DEFAULT_TILE_SIZE

        # Map zoom level to pyramid level
        pyramid_level = zoom_to_rgb_pyramid_level(z)

        # Get pyramid level file from viewport-specific directory
        tif_path = DATA_DIR / viewport_id / "pyramids" / str(year) / f"level_{pyramid_level}.tif"

        if not tif_path.exists():
            # Return transparent tile if file doesn't exist
            img = Image.new('RGBA', (tile_size, tile_size), (0, 0, 0, 0))
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)
            logger.debug(f"RGB pyramid file not found: {tif_path}")
            return Response(content=buf.getvalue(), media_type="image/png")

        # Get tile bounds
        bbox = tile_to_bbox(x, y, z)

        try:
            # Read tile from GeoTIFF with 1024px size
            img = get_rgb_tile(tif_path, bbox, tile_size)

            # Save to buffer
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)

            logger.debug(f"Served RGB tile {viewport_id}/level_{pyramid_level}/{z}/{x}/{y} ({tile_size}×{tile_size})")

            return Response(content=buf.getvalue(), media_type="image/png")

        except Exception as e:
            logger.warning(f"Error reading RGB tile {viewport_id}/level_{pyramid_level}/{z}/{x}/{y}: {e}")
            # Return transparent tile on error
            img = Image.new('RGBA', (tile_size, tile_size), (0, 0, 0, 0))
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)
            return Response(content=buf.getvalue(), media_type="image/png")

    except Exception as e:
        logger.error(f"Error serving RGB tile: {e}")
        return Response(content=f"Error: {e}", status_code=500)


@app.get("/api/tiles/bounds/{viewport_id}/{year}")
async def get_tile_bounds(viewport_id: str, year: int):
    """Get bounds for a viewport and year."""
    try:
        # Try to get from metadata
        metadata_file = DATA_DIR / viewport_id / "metadata.json"

        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)

            bounds = metadata.get('bounds', {})
            center = metadata.get('center', [0, 0])

            return {
                'bounds': bounds,
                'center': center,
                'years': metadata.get('years', [])
            }
        else:
            raise HTTPException(status_code=404, detail="Viewport not found")

    except Exception as e:
        logger.error(f"Error getting bounds for {viewport_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tiles/health")
async def health():
    """Health check endpoint."""
    return {
        'status': 'ok',
        'data_dir': str(DATA_DIR),
        'tile_size': DEFAULT_TILE_SIZE
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        'name': 'TEE Tile Server',
        'version': '1.0.0',
        'endpoints': {
            'sentinel2': '/api/tiles/sentinel2/{viewport_id}/{year}/{z}/{x}/{y}.png',
            'embeddings': '/api/tiles/embeddings/{viewport_id}/{year}/{z}/{x}/{y}.png',
            'rgb_pyramids': '/api/tiles/rgb/{viewport_id}/{year}/{z}/{x}/{y}.png',
            'bounds': '/api/tiles/bounds/{viewport_id}/{year}',
            'health': '/api/tiles/health'
        },
        'note': 'RGB pyramids: 5 levels (0-4) with √10 zoom factor between levels. Stored per-viewport.'
    }


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting TEE Tile Server...")
    logger.info(f"Serving tiles from: {DATA_DIR}")
    logger.info("Available endpoints:")
    logger.info("  - http://localhost:8001/api/tiles/sentinel2/{viewport_id}/{year}/{z}/{x}/{y}.png")
    logger.info("  - http://localhost:8001/api/tiles/embeddings/{viewport_id}/{year}/{z}/{x}/{y}.png")
    logger.info("  - http://localhost:8001/api/tiles/rgb/{viewport_id}/{year}/{z}/{x}/{y}.png (viewport-specific RGB pyramids)")
    logger.info("  - http://localhost:8001/api/tiles/bounds/{viewport_id}/{year}")
    logger.info("  - http://localhost:8001/api/tiles/health")
    logger.info("\nRGB pyramid structure:")
    logger.info("  - Level 0: 1m/pixel (highest zoom)")
    logger.info("  - Level 1: 3.16m/pixel")
    logger.info("  - Level 2: 10m/pixel")
    logger.info("  - Level 3: 31.6m/pixel")
    logger.info("  - Level 4: 100m/pixel (lowest zoom)")
    logger.info("  Each level zooms out by √10 ≈ 3.162x")
    logger.info("\nStarting server on http://localhost:8001\n")

    uvicorn.run(app, host="0.0.0.0", port=8001)
