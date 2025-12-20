# TEE Complete Workflow Guide

## Overview

This document describes the complete end-to-end workflow for the TESSERA Embedding Explorer (TEE):

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. Select Viewport & Save to viewport.txt                            │
│    (Frontend: ViewportSelector.svelte → Backend: /api/save-viewport)│
└─────────────────────────────────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 2. Download Data (Embeddings + Satellite RGB)                       │
│    (Python scripts read from viewport.txt)                          │
│    - download_embeddings_blore.py                                   │
│    - download_satellite_rgb_blore.py                                │
│    - download_google_earth_blore.py                                 │
│    Saves to: mosaics/                                               │
└─────────────────────────────────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 3. Create Pyramids (6 zoom levels per year)                        │
│    (create_pyramids_blore.py)                                       │
│    Reads: mosaics/                                                  │
│    Creates: pyramids/{YEAR}/level_0.tif - level_5.tif             │
│            pyramids/satellite/level_0.tif - level_5.tif           │
└─────────────────────────────────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 4. Serve Tiles (Flask Tile Server)                                  │
│    (tile_server_blore.py)                                           │
│    - Dynamically detects available pyramids                         │
│    - Serves tiles on http://localhost:5125                          │
│    - Endpoints:                                                     │
│      /tiles/{year}/{z}/{x}/{y}.png                                  │
│      /bounds/{year}                                                 │
│      /health                                                        │
└─────────────────────────────────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 5. View in 3-Panel Viewer                                           │
│    (bangalore_viewer_blore.html)                                    │
│    - Fetches bounds from tile server                                │
│    - Displays 9 synchronized maps (8 years + satellite)             │
│    - Click to label features                                        │
│    - Export labels as JSON                                          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Step 1: Select & Save Viewport

### Option A: Using Frontend GUI (Recommended)

1. Start the frontend (Vite dev server):
   ```bash
   npm run dev
   ```

2. Open browser to `http://localhost:5173`

3. Click "Select Viewport" or see the ViewportSelector component

4. Click on the map to select a 20km × 20km viewport

5. Click **"Save Viewport"** button

**What happens:**
- Frontend calls `POST /api/save-viewport`
- Backend writes to `/Users/skeshav/tee/viewport.txt`
- File contains center coordinates and bounds in parseable format

### Option B: Manual File Edit

Edit `viewport.txt` directly with format:
```
Viewport Configuration
=====================

Center (degrees):
  Latitude:  1.711508°
  Longitude: -52.040405°

Bounds (degrees):
  Min Latitude:  1.621677°
  Max Latitude:  1.801340°
  Min Longitude: -52.130276°
  Max Longitude: -51.950534°

Size: 20km × 20km

Generated: 2025-12-18T09:25:06.740162
```

**Verification:**
```bash
python3 -c "
import re
from pathlib import Path
content = Path('viewport.txt').read_text()
min_lat = float(re.search(r'Min Latitude:\s*([-\d.]+)°', content).group(1))
print(f'✓ Viewport parsed: {min_lat}°')
"
```

---

## Step 2: Download Data

All scripts read from `viewport.txt` automatically. No configuration needed!

### Download Embeddings (Tessera)
```bash
python3 download_embeddings_blore.py
```

**Output:**
- `embeddings/` - Cached tiles from GeoTessera
- `mosaics/bangalore_2017.tif` through `mosaics/bangalore_2024.tif`

### Download Sentinel-2 RGB
```bash
python3 download_satellite_rgb_blore.py
```

**Output:**
- `mosaics/satellite_rgb.tif` (2024 RGB composite)

### Download Google Earth RGB (Optional)
```bash
python3 download_google_earth_blore.py
```

**Output:**
- `mosaics/google_earth_rgb.tif`

**Note:** Requires Earth Engine authentication

---

## Step 3: Create Pyramids

Create 6-level zoom pyramids from downloaded mosaics:

```bash
python3 create_pyramids_blore.py
```

**Input:**
- `mosaics/bangalore_*.tif` (Tessera embeddings)
- `mosaics/satellite_rgb.tif` (Sentinel-2)

**Output:**
```
pyramids/
├── 2017/
│   ├── level_0.tif (full resolution)
│   ├── level_1.tif (1/2 resolution)
│   ├── ...
│   └── level_5.tif (1/32 resolution)
├── 2018/ ... ├── 2024/
└── satellite/
    ├── level_0.tif
    ├── level_1.tif
    ├── ...
    └── level_5.tif
```

