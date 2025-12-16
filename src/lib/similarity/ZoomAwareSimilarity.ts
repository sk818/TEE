/**
 * Zoom-aware similarity computation using coarsened embeddings.
 *
 * This module loads and manages coarsened embedding pyramids, enabling fast
 * similarity computation at any zoom level by selecting the appropriate
 * pyramid level based on the current map zoom.
 *
 * Performance:
 * - Level 0: 19.4M pixels × 128D = ~5000ms
 * - Level 3: 303K pixels × 128D = ~75ms (66x faster)
 * - Level 5: 18K pixels × 128D = ~5ms (1000x faster)
 */

import { parseNPY } from './npy-parser';

export interface SimilarityResult {
	level: number;
	width: number;
	height: number;
	dimensions: number;
	similarities: Float32Array;
	referencePixel: { x: number; y: number };
	computeTime: number;
}

export class ZoomAwareSimilarity {
	private embeddings: Float32Array | null = null;
	private width: number = 0;
	private height: number = 0;
	private dimensions: number = 128;
	private currentLevel: number = 0;

	/**
	 * Load coarsened embeddings for a specific pyramid level.
	 *
	 * @param viewportId - The viewport ID
	 * @param year - The year to load
	 * @param level - The pyramid level (0-5)
	 * @throws Error if loading fails
	 */
	async loadEmbeddingsForLevel(
		viewportId: string,
		year: number,
		level: number
	): Promise<void> {
		const url = `/api/viewports/${viewportId}/coarsened-embeddings/${year}/level_${level}.npy`;

		try {
			const response = await fetch(url);
			if (!response.ok) {
				throw new Error(`HTTP error! status: ${response.status}`);
			}

			const arrayBuffer = await response.arrayBuffer();
			this.embeddings = parseNPY(arrayBuffer);

			// Calculate dimensions for this level
			const levelScale = Math.pow(2, level);
			this.width = Math.floor(4408 / levelScale);
			this.height = Math.floor(4408 / levelScale);
			this.currentLevel = level;

			console.log(
				`[ZoomAwareSimilarity] Loaded level ${level}: ` +
				`${this.width}×${this.height}×${this.dimensions} ` +
				`(${this.embeddings.length} values)`
			);
		} catch (error) {
			console.error(`[ZoomAwareSimilarity] Error loading embeddings for level ${level}:`, error);
			throw error;
		}
	}

	/**
	 * Compute cosine similarity for all pixels relative to a reference pixel.
	 *
	 * @param clickX - Reference pixel X coordinate
	 * @param clickY - Reference pixel Y coordinate
	 * @returns Array of similarity scores (0-1) for all pixels
	 * @throws Error if embeddings not loaded
	 */
	computeSimilarity(clickX: number, clickY: number): SimilarityResult {
		if (!this.embeddings) {
			throw new Error('Embeddings not loaded. Call loadEmbeddingsForLevel first.');
		}

		// Validate coordinates
		if (clickX < 0 || clickX >= this.width || clickY < 0 || clickY >= this.height) {
			throw new Error(
				`Invalid click coordinates (${clickX}, ${clickY}) ` +
				`for image size ${this.width}×${this.height}`
			);
		}

		const startTime = performance.now();

		// Get reference pixel embedding
		const refIdx = (clickY * this.width + clickX) * this.dimensions;
		const refVector = this.embeddings.slice(refIdx, refIdx + this.dimensions);

		// Normalize reference vector
		const refNorm = this.vectorNorm(refVector);
		if (refNorm === 0) {
			throw new Error('Reference pixel has zero norm');
		}
		const refNormalized = new Float32Array(this.dimensions);
		for (let i = 0; i < this.dimensions; i++) {
			refNormalized[i] = refVector[i] / refNorm;
		}

		// Compute cosine similarity for all pixels
		const numPixels = this.width * this.height;
		const similarities = new Float32Array(numPixels);

		for (let i = 0; i < numPixels; i++) {
			const idx = i * this.dimensions;
			const vector = this.embeddings.slice(idx, idx + this.dimensions);

			// Compute dot product with normalized vectors
			let dot = 0;
			let vectorNorm = 0;

			for (let j = 0; j < this.dimensions; j++) {
				dot += refNormalized[j] * vector[j];
				vectorNorm += vector[j] * vector[j];
			}

			if (vectorNorm > 0) {
				vectorNorm = Math.sqrt(vectorNorm);
				similarities[i] = Math.max(-1, Math.min(1, dot / vectorNorm));
			} else {
				similarities[i] = 0;
			}
		}

		const computeTime = performance.now() - startTime;

		console.log(
			`[ZoomAwareSimilarity] Computed similarity in ${computeTime.toFixed(1)}ms ` +
			`for ${numPixels.toLocaleString()} pixels`
		);

		return {
			level: this.currentLevel,
			width: this.width,
			height: this.height,
			dimensions: this.dimensions,
			similarities,
			referencePixel: { x: clickX, y: clickY },
			computeTime
		};
	}

