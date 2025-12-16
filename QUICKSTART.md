# Quick Start Guide: TEE with Viewport-Based Embedding Download

## Overview

This guide shows how to run the TESSERA Embedding Explorer with the new viewport-based embedding download and pyramid creation system.

## Prerequisites

- Python 3.9+
- Node.js 18+
- geotessera library (for downloading embeddings)
- rasterio library (for GeoTIFF processing)

## Installation

### Backend Setup

```bash
# Create a Python virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install backend dependencies
cd backend
pip install -r requirements.txt
cd ..
```

### Frontend Setup

```bash
# Install frontend dependencies
npm install
```

## Running the Application

### Terminal 1: Start Backend

```bash
# Activate virtual environment
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Start the FastAPI server
cd backend
python -m uvicorn main:app --reload --port 8000

# Server will be available at http://localhost:8000
# API docs available at http://localhost:8000/docs
```

### Terminal 2: Start Frontend

```bash
# In the root directory
npm run dev

# Frontend will be available at http://localhost:5173
```

## Usage Workflow

1. **Open the Application**
   - Navigate to http://localhost:5173
   - You'll see the viewport selector with a map

2. **Select a Viewport**
   - Click on the map to select a location
   - Use search to find a specific location
   - Use preset buttons for quick access to known locations

3. **Process Viewport**
   - Click the "Load Explorer" button
   - This triggers the backend to:
     - Download TESSERA embeddings for that region via geotessera
     - Create 6-level GeoTIFF pyramids for efficient rendering
     - Save results to `public/data/viewports/{viewport_id}/`
   - A progress overlay shows the current state

4. **Explore Embeddings**
   - Once processing is complete, the explorer loads automatically
   - Click on pixels to compute similarity to other locations
   - Adjust the threshold slider to filter results
   - View statistics about similarities

## Directory Structure

```
tee/
├── backend/
│   ├── main.py                              # FastAPI application
│   ├── processing/
│   │   ├── download_viewport_embeddings.py  # Download via geotessera
│   │   └── create_viewport_pyramids.py      # Create pyramids
│   └── requirements.txt                     # Python dependencies
├── src/
│   ├── components/
│   │   ├── ViewportSelector.svelte          # Selection UI with API calls
│   │   └── ExplorerView.svelte              # Similarity explorer
│   └── lib/
│       ├── data/
│       │   └── GeoTIFFLoader.ts             # Load GeoTIFF pyramids
│       └── gpu/
│           └── CPUSimilarityCompute.ts      # CPU similarity computation
├── public/
│   └── data/
│       └── viewports/                       # Generated pyramid data
└── package.json                             # Frontend dependencies
```

## Architecture

### Frontend Flow
```
ViewportSelector (select region + click "Load")
    ↓
Call POST /api/viewports/process
    ↓
Show Progress Overlay (poll status every 1 second)
    ↓
On Complete: Load ExplorerView with viewport_id
    ↓
GeoTIFFLoader fetches pyramid levels (level_0 = full resolution)
    ↓
CPUSimilarityCompute computes cosine similarities
    ↓
Display results with colormap
```

### Backend Flow
```
POST /api/viewports/process
    ↓
Create task_id and viewport_id
    ↓
Background task:
  1. download_viewport_embeddings.py
     - Use geotessera to download embeddings
     - Save as .npy files
  2. create_viewport_pyramids.py
     - Create 6 pyramid levels per year
     - Save as GeoTIFF files
     - Add georeferencing
  3. Save metadata.json
    ↓
Return task_id immediately
    ↓
GET /api/viewports/{task_id}/status
    ↓
Serve GeoTIFF files from public/data/viewports/
```

## API Endpoints

### Process Viewport
```
POST /api/viewports/process
Body: {
  "bounds": { "minLon": float, "minLat": float, "maxLon": float, "maxLat": float },
  "center": [longitude, latitude],
  "sizeKm": float,
  "years": [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024]
}
Response: { "task_id": string, "viewport_id": string }
```

### Get Task Status
```
GET /api/viewports/{task_id}/status
Response: {
  "task_id": string,
  "viewport_id": string,
  "state": "pending|downloading|creating_pyramids|complete|error",
  "progress": 0-100,
  "message": string,
  "error": null|string
}
```

### Get Viewport Metadata
```
GET /api/viewports/{viewport_id}/metadata
Response: {
  "viewport_id": string,
  "bounds": {...},
  "center": [...],
  "years": [...],
  "pyramid_levels": 6,
  "processed_date": ISO8601,
  "status": "complete"
}
```

### Get GeoTIFF Pyramid Level
```
GET /api/viewports/{viewport_id}/pyramid/{year}/level_{level}.tif
Response: Binary GeoTIFF file
```

## Data Storage

Processed viewports are stored at:
```
public/data/viewports/{viewport_id}/
├── metadata.json
├── raw/
│   ├── embeddings_2017.npy
│   ├── embeddings_2018.npy
│   └── ...
└── pyramids/
    ├── 2017/
    │   ├── level_0.tif (full resolution)
    │   ├── level_1.tif (1/2 resolution)
    │   ├── level_2.tif (1/4 resolution)
    │   ├── level_3.tif (1/8 resolution)
    │   ├── level_4.tif (1/16 resolution)
    │   └── level_5.tif (1/32 resolution)
    ├── 2018/
    └── ...
```

## Troubleshooting

### Backend Won't Start
```bash
# Check if port 8000 is in use
lsof -i :8000  # On macOS/Linux
netstat -ano | findstr :8000  # On Windows

# Use a different port
python -m uvicorn main:app --port 8001
```

### Frontend Won't Connect to Backend
```bash
# Make sure backend is running on port 8000
# Check CORS configuration in backend/main.py
# Frontend needs VITE_API_URL environment variable:
VITE_API_URL=http://localhost:8000 npm run dev
```

### Processing Takes Too Long
- Check backend logs for errors
- Ensure geotessera library has valid API credentials
- Try a smaller viewport (smaller bounding box)
- Check available disk space (need ~1GB per viewport × years)

### GeoTIFF Files Not Loading
- Check that pyramid files exist in `public/data/viewports/`
- Verify files are valid GeoTIFF format
- Check browser console for error messages
- Ensure geotiff.js library is loaded (check npm install)

## Development Notes

### Adding More Years
Edit the `years` array in ViewportSelector.svelte:
```typescript
years: [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]
```

### Changing Pyramid Levels
Edit `NUM_ZOOM_LEVELS` in `backend/processing/create_viewport_pyramids.py`:
```python
NUM_ZOOM_LEVELS = 6  # Change to desired number
```

### Custom API URL
Set environment variable:
```bash
VITE_API_URL=https://your-api-url npm run dev
```

## Performance Tips

1. **Use smaller viewports** for faster processing
2. **Start with fewer years** for testing
3. **Use level_5 pyramids** for large regions (1/32 resolution)
4. **Cache processed viewports** to avoid reprocessing
5. **Use tiled GeoTIFF format** for efficient partial reads

## References

- [GeoTessera Documentation](https://geotessera.readthedocs.io/)
- [Rasterio Documentation](https://rasterio.readthedocs.io/)
- [GeoTIFF.js](https://geotiffjs.io/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)

## Support

For issues or questions:
1. Check the console (browser F12 for frontend, terminal for backend)
2. Review error messages in the progress overlay
3. Check server logs for backend errors
4. Refer to the plan file: `/Users/skeshav/tee/PLAN.md`
