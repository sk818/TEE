#!/usr/bin/env python3
"""
Tile server for Tessera embeddings
Serves map tiles dynamically from pyramid GeoTIFFs
Reads viewport and year range from viewport.txt
"""

from flask import Flask, send_file, jsonify
from flask_cors import CORS
from rio_tiler.io import Reader
from rio_tiler.models import ImageData
from pathlib import Path
import io
from PIL import Image
import numpy as np
import re

app = Flask(__name__)
CORS(app)

PYRAMIDS_DIR = Path("pyramids")
VIEWPORT_FILE = Path("viewport.txt")

def get_year_range():
    """Get year range from available pyramid directories."""
    years = []
    if PYRAMIDS_DIR.exists():
        for item in PYRAMIDS_DIR.iterdir():
            if item.is_dir():
                # Check if it's a year (numeric) or special dir like 'satellite'
                if item.name.isdigit():
                    years.append(item.name)
                elif item.name == 'satellite':
                    years.append(item.name)
    return sorted(years)

YEARS = get_year_range() if get_year_range() else [str(y) for y in range(2017, 2025)] + ['satellite']

# Cache for tile readers
readers = {}

def get_reader(map_id, zoom_level):
    """Get or create a Reader for a specific map and zoom level."""
    # Map web zoom levels to pyramid levels (we have 6 levels: 0-5)
    # With tileSize=2048 and zoomOffset=-3, Leaflet requests z=3 to z=14
    # Map z=14 → level 0 (most detail), z=3 → level 5 (least detail)
    # Use floor division to spread 12 zoom levels across 6 pyramid levels
    pyramid_level = max(0, min(5, (14 - zoom_level) // 2))

    key = f"{map_id}_{pyramid_level}"

    if key not in readers:
        if map_id == 'satellite':
            tif_path = PYRAMIDS_DIR / 'satellite' / f'level_{pyramid_level}.tif'
        else:
            tif_path = PYRAMIDS_DIR / map_id / f'level_{pyramid_level}.tif'

        if tif_path.exists():
            readers[key] = str(tif_path)
        else:
            return None

    return readers[key]

def mercator_to_tile(lon, lat, zoom):
    """Convert lon/lat to tile coordinates at given zoom level."""
    import math
    n = 2.0 ** zoom
    x_tile = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y_tile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x_tile, y_tile

def tile_to_bbox(x, y, zoom):
    """Convert tile coordinates to bounding box."""
    import math
    n = 2.0 ** zoom
    lon_min = x / n * 360.0 - 180.0
    lon_max = (x + 1) / n * 360.0 - 180.0
    lat_max_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat_min_rad = math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n)))
    lat_max = math.degrees(lat_max_rad)
    lat_min = math.degrees(lat_min_rad)
    return (lon_min, lat_min, lon_max, lat_max)

@app.route('/tiles/<map_id>/<int:z>/<int:x>/<int:y>.png')
def get_tile(map_id, z, x, y):
    """Serve a map tile."""
    # Use larger tile size for native resolution
    TILE_SIZE = 2048  # Larger tiles = minimal downsampling, near-native pixels

    try:
        tif_path = get_reader(map_id, z)

        if not tif_path:
            # Return transparent tile if file doesn't exist
            img = Image.new('RGBA', (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)
            return send_file(buf, mimetype='image/png')

        # Get tile bounds
        bbox = tile_to_bbox(x, y, z)

        # Read tile from GeoTIFF
        with Reader(tif_path) as src:
            # Try to read the tile
            try:
                img_data = src.part(bbox, width=TILE_SIZE, height=TILE_SIZE)

                # Convert to RGB
                if img_data.data.shape[0] == 1:
                    # Single band - convert to grayscale
                    arr = img_data.data[0]
                    rgb = np.stack([arr, arr, arr], axis=0)
                else:
                    # Already RGB
                    rgb = img_data.data[:3]

                # Transpose to (H, W, C) for PIL
                rgb_t = np.transpose(rgb, (1, 2, 0))

                # Create PIL image
                img = Image.fromarray(rgb_t.astype(np.uint8), mode='RGB')

                # Save to buffer
                buf = io.BytesIO()
                img.save(buf, format='PNG')
                buf.seek(0)

                return send_file(buf, mimetype='image/png')

            except Exception as e:
                # Return transparent tile on error
                print(f"Error reading tile {map_id}/{z}/{x}/{y}: {e}")
                img = Image.new('RGBA', (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
                buf = io.BytesIO()
                img.save(buf, format='PNG')
                buf.seek(0)
                return send_file(buf, mimetype='image/png')

    except Exception as e:
        print(f"Error serving tile: {e}")
        return f"Error: {e}", 500

@app.route('/bounds/<map_id>')
def get_bounds(map_id):
    """Get bounds for a map."""
    try:
        if map_id == 'satellite':
            tif_path = PYRAMIDS_DIR / 'satellite' / 'level_0.tif'
        else:
            tif_path = PYRAMIDS_DIR / map_id / 'level_0.tif'

        if tif_path.exists():
            with Reader(str(tif_path)) as src:
                bounds = src.bounds
                return jsonify({
                    'bounds': bounds,
                    'center': [(bounds[1] + bounds[3])/2, (bounds[0] + bounds[2])/2]
                })
        else:
            return jsonify({'error': 'File not found'}), 404

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'ok',
        'maps_available': [m for m in YEARS if (PYRAMIDS_DIR / m / 'level_0.tif').exists() if m != 'satellite'] +
                         (['satellite'] if (PYRAMIDS_DIR / 'satellite' / 'level_0.tif').exists() else [])
    })

if __name__ == '__main__':
    print("Starting Tessera Tile Server (viewport-aware)...")
    print(f"Serving tiles from: {PYRAMIDS_DIR.absolute()}")
    print(f"Available maps: {', '.join(YEARS)}")
    print("\nAvailable endpoints:")
    print("  - http://localhost:5125/tiles/<map_id>/<z>/<x>/<y>.png")
    print("  - http://localhost:5125/bounds/<map_id>")
    print("  - http://localhost:5125/health")
    print("\nStarting server on http://localhost:5125")
    app.run(debug=True, port=5125, threaded=True)
