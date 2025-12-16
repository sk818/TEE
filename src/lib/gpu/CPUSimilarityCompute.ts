/**
 * CPU-based similarity computation
 */

export interface ComputeParams {
    queryX: number;
    queryY: number;
    threshold: number;
    colormapId: number;
}

export class CPUSimilarityCompute {
    private embeddings: Float32Array = new Float32Array();
    private width: number;
    private height: number;
    private embeddingDims: number;

    constructor(width: number, height: number, dims: number) {
        this.width = width;
        this.height = height;
        this.embeddingDims = dims;
    }

    async initialize(embeddings: Float32Array): Promise<void> {
        this.embeddings = embeddings;
        console.log('✅ CPU-based similarity compute initialized');
    }

    async compute(params: ComputeParams): Promise<Float32Array> {
        const { queryX, queryY, threshold, colormapId } = params;

        const numPixels = this.width * this.height;

        // For large datasets, check if allocation would be viable
        const estimatedMemoryMB = (numPixels * 4 * 4) / (1024 * 1024); // 4 values per pixel, 4 bytes each
        if (estimatedMemoryMB > 500) {
            console.warn(`Large dataset detected (${estimatedMemoryMB.toFixed(0)}MB). Processing in chunks...`);
            return this.computeInChunks(queryX, queryY, threshold, colormapId);
        }

        // Compute similarities
        const similarities = this.computeSimilarities(queryX, queryY);

        // Apply threshold and colormap
        const colors = this.applyThresholdAndColormap(similarities, threshold, colormapId);

        return colors;
    }

    private computeInChunks(queryX: number, queryY: number, threshold: number, colormapId: number): Float32Array {
        const numPixels = this.width * this.height;
        const colors = new Float32Array(numPixels * 4);

        // Process in chunks of 256x256 pixels
        const chunkSize = 256;
        const chunksX = Math.ceil(this.width / chunkSize);
        const chunksY = Math.ceil(this.height / chunkSize);

        const queryIdx = queryY * this.width + queryX;
        const queryStart = queryIdx * this.embeddingDims;
        const queryEmbedding = this.embeddings.slice(queryStart, queryStart + this.embeddingDims);

        // Process each chunk
        for (let cy = 0; cy < chunksY; cy++) {
            for (let cx = 0; cx < chunksX; cx++) {
                const startY = cy * chunkSize;
                const startX = cx * chunkSize;
                const endY = Math.min(startY + chunkSize, this.height);
                const endX = Math.min(startX + chunkSize, this.width);

                // Process pixels in this chunk
                for (let y = startY; y < endY; y++) {
                    for (let x = startX; x < endX; x++) {
                        const pixelIdx = y * this.width + x;
                        const pixelStart = pixelIdx * this.embeddingDims;

                        // Compute cosine similarity for this pixel
                        let dotProduct = 0;
                        for (let j = 0; j < this.embeddingDims; j++) {
                            dotProduct += this.embeddings[pixelStart + j] * queryEmbedding[j];
                        }

                        // Apply threshold and colormap
                        const similarity = dotProduct;
                        const colorIdx = pixelIdx * 4;

                        if (similarity < threshold) {
                            // Below threshold: transparent
                            colors[colorIdx] = 0;
                            colors[colorIdx + 1] = 0;
                            colors[colorIdx + 2] = 0;
                            colors[colorIdx + 3] = 0;
                        } else {
                            // Above threshold: apply colormap
                            const normalized = (similarity - threshold) / (1 - threshold);

                            if (colormapId === 0) {
                                // Binary: yellow
                                colors[colorIdx] = 1.0;
                                colors[colorIdx + 1] = 0.843;
                                colors[colorIdx + 2] = 0.0;
                                colors[colorIdx + 3] = 0.8;
                            } else if (colormapId === 1) {
                                // Viridis
                                const rgb = this.viridis(normalized);
                                colors[colorIdx] = rgb[0];
                                colors[colorIdx + 1] = rgb[1];
                                colors[colorIdx + 2] = rgb[2];
                                colors[colorIdx + 3] = 0.8;
                            } else {
                                // Grayscale
                                colors[colorIdx] = normalized;
                                colors[colorIdx + 1] = normalized;
                                colors[colorIdx + 2] = normalized;
                                colors[colorIdx + 3] = 0.8;
                            }
                        }
                    }
                }
            }
        }

        return colors;
    }

    private computeSimilarities(queryX: number, queryY: number): Float32Array {
        const numPixels = this.width * this.height;
        const similarities = new Float32Array(numPixels);

        const queryIdx = queryY * this.width + queryX;
        const queryStart = queryIdx * this.embeddingDims;
        const queryEmbedding = this.embeddings.slice(queryStart, queryStart + this.embeddingDims);

        // Compute cosine similarity for all pixels
        for (let i = 0; i < numPixels; i++) {
            const pixelStart = i * this.embeddingDims;
            let dotProduct = 0;

            for (let j = 0; j < this.embeddingDims; j++) {
                dotProduct += this.embeddings[pixelStart + j] * queryEmbedding[j];
            }

            similarities[i] = dotProduct;
        }

        return similarities;
    }

    private applyThresholdAndColormap(
        similarities: Float32Array,
        threshold: number,
        colormapId: number
    ): Float32Array {
        const numPixels = similarities.length;
        const colors = new Float32Array(numPixels * 4); // RGBA

        for (let i = 0; i < numPixels; i++) {
            const similarity = similarities[i];
            const colorIdx = i * 4;

            if (similarity < threshold) {
                // Below threshold: transparent
                colors[colorIdx] = 0;
                colors[colorIdx + 1] = 0;
                colors[colorIdx + 2] = 0;
                colors[colorIdx + 3] = 0;
            } else {
                // Above threshold: apply colormap
                const normalized = (similarity - threshold) / (1 - threshold);

                if (colormapId === 0) {
                    // Binary: yellow
                    colors[colorIdx] = 1.0;
                    colors[colorIdx + 1] = 0.843;
                    colors[colorIdx + 2] = 0.0;
                    colors[colorIdx + 3] = 0.8;
                } else if (colormapId === 1) {
                    // Viridis
                    const rgb = this.viridis(normalized);
                    colors[colorIdx] = rgb[0];
                    colors[colorIdx + 1] = rgb[1];
                    colors[colorIdx + 2] = rgb[2];
                    colors[colorIdx + 3] = 0.8;
                } else {
                    // Grayscale
                    colors[colorIdx] = normalized;
                    colors[colorIdx + 1] = normalized;
                    colors[colorIdx + 2] = normalized;
                    colors[colorIdx + 3] = 0.8;
                }
            }
        }

        return colors;
    }

    private viridis(t: number): [number, number, number] {
        // Viridis colormap approximation (0-1 range)
        t = Math.max(0, Math.min(1, t));

        const c0 = [0.267004, 0.004874, 0.329415];
        const c1 = [0.127568, 0.566949, 0.550556];
        const c2 = [0.993248, 0.906157, 0.143936];

        const t2 = t * t;

        const temp = [
            c0[0] + (c1[0] - c0[0]) * t,
            c0[1] + (c1[1] - c0[1]) * t,
            c0[2] + (c1[2] - c0[2]) * t
        ];

        const final = [
            temp[0] + (c2[0] - temp[0]) * t2,
            temp[1] + (c2[1] - temp[1]) * t2,
            temp[2] + (c2[2] - temp[2]) * t2
        ];

        return [final[0], final[1], final[2]];
    }

    destroy(): void {
        // No GPU resources to clean up
    }
}
