# TEE: Tessera Embeddings Explorer

A comprehensive system for downloading, processing, and visualizing Sentinel-2 satellite embeddings across multiple years (2017-2025) with an interactive web interface for geographic viewports.

## Overview

TEE (Tessera Embeddings Explorer) integrates geospatial data processing with deep learning embeddings to create an interactive platform for exploring satellite imagery over time. The system:

- **Downloads** Tessera embeddings from GeoTessera for multiple years
- **Processes** embeddings into RGB visualizations and pyramid structures
- **Builds** FAISS indices for efficient similarity search
- **Visualizes** embeddings through an interactive web-based viewer
- **Enables** temporal analysis by switching between years

## Features

### Multi-Year Support
- Download embeddings for years 2017-2025 (depending on data availability)
- Select which years to process during viewport creation
- Switch between years instantly in the viewer
- Temporal coherence in similarity search through year-specific FAISS indices

### Interactive Viewer
- Zoomable, pannable map interface using Leaflet.js
- Real-time embedding visualization with year selector
- Pixel-level extraction of embeddings
- Similarity search to find matching locations across the viewport

### Viewport Management
- Create custom geographic viewports interactively
- Preset viewports for common regions (tile-aligned, Bangalore, Malleswaram)
- Multi-year processing with progress tracking
- Automatic navigation to viewer after processing

### Explorer Mode
- Click pixels on the embedding map to extract embeddings
- Find similar pixels using FAISS similarity search
- Visualize search results with similarity thresholds
- Real-time distance metrics

### Advanced Viewer: 6-Panel Exploration & Temporal Analysis
The **Advanced Viewer** extends the standard viewer with a comprehensive 6-panel layout for advanced analysis:

#### Layout
1. **Panel 1 (OSM)** - OpenStreetMap base layer (geographic reference)
2. **Panel 2 (RGB)** - Satellite RGB imagery with label painting tools
3. **Panel 3 (Embeddings Y1)** - First year embeddings with similarity search
4. **Panel 4 (UMAP)** - 2D UMAP projection of embedding space (auto-computed on load)
5. **Panel 5 (Heatmap)** - Temporal distance heatmap (Y1 vs Y2 pixel-by-pixel differences)
6. **Panel 6 (Embeddings Y2)** - Second year embeddings for temporal comparison

#### Features
- **One-Click Similarity Search** - Click any pixel to instantly search for similar pixels across the viewport
- **Real-Time Threshold Control** - Adjust the similarity slider to dynamically filter results
- **Persistent Colored Overlays** - Save similarity search results as named labels with custom colors
- **UMAP Visualization** - Automatic 2D projection of 128D embeddings with satellite RGB coloring
- **Temporal Distance Heatmap** - Tile-based L2 distance computation between years with adaptive subsampling
- **Temporal Analysis** - Switch Panel 6 year independently to compare embedding changes over time
- **Label Management** - Toggle label visibility, delete labels, view pixel counts per label
- **Year-Based Label Updates** - Labels automatically refresh when switching years to show changes in classification

#### How to Use
1. Open the **Viewport Selector** and choose a viewport
2. Select **"Advanced Viewer"** from the viewer dropdown
3. **Explore embeddings:**
   - Panel 3/6: Click pixels to search for similar locations
   - Adjust threshold slider for real-time filtering
   - All panels stay synchronized as you pan/zoom
4. **Analyze UMAP projection:**
   - Panel 4 automatically shows 2D embedding space
   - Colors reflect satellite RGB at each location
   - Click UMAP points to highlight corresponding geographic locations
5. **Compare temporal changes:**
   - Select different year in Panel 6
   - Panel 5 shows pixel-by-pixel embedding distance between years
   - Blue = similar embeddings, Red = different embeddings
6. **Create labels:**
   - Click "💾 Save Current as Label" to save similarity search results
   - Labels automatically color-code UMAP points
   - Toggle visibility or delete as needed

#### Label Data
- Labels are saved as **persistent JSON files** in `viewports/{viewport_name}_labels.json`
- Includes source pixel coordinates, threshold settings, and matched pixels with distances
- Survives page reloads - your labels are always preserved
- Automatically refresh when switching years to track temporal changes

## Quick Start

### Prerequisites

