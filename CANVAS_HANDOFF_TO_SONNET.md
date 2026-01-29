# Canvas Synchronization Issue - Handoff to Claude Sonnet

## Executive Summary

Explorer Mode for similarity search is **95% complete and working**:
- ✅ UI mode toggle (Labeling/Explorer)
- ✅ One-click pixel search
- ✅ Live threshold slider with 250K+ results
- ✅ Backend preprocessing (clipping, FAISS, RGB) optimized

**Critical Remaining Issue**: Canvas rendering white pixels to display explorer results is **invisible** or **misaligned**. This is a Leaflet layer integration problem that requires systematic debugging.

## Current State

### What Works
- Backend API endpoints deliver 250K matching pixels correctly
- JavaScript draws pixels to canvas (logs confirm: "Canvas rendered 250000 pixels in 218.0ms")
- Canvas element exists in DOM
- All events fire correctly

### What Doesn't Work
**Two variations of the same root problem:**

1. **Canvas invisible** - Rendering happens but white pixels don't appear on screen
2. **Canvas misaligned during pan** - White pixels move at different speed than map tiles

## Detailed Problem Description

User clicks a pixel in Explorer mode → Backend returns 250K similar embeddings → JavaScript creates HTML5 canvas layer and draws all pixels white at 50% opacity to `maps.rgb` (Bing satellite panel).

**Expected result**: White semi-transparent pixels overlay on satellite view, moving in perfect sync during pan/zoom
**Actual result**: Nothing visible or severe misalignment during panning

### Console Output (Working Correctly)
```
[CANVAS] Added to overlay pane
[CANVAS] Sized to 526×676px (1052×1352 device pixels, dpr=2)
[CANVAS] Events bound, drawing...
[EXPLORER] Canvas rendered 250000 pixels in 218.0ms
```

Canvas is created, sized, and pixels are drawn. But they're invisible.

## Approaches Tried (All Failed)

### Attempt 1: Overlay Pane with Continuous Redraw
- **Problem**: Redraw on `move` events caused double-movement (misalignment)
- **Why**: CSS transforms + coordinate recalculation = pixels moved faster/slower than tiles
- **Result**: Worst misalignment

### Attempt 2: Overlay Pane with requestAnimationFrame Throttle
- **Problem**: Still had misalignment, plus UI froze on 250K pixels
- **Why**: Throttling didn't sync with Leaflet's transform timing
- **Result**: Right panel froze, canvas still misaligned

### Attempt 3: Overlay Pane with moveend-Only Redraw
- **Problem**: Canvas was invisible during pan (didn't show off-screen pixels)
- **Why**: Only redrewing after pan completed meant intermediate pans showed blank areas
- **Result**: Sharp cutoff at pan edges

### Attempt 4: Direct Map Container Positioning
- **Problem**: Canvas completely invisible
- **Why**: Positioned absolutely on map container without pane transforms; as map panned, canvas stayed at top:0,left:0
- **Result**: Canvas fell behind or disappeared as viewport moved

### Attempt 5: Device Pixel Ratio Scaling Attempts
- Added/removed DPR scaling multiple times
- Tried with/without context.scale()
- Tried with/without CSS size matching
- Tried integer rounding for pixel coordinates
- **Result**: No improvement, still invisible

## Current Implementation (Last Attempt)

Location: `/Users/skeshav/blore/public/viewer.html`, class `DirectCanvasLayer` (~line 1593)

```javascript
// Canvas added to overlay pane (Leaflet's managed pane with CSS transforms)
// Events: 'zoom' and 'moveend' trigger redraw
// DPR scaling: Applied (canvas.width *= dpr, ctx.scale(dpr, dpr))
// Draw: Direct fillRect with integer-rounded coordinates
// Color: White (#FFFFFF), 50% opacity
// Target panel: maps.rgb (Bing satellite)
```

## Key Questions for Sonnet

1. **Why is the canvas invisible if it's being rendered?**
   - Is it being rendered to an off-screen area?
   - Is z-index preventing visibility?
   - Is opacity/blending preventing visibility?
   - Is Leaflet's overlay pane structure hiding it?

2. **What's the correct Leaflet layer abstraction for this use case?**
   - Should we NOT extend L.Layer?
   - Should we use a different pane?
   - Should we bypass Leaflet's layer system entirely?

3. **How do we handle pan synchronization correctly?**
   - Should we track map center/bounds and position canvas accordingly?
   - Should we update canvas transform directly instead of redrawing?
   - Should we use a canvas element per tile instead of one global canvas?

## Debug Information Available

### Browser Console Logs (When Searching)
- Confirms canvas creation and DOM insertion
- Confirms sizing (526×676px CSS, 1052×1352 device pixels at DPR=2)
- Confirms 250000 pixels rendered in 218ms
- Shows `opacity: 0.5` and `z-index: 200`

### Browser Inspector
- Canvas element **is in DOM** under overlay pane
- Canvas has correct dimensions
- Canvas has opacity and z-index set

### Network Requests
- Backend returns correct 250K matching pixel coordinates (lat/lon)
- JavaScript correctly converts to screen coordinates via `latLngToContainerPoint()`
- Drawing logic uses these coordinates for fillRect

## Files to Reference

**Main implementation:**
- `/Users/skeshav/blore/public/viewer.html` - Lines 1593-1720 (DirectCanvasLayer class)
- `/Users/skeshav/blore/public/viewer.html` - Lines 1558-1590 (visualizeExplorerResults function)

**Supporting:**
- `/Users/skeshav/blore/public/viewer.html` - Lines 1056-1072 (calculatePixelBounds function)
- `/Users/skeshav/blore/backend/web_server.py` - Endpoints return correct match data

## What Sonnet Should Focus On

1. **Systematic debugging**: Why is a canvas that's rendering 250K pixels invisible?
2. **Leaflet integration**: What's the correct way to layer a custom canvas with Leaflet?
3. **Coordinate systems**: Are lat/lng → screen coords being calculated correctly?
4. **Layer synchronization**: How do we keep canvas in sync with pan/zoom without double-movement?

## Success Criteria

✅ White semi-transparent pixels visible on Bing satellite map
✅ Pixels stay perfectly aligned during panning
✅ Pixels update correctly during zooming
✅ No misalignment, no flashing, no cutoff at edges
✅ Threshold slider filtering works smoothly
✅ No browser freezing with 250K pixels

## Recent Commits (Useful for Understanding Attempts)

```
654666e - Fix invisible canvas by returning to overlay pane with proper event handling
526d4d8 - Restore DPR scaling and add debugging for invisible canvas
845cfbb - Completely rewrite canvas layer: position on map container, not overlay pane
88558b3 - Simplify canvas sync by using moveend events instead of continuous move
```

---

**Key Takeaway**: The backend and search logic are working perfectly. This is purely a canvas rendering/Leaflet integration issue. The canvas is being created and drawn to, but something about the positioning, visibility, or layer system is preventing it from appearing or keeping it synchronized with the map.
