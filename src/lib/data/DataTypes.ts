/**
 * Common data types and interfaces
 */

export interface Bounds {
    minLon: number;
    minLat: number;
    maxLon: number;
    maxLat: number;
}

export interface ViewportConfig {
    center: [number, number];
    bounds: Bounds;
    sizeKm: number;
}

export interface EmbeddingHeader {
    magic: string;
    version: number;
    year: number;
    width: number;
    height: number;
    dimensions: number;
    bounds: [number, number, number, number]; // [minLon, minLat, maxLon, maxLat]
}

export interface PCAHeader {
    magic: string;
    width: number;
    height: number;
    components: number;
    explainedVariance: [number, number, number];
}
