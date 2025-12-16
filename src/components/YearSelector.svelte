<script lang="ts">
    import { createEventDispatcher } from 'svelte';

    export let years: number[];
    export let selected: number;

    const dispatch = createEventDispatcher();

    function handleChange(event: Event) {
        const target = event.target as HTMLSelectElement;
        selected = parseInt(target.value);
        dispatch('change', selected);
    }
</script>

<div class="year-selector">
    <label for="year">Year:</label>
    <select id="year" bind:value={selected} on:change={handleChange}>
        {#each years as year}
            <option value={year}>{year}</option>
        {/each}
    </select>
</div>

<style>
    .year-selector {
        margin: 15px 0;
    }

    label {
        display: block;
        margin-bottom: 8px;
        font-size: 14px;
        font-weight: 600;
        color: #333;
    }

    select {
        width: 100%;
        padding: 8px 12px;
        font-size: 14px;
        border: 2px solid #ddd;
        border-radius: 4px;
        background: white;
        cursor: pointer;
        transition: border-color 0.2s;
    }

    select:hover {
        border-color: #4CAF50;
    }

    select:focus {
        outline: none;
        border-color: #4CAF50;
        box-shadow: 0 0 0 3px rgba(76, 175, 80, 0.1);
    }
</style>
