import { sveltekit } from '@sveltejs/kit/vite';
/// <reference types="vitest" />
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [sveltekit()],
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true,
    host: '127.0.0.1'
  },
  envPrefix: ['VITE_', 'TAURI_'],
  build: {
    target: 'esnext'
  },
  test: {
    // jsdom is required for anything touching window/location; the popstate
    // helpers under test read window.location directly.
    environment: 'jsdom',
    include: ['src/**/*.{test,spec}.{js,ts}'],
    // Keep the run non-watching so `npm test` is usable in CI / build scripts.
    watch: false
  }
});
