<script lang="ts">
	import { onMount } from 'svelte';
	import L from 'leaflet';

	// Props
	export let viewportId: string = '';
	export let onClose: () => void = () => {};

	// State
	let maps: { osm?: L.Map; sentinel2?: L.Map; embeddings?: L.Map } = {};
	let selectedYear = 2024;
	let availableYears: number[] = [];
	let similarityMode = false;
	let currentZoom = 13;
	let currentPyramidLevel = 0;
	let isLoading = true;
	let errorMessage = '';
	let tileLayers: { sentinel2?: L.TileLayer; embeddings?: L.TileLayer } = {};

	const TILE_SIZE = 2048;

	// Map zoom to pyramid level
	function zoomToPyramidLevel(z: number, maxLevel: number = 5): number {
		const level = Math.floor((18 - z) / 2);
		return Math.max(0, Math.min(maxLevel, level));
	}

	// Initialize maps
	async function initializeMaps() {
		try {
			isLoading = true;
			errorMessage = '';

			// Get viewport metadata
			const metadataRes = await fetch(`/api/viewports/${viewportId}/metadata`);
			if (!metadataRes.ok) {
				throw new Error('Failed to load viewport metadata');
			}

			const metadata = await metadataRes.json();
			const bounds = metadata.bounds || { minLon: -0.02, minLat: 52.11, maxLon: 0.27, maxLat: 52.30 };
			const center: [number, number] = [
				(bounds.minLat + bounds.maxLat) / 2,
				(bounds.minLon + bounds.maxLon) / 2
			];

			// Set available years
			availableYears = (metadata.years || [2024]).sort((a: number, b: number) => b - a);
			selectedYear = availableYears[0] || 2024;

			// Create OSM map (reference map)
			const osmMapEl = document.getElementById('map-osm');
			if (!osmMapEl) throw new Error('OSM map container not found');

			maps.osm = L.map(osmMapEl, {
				center: center,
				zoom: 13,
				zoomControl: true,
				minZoom: 5,
				maxZoom: 18
			});

			L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
				attribution: '© OpenStreetMap contributors',
				maxZoom: 19
			}).addTo(maps.osm);

			// Create Sentinel-2 map
			const sentinel2MapEl = document.getElementById('map-sentinel2');
			if (!sentinel2MapEl) throw new Error('Sentinel-2 map container not found');

			maps.sentinel2 = L.map(sentinel2MapEl, {
				center: center,
				zoom: 13,
				zoomControl: true,
				minZoom: 5,
				maxZoom: 18
			});

			tileLayers.sentinel2 = L.tileLayer(`/api/tiles/sentinel2/${viewportId}/${selectedYear}/{z}/{x}/{y}.png`, {
				attribution: 'Sentinel-2',
				maxZoom: 18,
				minZoom: 5,
				tileSize: TILE_SIZE,
				zoomOffset: -3
			}).addTo(maps.sentinel2);

			// Create Embeddings map
			const embeddingsMapEl = document.getElementById('map-embeddings');
			if (!embeddingsMapEl) throw new Error('Embeddings map container not found');

			maps.embeddings = L.map(embeddingsMapEl, {
				center: center,
				zoom: 13,
				zoomControl: true,
				minZoom: 5,
				maxZoom: 18
			});

			tileLayers.embeddings = L.tileLayer(`/api/tiles/embeddings/${viewportId}/${selectedYear}/{z}/{x}/{y}.png`, {
				attribution: 'TESSERA',
				maxZoom: 18,
				minZoom: 5,
				tileSize: TILE_SIZE,
				zoomOffset: -3
			}).addTo(maps.embeddings);

			// Set up synchronization
			setupMapSync();

			// Track zoom level
			maps.osm.on('zoom', () => {
				currentZoom = maps.osm?.getZoom() || 13;
				currentPyramidLevel = zoomToPyramidLevel(currentZoom);
			});

			isLoading = false;
		} catch (err) {
			console.error('Error initializing maps:', err);
			errorMessage = `Failed to initialize maps: ${err instanceof Error ? err.message : String(err)}`;
			isLoading = false;
		}
	}

	// Synchronize maps
	function setupMapSync() {
		if (!maps.osm || !maps.sentinel2 || !maps.embeddings) return;

		let syncing = false;

		// OSM is the reference map
		maps.osm!.on('move zoom', () => {
			if (syncing) return;

			syncing = true;
			const center = maps.osm!.getCenter();
			const zoom = maps.osm!.getZoom();

			maps.sentinel2!.setView(center, zoom, { animate: false });
			maps.embeddings!.setView(center, zoom, { animate: false });

			syncing = false;
		});
	}

	// Change year
	async function changeYear(newYear: number) {
		if (!maps.sentinel2 || !maps.embeddings || !tileLayers.sentinel2 || !tileLayers.embeddings) return;

		selectedYear = newYear;

		// Update Sentinel-2 layer
		maps.sentinel2.removeLayer(tileLayers.sentinel2);
		tileLayers.sentinel2 = L.tileLayer(`/api/tiles/sentinel2/${viewportId}/${selectedYear}/{z}/{x}/{y}.png`, {
			attribution: 'Sentinel-2',
			maxZoom: 18,
			minZoom: 5,
			tileSize: TILE_SIZE,
			zoomOffset: -3
		}).addTo(maps.sentinel2);

		// Update Embeddings layer
		maps.embeddings.removeLayer(tileLayers.embeddings);
		tileLayers.embeddings = L.tileLayer(`/api/tiles/embeddings/${viewportId}/${selectedYear}/{z}/{x}/{y}.png`, {
			attribution: 'TESSERA',
			maxZoom: 18,
			minZoom: 5,
			tileSize: TILE_SIZE,
			zoomOffset: -3
		}).addTo(maps.embeddings);
	}

	// Toggle similarity mode
	function toggleSimilarityMode() {
		similarityMode = !similarityMode;
		if (similarityMode) {
			console.log(`Entered similarity mode at pyramid level ${currentPyramidLevel}`);
		} else {
			console.log('Exited similarity mode');
		}
	}

	onMount(() => {
		if (viewportId) {
			initializeMaps();
		}

		// Clean up on unmount
		return () => {
			Object.values(maps).forEach(map => map?.remove());
		};
	});

	// Define Leaflet CSS
	let leafletCss: string;
	onMount(async () => {
		const link = document.createElement('link');
		link.rel = 'stylesheet';
		link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
		document.head.appendChild(link);
	});
