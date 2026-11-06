import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Strip obsolete IE star-property hacks from the original player stylesheet.
  css: { lightningcss: { errorRecovery: true } },
  build: { rolldownOptions: { input: {
    app: fileURLToPath(new URL('./index.html', import.meta.url)),
    player: fileURLToPath(new URL('./player.html', import.meta.url)),
  } } },
  server: { host: '127.0.0.1', port: 3000, strictPort: true },
  preview: { host: '127.0.0.1', port: 3000, strictPort: true },
  test: { include: ['tests/**/*.test.{js,jsx}'] },
});
