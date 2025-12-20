<script lang="ts">
    import ViewportSelector from './components/ViewportSelector.svelte';

    // ViewportSelector opens public/viewer.html for the actual viewing
</script>

<main>
    <ViewportSelector />
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
