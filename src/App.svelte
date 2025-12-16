<script lang="ts">
    import ViewportSelector from './components/ViewportSelector.svelte';
    import ExplorerView from './components/ExplorerView.svelte';
    import ThreePaneView from './components/ThreePaneView.svelte';
    import type { ViewportConfig } from './lib/data/DataTypes';

    let currentView: 'selector' | 'explorer' | 'three-pane' = 'selector';
    let viewportConfig: ViewportConfig | null = null;
    let selectedViewportId: string = '';

    function handleViewportLoad(event: CustomEvent<ViewportConfig>) {
        viewportConfig = event.detail;
        currentView = 'explorer';
    }

    function handleOpenThreePane(viewportId: string) {
        selectedViewportId = viewportId;
        currentView = 'three-pane';
    }

    function handleBackToSelector() {
        currentView = 'selector';
        viewportConfig = null;
        selectedViewportId = '';
    }

    function handleCloseThreePane() {
        handleBackToSelector();
    }
</script>

<main>
    {#if currentView === 'selector'}
        <ViewportSelector on:load={handleViewportLoad} />
    {:else if currentView === 'explorer' && viewportConfig}
        <ExplorerView config={viewportConfig} on:back={handleBackToSelector} on:open-three-pane={(e) => handleOpenThreePane(e.detail)} />
    {:else if currentView === 'three-pane' && selectedViewportId}
        <ThreePaneView viewportId={selectedViewportId} onClose={handleCloseThreePane} />
    {/if}
</main>

<style>
    :global(body) {
        margin: 0;
        padding: 0;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen,
            Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }

    :global(*) {
        box-sizing: border-box;
    }

    main {
        width: 100%;
        height: 100vh;
    }
</style>
