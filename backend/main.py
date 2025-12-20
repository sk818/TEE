#!/usr/bin/env python3
"""
FastAPI backend for TESSERA Embedding Explorer.

Simple downloader that reads viewport.txt and downloads embeddings as GeoTIFF.
"""

import logging
import uuid
from pathlib import Path
from typing import Optional
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="TESSERA Embedding Explorer API",
    description="Simple viewport-based TESSERA embedding downloader",
    version="2.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:5173", "http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
DATA_DIR = Path(__file__).parent.parent / "public" / "data" / "viewports"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Task storage (in-memory)
tasks: dict = {}


# ============================================================================
# Pydantic Models
# ============================================================================

class Bounds(BaseModel):
    """Geographic bounds."""
    minLon: float
    minLat: float
    maxLon: float
    maxLat: float


class ViewportSaveRequest(BaseModel):
    """Request to save viewport to viewport.txt."""
    center: list[float]
    bounds: Bounds
    sizeKm: float


class TaskStatus(BaseModel):
    """Task status response."""
    task_id: str
    state: str  # 'downloading', 'complete', 'error'
    progress: float = 0.0
    message: str = ""
    error: Optional[str] = None


# ============================================================================
# Background Tasks
# ============================================================================

def download_embeddings_task(task_id: str, year: int = 2024, viewport_id: Optional[str] = None):
    """Background task to download embeddings from viewport.txt."""
    if task_id not in tasks:
        logger.error(f"Task {task_id} not found")
        return

    try:
        logger.info(f"Starting embeddings download task {task_id} for viewport {viewport_id}")
        tasks[task_id]['state'] = 'downloading'
        tasks[task_id]['message'] = 'Initializing...'

        from processing.download_embeddings import download_embeddings
        from processing.extract_rgb import extract_rgb
        from processing.create_rgb_pyramids import create_rgb_pyramids

        # Determine output directory based on viewport_id
        if viewport_id:
            output_dir = DATA_DIR / viewport_id
            output_dir.mkdir(parents=True, exist_ok=True)
        else:
            output_dir = DATA_DIR

        def progress_callback(message: str, percent: float):
            """Update task progress."""
            tasks[task_id]['progress'] = percent
            tasks[task_id]['message'] = message
            logger.info(f"Task {task_id}: {message} ({percent}%)")

        # Download embeddings to viewport-specific directory
        output_file = output_dir / f"embeddings_{year}.tif"
        result = download_embeddings(
            year=year,
            output_file=output_file,
            progress_callback=progress_callback
        )

        if not result['success']:
            tasks[task_id]['state'] = 'error'
            tasks[task_id]['error'] = result.get('error', 'Unknown error')
            logger.error(f"Task {task_id} failed: {result.get('error')}")
            return

        logger.info(f"✓ Embeddings downloaded, now extracting RGB...")

        # Extract RGB from embeddings
        def rgb_progress(message: str, percent: float):
            """Update task progress for RGB extraction."""
            progress = 50 + (percent / 100) * 25  # RGB extraction is 25-50%
            tasks[task_id]['progress'] = progress
            tasks[task_id]['message'] = message
            logger.info(f"Task {task_id}: {message} ({progress}%)")

        rgb_file = output_dir / f"rgb_{year}.tif"
        rgb_result = extract_rgb(
            embeddings_file=output_file,
            output_file=rgb_file,
            progress_callback=rgb_progress
        )

        if not rgb_result['success']:
            logger.warning(f"RGB extraction failed: {rgb_result.get('error')}")
            # Don't fail the task, just proceed without RGB
        else:
            logger.info(f"✓ RGB extracted")
            result['rgb_file'] = rgb_result['file']

            # Create RGB pyramids for tile serving (viewport-specific)
            try:
                logger.info(f"Creating RGB pyramids...")

                def pyramid_progress(level: int, message: str, percent: float):
                    """Update task progress for pyramid creation."""
                    progress = 75 + (percent / 100) * 25  # Pyramid creation is final 25%
                    tasks[task_id]['progress'] = progress
                    tasks[task_id]['message'] = message
                    logger.info(f"Task {task_id}: {message} ({progress}%)")

                # Create pyramids in viewport-specific directory
                pyramid_output_dir = output_dir / "pyramids" / str(year)
                pyramid_result = create_rgb_pyramids(
                    rgb_file=Path(rgb_result['file']),
                    output_dir=pyramid_output_dir,
                    source_resolution=1.0,  # RGB from embeddings is at 1m resolution
                    num_levels=5,
                    progress_callback=pyramid_progress,
                    check_cache=True  # Use caching to avoid recreating if unchanged
                )

                if pyramid_result['success']:
                    logger.info(f"✓ RGB pyramids created/cached")
                    result['pyramids'] = pyramid_result['pyramid_info']
                else:
                    logger.warning(f"Pyramid creation failed: {pyramid_result.get('error')}")

            except Exception as e:
                logger.warning(f"Error creating pyramids: {e}")
                # Don't fail the task, pyramids are optional

        tasks[task_id]['state'] = 'complete'
        tasks[task_id]['progress'] = 100.0
        tasks[task_id]['message'] = f"✓ Complete! Embeddings: {result['file']}"
        tasks[task_id]['result'] = result
        logger.info(f"Task {task_id} completed successfully")

    except Exception as e:
        logger.exception(f"Error in download task {task_id}")
        tasks[task_id]['state'] = 'error'
        tasks[task_id]['error'] = str(e)


