#!/usr/bin/env python3
"""
FastAPI backend for TESSERA Embedding Explorer.

Handles viewport-based embedding download and pyramid creation.
"""

import logging
import os
from pathlib import Path
from typing import Optional
import uuid
from datetime import datetime

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="TESSERA Embedding Explorer API",
    description="Backend for viewport-based TESSERA embedding download and visualization",
    version="1.0.0"
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

# Task storage (in-memory, can be replaced with database)
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


class ViewportProcessRequest(BaseModel):
    """Request to process a viewport."""
    bounds: Bounds
    center: list[float]
    sizeKm: float
    years: list[int] = [2024]


class DownloadAdditionalYearsRequest(BaseModel):
    """Request to download additional years for an existing viewport."""
    years: list[int]


class TaskStatus(BaseModel):
    """Task status response."""
    task_id: str
    viewport_id: Optional[str] = None
    state: str  # 'pending', 'downloading', 'creating_pyramids', 'complete', 'error'
    progress: float = 0.0
    message: str = ""
    error: Optional[str] = None


class ViewportMetadata(BaseModel):
    """Metadata about a processed viewport."""
    viewport_id: str
    bounds: Bounds
    center: list[float]
    years: list[int]
    pyramid_levels: int = 6
    width: int = 4408  # Default width of pyramid level 0
    height: int = 4408  # Default height of pyramid level 0
    bands: int = 3  # Number of bands in GeoTIFF (RGB)
    processed_date: str
    status: str


# ============================================================================
# Helper Functions
# ============================================================================

def create_task(bounds: Bounds, center: list[float], years: list[int]) -> tuple[str, str]:
    """Create a new processing task and return task_id and viewport_id."""
    task_id = str(uuid.uuid4())
    viewport_id = str(uuid.uuid4())

    tasks[task_id] = {
        'viewport_id': viewport_id,
        'state': 'pending',
        'progress': 0.0,
        'message': 'Queued for processing',
        'error': None,
        'bounds': bounds.model_dump(),
        'center': center,
        'years': years,
        'created_at': datetime.utcnow().isoformat()
    }

    logger.info(f"Created task {task_id} for viewport {viewport_id}")
    return task_id, viewport_id


def update_task_status(task_id: str, state: str, progress: float = None, message: str = None):
    """Update task status."""
    if task_id not in tasks:
        logger.warning(f"Task {task_id} not found")
        return

    if progress is not None:
        tasks[task_id]['progress'] = progress
    if message is not None:
        tasks[task_id]['message'] = message

    tasks[task_id]['state'] = state
    logger.info(f"Task {task_id} updated: {state} ({progress if progress else tasks[task_id].get('progress', 0)}%)")


def set_task_error(task_id: str, error: str):
    """Set task error state."""
    if task_id not in tasks:
        return

    tasks[task_id]['state'] = 'error'
    tasks[task_id]['error'] = error
    logger.error(f"Task {task_id} error: {error}")


# ============================================================================
# Background Processing
# ============================================================================

