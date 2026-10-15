import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          const normalizedId = id.replace(/\\/g, '/');
          if (normalizedId.includes('node_modules/katex')) return 'vendor-katex';
          if (normalizedId.includes('node_modules/lucide-react')) return 'vendor-icons';
          if (normalizedId.includes('node_modules/react')) return 'vendor-react';
        },
      },
    },
  },
})
