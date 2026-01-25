#!/usr/bin/env python3
"""
Simple Flask web server for viewport management.
Exposes viewport operations as HTTP endpoints.
"""

import sys
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

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.viewport_utils import (
    get_active_viewport,
    get_active_viewport_name,
    list_viewports,
    read_viewport_file
)
from lib.viewport_writer import set_active_viewport, create_viewport_from_bounds

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder=str(Path(__file__).parent.parent / 'public'))
CORS(app)

# Data directories
DATA_DIR = Path.home() / "blore_data"
MOSAICS_DIR = DATA_DIR / "mosaics"
PYRAMIDS_DIR = DATA_DIR / "pyramids"
FAISS_INDICES_DIR = DATA_DIR / "faiss_indices"

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
    return subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=timeout)

def check_viewport_mosaics_exist(viewport_name):
    """Check if embeddings mosaic exists for a viewport (satellite uses Esri/Bing imagery)."""
    embeddings_file = MOSAICS_DIR / f"{viewport_name}_embeddings_2024.tif"
    return embeddings_file.exists()

def check_viewport_pyramids_exist(viewport_name):
    """Check if pyramid tiles exist for a viewport (embeddings only, satellite uses Esri/Bing)."""
    viewport_pyramids_dir = PYRAMIDS_DIR / viewport_name
    pyramid_file = viewport_pyramids_dir / "2024" / "level_0.tif"
    return pyramid_file.exists()

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