def process_additional_years_task(task_id: str, viewport_id: str):
    """Background task to download and process additional years for existing viewport."""
    if task_id not in tasks:
        logger.error(f"Task {task_id} not found")
        return

    task = tasks[task_id]
    years = task['years']
    viewport_dir = DATA_DIR / viewport_id

    try:
        logger.info(f"Starting additional years download for viewport {viewport_id}")

        # Load existing metadata
        metadata_file = viewport_dir / "metadata.json"
        if not metadata_file.exists():
            raise RuntimeError(f"Viewport {viewport_id} not found")

        import json
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)

        existing_years = set(metadata.get('years', []))
        new_years = [y for y in years if y not in existing_years]

        if not new_years:
            logger.info(f"All requested years already downloaded for viewport {viewport_id}")
            update_task_status(task_id, 'complete', 100, 'All requested years already available')
            return

        # Step 1: Download embeddings for new years
        update_task_status(task_id, 'downloading', 0, f'Downloading {len(new_years)} additional years...')

        from backend.processing.download_viewport_embeddings import download_embeddings_for_viewport

        bounds_dict = metadata['bounds']
        bounds_tuple = (
            bounds_dict['minLon'],
            bounds_dict['minLat'],
            bounds_dict['maxLon'],
            bounds_dict['maxLat']
        )

        def download_progress(year, status, percent):
            overall_progress = (percent / 100) * 50
            if status == 'initializing':
                update_task_status(task_id, 'downloading', overall_progress, 'Initializing GeoTessera (checking registries, loading tile metadata)...')
            elif status == 'ready':
                update_task_status(task_id, 'downloading', overall_progress, f'Ready to download {len(new_years)} additional year(s)...')
            elif status == 'complete':
                update_task_status(task_id, 'downloading', overall_progress, f'✓ Completed year {year}')
            else:
                update_task_status(task_id, 'downloading', overall_progress, f'Downloading year {year}... (this may take several minutes)')

        logger.info(f"Downloading additional years: {new_years}")
        embeddings_metadata = download_embeddings_for_viewport(
            bounds=bounds_tuple,
            years=new_years,
            output_dir=viewport_dir / "raw",
            progress_callback=download_progress
        )

        # Step 2: Create pyramids for new years
        update_task_status(task_id, 'creating_pyramids', 50, 'Creating pyramids for additional years...')

        from backend.processing.create_viewport_pyramids import create_pyramids_for_viewport

        def pyramid_progress(year, level, status, percent):
            overall_progress = 50 + (percent / 100) * 35
            update_task_status(task_id, 'creating_pyramids', overall_progress, f'Creating pyramids for year {year}, level {level}...')

        logger.info(f"Creating pyramids for additional years")
        pyramid_info = create_pyramids_for_viewport(
            embeddings_dir=viewport_dir / "raw",
            pyramids_dir=viewport_dir / "pyramids",
            years=new_years,
            progress_callback=pyramid_progress
        )

        # Step 2.5: Create coarsened embeddings for new years
        update_task_status(task_id, 'creating_pyramids', 85, 'Creating coarsened embeddings for additional years...')

        from backend.processing.create_coarsened_embedding_pyramids import create_coarsened_pyramids

        def coarsening_progress(year, level, status, percent):
            overall_progress = 85 + (percent / 100) * 15
            update_task_status(task_id, 'creating_pyramids', overall_progress, f'Coarsening embeddings for year {year}, level {level}...')

        logger.info(f"Creating coarsened embeddings for additional years")
        coarsening_info = create_coarsened_pyramids(
            raw_embeddings_dir=viewport_dir / "raw",
            coarsened_dir=viewport_dir / "coarsened",
            years=new_years,
            progress_callback=coarsening_progress
        )

        # Step 3: Update metadata with new years
        metadata['years'] = sorted(list(set(metadata['years']) | set(new_years)))
        # Update dimensions if they were captured
        if 'width' not in metadata:
            metadata['width'] = pyramid_info.get('width', 4408)
        if 'height' not in metadata:
            metadata['height'] = pyramid_info.get('height', 4408)
        if 'bands' not in metadata:
            metadata['bands'] = pyramid_info.get('bands', 3)
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"Completed downloading additional years for viewport {viewport_id}")
        update_task_status(task_id, 'complete', 100, 'Additional years processed!')

    except Exception as e:
        logger.exception(f"Error processing additional years for viewport {viewport_id}")
        set_task_error(task_id, str(e))


