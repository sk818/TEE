<script lang="ts">
    import { createEventDispatcher } from 'svelte';

    export let value: number = 0.8;

    const dispatch = createEventDispatcher();

    function handleChange(event: Event) {
        const target = event.target as HTMLInputElement;
        value = parseFloat(target.value);
        dispatch('change', value);
    }
</script>

<div class="threshold-control">
    <label for="threshold">
        Similarity Threshold: <strong>{value.toFixed(2)}</strong>
    </label>
    <input
        type="range"
        id="threshold"
        min="0"
        max="1"
        step="0.01"
        bind:value
        on:input={handleChange}
    />
    <div class="scale">
        <span>0.0</span>
        <span>0.5</span>
        <span>1.0</span>
    </div>
</div>

<style>
    .threshold-control {
        margin: 15px 0;
    }

    label {
        display: block;
        margin-bottom: 8px;
        font-size: 14px;
        color: #333;
    }

    input[type="range"] {
        width: 100%;
        height: 6px;
        background: linear-gradient(to right, #ddd 0%, #4CAF50 100%);
        border-radius: 3px;
        outline: none;
        -webkit-appearance: none;
    }

    input[type="range"]::-webkit-slider-thumb {
        -webkit-appearance: none;
        appearance: none;
        width: 18px;
        height: 18px;
        background: #4CAF50;
        cursor: pointer;
        border-radius: 50%;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }

    input[type="range"]::-moz-range-thumb {
        width: 18px;
        height: 18px;
        background: #4CAF50;
        cursor: pointer;
        border-radius: 50%;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        border: none;
    }

    .scale {
        display: flex;
        justify-content: space-between;
        font-size: 12px;
        color: #666;
        margin-top: 4px;
    }
</style>
