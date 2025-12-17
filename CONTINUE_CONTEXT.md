# Continue/Qwen Context for TEE Project

## Quick Start for Continue

**Read this file first**, then refer to `.claude/plans/federated-crafting-volcano.md` for architecture details.

---

## Project Overview

**TESSERA Embedding Explorer (TEE)** - A three-pane synchronized geospatial viewer for exploring high-dimensional embedding data with zoom-aware similarity computation.

**Key Innovation**: Coarsened embedding pyramids enable 100-1000x faster similarity computation at different zoom levels.

---

## Current Status (as of Dec 16, 2025)

### ✅ Completed
- [x] Backend: Three-pane viewer setup (Leaflet maps)
- [x] Frontend: Synchronized map panes (OSM, Sentinel-2, Embeddings)
- [x] Backend: Coarsened embedding pyramid generation (6 levels)
- [x] Backend: Embeddings tile server (rio-tiler integration)
- [x] Frontend: Three-pane viewer button added to ExplorerView
- [x] Frontend/Backend: Type checking fixed (0 errors)
- [x] Backend: Sentinel-2 endpoint fix (streaming response)
- [x] Local LLM setup: Ollama with Qwen/DeepSeek models

### ⚠️ In Progress / Known Issues
- [ ] Sentinel-2 data: Not downloaded for Cambridge viewport (tiles show grey)
- [ ] Embeddings visualization: Shows tan/low-contrast (RGB of first 3 dims)
- [ ] Middle panel: Grey (no Sentinel-2 data - needs download)
- [ ] Right panel: Tan colors (data loads but low contrast)

### 📋 Next Priority Tasks
1. Test similarity computation on right panel (click to compute)
2. Add Sentinel-2 download for Cambridge viewport (optional)
3. Improve embeddings visualization color mapping
4. Add error handling for missing data
5. Test full three-pane workflow with real data

---

## Tech Stack

### Backend
- **Framework**: FastAPI (Python 3.13)
- **Tile Server**: rio-tiler for GeoTIFF handling
- **Geospatial**: geotessera for embeddings, rasterio
- **Data**: NumPy, Pillow
- **API**: RESTful with CORS enabled
- **Port**: 8000

### Frontend
- **Framework**: Svelte + TypeScript + Vite
- **Maps**: Leaflet.js (three synchronized instances)
- **Visualization**: Canvas-based heatmap overlay
- **Package Manager**: npm
- **Port**: 3000 (default), currently 3000+

### Data Format
- **Embeddings**: NPY (NumPy binary format)
- **Pyramids**: GeoTIFF
- **Metadata**: JSON

### Local Development LLM
- **Ollama**: Port 11434
- **Chat Model**: Qwen 2.5 Coder 14B
- **Autocomplete**: DeepSeek Coder 6.7B
- **Embeddings**: Nomic Embed Text

---

## Project Structure

```
/Users/skeshav/tee/
├── backend/                          # FastAPI server
│   ├── main.py                      # API endpoints, tile server
│   ├── tile_server.py               # rio-tiler integration
│   ├── requirements.txt             # Python dependencies
│   ├── venv/                        # Virtual environment
│   └── processing/
│       ├── create_coarsened_embedding_pyramids.py
│       └── download_sentinel2.py
├── src/                              # Frontend (Svelte)
│   ├── components/
│   │   ├── ThreePaneView.svelte     # 🆕 Three-pane viewer
│   │   ├── ExplorerView.svelte      # Original single-pane
│   │   ├── ViewportSelector.svelte
│   │   └── ...
│   ├── lib/
│   │   ├── similarity/
│   │   │   ├── ZoomAwareSimilarity.ts  # 🆕 Similarity logic
│   │   │   └── npy-parser.ts           # 🆕 NPY parser
│   │   ├── maps/
│   │   │   └── LeafletSync.ts          # 🆕 Map sync
│   │   ├── data/
│   │   │   ├── GeoTIFFLoader.ts
│   │   │   ├── EmbeddingLoader.ts
│   │   │   └── DataTypes.ts
│   │   └── gpu/
│   │       └── CPUSimilarityCompute.ts
│   ├── App.svelte                   # Router, view selector
│   └── main.ts
├── public/
│   └── data/viewports/              # Viewport data
│       └── 68751907-ffaf.../        # Cambridge viewport
│           ├── metadata.json        # 3702×1840×128
│           ├── raw/
│           │   └── embeddings_2024.npy (3.2GB)
│           ├── coarsened/
│           │   └── 2024/
│           │       ├── level_0.npy - level_5.npy
│           └── pyramids/
│               └── 2024/
│                   └── level_0.tif - level_5.tif
├── .continue/
│   ├── config.yaml                 # Ollama config (Qwen/DeepSeek)
│   ├── CLAUDE_CONTINUE_DIVISION.md # Division of labor guide
│   └── plans/
│       └── federated-crafting-volcano.md  # Full implementation plan
├── package.json
├── tsconfig.json
└── vite.config.ts
```