def process_viewport_task(task_id: str):
    """Background task to process viewport embeddings and create pyramids."""
    if task_id not in tasks:
        logger.error(f"Task {task_id} not found")
        return

    task = tasks[task_id]
    viewport_id = task['viewport_id']
    bounds_dict = task['bounds']
    center = task['center']
    years = task['years']

    try:
        logger.info(f"Starting processing for viewport {viewport_id}")

        # Create viewport directory
        viewport_dir = DATA_DIR / viewport_id
        viewport_dir.mkdir(parents=True, exist_ok=True)
        pyramids_dir = viewport_dir / "pyramids"
        pyramids_dir.mkdir(parents=True, exist_ok=True)
        sentinel2_dir = viewport_dir / "sentinel2"
        sentinel2_dir.mkdir(parents=True, exist_ok=True)

        bounds_tuple = (
            bounds_dict['minLon'],
            bounds_dict['minLat'],
            bounds_dict['maxLon'],
            bounds_dict['maxLat']
        )

        # Step 1: Download embeddings
        update_task_status(task_id, 'downloading', 0, 'Preparing to download TESSERA embeddings from geotessera...')

        from backend.processing.download_viewport_embeddings import download_embeddings_for_viewport

        def download_progress(year, status, percent):
            # Update progress for downloading phase (0-33%)
            overall_progress = (percent / 100) * 33
            if status == 'initializing':
                update_task_status(task_id, 'downloading', overall_progress, 'Initializing GeoTessera (checking registries, loading tile metadata)...')
            elif status == 'ready':
                update_task_status(task_id, 'downloading', overall_progress, 'Ready to download. Starting year-by-year download...')
            elif status == 'complete':
                update_task_status(task_id, 'downloading', overall_progress, f'✓ Completed embeddings year {year}')
            else:
                update_task_status(task_id, 'downloading', overall_progress, f'Downloading embeddings for year {year}... (this may take several minutes)')

        logger.info(f"Downloading embeddings for bounds {bounds_tuple}")
        embeddings_metadata = download_embeddings_for_viewport(
            bounds=bounds_tuple,
            years=years,
            output_dir=viewport_dir / "raw",
            progress_callback=download_progress
        )

        # Step 1.5: Download Sentinel-2 RGB imagery
        update_task_status(task_id, 'downloading', 33, 'Downloading Sentinel-2 RGB satellite imagery...')

        from backend.processing.download_sentinel2 import download_sentinel2_rgb

        sentinel2_metadata = {}
        for year in years:
            try:
                update_task_status(task_id, 'downloading', 33 + (years.index(year) / len(years)) * 33, f'Downloading Sentinel-2 for year {year}...')

                # Save as {year}_rgb.tif to match tile serving endpoint expectations
                sentinel2_path = sentinel2_dir / f"{year}_rgb.tif"

                def s2_progress(status, percent):
                    year_progress = 33 + (years.index(year) / len(years)) * 33
                    overall_progress = year_progress + (percent / 100) * (33 / len(years))
                    update_task_status(task_id, 'downloading', overall_progress, f'Sentinel-2 {year} ({status})...')

                logger.info(f"Downloading Sentinel-2 for year {year}")
                result_path = download_sentinel2_rgb(
                    bounds=bounds_tuple,
                    year=year,
                    output_file=sentinel2_path,
                    progress_callback=s2_progress
                )
                sentinel2_metadata[year] = str(result_path)
                logger.info(f"✓ Sentinel-2 saved to {result_path}")

            except Exception as e:
                logger.warning(f"Failed to download Sentinel-2 for year {year}: {e}")
                sentinel2_metadata[year] = None

        # Step 2: Create pyramids from embeddings and Sentinel-2
        update_task_status(task_id, 'creating_pyramids', 66, 'Creating multi-resolution pyramids from embeddings and Sentinel-2...')

        from backend.processing.create_viewport_pyramids import create_pyramids_for_viewport

        def pyramid_progress(year, level, status, percent):
            # Update progress for pyramid creation (66-100%)
            overall_progress = 66 + (percent / 100) * 34
            update_task_status(task_id, 'creating_pyramids', overall_progress, f'Creating pyramids for year {year}, level {level}...')

        logger.info(f"Creating pyramids from embeddings")
        pyramid_info = create_pyramids_for_viewport(
            embeddings_dir=viewport_dir / "raw",
            pyramids_dir=pyramids_dir,
            years=years,
            progress_callback=pyramid_progress
        )

        # Step 2.5: Create coarsened embedding pyramids
        update_task_status(task_id, 'creating_pyramids', 80, 'Creating coarsened embedding pyramids for zoom-aware similarity...')

        from backend.processing.create_coarsened_embedding_pyramids import create_coarsened_pyramids

        def coarsening_progress(year, level, status, percent):
            # Update progress for coarsening (80-100%)
            overall_progress = 80 + (percent / 100) * 20
            update_task_status(task_id, 'creating_pyramids', overall_progress, f'Coarsening embeddings for year {year}, level {level}...')

        coarsened_dir = viewport_dir / "coarsened"
        coarsened_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Creating coarsened embedding pyramids")
        coarsening_info = create_coarsened_pyramids(
            raw_embeddings_dir=viewport_dir / "raw",
            coarsened_dir=coarsened_dir,
            years=years,
            progress_callback=coarsening_progress
        )

        # Step 3: Save metadata
        metadata = ViewportMetadata(
            viewport_id=viewport_id,
            bounds=bounds_dict,
            center=center,
            years=years,
            pyramid_levels=6,
            width=pyramid_info.get('width', 4408),
            height=pyramid_info.get('height', 4408),
            bands=pyramid_info.get('bands', 3),
            processed_date=datetime.utcnow().isoformat(),
            status='complete'
        )

        metadata_file = viewport_dir / "metadata.json"
        with open(metadata_file, 'w') as f:
            import json
            metadata_dict = metadata.model_dump()
            metadata_dict['sentinel2_files'] = sentinel2_metadata
            json.dump(metadata_dict, f, indent=2)

        logger.info(f"Completed processing for viewport {viewport_id}")
        update_task_status(task_id, 'complete', 100, 'Processing complete!')

    except Exception as e:
        logger.exception(f"Error processing viewport {viewport_id}")
        set_task_error(task_id, str(e))