# ============================================================================
# Helper Functions
# ============================================================================

def find_existing_viewport(bounds: Bounds, tolerance: float = 0.00001) -> Optional[str]:
    """
    Search for existing viewport with matching bounds.

    Args:
        bounds: Bounds to search for
        tolerance: Tolerance in degrees for matching bounds (default ~1 meter)

    Returns:
        viewport_id if found, None otherwise
    """
    if not DATA_DIR.exists():
        return None

    for viewport_dir in DATA_DIR.iterdir():
        if not viewport_dir.is_dir():
            continue

        metadata_file = viewport_dir / "metadata.json"
        if not metadata_file.exists():
            continue

        try:
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)

            existing_bounds = metadata.get('bounds', {})

            # Check if bounds match within tolerance
            if (abs(existing_bounds.get('minLat', -1) - bounds.minLat) < tolerance and
                abs(existing_bounds.get('maxLat', -1) - bounds.maxLat) < tolerance and
                abs(existing_bounds.get('minLon', -1) - bounds.minLon) < tolerance and
                abs(existing_bounds.get('maxLon', -1) - bounds.maxLon) < tolerance):
                logger.info(f"Found existing viewport with matching bounds: {viewport_dir.name}")
                return viewport_dir.name
        except Exception as e:
            logger.warning(f"Error reading metadata from {metadata_file}: {e}")
            continue

    return None


# ============================================================================
# API Endpoints
# ============================================================================

