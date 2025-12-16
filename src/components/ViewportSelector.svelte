<script lang="ts">
    import { onMount, createEventDispatcher } from 'svelte';
    import maplibregl from 'maplibre-gl';
    import 'maplibre-gl/dist/maplibre-gl.css';
    import { VIEWPORT_SIZE_KM, calculateBounds, createBoxGeoJSON } from '../lib/utils/coordinates';
    import type { ViewportConfig, Bounds } from '../lib/data/DataTypes';

    const dispatch = createEventDispatcher();

    let mapContainer: HTMLDivElement;
    let map: maplibregl.Map;
    let searchQuery = '';

    // Processing state
    let processingState: 'idle' | 'requesting' | 'downloading' | 'creating_pyramids' | 'complete' | 'error' = 'idle';
    let processingProgress = 0;
    let taskId: string | null = null;
    let errorMessage = '';
    const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

    let centerLng = 0.1218; // Cambridge, UK
    let centerLat = 52.2053;

    const presets = [
        { name: 'Cambridge, UK', lng: 0.1218, lat: 52.2053 },
        { name: 'Amazon Rainforest', lng: -60.0, lat: -3.0 },
        { name: 'Congo Basin', lng: 24.0, lat: 0.0 },
        { name: 'Borneo', lng: 114.0, lat: 1.0 }
    ];

    onMount(() => {
        initializeMap();
        return () => {
            if (map) map.remove();
        };
    });

    function initializeMap() {
        map = new maplibregl.Map({
            container: mapContainer,
            style: 'https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json',
            center: [centerLng, centerLat],
            zoom: 2
        });

        map.on('load', () => {
            // Add viewport box source
            map.addSource('viewport-box', {
                type: 'geojson',
                data: createBoxGeoJSON(centerLng, centerLat, VIEWPORT_SIZE_KM)
            });

            // Add box outline
            map.addLayer({
                id: 'viewport-outline',
                type: 'line',
                source: 'viewport-box',
                paint: {
                    'line-color': '#FFD700',
                    'line-width': 3,
                    'line-opacity': 0.8
                }
            });

            // Add box fill
            map.addLayer({
                id: 'viewport-fill',
                type: 'fill',
                source: 'viewport-box',
                paint: {
                    'fill-color': '#FFD700',
                    'fill-opacity': 0.1
                }
            });
        });

        // Click handler
        map.on('click', (e) => {
            updateViewport(e.lngLat.lng, e.lngLat.lat);
        });
    }

    function updateViewport(lng: number, lat: number) {
        centerLng = lng;
        centerLat = lat;

        if (map && map.getSource('viewport-box')) {
            (map.getSource('viewport-box') as maplibregl.GeoJSONSource).setData(
                createBoxGeoJSON(lng, lat, VIEWPORT_SIZE_KM)
            );
        }
    }

    function selectPreset(preset: typeof presets[0]) {
        updateViewport(preset.lng, preset.lat);
        map.flyTo({ center: [preset.lng, preset.lat], zoom: 10 });
    }

    async function handleSearch() {
        if (!searchQuery.trim()) return;

        try {
            const response = await fetch(
                `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(searchQuery)}`
            );
            const results = await response.json();

            if (results.length > 0) {
                const { lat, lon } = results[0];
                const latitude = parseFloat(lat);
                const longitude = parseFloat(lon);

                updateViewport(longitude, latitude);
                map.flyTo({ center: [longitude, latitude], zoom: 10 });
            }
        } catch (error) {
            console.error('Search error:', error);
        }
    }

    async function handleProcessViewport() {
        const bounds = calculateBounds(centerLng, centerLat, VIEWPORT_SIZE_KM);

        processingState = 'requesting';
        taskId = null;
        errorMessage = '';

        try {
            console.log('Checking for existing viewport...');

            // Check if this viewport already exists
            const findResponse = await fetch(
                `${API_BASE_URL}/api/viewports/find-by-bounds?minLon=${bounds.minLon}&minLat=${bounds.minLat}&maxLon=${bounds.maxLon}&maxLat=${bounds.maxLat}`
            );

            if (findResponse.ok) {
                const findData = await findResponse.json();

                if (findData.found) {
                    console.log(`✅ Found existing viewport: ${findData.viewport_id}`);

                    // Load existing viewport directly
                    const config: ViewportConfig = {
                        center: [centerLng, centerLat],
                        bounds,
                        sizeKm: VIEWPORT_SIZE_KM,
                        viewportId: findData.viewport_id
                    };

                    processingState = 'idle';
                    dispatch('load', config);
                    return;
                }
            }

            console.log('No existing viewport found, starting new processing...');

            // Start processing task
            const response = await fetch(`${API_BASE_URL}/api/viewports/process`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    bounds: {
                        minLon: bounds.minLon,
                        minLat: bounds.minLat,
                        maxLon: bounds.maxLon,
                        maxLat: bounds.maxLat
                    },
                    center: [centerLng, centerLat],
                    sizeKm: VIEWPORT_SIZE_KM,
                    years: [2024]
                })
            });

            if (!response.ok) {
                throw new Error(`Server error: ${response.statusText}`);
            }

            const data = await response.json();
            taskId = data.task_id;

            console.log(`Task started with ID: ${taskId}`);

            // Poll for status
            await pollTaskStatus(taskId, bounds);
        } catch (e: any) {
            processingState = 'error';
            errorMessage = e.message || 'Unknown error during processing';
            console.error('Processing error:', e);
        }
    }

    async function pollTaskStatus(currentTaskId: string, bounds: Bounds) {
        const pollInterval = 1000; // 1 second

        const poll = async () => {
            try {
                const response = await fetch(`${API_BASE_URL}/api/viewports/${currentTaskId}/status`);

                if (!response.ok) {
                    throw new Error(`Failed to get status: ${response.statusText}`);
                }

                const status = await response.json();

                processingState = status.state;
                processingProgress = status.progress;

                console.log(`Task status: ${status.state} (${status.progress}%)`);

                if (status.state === 'complete') {
                    // Load explorer with processed data
                    const config: ViewportConfig = {
                        center: [centerLng, centerLat],
                        bounds,
                        sizeKm: VIEWPORT_SIZE_KM,
                        viewportId: status.viewport_id
                    };

                    dispatch('load', config);
                } else if (status.state === 'error') {
                    errorMessage = status.error || 'Processing failed';
                    processingState = 'error';
                } else {
                    // Continue polling
                    setTimeout(poll, pollInterval);
                }
            } catch (e: any) {
                console.error('Poll error:', e);
                errorMessage = e.message;
                processingState = 'error';
            }
        };

        await poll();
    }

    function handleLoadExplorer() {
        handleProcessViewport();
    }

    function handleReset() {
        updateViewport(0.1218, 52.2053); // Reset to Cambridge
        map.flyTo({ center: [0.1218, 52.2053], zoom: 2 });
    }

    function handleZoomIn() {
        const currentZoom = map.getZoom();
        map.flyTo({ zoom: Math.min(currentZoom + 1, 20) });
    }

    function handleZoomOut() {
        const currentZoom = map.getZoom();
        map.flyTo({ zoom: Math.max(currentZoom - 1, 1) });
    }
