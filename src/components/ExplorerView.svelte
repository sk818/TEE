<script lang="ts">
    import { onMount } from 'svelte';
    import { WebGPUContext } from '../lib/gpu/WebGPUContext';
    import { SimilarityCompute } from '../lib/gpu/SimilarityCompute';
    import { EmbeddingLoader } from '../lib/data/EmbeddingLoader';
    import ThresholdControl from './ThresholdControl.svelte';
    import YearSelector from './YearSelector.svelte';
    import StatsPanel from './StatsPanel.svelte';
    import type { ViewportConfig } from '../lib/data/DataTypes';
    import { geoToPixel } from '../lib/utils/coordinates';

    export let config: ViewportConfig;

    let gpuContext: WebGPUContext;
    let similarityCompute: SimilarityCompute;
    let embeddingLoader: EmbeddingLoader;

    let selectedYear = 2024;
    let threshold = 0.8;
    let selectedPixel: [number, number] | null = null;
    let similarityResults: Float32Array | null = null;

    let loading = true;
    let error = '';
    let loadingMessage = 'Initializing WebGPU...';

    onMount(async () => {
        try {
            // Initialize WebGPU
            loadingMessage = 'Initializing WebGPU...';
            gpuContext = new WebGPUContext();
            const gpuReady = await gpuContext.initialize();

            if (!gpuReady) {
                throw new Error('WebGPU not available');
            }

            // Initialize loaders
            loadingMessage = 'Loading embeddings...';
            embeddingLoader = new EmbeddingLoader();

            // Load initial year
            await loadYear(selectedYear);

            loadingMessage = 'Ready!';
            loading = false;
        } catch (e: any) {
            error = e.message;
            loading = false;
        }
    });

    async function loadYear(year: number) {
        const embeddings = await embeddingLoader.load(year, '/data/embeddings');

        // Initialize similarity compute if needed
        if (!similarityCompute) {
            const header = embeddingLoader.getHeader(year)!;
            similarityCompute = new SimilarityCompute(
                gpuContext,
                header.width,
                header.height,
                header.dimensions
            );
            await similarityCompute.initialize(embeddings);
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
            <h2>Error</h2>
            <p>{error}</p>
            <p>Please ensure your browser supports WebGPU (Chrome 113+, Edge 113+, or Safari 17.4+)</p>
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
                <p>Map visualization will be rendered here using Deck.gl</p>
                <p>Click anywhere to select a pixel and compute similarity</p>

                {#if selectedPixel}
                    <p class="selected">Selected: ({selectedPixel[0]}, {selectedPixel[1]})</p>
                {/if}

                <button
                    class="demo-click"
                    on:click={() => handlePixelClick(1000, 1000)}
                >
                    Demo Click (1000, 1000)
                </button>
            </div>
        </div>

        <div class="instructions">
            <p>Click on any pixel to find similar locations • Adjust threshold to control sensitivity</p>
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
</style>
