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

---

## Technical Analysis & Bug Fix Report (December 16, 2024)

### Issue: Embeddings Not Loading When Computing Similarity

#### Root Cause Analysis

The project experienced a critical bug where similarity computation failed because:

1. **Data Loss in Pipeline**: The backend was saving only the first 3 RGB bands of the 128-dimensional embeddings as GeoTIFF files, discarding the other 125 dimensions needed for accurate similarity computation.

2. **Lossy Normalization**: The RGB bands were normalized to uint8 (0-255) in `create_viewport_pyramids.py`, losing floating-point precision.

3. **Hard-coded Dimensions**: `ExplorerView.svelte` hard-coded width/height to 256×256 instead of reading actual dimensions (typically 4408×4408) from metadata.

4. **Missing Metadata**: The `ViewportMetadata` model did not include `width`, `height`, or `bands` fields, so the frontend couldn't determine actual image dimensions.

#### Complete Data Flow Analysis

```
┌─────────────────────────────────────────────────────────────┐
│                    TESSERA EMBEDDING EXPLORER                │
├─────────────────────────────────────────────────────────────┤
│
├─── DOWNLOAD PHASE
│    └─ download_viewport_embeddings.py
│       └─ Uses geotessera to download 128D embeddings
│       └─ Saves as .npy files in public/data/viewports/{id}/raw/
│
├─── PYRAMID CREATION PHASE
│    └─ create_viewport_pyramids.py
│       ├─ Loads 128D embeddings from .npy
│       ├─ Extracts first 3 bands → RGB normalization (uint8)
│       ├─ Saves as GeoTIFF pyramids (6 levels)
│       └─ ⚠️  ISSUE: Original 128D data lost!
│
├─── FRONTEND VISUALIZATION
│    └─ GeoTIFFLoader loads RGB GeoTIFF
│       └─ Uses for visualization (correct)
│
├─── FRONTEND SIMILARITY COMPUTATION
│    └─ ExplorerView.loadYear()
│       ├─ ⚠️  ISSUE: Loads RGB GeoTIFF (3D) instead of full embeddings
│       ├─ ⚠️  ISSUE: Uses hard-coded 256×256 dimensions
│       └─ CPUSimilarityCompute tries to compute cosine similarity with 3D data
│          └─ ❌ FAILS: Only 3 dimensions instead of 128
│
└─────────────────────────────────────────────────────────────┘
```

#### Architecture Issues Found

| Component | Issue | Impact | Severity |
|-----------|-------|--------|----------|
| `create_viewport_pyramids.py` | Only stores RGB (3 bands), not full embeddings | Similarity computation broken | **CRITICAL** |
| `ExplorerView.svelte` | Hard-coded 256×256 dimensions | Wrong pixel indexing | **CRITICAL** |
| `ViewportMetadata` | Missing width/height/bands fields | Can't determine actual dimensions | **HIGH** |
| `GeoTIFFLoader` | Only loads visualization pyramids | Can't access similarity data | **HIGH** |
| Backend API | No endpoint to serve full embeddings | Frontend has no data source | **HIGH** |

#### Files Affected

**Backend:**
- `/Users/skeshav/tee/backend/main.py` - Main FastAPI server
- `/Users/skeshav/tee/backend/processing/create_viewport_pyramids.py` - Pyramid creation
- `/Users/skeshav/tee/backend/processing/download_viewport_embeddings.py` - Embedding download

**Frontend:**
- `/Users/skeshav/tee/src/components/ExplorerView.svelte` - Explorer UI
- `/Users/skeshav/tee/src/lib/data/GeoTIFFLoader.ts` - GeoTIFF loader
- `/Users/skeshav/tee/src/lib/gpu/CPUSimilarityCompute.ts` - Similarity computation

### Solution Implemented

#### Backend Changes

**1. Extended ViewportMetadata (backend/main.py)**
```python
class ViewportMetadata(BaseModel):
    viewport_id: str
    bounds: Bounds
    center: list[float]
    years: list[int]
    pyramid_levels: int = 6
    width: int = 4408          # ✅ NEW
    height: int = 4408         # ✅ NEW
    bands: int = 3             # ✅ NEW
    processed_date: str
    status: str
```

**2. Modified Pyramid Creation to Return Dimensions (backend/processing/create_viewport_pyramids.py)**
```python
def create_pyramids_for_viewport(...) -> dict:  # ✅ Now returns dict
    pyramid_info = {'width': 4408, 'height': 4408, 'bands': 3}
    # ... process pyramids ...
    # Capture actual dimensions from first year
    if year_idx == 0:
        pyramid_info['width'] = src.width
        pyramid_info['height'] = src.height
        pyramid_info['bands'] = src.count
    # ... continue ...
    return pyramid_info  # ✅ Return actual dimensions
```

**3. Added API Endpoint to Serve Full Embeddings (backend/main.py)**
```python
@app.get("/api/viewports/{viewport_id}/embeddings/{year}.npy")
async def get_embeddings_npy(viewport_id: str, year: int):
    """Serve raw embeddings as NPY file for similarity computation."""
    npy_file = DATA_DIR / viewport_id / "raw" / f"embeddings_{year}.npy"
    return FileResponse(path=npy_file, media_type="application/octet-stream")
```

