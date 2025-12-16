/**
 * Load TESSERA embeddings from GeoTIFF pyramid files
 */

import type { EmbeddingHeader } from './DataTypes';
import { GeoTIFF, fromArrayBuffer } from 'geotiff';

export class GeoTIFFLoader {
    private cache: Map<string, Float32Array> = new Map();
    private metadata: Map<string, any> = new Map();

    constructor() {
        // Use relative paths for API calls - Vite proxy will handle routing
    }

    /**
     * Load a pyramid level for a specific viewport and year
     */
    async loadPyramidLevel(
        viewportId: string,
        year: number,
        level: number
    ): Promise<Float32Array> {
        const cacheKey = `${viewportId}_${year}_${level}`;

        // Check cache
        if (this.cache.has(cacheKey)) {
            console.log(`✓ Loaded pyramid from cache: ${cacheKey}`);
            return this.cache.get(cacheKey)!;
        }

        try {
            console.log(`Loading pyramid level: ${viewportId}/${year}/level_${level}`);

            // Fetch GeoTIFF file using relative path (Vite proxy handles routing)
            const url = `/api/viewports/${viewportId}/pyramid/${year}/level_${level}.tif`;
            const response = await fetch(url);

            if (!response.ok) {
                throw new Error(`Failed to fetch: ${response.statusText}`);
            }

            const arrayBuffer = await response.arrayBuffer();

            // Parse GeoTIFF using geotiff.js
            const tiff = await fromArrayBuffer(arrayBuffer);
            const image = await tiff.getImage();

            // Get dimensions
            const width = image.getWidth();
            const height = image.getHeight();
            const numBands = image.getSamplesPerPixel();

            console.log(`GeoTIFF dimensions: ${width}x${height} with ${numBands} bands`);

            // Read all bands
            const rasters = await image.readRasters();
            console.log(`Rasters loaded: ${rasters.length} bands, first band sample values:`,
                Array.from(rasters[0] as any).slice(0, 10));

            // Convert to Float32Array and interleave
            const embeddings = new Float32Array(width * height * numBands);

            for (let band = 0; band < numBands; band++) {
                const bandData = rasters[band];

                if (!bandData) {
                    console.warn(`Band ${band} is undefined`);
                    continue;
                }

                // Interleave data into embeddings array
                for (let i = 0; i < bandData.length; i++) {
                    const value = bandData[i];

                    // Handle different data types
                    if (typeof value === 'number') {
                        embeddings[i * numBands + band] = value;
                    } else if (ArrayLike.prototype.isPrototypeOf(value)) {
                        embeddings[i * numBands + band] = (value as any)[0];
                    } else {
                        embeddings[i * numBands + band] = 0;
                    }
                }
            }

            // Cache
            this.cache.set(cacheKey, embeddings);
            console.log(`✓ Cached pyramid level: ${cacheKey}`);

            // Debug: log some sample values (without spreading huge array)
            let min = embeddings[0];
            let max = embeddings[0];
            let sum = 0;
            for (let i = 0; i < Math.min(10000, embeddings.length); i++) {
                min = Math.min(min, embeddings[i]);
                max = Math.max(max, embeddings[i]);
                sum += embeddings[i];
            }
            const stats = {
                min: min,
                max: max,
                mean: sum / Math.min(10000, embeddings.length),
                size: embeddings.length
            };
            console.log(`Embeddings stats:`, stats);

            return embeddings;
        } catch (error) {
            console.error(`Error loading pyramid level ${level}:`, error);
            throw error;
        }
    }

    /**
     * Load metadata for a viewport
     */
    async loadViewportMetadata(viewportId: string): Promise<any> {
        if (this.metadata.has(viewportId)) {
            return this.metadata.get(viewportId);
        }

        try {
            const url = `/api/viewports/${viewportId}/metadata`;
            const response = await fetch(url);

            if (!response.ok) {
                throw new Error(`Failed to fetch metadata: ${response.statusText}`);
            }

            const metadata = await response.json();
            this.metadata.set(viewportId, metadata);

            return metadata;
        } catch (error) {
            console.error(`Error loading metadata for ${viewportId}:`, error);
            throw error;
        }
    }

    /**
     * Select the best pyramid level based on zoom level
     * This helps with multi-resolution rendering (optional)
     */
    selectPyramidLevel(mapZoom: number): number {
        // Map zoom levels (e.g., from Deck.gl) to pyramid levels
        // Lower zoom = higher pyramid level (more downsampled)
        // Zoom 0-3: level 5 (1/32 resolution)
        // Zoom 4-5: level 4 (1/16 resolution)
        // Zoom 6-7: level 3 (1/8 resolution)
        // Zoom 8-9: level 2 (1/4 resolution)
        // Zoom 10-11: level 1 (1/2 resolution)
        // Zoom 12+: level 0 (full resolution)

        if (mapZoom >= 12) return 0;
        if (mapZoom >= 10) return 1;
        if (mapZoom >= 8) return 2;
        if (mapZoom >= 6) return 3;
        if (mapZoom >= 4) return 4;
        return 5;
    }

    /**
     * Convert GeoTIFF to the binary format expected by EmbeddingLoader
     * (for compatibility if needed)
     */
    async convertToEmbeddingFormat(
        viewportId: string,
        year: number,
        level: number
    ): Promise<ArrayBuffer> {
        const embeddings = await this.loadPyramidLevel(viewportId, year, level);

        // Get metadata to calculate dimensions
        const metadata = await this.loadViewportMetadata(viewportId);

        // For now, just return the embeddings buffer
        // In the future, could add 64-byte header like EmbeddingLoader expects
        return embeddings.buffer;
    }

    /**
     * Clear cache
     */
    clearCache(): void {
        this.cache.clear();
    }

    /**
     * Get cache size (for debugging)
     */
    getCacheSize(): number {
        return this.cache.size;
    }
}

/**
 * Helper to check if value is array-like
 */
const ArrayLike = {
    prototype: Object.create(null)
};
