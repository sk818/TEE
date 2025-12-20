<script lang="ts">
	/**
	 * ⚠️ DEPRECATED - Do not use this component
	 *
	 * This component is deprecated and should not be used.
	 * Use /bangalore_viewer_3panel_blore.html (3-panel viewer from blore project) instead.
	 *
	 * The blore 3-panel viewer is:
	 * - More stable and tested
	 * - Better synchronized
	 * - Simpler and cleaner code
	 * - Fully integrated with viewport.txt
	 * - No zoom issues
	 *
	 * All ViewportSelector buttons now redirect to bangalore_viewer_3panel_blore.html
	 */
	import { onMount } from 'svelte';
	import L from 'leaflet';

	// Props
	export let viewportId: string = '';
	export let onClose: () => void = () => {};

	// State
	let maps: { osm?: L.Map; embedding?: L.Map; rgb?: L.Map } = {};
	let currentEmbeddingYear = '2024';
	let labelInput = 'building';
	let labelCount = 0;
	let isLoading = true;
	let errorMessage = '';

	// Storage for labels: {panel: [[lat, lon, label], ...]}
	let labels: {
		osm: [number, number, string][];
		embedding: [number, number, string][];
		rgb: [number, number, string][];
	} = {
		osm: [],
		embedding: [],
		rgb: []
	};

	// Storage for marker objects: {panel: {key: marker}}
	let markers: {
		osm: { [key: string]: L.Marker };
		embedding: { [key: string]: L.Marker };
		rgb: { [key: string]: L.Marker };
	} = {
		osm: {},
		embedding: {},
		rgb: {}
	};

	let center: [number, number] = [12.97, 77.59];
	let bounds: { minLon: number; minLat: number; maxLon: number; maxLat: number } | null = null;
	let zoom = 11;

	// Load viewport metadata to get correct center and bounds
	async function loadViewportMetadata() {
		try {
			const response = await fetch(`/api/viewports/${viewportId}/metadata`);
			if (response.ok) {
				const metadata = await response.json();
				if (metadata.center) {
					center = metadata.center;
					console.log(`Loaded viewport center: ${center}`);
				}
				if (metadata.bounds) {
					bounds = metadata.bounds;
				}
			}
		} catch (err) {
			console.warn(`Could not load viewport metadata: ${err}`);
		}
	}

	// Create all three maps
	function createMaps() {
		// OSM Map - with zoom control
		maps.osm = L.map('map-osm', {
			center: center,
			zoom: zoom,
			zoomControl: true,
			minZoom: 6,
			maxZoom: 18
		});

		L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
			attribution: '© OpenStreetMap contributors',
			maxZoom: 19
		}).addTo(maps.osm);

		// Embedding Map (Tessera) - NO zoom control, uses zoomOffset
		maps.embedding = L.map('map-embedding', {
			center: center,
			zoom: zoom,
			zoomControl: false,
			minZoom: 6,
			maxZoom: 17,
			dragging: true,
			touchZoom: false  // Disable touch zoom to prevent accidental zoom
		});

		L.tileLayer(`/api/tiles/rgb/${viewportId}/${currentEmbeddingYear}/{z}/{x}/{y}.png`, {
			attribution: 'RGB Pyramids',
			opacity: 1.0,
			maxZoom: 17,
			minZoom: 6,
			tileSize: 2048,
			zoomOffset: -3
		}).addTo(maps.embedding);

		// RGB Satellite Map - NO zoom control, uses zoomOffset
		maps.rgb = L.map('map-rgb', {
			center: center,
			zoom: zoom,
			zoomControl: false,
			minZoom: 6,
			maxZoom: 17,
			dragging: true,
			touchZoom: false  // Disable touch zoom to prevent accidental zoom
		});

		L.tileLayer(`/api/tiles/sentinel2/${viewportId}/${currentEmbeddingYear}/{z}/{x}/{y}.png`, {
			attribution: 'Sentinel-2 RGB',
			opacity: 1.0,
			maxZoom: 17,
			minZoom: 6,
			tileSize: 2048,
			zoomOffset: -3
		}).addTo(maps.rgb);

		// Fit bounds if available
		if (bounds && maps.osm) {
			const leafletBounds = L.latLngBounds(
				[bounds.minLat, bounds.minLon],
				[bounds.maxLat, bounds.maxLon]
			);

			// Add padding (10% on each side)
			const padding = 0.1;
			const latDiff = bounds.maxLat - bounds.minLat;
			const lonDiff = bounds.maxLon - bounds.minLon;
			const paddedBounds = L.latLngBounds(
				[bounds.minLat - latDiff * padding, bounds.minLon - lonDiff * padding],
				[bounds.maxLat + latDiff * padding, bounds.maxLon + lonDiff * padding]
			);

			// Fit all maps to the same bounds
			maps.osm.fitBounds(paddedBounds, { padding: [20, 20] });
			maps.embedding?.fitBounds(paddedBounds, { padding: [20, 20] });
			maps.rgb?.fitBounds(paddedBounds, { padding: [20, 20] });
		}

		// Add click handlers
		const panels: Array<'osm' | 'embedding' | 'rgb'> = ['osm', 'embedding', 'rgb'];
		panels.forEach(panel => {
			maps[panel]?.on('click', function(e: L.LeafletMouseEvent) {
				const label = labelInput || 'unlabeled';
				addMarker(panel, e.latlng.lat, e.latlng.lng, label);
			});
		});

		// Synchronize maps
		syncMaps();

		isLoading = false;
	}

	// Synchronize all maps
	function syncMaps() {
		// Use OSM as reference map
		const refMap = maps.osm;
		if (!refMap) return;

		refMap.on('zoomend moveend', function() {
			const refCenter = refMap.getCenter();
			const refZoom = refMap.getZoom();

			// Sync all maps to the same center and zoom
			// The zoomOffset: -3 on embedding/RGB is handled by Leaflet automatically
			if (maps.embedding) {
				maps.embedding.setView(refCenter, refZoom, { animate: false });
			}
			if (maps.rgb) {
				maps.rgb.setView(refCenter, refZoom, { animate: false });
			}
		});
	}

	// Add marker
	function addMarker(panel: 'osm' | 'embedding' | 'rgb', lat: number, lon: number, label: string) {
		const key = `${lat.toFixed(6)},${lon.toFixed(6)}`;

		// Check if marker already exists (remove it)
		if (markers[panel][key]) {
			removeMarker(panel, lat, lon);
			return;
		}

		// Create marker
		const marker = L.marker([lat, lon], {
			title: label
		}).addTo(maps[panel]!);

		marker.bindPopup(`<div class="marker-popup">${label}</div>`);

		// Store marker
		markers[panel][key] = marker;
		labels[panel].push([lat, lon, label]);

		updateLabelCount();
		console.log(`Added '${label}' at (${lat.toFixed(4)}, ${lon.toFixed(4)}) on ${panel} panel`);
	}

	// Remove marker
	function removeMarker(panel: 'osm' | 'embedding' | 'rgb', lat: number, lon: number) {
		const key = `${lat.toFixed(6)},${lon.toFixed(6)}`;

		if (markers[panel][key]) {
			maps[panel]?.removeLayer(markers[panel][key]);
			delete markers[panel][key];

			// Remove from labels
			labels[panel] = labels[panel].filter(
				([la, lo]) => Math.abs(la - lat) > 0.00001 || Math.abs(lo - lon) > 0.00001
			);

			updateLabelCount();
			console.log(`Removed marker at (${lat.toFixed(4)}, ${lon.toFixed(4)}) from ${panel} panel`);
		}
	}

	// Update label count
	function updateLabelCount() {
		labelCount = Object.values(labels).reduce((sum, arr) => sum + arr.length, 0);
	}

	// Save labels to localStorage
	function saveLabels() {
		const saveData = {
			labels: labels,
			embeddingYear: currentEmbeddingYear
		};
		localStorage.setItem('tee_labels_3panel', JSON.stringify(saveData));
		alert(`Saved ${labelCount} labels to browser storage`);
	}

	// Load labels from localStorage
	function loadLabels() {
		const stored = localStorage.getItem('tee_labels_3panel');
		if (stored) {
			const saveData = JSON.parse(stored);
			const panels: Array<'osm' | 'embedding' | 'rgb'> = ['osm', 'embedding', 'rgb'];
			panels.forEach(panel => {
				if (saveData.labels[panel]) {
					saveData.labels[panel].forEach(([lat, lon, label]: [number, number, string]) => {
						addMarker(panel, lat, lon, label);
					});
				}
			});
			console.log(
				`Loaded ${Object.values(saveData.labels).reduce((sum: number, arr: any[]) => sum + arr.length, 0)} labels`
			);
		}
	}

	// Clear all labels
	function clearAllLabels() {
		if (!confirm('Clear all labels?')) return;

		const panels: Array<'osm' | 'embedding' | 'rgb'> = ['osm', 'embedding', 'rgb'];
		panels.forEach(panel => {
			Object.values(markers[panel]).forEach(marker => {
				maps[panel]?.removeLayer(marker);
			});
			markers[panel] = {};
			labels[panel] = [];
		});

		updateLabelCount();
		console.log('Cleared all labels');
	}

	// Export labels to JSON
	function exportLabels() {
		const exportData = {
			embeddingYear: currentEmbeddingYear,
			labels: labels,
			timestamp: new Date().toISOString()
		};
		const dataStr = JSON.stringify(exportData, null, 2);
		const dataBlob = new Blob([dataStr], { type: 'application/json' });
		const url = URL.createObjectURL(dataBlob);
		const link = document.createElement('a');
		link.href = url;
		link.download = `tee_labels_${currentEmbeddingYear}_${Date.now()}.json`;
		link.click();
		URL.revokeObjectURL(url);
		console.log('Exported labels to JSON file');
	}

	// Change embedding year
	function changeYear(newYear: string) {
		currentEmbeddingYear = newYear;

		if (!maps.embedding || !maps.rgb) return;

		// Update embedding layer
		maps.embedding.eachLayer(function(layer: L.Layer) {
			if (layer instanceof L.TileLayer) {
				maps.embedding?.removeLayer(layer);
			}
		});

		L.tileLayer(`/api/tiles/rgb/${viewportId}/${currentEmbeddingYear}/{z}/{x}/{y}.png`, {
			attribution: 'RGB Pyramids',
			opacity: 1.0,
			maxZoom: 17,
			minZoom: 6,
			tileSize: 2048,
			zoomOffset: -3
		}).addTo(maps.embedding);

		// Update RGB layer
		maps.rgb.eachLayer(function(layer: L.Layer) {
			if (layer instanceof L.TileLayer) {
				maps.rgb?.removeLayer(layer);
			}
		});

		L.tileLayer(`/api/tiles/sentinel2/${viewportId}/${currentEmbeddingYear}/{z}/{x}/{y}.png`, {
			attribution: 'Sentinel-2 RGB',
			opacity: 1.0,
			maxZoom: 17,
			minZoom: 6,
			tileSize: 2048,
			zoomOffset: -3
		}).addTo(maps.rgb);
	}

	onMount(async () => {
		// Add Leaflet CSS
		const link = document.createElement('link');
		link.rel = 'stylesheet';
		link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
		document.head.appendChild(link);

		// Create maps
		try {
			// Load viewport metadata first to get correct center
			if (viewportId) {
				await loadViewportMetadata();
			}
			createMaps();
			loadLabels();
		} catch (err) {
			console.error('Error initializing maps:', err);
			errorMessage = `Failed to initialize maps: ${err instanceof Error ? err.message : String(err)}`;
			isLoading = false;
		}

		// Clean up on unmount
		return () => {
			Object.values(maps).forEach(map => map?.remove());
		};
	});
