# Implementation Plan: Viewport-Based TESSERA Embedding Download and Pyramid Creation

## Overview

Add dynamic, on-demand preprocessing to the TEE explorer. When users select a viewport, trigger backend processing to download TESSERA embeddings for that region, create multi-resolution pyramids (6 zoom levels), and load results into the explorer.

## User Requirements Summary

- **Workflow**: UI triggers preprocessing (ViewportSelector → Backend API → Download → Pyramids → Load)
- **Output**: GeoTIFF pyramids (6 levels) like blore project
- **Bounds**: From ViewportSelector UI (user clicks location)
- **Backend**: Python API server to execute preprocessing

## Architecture

### Backend: FastAPI (Python)

**Structure**:
```
backend/
├── main.py                              # FastAPI app
├── api/
│   ├── routes/preprocessing.py          # POST /viewports/process, GET /status
│   └── services/
│       ├── download_service.py          # Wraps download script
│       └── pyramid_service.py           # Wraps pyramid creation
├── processing/
│   ├── download_viewport_embeddings.py  # Based on blore's download_embeddings.py
│   └── create_viewport_pyramids.py      # Based on blore's create_pyramids.py
└── requirements.txt
```

### Data Storage

```
public/data/viewports/
└── {viewport_id}/                       # UUID for each viewport
    ├── metadata.json                    # Bounds, years, date
    └── pyramids/
        ├── 2017/
        │   ├── level_0.tif
        │   ├── level_1.tif
        │   ├── level_2.tif
        │   ├── level_3.tif
        │   ├── level_4.tif
        │   └── level_5.tif
        ├── 2018/
        └── ...
```

## Implementation Steps

### Phase 1: Backend Setup

1. Create FastAPI application (`backend/main.py`)
2. Key endpoints:
   - `POST /api/viewports/process` - Start processing
   - `GET /api/viewports/{task_id}/status` - Poll status
   - `GET /api/viewports/{viewport_id}/pyramid/{year}/level_{N}.tif` - Serve GeoTIFFs

3. Python scripts:
   - `download_viewport_embeddings.py` - Downloads via geotessera
   - `create_viewport_pyramids.py` - Creates 6-level pyramids

### Phase 2: Frontend Integration

1. Update `ViewportSelector.svelte` - Add processing trigger
2. Create `GeoTIFFLoader.ts` - Load GeoTIFF pyramids
3. Update `ExplorerView.svelte` - Use GeoTIFFLoader
4. Update `DataTypes.ts` - Add viewportId

## Critical Files

1. **NEW: `backend/main.py`**
2. **NEW: `backend/processing/download_viewport_embeddings.py`**
3. **NEW: `backend/processing/create_viewport_pyramids.py`**
4. **MODIFY: `src/components/ViewportSelector.svelte`**
5. **NEW: `src/lib/data/GeoTIFFLoader.ts`**
6. **MODIFY: `src/components/ExplorerView.svelte`**
7. **MODIFY: `src/lib/data/DataTypes.ts`**

## Dependencies

**Backend** (`backend/requirements.txt`):
```
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
pydantic>=2.0.0
geotessera>=1.0.0
rasterio>=1.3.0
numpy>=1.24.0
aiofiles>=23.0.0
```

**Frontend** (`package.json`):
```
geotiff: ^2.1.0
```

## Complete Flow

```
1. User selects viewport in ViewportSelector
2. Clicks "Process Viewport" button
3. Frontend calls POST /api/viewports/process
4. Backend starts background task:
   - download_viewport_embeddings.py
   - create_viewport_pyramids.py
5. Frontend polls GET /api/viewports/{task_id}/status
6. On completion, loads ExplorerView with viewport data
7. GeoTIFFLoader fetches pyramid GeoTIFFs
8. Explorer displays data with similarity computation
```

## Running the Application

**Terminal 1 - Backend:**
```bash
cd backend
python -m uvicorn main:app --reload --port 8000
```

**Terminal 2 - Frontend:**
```bash
npm run dev
```
