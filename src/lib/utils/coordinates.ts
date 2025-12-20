/**
 * Coordinate conversion utilities
 */

import type { Bounds } from '../data/DataTypes';

export const VIEWPORT_SIZE_KM = 1;

/**
 * Convert km to degrees at a given latitude
 */
export function kmToDegrees(km: number, latitude: number): { lat: number; lng: number } {
    const latOffset = km / 111.32;
    const lngOffset = km / (111.32 * Math.cos(latitude * Math.PI / 180));
    return { lat: latOffset, lng: lngOffset };
}

/**
 * Calculate bounds from center point and size
 */
export function calculateBounds(
    centerLng: number,
    centerLat: number,
    sizeKm: number
): Bounds {
    const offsets = kmToDegrees(sizeKm / 2, centerLat);

    return {
        minLon: centerLng - offsets.lng,
        maxLon: centerLng + offsets.lng,
        minLat: centerLat - offsets.lat,
        maxLat: centerLat + offsets.lat
    };
}

/**
 * Convert geographic coordinate to pixel coordinate
 */
export function geoToPixel(
    lon: number,
    lat: number,
    bounds: Bounds,
    width: number,
    height: number
): [number, number] {
    const x = Math.floor(
        ((lon - bounds.minLon) / (bounds.maxLon - bounds.minLon)) * width
    );
    const y = Math.floor(
        ((bounds.maxLat - lat) / (bounds.maxLat - bounds.minLat)) * height
    );

    return [x, y];
}

/**
 * Convert pixel coordinate to geographic coordinate
 */
export function pixelToGeo(
    x: number,
    y: number,
    bounds: Bounds,
    width: number,
    height: number
): [number, number] {
    const lon = bounds.minLon + (x / width) * (bounds.maxLon - bounds.minLon);
    const lat = bounds.maxLat - (y / height) * (bounds.maxLat - bounds.minLat);

    return [lon, lat];
}

/**
 * Create GeoJSON for viewport box
 */
export function createBoxGeoJSON(
    centerLng: number,
    centerLat: number,
    sizeKm: number
) {
    const bounds = calculateBounds(centerLng, centerLat, sizeKm);

    return {
        type: 'Feature' as const,
        properties: {},
        geometry: {
            type: 'Polygon' as const,
            coordinates: [[
                [bounds.minLon, bounds.minLat],
                [bounds.maxLon, bounds.minLat],
                [bounds.maxLon, bounds.maxLat],
                [bounds.minLon, bounds.maxLat],
                [bounds.minLon, bounds.minLat]
            ]]
        }
    };
}
