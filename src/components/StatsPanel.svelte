<script lang="ts">
    export let pixel: [number, number];
    export let similarities: Float32Array | null;
    export let threshold: number;

    $: stats = computeStats(similarities, threshold);

    function computeStats(sims: Float32Array | null, thresh: number) {
        if (!sims) return null;

        let count = 0;
        let sum = 0;
        let max = -Infinity;

        for (let i = 0; i < sims.length; i += 4) {
            const sim = sims[i]; // Assuming RGBA, similarity in R channel
            if (sim >= thresh) {
                count++;
                sum += sim;
                max = Math.max(max, sim);
            }
        }

        return {
            count,
            percentage: (count / (sims.length / 4) * 100).toFixed(2),
            avgSimilarity: count > 0 ? (sum / count).toFixed(3) : '0',
            maxSimilarity: max.toFixed(3)
        };
    }
</script>

{#if stats}
    <div class="stats-panel">
        <h3>Selection Stats</h3>
        <div class="stat">
            <span class="label">Selected Pixel:</span>
            <span class="value">({pixel[0]}, {pixel[1]})</span>
        </div>
        <div class="stat">
            <span class="label">Similar Pixels:</span>
            <span class="value">{stats.count.toLocaleString()}</span>
        </div>
        <div class="stat">
            <span class="label">Coverage:</span>
            <span class="value">{stats.percentage}%</span>
        </div>
        <div class="stat">
            <span class="label">Avg Similarity:</span>
            <span class="value">{stats.avgSimilarity}</span>
        </div>
        <div class="stat">
            <span class="label">Max Similarity:</span>
            <span class="value">{stats.maxSimilarity}</span>
        </div>
    </div>
{/if}

<style>
    .stats-panel {
        margin-top: 20px;
        padding-top: 20px;
        border-top: 2px solid #eee;
    }

    h3 {
        margin: 0 0 12px 0;
        font-size: 16px;
        color: #333;
    }

    .stat {
        display: flex;
        justify-content: space-between;
        margin: 8px 0;
        font-size: 13px;
    }

    .label {
        color: #666;
    }

    .value {
        font-weight: 600;
        color: #333;
    }
</style>
