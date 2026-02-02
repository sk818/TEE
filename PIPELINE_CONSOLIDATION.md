# Pipeline Orchestration Consolidation

## Problem Statement

Previously, the viewport data processing pipeline had **two separate orchestrators** with duplicate logic:

1. **web_server.py** (`trigger_data_download_and_processing()`) - Used by web UI
2. **setup_viewport.py** - Manual CLI script

This created:
- **Maintenance burden**: Bug fixes had to be made in two places
- **Inconsistency**: Different error handling, verification logic, stage sequencing
- **Confusion**: Unclear which is the "source of truth"

## Solution: Shared Pipeline Module

Created `lib/pipeline.py` with a `PipelineRunner` class that encapsulates the complete pipeline orchestration.

### Architecture

```
┌─────────────────────────────────────────────┐
│         Pipeline Entry Points               │
├──────────┬──────────────┬──────────────────┤
│          │              │                  │
│  web_server.py   │  setup_viewport.py │  Other endpoints
│  (viewport      │    (manual CLI)      │  (future)
│   creation)     │                      │
└──────────┴──────────────┴──────────────────┘
           │              │
           └──────┬───────┘
                  │
          ┌───────▼─────────┐
          │  PipelineRunner │
          │  (lib/pipeline) │
          ├─────────────────┤
          │ • Stage 1: Download
          │ • Stage 2: RGB
          │ • Stage 3: Pyramids (CRITICAL)
          │ • Stage 4: FAISS
          │ • Stage 5: UMAP (optional)
          │ • Verification
          │ • Error handling
          └─────────────────┘
```

## File Changes

### 1. **lib/pipeline.py** (NEW - ~280 lines)

Complete pipeline orchestration with:

```python
class PipelineRunner:
    def __init__(self, project_root, venv_python=None)
    def run_script(script_name, *args, timeout=1800)
    def wait_for_file(file_path, min_size_bytes=1024, ...)
    def stage_1_download_embeddings(viewport_name, years_str)
    def stage_2_create_rgb(viewport_name)
    def stage_3_create_pyramids(viewport_name)
    def stage_4_create_faiss(viewport_name)
    def stage_5_compute_umap(viewport_name, umap_year)
    def run_full_pipeline(viewport_name, years_str, compute_umap, umap_year)
```

**Key guarantees:**
- ✓ Downloads embeddings BEFORE creating pyramids
- ✓ Creates pyramids BEFORE creating FAISS
- ✓ Verifies each stage before proceeding
- ✓ Clear error messages with stage context
- ✓ UMAP is truly optional (doesn't fail pipeline if skipped)

### 2. **setup_viewport.py** (SIMPLIFIED - ~60 lines)

Now a thin wrapper around `PipelineRunner`:

```python
# Before: 143 lines of duplicated subprocess/error handling logic
# After: Simple orchestration that calls shared runner

runner = PipelineRunner(project_root)
success, error = runner.run_full_pipeline(
    viewport_name=viewport_name,
    years_str=args.years,
    compute_umap=True,
    umap_year=umap_year
)
```

**Changes:**
- Removed duplicate `run_command()` function
- Removed duplicate subprocess logic
- Now calls `PipelineRunner.run_full_pipeline()`
- Properly reads active viewport before processing

### 3. **backend/web_server.py** (SIMPLIFIED - ~40 line function)

Replaced ~170 lines of duplicate pipeline code with call to `PipelineRunner`:

```python
def trigger_data_download_and_processing(viewport_name, years=None):
    # ... status tracking setup ...

    runner = PipelineRunner(project_root, VENV_PYTHON)
    success, error = runner.run_full_pipeline(
        viewport_name=viewport_name,
        years_str=years_str,
        compute_umap=False  # Web UI doesn't compute UMAP
    )

    # ... status tracking update ...
```

**Benefits:**
- Single source of truth for pipeline logic
- Maintains status tracking for web UI
- Cleaner, more maintainable code
- ~130 lines of duplicate code eliminated

## Pipeline Stages (Guaranteed Order)

All entry points now guarantee this exact order:

1. **Download Embeddings** (GeoTessera)
   - Downloads for specified years (or all available)
   - Validates files exist and are >= 1MB

2. **Create RGB** (PCA visualization)
   - Converts embeddings to RGB
   - Validates RGB files >= 512KB

3. **Create Pyramids** (CRITICAL for viewer)
   - Builds multi-level zoom structure
   - Validates >= 3 pyramid levels exist
   - **This stage is REQUIRED for viewer to work**

4. **Create FAISS** (similarity search index)
   - Builds vector indices
   - Validates index files exist
   - Validates supporting metadata files

5. **Compute UMAP** (optional)
   - 2D projection of embeddings
   - Only computed if explicitly enabled
   - Failure does NOT fail the pipeline

## Error Handling

Each stage has:

```
Try:
  1. Run script with timeout
  2. Check return code
  3. Verify output files exist
  4. Verify output files have minimum size
  5. Return success or error message

If any step fails:
  - Log error with stage context
  - Return (False, error_message)
  - Pipeline stops immediately
  - No cleanup (previous stages' data remains)
```

## Configuration

### Web UI (web_server.py)
- Calls `runner.run_full_pipeline(..., compute_umap=False)`
- UMAP is optional for web UI
- Status tracked via operation_id in `tasks` dict
- Accessible via `/api/operations/pipeline-status/<viewport_name>`

### CLI (setup_viewport.py)
- Calls `runner.run_full_pipeline(..., compute_umap=True)`
- UMAP is computed by default (unless unavailable)
- Displays summary after completion
- Returns 0 on success, 1 on failure

## Testing

To verify the consolidation works:

```bash
# Test CLI setup
python3 setup_viewport.py --years 2024

# Test web UI (create viewport via http://localhost:8001)
# Check status via:
curl http://localhost:8001/api/operations/pipeline-status/viewport_name

# Verify all data exists after each approach
ls ~/blore_data/pyramids/viewport_name/2024/level_*.tif  # Should exist
ls ~/blore_data/faiss_indices/viewport_name/2024/embeddings.index  # Should exist
```

## Future Improvements

With this consolidated approach, future enhancements are simpler:

- **Add new stage**: Extend `PipelineRunner` with `stage_N_description()`
- **Modify verification logic**: Update in one place
- **Add caching**: Cache expensive computations in runner
- **Parallel stages**: Run independent stages in parallel (future)
- **Resume capability**: Track completed stages, resume from last failure

## Backward Compatibility

- Web UI continues to work unchanged (same API endpoints)
- CLI (`setup_viewport.py`) works with same arguments
- Individual operations (pyramid creation, FAISS creation) still available via `api_switch_viewport()`
- No database migrations or config changes required

## Benefits Summary

| Aspect | Before | After |
|--------|--------|-------|
| **Code duplication** | ~170 lines duplicated | Single source of truth |
| **Maintenance** | Bug fixes in 2 places | Single location |
| **Stage ordering** | Inconsistent | Guaranteed |
| **Error messages** | Different per orchestrator | Unified format |
| **Verification** | Different per stage | Consistent |
| **UMAP handling** | Different logic in each | Unified (truly optional) |
| **Future changes** | Painful (2 places) | Simple (1 place) |