- Python 3.8+
- Virtual environment (venv or conda)
- ~5GB storage per viewport (varies by number of years)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/sk818/TEE.git blore
   cd blore
   ```

2. **Create and activate virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up GeoTessera authentication** (if needed):
   - Create `.env` file with GeoTessera credentials
   - Or export environment variables as needed

### Usage

1. **Start the web server:**
   ```bash
   python3 backend/web_server.py
   ```
   Server runs on http://localhost:8001

2. **Open the viewport selector:**
   Navigate to http://localhost:8001 in your browser

3. **Create a new viewport:**
   - Click "+ Create New Viewport"
   - Click on the map to set location or enter bounds manually
   - Select which years to download (default: 2024)
   - Click "Create"
   - Wait for automatic processing (downloading, RGB creation, pyramid building, FAISS indexing)
   - Viewer automatically opens when complete

4. **Explore embeddings:**
   - Use the year selector dropdown to switch between years
   - Zoom and pan the embedding map
   - Click pixels in explorer mode to find similar locations
   - Adjust similarity threshold to see more/fewer results

## Project Structure

```
blore/
├── README.md                          # This file
├── requirements.txt                   # Python dependencies
│
├── public/                            # Web interface
│   ├── viewer.html                    # Standard embedding viewer with map interface
│   ├── experimental_viewer.html       # Advanced 6-panel viewer with UMAP & temporal analysis
│   ├── viewport_selector.html         # Viewport creation and management
│   └── README.md                      # Frontend documentation
│
├── backend/                           # Flask web server
│   └── web_server.py                  # API endpoints and server
│
├── lib/                               # Python utilities
│   ├── pipeline.py                    # Unified pipeline orchestration (single source of truth)
│   ├── viewport_utils.py              # Viewport file operations
│   ├── viewport_writer.py             # Viewport configuration writer
│   └── progress_tracker.py            # Progress tracking utilities
│
├── viewports/                         # Viewport configurations
│   ├── tile_aligned.txt               # Preset: tile-aligned viewport
│   ├── bangalore_10km.txt             # Preset: Bangalore region
│   └── malleswaram_500m.txt           # Preset: Malleswaram neighborhood
│
├── download_embeddings.py             # GeoTessera embedding downloader
├── create_rgb_embeddings.py           # Convert embeddings to RGB
├── create_pyramids.py                 # Build zoom-level pyramid structure
├── create_faiss_index.py              # Build similarity search indices
├── compute_umap.py                    # Compute 2D UMAP projection for embeddings
├── setup_viewport.py                  # Orchestrate full workflow (download → FAISS → UMAP)
├── SETUP_WORKFLOW.md                  # Comprehensive workflow documentation
│
├── save.sh                            # Backup script
├── restore.sh                         # Restore script
└── restart.sh                         # Restart servers script
```

## Data Pipeline

The system processes satellite embeddings through five main stages with **parallel multi-year processing**:

### Unified Orchestration (lib/pipeline.py)

All pipeline execution flows through `lib/pipeline.py::PipelineRunner`, providing a single source of truth for:
- Both web-based viewport creation (`api_create_viewport`)
- Command-line setup (`setup_viewport.py`)
- Consistent error handling and verification across entry points

### Pipeline Stages (Parallel Per-Year)

Each stage processes **all selected years in parallel** through single script calls:

### 1. Download Embeddings
```bash
python3 download_embeddings.py --years 2017,2021,2025
```
- Connects to GeoTessera
- Downloads Sentinel-2 embeddings for selected years (in parallel)
- Saves as GeoTIFF files in `blore_data/mosaics/`
- ✓ Multi-year support: Downloads all years concurrently

### 2. Create RGB Visualizations
```bash
python3 create_rgb_embeddings.py
```
- Converts 512D embeddings to RGB using PCA
- Processes all downloaded years in parallel
- Outputs to `blore_data/mosaics/rgb/`

### 3. Build Pyramid Structure
```bash
python3 create_pyramids.py
```
- Creates multi-level zoom pyramids (0-5) for all years
- Stores tiles at different resolutions
- Enables efficient web-based viewing
- **✓ Viewer becomes available** once ANY year has pyramids
- Output: `blore_data/pyramids/{viewport}/{year}/`

### 4. Create FAISS Indices
```bash
python3 create_faiss_index.py
```
- Builds vector similarity search indices for all years
- Year-specific indices for temporal coherence
- Enables fast similarity queries
- **✓ Labeling controls become available** once ANY year has FAISS
- Output: `blore_data/faiss_indices/{viewport}/{year}/`

### 5. Compute UMAP (Optional)
```bash
python3 compute_umap.py {viewport_name} {year}
```
- Computes 2D UMAP projection from first completed year
- Used by Advanced Viewer for visualization (Panel 4)
- Takes 1-2 minutes for 264K embeddings
- **✓ UMAP visualization becomes available** once computed
- Output: `blore_data/faiss_indices/{viewport}/{year}/umap_coords.npy`

### 6. View in Browser
- Pyramid tiles served at http://localhost:5125
- Embeddings displayed in interactive viewer
- Similarity search uses FAISS indices
- Advanced Viewer shows UMAP with automatic computation on first load

### Incremental Feature Availability

Features become available progressively as processing completes:

| Stage | Feature | Available When |
|-------|---------|-----------------|
| After Stage 3 (Pyramids) | Basic viewer with maps | ANY year has pyramids |
| After Stage 4 (FAISS) | Labeling/similarity search | ANY year has FAISS index |
| After Stage 5 (UMAP) | UMAP visualization (Panel 4) | UMAP computed for any year |

## Workflow: Complete Setup with UMAP

For a complete end-to-end setup with UMAP visualization (CLI mode):

```bash
./venv/bin/python3 setup_viewport.py --years 2023,2024,2025 --umap-year 2024
```

This orchestrates through unified pipeline (`lib/pipeline.py`):
1. Download embeddings for 2023, 2024, 2025 (in parallel)
2. Create RGB visualizations for all years
3. Build pyramid tiles for all years (**viewer available after this**)
4. Create FAISS indices for each year (**labeling available after this**)
5. Compute UMAP for 2024 (**UMAP visualization available after this**)
6. Output summary of created data

Or use the web interface:
```bash
bash restart.sh
# Open http://localhost:8001
# Click "+ Create New Viewport"
# Select years and click Create
# Processing happens in background with status tracking
# Viewer automatically switches on when pyramids are ready
```

### Web-Based Viewport Creation

When creating a viewport through the web interface:
1. **api_create_viewport()** calls **trigger_data_download_and_processing()**
2. Full pipeline (`PipelineRunner`) runs in background
3. Status is tracked and accessible via `/api/operations/pipeline-status/{viewport_name}`
4. **Viewer only monitors** - it does NOT initiate any processes
5. Features become available progressively as each stage completes

### Key Architectural Change

**Single Source of Truth**: All pipeline logic is now in `lib/pipeline.py::PipelineRunner`, used by:
- Web-based viewport creation
- Command-line `setup_viewport.py`
- Manual API calls

This ensures consistent behavior regardless of entry point.

## Pipeline Architecture

### Unified Orchestration System

TEE uses a unified pipeline orchestration system (`lib/pipeline.py`) that ensures consistent processing regardless of entry point:

```
┌─ Web UI (api_create_viewport)     ─┐
│                                    │
├─ CLI (setup_viewport.py)           ├─→ PipelineRunner.run_full_pipeline()
│                                    │   ├─ Download embeddings
│  All entry points converge on      │   ├─ Create RGB
│  single pipeline implementation    │   ├─ Create pyramids ← Viewer available
│                                    │   ├─ Create FAISS ← Labeling available
└─ Direct API calls                  ┘   └─ Compute UMAP ← UMAP available
```

### Key Design Principles

1. **Single Source of Truth**: All pipeline logic in `lib/pipeline.py`
2. **Incremental Feature Availability**: Features activate as soon as their dependencies complete
3. **Monitoring Only**: Viewer monitors pipeline progress but never initiates processes
4. **Parallel Multi-Year Processing**: All stages process multiple years in parallel
5. **Robust Error Tracking**: All stages track success/failure with detailed error messages

### Status Tracking

Pipeline status is tracked in memory via operation_id: `{viewport_name}_full_pipeline`

```
Status values:
- 'starting': Pipeline initializing
- 'success': All stages completed successfully
- 'failed': One or more stages failed