# ============================================================================
# API Routes
# ============================================================================

@app.get("/api/viewports/find-by-bounds")
async def find_viewport_by_bounds(minLon: float, minLat: float, maxLon: float, maxLat: float):
    """Find existing viewport for given bounds (within tolerance)."""
    tolerance = 0.001  # ~100 meters tolerance for duplicate detection

    try:
        import json

        # Search through existing viewports
        for viewport_dir in DATA_DIR.iterdir():
            if not viewport_dir.is_dir():
                continue

            metadata_file = viewport_dir / "metadata.json"
            if not metadata_file.exists():
                continue

            with open(metadata_file, 'r') as f:
                metadata = json.load(f)

            # Check if bounds match within tolerance
            vp_bounds = metadata.get('bounds', {})
            if (abs(vp_bounds.get('minLon', 0) - minLon) < tolerance and
                abs(vp_bounds.get('minLat', 0) - minLat) < tolerance and
                abs(vp_bounds.get('maxLon', 0) - maxLon) < tolerance and
                abs(vp_bounds.get('maxLat', 0) - maxLat) < tolerance and
                metadata.get('status') == 'complete'):

                logger.info(f"Found existing viewport {viewport_dir.name} for bounds")
                return {
                    "viewport_id": metadata['viewport_id'],
                    "found": True,
                    "years": metadata.get('years', [])
                }

        return {"found": False}

    except Exception as e:
        logger.exception("Error searching for viewport by bounds")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/viewports/process")
async def start_viewport_processing(request: ViewportProcessRequest, background_tasks: BackgroundTasks):
    """Start processing a viewport."""
    try:
        logger.info(f"Processing request for bounds {request.bounds}")

        # Create task
        task_id, viewport_id = create_task(request.bounds, request.center, request.years)

        # Add background task
        background_tasks.add_task(process_viewport_task, task_id)

        return {"task_id": task_id, "viewport_id": viewport_id}

    except Exception as e:
        logger.exception("Error starting viewport processing")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/viewports/{task_id}/status")
