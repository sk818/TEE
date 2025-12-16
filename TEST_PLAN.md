# Testing Plan: Similarity Computation Fix

## Overview

This document outlines the testing procedure for the embeddings loading fix (commit 65dddc9).

## Environment Setup

### Backend Requirements
- Python 3.9+
- FastAPI, uvicorn, numpy, rasterio
- Port 8000 available

### Frontend Requirements
- Node.js 18+
- npm/yarn
- Port 3000 available
- Modern browser with WebGL support

## Test Scenarios

### Scenario 1: Backend Startup & API Endpoints

**Objective**: Verify backend starts and endpoints respond correctly

**Steps**:
1. Start backend server on port 8000
2. Check API documentation at http://localhost:8000/docs
3. Verify these endpoints exist:
   - `GET /api/viewports/{viewport_id}/metadata`
   - `GET /api/viewports/{viewport_id}/pyramid/{year}/level_{level}.tif`
   - `GET /api/viewports/{viewport_id}/embeddings/{year}.npy` (NEW)
   - `POST /api/viewports/process`
   - `GET /api/viewports/{task_id}/status`

**Expected Results**:
- Server starts without errors
- API docs page loads
- All endpoints are listed
- No import errors in console

---

### Scenario 2: Frontend Build & Startup

**Objective**: Verify frontend builds and starts without errors

**Steps**:
1. Install dependencies: `npm install`
2. Start dev server: `npm run dev`
3. Open http://localhost:3000 in browser
4. Open browser DevTools (F12) and check Console tab
5. Check Network tab for API requests

**Expected Results**:
- Build completes without errors
- No TypeScript compilation errors
- Application loads in browser
- Console shows no critical errors
- Vite proxy is working (check Network tab)

---

### Scenario 3: ViewportSelector Component

**Objective**: Verify viewport selection UI works

**Steps**:
1. Navigate to http://localhost:3000
2. ViewportSelector should display a map
3. Check browser console for any errors
4. Click on map to select a location
5. Verify selection appears in UI

**Expected Results**:
- Map renders without errors
- Can click to select location
- Selection is registered
- No console errors
- Console shows location selection logs

---

### Scenario 4: Metadata Dimensions

**Objective**: Verify metadata includes width/height/bands fields

**Steps**:
1. After viewport processing completes
2. Check metadata file: `public/data/viewports/{viewport_id}/metadata.json`
3. Inspect the file content

**Expected JSON Structure**:
```json
{
  "viewport_id": "...",
  "bounds": {...},
  "center": [...],
  "years": [...],
  "pyramid_levels": 6,
  "width": 4408,           // NEW
  "height": 4408,          // NEW
  "bands": 3,              // NEW
  "processed_date": "...",
  "status": "complete"
}
```

---

### Scenario 5: GeoTIFF Pyramid Files

**Objective**: Verify pyramid files are created correctly

**Steps**:
1. After viewport processing
2. Check directory structure: `public/data/viewports/{viewport_id}/pyramids/`
3. List files for a year: `ls -lh public/data/viewports/{viewport_id}/pyramids/2024/`

**Expected Results**:
```
level_0.tif  (largest, ~4-10MB)
level_1.tif
level_2.tif
level_3.tif
level_4.tif
level_5.tif  (smallest, ~100KB)
```

---

### Scenario 6: NPY Embeddings Files

**Objective**: Verify full embedding files are preserved

**Steps**:
1. After viewport processing
2. Check raw embeddings: `ls -lh public/data/viewports/{viewport_id}/raw/`

**Expected Results**:
```
embeddings_2024.npy  (~200MB for 4408x4408x128 float32)
```

---

### Scenario 7: API Endpoint - Serve NPY

**Objective**: Verify new NPY serving endpoint works

**Steps**:
1. Get a viewport_id from existing metadata
2. Use curl to fetch NPY:
   ```bash
   curl http://localhost:8000/api/viewports/{viewport_id}/embeddings/2024.npy -o test.npy
   ```
3. Verify file is downloaded
4. Check file size: `ls -lh test.npy`

**Expected Results**:
- HTTP 200 response
- File downloads successfully
- File size matches expected (~200MB for 4408x4408x128)
- Binary content starts with NPY magic bytes (`\x93NUMPY`)

---

### Scenario 8: Frontend - Load Embeddings

**Objective**: Verify ExplorerView loads full embeddings

**Steps**:
1. Navigate to ExplorerView after viewport selection
2. Open browser DevTools Console
3. Monitor console output while embeddings load
4. Check for these log messages:
   - "Loading full embeddings for {year}..."
   - "Loaded full embeddings for similarity: X values"
   - "Initializing CPU compute with dimensions: 4408×4408, 128D embeddings"

**Expected Results**:
- Messages appear in order
- Embeddings size logs show 128D data
- No console errors
- No warnings about dimension mismatches

---

### Scenario 9: Frontend - Compute Similarity

