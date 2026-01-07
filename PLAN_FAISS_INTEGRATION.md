# FAISS Integration Plan for Embedding Similarity Search

## Overview
Integrate FAISS (Facebook AI Similarity Search) to build searchable indices on embedding mosaics downloaded via geotessera. This is a preprocessing step that creates indices after embeddings are downloaded.

## Current Workflow
1. User creates viewport
2. Frontend triggers download → downloads embeddings & satellite RGB in parallel
3. Post-processing → pyramid creation for visualization
4. User explores data in viewer

## Proposed Changes

### 1. New Script: `create_faiss_index.py`
**Purpose**: Create FAISS index from sampled embeddings + store all embeddings for threshold search

**Inputs**:
- GeoTIFF mosaic file (e.g., `mosaics/bangalore_2024.tif`)
- Contains 128 bands (128-dimensional embeddings)
- ~4408×4408 pixels (~19M total pixels for 10km viewport)

**Output**:
- FAISS index files stored in `faiss_indices/{viewport_id}/`
  - `embeddings.index` - IVF-PQ index from sampled embeddings (for fast lookup)
  - `all_embeddings.npy` - All pixel embeddings as numpy array (for threshold search)
  - `metadata.json` - Pixel coordinates, lat/lon, sampling info

**Two-Step Architecture**:

**Step 1: Create IVF-PQ Index from Sample**
- Read all bands from mosaic: (H, W, 128)
- Subsample embeddings (e.g., every 2×2 pixels = 4.9M vectors, or every 4×4 = 1.2M vectors)
- Convert uint8 to float32 [0-255] → [0-1]
- Create IVF-PQ FAISS index for fast similarity lookup
- Store sampled pixel coordinates in metadata

**Step 2: Store All Embeddings**
- Extract ALL pixel embeddings from mosaic
- Reshape: (H, W, 128) → (H*W, 128)
- Save as numpy array: `all_embeddings.npy` (float32)
- Store pixel-to-coordinate mapping for all pixels

**Metadata JSON Structure**:
```json
{
  "viewport_id": "viewport_13.0039_77.5566",
  "mosaic_file": "mosaics/bangalore_2024.tif",
  "num_total_pixels": 19414400,
  "num_sampled_pixels": 1214275,
  "sampling_factor": 4,
  "embedding_dim": 128,
  "pixel_size_meters": 10,
  "mosaic_height": 4408,
  "mosaic_width": 4408,
  "geotransform": [77.5566, 0.0000089, 0, 13.1039, 0, -0.0000089],
  "crs": "EPSG:4326",
  "faiss_index_type": "IVF1024,PQ64"
}
```

**Key Decisions**:
- **Index Type**: IVF-PQ (Inverted File with Product Quantization)
  - IVF: Partition space into regions for faster search
  - PQ: Quantize vectors for reduced memory (~1/8 of original)
  - Fast similarity search on large datasets
- **Sampling Strategy**:
  - Store sampled embeddings in FAISS for fast index lookup
  - Store ALL embeddings in numpy for threshold-based filtering
  - Supports: "Find all pixels with similarity > threshold" queries
- **Data Format**: uint8 [0-255] → normalized float32 [0-1] for FAISS
- **Memory**:
  - Index (19M × 128 × 4 bytes) = ~9.7GB raw → ~1.2GB with PQ64
  - All embeddings storage: ~9.7GB (compressed in numpy)

### 2. Integrate into Web Server Pipeline

**Location**: `backend/web_server.py`

**Integration Point**: Parallel execution with pyramid creation

**Changes in `run_download_process()`**:
- Current flow: Downloads → Pyramids → Done
- New flow: Downloads → [Pyramids + FAISS Index (parallel)] → Done
- Use ThreadPoolExecutor to run both in parallel (like current embeddings/satellite downloads)

**Progress Tracking** (revised timeline):
- 0-10%: "Starting parallel downloads..."
- 10-30%: "Downloading embeddings..." + "Downloading satellite RGB..."
- 30-45%: Skip downloads if cached (now used for next step)
- 45-60%: "Creating pyramids..." (slow step, parallelized)
- 45-75%: "Creating FAISS index..." (parallelized with pyramids)
- 75-85%: Wait for both to complete, aggregate progress
- 85-95%: Final validation
- 95-100%: "✓ Viewport ready for exploration"

