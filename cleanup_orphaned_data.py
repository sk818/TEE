#!/usr/bin/env python3
"""
Remove data files for viewports that no longer exist.

Safely identifies and removes orphaned embeddings, pyramids, and FAISS indices
for viewports that are not in the current viewports directory.
"""

from pathlib import Path
import shutil
import sys

# Get current viewports from viewport files
def get_current_viewports():
    """Get list of viewport IDs from viewport .txt files."""
    viewport_dir = Path.home() / "blore" / "viewports"
    viewports = set()

    for vp_file in viewport_dir.glob("*.txt"):
        # Skip the symlink
        if vp_file.name == "viewport.txt":
            continue
        # Remove .txt extension to get viewport ID
        viewport_id = vp_file.stem
        viewports.add(viewport_id)

    return viewports

def get_orphaned_mosaics(current_viewports):
    """Find mosaic files that don't correspond to current viewports."""
    data_dir = Path.home() / "blore_data"
    mosaics_dir = data_dir / "mosaics"
    orphaned = []

    for tif_file in mosaics_dir.glob("*.tif"):
        # Extract viewport ID: remove _embeddings_2024 or _satellite_rgb suffix
        filename = tif_file.stem  # Remove .tif

        # Try to match against current viewports
        found = False
        for vp in current_viewports:
            if filename.startswith(vp + "_"):
                found = True
                break

        if not found:
            orphaned.append(tif_file)

    return orphaned

def get_orphaned_faiss(current_viewports):
    """Find FAISS indices that don't correspond to current viewports."""
    data_dir = Path.home() / "blore_data"
    faiss_dir = data_dir / "faiss_indices"
    orphaned = []

    for index_dir in faiss_dir.glob("*/"):
        if index_dir.name not in current_viewports:
            orphaned.append(index_dir)

    return orphaned

def main():
    current_viewports = get_current_viewports()
    print(f"Current viewports: {sorted(current_viewports)}")
    print()

    orphaned_mosaics = get_orphaned_mosaics(current_viewports)
    orphaned_faiss = get_orphaned_faiss(current_viewports)

    if orphaned_mosaics or orphaned_faiss:
        print(f"Found {len(orphaned_mosaics)} orphaned mosaic files:")
        for f in sorted(orphaned_mosaics):
            print(f"  - {f.name}")

        if orphaned_faiss:
            print(f"\nFound {len(orphaned_faiss)} orphaned FAISS directories:")
            for d in sorted(orphaned_faiss):
                print(f"  - {d.name}/")

        response = input("\nDelete these files? (yes/no): ").strip().lower()

        if response == 'yes':
            for f in orphaned_mosaics:
                f.unlink()
                print(f"Deleted: {f.name}")

            for d in orphaned_faiss:
                shutil.rmtree(d)
                print(f"Deleted: {d.name}/")

            print("\n✅ Cleanup complete!")
        else:
            print("Cleanup cancelled.")
    else:
        print("✓ No orphaned files found.")

if __name__ == "__main__":
    main()
