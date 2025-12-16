/**
 * Load and manage TESSERA embeddings
 */

import type { EmbeddingHeader } from './DataTypes';

export class EmbeddingLoader {
    private cache: Map<number, Float32Array> = new Map();
    private headers: Map<number, EmbeddingHeader> = new Map();

    async load(year: number, baseUrl: string): Promise<Float32Array> {
        // Check cache
        if (this.cache.has(year)) {
            return this.cache.get(year)!;
        }

        // Fetch file
        const url = `${baseUrl}/embeddings_${year}.bin`;
        const response = await fetch(url);
        const buffer = await response.arrayBuffer();

        // Parse header
        const header = this.parseHeader(buffer);
        this.headers.set(year, header);

        // Extract embeddings (skip 64-byte header)
        const embeddings = new Float32Array(
            buffer,
            64,
            header.width * header.height * header.dimensions
        );

        // Cache
        this.cache.set(year, embeddings);

        return embeddings;
    }

    private parseHeader(buffer: ArrayBuffer): EmbeddingHeader {
        const view = new DataView(buffer);

        const magic = String.fromCharCode(
            view.getUint8(0),
            view.getUint8(1),
            view.getUint8(2),
            view.getUint8(3)
        );

        return {
            magic,
            version: view.getUint32(4, true),
            year: view.getUint32(8, true),
            width: view.getUint32(12, true),
            height: view.getUint32(16, true),
            dimensions: view.getUint32(20, true),
            bounds: [
                view.getFloat64(24, true),
                view.getFloat64(32, true),
                view.getFloat64(40, true),
                view.getFloat64(48, true)
            ]
        };
    }

    getHeader(year: number): EmbeddingHeader | undefined {
        return this.headers.get(year);
    }

    clearCache(): void {
        this.cache.clear();
    }
}