</script>

<div class="viewport-selector">
    <header>
        <h1>TESSERA Embedding Explorer</h1>
        <h2>Select 20km × 20km Viewport</h2>
    </header>

    <div class="controls">
        <div class="search-bar">
            <input
                type="text"
                placeholder="Search location..."
                bind:value={searchQuery}
                on:keydown={(e) => e.key === 'Enter' && handleSearch()}
            />
            <button on:click={handleSearch}>Search</button>
        </div>

        <div class="presets">
            <span>Quick locations:</span>
            {#each presets as preset}
                <button class="preset-btn" on:click={() => selectPreset(preset)}>
                    {preset.name}
                </button>
            {/each}
        </div>
    </div>

    <div class="map-wrapper">
        <div class="map-container" bind:this={mapContainer}></div>

        <div class="zoom-controls">
            <button class="zoom-btn zoom-in" on:click={handleZoomIn} title="Zoom In (+)">
                <span>+</span>
            </button>
            <button class="zoom-btn zoom-out" on:click={handleZoomOut} title="Zoom Out (−)">
                <span>−</span>
            </button>
        </div>
    </div>

    <div class="info-panel">
        <div class="viewport-info">
            <h3>Selected Viewport:</h3>
            <p>Center: {centerLat.toFixed(4)}°N, {centerLng.toFixed(4)}°E</p>
            <p>Size: {VIEWPORT_SIZE_KM}km × {VIEWPORT_SIZE_KM}km</p>
        </div>

        <div class="actions">
            <button class="btn-primary" on:click={handleLoadExplorer}>
                Load Explorer
            </button>
            <button class="btn-secondary" on:click={handleReset}>
                Reset
            </button>
        </div>
    </div>

    {#if processingState !== 'idle'}
        <div class="processing-overlay">
            <div class="processing-card">
                {#if processingState === 'error'}
                    <div class="error-content">
                        <h3>❌ Error</h3>
                        <p>{errorMessage}</p>
                        <button class="btn-retry" on:click={() => processingState = 'idle'}>
                            Try Again
                        </button>
                    </div>
                {:else}
                    <div class="loading-content">
                        <div class="spinner"></div>
                        <h3>Processing Viewport</h3>

                        {#if processingState === 'requesting'}
                            <p>Preparing request...</p>
                        {:else if processingState === 'downloading'}
                            <p>📥 Downloading TESSERA embeddings...</p>
                        {:else if processingState === 'creating_pyramids'}
                            <p>🎨 Creating multi-resolution pyramids...</p>
                        {:else if processingState === 'complete'}
                            <p>✅ Complete! Loading explorer...</p>
                        {/if}

                        <div class="progress-bar">
                            <div class="progress-fill" style="width: {processingProgress}%"></div>
                        </div>
                        <p class="progress-text">{processingProgress.toFixed(0)}%</p>
                    </div>
                {/if}
            </div>
        </div>
    {/if}
</div>

<style>
    .viewport-selector {
        width: 100vw;
        height: 100vh;
        display: flex;
        flex-direction: column;
        background: #f5f5f5;
    }

    header {
        background: #2c3e50;
        color: white;
        padding: 20px;
        text-align: center;
    }

    h1 {
        margin: 0;
        font-size: 28px;
        font-weight: 600;
    }

    h2 {
        margin: 8px 0 0 0;
        font-size: 16px;
        font-weight: 400;
        opacity: 0.9;
    }

    .controls {
        padding: 15px 20px;
        background: white;
        border-bottom: 1px solid #ddd;
    }

    .search-bar {
        display: flex;
        gap: 10px;
        margin-bottom: 15px;
    }

    .search-bar input {
        flex: 1;
        padding: 10px 15px;
        font-size: 14px;
        border: 2px solid #ddd;
        border-radius: 4px;
    }

    .search-bar button {
        padding: 10px 20px;
        background: #4CAF50;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 14px;
        font-weight: 600;
    }

    .search-bar button:hover {
        background: #45a049;
    }

    .presets {
        display: flex;
        gap: 10px;
        align-items: center;
        flex-wrap: wrap;
    }

    .presets span {
        font-size: 14px;
        color: #666;
        font-weight: 600;
    }

    .preset-btn {
        padding: 6px 12px;
        background: #e8f5e9;
        color: #2e7d32;
        border: 1px solid #4CAF50;
        border-radius: 4px;
        cursor: pointer;
        font-size: 13px;
    }

    .preset-btn:hover {
        background: #c8e6c9;
    }

    .map-wrapper {
        flex: 1;
        position: relative;
        overflow: hidden;
    }

    .map-container {
        width: 100%;
        height: 100%;
    }

    .info-panel {
        padding: 20px;
        background: white;
        border-top: 2px solid #ddd;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }

    .viewport-info h3 {
        margin: 0 0 8px 0;
        font-size: 16px;
        color: #333;
    }

    .viewport-info p {
        margin: 4px 0;
        font-size: 14px;
        color: #666;
    }

    .actions {
        display: flex;
        gap: 15px;
    }

    .btn-primary {
        padding: 12px 30px;
        background: #4CAF50;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 16px;
        font-weight: 600;
    }

    .btn-primary:hover {
        background: #45a049;
    }

    .btn-secondary {
        padding: 12px 30px;
        background: #fff;
        color: #333;
        border: 2px solid #ddd;
        border-radius: 4px;
        cursor: pointer;
        font-size: 16px;
        font-weight: 600;
    }

    .btn-secondary:hover {
        border-color: #999;
    }

    .zoom-controls {
        position: absolute;
        right: 20px;
        top: 50%;
        transform: translateY(-50%);
        display: flex;
        flex-direction: column;
        gap: 10px;
        z-index: 100;
    }

    .zoom-btn {
        width: 40px;
        height: 40px;
        background: white;
        border: 2px solid #ddd;
        border-radius: 4px;
        cursor: pointer;
        font-size: 20px;
        font-weight: 600;
        color: #333;
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
        transition: all 0.2s ease;
    }

    .zoom-btn:hover {
        background: #f5f5f5;
        border-color: #999;
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
    }

    .zoom-btn:active {
        transform: scale(0.95);
    }

    .zoom-btn span {
        line-height: 1;
    }

    .processing-overlay {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.7);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 1000;
    }

    .processing-card {
        background: white;
        border-radius: 8px;
        padding: 40px;
        text-align: center;
        min-width: 400px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
    }

    .loading-content,
    .error-content {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 20px;
    }

    .spinner {
        width: 50px;
        height: 50px;
        border: 4px solid #f3f3f3;
        border-top: 4px solid #4CAF50;
        border-radius: 50%;
        animation: spin 1s linear infinite;
    }

    @keyframes spin {
        0% {
            transform: rotate(0deg);
        }
        100% {
            transform: rotate(360deg);
        }
    }

    .processing-card h3 {
        margin: 0;
        font-size: 20px;
        color: #333;
    }

    .processing-card p {
        margin: 0;
        color: #666;
        font-size: 14px;
    }

    .progress-bar {
        width: 100%;
        height: 8px;
        background: #e0e0e0;
        border-radius: 4px;
        overflow: hidden;
    }

    .progress-fill {
        height: 100%;
        background: #4CAF50;
        transition: width 0.3s ease;
    }

    .progress-text {
        font-weight: 600;
        color: #4CAF50;
        font-size: 14px;
    }

    .error-content h3 {
        color: #d32f2f;
    }

    .error-content p {
        color: #666;
        margin: 10px 0;
    }

    .btn-retry {
        padding: 10px 20px;
        background: #4CAF50;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 14px;
        font-weight: 600;
    }

    .btn-retry:hover {
        background: #45a049;
    }
</style>
