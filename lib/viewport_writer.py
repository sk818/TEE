"""Viewport creation and writing utilities."""

import logging
from pathlib import Path
from datetime import datetime
from typing import Tuple, Optional

from lib.viewport_utils import validate_viewport_name

logger = logging.getLogger(__name__)


def create_viewport_from_bounds(
    viewport_name: str,
    bounds: Tuple[float, float, float, float],
    description: str = ""
) -> Path:
    """
    Create a new viewport file from geographic bounds.

    Args:
        viewport_name: Unique viewport name (no spaces, use underscores)
        bounds: (min_lon, min_lat, max_lon, max_lat) in WGS84
        description: Optional human-readable description

    Returns:
        Path to the created viewport file

    Raises:
        ValueError: If bounds are invalid
        FileExistsError: If viewport file already exists
    """
    # Validate viewport name against path traversal
    validate_viewport_name(viewport_name)

    # Validate bounds
    min_lon, min_lat, max_lon, max_lat = bounds

    if not (-180 <= min_lon <= 180) or not (-180 <= max_lon <= 180):
        raise ValueError(f"Invalid longitude bounds: {min_lon} to {max_lon}")
    if not (-90 <= min_lat <= 90) or not (-90 <= max_lat <= 90):
        raise ValueError(f"Invalid latitude bounds: {min_lat} to {max_lat}")
    if min_lon >= max_lon:
        raise ValueError(f"Min longitude ({min_lon}) must be < max longitude ({max_lon})")
    if min_lat >= max_lat:
        raise ValueError(f"Min latitude ({min_lat}) must be < max latitude ({max_lat})")

    # Calculate center
    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2

    # Build viewport file content
    timestamp = datetime.utcnow().isoformat()

    content = f"""Viewport Configuration
=====================

Viewport ID: {viewport_name}

Center (degrees):
  Latitude:  {center_lat:.4f}°
  Longitude: {center_lon:.4f}°

Bounds (degrees):
  Min Latitude:  {min_lat:.4f}°
  Max Latitude:  {max_lat:.4f}°
  Min Longitude: {min_lon:.4f}°
  Max Longitude: {max_lon:.4f}°

Size: 5km × 5km

Description: {description}

Generated: {timestamp}
"""

    # Write to file
    viewports_dir = Path(__file__).parent.parent / "viewports"
    viewport_path = viewports_dir / f"{viewport_name}.txt"

    if viewport_path.exists():
        raise FileExistsError(f"Viewport file already exists: {viewport_path}")

    viewport_path.write_text(content)
    logger.info(f"✓ Created viewport: {viewport_path}")

    return viewport_path


def set_active_viewport(viewport_name: str) -> None:
    """
    Set the active viewport by updating the symlink.

    Args:
        viewport_name: Viewport name (without .txt extension)

    Raises:
        ValueError: If viewport name contains unsafe characters
        FileNotFoundError: If viewport file doesn't exist
        OSError: If symlink operation fails
    """
    validate_viewport_name(viewport_name)
    viewports_dir = Path(__file__).parent.parent / "viewports"
    viewport_path = viewports_dir / f"{viewport_name}.txt"
    symlink_path = viewports_dir / "viewport.txt"
    active_path = viewports_dir / ".active"

    if not viewport_path.exists():
        raise FileNotFoundError(f"Viewport file not found: {viewport_path}")

    # Remove old symlink
    if symlink_path.exists() or symlink_path.is_symlink():
        symlink_path.unlink()

    # Create new symlink
    symlink_path.symlink_to(viewport_path.name)
    logger.info(f"✓ Updated symlink: viewport.txt -> {viewport_path.name}")

    # Update .active file
    active_path.write_text(viewport_name)
    logger.info(f"✓ Set active viewport: {viewport_name}")


def clear_active_viewport() -> None:
    """
    Clear the active viewport state (remove symlink and .active file).

    Call this when the active viewport is deleted or cancelled.
    """
    viewports_dir = Path(__file__).parent.parent / "viewports"
    symlink_path = viewports_dir / "viewport.txt"
    active_path = viewports_dir / ".active"

    # Remove symlink
    if symlink_path.exists() or symlink_path.is_symlink():
        symlink_path.unlink()
        logger.info("✓ Removed viewport.txt symlink")

    # Remove .active file
    if active_path.exists():
        active_path.unlink()
        logger.info("✓ Removed .active file")