@app.post("/api/save-viewport")
async def save_viewport(request: ViewportSaveRequest):
    """Save viewport to viewport.txt and create viewport-specific directory."""
    try:
        center_lng, center_lat = request.center
        bounds = request.bounds
        size_km = request.sizeKm

        # Check if a viewport with the same bounds already exists
        existing_viewport_id = find_existing_viewport(bounds)
        is_new_viewport = False
        if existing_viewport_id:
            logger.info(f"Using existing viewport: {existing_viewport_id}")
            viewport_id = existing_viewport_id
        else:
            # Generate new viewport ID
            viewport_id = str(uuid.uuid4())
            is_new_viewport = True
            logger.info(f"Created new viewport: {viewport_id}")

        # Create viewport-specific directory (idempotent)
        viewport_dir = DATA_DIR / viewport_id
        viewport_dir.mkdir(parents=True, exist_ok=True)
        if is_new_viewport:
            logger.info(f"Created viewport directory: {viewport_id}")

        # Write viewport.txt (for reference)
        viewport_file = Path(__file__).parent.parent / "viewport.txt"
        content = f"""Viewport Configuration
=====================

Viewport ID: {viewport_id}

Center (degrees):
  Latitude:  {center_lat:.6f}°
  Longitude: {center_lng:.6f}°

Bounds (degrees):
  Min Latitude:  {bounds.minLat:.6f}°
  Max Latitude:  {bounds.maxLat:.6f}°
  Min Longitude: {bounds.minLon:.6f}°
  Max Longitude: {bounds.maxLon:.6f}°

Size: {size_km}km × {size_km}km

Generated: {datetime.utcnow().isoformat()}
"""
        viewport_file.write_text(content)
        logger.info(f"✓ Saved viewport to {viewport_file}")

        # Also save metadata in viewport directory
        metadata_file = viewport_dir / "metadata.json"
        metadata = {
            'viewport_id': viewport_id,
            'center': {'lng': center_lng, 'lat': center_lat},
            'bounds': {
                'minLon': bounds.minLon,
                'maxLon': bounds.maxLon,
                'minLat': bounds.minLat,
                'maxLat': bounds.maxLat
            },
            'size_km': size_km,
            'created_at': datetime.utcnow().isoformat()
        }
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        logger.info(f"✓ Saved viewport metadata to {metadata_file}")

        return {
            "success": True,
            "message": "Viewport saved" if is_new_viewport else "Using existing viewport",
            "viewport_id": viewport_id,
            "viewport_file": str(viewport_file),
            "is_new": is_new_viewport
        }

    except Exception as e:
        logger.exception("Error saving viewport")
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/download-embeddings")
async def download_embeddings_endpoint(
    year: int = 2024,
    viewport_id: Optional[str] = None,
    background_tasks: BackgroundTasks = None
):
    """
    Start background task to download embeddings for viewport in viewport.txt.

    If viewport_id is not provided, uses the last saved viewport from viewport.txt.
    """
    try:
        # Verify viewport.txt exists
        viewport_file = Path(__file__).parent.parent / "viewport.txt"
        if not viewport_file.exists():
            return {
                "success": False,
                "error": "viewport.txt not found. Save a viewport first."
            }

        # If viewport_id not provided, try to extract from viewport.txt
        if not viewport_id:
            try:
                content = viewport_file.read_text()
                import re
                match = re.search(r'Viewport ID:\s*(\S+)', content)
                if match:
                    viewport_id = match.group(1)
            except:
                pass

        # Create task
        task_id = str(uuid.uuid4())
        tasks[task_id] = {
            'state': 'pending',
            'progress': 0.0,
            'message': 'Queued for download',
            'error': None,
            'year': year,
            'viewport_id': viewport_id,
            'created_at': datetime.utcnow().isoformat()
        }

        # Start background task
        background_tasks.add_task(download_embeddings_task, task_id, year, viewport_id)

        logger.info(f"Created download task {task_id} for year {year}, viewport {viewport_id}")
        return {
            "success": True,
            "task_id": task_id,
            "viewport_id": viewport_id,
            "message": f"Download started for year {year}"
        }

    except Exception as e:
        logger.exception("Error starting download task")
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/tasks/{task_id}/status")
async def get_task_status(task_id: str):
    """Get status of a download task."""
    if task_id not in tasks:
        return {
            "task_id": task_id,
            "state": "not_found",
            "progress": 0.0,
            "message": "Task not found"
        }

    task = tasks[task_id]
    return {
        "task_id": task_id,
        "state": task['state'],
        "progress": task['progress'],
        "message": task['message'],
        "error": task.get('error'),
        "result": task.get('result')
    }


@app.get("/api/viewport-info")
async def get_viewport_info():
    """Get info about the current viewport from viewport.txt."""
    try:
        viewport_file = Path(__file__).parent.parent / "viewport.txt"

        if not viewport_file.exists():
            return {
                "exists": False,
                "message": "No viewport saved yet"
            }

        # Read viewport.txt
        import re
        content = viewport_file.read_text()

        # Parse viewport ID
        viewport_id_match = re.search(r'Viewport ID:\s*(\S+)', content)

        # Parse bounds
        min_lat_match = re.search(r'Min Latitude:\s*([-\d.]+)°', content)
        max_lat_match = re.search(r'Max Latitude:\s*([-\d.]+)°', content)
        min_lon_match = re.search(r'Min Longitude:\s*([-\d.]+)°', content)
        max_lon_match = re.search(r'Max Longitude:\s*([-\d.]+)°', content)
        center_lat_match = re.search(r'Latitude:\s*([-\d.]+)°\s*\n\s*Longitude:', content)
        center_lon_match = re.search(r'Longitude:\s*([-\d.]+)°', content)

        if all([min_lat_match, max_lat_match, min_lon_match, max_lon_match]):
            bounds = {
                "minLat": float(min_lat_match.group(1)),
                "maxLat": float(max_lat_match.group(1)),
                "minLon": float(min_lon_match.group(1)),
                "maxLon": float(max_lon_match.group(1))
            }

            center = None
            if center_lat_match and center_lon_match:
                center = [float(center_lon_match.group(1)), float(center_lat_match.group(1))]

            return {
                "exists": True,
                "viewport_id": viewport_id_match.group(1) if viewport_id_match else None,
                "bounds": bounds,
                "center": center
            }
        else:
            return {
                "exists": True,
                "message": "Could not parse viewport.txt"
            }

    except Exception as e:
        logger.exception("Error reading viewport info")
        return {
            "exists": False,
            "error": str(e)
        }