---

## Key Viewport Data

**Cambridge Viewport** (Primary Test Data)
- **ID**: `68751907-ffaf-4e34-9b2f-fffae3b6d366`
- **Location**: Cambridge, UK (52.1°N, -0.02°E)
- **Embeddings**: 1840×3702 pixels, 128-dimensional
- **Coarsened Levels**: 6 levels (level_0 to level_5)
- **Zoom Pyramid Mapping**:
  - Zoom 13+: Level 0 (full res, slow ~5000ms)
  - Zoom 11-12: Level 1 (~1200ms)
  - Zoom 9-10: Level 2 (~300ms)
  - Zoom 7-8: Level 3 (~75ms) ← Typical zoom
  - Zoom 5-6: Level 4 (~20ms)
  - Zoom 0-4: Level 5 (~5ms)

---

## Important Code Conventions

### Backend (Python)
- Use async/await for I/O operations
- FastAPI endpoints follow `/api/resource/{param}` pattern
- Pyramid levels are 0-indexed
- Tile coordinates are z/x/y (Slippy Map format)
- Error responses use HTTPException

### Frontend (Svelte/TypeScript)
- Use `createEventDispatcher()` for component communication
- Import types with `import type { ... }`
- SVG/Canvas-based visualizations (no Three.js/WebGL yet)
- Leaflet maps indexed as reference/follower for sync
- Color scale: Blue (dissimilar, ~0.0) → Red (similar, ~1.0)

### File Naming
- Components: PascalCase, `.svelte`
- Utilities/Modules: camelCase, `.ts`
- Classes: PascalCase
- Interfaces/Types: PascalCase, prefix with `I` or use `type`

---

## Known Issues & Workarounds

### 1. Metadata Dimension Mismatch ✅ FIXED
- **Issue**: Old viewport metadata (4408×4408) vs actual embeddings (1840×3702)
- **Solution**: Updated metadata.json to match actual dimensions
- **Lesson**: Always verify metadata dimensions match actual data

### 2. Sentinel-2 Tiles Not Showing
- **Status**: Expected (no Sentinel-2 data for Cambridge viewport)
- **Workaround**: Returns transparent tiles gracefully
- **Fix**: Would require: `ollama pull nomic-embed-text` and running sentinel2 download

### 3. Embeddings Visualization Low Contrast
- **Status**: Expected (visualizing first 3 dims as RGB)
- **Impact**: Data loads but appears tan/beige
- **Future**: Implement better color mapping (PCA, t-SNE)

### 4. Type Casting in GeoTIFFLoader
- **Issue**: geotiff library returns mixed types (number | TypedArray)
- **Solution**: Use `as any` cast for band data
- **Note**: Functionally correct, TypeScript just strict

### 5. FileResponse Path Parameter
- **Issue**: Old FastAPI API used `path_or_file` parameter
- **Solution**: Use StreamingResponse for in-memory buffers
- **Applied to**: Sentinel-2 tile endpoint