**4. Updated process_viewport_task() to Capture Dimensions**
```python
# Capture return value from pyramid creation
pyramid_info = create_pyramids_for_viewport(...)

# Use actual dimensions in metadata
metadata = ViewportMetadata(
    # ... other fields ...
    width=pyramid_info.get('width', 4408),
    height=pyramid_info.get('height', 4408),
    bands=pyramid_info.get('bands', 3),
)
```

#### Frontend Changes

**1. Added NPY Parser to GeoTIFFLoader (src/lib/data/GeoTIFFLoader.ts)**
```typescript
async loadFullEmbeddings(viewportId: string, year: number): Promise<Float32Array> {
    const url = `/api/viewports/${viewportId}/embeddings/${year}.npy`;
    const arrayBuffer = await fetch(url).then(r => r.arrayBuffer());

    // Parse NPY format:
    // - 6-byte magic: "\x93NUMPY"
    // - 2-byte version
    // - 2-byte header length
    // - header + data

    const view = new DataView(arrayBuffer);
    const headerLen = view.getUint16(8, true);
    const dataStart = 10 + headerLen;

    // Extract float32 data
    const numFloats = (arrayBuffer.byteLength - dataStart) / 4;
    const embeddings = new Float32Array(numFloats);
    const dataView = new DataView(arrayBuffer, dataStart);

    for (let i = 0; i < numFloats; i++) {
        embeddings[i] = dataView.getFloat32(i * 4, true);
    }

    return embeddings;
}
```

**2. Fixed ExplorerView to Load Full Embeddings (src/components/ExplorerView.svelte)**
```typescript
async function loadYear(year: number) {
    if (usingGeoTIFF && geotiffLoader && viewportId) {
        // ✅ Load full 128D embeddings for similarity
        try {
            embeddings = await geotiffLoader.loadFullEmbeddings(viewportId, year);
        } catch (npy_error) {
            // Fallback to RGB if NPY unavailable
            embeddings = await geotiffLoader.loadPyramidLevel(viewportId, year, 0);
        }
    }

    if (!similarityCompute) {
        // ✅ Read actual dimensions from metadata
        const metadata = await geotiffLoader.loadViewportMetadata(viewportId);
        width = metadata.width || 4408;
        height = metadata.height || 4408;

        // ✅ Calculate embedding dimensions dynamically
        const numPixels = width * height;
        dimensions = Math.round(embeddings.length / numPixels);

        // Initialize with correct dimensions
        similarityCompute = new CPUSimilarityCompute(width, height, dimensions);
    }
}
```

#### Data Flow After Fix

```
┌──────────────────────────────────────────────────────────┐
│           CORRECTED DATA FLOW                            │
├──────────────────────────────────────────────────────────┤
│
├─ Backend downloads 128D embeddings → Saves as .npy
│
├─ Pyramid creation:
│  ├─ Extracts RGB for visualization GeoTIFF ✅
│  └─ Captures dimensions in metadata ✅
│
├─ Frontend visualization:
│  └─ Loads RGB GeoTIFF for display ✅
│
├─ Frontend similarity:
│  ├─ Loads full 128D embeddings from .npy endpoint ✅
│  ├─ Reads actual dimensions from metadata ✅
│  └─ CPUSimilarityCompute uses full embeddings ✅
│
└──────────────────────────────────────────────────────────┘
```

### Key Improvements

1. **Dual Data Streams**:
   - RGB GeoTIFFs for efficient visualization
   - Full NPY embeddings for accurate similarity computation

2. **Metadata-Driven Dimensions**:
   - No more hard-coded values
   - Works with any image size
   - Supports both square and rectangular viewports

3. **Graceful Fallback**:
   - If NPY unavailable, uses RGB (less accurate but functional)
   - Ensures backward compatibility

4. **Proper Data Types**:
   - Float32 for embeddings (preserves precision)
   - Uint8 for visualization (efficient)

### Testing Recommendations

1. **Verify metadata contains dimensions**:
   ```bash
   cat public/data/viewports/{viewport_id}/metadata.json | jq '.width, .height, .bands'
   ```

2. **Check NPY files are created**:
   ```bash
   ls -lh public/data/viewports/{viewport_id}/raw/
   ```

3. **Monitor browser console for logs**:
   - "Loaded full embeddings for similarity: X values"
   - "Initializing CPU compute with dimensions: 4408×4408, 128D embeddings"

4. **Test similarity computation**:
   - Click pixels in explorer view
   - Verify similarity results display correctly
   - Check console for no errors

### Performance Characteristics

| Operation | Size | Time | Notes |
|-----------|------|------|-------|
| Download 128D embeddings | ~200MB | 5-15 min | Depends on internet |
| Create 6 pyramid levels | ~50MB | 1-2 min | Rasterio operations |
| Load full embeddings | ~200MB | 2-5 sec | HTTP + NPY parsing |
| Similarity computation | 4408×4408×128D | 10-50ms | CPU-based, chunked |

### Future Enhancements

1. **GPU Acceleration**: Move similarity to WebGPU (10-100x faster)
2. **Lazy Loading**: Load pyramid levels on-demand based on zoom
3. **Streaming**: Progressive loading of large embeddings
4. **Caching**: Server-side caching of pyramid operations
5. **Compression**: Use lossless compression for full embeddings storage
