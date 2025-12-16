<script lang="ts">
    import { onMount } from 'svelte';
    import { WebGPUContext } from '../lib/gpu/WebGPUContext';
    import { SimilarityCompute } from '../lib/gpu/SimilarityCompute';
    import { CPUSimilarityCompute } from '../lib/gpu/CPUSimilarityCompute';
    import { EmbeddingLoader } from '../lib/data/EmbeddingLoader';
    import ThresholdControl from './ThresholdControl.svelte';
    import YearSelector from './YearSelector.svelte';
    import StatsPanel from './StatsPanel.svelte';
    import type { ViewportConfig } from '../lib/data/DataTypes';
    import { geoToPixel } from '../lib/utils/coordinates';

    export let config: ViewportConfig;

    // Use config to initialize viewport
    $: viewportCenter = config?.center || [0, 0];
    $: viewportBounds = config?.bounds;

    let gpuContext: WebGPUContext | null = null;
    let similarityCompute: SimilarityCompute | CPUSimilarityCompute;
    let embeddingLoader: EmbeddingLoader;
    let usingCPUFallback = false;

    let selectedYear = 2024;
    let threshold = 0.8;
    let selectedPixel: [number, number] | null = null;
    let similarityResults: Float32Array | null = null;

    let loading = true;
    let error = '';
    let loadingMessage = 'Initializing...';

    onMount(async () => {
        try {
            // Try WebGPU first
            loadingMessage = 'Initializing WebGPU...';
            gpuContext = new WebGPUContext();
            const gpuReady = await gpuContext.initialize();

            if (!gpuReady) {
                // Fall back to CPU computation
                console.log('WebGPU not available, using CPU fallback');
                loadingMessage = 'Using CPU-based computation...';
                usingCPUFallback = true;
            }

            // Initialize loaders
            loadingMessage = 'Loading embeddings...';
            embeddingLoader = new EmbeddingLoader();

            // Load initial year
            await loadYear(selectedYear);

            loadingMessage = 'Ready!';
            loading = false;

            // Log compute backend info
            if (usingCPUFallback) {
                console.log('✅ Using CPU-based similarity compute');
            } else {
                console.log('✅ Using WebGPU-accelerated similarity compute');
            }
        } catch (e: any) {
            console.error('❌ Initialization error:', e);
            error = e.message || 'Unknown error during initialization';
            loading = false;
        }
    });

    async function loadYear(year: number) {
        try {
            loadingMessage = `Loading embeddings for ${year}...`;
            const embeddings = await embeddingLoader.load(year, '/data/embeddings');

            // Initialize similarity compute if needed
            if (!similarityCompute) {
                const header = embeddingLoader.getHeader(year)!;

                if (usingCPUFallback) {
                    // Use CPU-based computation
                    similarityCompute = new CPUSimilarityCompute(
                        header.width,
                        header.height,
                        header.dimensions
                    );
                } else {
                    // Use GPU computation
                    similarityCompute = new SimilarityCompute(
                        gpuContext!,
                        header.width,
                        header.height,
                        header.dimensions
                    );
                }

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
</script>

<div class="explorer-container">
    {#if loading}
        <div class="loading">
            <div class="spinner"></div>
            <p>{loadingMessage}</p>
        </div>
    {:else if error}
        <div class="error">
            <h2>⚠️ WebGPU Not Available</h2>
            <p>{error}</p>
            <h3>How to Fix:</h3>
            <div class="fix-instructions">
                <div class="instruction">
                    <strong>Safari 18.3+:</strong>
                    <ol>
                        <li>Click "Develop" menu (enable if needed in Preferences > Advanced)</li>
                        <li>Look for "Experimental Features" or "WebGPU"</li>
                        <li>Enable the WebGPU option</li>
                        <li>Reload this page</li>
                    </ol>
                </div>
                <div class="instruction">
                    <strong>Chrome/Edge:</strong>
                    <ol>
                        <li>Update to version 113 or later</li>
                        <li>WebGPU should be enabled by default</li>
                    </ol>
                </div>
                <div class="instruction">
                    <strong>Firefox:</strong>
                    <ol>
                        <li>Type about:config in address bar</li>
                        <li>Search for "webgpu.enabled"</li>
                        <li>Set to true</li>
                    </ol>
                </div>
            </div>
            <p style="margin-top: 20px; color: #999;">Check browser console for more details.</p>
        </div>
    {:else}
        <div class="controls-panel">
            <h3>Controls</h3>

            <YearSelector
                years={[2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024]}
                selected={selectedYear}
                on:change={handleYearChange}
            />

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
                        Click the button below to select a test pixel (1000, 1000) and compute similarities using {usingCPUFallback ? 'CPU' : 'WebGPU'}
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

                {#if usingCPUFallback}
                    <p style="margin-top: 20px; color: #ff9800; font-size: 13px;">
                        ⚠️ Running in CPU mode (embeddings: {embeddingLoader ? '✓ loaded' : 'loading...'})
                    </p>
                {/if}
            </div>
        </div>

        <div class="instructions">
            <p>Click on any pixel to find similar locations • Adjust threshold to control sensitivity</p>
            {#if usingCPUFallback}
                <p class="cpu-fallback-badge">
                    ⚠️ Using CPU computation (WebGPU unavailable)
                </p>
            {/if}
        </div>
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

    .cpu-fallback-badge {
        margin-top: 8px;
        padding-top: 8px;
        border-top: 1px solid rgba(255,255,255,0.3);
        color: #ffb74d;
        font-size: 12px;
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

    .error h3 {
        margin-top: 30px;
        margin-bottom: 15px;
        color: #333;
        font-size: 16px;
    }

    .fix-instructions {
        display: flex;
        flex-direction: column;
        gap: 20px;
        margin: 20px 0;
        max-width: 700px;
        text-align: left;
    }

    .instruction {
        background: #f5f5f5;
        padding: 15px;
        border-radius: 4px;
        border-left: 4px solid #4CAF50;
    }

    .instruction strong {
        color: #333;
        display: block;
        margin-bottom: 8px;
    }

    .instruction ol {
        margin: 0;
        padding-left: 20px;
        color: #666;
    }

    .instruction li {
        margin: 5px 0;
        font-size: 14px;
    }
</style>