async def get_task_status(task_id: str):
    """Get task status."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = tasks[task_id]
    return TaskStatus(
        task_id=task_id,
        viewport_id=task.get('viewport_id'),
        state=task['state'],
        progress=task['progress'],
        message=task['message'],
        error=task.get('error')
    )


@app.get("/api/viewports/{viewport_id}/metadata")
async def get_viewport_metadata(viewport_id: str):
    """Get viewport metadata."""
    metadata_file = DATA_DIR / viewport_id / "metadata.json"

    if not metadata_file.exists():
        raise HTTPException(status_code=404, detail="Viewport not found")

    import json
    with open(metadata_file, 'r') as f:
        metadata = json.load(f)

    return metadata


@app.get("/api/viewports/{viewport_id}/pyramid/{year}/level_{level}.tif")
async def get_pyramid_tif(viewport_id: str, year: int, level: int):
    """Serve pyramid GeoTIFF file."""
    tif_file = DATA_DIR / viewport_id / "pyramids" / str(year) / f"level_{level}.tif"

    if not tif_file.exists():
        logger.warning(f"TIF file not found: {tif_file}")
        raise HTTPException(status_code=404, detail="Pyramid level not found")

    return FileResponse(
        path=tif_file,
        media_type="image/tiff",
        headers={"Content-Disposition": f"attachment; filename=level_{level}.tif"}
    )


@app.get("/api/viewports/{viewport_id}/embeddings/{year}.npy")
async def get_embeddings_npy(viewport_id: str, year: int):
    """Serve raw embeddings as NPY file for similarity computation."""
    npy_file = DATA_DIR / viewport_id / "raw" / f"embeddings_{year}.npy"

    if not npy_file.exists():
        logger.warning(f"NPY file not found: {npy_file}")
        raise HTTPException(status_code=404, detail="Embeddings not found")

    return FileResponse(
        path=npy_file,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename=embeddings_{year}.npy"}
    )


@app.get("/api/viewports/{viewport_id}/coarsened-embeddings/{year}/level_{level}.npy")
async def get_coarsened_embeddings_npy(viewport_id: str, year: int, level: int):
    """Serve coarsened embeddings for zoom-aware similarity computation."""
    npy_file = DATA_DIR / viewport_id / "coarsened" / str(year) / f"level_{level}.npy"

    if not npy_file.exists():
        logger.warning(f"Coarsened embeddings file not found: {npy_file}")
        raise HTTPException(status_code=404, detail="Coarsened embeddings not found")

    return FileResponse(
        path=npy_file,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename=level_{level}.npy"}
    )


@app.post("/api/viewports/{viewport_id}/download-years")
async def start_additional_years_download(viewport_id: str, request: DownloadAdditionalYearsRequest, background_tasks: BackgroundTasks):
    """Start downloading and processing additional years for an existing viewport."""
    try:
        logger.info(f"Additional years download request for viewport {viewport_id}: {request.years}")

        # Verify viewport exists
        metadata_file = DATA_DIR / viewport_id / "metadata.json"
        if not metadata_file.exists():
            raise HTTPException(status_code=404, detail="Viewport not found")

        # Create task
        task_id = str(uuid.uuid4())
        tasks[task_id] = {
            'viewport_id': viewport_id,
            'state': 'pending',
            'progress': 0.0,
            'message': 'Queued for processing',
            'error': None,
            'years': request.years,
            'created_at': datetime.utcnow().isoformat()
        }

        logger.info(f"Created additional years task {task_id} for viewport {viewport_id}")

        # Add background task
        background_tasks.add_task(process_additional_years_task, task_id, viewport_id)

        return {"task_id": task_id, "viewport_id": viewport_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error starting additional years download")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/viewports/{viewport_id}/download-years/{task_id}/status")
async def get_additional_years_status(viewport_id: str, task_id: str):
    """Get status of additional years download task."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = tasks[task_id]

    # Verify this task belongs to the requested viewport
    if task.get('viewport_id') != viewport_id:
        raise HTTPException(status_code=404, detail="Task not found for this viewport")

    return TaskStatus(
        task_id=task_id,
        viewport_id=task.get('viewport_id'),
        state=task['state'],
        progress=task['progress'],
        message=task['message'],
        error=task.get('error')
    )


