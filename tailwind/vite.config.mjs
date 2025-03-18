import { defineConfig } from 'vite';
import { resolve } from 'path';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  // Base path for assets
  base: '/static/',
  build: {
    // Output directory for production build
    outDir: '../haxball_site/static',
    assetsDir: 'tailwind',
    // Generate manifest.json for django-vite
    manifest: 'manifest.json',
    rollupOptions: {
      input: {
        tailwind: resolve('./main.js'),
      },
    },
  },
  plugins: [
    tailwindcss(),
  ],
}); 