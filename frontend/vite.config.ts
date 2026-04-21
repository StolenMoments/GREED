import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.indexOf('node_modules') === -1) return;
          if (id.indexOf('react-markdown') !== -1 || id.indexOf('remark-') !== -1) {
            return 'markdown';
          }
          if (
            id.indexOf('react') !== -1 ||
            id.indexOf('@tanstack') !== -1 ||
            id.indexOf('axios') !== -1
          ) {
            return 'vendor';
          }
        },
      },
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
});