---

## API Endpoints (Key Ones)

```
GET /api/health                               # Health check
GET /api/viewports/find-by-bounds?...        # Find viewport by bounds
GET /api/viewports/{id}/metadata             # Get viewport metadata
GET /api/viewports/{id}/embeddings/{y}.npy   # Full embeddings NPY
GET /api/viewports/{id}/coarsened-embeddings/{y}/level_{N}.npy
GET /api/tiles/embeddings/{id}/{y}/{z}/{x}/{y}.png
GET /api/tiles/sentinel2/{id}/{y}/{z}/{x}/{y}.png
GET /api/tiles/bounds/{id}                   # Bounds for map initialization
```

---

## How to Run

### Backend
```bash
cd /Users/skeshav/tee/backend
source venv/bin/activate
python -m uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd /Users/skeshav/tee
npm run dev          # Dev server with HMR
npm run build        # Production build
npm run check        # Type checking
```

### Ollama (for Continue)
```bash
ollama serve         # Starts on port 11434
# Pull models if not already there:
# ollama pull qwen2.5-coder:14b
# ollama pull deepseek-coder:6.7b
# ollama pull nomic-embed-text
```

---

## Testing the Feature

### Test Similarity Computation
1. Load Cambridge viewport in ThreePaneView
2. Click "🗺️ Open Three-Pane Viewer" button
3. Click on right panel (embeddings)
4. Should see blue→red heatmap
5. Check console for timing (should be <100ms at typical zoom)

### Debug Tips
- Browser console (F12): Check for fetch errors
- Backend logs: Watch for tile requests and errors
- Use curl to test API: `curl http://localhost:8000/api/...`
- Check network tab for tile loading times

---

## Division of Labor: You & Claude Code

**When working with Continue/Qwen:**
- Use Continue for single-file edits, quick fixes
- Ask Claude Code for multi-file changes, architecture
- This file + planning document = complete context

**When asking Claude Code questions:**
- Reference specific files/functions
- Include error messages from console/logs
- State what you've tried with Continue

---

## Next Steps for Development

1. **Test similarity computation** (highest priority)
   - Use Continue: Test the click handler on embeddings map
   - Ask Claude: "How do I debug why similarity computation isn't triggering?"

2. **Add Sentinel-2 data** (optional, nice-to-have)
   - Use Continue: Run the sentinel2 download script
   - Ask Claude: "Design the download/caching strategy"

3. **Improve visualization** (future)
   - Ask Claude: "How should we visualize 128D embeddings better?"
   - Use Continue: Implement the chosen approach

4. **Performance optimization** (later)
   - Ask Claude: "Where are the bottlenecks?"
   - Use Continue: Apply optimizations locally

---

## Quick Reference Commands

```bash
# Type check
npm run check

# Build
npm run build

# Dev server
npm run dev

# Backend type hints (Python)
python -m mypy backend/main.py --ignore-missing-imports

# Test API
curl http://localhost:8000/api/health

# Test tile endpoint
curl http://localhost:8000/api/tiles/embeddings/68751907-ffaf-4e34-9b2f-fffae3b6d366/2024/8/128/128.png -o /tmp/test.png
```

---

## Questions for Continue?

When asking Continue/Qwen:
- ✅ "Add comments to function X in file Y"
- ✅ "Fix the syntax error in..."
- ✅ "What does this code do?"
- ✅ "Generate a test for..."
- ❌ Don't ask about cross-file architecture (ask Claude Code instead)
- ❌ Don't ask about project-wide design (ask Claude Code instead)

---

## Contact/Support

- **Planning/Architecture**: See `.claude/plans/federated-crafting-volcano.md`
- **Division of Labor**: See `.continue/CLAUDE_CONTINUE_DIVISION.md`
- **Continue Config**: See `.continue/config.yaml`
- **Browser Dev Tools**: F12 to debug frontend
- **Backend Logs**: Check uvicorn console output