</script>

<div class="three-pane-container">
	<!-- Control Panel -->
	<div id="controls">
		<h1>TEE Viewer</h1>

		<label for="year-select">Embedding Year:</label>
		<select id="year-select" bind:value={currentEmbeddingYear} on:change={() => changeYear(currentEmbeddingYear)}>
			<option value="2024">2024</option>
			<option value="2023">2023</option>
			<option value="2022">2022</option>
			<option value="2021">2021</option>
			<option value="2020">2020</option>
			<option value="2019">2019</option>
			<option value="2018">2018</option>
			<option value="2017">2017</option>
		</select>

		<label for="label-input">Label:</label>
		<input type="text" id="label-input" bind:value={labelInput} placeholder="Enter label" />

		<button class="save-btn" on:click={saveLabels}>Save Labels</button>
		<button class="clear-btn" on:click={clearAllLabels}>Clear All</button>
		<button class="export-btn" on:click={exportLabels}>Export JSON</button>

		<span id="label-count">Labels: {labelCount}</span>

		<button class="close-btn" on:click={onClose}>Close</button>
	</div>

	<!-- Map Container -->
	<div id="map-container">
		<div class="panel">
			<div class="panel-header">OpenStreetMap</div>
			<div id="map-osm" class="map"></div>
		</div>
		<div class="panel">
			<div class="panel-header">Tessera Embeddings <span id="embedding-year">{currentEmbeddingYear}</span></div>
			<div id="map-embedding" class="map"></div>
		</div>
		<div class="panel">
			<div class="panel-header">Satellite RGB</div>
			<div id="map-rgb" class="map"></div>
		</div>
	</div>

	<!-- Status Bar -->
	<div id="status">
		<strong>Instructions:</strong> Pan/zoom on left panel (OSM) to navigate • All panels stay synchronized • Click to place labeled markers • Click existing markers to remove
		{#if errorMessage}
			<div class="error-message">{errorMessage}</div>
		{/if}
		{#if isLoading}
			<div class="loading-message">Loading maps...</div>
		{/if}
	</div>
</div>

<style>
	:global(body) {
		margin: 0;
		padding: 0;
		font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
		background: #1a1a1a;
		color: #fff;
		overflow: hidden;
	}

	:global(*) {
		box-sizing: border-box;
	}

	.three-pane-container {
		display: flex;
		flex-direction: column;
		height: 100vh;
		background: #1a1a1a;
		color: #fff;
	}

	#controls {
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		background: #2a2a2a;
		padding: 15px 20px;
		box-shadow: 0 2px 10px rgba(0, 0, 0, 0.5);
		z-index: 1000;
		display: flex;
		align-items: center;
		gap: 15px;
	}

	#controls h1 {
		font-size: 18px;
		font-weight: 600;
		margin-right: 20px;
		margin: 0;
	}

	#controls label {
		font-size: 14px;
		margin-right: 5px;
	}

	#controls select,
	#controls input {
		padding: 8px 12px;
		border: 1px solid #444;
		border-radius: 4px;
		background: #333;
		color: #fff;
		font-size: 14px;
	}

	#controls button {
		padding: 8px 16px;
		border: none;
		border-radius: 4px;
		cursor: pointer;
		font-weight: 600;
		font-size: 14px;
		transition: background 0.2s;
	}

	.save-btn {
		background: #28a745;
		color: white;
	}

	.save-btn:hover {
		background: #218838;
	}

	.clear-btn {
		background: #dc3545;
		color: white;
	}

	.clear-btn:hover {
		background: #c82333;
	}

	.export-btn {
		background: #007bff;
		color: white;
	}

	.export-btn:hover {
		background: #0056b3;
	}

	.close-btn {
		background: #666;
		color: white;
		margin-left: auto;
	}

	.close-btn:hover {
		background: #777;
	}

	#label-count {
		padding: 8px 12px;
		background: #333;
		border-radius: 4px;
		font-weight: 600;
	}

	#map-container {
		position: fixed;
		top: 70px;
		left: 0;
		right: 0;
		bottom: 40px;
		display: grid;
		grid-template-columns: 1fr 1fr 1fr;
		gap: 2px;
		background: #1a1a1a;
	}

	.panel {
		position: relative;
		background: #2a2a2a;
	}

	.panel-header {
		position: absolute;
		top: 10px;
		left: 10px;
		background: rgba(0, 0, 0, 0.7);
		color: white;
		padding: 8px 12px;
		border-radius: 4px;
		font-weight: 600;
		font-size: 14px;
		z-index: 400;
		backdrop-filter: blur(5px);
	}

	.map {
		width: 100%;
		height: 100%;
	}

	#status {
		position: fixed;
		bottom: 0;
		left: 0;
		right: 0;
		background: #2a2a2a;
		padding: 10px 20px;
		font-size: 12px;
		color: #999;
		border-top: 1px solid #333;
	}

	.error-message {
		display: inline-block;
		margin-left: 20px;
		padding: 5px 10px;
		background: #8b0000;
		border-radius: 4px;
		font-size: 11px;
		color: #fdd;
	}

	.loading-message {
		display: inline-block;
		margin-left: 20px;
		padding: 5px 10px;
		background: #1e5a96;
		border-radius: 4px;
		font-size: 11px;
		color: #adf;
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
