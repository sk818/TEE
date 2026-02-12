#!/usr/bin/env python3
"""
Simple Flask web server for viewport management.
Exposes viewport operations as HTTP endpoints.
"""

import sys
import os
import re
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
import time
import json
import numpy as np
import subprocess
from datetime import datetime
import faiss

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.viewport_utils import (
    get_active_viewport,
    get_active_viewport_name,
    list_viewports,
    read_viewport_file,
    validate_viewport_name
)
from lib.viewport_writer import set_active_viewport, clear_active_viewport, create_viewport_from_bounds
from lib.pipeline import PipelineRunner, cancel_pipeline
from lib.config import DATA_DIR, MOSAICS_DIR, PYRAMIDS_DIR, FAISS_DIR, VIEWPORTS_DIR, ensure_dirs
from backend.labels_db import (
    init_db as init_labels_db,
    get_labels,
    save_label,
    delete_label,
    delete_viewport_labels,
    get_label_count
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder=str(Path(__file__).parent.parent / 'public'))
CORS(app)

# Data directories (from lib.config, configurable via env vars)
FAISS_INDICES_DIR = FAISS_DIR  # Alias for compatibility

# Task tracking for downloads
tasks = {}
tasks_lock = threading.Lock()

# Get venv Python path for subprocess calls
PROJECT_ROOT = Path(__file__).parent.parent
VENV_PYTHON = PROJECT_ROOT / "venv" / "bin" / "python3"
if not VENV_PYTHON.exists():
    VENV_PYTHON = sys.executable  # Fallback to current Python if venv doesn't exist
logger.info(f"Using Python: {VENV_PYTHON}")

# ============================================================================
# HELPER FUNCTIONS FOR DATA PREPARATION
# ============================================================================

def run_script(script_name, *args, timeout=1800):
    """Run a Python script using the venv Python interpreter."""
    cmd = [str(VENV_PYTHON), str(PROJECT_ROOT / script_name)] + list(args)
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        logger.error(f"Script {script_name} failed with code {result.returncode}: {result.stderr[:500]}")
    return result

def wait_for_file(file_path, min_size_bytes=1024, max_retries=30, retry_interval=1.0):
    """
    Wait for a file to exist and reach minimum size (indicates write completion).

    Args:
        file_path: Path to file to wait for
        min_size_bytes: Minimum file size indicating complete write (default 1KB)
        max_retries: Maximum number of retry attempts
        retry_interval: Seconds to wait between retries

    Returns:
        True if file exists and meets size requirement, False if timeout
    """
    file_path = Path(file_path)
    for attempt in range(max_retries):
        if file_path.exists():
            try:
                file_size = file_path.stat().st_size
                if file_size >= min_size_bytes:
                    logger.info(f"[WAIT] File ready after {attempt} retries: {file_path.name} ({file_size / (1024*1024):.1f} MB)")
                    return True
                else:
                    logger.debug(f"[WAIT] File exists but too small ({file_size} bytes), retrying...")
            except OSError as e:
                logger.debug(f"[WAIT] Could not stat file: {e}, retrying...")

        if attempt < max_retries - 1:
            time.sleep(retry_interval)

    logger.error(f"[WAIT] Timeout waiting for file: {file_path}")
    return False

def check_viewport_mosaics_exist(viewport_name):
    """Check if embeddings mosaic exists for a viewport (checks for ANY year available).
    DEPRECATED: Use check_viewport_faiss_exist() instead - mosaics are deleted after FAISS creation.
    """
    if not MOSAICS_DIR.exists():
        return False
    # Check if any embeddings file exists for this viewport
    embeddings_files = list(MOSAICS_DIR.glob(f"{viewport_name}_embeddings_*.tif"))
    return len(embeddings_files) > 0

def check_viewport_faiss_exist(viewport_name):
    """Check if FAISS index exists for a viewport (checks for ANY year available)."""
    viewport_faiss_dir = FAISS_INDICES_DIR / viewport_name
    if not viewport_faiss_dir.exists():
        return False
    # Check if any year directory has embeddings.index
    for year_dir in viewport_faiss_dir.iterdir():
        if year_dir.is_dir():
            index_file = year_dir / "embeddings.index"
            if index_file.exists():
                return True
    return False

# Cache for FAISS pixel lookup (viewport_name, year) -> {(x,y): index}
_faiss_pixel_cache = {}
_faiss_data_cache = {}  # (viewport_name, year) -> {'embeddings': np.array, 'coords': np.array, 'metadata': dict}

def get_faiss_data(viewport_name, year):
    """Load and cache FAISS data (embeddings, coords, metadata) for a viewport/year."""
    cache_key = (viewport_name, year)

    if cache_key in _faiss_data_cache:
        return _faiss_data_cache[cache_key]

    faiss_dir = FAISS_INDICES_DIR / viewport_name / str(year)

    embeddings_file = faiss_dir / "all_embeddings.npy"
    coords_file = faiss_dir / "pixel_coords.npy"
    metadata_file = faiss_dir / "metadata.json"

    if not all(f.exists() for f in [embeddings_file, coords_file, metadata_file]):
        return None

    # Load data
    embeddings = np.load(embeddings_file)
    coords = np.load(coords_file)
    with open(metadata_file, 'r') as f:
        metadata = json.load(f)

    # Build pixel lookup: (x, y) -> index
    pixel_lookup = {}
    for idx, (x, y) in enumerate(coords):
        pixel_lookup[(int(x), int(y))] = idx

    data = {
        'embeddings': embeddings,
        'coords': coords,
        'metadata': metadata,
        'pixel_lookup': pixel_lookup
    }

    _faiss_data_cache[cache_key] = data
    logger.info(f"[FAISS] Cached data for {viewport_name}/{year}: {len(embeddings)} embeddings")

    return data

def check_viewport_pyramids_exist(viewport_name):
    """Check if pyramid tiles exist for a viewport (checks for ANY year available)."""
    viewport_pyramids_dir = PYRAMIDS_DIR / viewport_name
    if not viewport_pyramids_dir.exists():
        return False
    # Check if any year directory has pyramid level_0.tif
    for year_dir in viewport_pyramids_dir.glob("*"):
        if year_dir.is_dir() and year_dir.name not in ['satellite', 'rgb']:
            level_0_file = year_dir / "level_0.tif"
            if level_0_file.exists():
                return True
    return False

def get_viewport_data_size(viewport_name, active_viewport_name):
    """Calculate total data size for a viewport in MB."""
    total_size = 0

    # Mosaic files (viewport-specific)
    if MOSAICS_DIR.exists():
        for mosaic_file in MOSAICS_DIR.glob(f'{viewport_name}_*.tif'):
            if mosaic_file.is_file():
                total_size += mosaic_file.stat().st_size

    # FAISS indices (viewport-specific)
    faiss_dir = FAISS_INDICES_DIR / viewport_name
    if faiss_dir.exists():
        for item in faiss_dir.rglob('*'):
            if item.is_file():
                total_size += item.stat().st_size

    # Pyramids (viewport-specific)
    viewport_pyramids_dir = PYRAMIDS_DIR / viewport_name
    if viewport_pyramids_dir.exists():
        for item in viewport_pyramids_dir.rglob('*'):
            if item.is_file():
                total_size += item.stat().st_size

    # Convert to MB
    return round(total_size / (1024 * 1024), 1)

def trigger_data_download_and_processing(viewport_name, years=None):
    """Download embeddings and run full preprocessing pipeline using shared PipelineRunner.

    Pipeline stages:
    1. download_embeddings.py - Download GeoTessera embeddings
    2. create_rgb_embeddings.py - Create RGB visualization
    3. create_pyramids.py - Create pyramid tiles (CRITICAL for viewer)
    4. create_faiss_index.py - Create FAISS similarity search index
    5. (Optional) compute_umap.py - Compute 2D UMAP projection

    Uses single source of truth: lib.pipeline.PipelineRunner
    """
    operation_id = f"{viewport_name}_full_pipeline"

    def download_and_process():
        try:
            with tasks_lock:
                tasks[operation_id] = {'status': 'starting', 'current_stage': 'initialization', 'error': None}

            # Set this viewport as active before processing
            logger.info(f"[PIPELINE] Setting {viewport_name} as active viewport...")
            set_active_viewport(viewport_name)

            # Create pipeline runner and execute
            project_root = Path(__file__).parent.parent
            runner = PipelineRunner(project_root, VENV_PYTHON)

            # Convert years list to comma-separated string
            years_str = ','.join(str(y) for y in years) if years else None

            # Create cancellation check function
            def is_cancelled():
                with tasks_lock:
                    task = tasks.get(operation_id, {})
                    return task.get('status') == 'cancelled'

            # Run the full pipeline (stages 1-4, optional UMAP)
            # Note: UMAP is only computed if explicitly enabled; web UI doesn't compute it
            success, error = runner.run_full_pipeline(
                viewport_name=viewport_name,
                years_str=years_str,
                compute_umap=False,  # Web UI doesn't compute UMAP; it's optional for CLI
                cancel_check=is_cancelled
            )

            if success:
                logger.info(f"[PIPELINE] ✓✓✓ SUCCESS: All stages complete for viewport '{viewport_name}' ✓✓✓")
                with tasks_lock:
                    tasks[operation_id] = {'status': 'success', 'current_stage': 'complete', 'error': None}
            else:
                with tasks_lock:
                    tasks[operation_id] = {'status': 'failed', 'current_stage': 'pipeline_error', 'error': error}

        except subprocess.TimeoutExpired:
            error_msg = "Timeout during preprocessing"
            logger.error(f"[PIPELINE] ✗ {error_msg} for '{viewport_name}'")
            with tasks_lock:
                tasks[operation_id] = {'status': 'failed', 'current_stage': 'timeout', 'error': error_msg}
        except Exception as e:
            error_msg = f"Error during preprocessing: {str(e)}"
            logger.error(f"[PIPELINE] ✗ {error_msg} for '{viewport_name}'", exc_info=True)
            with tasks_lock:
                tasks[operation_id] = {'status': 'failed', 'current_stage': 'exception', 'error': error_msg}

    thread = threading.Thread(target=download_and_process, daemon=True)
    thread.start()

# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Docker/monitoring."""
    return jsonify({
        'status': 'healthy',
        'service': 'TEE',
        'data_dir': str(DATA_DIR)
    })


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.route('/api/viewports/list', methods=['GET'])
def api_list_viewports():
    """List all available viewports."""
    try:
        viewports = list_viewports()
        active_name = get_active_viewport_name()

        viewport_data = []
        for viewport_name in viewports:
            try:
                viewport = read_viewport_file(viewport_name)
                viewport['name'] = viewport_name
                viewport['is_active'] = (viewport_name == active_name)
                # Calculate and include data size
                viewport['data_size_mb'] = get_viewport_data_size(viewport_name, active_name)
                viewport_data.append(viewport)
            except Exception as e:
                logger.warning(f"Error reading viewport {viewport_name}: {e}")

        return jsonify({
            'success': True,
            'viewports': viewport_data,
            'active': active_name
        })
    except Exception as e:
        logger.error(f"Error listing viewports: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/viewports/current', methods=['GET'])
def api_current_viewport():
    """Get current active viewport."""
    try:
        viewport = get_active_viewport()
        active_name = get_active_viewport_name()
        viewport['name'] = active_name

        return jsonify({
            'success': True,
            'viewport': viewport
        })
    except Exception as e:
        logger.error(f"Error getting current viewport: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/viewports/switch', methods=['POST'])
def api_switch_viewport():
    """Switch to a different viewport and report processing status (monitoring only, no process initiation)."""
    try:
        data = request.get_json()
        viewport_name = data.get('name')

        if not viewport_name:
            return jsonify({'success': False, 'error': 'Viewport name required'}), 400

        try:
            validate_viewport_name(viewport_name)
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400

        set_active_viewport(viewport_name)

        # Get updated viewport info
        viewport = read_viewport_file(viewport_name)
        viewport['name'] = viewport_name

        response_data = {
            'success': True,
            'message': f'Switched to viewport: {viewport_name}',
            'viewport': viewport,
            'data_ready': True,
            'pyramids_ready': True,
            'faiss_ready': False
        }

        # Check if full pipeline is running for this viewport
        operation_id = f"{viewport_name}_full_pipeline"
        pipeline_status = None
        current_stage = None
        with tasks_lock:
            if operation_id in tasks:
                pipeline_status = tasks[operation_id].get('status')
                current_stage = tasks[operation_id].get('current_stage')
                logger.info(f"[MONITOR] Pipeline for '{viewport_name}': status={pipeline_status}, stage={current_stage}")

        # Monitor data availability (no initiation)
        if not check_viewport_mosaics_exist(viewport_name):
            response_data['data_ready'] = False
            if pipeline_status:
                response_data['message'] += f'\nPipeline processing (current stage: {current_stage}). This may take 15-30 minutes...'
            else:
                response_data['message'] += '\nData not available. No processing was initiated at viewport creation.'

        # Monitor pyramid availability (no initiation)
        if not check_viewport_pyramids_exist(viewport_name):
            response_data['pyramids_ready'] = False
            if not pipeline_status:
                response_data['message'] += '\nPyramids not ready. Waiting for data to complete...'

        # Monitor FAISS availability (no initiation)
        faiss_dir = FAISS_INDICES_DIR / viewport_name
        faiss_index_file = faiss_dir / 'all_embeddings.npy'

        if faiss_index_file.exists():
            response_data['faiss_ready'] = True
            logger.info(f"[MONITOR] FAISS ready for '{viewport_name}'")
        else:
            response_data['faiss_ready'] = False
            if pipeline_status:
                response_data['message'] += '\nWaiting for FAISS index (created during pipeline processing)...'

        return jsonify(response_data)
    except FileNotFoundError:
        return jsonify({'success': False, 'error': f'Viewport not found'}), 404
    except Exception as e:
        logger.error(f"Error switching viewport: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/viewports/create', methods=['POST'])
def api_create_viewport():
    """Create a new viewport from bounds."""
    try:
        data = request.get_json()

        # Validate input
        bounds_str = data.get('bounds')
        name = data.get('name')
        description = data.get('description', '')

        if not bounds_str:
            return jsonify({'success': False, 'error': 'Bounds required'}), 400

        # Parse bounds
        try:
            parts = bounds_str.split(',')
            if len(parts) != 4:
                raise ValueError("Bounds must have 4 values")
            bounds = tuple(float(p.strip()) for p in parts)
        except ValueError as e:
            return jsonify({'success': False, 'error': f'Invalid bounds format: {e}'}), 400

        # Generate name if not provided
        if not name:
            import time
            name = f"viewport_{int(time.time())}"

        # Validate viewport name (whether user-provided or auto-generated)
        try:
            validate_viewport_name(name)
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400

        # Get selected years
        years = data.get('years')  # Will be list of integers or None
        logger.info(f"[NEW VIEWPORT] API received years: {years} (type: {type(years).__name__})")

        # Create viewport
        create_viewport_from_bounds(name, bounds, description)

        # Get created viewport info
        viewport = read_viewport_file(name)
        viewport['name'] = name

        # Save selected years to config file (for auto-resume)
        if years:
            config_file = VIEWPORTS_DIR / f"{name}_config.json"
            with open(config_file, 'w') as f:
                json.dump({'years': years}, f)
            logger.info(f"[NEW VIEWPORT] Saved years config: {config_file}")

        # Automatically trigger data download and processing for new viewport
        logger.info(f"[NEW VIEWPORT] Triggering data download for new viewport '{name}' with years={years}...")
        trigger_data_download_and_processing(name, years=years)

        return jsonify({
            'success': True,
            'message': f'Created viewport: {name}. Downloading data and creating pyramids in background (this may take 15-30 minutes)...',
            'viewport': viewport,
            'data_preparing': True
        })
    except FileExistsError as e:
        return jsonify({'success': False, 'error': str(e)}), 409
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error creating viewport: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/downloads/embeddings', methods=['POST'])
def api_download_embeddings():
    """Download embeddings for the current viewport."""
    try:
        import subprocess
        project_root = Path(__file__).parent.parent

        # Get current viewport info
        viewport = get_active_viewport()
        logger.info(f"Downloading embeddings for viewport: {viewport['viewport_id']}")

        # Run the download script
        result = run_script('download_embeddings.py', timeout=600)

        if result.returncode == 0:
            logger.info("Embeddings download completed successfully")
            return jsonify({
                'success': True,
                'message': 'Embeddings downloaded successfully',
                'viewport': viewport['viewport_id']
            })
        else:
            error_msg = result.stderr or result.stdout
            logger.error(f"Embeddings download failed: {error_msg}")
            return jsonify({
                'success': False,
                'error': f'Download failed: {error_msg}'
            }), 400

    except subprocess.TimeoutExpired:
        logger.error("Embeddings download timeout")
        return jsonify({'success': False, 'error': 'Download timeout'}), 408
    except Exception as e:
        logger.error(f"Error downloading embeddings: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400



def run_download_process(task_id):
    """Background task to run downloads and processing in parallel."""
    import subprocess
    import time
    import rasterio

    project_root = Path(__file__).parent.parent

    def update_progress(progress, stage):
        with tasks_lock:
            if task_id in tasks:
                tasks[task_id]['progress'] = progress
                tasks[task_id]['stage'] = stage

    try:
        # Check if pyramid data already exists for current viewport
        update_progress(5, "Checking for existing pyramid data...")

        viewport = get_active_viewport()
        viewport_name = viewport['viewport_id']
        bounds = viewport['bounds']
        BOUNDS_TOLERANCE = 0.0001

        pyramids_dir = PYRAMIDS_DIR / '2024'
        pyramid_metadata = pyramids_dir / 'pyramid_metadata.json'

        # If pyramid metadata exists, skip downloads and processing
        if pyramid_metadata.exists():
            try:
                import json
                with open(pyramid_metadata) as f:
                    metadata = json.load(f)
                    cached_bounds = metadata.get('bounds', {})

                    # Check if bounds match
                    if (abs(cached_bounds.get('minLon', 0) - bounds['minLon']) < BOUNDS_TOLERANCE and
                        abs(cached_bounds.get('minLat', 0) - bounds['minLat']) < BOUNDS_TOLERANCE and
                        abs(cached_bounds.get('maxLon', 0) - bounds['maxLon']) < BOUNDS_TOLERANCE and
                        abs(cached_bounds.get('maxLat', 0) - bounds['maxLat']) < BOUNDS_TOLERANCE):

                        logger.info(f"Pyramid data already exists for viewport - skipping downloads")
                        update_progress(100, "✓ Pyramid data already cached!")

                        with tasks_lock:
                            if task_id in tasks:
                                tasks[task_id]['completed'] = True
                        return
            except Exception as e:
                logger.warning(f"Could not read pyramid metadata: {e}")

        # Check if mosaics already exist with matching bounds
        update_progress(8, "Checking for existing mosaic files...")

        # Use viewport-specific filenames for proper caching across viewports
        embeddings_mosaic = MOSAICS_DIR / f'{viewport_name}_embeddings_2024.tif'

        skip_downloads = False
        if embeddings_mosaic.exists():
            try:
                # Check if mosaic contains the viewport area (containment, not exact match)
                with rasterio.open(embeddings_mosaic) as src:
                    cached_bounds = src.bounds

                    # Check if viewport is contained within mosaic bounds
                    viewport_contained = (
                        cached_bounds.left <= bounds['minLon'] + BOUNDS_TOLERANCE and
                        cached_bounds.bottom <= bounds['minLat'] + BOUNDS_TOLERANCE and
                        cached_bounds.right >= bounds['maxLon'] - BOUNDS_TOLERANCE and
                        cached_bounds.top >= bounds['maxLat'] - BOUNDS_TOLERANCE
                    )

                    if viewport_contained:
                        logger.info(f"Embeddings mosaic already exists and contains viewport - skipping downloads, proceeding to pyramid creation")
                        skip_downloads = True
                        update_progress(45, "✓ Embeddings mosaic found - skipping downloads, creating pyramids...")
            except Exception as e:
                logger.warning(f"Could not check mosaic bounds: {e}")

        # Run downloads only if mosaics don't exist
        if not skip_downloads:
            update_progress(5, "Downloading TESSERA embeddings...")

            # Run embeddings download
            executor = ThreadPoolExecutor(max_workers=1)

            def download_embeddings():
                try:
                    update_progress(10, "Downloading embeddings_2024.tif (TESSERA)...")
                    result = run_script('download_embeddings.py', timeout=600)
                    if result.returncode == 0:
                        update_progress(30, "✓ Embeddings downloaded")
                    return result.returncode == 0
                except Exception as e:
                    logger.error(f"Embeddings download error: {e}")
                    update_progress(30, "✗ Embeddings download failed")
                    return False

            # Submit embeddings download only (satellite data not needed)
            update_progress(10, "Starting embeddings download...")
            embeddings_future = executor.submit(download_embeddings)

            # Wait for embeddings to complete
            embeddings_ok = embeddings_future.result()

            if not embeddings_ok:
                raise Exception("Embeddings download failed")
            update_progress(50, "Downloads complete. Creating pyramids...")

        # Run pyramid creation and FAISS index creation in parallel
        update_progress(55, "Creating pyramids and FAISS index in parallel...")

        executor = ThreadPoolExecutor(max_workers=2)

        def create_pyramids():
            try:
                update_progress(60, "Creating pyramid tiles...")
                result = run_script('create_pyramids.py', timeout=1200)
                if result.returncode != 0:
                    logger.warning(f"Pyramid creation returned non-zero: {result.stderr}")
                return result.returncode == 0
            except Exception as e:
                logger.error(f"Pyramid creation error: {e}")
                return False

        def create_faiss_index():
            try:
                # Check if FAISS index already exists for current viewport
                # Use the viewport_name captured at the START of this function, not the active viewport
                # (which may have changed if user switched viewports)
                faiss_dir = FAISS_INDICES_DIR / viewport_name
                metadata_file = faiss_dir / 'metadata.json'

                if faiss_dir.exists() and metadata_file.exists():
                    try:
                        import json
                        with open(metadata_file) as f:
                            metadata = json.load(f)
                            cached_bounds = metadata.get('viewport_bounds', [])

                            # Check if bounds match
                            bounds_list = [bounds['minLon'], bounds['minLat'],
                                         bounds['maxLon'], bounds['maxLat']]
                            BOUNDS_TOLERANCE = 0.0001

                            if (len(cached_bounds) == 4 and
                                abs(cached_bounds[0] - bounds_list[0]) < BOUNDS_TOLERANCE and
                                abs(cached_bounds[1] - bounds_list[1]) < BOUNDS_TOLERANCE and
                                abs(cached_bounds[2] - bounds_list[2]) < BOUNDS_TOLERANCE and
                                abs(cached_bounds[3] - bounds_list[3]) < BOUNDS_TOLERANCE):

                                logger.info(f"FAISS index already exists for viewport - skipping creation")
                                return True
                    except Exception as e:
                        logger.warning(f"Could not validate FAISS metadata: {e}")

                update_progress(65, "Creating FAISS index for similarity search...")
                result = run_script('create_faiss_index.py', timeout=600)
                if result.returncode == 0:
                    update_progress(75, "✓ FAISS index created")
                else:
                    logger.warning(f"FAISS index creation returned non-zero: {result.stderr}")
                    update_progress(75, "✓ FAISS index creation skipped")
                return True  # Non-blocking, don't fail if FAISS creation fails
            except Exception as e:
                logger.error(f"FAISS index creation error: {e}")
                logger.warning("Continuing without FAISS index (non-blocking)")
                return True  # Non-blocking error

        # Submit both tasks in parallel
        pyramids_future = executor.submit(create_pyramids)
        faiss_future = executor.submit(create_faiss_index)

        # Wait for both to complete
        pyramids_ok = pyramids_future.result()
        faiss_ok = faiss_future.result()

        if not pyramids_ok:
            logger.warning("Pyramid creation may have failed")

        update_progress(90, "Finalizing...")
        update_progress(100, "✓ Complete! All data ready")

        with tasks_lock:
            if task_id in tasks:
                tasks[task_id]['completed'] = True

        logger.info(f"Download process {task_id} completed successfully")

    except Exception as e:
        logger.error(f"Download process {task_id} error: {e}")
        with tasks_lock:
            if task_id in tasks:
                tasks[task_id]['error'] = str(e)
                tasks[task_id]['completed'] = True


@app.route('/api/downloads/process', methods=['POST'])
def api_downloads_process():
    """Start parallel downloads and processing."""
    try:
        task_id = str(uuid.uuid4())

        with tasks_lock:
            tasks[task_id] = {
                'progress': 0,
                'stage': 'Initializing...',
                'completed': False,
                'error': None
            }

        # Start background task
        thread = threading.Thread(target=run_download_process, args=(task_id,))
        thread.daemon = True
        thread.start()

        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': 'Download process started'
        })

    except Exception as e:
        logger.error(f"Error starting download process: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/downloads/progress/<task_id>', methods=['GET'])
def api_downloads_progress(task_id):
    """Get progress of a download task."""
    try:
        with tasks_lock:
            if task_id not in tasks:
                return jsonify({'success': False, 'error': 'Task not found'}), 404

            task = tasks[task_id]

        response = {
            'success': True,
            'progress': task['progress'],
            'stage': task['stage'],
            'completed': task['completed'],
            'error': task['error']
        }

        # Check for detailed operation progress from single source of truth
        try:
            viewport = get_active_viewport()
            viewport_name = viewport['viewport_id']

            # Single source of truth: pipeline progress file
            progress_file = Path(f"/tmp/{viewport_name}_pipeline_progress.json")
            if progress_file.exists():
                try:
                    with open(progress_file, 'r') as f:
                        op_progress = json.load(f)
                        # Include detailed message if available
                        if op_progress.get('message'):
                            response['detailed_message'] = op_progress['message']
                        if op_progress.get('current_file'):
                            response['current_file'] = op_progress['current_file']
                        if op_progress.get('current_value'):
                            response['current_value'] = op_progress['current_value']
                        if op_progress.get('total_value'):
                            response['total_value'] = op_progress['total_value']
                except (json.JSONDecodeError, IOError):
                    pass
        except Exception:
            # If detailed progress isn't available, just use the simplified progress
            pass

        return jsonify(response)

    except Exception as e:
        logger.error(f"Error getting progress: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/operations/progress/<operation_id>', methods=['GET'])
def api_operations_progress(operation_id):
    """Get progress of an operation (embeddings, pyramids, FAISS) from progress JSON file.

    For pipeline operations, merges detailed progress from sub-operations (e.g., embeddings download)
    to provide unified progress tracking with full detail (current_file, bytes, etc.).
    """
    try:
        # Validate operation_id to prevent path traversal in /tmp/ reads
        if not re.match(r'^[A-Za-z0-9_-]+$', operation_id):
            return jsonify({'success': False, 'error': 'Invalid operation_id'}), 400

        progress_file = Path(f"/tmp/{operation_id}_progress.json")

        if not progress_file.exists():
            return jsonify({
                'success': False,
                'status': 'not_started',
                'message': 'Operation not started yet'
            }), 200

        with open(progress_file, 'r') as f:
            progress_data = json.load(f)

        # Single source of truth - all progress written to {viewport}_pipeline_progress.json
        return jsonify({
            'success': True,
            **progress_data
        }), 200

    except Exception as e:
        logger.error(f"Error getting operation progress: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/operations/pipeline-status/<viewport_name>', methods=['GET'])
def api_pipeline_status(viewport_name):
    """Get status of viewport pipeline processing."""
    try:
        validate_viewport_name(viewport_name)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    try:
        operation_id = f"{viewport_name}_full_pipeline"
        with tasks_lock:
            if operation_id in tasks:
                status_info = tasks[operation_id]
                return jsonify({
                    'success': True,
                    'operation_id': operation_id,
                    **status_info
                }), 200
            else:
                return jsonify({
                    'success': False,
                    'status': 'no_pipeline',
                    'message': 'No pipeline operation found for this viewport'
                }), 200

    except Exception as e:
        logger.error(f"Error getting pipeline status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/viewports/<viewport_name>/cancel-processing', methods=['POST'])
def api_cancel_processing(viewport_name):
    """Cancel viewport processing pipeline and clean up all generated files."""
    try:
        validate_viewport_name(viewport_name)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    try:
        import glob
        import shutil

        operation_id = f"{viewport_name}_full_pipeline"
        deleted_items = []
        task_was_active = False

        # Kill running subprocess (if any)
        if cancel_pipeline(viewport_name):
            logger.info(f"[CANCEL] Killed running pipeline subprocess for '{viewport_name}'")
            deleted_items.append("subprocess killed")

        # Try to cancel the active task (if any)
        with tasks_lock:
            if operation_id in tasks:
                current_status = tasks[operation_id].get('status')
                if current_status in ('starting', 'in_progress'):
                    tasks[operation_id] = {
                        'status': 'cancelled',
                        'current_stage': 'cancelled',
                        'error': 'Cancelled by user'
                    }
                    task_was_active = True
                    logger.info(f"[PIPELINE] Cancelled processing for viewport '{viewport_name}'")

        # Always clean up files regardless of task state
        # (files may exist even if task tracking was lost)

        # Clean up progress files
        progress_patterns = [
            f"/tmp/{viewport_name}_progress.json",
            f"/tmp/{viewport_name}_*_progress.json"
        ]
        for pattern in progress_patterns:
            for f in glob.glob(pattern):
                try:
                    Path(f).unlink()
                    deleted_items.append(f"progress: {Path(f).name}")
                except:
                    pass

        # Delete mosaic files
        if MOSAICS_DIR.exists():
            for mosaic_file in MOSAICS_DIR.glob(f'{viewport_name}_*.tif'):
                try:
                    mosaic_file.unlink()
                    deleted_items.append(f"mosaic: {mosaic_file.name}")
                except:
                    pass

            # Delete years metadata
            years_file = MOSAICS_DIR / f'{viewport_name}_years.json'
            if years_file.exists():
                try:
                    years_file.unlink()
                    deleted_items.append(f"years: {years_file.name}")
                except:
                    pass

            # Delete RGB mosaics
            rgb_dir = MOSAICS_DIR / 'rgb'
            if rgb_dir.exists():
                for rgb_file in rgb_dir.glob(f'{viewport_name}_*.tif'):
                    try:
                        rgb_file.unlink()
                        deleted_items.append(f"RGB: {rgb_file.name}")
                    except:
                        pass

        # Delete pyramids directory
        if PYRAMIDS_DIR.exists():
            viewport_pyramids_dir = PYRAMIDS_DIR / viewport_name
            if viewport_pyramids_dir.exists():
                try:
                    shutil.rmtree(viewport_pyramids_dir)
                    deleted_items.append(f"pyramids: {viewport_name}/")
                except:
                    pass

        # Delete FAISS directory
        if FAISS_INDICES_DIR.exists():
            faiss_viewport_dir = FAISS_INDICES_DIR / viewport_name
            if faiss_viewport_dir.exists():
                try:
                    shutil.rmtree(faiss_viewport_dir)
                    deleted_items.append(f"FAISS: {viewport_name}/")
                except:
                    pass

        # Delete viewport config and definition files
        viewports_dir = Path(__file__).parent.parent / 'viewports'
        for pattern in [f'{viewport_name}.txt', f'{viewport_name}_config.json']:
            filepath = viewports_dir / pattern
            if filepath.exists():
                try:
                    filepath.unlink()
                    deleted_items.append(f"config: {pattern}")
                except:
                    pass

        # If this was the active viewport, clear the active state
        try:
            active_name = get_active_viewport_name()
            if active_name == viewport_name:
                clear_active_viewport()
                deleted_items.append("active viewport state")
                logger.info(f"[CANCEL] Cleared active viewport state for '{viewport_name}'")
        except:
            pass

        logger.info(f"[CANCEL] Cleaned up {len(deleted_items)} items for '{viewport_name}'")

        if task_was_active:
            message = f'Processing cancelled for {viewport_name}'
        elif deleted_items:
            message = f'No active task, but cleaned up {len(deleted_items)} leftover files for {viewport_name}'
        else:
            message = f'No active processing or files found for {viewport_name}'

        return jsonify({
            'success': True,
            'message': message,
            'deleted_items': deleted_items,
            'task_was_active': task_was_active
        }), 200

    except Exception as e:
        logger.error(f"Error cancelling processing: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/viewports/delete', methods=['POST'])
def api_delete_viewport():
    """Delete a viewport and all associated data."""
    try:
        import rasterio
        import shutil

        data = request.get_json()
        viewport_name = data.get('name')

        if not viewport_name:
            return jsonify({'success': False, 'error': 'Viewport name required'}), 400

        try:
            validate_viewport_name(viewport_name)
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400

        viewports_dir = Path(__file__).parent.parent / 'viewports'
        viewport_file = viewports_dir / f'{viewport_name}.txt'

        if not viewport_file.exists():
            return jsonify({'success': False, 'error': 'Viewport not found'}), 404

        # If this is the active viewport, clear the active state first
        active_viewport = get_active_viewport_name()
        if active_viewport == viewport_name:
            clear_active_viewport()
            logger.info(f"Cleared active viewport state before deleting '{viewport_name}'")

        # Read the viewport to get its bounds
        try:
            viewport = read_viewport_file(viewport_name)
            bounds = viewport['bounds']
            BOUNDS_TOLERANCE = 0.0001  # Same as in viewport_utils
        except Exception as e:
            logger.warning(f"Could not read viewport bounds, skipping data cleanup: {e}")
            bounds = None

        deleted_items = []

        # Delete associated mosaic files (match by viewport name in filename)
        if MOSAICS_DIR.exists():
            # Delete embedding mosaics
            for mosaic_file in MOSAICS_DIR.glob('*.tif'):
                if mosaic_file.stem.startswith(viewport_name + '_'):
                    mosaic_file.unlink()
                    deleted_items.append(f"mosaic: {mosaic_file.name}")
                    logger.info(f"✓ Deleted mosaic: {mosaic_file.name}")

            # Delete years metadata JSON
            years_file = MOSAICS_DIR / f'{viewport_name}_years.json'
            if years_file.exists():
                years_file.unlink()
                deleted_items.append(f"years metadata: {years_file.name}")
                logger.info(f"✓ Deleted years metadata: {years_file.name}")

            # Delete RGB mosaics (in mosaics/rgb/ subdirectory)
            rgb_dir = MOSAICS_DIR / 'rgb'
            if rgb_dir.exists():
                for rgb_file in rgb_dir.glob(f'{viewport_name}_*.tif'):
                    rgb_file.unlink()
                    deleted_items.append(f"RGB mosaic: {rgb_file.name}")
                    logger.info(f"✓ Deleted RGB mosaic: {rgb_file.name}")

        # Delete viewport-specific pyramid directory
        if PYRAMIDS_DIR.exists():
            try:
                viewport_pyramids_dir = PYRAMIDS_DIR / viewport_name
                if viewport_pyramids_dir.exists():
                    shutil.rmtree(viewport_pyramids_dir)
                    deleted_items.append(f"pyramids directory: {viewport_name}/")
                    logger.info(f"✓ Deleted pyramids directory: {viewport_name}/")
            except Exception as e:
                logger.warning(f"Error deleting pyramids directory for {viewport_name}: {e}")

        # Delete FAISS indices directory for this viewport (includes UMAP coords)
        if FAISS_INDICES_DIR.exists():
            try:
                faiss_viewport_dir = FAISS_INDICES_DIR / viewport_name
                if faiss_viewport_dir.exists():
                    shutil.rmtree(faiss_viewport_dir)
                    deleted_items.append(f"FAISS/UMAP directory: {viewport_name}/")
                    logger.info(f"✓ Deleted FAISS/UMAP directory: {viewport_name}/")
            except Exception as e:
                logger.warning(f"Error deleting FAISS index directory for {viewport_name}: {e}")

        # Delete labels from SQLite database
        try:
            labels_deleted = delete_viewport_labels(viewport_name)
            if labels_deleted > 0:
                deleted_items.append(f"labels: {labels_deleted} from database")
                logger.info(f"✓ Deleted {labels_deleted} labels from database")
        except Exception as e:
            logger.warning(f"Error deleting labels from database for {viewport_name}: {e}")

        # Also delete legacy labels JSON file if it exists
        labels_file = viewports_dir / f'{viewport_name}_labels.json'
        if labels_file.exists():
            try:
                labels_file.unlink()
                deleted_items.append(f"labels JSON: {labels_file.name}")
                logger.info(f"✓ Deleted legacy labels file: {labels_file.name}")
            except Exception as e:
                logger.warning(f"Error deleting labels file for {viewport_name}: {e}")

        # Delete viewport config JSON file (stores years selection)
        config_file = viewports_dir / f'{viewport_name}_config.json'
        if config_file.exists():
            try:
                config_file.unlink()
                deleted_items.append(f"config: {config_file.name}")
                logger.info(f"✓ Deleted config: {config_file.name}")
            except Exception as e:
                logger.warning(f"Error deleting config file for {viewport_name}: {e}")

        # Delete progress tracking files for this viewport
        tmp_dir = Path('/tmp')
        progress_patterns = [
            f'{viewport_name}_embeddings_progress.json',
            f'{viewport_name}_pyramids_progress.json',
            f'{viewport_name}_faiss_*_progress.json',
            f'{viewport_name}_umap_*_progress.json',
            f'{viewport_name}_pca_*_progress.json',
            f'{viewport_name}_pipeline_progress.json',
        ]
        for pattern in progress_patterns:
            for progress_file in tmp_dir.glob(pattern):
                try:
                    progress_file.unlink()
                    deleted_items.append(f"progress file: {progress_file.name}")
                    logger.info(f"✓ Deleted progress file: {progress_file.name}")
                except Exception as e:
                    logger.warning(f"Error deleting progress file {progress_file.name}: {e}")

        # Delete the viewport file
        viewport_file.unlink()
        deleted_items.append(f"viewport: {viewport_name}.txt")
        logger.info(f"✓ Deleted viewport: {viewport_name}")

        return jsonify({
            'success': True,
            'message': f'Deleted viewport and {len(deleted_items)-1} data files',
            'deleted': deleted_items
        })

    except Exception as e:
        logger.error(f"Error deleting viewport: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/viewports/<viewport_name>/available-years', methods=['GET'])
def api_get_available_years(viewport_name):
    """Get list of years with available data for a viewport."""
    try:
        validate_viewport_name(viewport_name)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    try:
        pyramid_years = []
        viewport_pyramids_dir = PYRAMIDS_DIR / viewport_name
        if viewport_pyramids_dir.exists():
            for year in range(2017, 2026):
                pyramid_file = viewport_pyramids_dir / str(year) / "level_0.tif"
                if pyramid_file.exists():
                    pyramid_years.append(year)

        return jsonify({
            'success': True,
            'years': sorted(pyramid_years, reverse=True)  # Newest first
        })
    except Exception as e:
        logger.error(f"Error getting available years: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/viewports/<viewport_name>/is-ready', methods=['GET'])
def api_is_viewport_ready(viewport_name):
    """Simple synchronous check: is this viewport ready to view?"""
    try:
        validate_viewport_name(viewport_name)
    except ValueError as e:
        return jsonify({'ready': False, 'message': str(e)}), 400
    try:
        # Check FAISS (primary indicator - mosaics are deleted after FAISS creation)
        has_faiss = False
        faiss_dir = FAISS_INDICES_DIR / viewport_name
        if faiss_dir.exists():
            for year_dir in faiss_dir.glob("*"):
                if year_dir.is_dir() and (year_dir / "embeddings.index").exists():
                    has_faiss = True
                    break

        # Check for mosaics (only during pipeline, before FAISS is created)
        embedding_files = list(MOSAICS_DIR.glob(f"{viewport_name}_embeddings_*.tif"))
        has_mosaics = len(embedding_files) > 0

        # has_embeddings is true if FAISS exists OR mosaics exist (mosaics are temporary)
        has_embeddings = has_faiss or has_mosaics

        # Check pyramids
        pyramid_dir = PYRAMIDS_DIR / viewport_name
        has_pyramids = False
        years_available = []
        if pyramid_dir.exists():
            for year_dir in pyramid_dir.glob("*"):
                if year_dir.is_dir() and year_dir.name not in ['satellite', 'rgb']:
                    if (year_dir / "level_0.tif").exists():
                        has_pyramids = True
                        years_available.append(year_dir.name)

        # Check PCA (need one from any year for Panel 4 visualization)
        has_pca = False
        if faiss_dir.exists():
            for year_dir in faiss_dir.glob("*"):
                if year_dir.is_dir() and (year_dir / 'pca_coords.npy').exists():
                    has_pca = True
                    break

        # Check UMAP (just need one from any year)
        has_umap = False
        if faiss_dir.exists():
            for year_dir in faiss_dir.glob("*"):
                if year_dir.is_dir() and (year_dir / 'umap_coords.npy').exists():
                    has_umap = True
                    break

        # Determine readiness: can view if pyramids exist (FAISS is optional for initial view)
        is_ready = has_pyramids

        if is_ready:
            year_count = len(years_available)
            message = f"✓ Ready to view ({year_count} year{'s' if year_count != 1 else ''})"
        elif not has_embeddings:
            message = "⏳ Downloading embeddings..."
        else:
            # Embeddings exist but pyramids don't — check if pipeline is actually running.
            # If not (e.g. daemon thread died on restart), re-trigger it so processing
            # resumes automatically instead of staying stuck forever.
            operation_id = f"{viewport_name}_full_pipeline"
            pipeline_running = False
            with tasks_lock:
                if operation_id in tasks:
                    pipeline_running = tasks[operation_id].get('status') in ('starting', 'in_progress')

            if not pipeline_running:
                logger.info(f"[is-ready] Pipeline not running for '{viewport_name}' but data incomplete — re-triggering pipeline")
                # Read saved years from config file (if exists)
                config_file = VIEWPORTS_DIR / f"{viewport_name}_config.json"
                saved_years = None
                if config_file.exists():
                    try:
                        with open(config_file) as f:
                            config = json.load(f)
                            saved_years = config.get('years')
                            logger.info(f"[is-ready] Loaded saved years from config: {saved_years}")
                    except Exception as e:
                        logger.warning(f"[is-ready] Could not read config file: {e}")
                trigger_data_download_and_processing(viewport_name, years=saved_years)
                message = "⏳ Restarting pipeline..."
            else:
                message = "⏳ Creating pyramids..."

        return jsonify({
            'ready': is_ready,
            'message': message,
            'has_embeddings': has_embeddings,
            'has_pyramids': has_pyramids,
            'has_faiss': has_faiss,
            'has_pca': has_pca,
            'has_umap': has_umap,
            'years_available': years_available
        }), 200

    except Exception as e:
        logger.error(f"Error checking viewport readiness: {e}")
        return jsonify({'ready': False, 'message': f'Error: {str(e)}'}), 400


@app.route('/api/embeddings/extract', methods=['POST'])
def api_extract_embedding():
    """Extract embedding vector at a given latitude/longitude coordinate.

    Uses pre-computed FAISS data (numpy arrays) instead of GeoTIFF for faster lookups.
    This allows GeoTIFF files to be deleted after FAISS index creation.
    """
    try:
        data = request.get_json()
        lat = float(data.get('lat'))
        lon = float(data.get('lon'))
        year = int(data.get('year', 2024))  # Default to 2024

        # Get active viewport
        viewport_name = get_active_viewport_name()

        # Load FAISS data (cached)
        faiss_data = get_faiss_data(viewport_name, year)

        if faiss_data is None:
            return jsonify({
                'success': False,
                'error': f'FAISS data not found for {viewport_name}/{year}'
            }), 404

        # Get geotransform from metadata
        gt = faiss_data['metadata']['geotransform']

        # Convert lat/lon to pixel coordinates
        # x = (lon - c) / a
        # y = (lat - f) / e
        px = (lon - gt['c']) / gt['a']
        py = (lat - gt['f']) / gt['e']

        x_int = int(px)
        y_int = int(py)

        # Look up the embedding by pixel coordinates
        pixel_lookup = faiss_data['pixel_lookup']

        if (x_int, y_int) not in pixel_lookup:
            # Try nearby pixels (within 1 pixel tolerance)
            found = False
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if (x_int + dx, y_int + dy) in pixel_lookup:
                        x_int += dx
                        y_int += dy
                        found = True
                        break
                if found:
                    break

            if not found:
                return jsonify({
                    'success': False,
                    'error': f'Pixel ({x_int}, {y_int}) not found in FAISS index'
                }), 400

        idx = pixel_lookup[(x_int, y_int)]
        embedding = faiss_data['embeddings'][idx].tolist()

        logger.info(f"Extracted embedding at ({lat:.6f}, {lon:.6f}) - pixel ({x_int}, {y_int}) - idx {idx}")

        return jsonify({
            'success': True,
            'embedding': embedding,
            'pixel': {'x': x_int, 'y': y_int},
            'coordinate': {'lat': lat, 'lon': lon}
        })

    except ValueError as e:
        logger.error(f"Invalid coordinate: {e}")
        return jsonify({'success': False, 'error': f'Invalid coordinate: {e}'}), 400
    except Exception as e:
        logger.error(f"Error extracting embedding: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/embeddings/search-similar', methods=['POST'])
def api_search_similar_embeddings():
    """Find all pixels similar to a query embedding using L2 distance.

    Embeddings are 128-dimensional float32 vectors with actual L2 distances:
    - Min: 0.0 (exact match)
    - Median: ~28.0 (typical distance)
    - Max: ~45.0 (completely different)

    Request body:
    {
        "embedding": [128-dim array of float32 values],
        "threshold": 25.0,
        "viewport_id": "came"
    }

    Suggested thresholds:
    - 25.0: Close matches (5th percentile - find very similar pixels)
    - 30.0: Moderate matches (around median distance)
    - 35.0: Loose matches (find broader similarities)
    - 40.0: Very loose matches (almost everything)

    Response:
    {
        "success": true,
        "matches": [
            {"lat": 13.0045, "lon": 77.5670, "distance": 25.234, "pixel": {"x": 100, "y": 200}},
            ...
        ],
        "query_stats": {
            "total_pixels": 3516168,
            "matches_found": 234,
            "computation_time_ms": 450,
            "threshold": 25.0
        }
    }
    """
    try:
        project_root = Path(__file__).parent.parent

        # Parse request
        data = request.get_json()

        # Convert embedding to float32 (embeddings are stored as float32 in the GeoTIFF)
        embedding_list = data.get('embedding')

        # Debug: log what we received
        logger.info(f"[SEARCH] Received embedding type: {type(embedding_list)}, length: {len(embedding_list) if embedding_list else 'None'}")
        if embedding_list and len(embedding_list) > 0:
            logger.info(f"[SEARCH] First 5 values: {embedding_list[:5]}")
            logger.info(f"[SEARCH] Value types: {type(embedding_list[0])}, sample: {embedding_list[0]}")

        query_embedding = np.array(embedding_list, dtype=np.float32)

        logger.info(f"[SEARCH] Converted to numpy: shape={query_embedding.shape}, dtype={query_embedding.dtype}")
        logger.info(f"[SEARCH] Range: [{query_embedding.min():.4f}, {query_embedding.max():.4f}]")

        threshold = float(data.get('threshold', 0.5))
        viewport_id = data.get('viewport_id') or get_active_viewport_name()
        year = int(data.get('year', 2024))  # Default to 2024

        validate_viewport_name(viewport_id)

        if query_embedding.size != 128:
            return jsonify({
                'success': False,
                'error': f'Invalid embedding dimension: {query_embedding.size}, expected 128'
            }), 400

        if not (0.0 <= threshold <= 50.0):
            return jsonify({
                'success': False,
                'error': f'Invalid threshold: {threshold}, must be between 0.0 and 50.0'
            }), 400

        logger.info(f"[SEARCH] Query: threshold={threshold}, viewport={viewport_id}, year={year}")

        # Check if FAISS index exists (year-specific)
        faiss_dir = FAISS_INDICES_DIR / viewport_id / str(year)
        if not faiss_dir.exists():
            logger.warning(f"[SEARCH] FAISS index not found: {faiss_dir}")
            return jsonify({
                'success': False,
                'error': f'FAISS index not found for viewport {viewport_id} ({year}). Please run data processing first.'
            }), 404

        # Load FAISS data
        logger.info(f"[SEARCH] Loading FAISS data from {faiss_dir}...")
        start_time = time.time()

        try:
            all_embeddings = np.load(str(faiss_dir / 'all_embeddings.npy'))  # (N, 128) float32
            pixel_coords = np.load(str(faiss_dir / 'pixel_coords.npy'))       # (N, 2) int32

            with open(faiss_dir / 'metadata.json') as f:
                metadata = json.load(f)
        except Exception as e:
            logger.error(f"[SEARCH] Error loading FAISS data: {e}")
            return jsonify({
                'success': False,
                'error': f'Error loading FAISS index: {str(e)}'
            }), 500

        logger.info(f"[SEARCH] Loaded {len(all_embeddings):,} embeddings")

        # Use embeddings as-is (already float32 in native range, no normalization needed)
        query_emb_f32 = query_embedding.astype(np.float32)  # (128,)
        all_emb_f32 = all_embeddings.astype(np.float32)     # (N, 128)

        # Compute L2 distances: sqrt(sum((a - b)^2))
        logger.info(f"[SEARCH] Computing L2 distances for {len(all_embeddings):,} pixels...")
        diff = all_emb_f32 - query_emb_f32[np.newaxis, :]  # (N, 128)
        distances = np.sqrt(np.sum(diff ** 2, axis=1))      # (N,)

        # Log distance statistics
        logger.info(f"[SEARCH] Distance statistics: min={distances.min():.4f}, max={distances.max():.4f}, mean={distances.mean():.4f}, median={np.median(distances):.4f}")
        nan_count = np.isnan(distances).sum()
        inf_count = np.isinf(distances).sum()
        if nan_count > 0:
            logger.warning(f"[SEARCH] Found {nan_count} NaN distances!")
        if inf_count > 0:
            logger.warning(f"[SEARCH] Found {inf_count} Inf distances!")

        # Filter by threshold
        logger.info(f"[SEARCH] Filtering by threshold {threshold}...")
        similar_indices = np.where(distances <= threshold)[0]
        logger.info(f"[SEARCH] Found {len(similar_indices):,} pixels within threshold")
        if len(similar_indices) > 0:
            logger.info(f"[SEARCH] Closest match distance: {distances[similar_indices].min():.4f}")
        else:
            # Log closest pixels even if none match threshold
            closest_10 = np.argsort(distances)[:10]
            logger.info(f"[SEARCH] No matches. Closest 10 distances: {distances[closest_10]}")

        # Limit results to prevent overwhelming the client
        # For 5km x 5km viewports (~250K embeddings), we can handle 250K results
        MAX_RESULTS = 250000
        if len(similar_indices) > MAX_RESULTS:
            logger.info(f"[SEARCH] Limiting results to {MAX_RESULTS} (found {len(similar_indices)})")
            # Sort by distance and take top matches
            sorted_indices = similar_indices[np.argsort(distances[similar_indices])]
            similar_indices = sorted_indices[:MAX_RESULTS]

        # Convert pixel coordinates to lat/lon using geotransform
        logger.info(f"[SEARCH] Converting {len(similar_indices):,} pixels to lat/lon...")
        matches = []
        geotransform = metadata['geotransform']

        for idx in similar_indices:
            px, py = pixel_coords[idx]
            distance = float(distances[idx])

            # Convert pixel (px, py) to lat/lon using geotransform
            # lon = c + px * a  (c = upper_left_x, a = pixel_width)
            # lat = f + py * e  (f = upper_left_y, e = pixel_height, negative)
            lon = geotransform['c'] + px * geotransform['a']
            lat = geotransform['f'] + py * geotransform['e']

            matches.append({
                'lat': lat,
                'lon': lon,
                'distance': distance,
                'pixel': {'x': int(px), 'y': int(py)}
            })

        computation_time = (time.time() - start_time) * 1000  # ms
        logger.info(f"[SEARCH] ✓ Complete! Found {len(matches):,} matches in {computation_time:.0f}ms")

        return jsonify({
            'success': True,
            'matches': matches,
            'query_stats': {
                'total_pixels': len(all_embeddings),
                'matches_found': len(matches),
                'computation_time_ms': round(computation_time, 2),
                'threshold': threshold
            }
        })

    except ValueError as e:
        logger.error(f"[SEARCH] Invalid value: {e}")
        return jsonify({'success': False, 'error': f'Invalid value: {e}'}), 400
    except Exception as e:
        logger.error(f"[SEARCH] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/embeddings/relabel-by-similarity', methods=['POST'])
def api_relabel_by_similarity():
    """Determine which labeled pixels should be relabeled based on refined label averages.

    When new pixels are added to a label class, their average embedding changes (refines).
    This endpoint re-evaluates ALL labeled pixels and finds any that are now closer to
    a different label's average than their current label.

    Request body:
    {
        "label_embeddings": {
            "road": [[128-dim], [128-dim], ...],
            "building": [[128-dim], [128-dim], ...],
            ...
        },
        "labeled_pixels": {
            "x,y": {"label": "road", "embedding": [128-dim], "lat": 13.0045, "lon": 77.5670},
            ...
        }
    }

    Response:
    {
        "success": true,
        "relabeled": [
            {
                "key": "150,200",
                "old_label": "building",
                "new_label": "road",
                "old_distance": 0.45,
                "new_distance": 0.32,
                "lat": 13.0050,
                "lon": 77.5675
            },
            ...
        ],
        "relabel_count": 5,
        "stats": {
            "total_pixels": 15,
            "relabeled_pixels": 5,
            "unchanged_pixels": 10
        }
    }
    """
    try:
        # Parse request
        data = request.get_json()
        label_embeddings = data.get('label_embeddings', {})
        labeled_pixels = data.get('labeled_pixels', {})

        logger.info(f"[RELABEL] Starting relabeling process...")
        logger.info(f"[RELABEL] Labels: {list(label_embeddings.keys())}")
        logger.info(f"[RELABEL] Labeled pixels: {len(labeled_pixels)}")

        # Validate input
        if not label_embeddings:
            return jsonify({
                'success': False,
                'error': 'No label embeddings provided'
            }), 400

        if not labeled_pixels:
            return jsonify({
                'success': True,
                'relabeled': [],
                'relabel_count': 0,
                'stats': {
                    'total_pixels': 0,
                    'relabeled_pixels': 0,
                    'unchanged_pixels': 0
                }
            })

        # Calculate average embedding for each label
        logger.info(f"[RELABEL] Computing label averages...")
        label_avgs = {}
        for label, embeddings in label_embeddings.items():
            if embeddings:  # Only if label has embeddings
                # Keep as float32 - embeddings are already in their native range, not uint8
                emb_array = np.array(embeddings, dtype=np.float32)
                label_avgs[label] = np.mean(emb_array, axis=0)
                logger.info(f"[RELABEL]   {label}: {len(embeddings)} embeddings → avg")
            else:
                logger.warning(f"[RELABEL]   {label}: NO EMBEDDINGS (skipping)")

        if not label_avgs:
            return jsonify({
                'success': False,
                'error': 'No valid labels with embeddings'
            }), 400

        # Re-evaluate each labeled pixel
        logger.info(f"[RELABEL] Re-evaluating {len(labeled_pixels)} labeled pixels...")
        relabeled = []
        unchanged = 0

        # Vectorized computation: convert all pixel embeddings and label averages to arrays
        pixel_keys = list(labeled_pixels.keys())
        pixel_embeddings = np.array([labeled_pixels[k]['embedding'] for k in pixel_keys], dtype=np.float32)

        # Convert label averages to a dict with float32 arrays
        label_avgs_f32 = {label: avg.astype(np.float32) for label, avg in label_avgs.items()}

        # Process pixels in batches
        batch_size = 1000
        for batch_start in range(0, len(pixel_keys), batch_size):
            batch_end = min(batch_start + batch_size, len(pixel_keys))
            batch_keys = pixel_keys[batch_start:batch_end]
            batch_embeddings = pixel_embeddings[batch_start:batch_end]

            for i, key in enumerate(batch_keys):
                pixel_data = labeled_pixels[key]
                current_label = pixel_data['label']
                pixel_emb = batch_embeddings[i]

                # Calculate L2 distance to each label's average
                distances = {}
                for label, label_avg_f32 in label_avgs_f32.items():
                    diff = pixel_emb - label_avg_f32
                    distance = float(np.sqrt(np.sum(diff ** 2)))
                    distances[label] = distance

                # Find closest label
                new_label = min(distances, key=distances.get)
                old_distance = distances[current_label]
                new_distance = distances[new_label]

                # Check if label changed
                if new_label != current_label:
                    relabeled.append({
                        'key': key,
                        'old_label': current_label,
                        'new_label': new_label,
                        'old_distance': round(old_distance, 4),
                        'new_distance': round(new_distance, 4),
                        'lat': pixel_data['lat'],
                        'lon': pixel_data['lon']
                    })
                else:
                    unchanged += 1

        logger.info(f"[RELABEL] ✓ Complete! {len(relabeled)} relabeled, {unchanged} unchanged")

        return jsonify({
            'success': True,
            'relabeled': relabeled,
            'relabel_count': len(relabeled),
            'stats': {
                'total_pixels': len(labeled_pixels),
                'relabeled_pixels': len(relabeled),
                'unchanged_pixels': unchanged
            }
        })

    except Exception as e:
        logger.error(f"[RELABEL] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# UMAP AND HEATMAP API
# ============================================================================

@app.route('/api/viewports/<viewport_name>/compute-umap', methods=['POST'])
def api_compute_umap(viewport_name):
    """Compute UMAP 2D projection for all viewport embeddings."""
    """Load pre-computed UMAP coordinates for visualization."""
    try:
        validate_viewport_name(viewport_name)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    try:
        data = request.get_json()
        year = data.get('year', 2024)

        faiss_dir = FAISS_INDICES_DIR / viewport_name / str(year)
        if not faiss_dir.exists():
            return jsonify({
                'success': False,
                'error': f'FAISS index not found for {viewport_name} ({year})'
            }), 404

        # Load pre-computed UMAP coordinates
        umap_file = faiss_dir / 'umap_coords.npy'
        pixel_coords_file = faiss_dir / 'pixel_coords.npy'
        metadata_file = faiss_dir / 'metadata.json'

        if not umap_file.exists():
            return jsonify({
                'success': False,
                'error': f'UMAP not computed. Run: python3 compute_umap.py {viewport_name} {year}'
            }), 404

        try:
            # Load pre-computed data
            umap_coords = np.load(str(umap_file))        # (N, 2)
            pixel_coords = np.load(str(pixel_coords_file))  # (N, 2)

            with open(metadata_file) as f:
                metadata = json.load(f)

            # Convert pixel coordinates to lat/lon using geotransform
            geotransform = metadata['geotransform']
            a = geotransform['a']
            b = geotransform['b']
            c = geotransform['c']
            d = geotransform['d']
            e = geotransform['e']
            f = geotransform['f']

            lons = c + a * pixel_coords[:, 0] + b * pixel_coords[:, 1]
            lats = f + d * pixel_coords[:, 0] + e * pixel_coords[:, 1]

        except Exception as e:
            logger.error(f"[UMAP] Error loading pre-computed UMAP: {e}")
            return jsonify({
                'success': False,
                'error': f'Error loading UMAP data: {str(e)}'
            }), 500

        # Package result (supports both 2D and 3D UMAP coords)
        has_z = umap_coords.shape[1] >= 3
        points = []
        for i in range(len(lats)):
            point = {
                'lat': float(lats[i]),
                'lon': float(lons[i]),
                'x': float(umap_coords[i, 0]),
                'y': float(umap_coords[i, 1])
            }
            if has_z:
                point['z'] = float(umap_coords[i, 2])
            points.append(point)

        logger.info(f"[UMAP] ✓ Loaded pre-computed UMAP for {len(points):,} points")
        return jsonify({
            'success': True,
            'points': points,
            'num_points': len(points)
        })

    except Exception as e:
        logger.error(f"[UMAP] Unexpected error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/viewports/<viewport_name>/compute-pca', methods=['POST'])
def api_compute_pca(viewport_name):
    """Load pre-computed PCA coordinates for visualization."""
    try:
        validate_viewport_name(viewport_name)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    try:
        data = request.get_json()
        year = data.get('year', 2024)

        faiss_dir = FAISS_INDICES_DIR / viewport_name / str(year)
        if not faiss_dir.exists():
            return jsonify({
                'success': False,
                'error': f'FAISS index not found for {viewport_name} ({year})'
            }), 404

        # Load pre-computed PCA coordinates
        pca_file = faiss_dir / 'pca_coords.npy'
        pixel_coords_file = faiss_dir / 'pixel_coords.npy'
        metadata_file = faiss_dir / 'metadata.json'

        if not pca_file.exists():
            return jsonify({
                'success': False,
                'error': f'PCA not computed. Run: python3 compute_pca.py {viewport_name} {year}'
            }), 404

        try:
            # Load pre-computed data
            pca_coords = np.load(str(pca_file))          # (N, 3)
            pixel_coords = np.load(str(pixel_coords_file))  # (N, 2)

            with open(metadata_file) as f:
                metadata = json.load(f)

            # Convert pixel coordinates to lat/lon using geotransform
            geotransform = metadata['geotransform']
            a = geotransform['a']
            b = geotransform['b']
            c = geotransform['c']
            d = geotransform['d']
            e = geotransform['e']
            f = geotransform['f']

            lons = c + a * pixel_coords[:, 0] + b * pixel_coords[:, 1]
            lats = f + d * pixel_coords[:, 0] + e * pixel_coords[:, 1]

        except Exception as e:
            logger.error(f"[PCA] Error loading pre-computed PCA: {e}")
            return jsonify({
                'success': False,
                'error': f'Error loading PCA data: {str(e)}'
            }), 500

        # Package result (PCA always has 3 components)
        points = []
        for i in range(len(lats)):
            points.append({
                'lat': float(lats[i]),
                'lon': float(lons[i]),
                'x': float(pca_coords[i, 0]),
                'y': float(pca_coords[i, 1]),
                'z': float(pca_coords[i, 2])
            })

        logger.info(f"[PCA] ✓ Loaded pre-computed PCA for {len(points):,} points")
        return jsonify({
            'success': True,
            'points': points,
            'num_points': len(points)
        })

    except Exception as e:
        logger.error(f"[PCA] Unexpected error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/viewports/<viewport_name>/umap-status', methods=['GET'])
def api_umap_status(viewport_name):
    """Check if UMAP exists. UMAP is computed by pipeline orchestration."""
    try:
        validate_viewport_name(viewport_name)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    try:
        year = request.args.get('year', '2024')
        faiss_dir = FAISS_INDICES_DIR / viewport_name / str(year)
        umap_file = faiss_dir / 'umap_coords.npy'
        operation_id = f"{viewport_name}_pipeline"  # Single source of truth
        progress_file = Path(f"/tmp/{operation_id}_progress.json")

        # Already computed
        if umap_file.exists():
            return jsonify({'exists': True, 'computing': False})

        # Check if pipeline is running (UMAP will be computed as part of it)
        if progress_file.exists():
            with open(progress_file) as f:
                progress = json.load(f)
            if progress.get('status') in ('in_progress', 'processing', 'starting', 'downloading'):
                return jsonify({'exists': False, 'computing': True, 'operation_id': operation_id})

        # Not computed and pipeline not running - waiting for pipeline to start
        return jsonify({
            'exists': False,
            'computing': False,
            'waiting': True,
            'message': 'Waiting for pipeline to compute UMAP...'
        })

    except Exception as e:
        logger.error(f"[UMAP] Status error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/viewports/<viewport_name>/pca-status', methods=['GET'])
def api_pca_status(viewport_name):
    """Check if PCA exists. PCA is computed by pipeline orchestration."""
    try:
        validate_viewport_name(viewport_name)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    try:
        year = request.args.get('year', '2024')
        faiss_dir = FAISS_INDICES_DIR / viewport_name / str(year)
        pca_file = faiss_dir / 'pca_coords.npy'
        operation_id = f"{viewport_name}_pipeline"  # Single source of truth
        progress_file = Path(f"/tmp/{operation_id}_progress.json")

        # Already computed
        if pca_file.exists():
            return jsonify({'exists': True, 'computing': False})

        # Check if pipeline is running (PCA will be computed as part of it)
        if progress_file.exists():
            with open(progress_file) as f:
                progress = json.load(f)
            if progress.get('status') in ('in_progress', 'processing', 'starting', 'downloading'):
                return jsonify({'exists': False, 'computing': True, 'operation_id': operation_id})

        # Not computed and pipeline not running - waiting for pipeline to start
        return jsonify({
            'exists': False,
            'computing': False,
            'waiting': True,
            'message': 'Waiting for pipeline to compute PCA...'
        })

    except Exception as e:
        logger.error(f"[PCA] Status error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/embeddings/distance-heatmap', methods=['POST'])
def api_distance_heatmap():
    """Compute pixel-wise Euclidean distance between two years of embeddings (vectorized)."""
    try:
        from scipy.spatial import cKDTree
        import time

        data = request.get_json()
        viewport_id = data.get('viewport_id')
        year1 = data.get('year1', 2024)
        year2 = data.get('year2', 2024)

        if not viewport_id:
            return jsonify({
                'success': False,
                'error': 'viewport_id required'
            }), 400

        validate_viewport_name(viewport_id)

        start_time = time.time()
        logger.info(f"[HEATMAP] Computing distance between {year1} and {year2} for {viewport_id}...")

        # Load FAISS indices for both years
        faiss_dir1 = FAISS_INDICES_DIR / viewport_id / str(year1)
        faiss_dir2 = FAISS_INDICES_DIR / viewport_id / str(year2)

        for faiss_dir in [faiss_dir1, faiss_dir2]:
            if not faiss_dir.exists():
                return jsonify({
                    'success': False,
                    'error': f'FAISS index not found: {faiss_dir}'
                }), 404

        try:
            # Load embeddings and metadata from both years
            all_emb1 = np.load(str(faiss_dir1 / 'all_embeddings.npy'))
            pixel_coords1 = np.load(str(faiss_dir1 / 'pixel_coords.npy'))
            with open(faiss_dir1 / 'metadata.json') as f:
                metadata1 = json.load(f)

            all_emb2 = np.load(str(faiss_dir2 / 'all_embeddings.npy'))
            pixel_coords2 = np.load(str(faiss_dir2 / 'pixel_coords.npy'))
            with open(faiss_dir2 / 'metadata.json') as f:
                metadata2 = json.load(f)

            load_time = time.time()
            logger.info(f"[HEATMAP] Loaded data in {load_time - start_time:.2f}s")

            # Convert pixel coordinates to lat/lon using geotransform for year1
            gt1 = metadata1['geotransform']
            lons1 = gt1['c'] + gt1['a'] * pixel_coords1[:, 0] + gt1['b'] * pixel_coords1[:, 1]
            lats1 = gt1['f'] + gt1['d'] * pixel_coords1[:, 0] + gt1['e'] * pixel_coords1[:, 1]

            # Convert pixel coordinates to lat/lon using geotransform for year2
            gt2 = metadata2['geotransform']
            lons2 = gt2['c'] + gt2['a'] * pixel_coords2[:, 0] + gt2['b'] * pixel_coords2[:, 1]
            lats2 = gt2['f'] + gt2['d'] * pixel_coords2[:, 0] + gt2['e'] * pixel_coords2[:, 1]

        except Exception as e:
            logger.error(f"[HEATMAP] Error loading FAISS data: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({
                'success': False,
                'error': f'Error loading embeddings: {str(e)}'
            }), 500

        # Vectorized coordinate matching using KDTree
        # Build KDTree for year2 coordinates
        coords2 = np.column_stack([lats2, lons2])
        tree2 = cKDTree(coords2)

        # Query for nearest neighbors (tolerance ~1m in lat/lon degrees)
        coords1 = np.column_stack([lats1, lons1])
        distances_to_nearest, indices2 = tree2.query(coords1, k=1, distance_upper_bound=1e-5)

        # Find matched pixels (those within tolerance)
        matched_mask = np.isfinite(distances_to_nearest)
        matched_idx1 = np.where(matched_mask)[0]
        matched_idx2 = indices2[matched_mask]

        match_time = time.time()
        logger.info(f"[HEATMAP] Matched {len(matched_idx1):,} of {len(lats1):,} pixels in {match_time - load_time:.2f}s")

        if len(matched_idx1) == 0:
            return jsonify({
                'success': True,
                'distances': [],
                'stats': {
                    'matched': 0,
                    'unmatched': len(lats1),
                    'total': len(lats1),
                    'min_distance': 0.0,
                    'max_distance': 0.0,
                    'mean_distance': 0.0,
                    'median_distance': 0.0
                }
            })

        # Vectorized distance computation
        emb1_matched = all_emb1[matched_idx1].astype(np.float32)
        emb2_matched = all_emb2[matched_idx2].astype(np.float32)

        # Compute L2 distances for all matched pairs at once
        distance_values = np.linalg.norm(emb1_matched - emb2_matched, axis=1)

        dist_time = time.time()
        logger.info(f"[HEATMAP] Computed {len(distance_values):,} distances in {dist_time - match_time:.2f}s")

        # Get matched coordinates
        lats_matched = lats1[matched_idx1]
        lons_matched = lons1[matched_idx1]

        # Build output list efficiently
        distances = [
            {'lat': float(lat), 'lon': float(lon), 'distance': float(dist)}
            for lat, lon, dist in zip(lats_matched, lons_matched, distance_values)
        ]

        # Compute statistics (already have numpy array)
        min_dist = float(np.min(distance_values))
        max_dist = float(np.max(distance_values))
        mean_dist = float(np.mean(distance_values))
        median_dist = float(np.median(distance_values))

        total_time = time.time() - start_time
        logger.info(f"[HEATMAP] ✓ Complete in {total_time:.2f}s - min: {min_dist:.3f}, max: {max_dist:.3f}, mean: {mean_dist:.3f}")

        return jsonify({
            'success': True,
            'distances': distances,
            'stats': {
                'matched': len(matched_idx1),
                'unmatched': len(lats1) - len(matched_idx1),
                'total': len(lats1),
                'min_distance': min_dist,
                'max_distance': max_dist,
                'mean_distance': mean_dist,
                'median_distance': median_dist,
                'compute_time_ms': int(total_time * 1000)
            }
        })

    except Exception as e:
        logger.error(f"[HEATMAP] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# PERSISTENT LABELS API
# ============================================================================

@app.route('/api/viewports/<viewport_name>/labels', methods=['GET'])
def api_get_viewport_labels(viewport_name):
    """Load all saved labels for a viewport from SQLite database."""
    try:
        validate_viewport_name(viewport_name)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    try:
        labels = get_labels(viewport_name)
        return jsonify({
            'success': True,
            'labels': labels,
            'label_count': len(labels)
        })
    except Exception as e:
        logger.error(f"Error loading labels for viewport {viewport_name}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/viewports/<viewport_name>/labels', methods=['POST'])
def api_save_viewport_label(viewport_name):
    """Save a new label to SQLite database."""
    try:
        validate_viewport_name(viewport_name)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    try:
        label_data = request.get_json()
        label_id = save_label(viewport_name, label_data)
        pixel_count = len(label_data.get('pixels', []))

        return jsonify({
            'success': True,
            'label_id': label_id,
            'pixel_count': pixel_count
        })

    except Exception as e:
        logger.error(f"Error saving label for viewport {viewport_name}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/viewports/<viewport_name>/labels/<label_id>', methods=['DELETE'])
def api_delete_viewport_label(viewport_name, label_id):
    """Delete a specific label from SQLite database."""
    try:
        validate_viewport_name(viewport_name)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    try:
        deleted = delete_label(viewport_name, label_id)

        if not deleted:
            return jsonify({'success': False, 'error': 'Label not found'}), 404

        return jsonify({'success': True, 'label_id': label_id})

    except Exception as e:
        logger.error(f"Error deleting label from viewport {viewport_name}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# CLIENT CONFIG
# ============================================================================

@app.route('/api/config', methods=['GET'])
def get_config():
    """Return client configuration including tile server URL."""
    return jsonify({
        'tile_server': app.config.get('TILE_SERVER_URL', 'http://localhost:5125')
    })


# ============================================================================
# STATIC FILES
# ============================================================================

@app.route('/', methods=['GET'])
def serve_index():
    """Serve the viewport selector HTML."""
    return send_from_directory(app.static_folder, 'viewport_selector.html')


@app.route('/<path:filename>', methods=['GET'])
def serve_static(filename):
    """Serve static files."""
    return send_from_directory(app.static_folder, filename)


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'error': 'Not found'}), 404


@app.errorhandler(500)
def server_error(error):
    logger.error(f"Server error: {error}")
    return jsonify({'success': False, 'error': 'Internal server error'}), 500


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Tessera Web Server')
    parser.add_argument('--prod', action='store_true', help='Disable Flask debug mode for production use')
    parser.add_argument('--port', type=int, default=8001, help='Port to listen on (default: 8001)')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to (default: 0.0.0.0)')
    parser.add_argument('--tile-server', default=None,
                        help='Tile server URL (default: http://localhost:5125, env: TILE_SERVER_URL)')
    args = parser.parse_args()

    # Set tile server URL from CLI flag, env var, or default
    app.config['TILE_SERVER_URL'] = (
        args.tile_server
        or os.environ.get('TILE_SERVER_URL')
        or 'http://localhost:5125'
    )

    debug = not args.prod

    print("Starting Blore Viewport Manager Web Server...")
    print(f"Open http://localhost:{args.port} in your browser")
    if debug:
        print("Debug mode enabled (use --prod to disable)")
    print("Press Ctrl+C to stop")

    # Initialize labels database
    init_labels_db()

    app.run(debug=debug, host=args.host, port=args.port)
