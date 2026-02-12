# Blore Viewport Manager - Web Interface

A simple web-based interface for managing geographic viewports and data selection for the Blore project.

## Features

- **Interactive Map**: OpenStreetMap-based map using Leaflet.js
- **Viewport Visualization**: See the current viewport box on the map
- **Viewport Switching**: Switch between preset viewports with one click
- **Viewport Creation**: Create new viewports by:
  - Clicking on the map to set center point
  - Manually entering geographic bounds
  - Adding optional descriptions
- **Viewport Search**: Search through available viewports by name
- **Real-time Bounds Display**: See latitude/longitude coordinates for current viewport

## Getting Started

### Start the Web Server

From the blore project directory:

```bash
python3 backend/web_server.py          # debug mode (default)
python3 backend/web_server.py --prod   # production mode (debug off)
```

The server will start on **http://localhost:8001**. Use `--port` to change the port.

### Using the Interface

Open your browser and navigate to:
```
http://localhost:8001
```

## Interface Layout

### Left Sidebar
- **Current Viewport**: Shows the active viewport with bounds and center coordinates
- **Viewport List**: Shows all available viewports with search capability
- **Create New Viewport**: Form to create custom viewports

### Map Area
- **Viewport Box**: Blue rectangle showing the current viewport
- **Viewport Info**: Bottom-right shows instructions for viewport creation

## Common Tasks

### Switch to a Different Viewport

1. Look in the "Available Viewports" list on the left
2. Click on the viewport name you want to switch to
3. The map will update to show the new viewport bounds
4. The "Active Viewport" panel will refresh with new coordinates

### Create a New Viewport

**Option 1: Click on the Map**
1. Click "+ Create New Viewport" button
2. Click on the map at your desired center point
3. The bounds will auto-fill in the form
4. Enter an optional name and description
5. Click "Create"

**Option 2: Manual Bounds Entry**
1. Click "+ Create New Viewport" button
2. Enter bounds in format: `min_lon,min_lat,max_lon,max_lat`
   - Example: `77.55,13.0,77.57,13.02`
3. Enter an optional viewport name
4. Click "Create"

### View Viewport Coordinates

The current viewport's exact bounds are displayed in the "Active Viewport" panel:
- Min/Max Latitude in degrees
- Min/Max Longitude in degrees

These coordinates are also shown in the viewport list items.

## Preset Viewports

The project comes with three preset viewports:

1. **tile_aligned** (Default)
   - Aligns with Tessera pyramid tiles
   - Bounds: 77.499°E to 77.6011°E, 12.999°N to 13.101°N

2. **bangalore_10km**
   - 10km × 10km viewport preset (legacy name for Bangalore region)
   - Bounds: 77.5446°E to 77.6446°E, 12.9216°N to 13.0216°N

3. **malleswaram_500m**
   - 500m × 500m viewport preset (region within Bangalore)
   - Bounds: 77.5659°E to 77.5751°E, 13.0039°N to 13.0129°N

## Data Files

Viewport configurations are stored in the `viewports/` directory:

```
viewports/
├── viewport.txt          # Symlink to active viewport
├── .active               # Text file with active viewport name
├── tile_aligned.txt      # Tile-aligned preset (default)
├── bangalore_10km.txt    # Preset viewport (Bangalore region)
├── malleswaram_500m.txt  # Preset viewport (Malleswaram region)
└── README.md             # Viewport system documentation
```

## API Endpoints

If you need to use the API programmatically:

### List All Viewports
```
GET /api/viewports/list
```

Returns: JSON array of all viewports with active indicator

### Get Current Viewport
```
GET /api/viewports/current
```

Returns: JSON object with current viewport details

### Switch Viewport
```
POST /api/viewports/switch
Content-Type: application/json

{"name": "viewport_name"}
```

### Create New Viewport
```
POST /api/viewports/create
Content-Type: application/json

{
  "bounds": "min_lon,min_lat,max_lon,max_lat",
  "name": "optional_name",
  "description": "optional description"
}
```

## Troubleshooting

### Port 8001 Already in Use
If you get "Address already in use" error, the port is occupied. Either:
1. Stop the other program using port 8001
2. Use a different port: `python3 backend/web_server.py --port 9000`

### Viewport Files Not Found
Make sure you're running the web server from the blore project root directory.

### Map Not Loading
Check your internet connection - the interface uses CDN-hosted Leaflet.js and OpenStreetMap tiles.

## Technical Details

- **Backend**: Flask web framework (Python)
- **Frontend**: HTML5, Vanilla JavaScript, Leaflet.js
- **Map Source**: OpenStreetMap tiles
- **Data Format**: Human-readable text files with geographic bounds
- **Viewport Size**: Fixed size (existing: 10km × 10km, new viewports: 5km × 5km)

## Related Documentation

- See `viewports/README.md` for detailed viewport system documentation
- See `scripts/viewport_manager.py` for command-line viewport management
- See `lib/viewport_utils.py` for programmatic viewport access