**Objective**: Verify similarity computation works with full embeddings

**Steps**:
1. In ExplorerView, look for test button or try clicking on map
2. Click pixel to trigger similarity computation
3. Monitor console for computation logs
4. Check for similarity results

**Expected Results**:
- No errors when clicking pixels
- Similarity computation completes
- Results display in UI
- Console shows:
  - "Selected Pixel: (x, y)"
  - No errors about dimensions
  - No type errors

---

### Scenario 10: Dimension Calculation

**Objective**: Verify dimensions are calculated correctly from embeddings

**Steps**:
1. In browser console, monitor ExplorerView initialization
2. Check log messages about dimension loading
3. Verify formula: `dimensions = embeddings.length / (width * height)`

**Expected Flow**:
```
✓ Loaded dimensions from metadata: 4408×4408 with 3 bands
✓ Initializing CPU compute with dimensions: 4408×4408, 128D embeddings
```

---

## Test Data Preparation

### Option 1: Use Existing Viewport
If viewport data already exists:
1. Find viewport_id in `public/data/viewports/`
2. Check if both pyramids and raw embeddings exist
3. Use for testing

### Option 2: Create Test Viewport (if needed)
If no viewport data exists:
1. Would require geotessera credentials
2. Would trigger 5-15 minute download
3. Not practical for quick testing

---

## Manual Testing Checklist

### Backend Verification
- [ ] Backend starts without errors
- [ ] API docs page loads
- [ ] All endpoints listed
- [ ] No import/dependency errors

### Frontend Verification
- [ ] Frontend builds without errors
- [ ] No TypeScript errors
- [ ] Application loads at http://localhost:3000
- [ ] Console shows no critical errors

### Data Integrity
- [ ] Metadata includes width, height, bands
- [ ] Pyramid files exist (6 levels)
- [ ] NPY files exist in raw directory
- [ ] NPY files have correct size

### API Functionality
- [ ] NPY endpoint serves files
- [ ] Files can be downloaded successfully
- [ ] File size matches expected

### Frontend Computation
- [ ] ExplorerView loads full embeddings
- [ ] Embeddings have 128 dimensions
- [ ] Image dimensions are correct (4408×4408)
- [ ] Similarity computation doesn't error
- [ ] Pixel click triggers computation

### Console Logs (no errors)
- [ ] "Loaded full embeddings" message appears
- [ ] "Initializing CPU compute" message appears
- [ ] Correct dimensions logged
- [ ] No TypeScript/JavaScript errors
- [ ] No API request errors

---

## Troubleshooting Guide

### Issue: Backend won't start
```bash
# Check port 8000 is available
lsof -i :8000

# Check Python dependencies
pip list | grep fastapi

# Try different port
python -m uvicorn backend.main:app --port 8001
```

### Issue: Frontend won't load
```bash
# Clear node_modules cache
rm -rf node_modules package-lock.json
npm install

# Clear Vite cache
rm -rf .vite

# Start with verbose output
npm run dev -- --debug
```

### Issue: NPY file not found
```bash
# Check file exists
ls -la public/data/viewports/{viewport_id}/raw/embeddings_*.npy

# Check API endpoint
curl -v http://localhost:8000/api/viewports/{viewport_id}/embeddings/2024.npy
```

### Issue: Similarity computation fails
```bash
# Check console for specific error
# Common causes:
# - Embeddings not loaded (check loadFullEmbeddings logs)
# - Wrong dimensions (check dimension calculation logs)
# - Array indexing out of bounds (check width/height)
```

---

## Performance Benchmarks

Expected performance metrics:

| Operation | Expected Time | Max Time |
|-----------|---------------|----------|
| Load full embeddings | 2-5 sec | 10 sec |
| Calculate similarity | 10-50 ms | 100 ms |
| Dimension parsing | <100 ms | 500 ms |
| Threshold filtering | 5-10 ms | 50 ms |

---

## Success Criteria

All of the following must pass:

1. ✅ Backend starts and serves all endpoints
2. ✅ Frontend builds and loads without errors
3. ✅ Metadata includes width/height/bands fields
4. ✅ NPY files are created and accessible via API
5. ✅ Frontend loads full 128D embeddings
6. ✅ Image dimensions are read from metadata (not hard-coded)
7. ✅ Similarity computation executes without errors
8. ✅ Console logs show correct dimensions
9. ✅ No TypeScript or runtime errors
10. ✅ Performance is within expected ranges

---

## Test Execution Report Template

```
Test Date: YYYY-MM-DD
Tester: [Name]
Environment: macOS/Linux/Windows

Scenario 1: Backend Startup
- Status: ✓ PASS / ✗ FAIL
- Notes:

Scenario 2: Frontend Build
- Status: ✓ PASS / ✗ FAIL
- Notes:

... [continue for all scenarios]

Overall Result: ✓ PASS / ✗ FAIL
Issues Found: [list any issues]
Recommendations: [any improvements]
```