**Verification:**
```bash
ls -la pyramids/2024/
ls -la pyramids/satellite/
```

---

## Step 4: Start Tile Server

Serve pyramid tiles dynamically:

```bash
cd /Users/skeshav/tee
python3 tile_server_blore.py
```

**Output:**
```
Starting Tessera Tile Server (viewport-aware)...
Serving tiles from: /Users/skeshav/tee/pyramids
Available maps: 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, satellite

Available endpoints:
  - http://localhost:5125/tiles/<map_id>/<z>/<x>/<y>.png
  - http://localhost:5125/bounds/<map_id>
  - http://localhost:5125/health

Starting server on http://localhost:5125
```

**Test the server:**
```bash
# Check health
curl http://localhost:5125/health

# Get bounds for satellite map
curl http://localhost:5125/bounds/satellite

# Fetch a tile (replace z/x/y with actual values)
curl http://localhost:5125/tiles/2024/8/128/128.png -o /tmp/test.png
```

**Key Features:**
- ✓ Automatically detects available pyramid years
- ✓ Serves 2048×2048 high-resolution tiles
- ✓ Returns transparent tiles for missing data
- ✓ CORS enabled for browser access

---

## Step 5: View in 3-Panel Viewer

### Start the Viewer

Simply open the HTML file in a browser:

```bash
# Option 1: Open directly in browser
open bangalore_viewer_blore.html

# Option 2: Serve with Python
python3 -m http.server 8080 --directory /Users/skeshav/tee

# Then visit: http://localhost:8080/bangalore_viewer_blore.html
```

### What You See

- **9-Panel Grid:**
  - 8 panels showing Tessera embeddings (2017-2024)
  - 1 center panel showing satellite RGB or OpenStreetMap
  - All maps synchronized (zoom/pan together)

- **Interactive Features:**
  - Click on any map to add labeled markers
  - Enter label (e.g., "building", "water", "vegetation")
  - Export labels as JSON
  - Labels persist in browser storage

### Troubleshooting Viewer

**Issue:** Maps show gray/blank
- Tile server not running? Start it: `python3 tile_server_blore.py`
- Wrong port? Check viewer: `TILE_SERVER = 'http://localhost:5125'`
- Pyramids not created? Run: `python3 create_pyramids_blore.py`

**Issue:** Bounds not loading
- Tile server health check: `curl http://localhost:5125/health`
- Browser console (F12) shows errors?

**Issue:** Maps not syncing
- Refresh the page
- Check browser console for JavaScript errors

---

## Complete Workflow Example

```bash
# 1. Select viewport (via frontend or manual edit)
# viewport.txt is already set with your viewport

# 2. Download data
python3 download_embeddings_blore.py      # ~5-15 minutes
python3 download_satellite_rgb_blore.py   # ~2-5 minutes

# 3. Create pyramids
python3 create_pyramids_blore.py           # ~1-2 minutes

# 4. Start tile server (keep running)
python3 tile_server_blore.py &

# 5. Open viewer
open bangalore_viewer_blore.html
# or
python3 -m http.server 8080 --directory /Users/skeshav/tee
# Then visit http://localhost:8080/bangalore_viewer_blore.html
```

---

## Data Flow Verification

### 1. Viewport.txt Parsing

All Python scripts use the same parser:

```python
import re
from pathlib import Path

VIEWPORT_FILE = Path("viewport.txt")

def parse_viewport_bounds():
    with open(VIEWPORT_FILE, 'r') as f:
        content = f.read()

    min_lat_match = re.search(r'Min Latitude:\s*([-\d.]+)°', content)
    max_lat_match = re.search(r'Max Latitude:\s*([-\d.]+)°', content)
    min_lon_match = re.search(r'Min Longitude:\s*([-\d.]+)°', content)
    max_lon_match = re.search(r'Max Longitude:\s*([-\d.]+)°', content)

    bbox = (
        float(min_lon_match.group(1)),
        float(min_lat_match.group(1)),
        float(max_lon_match.group(1)),
        float(max_lat_match.group(1))
    )
    return bbox
```

### 2. Download Scripts

All three use the parsed BBOX:

```python
BBOX = parse_viewport_bounds()  # Reads from viewport.txt

# Then use BBOX:
# - download_embeddings_blore.py: tessera.fetch_mosaic_for_region(bbox=BBOX)
# - download_satellite_rgb_blore.py: catalog.search(bbox=[...])
# - download_google_earth_blore.py: ee.Geometry.Rectangle([...])
```

### 3. Pyramid Creation

Looks for downloaded files:

```python
tessera_file = MOSAICS_DIR / f"bangalore_{year}.tif"
satellite_file = MOSAICS_DIR / "satellite_rgb.tif"
```

### 4. Tile Server

Dynamically discovers pyramids:

```python
def get_year_range():
    years = []
    if PYRAMIDS_DIR.exists():
        for item in PYRAMIDS_DIR.iterdir():
            if item.name.isdigit():
                years.append(item.name)
            elif item.name == 'satellite':
                years.append(item.name)
    return sorted(years)
```

### 5. Viewer

Fetches bounds from tile server:

```javascript
async function loadViewportBounds() {
    const response = await fetch(`${TILE_SERVER}/bounds/satellite`);
    const data = await response.json();
    if (data.center) {
        center = data.center;
        console.log('Loaded viewport center from tile server:', center);
    }
}
```

---

## File Structure After Complete Setup

```
/Users/skeshav/tee/
├── viewport.txt                    # ← User-selected viewport
├── download_embeddings_blore.py
├── download_satellite_rgb_blore.py
├── download_google_earth_blore.py
├── create_pyramids_blore.py
├── tile_server_blore.py
├── bangalore_viewer_blore.html    # ← Open this in browser
├── embeddings/                     # ← Cache (can delete after pyramids created)
│   └── [GeoTessera cached tiles]
├── mosaics/                        # ← Downloaded data
│   ├── bangalore_2017.tif
│   ├── bangalore_2018.tif
│   ├── ...
│   ├── bangalore_2024.tif
│   └── satellite_rgb.tif
└── pyramids/                       # ← Multi-resolution tiles (used by server)
    ├── 2017/
    │   ├── level_0.tif
    │   ├── level_1.tif
    │   ├── ...
    │   └── level_5.tif
    ├── 2018/ ... ├── 2024/
    └── satellite/
        ├── level_0.tif
        ├── ...
        └── level_5.tif
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `viewport.txt` not found | Manually create it with desired bounds or use frontend to save |
| Downloads fail | Check network, verify BBOX is valid, check GeoTessera API |
| Pyramids create but are blank | Check `mosaics/` files are valid GeoTIFFs |
| Tile server crashes | Check `pyramids/` directory exists, check port 5125 not in use |
| Viewer shows gray tiles | Tile server not running or TILE_SERVER URL wrong in HTML |
| Viewer won't load | Check browser console (F12) for errors, verify tile server is running |

---

## Next Steps

1. **Change Viewport:** Edit `viewport.txt` or use frontend "Save Viewport"
2. **Add More Years:** Download additional years, re-run pyramid creation
3. **Improve Visualization:** Implement better color mapping for 128D embeddings
4. **Performance Optimization:** Profile bottlenecks, optimize tile server caching

---

## Architecture Notes

- **Viewport-Agnostic:** Same code works for any 20km × 20km region
- **Modular:** Each step is independent Python script
- **Scalable:** Pyramid levels allow fast viewing at any zoom
- **Web-Ready:** Standard Leaflet maps, no custom rendering needed
- **Persistent:** Labels stored in browser localStorage

---

## API Endpoints (Backend)

```
POST /api/save-viewport
  - Saves viewport coordinates to viewport.txt
  - Input: { center: [lon, lat], bounds: {...}, sizeKm: 20 }

POST /api/viewports/process
  - Starts async viewport processing (download + pyramids)

GET /api/viewports/{task_id}/status
  - Check processing progress

GET /api/health
  - Health check
```

---

## Tile Server Endpoints

```
GET /tiles/{year}/{z}/{x}/{y}.png
  - Serve tile for year (2017-2024) or 'satellite'

GET /bounds/{year}
  - Get GeoTIFF bounds and center

GET /health
  - Health check, lists available maps
```

---

## Version Information

- **Frontend:** Svelte + TypeScript + Vite
- **Backend:** FastAPI (Python 3.13)
- **Tile Server:** Flask
- **Maps:** Leaflet.js
- **Geospatial:** rio-tiler, rasterio, GeoTessera