	/**
	 * Get statistics about the similarities.
	 *
	 * @param similarities - Array of similarity scores
	 * @returns Statistics object
	 */
	static getStatistics(similarities: Float32Array): {
		min: number;
		max: number;
		mean: number;
		std: number;
		count: number;
	} {
		if (similarities.length === 0) {
			return { min: 0, max: 0, mean: 0, std: 0, count: 0 };
		}

		// Calculate min and max
		let min = similarities[0];
		let max = similarities[0];
		let sum = 0;

		for (let i = 0; i < similarities.length; i++) {
			const val = similarities[i];
			if (val < min) min = val;
			if (val > max) max = val;
			sum += val;
		}

		const mean = sum / similarities.length;

		// Calculate standard deviation
		let sumSquaredDiff = 0;
		for (let i = 0; i < similarities.length; i++) {
			const diff = similarities[i] - mean;
			sumSquaredDiff += diff * diff;
		}

		const std = Math.sqrt(sumSquaredDiff / similarities.length);

		return {
			min,
			max,
			mean,
			std,
			count: similarities.length
		};
	}

	/**
	 * Get the top-K most similar pixels.
	 *
	 * @param similarities - Array of similarity scores
	 * @param k - Number of top results to return
	 * @returns Array of {pixelIndex, similarity, x, y} sorted by similarity descending
	 */
	getTopSimilar(similarities: Float32Array, k: number = 100): Array<{
		pixelIndex: number;
		similarity: number;
		x: number;
		y: number;
	}> {
		// Create array of indices and values
		const indexed = Array.from(similarities).map((val, idx) => ({
			pixelIndex: idx,
			similarity: val,
			x: idx % this.width,
			y: Math.floor(idx / this.width)
		}));

		// Sort by similarity (descending)
		indexed.sort((a, b) => b.similarity - a.similarity);

		// Return top K
		return indexed.slice(0, Math.min(k, indexed.length));
	}

	/**
	 * Convert lat/lng coordinates to pixel coordinates at current pyramid level.
	 *
	 * @param lat - Latitude
	 * @param lng - Longitude
	 * @param bounds - Viewport bounds {minLon, minLat, maxLon, maxLat}
	 * @returns Pixel coordinates {x, y}
	 */
	latLngToPixel(
		lat: number,
		lng: number,
		bounds: { minLon: number; minLat: number; maxLon: number; maxLat: number }
	): { x: number; y: number } {
		// Normalize lat/lng to 0-1 within bounds
		const lonNorm = (lng - bounds.minLon) / (bounds.maxLon - bounds.minLon);
		const latNorm = (bounds.maxLat - lat) / (bounds.maxLat - bounds.minLat);

		// Convert to pixel coordinates
		const x = Math.floor(lonNorm * this.width);
		const y = Math.floor(latNorm * this.height);

		// Clamp to bounds
		return {
			x: Math.max(0, Math.min(this.width - 1, x)),
			y: Math.max(0, Math.min(this.height - 1, y))
		};
	}

	/**
	 * Convert pixel coordinates to lat/lng.
	 *
	 * @param x - Pixel X coordinate
	 * @param y - Pixel Y coordinate
	 * @param bounds - Viewport bounds
	 * @returns Lat/lng coordinates
	 */
	pixelToLatLng(
		x: number,
		y: number,
		bounds: { minLon: number; minLat: number; maxLon: number; maxLat: number }
	): { lat: number; lng: number } {
		const lonNorm = x / this.width;
		const latNorm = y / this.height;

		const lng = bounds.minLon + lonNorm * (bounds.maxLon - bounds.minLon);
		const lat = bounds.maxLat - latNorm * (bounds.maxLat - bounds.minLat);

		return { lat, lng };
	}

	/**
	 * Get current state.
	 */
	getState() {
		return {
			level: this.currentLevel,
			width: this.width,
			height: this.height,
			dimensions: this.dimensions,
			loaded: this.embeddings !== null,
			numPixels: this.width * this.height,
			numValues: this.embeddings?.length || 0
		};
	}

	/**
	 * Compute vector norm (L2 norm / Euclidean norm).
	 */
	private vectorNorm(vector: Float32Array): number {
		let sum = 0;
		for (let i = 0; i < vector.length; i++) {
			sum += vector[i] * vector[i];
		}
		return Math.sqrt(sum);
	}

	/**
	 * Compute dot product of two vectors.
	 */
	private dotProduct(a: Float32Array, b: Float32Array): number {
		let sum = 0;
		for (let i = 0; i < Math.min(a.length, b.length); i++) {
			sum += a[i] * b[i];
		}
		return sum;
	}
}
