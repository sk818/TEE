import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
    plugins: [svelte()],
    server: {
        port: 3000,
        fs: {
            // Allow serving files from project root
            allow: ['..']
        }
    },
    build: {
        target: 'esnext',
        // Increase chunk size warning limit for large binary files
        chunkSizeWarningLimit: 10000
    },
    optimizeDeps: {
        exclude: ['zarr']
    }
});