# ============================================================================
# Tile Serving Routes (for three-pane viewer)
# ============================================================================

def zoom_to_pyramid_level(z: int, max_pyramid_level: int = 5) -> int:
    """Map Leaflet zoom level to pyramid level."""
    # Account for zoomOffset: -3 on custom tiles
    # Frontend requests z-3, so we need to add 3 back for proper level mapping
    z_adjusted = z + 3
    pyramid_level = (18 - z_adjusted) // 2
    return max(0, min(max_pyramid_level, pyramid_level))


def tile_to_bbox(x: int, y: int, z: int) -> tuple:
    """Convert tile coordinates to bounding box in EPSG:4326."""
    import math

    # Account for zoomOffset: -3 on custom tiles
    # Frontend requests z-3, so we need to add 3 back for proper bbox calculation
    z_adjusted = z + 3

    n = 2.0 ** z_adjusted
    lon_min = x / n * 360.0 - 180.0
    lon_max = (x + 1) / n * 360.0 - 180.0

    lat_max_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat_min_rad = math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n)))

    lat_max = math.degrees(lat_max_rad)
    lat_min = math.degrees(lat_min_rad)

    return (lon_min, lat_min, lon_max, lat_max)


def get_rgb_tile(tif_path: Path, bbox: tuple, tile_size: int = 2048):
    """Extract a tile from a GeoTIFF and return as PIL Image."""
    try:
        from rio_tiler.io import Reader
        from PIL import Image
        import numpy as np

        with Reader(str(tif_path)) as src:
            # Read tile from GeoTIFF
            img_data = src.part(bbox, width=tile_size, height=tile_size)
            data = img_data.data

            # Handle different band counts
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
                if rgb_t.max() > 255:
                    rgb_t = (rgb_t / rgb_t.max() * 255).astype(np.uint8)
                else:
                    rgb_t = rgb_t.astype(np.uint8)

            # Create PIL image
            img = Image.fromarray(rgb_t, mode='RGB')
            return img

    except ImportError:
        logger.warning("rio_tiler not installed, tile serving unavailable")
        return None


@app.get("/api/tiles/sentinel2/{viewport_id}/{year}/{z}/{x}/{y}.png")
async def get_sentinel2_tile(viewport_id: str, year: int, z: int, x: int, y: int):
    """Serve Sentinel-2 RGB tile."""
    import io
    from PIL import Image

    try:
        tif_path = DATA_DIR / viewport_id / "sentinel2" / f"{year}_rgb.tif"

        if not tif_path.exists():
            # Return transparent tile if file doesn't exist
            from fastapi.responses import StreamingResponse
            img = Image.new('RGBA', (2048, 2048), (0, 0, 0, 0))
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)
            return StreamingResponse(iter([buf.getvalue()]), media_type="image/png")

        # Get tile bounds
        bbox = tile_to_bbox(x, y, z)

        try:
            img = get_rgb_tile(tif_path, bbox)

            if img is None:
                # rio_tiler not available
                raise HTTPException(status_code=500, detail="Tile server not available")

            # Save to buffer
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)

            from fastapi.responses import StreamingResponse

            return StreamingResponse(iter([buf.getvalue()]), media_type="image/png")

        except Exception as e:
            logger.warning(f"Error reading Sentinel-2 tile {viewport_id}/{year}/{z}/{x}/{y}: {e}")
            # Return transparent tile on error
            img = Image.new('RGBA', (2048, 2048), (0, 0, 0, 0))
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)

            from fastapi.responses import StreamingResponse

            return StreamingResponse(iter([buf.getvalue()]), media_type="image/png")

    except Exception as e:
        logger.error(f"Error serving Sentinel-2 tile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tiles/embeddings/{viewport_id}/{year}/{z}/{x}/{y}.png")
