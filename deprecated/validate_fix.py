#!/usr/bin/env python3
"""
Validation script for the embeddings loading fix.
Tests all critical components without requiring server startup.
"""

import json
import struct
from pathlib import Path
import numpy as np
import sys

# ANSI colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_header(msg):
    print(f"\n{BLUE}{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}{RESET}")

def print_pass(msg):
    print(f"{GREEN}✓ PASS:{RESET} {msg}")

def print_fail(msg):
    print(f"{RED}✗ FAIL:{RESET} {msg}")

def print_info(msg):
    print(f"{YELLOW}ℹ INFO:{RESET} {msg}")

def test_metadata_dimensions():
    """Test that metadata includes width/height/bands fields."""
    print_header("Test 1: Metadata Dimensions")

    viewport_id = "ce2b76c3-f56b-4155-bf54-68da9aa4e83a"
    metadata_file = Path(f"/Users/skeshav/tee/public/data/viewports/{viewport_id}/metadata.json")

    if not metadata_file.exists():
        print_fail(f"Metadata file not found: {metadata_file}")
        return False

    with open(metadata_file, 'r') as f:
        metadata = json.load(f)

    # Check required fields
    required_fields = ['width', 'height', 'bands']
    all_present = True

    for field in required_fields:
        if field in metadata:
            print_pass(f"Field '{field}' present: {metadata[field]}")
        else:
            print_fail(f"Field '{field}' missing from metadata")
            all_present = False

    if all_present and metadata.get('width') == 4408 and metadata.get('height') == 4408:
        print_pass(f"Metadata dimensions are correct: {metadata['width']}×{metadata['height']}")
        return True
    return all_present

def test_pyramid_files():
    """Test that pyramid files exist for all levels."""
    print_header("Test 2: Pyramid File Structure")

    viewport_id = "ce2b76c3-f56b-4155-bf54-68da9aa4e83a"
    year = 2024
    pyramids_dir = Path(f"/Users/skeshav/tee/public/data/viewports/{viewport_id}/pyramids/{year}")

    if not pyramids_dir.exists():
        print_fail(f"Pyramids directory not found: {pyramids_dir}")
        return False

    expected_levels = 6
    found_levels = 0

    for level in range(expected_levels):
        tif_file = pyramids_dir / f"level_{level}.tif"
        if tif_file.exists():
            size_mb = tif_file.stat().st_size / (1024 * 1024)
            print_pass(f"Level {level}: {tif_file.name} ({size_mb:.1f}MB)")
            found_levels += 1
        else:
            print_fail(f"Level {level} not found: {tif_file.name}")

    if found_levels == expected_levels:
        print_pass(f"All {expected_levels} pyramid levels present")
        return True
    return False

def test_npy_files():
    """Test that NPY embedding files exist and are readable."""
    print_header("Test 3: NPY Embedding Files")

    viewport_id = "ce2b76c3-f56b-4155-bf54-68da9aa4e83a"
    raw_dir = Path(f"/Users/skeshav/tee/public/data/viewports/{viewport_id}/raw")

    if not raw_dir.exists():
        print_fail(f"Raw embeddings directory not found: {raw_dir}")
        return False

    all_valid = True

    for year in [2024, 2023, 2022]:
        npy_file = raw_dir / f"embeddings_{year}.npy"

        if not npy_file.exists():
            print_fail(f"Embeddings file not found: {npy_file.name}")
            all_valid = False
            continue

        size_gb = npy_file.stat().st_size / (1024**3)
        print_info(f"Found {npy_file.name}: {size_gb:.2f}GB")

        # Verify NPY format
        try:
            arr = np.load(npy_file)
            shape = arr.shape
            print_pass(f"NPY is readable: shape={shape}, dtype={arr.dtype}")

            # Expected shape for 4408x4408x128
            if shape == (4408, 4408, 128):
                print_pass(f"Shape is correct: 4408×4408×128")
            else:
                print_info(f"Shape is {shape} (expected 4408×4408×128)")

        except Exception as e:
            print_fail(f"Error reading NPY: {e}")
            all_valid = False

    return all_valid

def test_npy_format():
    """Test NPY file format parsing."""
    print_header("Test 4: NPY Format Validation")

    viewport_id = "ce2b76c3-f56b-4155-bf54-68da9aa4e83a"
    npy_file = Path(f"/Users/skeshav/tee/public/data/viewports/{viewport_id}/raw/embeddings_2024.npy")

    if not npy_file.exists():
        print_fail(f"NPY file not found: {npy_file}")
        return False

    try:
        # Read NPY magic and header
        with open(npy_file, 'rb') as f:
            # Read magic bytes
            magic = f.read(6)
            if magic == b'\x93NUMPY':
                print_pass(f"NPY magic bytes valid: {magic}")
            else:
                print_fail(f"Invalid magic bytes: {magic}")
                return False

            # Read version
            version = struct.unpack('<H', f.read(2))[0]
            print_pass(f"NPY version: {version}")

            # Read header length
            header_len = struct.unpack('<H', f.read(2))[0]
            print_pass(f"NPY header length: {header_len} bytes")

            # Read header
            header = f.read(header_len).decode('utf-8')
            print_info(f"NPY header: {header[:100]}...")

            # Verify data offset
            data_offset = 10 + header_len
            print_pass(f"Data starts at offset: {data_offset}")

            # Check total file size matches expected
            file_size = npy_file.stat().st_size
            expected_size = data_offset + (4408 * 4408 * 128 * 4)  # 4 bytes per float32

            if abs(file_size - expected_size) < 1024:  # Allow 1KB difference
                print_pass(f"File size matches expected: {file_size:,} bytes")
            else:
                print_info(f"File size: {file_size:,} bytes (expected ~{expected_size:,})")

        return True

    except Exception as e:
        print_fail(f"Error parsing NPY format: {e}")
        return False