@app.get("/api/embeddings-bounds")
async def get_embeddings_bounds(year: int = 2024):
    """Get the actual georeferenced bounds of the embeddings GeoTIFF."""
    try:
        import rasterio

        embeddings_file = DATA_DIR / f"embeddings_{year}.tif"

        if not embeddings_file.exists():
            return {
                "exists": False,
                "error": f"No embeddings file for year {year}"
            }

        with rasterio.open(embeddings_file) as src:
            bounds = src.bounds
            return {
                "exists": True,
                "year": year,
                "bounds": {
                    "minLon": bounds.left,
                    "minLat": bounds.bottom,
                    "maxLon": bounds.right,
                    "maxLat": bounds.top
                },
                "crs": str(src.crs),
                "width": src.width,
                "height": src.height,
                "bands": src.count
            }

    except Exception as e:
        logger.exception(f"Error reading embeddings bounds")
        return {
            "exists": False,
            "error": str(e)
        }


@app.get("/api/embeddings-tile/{z}/{x}/{y}")
async def get_embeddings_tile(z: int, x: int, y: int, year: int = 2024):
    """
    Serve GeoTIFF as web map tiles (XYZ format).
    This provides optimal resolution at any zoom level.
    """
    try:
        import rasterio
        from rasterio.windows import from_bounds
        import numpy as np
        from PIL import Image
        import io

        embeddings_file = DATA_DIR / f"embeddings_{year}.tif"
        if not embeddings_file.exists():
            return {"error": "Embeddings file not found"}, 404

        # Web Mercator tile calculations
        n = 2.0 ** z
        lon_min = (x / n) * 360.0 - 180.0
        lon_max = ((x + 1) / n) * 360.0 - 180.0
        lat_max = 85.051129  # Web Mercator limit
        lat_min = -85.051129

        # Inverse Mercator for latitude
        import math
        y_min = math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n)))
        y_max = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
        lat_min = math.degrees(y_min)
        lat_max = math.degrees(y_max)

        with rasterio.open(embeddings_file) as src:
            # Read the tile bounds from the GeoTIFF
            window = from_bounds(lon_min, lat_min, lon_max, lat_max, src.transform)

            # Ensure window is within bounds
            window = window.intersection(rasterio.windows.Window(0, 0, src.width, src.height))

            if window.width <= 0 or window.height <= 0:
                # Empty tile
                img = Image.new('RGB', (256, 256), color=(0, 0, 0))
                buf = io.BytesIO()
                img.save(buf, format='PNG')
                buf.seek(0)
                return buf.getvalue(), 200, {'Content-Type': 'image/png'}

            # Read RGB channels (first 3 bands)
            try:
                rgb_data = src.read([1, 2, 3], window=window)
            except:
                # If less than 3 bands, read what's available
                rgb_data = []
                for band in [1, 2, 3]:
                    try:
                        rgb_data.append(src.read(band, window=window))
                    except:
                        rgb_data.append(np.zeros((int(window.height), int(window.width)), dtype=np.uint8))
                rgb_data = np.array(rgb_data)

            # Normalize to 0-255 if needed
            if rgb_data.dtype != np.uint8:
                rgb_data = np.clip(rgb_data * 255, 0, 255).astype(np.uint8)

            # Resample to 256×256 tile
            from PIL import Image as PILImage
            height, width = rgb_data.shape[1], rgb_data.shape[2]

            # Create RGB image
            img_array = np.zeros((height, width, 3), dtype=np.uint8)
            for i in range(3):
                img_array[:, :, i] = rgb_data[i]

            img = PILImage.fromarray(img_array, 'RGB')
            img = img.resize((256, 256), PILImage.LANCZOS)

            # Save to bytes
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)

            return buf.getvalue(), 200, {'Content-Type': 'image/png'}

    except Exception as e:
        logger.exception(f"Error generating tile {z}/{x}/{y}")
        return {"error": str(e)}, 500


# Mount static files
public_dir = Path(__file__).parent.parent / "public"
if public_dir.exists():
    app.mount("/", StaticFiles(directory=public_dir, html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
