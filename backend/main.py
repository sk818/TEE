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
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://localhost:8080"],
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
    years: list[int] = [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024]


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

        # Step 1: Download embeddings
        update_task_status(task_id, 'downloading', 0, 'Preparing to download TESSERA embeddings from geotessera...')

        from backend.processing.download_viewport_embeddings import download_embeddings_for_viewport

        bounds_tuple = (
            bounds_dict['minLon'],
            bounds_dict['minLat'],
            bounds_dict['maxLon'],
            bounds_dict['maxLat']
        )

        def download_progress(year, status, percent):
            # Update progress for downloading phase (0-50%)
            overall_progress = (percent / 100) * 50
            if status == 'complete':
                update_task_status(task_id, 'downloading', overall_progress, f'✓ Completed year {year}')
            else:
                update_task_status(task_id, 'downloading', overall_progress, f'Downloading embeddings for year {year}... (this may take several minutes)')

        logger.info(f"Downloading embeddings for bounds {bounds_tuple}")
        embeddings_metadata = download_embeddings_for_viewport(
            bounds=bounds_tuple,
            years=years,
            output_dir=viewport_dir / "raw",
            progress_callback=download_progress
        )

        # Step 2: Create pyramids
        update_task_status(task_id, 'creating_pyramids', 50, 'Creating multi-resolution pyramids...')

        from backend.processing.create_viewport_pyramids import create_pyramids_for_viewport

        def pyramid_progress(year, level, status, percent):
            # Update progress for pyramid creation (50-100%)
            overall_progress = 50 + (percent / 100) * 50
            update_task_status(task_id, 'creating_pyramids', overall_progress, f'Creating pyramids for year {year}, level {level}...')

        logger.info(f"Creating pyramids from embeddings")
        create_pyramids_for_viewport(
            embeddings_dir=viewport_dir / "raw",
            pyramids_dir=pyramids_dir,
            years=years,
            progress_callback=pyramid_progress
        )

        # Step 3: Save metadata
        metadata = ViewportMetadata(
            viewport_id=viewport_id,
            bounds=bounds_dict,
            center=center,
            years=years,
            pyramid_levels=6,
            processed_date=datetime.utcnow().isoformat(),
            status='complete'
        )

        metadata_file = viewport_dir / "metadata.json"
        with open(metadata_file, 'w') as f:
            import json
            json.dump(metadata.model_dump(), f, indent=2)

        logger.info(f"Completed processing for viewport {viewport_id}")
        update_task_status(task_id, 'complete', 100, 'Processing complete!')

    except Exception as e:
        logger.exception(f"Error processing viewport {viewport_id}")
        set_task_error(task_id, str(e))


# ============================================================================
# API Routes
# ============================================================================

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
