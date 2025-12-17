<script lang="ts">
    import { onMount, createEventDispatcher } from 'svelte';
    import { CPUSimilarityCompute } from '../lib/gpu/CPUSimilarityCompute';
    import { GeoTIFFLoader } from '../lib/data/GeoTIFFLoader';
    import { EmbeddingLoader } from '../lib/data/EmbeddingLoader';
    import ThresholdControl from './ThresholdControl.svelte';
    import YearSelector from './YearSelector.svelte';
    import StatsPanel from './StatsPanel.svelte';
    import type { ViewportConfig } from '../lib/data/DataTypes';
    import { geoToPixel } from '../lib/utils/coordinates';

    export let config: ViewportConfig;

    const dispatch = createEventDispatcher();

    // Use config to initialize viewport
    $: viewportCenter = config?.center || [0, 0];
    $: viewportBounds = config?.bounds;
    $: viewportId = config?.viewportId || null;

    let similarityCompute: CPUSimilarityCompute;
    let embeddingLoader: EmbeddingLoader | null = null;
    let geotiffLoader: GeoTIFFLoader | null = null;
    let usingGeoTIFF = false;

    let selectedYear = 2024;
    let threshold = 0.8;
    let selectedPixel: [number, number] | null = null;
    let similarityResults: Float32Array | null = null;

    // Additional years management
    const allYears = [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024];
    let availableYears = [2024]; // Years downloaded so far
    let showAdditionalYearsDialog = false;
    let selectedAdditionalYears = new Set<number>();
    let downloadingAdditionalYears = false;
    let additionalYearsError = '';
    const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

    let loading = true;
    let error = '';
    let loadingMessage = 'Initializing...';

    onMount(async () => {
        try {
            // Initialize loaders based on whether we have a viewport ID
            if (viewportId) {
                loadingMessage = 'Loading GeoTIFF pyramid data...';
                geotiffLoader = new GeoTIFFLoader();
                usingGeoTIFF = true;
                console.log(`✅ Using GeoTIFF loader for viewport ${viewportId}`);

                // Load metadata to get available years
                try {
                    const metadata = await geotiffLoader.loadViewportMetadata(viewportId);
                    if (metadata.years && Array.isArray(metadata.years)) {
                        availableYears = metadata.years.sort((a: number, b: number) => a - b);
                        selectedYear = availableYears[availableYears.length - 1]; // Use latest year
                        console.log(`✓ Loaded available years from metadata: ${availableYears.join(', ')}`);
                    }
                } catch (metadata_error) {
                    console.warn('Could not load metadata for years:', metadata_error);
                }
            } else {
                loadingMessage = 'Loading embeddings...';
                embeddingLoader = new EmbeddingLoader();
                usingGeoTIFF = false;
                console.log('✅ Using binary embedding loader (legacy)');
            }

            // Load initial year
            await loadYear(selectedYear);

            loadingMessage = 'Ready!';
            loading = false;

            // Log compute backend info
            console.log('✅ Using CPU-based similarity compute');
        } catch (e: any) {
            console.error('❌ Initialization error:', e);
            error = e.message || 'Unknown error during initialization';
            loading = false;
        }
    });

    async function loadYear(year: number) {
        try {
            loadingMessage = `Loading embeddings for ${year}...`;

            let embeddings: Float32Array;

            if (usingGeoTIFF && geotiffLoader && viewportId) {
                // Load full embeddings from NPY file for similarity computation
                try {
                    loadingMessage = `Loading full embeddings for ${year}...`;
                    embeddings = await geotiffLoader.loadFullEmbeddings(viewportId, year);
                    console.log(`✓ Loaded full embeddings for similarity: ${embeddings.length} values`);
                } catch (npy_error) {
                    console.warn('Could not load NPY embeddings, falling back to GeoTIFF:', npy_error);
                    // Fallback to GeoTIFF (RGB only, less accurate)
                    embeddings = await geotiffLoader.loadPyramidLevel(viewportId, year, 0);
                }
            } else if (embeddingLoader) {
                // Load from binary format (legacy)
                embeddings = await embeddingLoader.load(year, '/data/embeddings');
            } else {
                throw new Error('No embedding loader available');
            }

            // Initialize similarity compute if needed
            if (!similarityCompute) {
                let width: number;
                let height: number;
                let dimensions: number;

                if (usingGeoTIFF && geotiffLoader && viewportId) {
                    // Get metadata from GeoTIFF
                    const metadata = await geotiffLoader.loadViewportMetadata(viewportId);

                    // Extract dimensions from metadata
                    width = metadata.width || 4408;
                    height = metadata.height || 4408;

                    // Calculate actual embedding dimensions from array size
                    // embeddings.length should be width * height * dimensions
                    const numPixels = width * height;
                    dimensions = Math.round(embeddings.length / numPixels);

                    if (dimensions === 0 || embeddings.length !== numPixels * dimensions) {
                        console.warn(`Dimension mismatch: embeddings.length=${embeddings.length}, expected=${numPixels * dimensions}`);
                        dimensions = Math.max(1, dimensions);
                    }

                    console.log(`✓ Loaded dimensions from metadata: ${width}×${height} with ${dimensions} embedding dimensions`);
                } else if (embeddingLoader) {
                    const header = embeddingLoader.getHeader(year)!;
                    width = header.width;
                    height = header.height;
                    dimensions = header.dimensions;
                } else {
                    throw new Error('Cannot determine embedding dimensions');
                }

                // Use CPU-based computation
                console.log(`✓ Initializing CPU compute with dimensions: ${width}×${height}, ${dimensions}D embeddings`);
                similarityCompute = new CPUSimilarityCompute(width, height, dimensions);
                await similarityCompute.initialize(embeddings);
            }
        } catch (e: any) {
            console.error('Error loading year:', year, e);
            throw new Error(`Failed to load embeddings for year ${year}: ${e.message || e}`);
        }
    }

    async function handlePixelClick(x: number, y: number) {
        selectedPixel = [x, y];
        await computeSimilarity(x, y);
    }

    async function computeSimilarity(x: number, y: number) {
        if (!similarityCompute) return;

        similarityResults = await similarityCompute.compute({
            queryX: x,
            queryY: y,
            threshold,
            colormapId: 1 // Viridis
        });
    }

    async function handleYearChange(event: CustomEvent<number>) {
        selectedYear = event.detail;
        await loadYear(selectedYear);

        // Recompute similarity if pixel selected
        if (selectedPixel) {
            await computeSimilarity(selectedPixel[0], selectedPixel[1]);
        }
    }

    async function handleThresholdChange(event: CustomEvent<number>) {
        threshold = event.detail;

        // Recompute with new threshold
        if (selectedPixel) {
            await computeSimilarity(selectedPixel[0], selectedPixel[1]);
        }
    }

    function toggleYear(year: number) {
        if (selectedAdditionalYears.has(year)) {
            selectedAdditionalYears.delete(year);
        } else {
            selectedAdditionalYears.add(year);
        }
        selectedAdditionalYears = selectedAdditionalYears; // Trigger reactivity
    }

    async function downloadAdditionalYears() {
        if (selectedAdditionalYears.size === 0) return;

        downloadingAdditionalYears = true;
        additionalYearsError = '';

        try {
            const yearsToDownload = Array.from(selectedAdditionalYears).sort();

            const response = await fetch(`${API_BASE_URL}/api/viewports/${viewportId}/download-years`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    years: yearsToDownload
                })
            });

            if (!response.ok) {
                throw new Error(`Server error: ${response.statusText}`);
            }

            const data = await response.json();
            const taskId = data.task_id;

            console.log(`Additional years download started with task ID: ${taskId}`);

            // Poll for completion
            await pollAdditionalYearsProgress(taskId, yearsToDownload);

        } catch (e: any) {
            console.error('Error downloading additional years:', e);
            additionalYearsError = e.message || 'Unknown error during download';
            downloadingAdditionalYears = false;
        }
    }

    async function pollAdditionalYearsProgress(taskId: string, yearsToDownload: number[]) {
        const pollInterval = 1000;

        const poll = async () => {
            try {
                const response = await fetch(`${API_BASE_URL}/api/viewports/${viewportId}/download-years/${taskId}/status`);

                if (!response.ok) {
                    throw new Error(`Failed to get status: ${response.statusText}`);
                }

                const status = await response.json();

                if (status.state === 'complete') {
                    // Update available years
                    availableYears = [...new Set([...availableYears, ...yearsToDownload])].sort((a, b) => a - b);

                    // Clear selections
                    selectedAdditionalYears.clear();
                    showAdditionalYearsDialog = false;
                    downloadingAdditionalYears = false;

                    console.log(`✅ Downloaded years: ${yearsToDownload.join(', ')}`);
                } else if (status.state === 'error') {
                    additionalYearsError = status.error || 'Download failed';
                    downloadingAdditionalYears = false;
                } else {
                    // Continue polling
                    setTimeout(poll, pollInterval);
                }
            } catch (e: any) {
                console.error('Poll error:', e);
                additionalYearsError = e.message;
                downloadingAdditionalYears = false;
            }
        };

        await poll();
    }
