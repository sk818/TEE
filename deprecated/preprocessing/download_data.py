#!/usr/bin/env python3
"""
Download TESSERA embeddings, Sentinel-2 imagery, and OSM data for selected viewport.
"""

import argparse
import requests
from pathlib import Path
from typing import Tuple

def download_tessera_embeddings(bounds: Tuple[float, float, float, float],
                                 years: list[int],
                                 output_dir: Path):
    """
    Download TESSERA embeddings for specified bounds and years.

    Args:
        bounds: (min_lon, min_lat, max_lon, max_lat)
        years: List of years to download
        output_dir: Output directory
    """
    # TODO: Replace with actual TESSERA API endpoint
    api_endpoint = "https://tessera-api.example.com/embeddings"

    for year in years:
        params = {
            'min_lon': bounds[0],
            'min_lat': bounds[1],
            'max_lon': bounds[2],
            'max_lat': bounds[3],
            'year': year,
            'resolution': 10
        }

        print(f"Downloading TESSERA embeddings for {year}...")
        # response = requests.post(api_endpoint, json=params)
        # Save to file
        pass

def download_sentinel2(bounds: Tuple[float, float, float, float],
                       years: list[int],
                       quarters: list[int],
                       output_dir: Path):
    """
    Download Sentinel-2 quarterly composites.
    Can use Google Earth Engine, Microsoft Planetary Computer, or AWS.
    """
    # Use Earth Engine Python API or direct access
    pass

def download_osm(bounds: Tuple[float, float, float, float],
                 output_dir: Path):
    """
    Download OpenStreetMap data using Overpass API.
    """
    overpass_url = "https://overpass-api.de/api/interpreter"

    query = f"""
    [out:json][timeout:180];
    (
      way["building"]({bounds[1]},{bounds[0]},{bounds[3]},{bounds[2]});
      way["highway"]({bounds[1]},{bounds[0]},{bounds[3]},{bounds[2]});
      way["natural"="water"]({bounds[1]},{bounds[0]},{bounds[3]},{bounds[2]});
      relation["landuse"]({bounds[1]},{bounds[0]},{bounds[3]},{bounds[2]});
    );
    out geom;
    """

    print("Downloading OSM data...")
    response = requests.post(overpass_url, data={'data': query})

    if response.status_code == 200:
        output_file = output_dir / 'osm_features.geojson'
        # Convert Overpass JSON to GeoJSON
        # Save to file
        pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--bounds', nargs=4, type=float, required=True,
                        help='min_lon min_lat max_lon max_lat')
    parser.add_argument('--years', nargs='+', type=int,
                        default=list(range(2017, 2025)))
    parser.add_argument('--output', type=Path, default=Path('data'))

    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)

    download_tessera_embeddings(args.bounds, args.years, args.output / 'embeddings')
    download_sentinel2(args.bounds, args.years, [1,2,3,4], args.output / 'sentinel2')
    download_osm(args.bounds, args.output / 'osm')
