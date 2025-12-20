#!/usr/bin/env python3
"""
Extract first 3 bands from embeddings GeoTIFF and save as RGB GeoTIFF.
"""

import logging
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import Affine

logger = logging.getLogger(__name__)


def normalize_band(band: np.ndarray) -> np.ndarray:
    """Normalize a band to 0-255 using percentile-based normalization."""
    valid_data = band[~np.isnan(band)]

    if len(valid_data) == 0:
        return np.zeros_like(band, dtype=np.uint8)

    # Get 2nd and 98th percentiles to avoid outliers
    p2, p98 = np.percentile(valid_data, [2, 98])

    # Normalize to 0-255
    if p98 > p2:
        normalized = np.clip((band - p2) / (p98 - p2) * 255, 0, 255)
    else:
        normalized = np.clip(band * 255, 0, 255)

    return normalized.astype(np.uint8)


def extract_rgb(
    embeddings_file: Path,
    output_file: Path,
    progress_callback=None
) -> dict:
    """
    Extract first 3 bands from embeddings GeoTIFF and save as RGB.

    Checks for existing RGB file first - if it exists and has the same
    bounds as the embeddings file, reuses it.

    Args:
        embeddings_file: Path to embeddings GeoTIFF
        output_file: Path to save RGB GeoTIFF
        progress_callback: Optional callback(message, percent)

    Returns:
        Dictionary with metadata about the RGB extraction
    """
    try:
        if progress_callback:
            progress_callback("Checking for existing RGB...", 10)

        # Check if RGB file already exists with matching bounds
        if output_file.exists():
            try:
                with rasterio.open(embeddings_file) as src_emb:
                    emb_bounds = src_emb.bounds

                with rasterio.open(output_file) as src_rgb:
                    rgb_bounds = src_rgb.bounds

                    # Check if bounds match (with small tolerance)
                    tolerance = 0.0001
                    if (abs(rgb_bounds.left - emb_bounds.left) < tolerance and
                        abs(rgb_bounds.bottom - emb_bounds.bottom) < tolerance and
                        abs(rgb_bounds.right - emb_bounds.right) < tolerance and
                        abs(rgb_bounds.top - emb_bounds.top) < tolerance and
                        src_rgb.count == 3):

                        size_mb = output_file.stat().st_size / (1024 * 1024)
                        logger.info(f"✓ Found matching existing RGB file: {output_file}")

                        if progress_callback:
                            progress_callback(f"Using cached RGB ({size_mb:.1f} MB)", 100)

                        return {
                            'success': True,
                            'file': str(output_file),
                            'size_mb': size_mb,
                            'width': src_rgb.width,
                            'height': src_rgb.height,
                            'bands': 3,
                            'crs': str(src_rgb.crs),
                            'cached': True
                        }
            except Exception as e:
                logger.warning(f"Error checking existing RGB file: {e}")

        if progress_callback:
            progress_callback("Extracting RGB from embeddings...", 15)

        logger.info(f"Extracting RGB from {embeddings_file}")

        # Read embeddings
        with rasterio.open(embeddings_file) as src:
            # Read first 3 bands
            bands_data = []
            for band_idx in range(1, min(4, src.count + 1)):
                band_data = src.read(band_idx)
                bands_data.append(band_data)

            # If less than 3 bands, pad with zeros
            while len(bands_data) < 3:
                bands_data.append(np.zeros_like(bands_data[0]))

            # Normalize each band
            if progress_callback:
                progress_callback("Normalizing bands...", 30)

            rgb_array = np.stack([
                normalize_band(bands_data[0]),
                normalize_band(bands_data[1]),
                normalize_band(bands_data[2])
            ], axis=0)

            # Copy metadata
            profile = src.profile.copy()
            crs = src.crs
            transform = src.transform

            logger.info(f"RGB shape: {rgb_array.shape}")
            logger.info(f"CRS: {crs}, Transform: {transform}")

        # Save RGB GeoTIFF
        if progress_callback:
            progress_callback("Saving RGB GeoTIFF...", 60)

        output_file.parent.mkdir(parents=True, exist_ok=True)

        profile.update({
            'count': 3,
            'dtype': 'uint8',
            'compress': 'lzw'
        })

        with rasterio.open(output_file, 'w', **profile) as dst:
            dst.write(rgb_array)

        size_mb = output_file.stat().st_size / (1024 * 1024)
        logger.info(f"✓ Saved RGB: {output_file} ({size_mb:.2f} MB)")

        if progress_callback:
            progress_callback(f"✓ RGB extracted ({size_mb:.1f} MB)", 100)

        return {
            'success': True,
            'file': str(output_file),
            'size_mb': size_mb,
            'width': rgb_array.shape[2],
            'height': rgb_array.shape[1],
            'bands': 3,
            'crs': str(crs),
            'transform': str(transform)
        }

    except Exception as e:
        logger.error(f"Error extracting RGB: {e}")
        import traceback
        traceback.print_exc()

        if progress_callback:
            progress_callback(f"Error: {str(e)}", 0)

        return {
            'success': False,
            'error': str(e)
        }


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Extract RGB from embeddings GeoTIFF")
    parser.add_argument("--input", type=str, required=True, help="Input embeddings GeoTIFF")
    parser.add_argument("--output", type=str, required=True, help="Output RGB GeoTIFF")

    args = parser.parse_args()

    result = extract_rgb(Path(args.input), Path(args.output))

    if result['success']:
        print(f"\n✅ RGB extraction complete!")
        print(f"File: {result['file']}")
        print(f"Size: {result['size_mb']:.1f} MB")
    else:
        print(f"\n❌ Error: {result['error']}")
        exit(1)