Current stage tracking:
- 'downloading_embeddings'
- 'creating_rgb'
- 'creating_pyramids'
- 'creating_faiss'
- 'complete' (or 'exception'/'timeout' on error)
```

Check status via:
```bash
curl http://localhost:8001/api/operations/pipeline-status/{viewport_name}
```

Response includes:
```json
{
  "status": "success",
  "current_stage": "complete",
  "error": null
}
```

## API Reference

### Viewport Management

**List all viewports:**
```
GET /api/viewports/list
```

**Get current viewport:**
```
GET /api/viewports/current
```

**Switch viewport:**
```
POST /api/viewports/switch
Content-Type: application/json

{"name": "viewport_name"}
```

**Create new viewport:**
```
POST /api/viewports/create
Content-Type: application/json

{
  "bounds": "min_lon,min_lat,max_lon,max_lat",
  "name": "My Viewport",
  "years": ["2017", "2024"]  // Optional: default is [2024]
}
```

**Check viewport readiness:**
```
GET /api/viewports/{viewport_name}/is-ready
```
Returns: `{ready: bool, message: string, has_embeddings: bool, has_pyramids: bool, has_faiss: bool}`

**Get available years:**
```
GET /api/viewports/{viewport_name}/available-years
```
Returns: `{success: bool, years: [2024, 2023, ...]}`

### Embeddings

**Extract embedding at location:**
```
POST /api/embeddings/extract
Content-Type: application/json

{
  "lat": 13.0,
  "lon": 77.55,
  "year": 2024
}
```

**Search for similar locations:**
```
POST /api/embeddings/search-similar
Content-Type: application/json

