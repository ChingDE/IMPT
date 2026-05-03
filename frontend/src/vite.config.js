import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],

  server: {
    port: 3000,
    // Dev proxy: forwards /api/* to the local FastAPI server
    // In production, VITE_API_URL points directly to the DO Droplet API
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },

  build: {
    // Vercel reads from this directory (configured in vercel.json / project settings)
    outDir: 'dist',
    emptyOutDir: true,
  },
});