def trigger_data_download_and_processing(viewport_name):
    """Download embeddings and create pyramids. Satellite data uses Bing/Esri imagery."""
    def download_and_process():
        try:
            project_root = Path(__file__).parent.parent
            logger.info(f"[DATA] Starting download for viewport '{viewport_name}'...")

            # Download embeddings only (satellite uses Bing/Esri imagery)
            logger.info(f"[DATA] Downloading embeddings for '{viewport_name}'...")
            result = run_script('download_embeddings.py', timeout=1800)
            if result.returncode != 0:
                logger.error(f"[DATA] ✗ Embeddings download failed for '{viewport_name}':\n{result.stderr}")
                return
            logger.info(f"[DATA] ✓ Embeddings downloaded for '{viewport_name}'")

            # Verify embeddings mosaic was actually created
            embeddings_file = MOSAICS_DIR / f"{viewport_name}_embeddings_2024.tif"
            if not embeddings_file.exists():
                logger.error(f"[DATA] ✗ Embeddings mosaic file not found for '{viewport_name}' after download")
                return

            # Create pyramids (satellite layer uses Esri World Imagery)
            logger.info(f"[DATA] Creating pyramids for '{viewport_name}'...")
            result = run_script('create_pyramids.py', timeout=1800)
            if result.returncode != 0:
                logger.error(f"[DATA] ✗ Pyramid creation failed for '{viewport_name}':\n{result.stderr}")
                return
            logger.info(f"[DATA] ✓ Pyramids created for '{viewport_name}'")

        except subprocess.TimeoutExpired:
            logger.error(f"[DATA] ✗ Download/processing timeout for '{viewport_name}'")
        except Exception as e:
            logger.error(f"[DATA] ✗ Error downloading/processing data for '{viewport_name}': {e}")

    thread = threading.Thread(target=download_and_process, daemon=True)
    thread.start()

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
    """Switch to a different viewport and ensure data and FAISS index exist."""
    try:
        data = request.get_json()
        viewport_name = data.get('name')

        if not viewport_name:
            return jsonify({'success': False, 'error': 'Viewport name required'}), 400

        set_active_viewport(viewport_name)

        # Get updated viewport info
        viewport = read_viewport_file(viewport_name)
        viewport['name'] = viewport_name

        response_data = {
            'success': True,
            'message': f'Switched to viewport: {viewport_name}',
            'viewport': viewport,
            'data_ready': True,
            'faiss_ready': False
        }

        # Step 1: Check if mosaics exist, trigger download if not
        if not check_viewport_mosaics_exist(viewport_name):
            logger.info(f"[DATA] Mosaics not found for viewport '{viewport_name}', triggering download...")
            trigger_data_download_and_processing(viewport_name)
            response_data['data_ready'] = False
            response_data['message'] += f'\nDownloading data and creating pyramids (this may take 15-30 minutes)...'

        # Step 2: Check if pyramids exist
        if not check_viewport_pyramids_exist(viewport_name):
            if response_data['data_ready']:
                logger.info(f"[PYRAMIDS] Pyramids not found for viewport '{viewport_name}', triggering creation...")
                # If data is ready but pyramids aren't, trigger pyramid creation
                def create_pyramids_in_background():
                    try:
                        logger.info(f"[PYRAMIDS] Starting pyramid creation for '{viewport_name}'...")
                        result = run_script('create_pyramids.py', timeout=1800)
                        if result.returncode == 0:
                            logger.info(f"[PYRAMIDS] ✓ Pyramid creation complete for '{viewport_name}'")
                        else:
                            logger.error(f"[PYRAMIDS] ✗ Pyramid creation failed for '{viewport_name}':\n{result.stderr}")
                    except subprocess.TimeoutExpired:
                        logger.error(f"[PYRAMIDS] ✗ Pyramid creation timeout for '{viewport_name}'")
                    except Exception as e:
                        logger.error(f"[PYRAMIDS] ✗ Error creating pyramids for '{viewport_name}': {e}")

                thread = threading.Thread(target=create_pyramids_in_background, daemon=True)
                thread.start()
                response_data['message'] += '\nCreating pyramids (this may take 10-15 minutes)...'

        # Step 3: Check if FAISS index exists (only if data and pyramids are ready)
        faiss_dir = FAISS_INDICES_DIR / viewport_name
        faiss_index_file = faiss_dir / 'all_embeddings.npy'

        if response_data['data_ready'] and not faiss_index_file.exists():
            logger.info(f"[FAISS] Index not found for viewport '{viewport_name}', triggering creation...")

            # Trigger FAISS index creation in background thread
            def create_faiss_in_background():
                try:
                    logger.info(f"[FAISS] Starting index creation for '{viewport_name}'...")
                    result = run_script('create_faiss_index.py', timeout=600)
                    if result.returncode == 0:
                        logger.info(f"[FAISS] ✓ Index creation complete for '{viewport_name}'")
                    else:
                        logger.error(f"[FAISS] ✗ Index creation failed for '{viewport_name}':\n{result.stderr}")
                except subprocess.TimeoutExpired:
                    logger.error(f"[FAISS] ✗ Index creation timeout for '{viewport_name}'")
                except Exception as e:
                    logger.error(f"[FAISS] ✗ Error creating index for '{viewport_name}': {e}")

            thread = threading.Thread(target=create_faiss_in_background, daemon=True)
            thread.start()
            response_data['message'] += '\nCreating FAISS index for similarity search (this may take 2-5 minutes)...'
            response_data['faiss_ready'] = False
        elif faiss_index_file.exists():
            logger.info(f"[FAISS] ✓ Index ready for viewport '{viewport_name}'")
            response_data['faiss_ready'] = True
        else:
            logger.info(f"[FAISS] Waiting for data and pyramids before creating index for '{viewport_name}'")
            response_data['faiss_ready'] = False

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

        # Create viewport
        create_viewport_from_bounds(name, bounds, description)

        # Get created viewport info
        viewport = read_viewport_file(name)
        viewport['name'] = name

        # Automatically trigger data download and processing for new viewport
        logger.info(f"[NEW VIEWPORT] Triggering data download for new viewport '{name}'...")
        trigger_data_download_and_processing(name)

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
                viewport_id = get_active_viewport_name()
                faiss_dir = FAISS_INDICES_DIR / viewport_id
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

        # Check for detailed operation progress (e.g., embeddings download)
        try:
            viewport = get_active_viewport()
            viewport_name = viewport['viewport_id']

            # Check for embeddings operation progress file
            embeddings_progress_file = Path(f"/tmp/{viewport_name}_embeddings_progress.json")
            if embeddings_progress_file.exists():
                with open(embeddings_progress_file, 'r') as f:
                    op_progress = json.load(f)
                    # Include detailed message if available
                    if op_progress.get('message'):
                        response['detailed_message'] = op_progress['message']
                    if op_progress.get('current_file'):
                        response['current_file'] = op_progress['current_file']
        except Exception:
            # If detailed progress isn't available, just use the simplified progress
            pass

        return jsonify(response)

    except Exception as e:
        logger.error(f"Error getting progress: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/operations/progress/<operation_id>', methods=['GET'])
def api_operations_progress(operation_id):
    """Get progress of an operation (embeddings, pyramids, FAISS) from progress JSON file."""
    try:
        progress_file = Path(f"/tmp/{operation_id}_progress.json")

        if not progress_file.exists():
            return jsonify({
                'success': False,
                'status': 'not_started',
                'message': 'Operation not started yet'
            }), 200

        with open(progress_file, 'r') as f:
            progress_data = json.load(f)

        return jsonify({
            'success': True,
            **progress_data
        }), 200

    except Exception as e:
        logger.error(f"Error getting operation progress: {e}")
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

        viewports_dir = Path(__file__).parent.parent / 'viewports'
        viewport_file = viewports_dir / f'{viewport_name}.txt'

        # Don't allow deleting files outside viewports directory
        if not viewport_file.resolve().parent == viewports_dir.resolve():
            return jsonify({'success': False, 'error': 'Invalid viewport name'}), 400

        if not viewport_file.exists():
            return jsonify({'success': False, 'error': 'Viewport not found'}), 404

        # Check if this is the active viewport
        active_viewport = get_active_viewport_name()
        if active_viewport == viewport_name:
            return jsonify({
                'success': False,
                'error': 'Cannot delete the active viewport. Switch to another viewport first.'
            }), 400

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
            for mosaic_file in MOSAICS_DIR.glob('*.tif'):
                # Check if mosaic filename starts with viewport name
                if mosaic_file.stem.startswith(viewport_name + '_'):
                    mosaic_file.unlink()
                    deleted_items.append(f"mosaic: {mosaic_file.name}")
                    logger.info(f"✓ Deleted mosaic: {mosaic_file.name}")

        # Delete viewport-specific pyramid directory
        if PYRAMIDS_DIR.exists():
            try:
                viewport_pyramids_dir = PYRAMIDS_DIR / viewport_name
                if viewport_pyramids_dir.exists():
                    import shutil
                    shutil.rmtree(viewport_pyramids_dir)
                    deleted_items.append(f"pyramids directory: {viewport_name}/")
                    logger.info(f"✓ Deleted pyramids directory: {viewport_name}/")
            except Exception as e:
                logger.warning(f"Error deleting pyramids directory for {viewport_name}: {e}")

        # Delete FAISS indices directory for this viewport
        if FAISS_INDICES_DIR.exists():
            try:
                faiss_viewport_dir = FAISS_INDICES_DIR / viewport_name
                if faiss_viewport_dir.exists():
                    import shutil
                    shutil.rmtree(faiss_viewport_dir)
                    deleted_items.append(f"FAISS index directory: {viewport_name}/")
                    logger.info(f"✓ Deleted FAISS index directory: {viewport_name}/")
            except Exception as e:
                logger.warning(f"Error deleting FAISS index directory for {viewport_name}: {e}")

        # Delete progress tracking files for this viewport
        tmp_dir = Path('/tmp')
        progress_patterns = [
            f'{viewport_name}_embeddings_progress.json',
            f'{viewport_name}_pyramids_progress.json',
            f'{viewport_name}_faiss_progress.json'
        ]
        for pattern in progress_patterns:
            progress_file = tmp_dir / pattern
            if progress_file.exists():
                try:
                    progress_file.unlink()
                    deleted_items.append(f"progress file: {pattern}")
                    logger.info(f"✓ Deleted progress file: {pattern}")
                except Exception as e:
                    logger.warning(f"Error deleting progress file {pattern}: {e}")

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


@app.route('/api/embeddings/extract', methods=['POST'])
def api_extract_embedding():
    """Extract embedding vector at a given latitude/longitude coordinate."""
    try:
        import rasterio
        from rasterio import windows as rasterio_windows
        import numpy as np

        data = request.get_json()
        lat = float(data.get('lat'))
        lon = float(data.get('lon'))

        # Get active viewport for mosaic file
        viewport_name = get_active_viewport_name()

        # Open the embedding mosaic file (viewport-specific)
        mosaic_file = MOSAICS_DIR / f'{viewport_name}_embeddings_2024.tif'

        if not mosaic_file.exists():
            return jsonify({
                'success': False,
                'error': 'Embedding mosaic file not found'
            }), 404

        with rasterio.open(mosaic_file) as src:
            # Convert lat/lon to pixel coordinates using the geotransform
            # geotransform: (upper_left_x, pixel_width, 0, upper_left_y, 0, pixel_height)
            transform = src.transform

            # Calculate pixel coordinates
            # x = (lon - transform.c) / transform.a
            # y = (lat - transform.f) / transform.e
            px = (lon - transform.c) / transform.a
            py = (lat - transform.f) / transform.e

            # Check if pixel coordinates are within the image
            if not (0 <= px < src.width and 0 <= py < src.height):
                return jsonify({
                    'success': False,
                    'error': 'Pixel coordinates outside mosaic bounds'
                }), 400

            # Read all 128 bands at this pixel location (optimized)
            x_int = int(px)
            y_int = int(py)

            # Read a small window around the pixel (3x3) to ensure we get data
            # Then extract just the center pixel
            window = rasterio_windows.Window(max(0, x_int - 1), max(0, y_int - 1), 3, 3)

            # Read all bands in one operation (much faster than band-by-band)
            all_bands = src.read(window=window)

            # Extract the center pixel (which is at [1, 1] in our 3x3 window)
            center_x = min(1, x_int)
            center_y = min(1, y_int)

            embedding = []
            for band_idx in range(all_bands.shape[0]):
                # Keep as float32 to match FAISS index (which uses float32)
                pixel_value = float(all_bands[band_idx, center_y, center_x])
                embedding.append(pixel_value)

            logger.info(f"Extracted embedding at ({lat:.6f}, {lon:.6f}) - pixel ({x_int}, {y_int})")

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

        logger.info(f"[SEARCH] Query: threshold={threshold}, viewport={viewport_id}")

        # Check if FAISS index exists
        faiss_dir = FAISS_INDICES_DIR / viewport_id
        if not faiss_dir.exists():
            logger.warning(f"[SEARCH] FAISS index not found: {faiss_dir}")
            return jsonify({
                'success': False,
                'error': f'FAISS index not found for viewport {viewport_id}. Please run data processing first.'
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
        MAX_RESULTS = 10000
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

        for key, pixel_data in labeled_pixels.items():
            current_label = pixel_data['label']
            # Keep as float32 - embeddings are already in their native range, not uint8
            pixel_emb_f32 = np.array(pixel_data['embedding'], dtype=np.float32)

            # Calculate L2 distance to each label's average
            distances = {}
            for label, label_avg in label_avgs.items():
                label_avg_f32 = label_avg.astype(np.float32)
                diff = pixel_emb_f32 - label_avg_f32
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
                logger.info(f"[RELABEL]   {key}: {current_label} ({old_distance:.4f}) → {new_label} ({new_distance:.4f})")
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
    print("Starting Blore Viewport Manager Web Server...")
    print("Open http://localhost:8001 in your browser")
    print("Press Ctrl+C to stop")
    app.run(debug=True, host='0.0.0.0', port=8001)
