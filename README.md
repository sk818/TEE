# TESSERA Embedding Explorer (TEE)

A streamlined web-based viewer for exploring TESSERA embeddings via multi-resolution image pyramids and tile-based visualization.

## Workflow

The TEE project implements a simple, focused workflow:

1. **Select Viewport** → Choose a geographic area (1km × 1km or larger)
2. **Download Embeddings** → Fetch TESSERA embeddings for the selected area
3. **Create Pyramids** → Generate multi-resolution RGB image pyramids
4. **Serve Tiles** → Serve pyramid levels via tile server
5. **View** → Visualize with synchronized 2-panel viewer (RGB + OSM)

## Quick Start

### Prerequisites

- Python 3.8+
- Node.js 16+
- Modern browser (Chrome, Edge, Safari)

### Installation

```bash
# Install Python dependencies
pip install -r backend/requirements.txt

# Install Node dependencies
npm install
```

### Running the System

**Terminal 1 - Start Backend API:**
```bash
cd backend
python main.py
# Runs on http://localhost:8000
```

**Terminal 2 - Start Tile Server:**
```bash
cd backend
python tile_server.py
# Runs on http://localhost:8001
```

**Terminal 3 - Start Frontend:**
```bash
npm run dev
# Runs on http://localhost:5173
```

Then open http://localhost:5173 in your browser.

## Usage

1. **Select Viewport**:
   - Click the map to place viewport center
   - System generates UUID for viewport

2. **Download Embeddings**:
   - Click "Download Embeddings" button
   - System downloads TESSERA embeddings
   - Automatically extracts RGB from embeddings

3. **Automatic Pyramid Creation**:
   - Pyramids created automatically after RGB extraction
   - 5 levels: 1m → 3.16m → 10m → 31.6m → 100m/pixel
   - Cached by default (skips recreation if unchanged)

4. **View in 2-Panel Viewer**:
   - Left panel: RGB image pyramids (from tile server)
   - Right panel: OpenStreetMap basemap
   - Synchronized zoom/pan across both panels

## Project Structure

```
tee/
├── backend/
│   ├── main.py                      # FastAPI backend
│   ├── tile_server.py               # Tile serving (port 8001)
│   ├── processing/
│   │   ├── download_embeddings.py   # TESSERA downloader
│   │   ├── extract_rgb.py           # RGB extraction
│   │   └── create_rgb_pyramids.py   # Pyramid builder
│   └── requirements.txt
├── src/
│   ├── components/
│   │   └── ViewportSelector.svelte  # Viewport selection UI
│   └── App.svelte                   # Main app
├── public/
│   ├── viewer.html                  # 2-panel viewer
│   └── data/                        # Viewport data
│       └── viewports/
│           └── {viewport_id}/
│               ├── embeddings_2024.tif
│               ├── rgb_2024.tif
│               └── pyramids/
│                   └── 2024/
│                       ├── level_0.tif (1m/pixel)
│                       ├── level_1.tif (3.16m/pixel)
│                       ├── level_2.tif (10m/pixel)
│                       ├── level_3.tif (31.6m/pixel)
│                       └── level_4.tif (100m/pixel)
└── deprecated/                      # Old files and unused code
```

## Pyramid Structure

Each pyramid has 5 levels with √10 (≈ 3.162x) zoom factor:

| Level | Resolution | Use Case |
|-------|-------------|----------|
| 0 | 1m/pixel | Highest zoom (fine detail) |
| 1 | 3.16m/pixel | Intermediate zoom |
| 2 | 10m/pixel | Medium zoom (typical view) |
| 3 | 31.6m/pixel | Zoomed out |
| 4 | 100m/pixel | Lowest zoom (overview) |

**Display Characteristics:**
- At highest zoom: 400×400 screen pixels = 40×40 embeddings = 400m×400m area
- 1 screen pixel = 1m ground coverage at max zoom
- Each zoom level transitions smoothly with √10 factor

## API Endpoints

### Backend (port 8000)

- `POST /api/save-viewport` - Save viewport bounds and create directory
- `POST /api/download-embeddings` - Start embeddings download task
- `GET /api/tasks/{task_id}/status` - Check download progress
- `GET /api/viewport-info` - Get current viewport info

### Tile Server (port 8001)

- `GET /api/tiles/rgb/{viewport_id}/{year}/{z}/{x}/{y}.png` - RGB pyramid tiles
- `GET /api/tiles/embeddings/{viewport_id}/{year}/{z}/{x}/{y}.png` - Embedding pyramid tiles
- `GET /api/tiles/bounds/{viewport_id}/{year}` - Get viewport bounds

## Performance

- Viewport selection: < 100ms
- Embedding download: 30-60 seconds (depending on size)
- Pyramid creation: 5-10 seconds (cached on repeat)
- Tile serving: < 100ms per tile
- Map pan/zoom: 60 FPS

## Caching

- **Embeddings**: Cached by viewport bounds (skips re-download if unchanged)
- **RGB**: Cached alongside embeddings
- **Pyramids**: Cached by checking source file modification time
  - If embeddings unchanged, pyramid generation skipped
  - Metadata saved in `pyramid_metadata.json`

## Troubleshooting

### No tiles showing in viewer
- Check tile server is running (port 8001)
- Verify viewport has been created and embeddings downloaded
- Check browser console for network errors

### Slow tile loading
- Ensure tile server has access to pyramid files
- Check network bandwidth
- Monitor server CPU/memory usage

### Out of memory
- Reduce viewport size
- Close other browser tabs
- Clear browser cache

## Files

See `deprecated/README.md` for information about old code and experimental features.

## License

MIT

---

**Version**: 2.0.0 (Streamlined)
**Last Updated**: December 2024
