# Blore System Setup & Running

This document explains how to properly set up and run the Blore geospatial visualization system.

## Virtual Environment Setup

All Python scripts require the virtual environment to be activated due to dependencies like:
- `geotessera` - For Tessera embeddings
- `rasterio` - For GeoTIFF processing
- `flask` - For web server
- `faiss` - For similarity search (optional)

### Check venv Status

```bash
cd /Users/skeshav/blore
ls -la venv/bin/python3
```

Should show: `/Users/skeshav/blore/venv/bin/python3`

## Starting Services

### Option 1: Using the Startup Script (Recommended)

```bash
/Users/skeshav/blore/start_services.sh
```

This automatically:
- Activates the venv
- Kills any existing instances
- Starts backend on port 8001
- Starts tile server on port 5125
- Logs to `/tmp/backend.log` and `/tmp/tile_server.log`

### Option 2: Manual Startup

```bash
# Terminal 1 - Backend
cd /Users/skeshav/blore
source venv/bin/activate
python3 backend/web_server.py

# Terminal 2 - Tile Server
cd /Users/skeshav/blore
source venv/bin/activate
python3 tile_server.py
```

## Accessing the System

Open your browser to: **http://localhost:8001**

## Troubleshooting

### "Module not found" errors (geotessera, rasterio, etc.)

**Cause**: Scripts are running with system Python instead of venv Python

**Solution**: 
1. Verify venv is being used:
   ```bash
   which python3  # Should show /Users/skeshav/blore/venv/bin/python3
   ```

2. If not, run startup script or manually activate:
   ```bash
   source /Users/skeshav/blore/venv/bin/activate
   ```

### Backend subprocess calls failing

All subprocess calls in `web_server.py` now use the `run_script()` helper which automatically uses venv Python.

If you modify subprocess calls, use this pattern:
```python
result = run_script('script_name.py', timeout=600)
```

NOT:
```python
subprocess.run([sys.executable, 'script.py'])  # ❌ Wrong - uses system Python
```

## Important Notes

1. **All Python scripts must run with venv Python** - System Python lacks required dependencies
2. **Backend auto-runs scripts** - When you process viewports, the backend automatically calls download and pyramid scripts using venv Python
3. **Manual script running** - If you manually run scripts, always:
   ```bash
   source venv/bin/activate
   python3 script_name.py
   ```

## Environment Variables

For venv activation to work correctly, ensure:
- `PROJECT_DIR` = `/Users/skeshav/blore`
- `VENV_PYTHON` = `/Users/skeshav/blore/venv/bin/python3`

These are automatically set in `start_services.sh` and `web_server.py`.

## Service Ports

- **Backend**: 8001 (Flask web server)
- **Tile Server**: 5125 (Tile serving for maps)
- **Frontend**: Served from backend at http://localhost:8001

## Logs

- Backend: `/tmp/backend.log`
- Tile Server: `/tmp/tile_server.log`

View with:
```bash
tail -f /tmp/backend.log
tail -f /tmp/tile_server.log
```