</script>

<div class="three-pane-container">
	<!-- Control Panel -->
	<div class="control-panel">
		<h2>Three-Pane Synchronized Viewer</h2>

		<div class="controls">
			<div class="control-group">
				<label for="year-select">Year:</label>
				<select id="year-select" bind:value={selectedYear} on:change={() => changeYear(selectedYear)}>
					{#each availableYears as year}
						<option value={year}>{year}</option>
					{/each}
				</select>
			</div>

			<div class="control-group">
				<button
					class="btn btn-similarity"
					class:active={similarityMode}
					on:click={toggleSimilarityMode}
				>
					{similarityMode ? 'Exit' : 'Enter'} Similarity Mode
				</button>
			</div>

			<div class="control-group">
				<span class="zoom-info">
					Zoom: {currentZoom} | Pyramid Level: {currentPyramidLevel}
				</span>
			</div>

			<button class="btn btn-close" on:click={onClose}>Close</button>
		</div>

		{#if errorMessage}
			<div class="error-message">{errorMessage}</div>
		{/if}

		{#if isLoading}
			<div class="loading-message">Loading maps...</div>
		{/if}
	</div>

	<!-- Map Container -->
	<div class="map-container">
		<div class="map-pane">
			<div class="map-header">OpenStreetMap</div>
			<div id="map-osm" class="map"></div>
		</div>

		<div class="map-pane">
			<div class="map-header">Sentinel-2 RGB</div>
			<div id="map-sentinel2" class="map"></div>
		</div>

		<div class="map-pane">
			<div class="map-header">TESSERA Embeddings</div>
			<div id="map-embeddings" class="map"></div>
		</div>
	</div>

	<!-- Status Bar -->
	<div class="status-bar">
		<span>Pan/zoom on any map to navigate • All maps are synchronized</span>
	</div>
</div>

<style>
	.three-pane-container {
		display: flex;
		flex-direction: column;
		height: 100vh;
		background: #1a1a1a;
		color: #fff;
	}

	.control-panel {
		background: #2a2a2a;
		padding: 15px 20px;
		border-bottom: 1px solid #333;
		box-shadow: 0 2px 10px rgba(0, 0, 0, 0.5);
	}

	.control-panel h2 {
		margin: 0 0 15px 0;
		font-size: 18px;
		font-weight: 600;
	}

	.controls {
		display: flex;
		align-items: center;
		gap: 20px;
		flex-wrap: wrap;
	}

	.control-group {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	label {
		font-size: 14px;
		font-weight: 500;
	}

	select {
		padding: 8px 12px;
		border: 1px solid #444;
		border-radius: 4px;
		background: #333;
		color: #fff;
		font-size: 14px;
		cursor: pointer;
	}

	.btn {
		padding: 8px 16px;
		border: none;
		border-radius: 4px;
		cursor: pointer;
		font-weight: 600;
		font-size: 14px;
		transition: all 0.2s ease;
	}

	.btn-similarity {
		background: #0056b3;
		color: white;
	}

	.btn-similarity:hover {
		background: #004494;
	}

	.btn-similarity.active {
		background: #28a745;
	}

	.btn-close {
		background: #dc3545;
		color: white;
		margin-left: auto;
	}

	.btn-close:hover {
		background: #c82333;
	}

	.zoom-info {
		font-size: 12px;
		color: #aaa;
		font-family: monospace;
	}

	.error-message {
		margin-top: 10px;
		padding: 10px 12px;
		background: #8b0000;
		border-radius: 4px;
		font-size: 12px;
		color: #fdd;
	}

	.loading-message {
		margin-top: 10px;
		padding: 10px 12px;
		background: #1e5a96;
		border-radius: 4px;
		font-size: 12px;
		color: #adf;
	}

	.map-container {
		display: flex;
		flex: 1;
		overflow: hidden;
		gap: 2px;
		background: #000;
	}

	.map-pane {
		flex: 1;
		position: relative;
		background: #2a2a2a;
		overflow: hidden;
	}

	.map-header {
		position: absolute;
		top: 10px;
		left: 10px;
		background: rgba(0, 0, 0, 0.7);
		color: white;
		padding: 8px 12px;
		border-radius: 4px;
		font-weight: 600;
		font-size: 13px;
		z-index: 400;
		backdrop-filter: blur(5px);
		pointer-events: none;
	}

	.map {
		width: 100%;
		height: 100%;
	}

	.status-bar {
		background: #2a2a2a;
		padding: 10px 20px;
		font-size: 12px;
		color: #999;
		border-top: 1px solid #333;
		text-align: center;
	}

	/* Leaflet overrides for dark theme */
	:global(.leaflet-control-zoom) {
		background: #333 !important;
		border: 1px solid #555 !important;
	}

	:global(.leaflet-control-zoom a) {
		background: #333 !important;
		color: #fff !important;
		border-bottom: 1px solid #555 !important;
	}

	:global(.leaflet-control-zoom a:hover) {
		background: #444 !important;
	}

	:global(.leaflet-tile) {
		filter: none;
	}
</style>