**Caching Logic**:
- Check if FAISS index exists before creation:
  - Verify metadata.json contains matching viewport_id/bounds
  - Skip if already exists and valid
- Track pyramid + index creation status separately
- Both must complete successfully for "ready" status

**Error Handling**:
- If pyramid creation fails: continue (graceful fallback)
- If FAISS index fails: continue (non-blocking, log warning)
- Both don't prevent viewport from being usable, just missing features

### 3. Directory Structure
```
faiss_indices/
├── viewport_13.0039_77.5566/
│   ├── embeddings.index        (FAISS IVF-PQ index from sampled pixels)
│   ├── all_embeddings.npy      (All pixel embeddings as numpy array)
│   └── metadata.json           (Sampling info, coordinates, geotransform)
├── malleswaram_500m/
│   ├── embeddings.index
│   ├── all_embeddings.npy
│   └── metadata.json
└── ...
```

### 4. Sampling Configuration

**Default Sampling Strategy**: Every 4×4 pixels (sampling_factor=4)
- Reduces 19M pixels → ~1.2M vectors in FAISS
- Trade-off: Fast index (~1.2GB with PQ64) vs. all embeddings (~9.7GB stored)
- Can be tuned based on memory/performance needs
- Metadata JSON stores sampling_factor for later use

## Dependencies
- FAISS: Already available or install via `pip install faiss-cpu` (or `faiss-gpu`)
- Existing: numpy, rasterio, pathlib

## Implementation Phases

### Phase 1: Basic Index Creation (THIS TASK)
**Files to Create/Modify**:
- `create_faiss_index.py` (new) - FAISS index creation logic
  - Read mosaic GeoTIFF
  - Sample embeddings → create IVF-PQ index
  - Extract all embeddings → save numpy array
  - Generate metadata JSON with geotransform & sampling info

- `backend/web_server.py` (modify)
  - Parallel thread for FAISS creation in `run_download_process()`
  - Add FAISS creation call after downloads complete
  - Update progress tracking (shared executor)
  - Add caching logic (check if index exists)

**Deliverables**:
- [ ] `create_faiss_index.py` script with full implementation
- [ ] Integration into web_server.py with parallel execution
- [ ] Progress tracking updates in UI
- [ ] Caching logic to avoid recreating indices
- [ ] Test with existing mosaics in `mosaics/` directory
- [ ] Documentation of FAISS file format and structure

### Phase 2: Query/Search Endpoint (FUTURE - User will specify)
- API endpoint: `/api/faiss/search` with similarity threshold
- Accept query embedding → fast FAISS search on sampled index
- Get candidate pixels from FAISS, then threshold filter on all embeddings
- Return pixel locations (lat/lon) with similarity scores
- Possibly integrate into viewer for visual feedback

### Phase 3: Optimization (FUTURE - Optional)
- Fine-tune IVF parameters (number of cells)
- Adjust PQ dimensionality vs accuracy trade-off
- GPU acceleration if available
- Batch operations for multiple queries

## Testing Strategy
1. **Unit Test**: `create_faiss_index.py` standalone
   - Run with existing mosaic: `python create_faiss_index.py`
   - Verify index file exists and is valid
   - Verify numpy array shape is correct
   - Verify metadata JSON is valid JSON

2. **Integration Test**: Full download flow
   - Create new viewport
   - Monitor progress bar
   - Verify both pyramids and FAISS indices are created
   - Verify files in `faiss_indices/` directory

3. **Caching Test**:
   - Re-download same viewport
   - Verify FAISS creation is skipped
   - Verify timestamps show no new files created

4. **Query Test** (Phase 2):
   - Load all_embeddings.npy
   - Do sample similarity search against FAISS index
   - Verify returned pixel indices are valid

## Key Implementation Notes
- User will specify how to use indices in Phase 2
- Index creation runs in parallel with pyramids (not blocking)
- Metadata includes geotransform for converting pixel coords → lat/lon
- FAISS IVF-PQ provides fast similarity search on high-dimensional data
- All embeddings stored as backup for threshold-based filtering
- Sampling factor configurable via metadata

