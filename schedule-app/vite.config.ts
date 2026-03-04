import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:5001'
    }
  },
  build: {
    outDir: '../app/static/schedule-app',
    emptyOutDir: true,
    cssCodeSplit: false,
    copyPublicDir: false,
    rollupOptions: {
      input: './src/main.tsx',
      output: {
        entryFileNames: 'schedule-app.js',
        chunkFileNames: 'schedule-app-[name].js',
        assetFileNames: (info) => {
          if (info.name?.endsWith('.css')) return 'schedule-app.css'
          return '[name][extname]'
        }
      }
    }
  }
})