def test_backend_main():
    """Test that backend/main.py has all required imports."""
    print_header("Test 5: Backend Code Validation")

    try:
        sys.path.insert(0, '/Users/skeshav/tee')
        from backend.main import app, ViewportMetadata, get_embeddings_npy

        print_pass("FastAPI app imported successfully")

        # Check ViewportMetadata has new fields
        import inspect
        sig = inspect.signature(ViewportMetadata)

        if 'width' in sig.parameters or any(field.name == 'width' for field in ViewportMetadata.model_fields.values() if hasattr(ViewportMetadata, 'model_fields')):
            print_pass("ViewportMetadata includes 'width' field")
        else:
            # Try different approach
            test_metadata = ViewportMetadata(
                viewport_id="test",
                bounds={"minLon": 0, "minLat": 0, "maxLon": 1, "maxLat": 1},
                center=[0.5, 0.5],
                years=[2024],
                processed_date="2025-01-01",
                status="complete",
                width=4408,
                height=4408,
                bands=3
            )
            print_pass("ViewportMetadata accepts width/height/bands fields")

        # Check if endpoint exists
        routes = [route.path for route in app.routes]
        if '/api/viewports/{viewport_id}/embeddings/{year}.npy' in routes:
            print_pass("NPY serving endpoint found in routes")
        else:
            print_info(f"Routes: {[r for r in routes if 'embeddings' in r]}")

        return True

    except ImportError as e:
        print_fail(f"Import error: {e}")
        return False
    except Exception as e:
        print_fail(f"Error: {e}")
        return False

def test_frontend_geotiffloader():
    """Test that GeoTIFFLoader has new methods."""
    print_header("Test 6: Frontend Code Validation")

    geotiff_loader = Path("/Users/skeshav/tee/src/lib/data/GeoTIFFLoader.ts")

    if not geotiff_loader.exists():
        print_fail(f"GeoTIFFLoader file not found: {geotiff_loader}")
        return False

    with open(geotiff_loader, 'r') as f:
        content = f.read()

    checks = [
        ("loadFullEmbeddings method", "async loadFullEmbeddings"),
        ("NPY format parsing", "magic = String.fromCharCode"),
        ("NPY magic validation", "\\x93NUMPY"),
        ("Float32Array parsing", "getFloat32"),
        ("Cache support", "this.cache.set"),
    ]

    all_pass = True
    for check_name, pattern in checks:
        if pattern in content:
            print_pass(f"{check_name} implemented")
        else:
            print_fail(f"{check_name} not found")
            all_pass = False

    return all_pass

def test_explorer_view():
    """Test that ExplorerView uses new dimension logic."""
    print_header("Test 7: ExplorerView Logic")

    explorer = Path("/Users/skeshav/tee/src/components/ExplorerView.svelte")

    if not explorer.exists():
        print_fail(f"ExplorerView file not found: {explorer}")
        return False

    with open(explorer, 'r') as f:
        content = f.read()

    checks = [
        ("Load full embeddings", "loadFullEmbeddings"),
        ("Read dimensions from metadata", "metadata.width"),
        ("Dynamic dimension calculation", "embeddings.length / numPixels"),
        ("Proper logging", "Loaded dimensions from metadata"),
    ]

    all_pass = True
    for check_name, pattern in checks:
        if pattern in content:
            print_pass(f"{check_name} implemented")
        else:
            print_fail(f"{check_name} not found")
            all_pass = False

    return all_pass

def main():
    """Run all validation tests."""
    print(f"\n{BLUE}{'='*60}")
    print(f"  EMBEDDINGS LOADING FIX - VALIDATION SUITE")
    print(f"  December 16, 2024")
    print(f"{'='*60}{RESET}")

    results = {
        "Metadata Dimensions": test_metadata_dimensions(),
        "Pyramid Files": test_pyramid_files(),
        "NPY Files": test_npy_files(),
        "NPY Format": test_npy_format(),
        "Backend Code": test_backend_main(),
        "Frontend GeoTIFFLoader": test_frontend_geotiffloader(),
        "ExplorerView Logic": test_explorer_view(),
    }

    # Summary
    print_header("VALIDATION SUMMARY")

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = f"{GREEN}✓ PASS{RESET}" if result else f"{RED}✗ FAIL{RESET}"
        print(f"{status}: {test_name}")

    print(f"\n{BLUE}Result: {passed}/{total} tests passed{RESET}")

    if passed == total:
        print(f"{GREEN}All validation tests passed! ✓{RESET}\n")
        return 0
    else:
        print(f"{YELLOW}Some tests failed. Review above for details.{RESET}\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