async def get_embeddings_tile(viewport_id: str, year: int, z: int, x: int, y: int):
    """Serve embeddings visualization tile (RGB pyramids)."""
    import io
    from PIL import Image

    try:
        # Map zoom level to pyramid level
        pyramid_level = zoom_to_pyramid_level(z)

        # Get pyramid level file
        tif_path = DATA_DIR / viewport_id / "pyramids" / str(year) / f"level_{pyramid_level}.tif"

        if not tif_path.exists():
            # Return transparent tile if file doesn't exist
            img = Image.new('RGBA', (2048, 2048), (0, 0, 0, 0))
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)

            from fastapi.responses import StreamingResponse

            return StreamingResponse(iter([buf.getvalue()]), media_type="image/png")

        # Get tile bounds
        bbox = tile_to_bbox(x, y, z)

        try:
            img = get_rgb_tile(tif_path, bbox)

            if img is None:
                # rio_tiler not available
                raise HTTPException(status_code=500, detail="Tile server not available")

            # Save to buffer
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)

            from fastapi.responses import StreamingResponse

            logger.debug(f"Served embeddings tile {viewport_id}/{year}/level_{pyramid_level}/{z}/{x}/{y}")

            return StreamingResponse(iter([buf.getvalue()]), media_type="image/png")

        except Exception as e:
            logger.warning(f"Error reading embeddings tile {viewport_id}/{year}/level_{pyramid_level}/{z}/{x}/{y}: {e}")
            # Return transparent tile on error
            img = Image.new('RGBA', (2048, 2048), (0, 0, 0, 0))
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)

            from fastapi.responses import StreamingResponse

            return StreamingResponse(iter([buf.getvalue()]), media_type="image/png")

    except Exception as e:
        logger.error(f"Error serving embeddings tile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tiles/bounds/{viewport_id}")
async def get_tile_bounds(viewport_id: str):
    """Get bounds and center for a viewport."""
    import json

    try:
        metadata_file = DATA_DIR / viewport_id / "metadata.json"

        if not metadata_file.exists():
            raise HTTPException(status_code=404, detail="Viewport not found")

        with open(metadata_file, 'r') as f:
            metadata = json.load(f)

        return {
            'bounds': metadata.get('bounds', {}),
            'center': metadata.get('center', [0, 0]),
            'years': metadata.get('years', [])
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting bounds for {viewport_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/save-viewport")
async def save_viewport(request: dict):
    """Save the selected viewport to viewport.txt."""
    try:
        center = request.get('center', [0, 0])
        bounds = request.get('bounds', {})
        sizeKm = request.get('sizeKm', 20)

        # Create viewport.txt content
        viewport_content = f"""Viewport Configuration
=====================

Center (degrees):
  Latitude:  {center[1]:.6f}°
  Longitude: {center[0]:.6f}°

Bounds (degrees):
  Min Latitude:  {bounds.get('minLat', 0):.6f}°
  Max Latitude:  {bounds.get('maxLat', 0):.6f}°
  Min Longitude: {bounds.get('minLon', 0):.6f}°
  Max Longitude: {bounds.get('maxLon', 0):.6f}°

Size: {sizeKm}km × {sizeKm}km

Generated: {datetime.now().isoformat()}
"""

        # Save to file in the project root
        viewport_file = Path(__file__).parent.parent / "viewport.txt"
        viewport_file.write_text(viewport_content)

        logger.info(f"Viewport saved to {viewport_file}")
        return {
            "status": "success",
            "message": "Viewport saved to viewport.txt",
            "file": str(viewport_file),
            "center": center,
            "bounds": bounds
        }

    except Exception as e:
        logger.error(f"Error saving viewport: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "TESSERA Embedding Explorer API",
        "docs": "/docs"
    }


# ============================================================================
# Static Files
# ============================================================================

# Mount the public directory for serving GeoTIFFs
try:
    public_path = Path(__file__).parent.parent / "public"
    if public_path.exists():
        app.mount("/data", StaticFiles(directory=str(public_path / "data")), name="data")
        logger.info(f"Mounted static files from {public_path}")
except Exception as e:
    logger.warning(f"Could not mount static files: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