{
  "embedding": [0.1, 0.2, ...],  // 512D vector
  "threshold": 20,                 // Distance threshold
  "viewport_id": "tile_aligned",
  "year": 2024
}
```

## Configuration

### Environment Variables

Create a `.env` file in the project root:
```env
# GeoTessera API credentials (if required)
GEOTESSERA_API_KEY=your_api_key

# Server ports
WEB_SERVER_PORT=8001
TILE_SERVER_PORT=5125
```

### Preset Viewports

Modify `viewports/{name}.txt` to customize preset viewports:
```
name: My Viewport
description: Optional description
bounds: 77.55,13.0,77.57,13.02
```

## Development

### Running with Custom Settings

**Download specific years only:**
```bash
python3 download_embeddings.py --years 2023,2024
```

**Process single viewport:**
Set the active viewport first, then run pipeline scripts.

### Development Scripts

- **save.sh** - Backup viewport data and FAISS indices
- **restore.sh** - Restore from backup
- **restart.sh** - Restart web and tile servers

### Performance Notes

- **Memory**: FAISS indices loaded on-demand (~2-3GB per year)
- **Storage**: ~150-300MB per year per viewport
- **Processing**: 10-30 minutes per year depending on viewport size
- **Pyramid tiles**: ~500MB-1GB per year

## Troubleshooting

### Server fails to start
- Check if ports 8001 (web) or 5125 (tiles) are in use
- Update port numbers in `backend/web_server.py` and `tile_server.py`

### No data appears in viewer
- Verify pyramids exist: `ls blore_data/pyramids/{viewport}/{year}/`
- Check FAISS indices: `ls blore_data/faiss_indices/{viewport}/{year}/`
- Re-run `create_pyramids.py` or `create_faiss_index.py` as needed

### Slow similarity search
- Check FAISS index was created for the selected year
- Reduce similarity threshold for faster results
- Process fewer years per viewport

### Year doesn't appear in dropdown
- Verify embeddings were downloaded: `ls blore_data/mosaics/*_{year}.tif`
- Confirm pyramids exist for that year
- Check that FAISS index was built

## Key Files

| File | Purpose |
|------|---------|
| `setup_viewport.py` | Orchestrate complete workflow (download → FAISS → UMAP) |
| `download_embeddings.py` | Download Tessera embeddings for selected years |
| `create_rgb_embeddings.py` | Generate RGB preview from embeddings |
| `create_pyramids.py` | Build pyramid tile structure for web viewing |
| `create_faiss_index.py` | Create similarity search indices |
| `compute_umap.py` | Compute 2D UMAP projection for Advanced Viewer (Panel 4) |
| `backend/web_server.py` | Flask API and viewport management |
| `public/viewer.html` | Standard embedding viewer |
| `public/experimental_viewer.html` | Advanced 6-panel viewer with UMAP & temporal analysis |
| `public/viewport_selector.html` | Viewport creation interface |

## Performance Benchmarks

Typical processing times on standard hardware:

| Stage | Time (per year) | Notes |
|-------|-----------------|-------|
| Download embeddings | 5-15 min | All years download in parallel |
| Create RGB | 2-5 min | All years process in parallel |
| Build pyramids | 5-10 min | All years process in parallel |
| Create FAISS index | 5-15 min | All years process in parallel |
| **Total** | **17-45 min** | Same time for 1 year or 8 years |

**Parallel Processing**: Multiple years are downloaded and processed concurrently. The total time is approximately the same whether you request 1 year or 8 years (limited by the slowest stage).

**Incremental Availability**: You don't need to wait for all years - features become available as each year completes:
- Viewer available after first year completes Stage 3 (pyramids)
- Labeling available after first year completes Stage 4 (FAISS)
- UMAP available once computed (typically ~1-2 min)

## License

MIT License - See LICENSE file for details

## Authors

- **S. Keshav** - Primary development and design
- **Anthropic Haiku** - AI-assisted development and feature implementation

## Related Resources

- [GeoTessera Documentation](https://geotessera.readthedocs.io/)
- [FAISS Documentation](https://faiss.ai/)
- [Leaflet.js Map Library](https://leafletjs.com/)
- [Sentinel-2 Satellite Data](https://sentinel.esa.int/web/sentinel/missions/sentinel-2)

## Support

For issues or questions:
1. Check the troubleshooting section
2. Review server logs: `backend/web_server.log`
3. Verify data files exist in `blore_data/`
4. Check browser console for JavaScript errors

## Citation

If you use this project in research, please cite:

```bibtex
@software{tee2025,
  title={TEE: Tessera Embeddings Explorer},
  author={Keshav, S. and Anthropic Haiku},
  year={2025},
  url={https://github.com/sk818/TEE}
}
```
