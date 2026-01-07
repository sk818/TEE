#!/usr/bin/env python3
"""
Viewport Manager CLI

Manage viewport configurations for the blore project.

Usage:
    python scripts/viewport_manager.py list
    python scripts/viewport_manager.py current
    python scripts/viewport_manager.py use <viewport_name>
    python scripts/viewport_manager.py create-from-bounds --bounds "77.5,13.0,77.6,13.1" [--name <name>] [--description <desc>]
"""

import sys
import argparse
import logging
from pathlib import Path

# Add parent directory to path to import lib modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.viewport_utils import (
    get_active_viewport,
    get_active_viewport_name,
    list_viewports,
    read_viewport_file
)
from lib.viewport_writer import set_active_viewport, create_viewport_from_bounds

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)


def cmd_list(args):
    """List all available viewports."""
    viewports = list_viewports()

    if not viewports:
        print("No viewports found.")
        return

    print("Available viewports:")
    print()

    active_name = get_active_viewport_name()

    for viewport_name in viewports:
        try:
            viewport = read_viewport_file(viewport_name)
            bounds = viewport['bounds']
            is_active = " (ACTIVE)" if viewport_name == active_name else ""

            print(f"  {viewport_name}{is_active}")
            print(f"    Center: {viewport['center'][0]:.4f}°N, {viewport['center'][1]:.4f}°E")
            print(f"    Bounds: {bounds['minLat']:.4f}° to {bounds['maxLat']:.4f}°N, "
                  f"{bounds['minLon']:.4f}° to {bounds['maxLon']:.4f}°E")
            print()
        except Exception as e:
            print(f"  {viewport_name} (ERROR: {e})")
            print()


def cmd_current(args):
    """Show current active viewport."""
    try:
        viewport = get_active_viewport()
        bounds = viewport['bounds']

        print(f"Active Viewport: {viewport['viewport_id']}")
        print()
        print(f"Center (degrees):")
        print(f"  Latitude:  {viewport['center'][0]:.4f}°")
        print(f"  Longitude: {viewport['center'][1]:.4f}°")
        print()
        print(f"Bounds (degrees):")
        print(f"  Min Latitude:  {bounds['minLat']:.4f}°")
        print(f"  Max Latitude:  {bounds['maxLat']:.4f}°")
        print(f"  Min Longitude: {bounds['minLon']:.4f}°")
        print(f"  Max Longitude: {bounds['maxLon']:.4f}°")
        print()
        print(f"Size: {viewport['size_km']:.1f}km × {viewport['size_km']:.1f}km")
        print()
        print(f"Bounds tuple: {viewport['bounds_tuple']}")

    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to read viewport: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_use(args):
    """Switch to a different viewport."""
    viewport_name = args.viewport_name

    try:
        # Verify viewport exists
        read_viewport_file(viewport_name)

        # Switch to it
        set_active_viewport(viewport_name)
        print(f"✓ Switched to viewport: {viewport_name}")

    except FileNotFoundError:
        print(f"ERROR: Viewport '{viewport_name}' not found", file=sys.stderr)
        print(f"Use 'python scripts/viewport_manager.py list' to see available viewports", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_create_from_bounds(args):
    """Create a new viewport from geographic bounds."""
    # Parse bounds
    try:
        bounds_str = args.bounds
        parts = bounds_str.split(',')
        if len(parts) != 4:
            raise ValueError("Bounds must have 4 values: min_lon,min_lat,max_lon,max_lat")
        bounds = tuple(float(p.strip()) for p in parts)
    except ValueError as e:
        print(f"ERROR: Invalid bounds format: {e}", file=sys.stderr)
        print(f"Expected: '77.5,13.0,77.6,13.1'", file=sys.stderr)
        sys.exit(1)

    # Generate viewport name if not provided
    viewport_name = args.name
    if not viewport_name:
        import time
        viewport_name = f"viewport_{int(time.time())}"

    description = args.description or ""

    try:
        create_viewport_from_bounds(viewport_name, bounds, description)
        print(f"✓ Created viewport: {viewport_name}")
        print(f"Bounds: {bounds}")
        print()
        print(f"To activate it, run:")
        print(f"  python scripts/viewport_manager.py use {viewport_name}")

    except FileExistsError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to create viewport: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Manage viewport configurations for blore project"
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # list command
    subparsers.add_parser('list', help='List all available viewports')

    # current command
    subparsers.add_parser('current', help='Show current active viewport')

    # use command
    use_parser = subparsers.add_parser('use', help='Switch to a different viewport')
    use_parser.add_argument('viewport_name', help='Viewport name to switch to')

    # create-from-bounds command
    create_parser = subparsers.add_parser(
        'create-from-bounds',
        help='Create a new viewport from geographic bounds'
    )
    create_parser.add_argument(
        '--bounds',
        required=True,
        help='Geographic bounds as "min_lon,min_lat,max_lon,max_lat" (e.g., "77.5,13.0,77.6,13.1")'
    )
    create_parser.add_argument(
        '--name',
        help='Viewport name (auto-generated if not provided)'
    )
    create_parser.add_argument(
        '--description',
        help='Human-readable description of this viewport'
    )

    args = parser.parse_args()

    # Dispatch to appropriate command handler
    if args.command == 'list':
        cmd_list(args)
    elif args.command == 'current':
        cmd_current(args)
    elif args.command == 'use':
        cmd_use(args)
    elif args.command == 'create-from-bounds':
        cmd_create_from_bounds(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
