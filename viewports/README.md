# Viewport Configuration

This directory contains viewport definitions for the blore project.

## Viewport Files

Each viewport is defined in a `.txt` file with human-readable bounds and center coordinates.

### Preset Viewports (Tracked in Git)

- **tile_aligned.txt** - Default: Tile-aligned bounds from Tessera embeddings (10km × 10km)
- **malleswaram_500m.txt** - 500m × 500m area in Malleswaram, Bangalore
- **bangalore_10km.txt** - 10km × 10km area centered on Bangalore city center

### Active Viewport (User-Specific, Gitignored)

- **viewport.txt** - Symlink to the currently active viewport
- **.active** - Text file tracking which viewport is currently active

## Viewport File Format

```
Viewport Configuration
=====================

Viewport ID: unique_name

Center (degrees):
  Latitude:  13.0000°
  Longitude: 77.5000°

Bounds (degrees):
  Min Latitude:  12.9990°
  Max Latitude:  13.0010°
  Min Longitude: 77.4990°
  Max Longitude: 77.5010°

Size: 10.0km × 10.0km

Description: Human-readable description of this viewport

Generated: 2026-01-06T00:00:00
```

### Fields

- **Viewport ID**: Unique identifier (no spaces, use underscores)
- **Center**: Latitude and longitude in decimal degrees
- **Bounds**: Min/Max latitude and longitude in decimal degrees
- **Size**: Fixed size (existing viewports: 10km × 10km, new viewports: 5km × 5km)
- **Description**: Optional human-readable description
- **Generated**: ISO timestamp when the viewport was created

## Usage

### Switch Active Viewport

```bash
python scripts/viewport_manager.py use tile_aligned
python scripts/viewport_manager.py use malleswaram_500m
python scripts/viewport_manager.py use bangalore_10km
```

### List All Viewports

```bash
python scripts/viewport_manager.py list
```

### Show Current Active Viewport

```bash
python scripts/viewport_manager.py current
```

### Create New Viewport

```bash
python scripts/viewport_manager.py create-from-bounds \
  --name my_area \
  --bounds "77.5,13.0,77.6,13.1" \
  --description "My custom area"
```

## How It Works

1. When you switch viewports using `viewport_manager.py use <name>`, the symlink `viewport.txt` is updated to point to the new viewport file.

2. Download scripts (`download_embeddings.py`, `download_satellite_rgb.py`, etc.) read from `viewport.txt` to get the current bounds.

3. Before downloading, the scripts check if the bounds match any existing mosaic files (cache lookup with ±10m tolerance).

4. If a match is found, the script skips downloading and reuses the cached data.

5. If no match is found, the script downloads new data for those bounds.

## Important Notes

- **Viewport Size**:
  - Existing/legacy viewports: 10km × 10km
  - New viewports (created going forward): 5km × 5km
- Bounds are in **WGS84 (EPSG:4326)** coordinates (latitude/longitude in decimal degrees)
- The cache lookup uses a tolerance of **±0.0001°** (approximately ±10 meters)