</script>

<div class="explorer-container">
    {#if loading}
        <div class="loading">
            <div class="spinner"></div>
            <p>{loadingMessage}</p>
        </div>
    {:else if error}
        <div class="error">
            <h2>⚠️ Error</h2>
            <p>{error}</p>
            <p style="margin-top: 20px; color: #999;">Check browser console for more details.</p>
        </div>
    {:else}
        <div class="controls-panel">
            <h3>Controls</h3>

            <YearSelector
                years={availableYears}
                selected={selectedYear}
                on:change={handleYearChange}
            />

            {#if viewportId && availableYears.length < allYears.length}
                <button class="btn-download-years" on:click={() => showAdditionalYearsDialog = true}>
                    ⬇️ Download More Years
                </button>
            {/if}

            {#if viewportId}
                <button class="btn-three-pane" on:click={() => dispatch('open-three-pane', viewportId)}>
                    🗺️ Open Three-Pane Viewer
                </button>
            {/if}

            <ThresholdControl
                value={threshold}
                on:change={handleThresholdChange}
            />

            {#if selectedPixel}
                <StatsPanel
                    pixel={selectedPixel}
                    similarities={similarityResults}
                    threshold={threshold}
                />
            {/if}
        </div>

        <div class="map-view">
            <div class="placeholder-map">
                <h3>Embedding Visualization</h3>
                <p style="color: #999; font-size: 14px;">Map rendering (Deck.gl) coming soon</p>

                <div style="margin: 20px 0; padding: 15px; background: #f0f0f0; border-radius: 4px;">
                    <p style="margin: 0 0 10px 0; font-weight: 600;">Test Similarity Computation:</p>
                    <p style="margin: 5px 0; color: #666; font-size: 14px;">
                        Click the button below to select a test pixel and compute similarities using CPU.
                    </p>
                </div>

                {#if selectedPixel}
                    <p class="selected">✓ Selected Pixel: ({selectedPixel[0]}, {selectedPixel[1]})</p>
                    <p style="color: #666; font-size: 13px;">Similarity computed and ready for visualization</p>
                {/if}

                <button
                    class="demo-click"
                    on:click={() => handlePixelClick(100, 100)}
                >
                    🧪 Test Pixel Selection
                </button>

                <p style="margin-top: 20px; color: #4CAF50; font-size: 13px;">
                    ✅ Running in CPU mode (embeddings: {embeddingLoader ? '✓ loaded' : 'loading...'})
                </p>
            </div>
        </div>

        <div class="instructions">
            <p>Click on any pixel to find similar locations • Adjust threshold to control sensitivity</p>
        </div>

        {#if showAdditionalYearsDialog}
            <div class="modal-overlay" on:click={() => !downloadingAdditionalYears && (showAdditionalYearsDialog = false)}>
                <div class="modal-card" on:click={(e) => e.stopPropagation()}>
                    <h3>Download Additional Years</h3>

                    <div class="warning-box">
                        <p>⚠️ <strong>Warning:</strong> Downloading additional years is time-consuming. Each year typically takes 5-15+ minutes to download and process.</p>
                    </div>

                    <div class="years-list">
                        <p style="margin: 0 0 10px 0; font-weight: 600;">Select years to download:</p>
                        {#each allYears.filter(y => !availableYears.includes(y)) as year}
                            <label class="year-checkbox">
                                <input
                                    type="checkbox"
                                    disabled={downloadingAdditionalYears}
                                    checked={selectedAdditionalYears.has(year)}
                                    on:change={() => toggleYear(year)}
                                />
                                <span>{year}</span>
                            </label>
                        {/each}
                    </div>

                    {#if additionalYearsError}
                        <div class="error-message">
                            <p>{additionalYearsError}</p>
                        </div>
                    {/if}

                    <div class="modal-actions">
                        <button
                            class="btn-cancel"
                            disabled={downloadingAdditionalYears}
                            on:click={() => showAdditionalYearsDialog = false}
                        >
                            Cancel
                        </button>
                        <button
                            class="btn-download"
                            disabled={selectedAdditionalYears.size === 0 || downloadingAdditionalYears}
                            on:click={downloadAdditionalYears}
                        >
                            {downloadingAdditionalYears ? '⏳ Downloading...' : '⬇️ Download'}
                        </button>
                    </div>
                </div>
            </div>
        {/if}
    {/if}
</div>

<style>
    .explorer-container {
        width: 100vw;
        height: 100vh;
        display: flex;
        position: relative;
        background: #f5f5f5;
    }

    .controls-panel {
        width: 320px;
        background: white;
        padding: 20px;
        box-shadow: 2px 0 8px rgba(0,0,0,0.1);
        overflow-y: auto;
        z-index: 1000;
    }

    .controls-panel h3 {
        margin: 0 0 20px 0;
        font-size: 20px;
        color: #333;
    }

    .map-view {
        flex: 1;
        position: relative;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .placeholder-map {
        text-align: center;
        padding: 40px;
        background: white;
        border-radius: 8px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }

    .placeholder-map p {
        margin: 10px 0;
        color: #666;
    }

    .selected {
        margin-top: 20px;
        font-weight: 600;
        color: #4CAF50;
    }

    .demo-click {
        margin-top: 20px;
        padding: 10px 20px;
        background: #4CAF50;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 14px;
    }

    .demo-click:hover {
        background: #45a049;
    }

    .instructions {
        position: absolute;
        bottom: 20px;
        left: 50%;
        transform: translateX(-50%);
        background: rgba(0,0,0,0.7);
        color: white;
        padding: 10px 20px;
        border-radius: 4px;
        font-size: 14px;
        text-align: center;
    }

    .instructions p {
        margin: 0;
    }

    .loading, .error {
        width: 100%;
        height: 100%;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        font-size: 18px;
    }

    .loading {
        color: #333;
    }

    .spinner {
        width: 50px;
        height: 50px;
        border: 4px solid #f3f3f3;
        border-top: 4px solid #4CAF50;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        margin-bottom: 20px;
    }

    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }

    .error {
        color: #d32f2f;
        padding: 40px;
    }

    .error h2 {
        margin: 0 0 20px 0;
    }

    .error p {
        margin: 10px 0;
        max-width: 600px;
        text-align: center;
    }

    .btn-download-years {
        width: 100%;
        margin: 15px 0;
        padding: 12px 16px;
        background: #2196F3;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 14px;
        font-weight: 600;
        transition: background 0.2s ease;
    }

    .btn-download-years:hover {
        background: #1976D2;
    }

    .btn-three-pane {
        width: 100%;
        margin: 10px 0;
        padding: 12px 16px;
        background: #4CAF50;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 14px;
        font-weight: 600;
        transition: background 0.2s ease;
    }

    .btn-three-pane:hover {
        background: #45a049;
    }

    .modal-overlay {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.7);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 2000;
    }

    .modal-card {
        background: white;
        border-radius: 8px;
        padding: 30px;
        max-width: 500px;
        width: 90%;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
    }

    .modal-card h3 {
        margin: 0 0 20px 0;
        font-size: 20px;
        color: #333;
    }

    .warning-box {
        background: #fff3cd;
        border: 1px solid #ffc107;
        border-radius: 4px;
        padding: 12px 16px;
        margin-bottom: 20px;
    }

    .warning-box p {
        margin: 0;
        color: #856404;
        font-size: 14px;
    }

    .years-list {
        margin-bottom: 20px;
        max-height: 250px;
        overflow-y: auto;
    }

    .year-checkbox {
        display: flex;
        align-items: center;
        padding: 8px 0;
        cursor: pointer;
        font-size: 14px;
        user-select: none;
    }

    .year-checkbox input {
        margin-right: 10px;
        cursor: pointer;
        width: 16px;
        height: 16px;
    }

    .year-checkbox input:disabled {
        cursor: not-allowed;
        opacity: 0.5;
    }

    .year-checkbox span {
        color: #333;
    }

    .error-message {
        background: #ffebee;
        border: 1px solid #ef5350;
        border-radius: 4px;
        padding: 12px 16px;
        margin-bottom: 20px;
    }

    .error-message p {
        margin: 0;
        color: #c62828;
        font-size: 14px;
    }

    .modal-actions {
        display: flex;
        gap: 10px;
        justify-content: flex-end;
    }

    .btn-cancel {
        padding: 10px 20px;
        background: #f5f5f5;
        color: #333;
        border: 1px solid #ddd;
        border-radius: 4px;
        cursor: pointer;
        font-size: 14px;
        font-weight: 600;
        transition: background 0.2s ease;
    }

    .btn-cancel:hover:not(:disabled) {
        background: #e0e0e0;
    }

    .btn-cancel:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }

    .btn-download {
        padding: 10px 20px;
        background: #2196F3;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 14px;
        font-weight: 600;
        transition: background 0.2s ease;
    }

    .btn-download:hover:not(:disabled) {
        background: #1976D2;
    }

    .btn-download:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }

</style>
