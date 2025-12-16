<script lang="ts">
    import { onMount, createEventDispatcher } from 'svelte';
    import maplibregl from 'maplibre-gl';
    import 'maplibre-gl/dist/maplibre-gl.css';
    import { VIEWPORT_SIZE_KM, calculateBounds, createBoxGeoJSON } from '../lib/utils/coordinates';
    import type { ViewportConfig } from '../lib/data/DataTypes';

    const dispatch = createEventDispatcher();

    let mapContainer: HTMLDivElement;
    let map: maplibregl.Map;
    let searchQuery = '';

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
            style: 'https://demotiles.maplibre.org/style.json',
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

    function handleLoadExplorer() {
        const bounds = calculateBounds(centerLng, centerLat, VIEWPORT_SIZE_KM);
        const config: ViewportConfig = {
            center: [centerLng, centerLat],
            bounds,
            sizeKm: VIEWPORT_SIZE_KM
        };

        dispatch('load', config);
    }

    function handleReset() {
        updateViewport(0.1218, 52.2053); // Reset to Cambridge
        map.flyTo({ center: [0.1218, 52.2053], zoom: 2 });
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
</style>
